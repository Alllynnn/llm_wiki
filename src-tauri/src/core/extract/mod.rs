//! Image extraction from PDF and Office files.
//!
//! No Tauri, no AppHandle. The thin `#[tauri::command]` wrappers live in
//! `commands::extract_images`.
//!
//! Sub-modules split along format boundaries:
//! - `pdf`    — PDF image extraction via pdfium
//! - `office` — DOCX/XLSX/PPTX image extraction via zip

pub mod office;
pub mod pdf;

// ── Error type ──────────────────────────────────────────────────────────

#[derive(Debug, thiserror::Error)]
pub enum ExtractError {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("pdfium error: {0}")]
    Pdfium(String),
    #[error("office parser error: {0}")]
    Office(String),
    #[error("image encoding error: {0}")]
    Image(String),
    #[error("invalid argument: {0}")]
    InvalidArgument(String),
    #[error("blocking task panicked: {0}")]
    Panic(String),
    #[error("internal: {0}")]
    Internal(String),
}

impl ExtractError {
    /// Convert a `String` error from `panic_guard::run_guarded` into a typed
    /// variant. Mirrors the heuristic used in `core::vectorstore`.
    pub fn from_guarded(s: String) -> Self {
        if s.starts_with("panic:") || s.contains("panicked") || s.starts_with("Internal error in")
        {
            ExtractError::Panic(s)
        } else {
            ExtractError::Internal(s)
        }
    }
}

// ── Shared data types ───────────────────────────────────────────────────

/// Filter knobs. The defaults mirror what's documented in
/// plans/multimodal-images.md; callers (the TS layer wiring this up)
/// will eventually surface them in Settings.
#[derive(Debug, Clone)]
pub struct ExtractOptions {
    /// Skip images smaller than this on EITHER axis. 100×100 catches
    /// the vast majority of icons / logos / page-corner decorations
    /// without dropping legitimate small chart insets.
    pub min_width: u32,
    pub min_height: u32,
    /// Hard cap on the number of images returned per document. A
    /// pathological 5000-image PDF would otherwise blow up memory
    /// (each image base64'd is ~MB-scale) AND blow up downstream VLM
    /// cost during Phase 3.
    pub max_images: usize,
}

impl Default for ExtractOptions {
    fn default() -> Self {
        Self {
            min_width: 100,
            min_height: 100,
            max_images: 500,
        }
    }
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExtractedImage {
    /// 1-based index in document order. Stable across re-extractions.
    pub index: u32,
    /// MIME type ("image/png" / "image/jpeg" / etc.).
    pub mime_type: String,
    /// 1-based page number for PDFs / 1-based slide number for PPTX.
    /// `None` for DOCX.
    pub page: Option<u32>,
    pub width: u32,
    pub height: u32,
    /// Image bytes, base64-encoded.
    pub data_base64: String,
    /// SHA-256 hex of the encoded bytes.
    pub sha256: String,
}

/// Metadata for an image that's already been written to disk.
/// Mirrors `ExtractedImage` but swaps `data_base64` for `rel_path`.
///
/// `rename_all = "camelCase"` is REQUIRED: the TS layer validates the IPC
/// payload by exact field names (`relPath`, `absPath`, `mimeType`) — without
/// this Serde would emit snake_case names and the validator drops every item.
#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SavedImage {
    pub index: u32,
    pub mime_type: String,
    pub page: Option<u32>,
    pub width: u32,
    pub height: u32,
    /// Path of the written file, relative to `dest_dir_relative_to`.
    pub rel_path: String,
    /// Absolute path on disk.
    pub abs_path: String,
    pub sha256: String,
}

// ── Shared helpers ──────────────────────────────────────────────────────

pub(super) fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    let digest = hasher.finalize();
    hex_encode(&digest)
}

fn hex_encode(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        out.push(HEX[(b >> 4) as usize] as char);
        out.push(HEX[(b & 0x0f) as usize] as char);
    }
    out
}

// ── Tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sha256_hex_is_deterministic_and_64_chars() {
        let h1 = sha256_hex(b"hello world");
        let h2 = sha256_hex(b"hello world");
        assert_eq!(h1, h2);
        assert_eq!(h1.len(), 64);
        // Known SHA-256 of "hello world".
        assert_eq!(
            h1,
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        );
    }

    #[test]
    fn extract_options_defaults_match_plan() {
        let o = ExtractOptions::default();
        assert_eq!(o.min_width, 100);
        assert_eq!(o.min_height, 100);
        assert_eq!(o.max_images, 500);
    }
}

pub(super) fn save_one_image(
    bytes: &[u8],
    dest_dir: &std::path::Path,
    dest_dir_relative_to: &std::path::Path,
    file_name: &str,
) -> Result<(String, String), ExtractError> {
    if !dest_dir.exists() {
        std::fs::create_dir_all(dest_dir)?;
    }
    let abs = dest_dir.join(file_name);
    std::fs::write(&abs, bytes)?;

    let rel = abs
        .strip_prefix(dest_dir_relative_to)
        .map(|p| p.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| file_name.to_string());
    Ok((rel, abs.to_string_lossy().to_string()))
}

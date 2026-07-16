//! Office Open XML (DOCX/XLSX/PPTX) image extraction via zip.
//!
//! Images are embedded verbatim under `<root>/media/` in the zip container.
//! We don't parse surrounding XML to find per-image position — PPTX gets a
//! slide-number heuristic via `.rels` files; DOCX yields `page: None`.

use std::fs::File;
use std::io::Read;
use std::path::Path;

use base64::{engine::general_purpose::STANDARD as B64, Engine as _};

use super::{save_one_image, sha256_hex, ExtractError, ExtractOptions, ExtractedImage, SavedImage};

// ── PPTX / DOCX zip helpers ─────────────────────────────────────────────

fn is_media_path(name: &str) -> bool {
    // PPTX: ppt/media/...    DOCX: word/media/...    XLSX: xl/media/...
    let lower = name.to_ascii_lowercase();
    lower.starts_with("ppt/media/")
        || lower.starts_with("word/media/")
        || lower.starts_with("xl/media/")
}

fn guess_mime_from_name(name: &str) -> Option<String> {
    let ext = Path::new(name)
        .extension()
        .and_then(|e| e.to_str())?
        .to_ascii_lowercase();
    match ext.as_str() {
        "png" => Some("image/png".to_string()),
        "jpg" | "jpeg" => Some("image/jpeg".to_string()),
        "gif" => Some("image/gif".to_string()),
        "webp" => Some("image/webp".to_string()),
        "bmp" => Some("image/bmp".to_string()),
        // Vector formats explicitly skipped — we don't have a
        // rasterizer wired up in this phase.
        _ => None,
    }
}

fn ext_for_mime(mime: &str) -> &'static str {
    match mime {
        "image/png" => "png",
        "image/jpeg" => "jpg",
        "image/gif" => "gif",
        "image/webp" => "webp",
        "image/bmp" => "bmp",
        _ => "bin",
    }
}

/// Walk every `ppt/slides/slide<N>.xml.rels` file and record which
/// `ppt/media/*` files each slide references. Returns a flat map
/// `media_path -> Some(slide_number)`.
fn build_pptx_media_slide_map(
    archive: &mut zip::ZipArchive<File>,
) -> std::collections::HashMap<String, Option<u32>> {
    use std::collections::HashMap;
    let mut out: HashMap<String, Option<u32>> = HashMap::new();

    let rels_paths: Vec<String> = archive
        .file_names()
        .filter(|n| n.starts_with("ppt/slides/_rels/slide") && n.ends_with(".xml.rels"))
        .map(String::from)
        .collect();

    for rels_path in rels_paths {
        let slide_num: Option<u32> = rels_path
            .strip_prefix("ppt/slides/_rels/slide")
            .and_then(|s| s.strip_suffix(".xml.rels"))
            .and_then(|s| s.parse().ok());

        let mut entry = match archive.by_name(&rels_path) {
            Ok(e) => e,
            Err(_) => continue,
        };
        let mut xml = String::new();
        if entry.read_to_string(&mut xml).is_err() {
            continue;
        }

        let mut search_from = 0;
        while let Some(pos) = xml[search_from..].find("Target=\"") {
            let start = search_from + pos + "Target=\"".len();
            let end = match xml[start..].find('"') {
                Some(e) => start + e,
                None => break,
            };
            let target = &xml[start..end];
            search_from = end + 1;

            if let Some(stripped) = target.strip_prefix("../") {
                let canonical = format!("ppt/{stripped}");
                if is_media_path(&canonical) {
                    out.insert(canonical, slide_num);
                }
            }
        }
    }

    out
}

// ── Public extraction functions ─────────────────────────────────────────

/// Office Open XML: extract every embedded image and return as base64.
pub fn extract_images(
    path: &str,
    options: &ExtractOptions,
) -> Result<Vec<ExtractedImage>, ExtractError> {
    let file = File::open(path)?;
    let mut archive = zip::ZipArchive::new(file)
        .map_err(|e| ExtractError::Office(format!("Failed to read zip '{path}': {e}")))?;

    let is_pptx = archive
        .file_names()
        .any(|n| n == "ppt/presentation.xml" || n.starts_with("ppt/slides/slide"));

    let media_to_slide = if is_pptx {
        build_pptx_media_slide_map(&mut archive)
    } else {
        std::collections::HashMap::new()
    };

    let media_indices: Vec<usize> = (0..archive.len())
        .filter(|i| {
            archive
                .by_index_raw(*i)
                .ok()
                .map(|f| is_media_path(f.name()))
                .unwrap_or(false)
        })
        .collect();

    let mut out: Vec<ExtractedImage> = Vec::new();
    let mut idx: u32 = 0;

    for archive_idx in media_indices {
        let mut entry = match archive.by_index(archive_idx) {
            Ok(e) => e,
            Err(e) => {
                eprintln!("[extract_office_images] zip entry {archive_idx} read failed: {e}");
                continue;
            }
        };

        let entry_name = entry.name().to_string();
        let mime_type = guess_mime_from_name(&entry_name);
        if mime_type.is_none() {
            continue;
        }
        let mime_type = mime_type.unwrap();

        let mut bytes = Vec::with_capacity(entry.size() as usize);
        if let Err(e) = entry.read_to_end(&mut bytes) {
            eprintln!("[extract_office_images] read '{entry_name}' failed: {e}");
            continue;
        }

        let (width, height) = match image::load_from_memory(&bytes) {
            Ok(img) => (img.width(), img.height()),
            Err(e) => {
                eprintln!("[extract_office_images] decode '{entry_name}' failed: {e}");
                continue;
            }
        };
        if width < options.min_width || height < options.min_height {
            continue;
        }

        idx += 1;
        let data_base64 = B64.encode(&bytes);
        let sha256 = sha256_hex(&bytes);
        let page = media_to_slide.get(&entry_name).copied().flatten();

        out.push(ExtractedImage {
            index: idx,
            mime_type,
            page,
            width,
            height,
            data_base64,
            sha256,
        });

        if out.len() >= options.max_images {
            eprintln!(
                "[extract_office_images] reached max_images={} cap; remaining skipped",
                options.max_images
            );
            break;
        }
    }

    Ok(out)
}

/// PPTX/DOCX: pull embedded images directly from the zip media/ directory
/// and write each to `dest_dir`. Source format is preserved (PNG stays PNG,
/// JPEG stays JPEG).
pub fn extract_and_save_images(
    path: &str,
    dest_dir: &Path,
    rel_to: &Path,
    options: &ExtractOptions,
) -> Result<Vec<SavedImage>, ExtractError> {
    let file = File::open(path)?;
    let mut archive = zip::ZipArchive::new(file)
        .map_err(|e| ExtractError::Office(format!("Failed to read zip '{path}': {e}")))?;

    let is_pptx = archive
        .file_names()
        .any(|n| n == "ppt/presentation.xml" || n.starts_with("ppt/slides/slide"));
    let media_to_slide = if is_pptx {
        build_pptx_media_slide_map(&mut archive)
    } else {
        std::collections::HashMap::new()
    };

    let media_indices: Vec<usize> = (0..archive.len())
        .filter(|i| {
            archive
                .by_index_raw(*i)
                .ok()
                .map(|f| is_media_path(f.name()))
                .unwrap_or(false)
        })
        .collect();

    let mut out: Vec<SavedImage> = Vec::new();
    let mut idx: u32 = 0;

    for archive_idx in media_indices {
        let mut entry = match archive.by_index(archive_idx) {
            Ok(e) => e,
            Err(e) => {
                eprintln!("[extract_and_save_office_images] zip entry read failed: {e}");
                continue;
            }
        };
        let entry_name = entry.name().to_string();
        let mime_type = match guess_mime_from_name(&entry_name) {
            Some(m) => m,
            None => continue,
        };

        let mut bytes = Vec::with_capacity(entry.size() as usize);
        if let Err(e) = entry.read_to_end(&mut bytes) {
            eprintln!("[extract_and_save_office_images] read '{entry_name}' failed: {e}");
            continue;
        }

        let (width, height) = match image::load_from_memory(&bytes) {
            Ok(img) => (img.width(), img.height()),
            Err(e) => {
                eprintln!("[extract_and_save_office_images] decode '{entry_name}' failed: {e}");
                continue;
            }
        };
        if width < options.min_width || height < options.min_height {
            continue;
        }

        idx += 1;
        let ext = ext_for_mime(&mime_type);
        let file_name = format!("img-{idx}.{ext}");
        let (rel_path, abs_path) = save_one_image(&bytes, dest_dir, rel_to, &file_name)?;
        let sha256 = sha256_hex(&bytes);
        let page = media_to_slide.get(&entry_name).copied().flatten();

        out.push(SavedImage {
            index: idx,
            mime_type,
            page,
            width,
            height,
            rel_path,
            abs_path,
            sha256,
        });

        if out.len() >= options.max_images {
            eprintln!(
                "[extract_and_save_office_images] reached max_images={} cap; skipped rest",
                options.max_images
            );
            break;
        }
    }

    Ok(out)
}

// ── Tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn is_media_path_recognizes_pptx_docx_xlsx() {
        assert!(is_media_path("ppt/media/image1.png"));
        assert!(is_media_path("word/media/image2.jpeg"));
        assert!(is_media_path("xl/media/image3.gif"));
        assert!(!is_media_path("ppt/slides/slide1.xml"));
        assert!(!is_media_path("word/document.xml"));
        assert!(!is_media_path("docProps/thumbnail.jpeg"));
    }

    #[test]
    fn guess_mime_from_name_covers_common_formats() {
        assert_eq!(
            guess_mime_from_name("ppt/media/image1.PNG"),
            Some("image/png".to_string())
        );
        assert_eq!(
            guess_mime_from_name("word/media/image2.jpeg"),
            Some("image/jpeg".to_string())
        );
        assert_eq!(
            guess_mime_from_name("ppt/media/image3.jpg"),
            Some("image/jpeg".to_string())
        );
        // Vector formats deliberately rejected.
        assert_eq!(guess_mime_from_name("ppt/media/foo.svg"), None);
        assert_eq!(guess_mime_from_name("ppt/media/foo.emf"), None);
    }
}

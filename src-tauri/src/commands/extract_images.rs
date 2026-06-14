//! Tauri command wrappers for image extraction.
//!
//! All logic, data types, and tests live in `crate::core::extract`.
//! Each function here is a thin `#[tauri::command]` shim that delegates
//! immediately to the appropriate `core::extract::{pdf,office}` function.

use std::path::Path;

// Re-export the shared types so that code importing from
// `commands::extract_images` (e.g. `commands::fs`) continues to compile
// without any import-path changes.
pub use crate::core::extract::{ExtractOptions, ExtractedImage, SavedImage};

/// Re-export `extract_pdf_markdown` at the commands level so `commands::fs`
/// can call it as `crate::commands::extract_images::extract_pdf_markdown`.
pub use crate::core::extract::pdf::extract_markdown as extract_pdf_markdown;

#[tauri::command]
pub async fn extract_pdf_images_cmd(path: String) -> Result<Vec<ExtractedImage>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        crate::panic_guard::run_guarded("extract_pdf_images", || {
            crate::core::extract::pdf::extract_images(&path, &ExtractOptions::default())
                .map_err(|e| e.to_string())
        })
    })
    .await
    .map_err(|e| format!("extract_pdf_images blocking task join error: {e}"))?
}

#[tauri::command]
pub async fn extract_office_images_cmd(path: String) -> Result<Vec<ExtractedImage>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        crate::panic_guard::run_guarded("extract_office_images", || {
            crate::core::extract::office::extract_images(&path, &ExtractOptions::default())
                .map_err(|e| e.to_string())
        })
    })
    .await
    .map_err(|e| format!("extract_office_images blocking task join error: {e}"))?
}

#[tauri::command]
pub async fn extract_and_save_pdf_images_cmd(
    source_path: String,
    dest_dir: String,
    rel_to: String,
) -> Result<Vec<SavedImage>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        crate::panic_guard::run_guarded("extract_and_save_pdf_images", || {
            crate::core::extract::pdf::extract_and_save_images(
                &source_path,
                Path::new(&dest_dir),
                Path::new(&rel_to),
                &ExtractOptions::default(),
            )
            .map_err(|e| e.to_string())
        })
    })
    .await
    .map_err(|e| format!("extract_and_save_pdf_images blocking task join error: {e}"))?
}

#[tauri::command]
pub async fn extract_and_save_office_images_cmd(
    source_path: String,
    dest_dir: String,
    rel_to: String,
) -> Result<Vec<SavedImage>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        crate::panic_guard::run_guarded("extract_and_save_office_images", || {
            crate::core::extract::office::extract_and_save_images(
                &source_path,
                Path::new(&dest_dir),
                Path::new(&rel_to),
                &ExtractOptions::default(),
            )
            .map_err(|e| e.to_string())
        })
    })
    .await
    .map_err(|e| format!("extract_and_save_office_images blocking task join error: {e}"))?
}

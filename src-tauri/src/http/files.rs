//! HTTP handler for file preview bytes.

use axum::body::Body;
use axum::extract::{Query, State};
use axum::http::{header, StatusCode};
use axum::response::Response;
use axum::routing::{get, post};
use axum::Router;
use serde::Deserialize;

use crate::http::auth::AuthUser;
use crate::http::error::ApiError;
use crate::http::AppState;
use crate::storage::paths::{resolve_project_path, resolve_under, PathError};

pub fn files_router() -> Router<AppState> {
    Router::new()
        .route("/api/v1/files/raw", get(raw))
        .route("/api/v1/files/extracted-text", get(extracted_text))
        .route("/api/v1/files/extract-images", post(extract_images))
}

#[derive(Debug, Deserialize)]
struct RawQuery {
    /// Two accepted shapes, in priority order:
    ///   (a) `project_path` + `path` — project_path can be absolute (under
    ///       projects_root) or relative; `path` is project-relative.
    ///   (b) Only `path` — must be an absolute path under projects_root.
    /// Legacy callers in the migrated frontend send (b); newer callers should
    /// prefer (a) because it's path-safer.
    #[serde(default)]
    project_path: Option<String>,
    path: String,
}

async fn raw(
    State(state): State<AppState>,
    AuthUser(_user): AuthUser,
    Query(q): Query<RawQuery>,
) -> Result<Response, ApiError> {
    let projects_root = &state.config.projects_root;

    let file_path = match q.project_path.as_deref() {
        Some(pp) if !pp.is_empty() => {
            let project_root = resolve_project_path(projects_root, pp).map_err(|e| {
                ApiError::bad_request("PATH_ESCAPE", e.to_string())
                    .with_details(serde_json::json!({ "requested": pp }))
            })?;
            resolve_under(&project_root, &q.path).map_err(|e| match e {
                PathError::NotFound => ApiError::new(
                    StatusCode::NOT_FOUND,
                    "NOT_FOUND",
                    format!("file not found: {}", q.path),
                ),
                _ => ApiError::bad_request("PATH_ESCAPE", e.to_string())
                    .with_details(serde_json::json!({ "requested": q.path })),
            })?
        }
        _ => {
            // Single absolute path — must be under projects_root.
            resolve_project_path(projects_root, &q.path).map_err(|e| match e {
                PathError::NotFound => ApiError::new(
                    StatusCode::NOT_FOUND,
                    "NOT_FOUND",
                    format!("file not found: {}", q.path),
                ),
                _ => ApiError::bad_request("PATH_ESCAPE", e.to_string())
                    .with_details(serde_json::json!({ "requested": q.path })),
            })?
        }
    };

    if !file_path.is_file() {
        return Err(ApiError::new(
            StatusCode::NOT_FOUND,
            "NOT_FOUND",
            format!("file not found: {}", q.path),
        ));
    }

    let bytes = tokio::fs::read(&file_path)
        .await
        .map_err(|e| match e.kind() {
            std::io::ErrorKind::NotFound => ApiError::new(
                StatusCode::NOT_FOUND,
                "NOT_FOUND",
                format!("file not found: {}", q.path),
            ),
            _ => ApiError::internal(e.to_string()),
        })?;

    let mime = mime_guess::from_path(&file_path).first_or_octet_stream();
    let resp = Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, mime.as_ref())
        .body(Body::from(bytes))
        .unwrap();
    // No caching headers for now — the frontend can re-fetch as needed.
    Ok(resp)
}

// ── Extracted text preview ───────────────────────────────────────────────────
//
// Plain-text extraction of PDF (and eventually DOCX/PPTX) for the preview
// pane. The desktop pipeline used pdfium-via-Tauri for this; we now expose
// it as an HTTP endpoint so the React preview can request text directly
// instead of trying to render raw binary bytes as a string.

async fn extracted_text(
    State(state): State<AppState>,
    AuthUser(_user): AuthUser,
    Query(q): Query<RawQuery>,
) -> Result<Response, ApiError> {
    let projects_root = &state.config.projects_root;

    let file_path = match q.project_path.as_deref() {
        Some(pp) if !pp.is_empty() => {
            let project_root = resolve_project_path(projects_root, pp).map_err(|e| {
                ApiError::bad_request("PATH_ESCAPE", e.to_string())
                    .with_details(serde_json::json!({ "requested": pp }))
            })?;
            resolve_under(&project_root, &q.path).map_err(|e| match e {
                PathError::NotFound => ApiError::new(
                    StatusCode::NOT_FOUND,
                    "NOT_FOUND",
                    format!("file not found: {}", q.path),
                ),
                _ => ApiError::bad_request("PATH_ESCAPE", e.to_string())
                    .with_details(serde_json::json!({ "requested": q.path })),
            })?
        }
        _ => resolve_project_path(projects_root, &q.path).map_err(|e| match e {
            PathError::NotFound => ApiError::new(
                StatusCode::NOT_FOUND,
                "NOT_FOUND",
                format!("file not found: {}", q.path),
            ),
            _ => ApiError::bad_request("PATH_ESCAPE", e.to_string())
                .with_details(serde_json::json!({ "requested": q.path })),
        })?,
    };

    if !file_path.is_file() {
        return Err(ApiError::new(
            StatusCode::NOT_FOUND,
            "NOT_FOUND",
            format!("file not found: {}", q.path),
        ));
    }

    let ext = file_path
        .extension()
        .and_then(|s| s.to_str())
        .map(|s| s.to_lowercase())
        .unwrap_or_default();

    let path_string = file_path.to_string_lossy().to_string();
    const OFFICE_TEXT_EXTS: &[&str] = &["doc", "docx", "pptx", "xls", "xlsx", "odt", "ods", "odp"];

    // Dispatch to the right extractor by extension. PDFium, Office parsers,
    // calamine, and zip parsing all block; run them on worker threads so the
    // axum runtime stays responsive.
    let text = match ext.as_str() {
        "pdf" => tokio::task::spawn_blocking(move || {
            crate::core::files::extract_pdf_text(&path_string, false)
        })
        .await
        .map_err(|e| ApiError::internal(format!("blocking task panicked: {e}")))?
        .map_err(|msg| ApiError::internal(format!("pdf extract: {msg}")))?,
        e if OFFICE_TEXT_EXTS.contains(&e) => {
            let ext_for_task = ext.clone();
            tokio::task::spawn_blocking(move || {
                crate::core::files::extract_office_text(&path_string, &ext_for_task)
            })
            .await
            .map_err(|e| ApiError::internal(format!("blocking task panicked: {e}")))?
            .map_err(|msg| ApiError::internal(format!("office extract: {msg}")))?
        }
        _ => {
            return Err(ApiError::new(
                StatusCode::UNSUPPORTED_MEDIA_TYPE,
                "UNSUPPORTED",
                format!("no text extractor for .{}", ext),
            ));
        }
    };

    let resp = Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, "text/plain; charset=utf-8")
        .body(Body::from(text))
        .unwrap();
    Ok(resp)
}

// ── Extract embedded images ─────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct ExtractImagesRequest {
    project_path: String,
    source_path: String,
    dest_dir: String,
    rel_to: String,
}

async fn extract_images(
    State(state): State<AppState>,
    AuthUser(_user): AuthUser,
    axum::Json(req): axum::Json<ExtractImagesRequest>,
) -> Result<axum::Json<serde_json::Value>, ApiError> {
    let project_root = resolve_project_path(&state.config.projects_root, &req.project_path)
        .map_err(|e| {
            ApiError::bad_request("PATH_ESCAPE", e.to_string())
                .with_details(serde_json::json!({ "requested": req.project_path }))
        })?;

    let source_path = resolve_existing_under_project(&project_root, &req.source_path)?;
    let dest_dir = resolve_writable_under_project(&project_root, &req.dest_dir)?;
    let rel_to = resolve_writable_under_project(&project_root, &req.rel_to)?;

    let ext = source_path
        .extension()
        .and_then(|s| s.to_str())
        .map(|s| s.to_lowercase())
        .unwrap_or_default();

    let source_string = source_path.to_string_lossy().to_string();
    let images = match ext.as_str() {
        "pdf" => {
            let dest = dest_dir.clone();
            let rel = rel_to.clone();
            tokio::task::spawn_blocking(move || {
                crate::core::extract::pdf::extract_and_save_images(
                    &source_string,
                    &dest,
                    &rel,
                    &crate::core::extract::ExtractOptions::default(),
                )
            })
            .await
            .map_err(|e| ApiError::internal(format!("blocking task panicked: {e}")))?
            .map_err(|e| ApiError::internal(format!("pdf image extract: {e}")))?
        }
        "docx" | "pptx" => {
            let dest = dest_dir.clone();
            let rel = rel_to.clone();
            tokio::task::spawn_blocking(move || {
                crate::core::extract::office::extract_and_save_images(
                    &source_string,
                    &dest,
                    &rel,
                    &crate::core::extract::ExtractOptions::default(),
                )
            })
            .await
            .map_err(|e| ApiError::internal(format!("blocking task panicked: {e}")))?
            .map_err(|e| ApiError::internal(format!("office image extract: {e}")))?
        }
        _ => Vec::new(),
    };

    Ok(axum::Json(serde_json::to_value(images).map_err(|e| {
        ApiError::internal(format!("serialize extracted images: {e}"))
    })?))
}

fn resolve_existing_under_project(
    project_root: &std::path::Path,
    raw: &str,
) -> Result<std::path::PathBuf, ApiError> {
    if raw.trim().is_empty() {
        return Err(ApiError::bad_request(
            "BAD_REQUEST",
            "path must not be empty",
        ));
    }
    let p = std::path::Path::new(raw);
    let target = if p.is_absolute() {
        p.canonicalize()
            .map_err(|e| ApiError::bad_request("PATH_ESCAPE", e.to_string()))?
    } else {
        resolve_under(project_root, raw).map_err(|e| match e {
            PathError::NotFound => ApiError::new(
                StatusCode::NOT_FOUND,
                "NOT_FOUND",
                format!("file not found: {raw}"),
            ),
            _ => ApiError::bad_request("PATH_ESCAPE", e.to_string())
                .with_details(serde_json::json!({ "requested": raw })),
        })?
    };
    ensure_under_project(project_root, &target)?;
    Ok(target)
}

fn resolve_writable_under_project(
    project_root: &std::path::Path,
    raw: &str,
) -> Result<std::path::PathBuf, ApiError> {
    if raw.trim().is_empty() {
        return Err(ApiError::bad_request(
            "BAD_REQUEST",
            "path must not be empty",
        ));
    }
    let p = std::path::Path::new(raw);
    let candidate = if p.is_absolute() {
        let mut ancestor = p;
        loop {
            if ancestor.exists() {
                break;
            }
            match ancestor.parent() {
                Some(parent) if parent != ancestor => ancestor = parent,
                _ => break,
            }
        }
        ensure_under_project(
            project_root,
            &ancestor
                .canonicalize()
                .map_err(|e| ApiError::bad_request("PATH_ESCAPE", e.to_string()))?,
        )?;
        p.to_path_buf()
    } else {
        for component in p.components() {
            if matches!(
                component,
                std::path::Component::ParentDir
                    | std::path::Component::Prefix(_)
                    | std::path::Component::RootDir
            ) {
                return Err(ApiError::bad_request(
                    "PATH_ESCAPE",
                    ".. or root segments not allowed",
                ));
            }
        }
        project_root.join(raw)
    };
    Ok(candidate)
}

fn ensure_under_project(
    project_root: &std::path::Path,
    target: &std::path::Path,
) -> Result<(), ApiError> {
    let root = project_root
        .canonicalize()
        .map_err(|e| ApiError::internal(format!("project root: {e}")))?;
    if !target.starts_with(root) {
        return Err(ApiError::bad_request(
            "PATH_ESCAPE",
            "path is outside project root",
        ));
    }
    Ok(())
}

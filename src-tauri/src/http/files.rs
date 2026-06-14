//! HTTP handler for file preview bytes.

use axum::body::Body;
use axum::extract::{Query, State};
use axum::http::{header, StatusCode};
use axum::response::Response;
use axum::routing::get;
use axum::Router;
use serde::Deserialize;

use crate::http::auth::AuthUser;
use crate::http::error::ApiError;
use crate::http::AppState;
use crate::storage::paths::{resolve_under, PathError};

pub fn files_router() -> Router<AppState> {
    Router::new().route("/api/v1/files/raw", get(raw))
}

#[derive(Debug, Deserialize)]
struct RawQuery {
    project_path: String,
    path: String,
}

async fn raw(
    State(state): State<AppState>,
    AuthUser(_user): AuthUser,
    Query(q): Query<RawQuery>,
) -> Result<Response, ApiError> {
    let project_root =
        resolve_under(&state.config.projects_root, &q.project_path).map_err(|e| {
            ApiError::bad_request("PATH_ESCAPE", e.to_string())
                .with_details(serde_json::json!({ "requested": q.project_path }))
        })?;
    let file_path = resolve_under(&project_root, &q.path).map_err(|e| match e {
        PathError::NotFound => ApiError::new(
            StatusCode::NOT_FOUND,
            "NOT_FOUND",
            format!("file not found: {}", q.path),
        ),
        _ => ApiError::bad_request("PATH_ESCAPE", e.to_string())
            .with_details(serde_json::json!({ "requested": q.path })),
    })?;

    if !file_path.is_file() {
        return Err(ApiError::new(
            StatusCode::NOT_FOUND,
            "NOT_FOUND",
            format!("file not found: {}", q.path),
        ));
    }

    let bytes = tokio::fs::read(&file_path).await.map_err(|e| match e.kind() {
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

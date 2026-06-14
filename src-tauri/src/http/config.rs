//! HTTP handlers for per-user opaque JSON config.

use axum::extract::State;
use axum::routing::get;
use axum::{Json, Router};

use crate::http::auth::AuthUser;
use crate::http::error::ApiError;
use crate::http::AppState;

pub fn config_router() -> Router<AppState> {
    Router::new().route("/api/v1/config", get(get_config).put(put_config))
}

async fn get_config(
    State(state): State<AppState>,
    AuthUser(user): AuthUser,
) -> Result<Json<serde_json::Value>, ApiError> {
    let cfg = state
        .user_data
        .load_config(&user.id)
        .map_err(|e| ApiError::internal(e.to_string()))?;
    Ok(Json(cfg))
}

async fn put_config(
    State(state): State<AppState>,
    AuthUser(user): AuthUser,
    Json(body): Json<serde_json::Value>,
) -> Result<axum::http::StatusCode, ApiError> {
    state
        .user_data
        .save_config(&user.id, &body)
        .map_err(|e| ApiError::internal(e.to_string()))?;
    Ok(axum::http::StatusCode::OK)
}

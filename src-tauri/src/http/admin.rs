//! Admin endpoints for syncing per-user permissions from an external panel.
//!
//! Protected by the shared bridge secret (`LLM_WIKI_BRIDGE_SECRET`) sent in the
//! `X-Wiki-Bridge-Secret` header — the same trust boundary as bridge login.
//! These routes are mounted outside the session-auth layer.

use axum::extract::State;
use axum::http::HeaderMap;
use axum::routing::put;
use axum::{Json, Router};

use crate::auth::permissions::{Permissions, PermissionsFile};
use crate::http::error::ApiError;
use crate::http::AppState;

pub fn admin_router() -> Router<AppState> {
    Router::new().route("/api/v1/admin/permissions", put(put_permissions))
}

fn check_bridge_secret(state: &AppState, headers: &HeaderMap) -> Result<(), ApiError> {
    let configured = state.config.bridge_secret.as_deref();
    let provided = headers
        .get("X-Wiki-Bridge-Secret")
        .and_then(|v| v.to_str().ok());
    match (configured, provided) {
        (Some(s), Some(p)) if crate::http::access::secret_eq(p, s) => Ok(()),
        _ => Err(ApiError::unauthenticated()),
    }
}

/// `PUT /api/v1/admin/permissions` — replace the whole permissions file.
async fn put_permissions(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<PermissionsFile>,
) -> Result<Json<serde_json::Value>, ApiError> {
    check_bridge_secret(&state, &headers)?;
    Permissions::save(&state.config.data_root, &body)
        .map_err(|e| ApiError::internal(format!("could not save permissions: {e}")))?;
    Ok(Json(serde_json::json!({
        "ok": true,
        "admins": body.admins.len(),
        "users": body.access.len(),
    })))
}

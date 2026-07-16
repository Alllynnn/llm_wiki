//! Session cookie middleware + `AuthUser` extractor.

use axum::extract::{FromRequestParts, Json as ExtractJson, State};
use axum::http::request::Parts;
use axum::http::StatusCode;
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::json;
use tower_cookies::{cookie::SameSite, Cookie, Cookies};

use crate::auth::users::User;
use crate::http::error::ApiError;
use crate::http::AppState;

// 30 days in seconds — matches Sessions DEFAULT_SESSION_TTL_SECS
const COOKIE_MAX_AGE_SECS: i64 = 60 * 60 * 24 * 30;

#[derive(Debug, Deserialize)]
pub struct LoginRequest {
    pub username: String,
    pub password: String,
}

pub fn auth_router() -> Router<AppState> {
    Router::new()
        .route("/api/v1/auth/login", post(login))
        .route("/api/v1/auth/bridge-login", post(bridge_login))
        .route("/api/v1/auth/logout", post(logout))
        .route("/api/v1/auth/whoami", get(whoami))
}

/// Body for `POST /api/v1/auth/bridge-login`.
///
/// Used by a trusted front-door (the admin panel) that has already
/// authenticated a real person (e.g. via Feishu SSO). It mints a wiki session
/// for that identity without requiring a `users.toml` account. Protected by a
/// shared secret (`LLM_WIKI_BRIDGE_SECRET`).
#[derive(Debug, Deserialize)]
pub struct BridgeLoginRequest {
    pub user_id: String,
    pub username: String,
    pub secret: String,
}

async fn bridge_login(
    State(state): State<AppState>,
    cookies: Cookies,
    ExtractJson(body): ExtractJson<BridgeLoginRequest>,
) -> Result<axum::response::Response, ApiError> {
    match state.config.bridge_secret.as_deref() {
        Some(secret) if crate::http::access::secret_eq(&body.secret, secret) => {}
        _ => return Err(ApiError::invalid_credentials()),
    }
    if body.user_id.trim().is_empty() {
        return Err(ApiError::bad_request("BAD_REQUEST", "user_id is required"));
    }

    let session_id = state
        .sessions
        .create_named(&body.user_id, Some(body.username.clone()))
        .map_err(|e| ApiError::internal(format!("could not create session: {e}")))?;

    let cookie = Cookie::build((
        state.config.session_cookie_name.clone(),
        session_id.as_str().to_string(),
    ))
    .http_only(true)
    .same_site(SameSite::Lax)
    .max_age(tower_cookies::cookie::time::Duration::seconds(COOKIE_MAX_AGE_SECS))
    .path("/")
    .build();
    cookies.add(cookie);

    Ok((
        StatusCode::OK,
        Json(json!({"user_id": body.user_id, "username": body.username})),
    )
        .into_response())
}

async fn login(
    State(state): State<AppState>,
    cookies: Cookies,
    ExtractJson(body): ExtractJson<LoginRequest>,
) -> Result<axum::response::Response, ApiError> {
    let user = state
        .users
        .verify_password(&body.username, &body.password)
        .map_err(|_| ApiError::invalid_credentials())?;

    let session_id = state
        .sessions
        .create(&user.id)
        .map_err(|e| ApiError::internal(format!("could not create session: {e}")))?;

    let cookie = Cookie::build((
        state.config.session_cookie_name.clone(),
        session_id.as_str().to_string(),
    ))
    .http_only(true)
    .same_site(SameSite::Lax)
    .max_age(tower_cookies::cookie::time::Duration::seconds(COOKIE_MAX_AGE_SECS))
    .path("/")
    .build();
    cookies.add(cookie);

    Ok((
        StatusCode::OK,
        Json(json!({"user_id": user.id, "username": user.username})),
    )
        .into_response())
}

async fn logout(
    State(state): State<AppState>,
    cookies: Cookies,
) -> Result<StatusCode, ApiError> {
    if let Some(cookie) = cookies.get(&state.config.session_cookie_name) {
        // Best-effort delete — even if sled errors, we still want to clear
        // the client cookie below.
        let _ = state.sessions.delete(cookie.value());
    }
    // Mirror the login cookie's attributes minus Max-Age so the browser
    // recognizes this as the same cookie and deletes it cleanly. RFC 6265
    // only requires matching Name+Domain+Path for deletion, but matching
    // all the security attrs avoids confusing strict cookie audits.
    let empty = Cookie::build((state.config.session_cookie_name.clone(), ""))
        .http_only(true)
        .same_site(SameSite::Lax)
        .max_age(tower_cookies::cookie::time::Duration::seconds(0))
        .path("/")
        .build();
    cookies.add(empty);
    Ok(StatusCode::NO_CONTENT)
}

async fn whoami(
    State(state): State<AppState>,
    AuthUser(user): AuthUser,
) -> Json<serde_json::Value> {
    let recently_opened = state.user_data.recently_opened(&user.id);
    Json(json!({
        "user_id": user.id,
        "username": user.username,
        "recently_opened": recently_opened,
    }))
}

/// Extractor that yields the authenticated user, or 401 if missing.
///
/// `session_middleware` is responsible for placing the `User` into request
/// extensions. Routes mounted under the authed router get the middleware
/// automatically; legacy 127.0.0.1:19828 routes do not.
#[derive(Debug, Clone)]
pub struct AuthUser(pub User);

impl<S> FromRequestParts<S> for AuthUser
where
    S: Send + Sync,
{
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        parts
            .extensions
            .get::<User>()
            .cloned()
            .map(AuthUser)
            .ok_or_else(ApiError::unauthenticated)
    }
}

/// Middleware: read the session cookie, look up the session, look up the
/// user. On hit, inject `User` into request extensions. On miss, do nothing
/// (the request proceeds; only routes that extract `AuthUser` will reject).
pub async fn session_middleware(
    State(state): State<AppState>,
    cookies: Cookies,
    mut request: axum::extract::Request,
    next: Next,
) -> Response {
    if let Some(cookie) = cookies.get(&state.config.session_cookie_name) {
        if let Some((user_id, display_name)) = state.sessions.lookup_full(cookie.value()) {
            // Bridge sessions carry their own display name and are not backed
            // by users.toml; password sessions resolve the User by id.
            let user = match display_name {
                Some(username) => Some(User { id: user_id, username }),
                None => state.users.lookup_user(&user_id),
            };
            if let Some(user) = user {
                request.extensions_mut().insert(user);
            }
        }
    }
    next.run(request).await
}

/// Middleware: enforce that a `User` is present in request extensions.
///
/// This is used for routes whose handlers do not extract `AuthUser` themselves
/// (e.g. agent endpoints, which must remain auth-free on the legacy listener).
/// On the main listener, mount this middleware via `route_layer` after
/// `session_middleware` has already run.
pub async fn require_auth_middleware(
    request: axum::extract::Request,
    next: Next,
) -> Response {
    if request.extensions().get::<User>().is_none() {
        return ApiError::unauthenticated().into_response();
    }
    next.run(request).await
}

//! Uniform API error response.

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Serialize;
use serde_json::Value;

#[derive(Debug, Serialize)]
pub struct ApiError {
    #[serde(skip)]
    pub status: StatusCode,
    pub code: &'static str,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<Value>,
}

#[derive(Debug, Serialize)]
struct ErrorEnvelope<'a> {
    error: ErrorBody<'a>,
}

#[derive(Debug, Serialize)]
struct ErrorBody<'a> {
    code: &'a str,
    message: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    details: Option<&'a Value>,
}

impl ApiError {
    pub fn new(status: StatusCode, code: &'static str, message: impl Into<String>) -> Self {
        Self {
            status,
            code,
            message: message.into(),
            details: None,
        }
    }

    pub fn with_details(mut self, details: Value) -> Self {
        self.details = Some(details);
        self
    }

    // --- Phase-2 helper constructors ---

    pub fn unauthenticated() -> Self {
        Self::new(StatusCode::UNAUTHORIZED, "UNAUTHENTICATED", "authentication required")
    }

    pub fn invalid_credentials() -> Self {
        Self::new(StatusCode::UNAUTHORIZED, "INVALID_CREDENTIALS", "invalid username or password")
    }

    pub fn internal(message: impl Into<String>) -> Self {
        Self::new(StatusCode::INTERNAL_SERVER_ERROR, "INTERNAL", message)
    }

    pub fn bad_request(code: &'static str, message: impl Into<String>) -> Self {
        Self::new(StatusCode::BAD_REQUEST, code, message)
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let envelope = ErrorEnvelope {
            error: ErrorBody {
                code: self.code,
                message: &self.message,
                details: self.details.as_ref(),
            },
        };
        (self.status, Json(envelope)).into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;

    #[tokio::test]
    async fn unauthenticated_renders_401_with_uniform_shape() {
        let err = ApiError::unauthenticated();
        let resp = err.into_response();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
        let body = to_bytes(resp.into_body(), 4096).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(v["error"]["code"], "UNAUTHENTICATED");
        assert_eq!(v["error"]["message"], "authentication required");
        assert!(v["error"]["details"].is_null() || !v["error"].as_object().unwrap().contains_key("details"));
    }

    #[tokio::test]
    async fn invalid_credentials_renders_401_with_correct_code() {
        let resp = ApiError::invalid_credentials().into_response();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
        let body = to_bytes(resp.into_body(), 4096).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(v["error"]["code"], "INVALID_CREDENTIALS");
    }

    #[tokio::test]
    async fn with_details_serializes_details() {
        let err = ApiError::bad_request("PATH_ESCAPE", "path escapes root")
            .with_details(serde_json::json!({"requested": "../etc/passwd"}));
        let resp = err.into_response();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
        let body = to_bytes(resp.into_body(), 4096).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(v["error"]["code"], "PATH_ESCAPE");
        assert_eq!(v["error"]["details"]["requested"], "../etc/passwd");
    }

    #[tokio::test]
    async fn internal_renders_500() {
        let resp = ApiError::internal("boom").into_response();
        assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
        let body = to_bytes(resp.into_body(), 4096).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(v["error"]["code"], "INTERNAL");
        assert_eq!(v["error"]["message"], "boom");
    }
}

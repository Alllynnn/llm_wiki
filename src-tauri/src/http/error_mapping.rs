//! `From<XError> for ApiError` impls for every `core::*` error type.
//!
//! These impls allow HTTP handlers to use `?` on core functions and have
//! errors automatically converted to the uniform API error envelope.

use axum::http::StatusCode;

use crate::http::error::ApiError;

// ──────────────────────────────────────────────────────────────────────────
// VectorstoreError
// ──────────────────────────────────────────────────────────────────────────

use crate::core::vectorstore::VectorstoreError;

impl From<VectorstoreError> for ApiError {
    fn from(err: VectorstoreError) -> Self {
        match err {
            VectorstoreError::InvalidArgument(msg) => ApiError::bad_request("BAD_REQUEST", msg),
            VectorstoreError::Io(e) if e.kind() == std::io::ErrorKind::NotFound => {
                ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", e.to_string())
            }
            VectorstoreError::Io(e) => ApiError::internal(e.to_string()),
            VectorstoreError::Lance(s) => ApiError::internal(s),
            VectorstoreError::Arrow(s) => ApiError::internal(s),
            VectorstoreError::Panic(s) => ApiError::internal(format!("panic: {s}")),
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// SearchError
// ──────────────────────────────────────────────────────────────────────────

use crate::core::search::SearchError;

impl From<SearchError> for ApiError {
    fn from(err: SearchError) -> Self {
        match err {
            SearchError::InvalidArgument(msg) => ApiError::bad_request("BAD_REQUEST", msg),
            SearchError::Io(e) if e.kind() == std::io::ErrorKind::NotFound => {
                ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", e.to_string())
            }
            SearchError::Io(e) => ApiError::internal(e.to_string()),
            SearchError::Vectorstore(e) => ApiError::from(e),
            SearchError::Internal(s) => ApiError::internal(s),
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// ExtractError
// ──────────────────────────────────────────────────────────────────────────

use crate::core::extract::ExtractError;

impl From<ExtractError> for ApiError {
    fn from(err: ExtractError) -> Self {
        match err {
            ExtractError::InvalidArgument(msg) => ApiError::bad_request("BAD_REQUEST", msg),
            ExtractError::Io(e) if e.kind() == std::io::ErrorKind::NotFound => {
                ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", e.to_string())
            }
            ExtractError::Io(e) => ApiError::internal(e.to_string()),
            ExtractError::Pdfium(s) => ApiError::internal(s),
            ExtractError::Office(s) => ApiError::internal(s),
            ExtractError::Image(s) => ApiError::internal(s),
            ExtractError::Panic(s) => ApiError::internal(format!("panic: {s}")),
            ExtractError::Internal(s) => ApiError::internal(s),
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// FilesError
// ──────────────────────────────────────────────────────────────────────────

use crate::core::files::FilesError;

impl From<FilesError> for ApiError {
    fn from(err: FilesError) -> Self {
        match err {
            FilesError::InvalidArgument(msg) => ApiError::bad_request("BAD_REQUEST", msg),
            FilesError::NotFound(msg) => ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", msg),
            FilesError::Io(e) if e.kind() == std::io::ErrorKind::NotFound => {
                ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", e.to_string())
            }
            FilesError::Io(e) => ApiError::internal(e.to_string()),
            FilesError::Join(s) => ApiError::internal(format!("panic: {s}")),
            FilesError::Internal(s) => ApiError::internal(s),
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// WikiError
// ──────────────────────────────────────────────────────────────────────────

use crate::core::wiki::WikiError;

impl From<WikiError> for ApiError {
    fn from(err: WikiError) -> Self {
        match err {
            WikiError::Io(e) if e.kind() == std::io::ErrorKind::NotFound => {
                ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", e.to_string())
            }
            WikiError::Io(e) => ApiError::internal(e.to_string()),
            WikiError::Join(s) => ApiError::internal(format!("panic: {s}")),
            WikiError::Internal(s) => ApiError::internal(s),
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// FsOpsError
// ──────────────────────────────────────────────────────────────────────────

use crate::core::fs_ops::FsOpsError;

impl From<FsOpsError> for ApiError {
    fn from(err: FsOpsError) -> Self {
        match err {
            FsOpsError::InvalidArgument(msg) => ApiError::bad_request("BAD_REQUEST", msg),
            FsOpsError::NotFound(msg) => ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", msg),
            FsOpsError::Io(e) if e.kind() == std::io::ErrorKind::NotFound => {
                ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", e.to_string())
            }
            FsOpsError::Io(e) => ApiError::internal(e.to_string()),
            FsOpsError::Join(s) => ApiError::internal(format!("panic: {s}")),
            FsOpsError::Internal(s) => ApiError::internal(s),
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// ProjectError
// ──────────────────────────────────────────────────────────────────────────

use crate::core::project::ProjectError;

impl From<ProjectError> for ApiError {
    fn from(err: ProjectError) -> Self {
        match err {
            ProjectError::InvalidArgument(msg) => ApiError::bad_request("BAD_REQUEST", msg),
            ProjectError::NotFound(msg) => ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", msg),
            ProjectError::AlreadyExists(msg) => {
                ApiError::new(StatusCode::CONFLICT, "ALREADY_EXISTS", msg)
            }
            ProjectError::Io(e) if e.kind() == std::io::ErrorKind::NotFound => {
                ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", e.to_string())
            }
            ProjectError::Io(e) => ApiError::internal(e.to_string()),
            ProjectError::Template(s) => ApiError::internal(s),
            ProjectError::Internal(s) => ApiError::internal(s),
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// IngestQueueError
// ──────────────────────────────────────────────────────────────────────────

use crate::core::ingest_queue::IngestQueueError;

impl From<IngestQueueError> for ApiError {
    fn from(err: IngestQueueError) -> Self {
        match err {
            IngestQueueError::Io(e) if e.kind() == std::io::ErrorKind::NotFound => {
                ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", e.to_string())
            }
            IngestQueueError::Io(e) => ApiError::internal(e.to_string()),
            IngestQueueError::Json(s) => ApiError::internal(s),
            IngestQueueError::Internal(s) => ApiError::internal(s),
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// FileSyncError
// ──────────────────────────────────────────────────────────────────────────

use crate::core::file_sync::FileSyncError;

impl From<FileSyncError> for ApiError {
    fn from(err: FileSyncError) -> Self {
        match err {
            FileSyncError::InvalidArgument(msg) => ApiError::bad_request("BAD_REQUEST", msg),
            FileSyncError::Io(e) if e.kind() == std::io::ErrorKind::NotFound => {
                ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", e.to_string())
            }
            FileSyncError::Io(e) => ApiError::internal(e.to_string()),
            FileSyncError::Notify(s) => ApiError::internal(s),
            FileSyncError::Queue(e) => ApiError::from(e),
            FileSyncError::Internal(s) => ApiError::internal(s),
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// LlmError
// ──────────────────────────────────────────────────────────────────────────

use crate::core::llm_client::LlmError;

impl From<LlmError> for ApiError {
    fn from(err: LlmError) -> Self {
        match err {
            LlmError::InvalidConfig(msg) => {
                ApiError::bad_request("LLM_PROVIDER_NOT_CONFIGURED", msg)
            }
            LlmError::Timeout => ApiError::new(
                StatusCode::GATEWAY_TIMEOUT,
                "LLM_PROVIDER_REQUEST_FAILED",
                "LLM provider request timed out",
            )
            .with_details(serde_json::json!({"kind": "timeout"})),
            LlmError::Network(s) => ApiError::new(
                StatusCode::BAD_GATEWAY,
                "LLM_PROVIDER_REQUEST_FAILED",
                s,
            )
            .with_details(serde_json::json!({"kind": "network"})),
            LlmError::StreamParse(s) => ApiError::new(
                StatusCode::BAD_GATEWAY,
                "LLM_PROVIDER_REQUEST_FAILED",
                s,
            )
            .with_details(serde_json::json!({"kind": "stream_parse"})),
            LlmError::UpstreamStatus { status, body } => {
                // Forward 4xx–5xx from upstream, fall back to 502 otherwise.
                let status_code = StatusCode::from_u16(status)
                    .ok()
                    .filter(|s| s.is_client_error() || s.is_server_error())
                    .unwrap_or(StatusCode::BAD_GATEWAY);
                ApiError::new(
                    status_code,
                    "LLM_PROVIDER_REQUEST_FAILED",
                    body,
                )
            }
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::StatusCode;

    use crate::core::vectorstore::VectorstoreError;
    use crate::core::llm_client::LlmError;
    use crate::core::project::ProjectError;

    #[test]
    fn vectorstore_invalid_argument_is_400() {
        let api: ApiError = VectorstoreError::InvalidArgument("bad".into()).into();
        assert_eq!(api.status, StatusCode::BAD_REQUEST);
        assert_eq!(api.code, "BAD_REQUEST");
    }

    #[test]
    fn vectorstore_lance_is_500() {
        let api: ApiError = VectorstoreError::Lance("kaboom".into()).into();
        assert_eq!(api.status, StatusCode::INTERNAL_SERVER_ERROR);
        assert_eq!(api.code, "INTERNAL");
    }

    #[test]
    fn project_already_exists_is_409() {
        let api: ApiError = ProjectError::AlreadyExists("dupe".into()).into();
        assert_eq!(api.status, StatusCode::CONFLICT);
        assert_eq!(api.code, "ALREADY_EXISTS");
    }

    #[test]
    fn llm_upstream_401_is_forwarded() {
        let api: ApiError = LlmError::UpstreamStatus { status: 401, body: "no auth".into() }.into();
        assert_eq!(api.status, StatusCode::UNAUTHORIZED);
        assert_eq!(api.code, "LLM_PROVIDER_REQUEST_FAILED");
    }

    #[test]
    fn llm_timeout_is_504() {
        let api: ApiError = LlmError::Timeout.into();
        assert_eq!(api.status, StatusCode::GATEWAY_TIMEOUT);
        assert_eq!(api.code, "LLM_PROVIDER_REQUEST_FAILED");
    }

    #[test]
    fn llm_invalid_config_is_400() {
        let api: ApiError = LlmError::InvalidConfig("missing key".into()).into();
        assert_eq!(api.status, StatusCode::BAD_REQUEST);
        assert_eq!(api.code, "LLM_PROVIDER_NOT_CONFIGURED");
    }
}

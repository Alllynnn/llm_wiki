//! HTTP layer for the LLM Wiki server.
//!
//! Modules:
//! - `error`: uniform error response type used by every handler.
//! - `auth`: login, logout, whoami, session middleware (Task 2.7+).
//! - `events`: per-session SSE stream (Task 2.9).
//! - `embed`: rust-embed frontend serving (Task 2.10).

pub mod error;

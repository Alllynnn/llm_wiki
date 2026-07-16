use axum::http::{header, HeaderMap};
use chrono::Utc;

use crate::http::error::ApiError;

const DEFAULT_EXPECTED_ROWS: usize = 5;

pub fn ensure_token_authorized(headers: &HeaderMap) -> Result<(), ApiError> {
    let expected = std::env::var("VISUAL_HARDCASE_QC_API_TOKEN")
        .or_else(|_| std::env::var("LLM_WIKI_API_TOKEN"))
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .ok_or_else(ApiError::unauthenticated)?;
    let Some(actual) = request_token(headers) else {
        return Err(ApiError::unauthenticated());
    };
    if actual == expected {
        Ok(())
    } else {
        Err(ApiError::unauthenticated())
    }
}

fn request_token(headers: &HeaderMap) -> Option<String> {
    if let Some(value) = headers
        .get(header::AUTHORIZATION)
        .and_then(|h| h.to_str().ok())
    {
        let trimmed = value.trim();
        if let Some(token) = trimmed
            .strip_prefix("Bearer ")
            .or_else(|| trimmed.strip_prefix("bearer "))
        {
            let token = token.trim();
            if !token.is_empty() {
                return Some(token.to_string());
            }
        }
    }
    headers
        .get("X-Visual-Hardcase-QC-Token")
        .or_else(|| headers.get("X-LLM-Wiki-Token"))
        .and_then(|h| h.to_str().ok())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(ToOwned::to_owned)
}

pub fn expand_rows(rows: &str) -> Result<Vec<u32>, String> {
    let value = rows.trim().replace('：', ":").replace('，', ",");
    if value.is_empty() {
        return Err("rows is required".to_string());
    }
    if value.contains(':') || value.contains('-') {
        let sep = if value.contains(':') { ':' } else { '-' };
        let mut parts = value.splitn(2, sep);
        let start = parse_row(parts.next().unwrap_or_default())?;
        let end = parse_row(parts.next().unwrap_or_default())?;
        if end < start {
            return Err("end row is smaller than start row".to_string());
        }
        return Ok((start..=end).collect());
    }
    value.split(',').map(parse_row).collect()
}

fn parse_row(value: &str) -> Result<u32, String> {
    value
        .trim()
        .parse::<u32>()
        .map_err(|_| format!("invalid row number: {}", value.trim()))
}

pub fn non_empty(value: String, fallback: &str) -> String {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        fallback.to_string()
    } else {
        trimmed.to_string()
    }
}

pub fn expected_row_count() -> usize {
    std::env::var("VISUAL_HARDCASE_ASSIGNMENT_COUNT")
        .ok()
        .and_then(|s| s.trim().parse::<usize>().ok())
        .unwrap_or(DEFAULT_EXPECTED_ROWS)
}

pub fn worker_disabled() -> bool {
    matches!(
        std::env::var("VISUAL_HARDCASE_QC_DISABLE_WORKER")
            .unwrap_or_default()
            .to_lowercase()
            .as_str(),
        "1" | "true" | "yes"
    )
}

pub fn now() -> String {
    Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
}

pub fn tail(mut value: String, max_chars: usize) -> String {
    if value.len() <= max_chars {
        return value;
    }
    let start = value.len().saturating_sub(max_chars);
    value.drain(..start);
    value
}

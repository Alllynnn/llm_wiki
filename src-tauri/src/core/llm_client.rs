//! Server-side OpenAI-compatible HTTP client.
//!
//! Used by Phase 4's `/proxy/llm` endpoint to forward chat completion
//! requests to the user's configured provider, with optional streaming
//! delivered via `EventSink`.

use futures::StreamExt;
use serde_json::Value;
use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct ProviderConfig {
    /// e.g. "https://api.openai.com" — without trailing slash, no path.
    pub base_url: String,
    /// Optional bearer token. Sent as `Authorization: Bearer <token>`.
    pub api_key: Option<String>,
    /// e.g. "gpt-4o-mini". Passed in the body, not the URL.
    pub model: String,
    /// Extra headers to attach (e.g. for OpenRouter routing hints).
    pub extra_headers: HashMap<String, String>,
}

#[derive(Debug, thiserror::Error)]
pub enum LlmError {
    #[error("network error: {0}")]
    Network(String),
    #[error("upstream returned status {status}: {body}")]
    UpstreamStatus { status: u16, body: String },
    #[error("request timed out")]
    Timeout,
    #[error("invalid config: {0}")]
    InvalidConfig(String),
    #[error("stream parse error: {0}")]
    StreamParse(String),
}

#[derive(Debug, Clone)]
pub struct LlmClient {
    client: reqwest::Client,
}

impl LlmClient {
    pub fn new() -> Self {
        Self {
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(120))
                .build()
                .expect("reqwest client builds"),
        }
    }

    /// Non-streaming completion. Body shape is OpenAI-compatible JSON; we
    /// don't introspect it, we just forward. Returns the parsed JSON body
    /// from the upstream.
    pub async fn chat_completion(
        &self,
        cfg: &ProviderConfig,
        body: Value,
    ) -> Result<Value, LlmError> {
        let url = format!("{}/v1/chat/completions", cfg.base_url.trim_end_matches('/'));
        let mut body_with_model = body;
        if let Value::Object(map) = &mut body_with_model {
            map.insert("model".to_string(), Value::String(cfg.model.clone()));
            map.insert("stream".to_string(), Value::Bool(false));
        } else {
            return Err(LlmError::InvalidConfig("body must be a JSON object".into()));
        }

        let mut req = self.client.post(&url).json(&body_with_model);
        if let Some(key) = &cfg.api_key {
            req = req.bearer_auth(key);
        }
        for (k, v) in &cfg.extra_headers {
            req = req.header(k, v);
        }

        let resp = req.send().await.map_err(|e| {
            if e.is_timeout() {
                LlmError::Timeout
            } else {
                LlmError::Network(e.to_string())
            }
        })?;

        let status = resp.status();
        if !status.is_success() {
            let body_text = resp.text().await.unwrap_or_default();
            return Err(LlmError::UpstreamStatus {
                status: status.as_u16(),
                body: body_text,
            });
        }

        let parsed: Value = resp
            .json()
            .await
            .map_err(|e| LlmError::StreamParse(e.to_string()))?;
        Ok(parsed)
    }

    /// Streaming completion. Each delta payload (the SSE `data: { … }`
    /// payload from upstream) is forwarded to `sink.emit("chat:token", payload)`.
    /// Returns Ok(()) when upstream sends `[DONE]` or closes the connection.
    pub async fn chat_completion_stream(
        &self,
        cfg: &ProviderConfig,
        body: Value,
        sink: &(impl crate::core::events::EventSink + ?Sized),
    ) -> Result<(), LlmError> {
        let url = format!("{}/v1/chat/completions", cfg.base_url.trim_end_matches('/'));
        let mut body_with_model = body;
        if let Value::Object(map) = &mut body_with_model {
            map.insert("model".to_string(), Value::String(cfg.model.clone()));
            map.insert("stream".to_string(), Value::Bool(true));
        } else {
            return Err(LlmError::InvalidConfig("body must be a JSON object".into()));
        }

        let mut req = self.client.post(&url).json(&body_with_model);
        if let Some(key) = &cfg.api_key {
            req = req.bearer_auth(key);
        }
        for (k, v) in &cfg.extra_headers {
            req = req.header(k, v);
        }

        let resp = req.send().await.map_err(|e| {
            if e.is_timeout() {
                LlmError::Timeout
            } else {
                LlmError::Network(e.to_string())
            }
        })?;

        let status = resp.status();
        if !status.is_success() {
            let body_text = resp.text().await.unwrap_or_default();
            return Err(LlmError::UpstreamStatus {
                status: status.as_u16(),
                body: body_text,
            });
        }

        let mut stream = resp.bytes_stream();
        let mut buf: Vec<u8> = Vec::new();
        while let Some(chunk) = stream.next().await {
            let chunk = chunk.map_err(|e| LlmError::Network(e.to_string()))?;
            buf.extend_from_slice(&chunk);

            // Parse complete SSE events delimited by "\n\n"
            loop {
                let Some(idx) = find_double_newline(&buf) else {
                    break;
                };
                let event_bytes: Vec<u8> = buf.drain(..idx + 2).collect();
                // remove the double newline
                let event_str =
                    std::str::from_utf8(&event_bytes[..event_bytes.len() - 2])
                        .map_err(|e| LlmError::StreamParse(e.to_string()))?;

                for line in event_str.lines() {
                    let Some(data) = line.strip_prefix("data:") else {
                        continue;
                    };
                    let data = data.trim();
                    if data == "[DONE]" {
                        return Ok(());
                    }
                    let payload: Value = serde_json::from_str(data)
                        .map_err(|e| LlmError::StreamParse(e.to_string()))?;
                    sink.emit("chat:token", payload);
                }
            }
        }
        Ok(())
    }
}

impl Default for LlmClient {
    fn default() -> Self {
        Self::new()
    }
}

fn find_double_newline(buf: &[u8]) -> Option<usize> {
    buf.windows(2).position(|w| w == b"\n\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::events::CapturingEventSink;
    use serde_json::json;

    fn cfg_for(server: &mockito::ServerGuard) -> ProviderConfig {
        ProviderConfig {
            base_url: server.url(),
            api_key: Some("test-key".to_string()),
            model: "test-model".to_string(),
            extra_headers: HashMap::new(),
        }
    }

    #[tokio::test]
    async fn non_streaming_happy_path_returns_body() {
        let mut server = mockito::Server::new_async().await;
        let mock = server
            .mock("POST", "/v1/chat/completions")
            .match_header("authorization", "Bearer test-key")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"choices":[{"message":{"content":"hi"}}]}"#)
            .create_async()
            .await;

        let client = LlmClient::new();
        let cfg = cfg_for(&server);
        let result = client.chat_completion(&cfg, json!({})).await.unwrap();
        assert_eq!(result["choices"][0]["message"]["content"], "hi");
        mock.assert_async().await;
    }

    #[tokio::test]
    async fn non_streaming_4xx_returns_upstream_status() {
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("POST", "/v1/chat/completions")
            .with_status(401)
            .with_body(r#"{"error":"invalid api key"}"#)
            .create_async()
            .await;

        let client = LlmClient::new();
        let cfg = cfg_for(&server);
        let result = client.chat_completion(&cfg, json!({})).await;
        assert!(matches!(
            result,
            Err(LlmError::UpstreamStatus { status: 401, .. })
        ));
    }

    #[tokio::test]
    async fn invalid_body_returns_invalid_config() {
        let server = mockito::Server::new_async().await;
        let client = LlmClient::new();
        let cfg = cfg_for(&server);
        let result = client.chat_completion(&cfg, json!(42)).await;
        assert!(matches!(result, Err(LlmError::InvalidConfig(_))));
    }

    #[tokio::test]
    async fn streaming_emits_one_event_per_delta() {
        let mut server = mockito::Server::new_async().await;
        // SSE response with 3 deltas then [DONE]
        let sse_body = "data: {\"delta\":\"hello\"}\n\n\
             data: {\"delta\":\" \"}\n\n\
             data: {\"delta\":\"world\"}\n\n\
             data: [DONE]\n\n";
        let _mock = server
            .mock("POST", "/v1/chat/completions")
            .with_status(200)
            .with_header("content-type", "text/event-stream")
            .with_body(sse_body)
            .create_async()
            .await;

        let client = LlmClient::new();
        let cfg = cfg_for(&server);
        let sink = CapturingEventSink::default();
        client
            .chat_completion_stream(&cfg, json!({}), &sink)
            .await
            .unwrap();

        let events = sink.snapshot();
        assert_eq!(events.len(), 3);
        assert_eq!(events[0].0, "chat:token");
        assert_eq!(events[0].1["delta"], "hello");
        assert_eq!(events[2].1["delta"], "world");
    }

    #[tokio::test]
    async fn streaming_4xx_returns_upstream_status_without_emitting() {
        let mut server = mockito::Server::new_async().await;
        let _mock = server
            .mock("POST", "/v1/chat/completions")
            .with_status(500)
            .with_body("server unavailable")
            .create_async()
            .await;

        let client = LlmClient::new();
        let cfg = cfg_for(&server);
        let sink = CapturingEventSink::default();
        let result = client.chat_completion_stream(&cfg, json!({}), &sink).await;
        assert!(matches!(
            result,
            Err(LlmError::UpstreamStatus { status: 500, .. })
        ));
        assert!(sink.snapshot().is_empty());
    }
}

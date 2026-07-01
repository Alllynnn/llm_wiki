use std::collections::HashMap;

use serde_json::Value;

use crate::core::llm_client::ProviderConfig;
use crate::core::search::SearchEmbeddingConfig;

/// Extract the server-side OpenAI-compatible provider config from the
/// per-user JSON config.
///
/// The browser/LAN frontend persists the current settings as `llmConfig`.
/// Older server-only API clients may still write the legacy `llm` shape, so
/// keep both formats working. `llmConfig` wins when it is valid.
pub(crate) fn provider_config_from_user(cfg: &Value) -> Result<ProviderConfig, String> {
    if let Some(llm_config) = cfg.get("llmConfig") {
        match provider_config_from_llm_config(llm_config) {
            Ok(config) => return Ok(config),
            Err(new_shape_error) => {
                if cfg.get("llm").is_none() {
                    return Err(new_shape_error);
                }
            }
        }
    }

    provider_config_from_legacy_llm(cfg)
}

pub(crate) fn embedding_config_from_user(cfg: &Value) -> Option<SearchEmbeddingConfig> {
    let config = serde_json::from_value::<SearchEmbeddingConfig>(
        cfg.get("embeddingConfig")?.clone(),
    )
    .ok()?;
    if !config.enabled || config.endpoint.trim().is_empty() || config.model.trim().is_empty() {
        return None;
    }
    Some(config)
}

fn provider_config_from_llm_config(llm: &Value) -> Result<ProviderConfig, String> {
    let provider = llm
        .get("provider")
        .and_then(Value::as_str)
        .unwrap_or("custom");
    let model = string_field(llm, "model", "missing llmConfig.model")?;
    let raw_base_url = match provider {
        "openai" => non_empty_string(llm, "customEndpoint")
            .unwrap_or_else(|| "https://api.openai.com".to_string()),
        "ollama" => string_field(llm, "ollamaUrl", "missing llmConfig.ollamaUrl")?,
        "custom" | "minimax" | "azure" | "google" | "anthropic" => {
            string_field(llm, "customEndpoint", "missing llmConfig.customEndpoint")?
        }
        other => {
            return Err(format!("unsupported llmConfig.provider: {other}"));
        }
    };
    let api_key = non_empty_string(llm, "apiKey");

    Ok(ProviderConfig {
        base_url: normalize_openai_base_url(&raw_base_url),
        api_key,
        model,
        extra_headers: HashMap::new(),
    })
}

fn provider_config_from_legacy_llm(cfg: &Value) -> Result<ProviderConfig, String> {
    let llm = cfg.get("llm").ok_or("missing llm config")?;
    let base_url = string_field(llm, "base_url", "missing llm.base_url")?;
    let api_key = non_empty_string(llm, "api_key");
    let model = string_field(llm, "model", "missing llm.model")?;
    let extra_headers = llm
        .get("extra_headers")
        .and_then(Value::as_object)
        .map(|m| {
            m.iter()
                .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string())))
                .collect()
        })
        .unwrap_or_default();
    Ok(ProviderConfig {
        base_url,
        api_key,
        model,
        extra_headers,
    })
}

fn string_field(value: &Value, key: &'static str, error: &'static str) -> Result<String, String> {
    non_empty_string(value, key).ok_or_else(|| error.to_string())
}

fn non_empty_string(value: &Value, key: &'static str) -> Option<String> {
    let value = value.get(key)?.as_str()?.trim();
    if value.is_empty() {
        None
    } else {
        Some(value.to_string())
    }
}

fn normalize_openai_base_url(raw: &str) -> String {
    let trimmed = raw.trim().trim_end_matches('/');
    let without_chat = trimmed
        .strip_suffix("/chat/completions")
        .unwrap_or(trimmed)
        .trim_end_matches('/');
    without_chat
        .strip_suffix("/v1")
        .unwrap_or(without_chat)
        .trim_end_matches('/')
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn provider_config_reads_frontend_llm_config() {
        let cfg = json!({
            "llmConfig": {
                "provider": "custom",
                "customEndpoint": "http://127.0.0.1:7860/v1",
                "apiKey": "k",
                "model": "gpt-test"
            }
        });

        let provider = provider_config_from_user(&cfg).unwrap();

        assert_eq!(provider.base_url, "http://127.0.0.1:7860");
        assert_eq!(provider.api_key.as_deref(), Some("k"));
        assert_eq!(provider.model, "gpt-test");
    }

    #[test]
    fn provider_config_keeps_legacy_llm_shape() {
        let cfg = json!({
            "llm": {
                "base_url": "https://api.example.com",
                "api_key": "k",
                "model": "legacy-model",
                "extra_headers": { "X-Test": "1" }
            }
        });

        let provider = provider_config_from_user(&cfg).unwrap();

        assert_eq!(provider.base_url, "https://api.example.com");
        assert_eq!(provider.api_key.as_deref(), Some("k"));
        assert_eq!(provider.model, "legacy-model");
        assert_eq!(provider.extra_headers.get("X-Test").map(String::as_str), Some("1"));
    }

    #[test]
    fn provider_config_falls_back_to_legacy_if_frontend_snapshot_is_empty() {
        let cfg = json!({
            "llmConfig": { "provider": "custom", "customEndpoint": "", "model": "" },
            "llm": { "base_url": "https://api.example.com", "model": "legacy-model" }
        });

        let provider = provider_config_from_user(&cfg).unwrap();

        assert_eq!(provider.base_url, "https://api.example.com");
        assert_eq!(provider.model, "legacy-model");
    }

    #[test]
    fn embedding_config_reads_frontend_embedding_config() {
        let cfg = json!({
            "embeddingConfig": {
                "enabled": true,
                "endpoint": "http://127.0.0.1:7860/v1/embeddings",
                "apiKey": "k",
                "model": "embed-test",
                "outputDimensionality": 768,
                "extraHeaders": { "X-Route": "emb" }
            }
        });

        let embedding = embedding_config_from_user(&cfg).unwrap();

        assert!(embedding.enabled);
        assert_eq!(embedding.endpoint, "http://127.0.0.1:7860/v1/embeddings");
        assert_eq!(embedding.api_key, "k");
        assert_eq!(embedding.model, "embed-test");
        assert_eq!(embedding.output_dimensionality, Some(768));
        assert_eq!(
            embedding.extra_headers.as_ref().and_then(|h| h.get("X-Route")).map(String::as_str),
            Some("emb")
        );
    }

    #[test]
    fn embedding_config_ignores_disabled_or_incomplete_config() {
        assert!(embedding_config_from_user(&json!({
            "embeddingConfig": { "enabled": false, "endpoint": "http://x", "apiKey": "", "model": "m" }
        })).is_none());
        assert!(embedding_config_from_user(&json!({
            "embeddingConfig": { "enabled": true, "endpoint": "", "apiKey": "", "model": "m" }
        })).is_none());
        assert!(embedding_config_from_user(&json!({
            "embeddingConfig": { "enabled": true, "endpoint": "http://x", "apiKey": "", "model": "" }
        })).is_none());
    }
}

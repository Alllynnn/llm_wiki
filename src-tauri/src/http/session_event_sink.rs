//! Adapter that lets `core::*` streaming functions deliver events to the
//! requester's SSE stream by routing through `SessionBus`.

use std::sync::Arc;

use crate::core::events::EventSink;
use crate::storage::session_bus::{SessionBus, SseEvent};

#[derive(Clone)]
pub struct SessionEventSink {
    bus: SessionBus,
    session_id: Arc<str>,
}

impl SessionEventSink {
    pub fn new(bus: SessionBus, session_id: String) -> Self {
        Self {
            bus,
            session_id: Arc::from(session_id),
        }
    }
}

impl EventSink for SessionEventSink {
    fn emit(&self, event_type: &str, payload: serde_json::Value) {
        let _ = self.bus.send_to(
            &self.session_id,
            SseEvent {
                event_type: event_type.to_string(),
                data: payload,
            },
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[tokio::test]
    async fn emit_delivers_to_subscribed_session() {
        let bus = SessionBus::new();
        let (_conn_id, mut rx) = bus.register("sid-X");
        let sink = SessionEventSink::new(bus, "sid-X".to_string());

        sink.emit("hello", json!({"i": 1}));

        let evt = rx.recv().await.unwrap();
        assert_eq!(evt.event_type, "hello");
        assert_eq!(evt.data, json!({"i": 1}));
    }

    #[tokio::test]
    async fn emit_with_no_subscribers_does_not_panic() {
        let bus = SessionBus::new();
        let sink = SessionEventSink::new(bus, "ghost".to_string());
        sink.emit("nobody-home", json!({}));
        // Just verify no panic
    }
}

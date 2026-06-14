//! Per-session SSE event bus.
//!
//! Each active SSE connection registers an `mpsc::Sender<SseEvent>` keyed by
//! a per-connection `ConnectionId`. Business code (LLM streaming, ingest
//! progress, etc.) calls `bus.send_to(session_id, event)` to deliver an event
//! to every connection belonging to that session — supporting multiple
//! concurrent browser tabs with the same session cookie.

use std::collections::HashMap;
use std::sync::Arc;

use parking_lot::Mutex;
use tokio::sync::mpsc;

/// Bounded channel size per connection. Trades a little latency for an upper
/// bound on memory if a browser pauses an SSE stream. 32 events is plenty
/// for chat-token streaming with reasonable per-tick batching.
const PER_SESSION_BUFFER: usize = 32;

#[derive(Clone, Debug, serde::Serialize)]
pub struct SseEvent {
    pub event_type: String,
    pub data: serde_json::Value,
}

/// A unique identifier for a single SSE connection. Multiple connections can
/// share the same session id (e.g., two browser tabs); each gets its own
/// `ConnectionId` so that closing one tab does not affect the other.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ConnectionId(pub String);

impl ConnectionId {
    /// Generate a fresh, random `ConnectionId` (22-char base64url, no pad).
    pub fn new() -> Self {
        use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
        use rand::RngCore;
        let mut bytes = [0u8; 16];
        rand::thread_rng().fill_bytes(&mut bytes);
        Self(URL_SAFE_NO_PAD.encode(bytes))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Default)]
pub struct SessionBus {
    /// Keyed by connection_id → (session_id, sender).
    inner: Arc<Mutex<HashMap<String, (String, mpsc::Sender<SseEvent>)>>>,
}

impl SessionBus {
    pub fn new() -> Self {
        Self::default()
    }

    /// Register a new SSE connection for `session_id`. Returns a unique
    /// `ConnectionId` and the receiver end of the event channel.
    pub fn register(&self, session_id: &str) -> (ConnectionId, mpsc::Receiver<SseEvent>) {
        let conn_id = ConnectionId::new();
        let (tx, rx) = mpsc::channel(PER_SESSION_BUFFER);
        self.inner
            .lock()
            .insert(conn_id.0.clone(), (session_id.to_string(), tx));
        (conn_id, rx)
    }

    /// Unregister a single connection. Other connections for the same session
    /// are not affected.
    pub fn unregister(&self, connection_id: &ConnectionId) {
        self.inner.lock().remove(&connection_id.0);
    }

    /// Send `event` to every active connection belonging to `session_id`.
    /// Returns the number of connections that accepted the event (i.e., had
    /// room in their channel).
    pub fn send_to(&self, session_id: &str, event: SseEvent) -> usize {
        let guard = self.inner.lock();
        let mut count = 0;
        for (_conn_id, (sid, tx)) in guard.iter() {
            if sid == session_id {
                if tx.try_send(event.clone()).is_ok() {
                    count += 1;
                }
            }
        }
        count
    }

    #[cfg(test)]
    pub(crate) fn registered_count(&self) -> usize {
        self.inner.lock().len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn evt(t: &str) -> SseEvent {
        SseEvent { event_type: t.into(), data: json!({}) }
    }

    #[tokio::test]
    async fn register_and_send_delivers_event() {
        let bus = SessionBus::new();
        let (_conn_id, mut rx) = bus.register("sid-1");
        assert_eq!(bus.send_to("sid-1", evt("ping")), 1);
        let received = rx.recv().await.unwrap();
        assert_eq!(received.event_type, "ping");
    }

    #[tokio::test]
    async fn send_to_unknown_session_returns_zero() {
        let bus = SessionBus::new();
        assert_eq!(bus.send_to("nobody", evt("ping")), 0);
    }

    #[tokio::test]
    async fn unregister_removes_session() {
        let bus = SessionBus::new();
        let (conn_id, _rx) = bus.register("sid-1");
        assert_eq!(bus.registered_count(), 1);
        bus.unregister(&conn_id);
        assert_eq!(bus.registered_count(), 0);
        assert_eq!(bus.send_to("sid-1", evt("ping")), 0);
    }

    #[tokio::test]
    async fn connection_ids_are_unique() {
        let bus = SessionBus::new();
        let (c1, _rx1) = bus.register("sid-1");
        let (c2, _rx2) = bus.register("sid-1");
        assert_ne!(c1, c2);
        assert_eq!(bus.registered_count(), 2);
    }

    #[tokio::test]
    async fn send_drops_silently_when_buffer_full() {
        let bus = SessionBus::new();
        let (_conn_id, _rx) = bus.register("sid-1");
        // Fill the buffer without draining
        for _ in 0..PER_SESSION_BUFFER {
            assert_eq!(bus.send_to("sid-1", evt("ping")), 1);
        }
        // Next send must fail (buffer full) — zero subscribers accepted it
        assert_eq!(bus.send_to("sid-1", evt("overflow")), 0);
    }

    #[tokio::test]
    async fn bus_is_cheaply_cloneable() {
        let bus = SessionBus::new();
        let bus2 = bus.clone();
        let (_conn_id, _rx) = bus.register("sid-1");
        assert_eq!(bus2.send_to("sid-1", evt("ping")), 1);
    }

    #[tokio::test]
    async fn two_concurrent_subscribers_for_same_session_both_receive_events() {
        let bus = SessionBus::new();
        let (_c1, mut rx1) = bus.register("sid-1");
        let (_c2, mut rx2) = bus.register("sid-1");
        let count = bus.send_to("sid-1", evt("hello"));
        assert_eq!(count, 2);
        assert_eq!(rx1.recv().await.unwrap().event_type, "hello");
        assert_eq!(rx2.recv().await.unwrap().event_type, "hello");
    }

    #[tokio::test]
    async fn dropping_one_subscriber_does_not_remove_the_other() {
        let bus = SessionBus::new();
        let (c1, _rx1) = bus.register("sid-1");
        let (_c2, mut rx2) = bus.register("sid-1");
        bus.unregister(&c1);
        let count = bus.send_to("sid-1", evt("ping"));
        assert_eq!(count, 1);
        assert_eq!(rx2.recv().await.unwrap().event_type, "ping");
    }
}

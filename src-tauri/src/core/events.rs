//! Streaming-event abstraction used by long-running `core::*` operations.
//!
//! `core` code does not know whether events go to Tauri's IPC bridge,
//! an HTTP SSE stream, or get dropped on the floor. It just calls
//! `sink.emit(event_type, payload)` and moves on.

use serde_json::Value;

/// Receives streamed events from `core::*` functions.
///
/// Implementations must be `Send + Sync` and cheap to clone, because the
/// same sink may be shared across spawned tasks within a single operation
/// (e.g., a parallel ingest pipeline).
pub trait EventSink: Send + Sync {
    fn emit(&self, event_type: &str, payload: Value);
}

/// Drop every event. Useful in tests and in HTTP request flows that don't
/// care about streamed progress (e.g., a simple JSON-response handler that
/// just wants the final result).
#[derive(Debug, Clone, Default)]
pub struct NullEventSink;

impl EventSink for NullEventSink {
    fn emit(&self, _event_type: &str, _payload: Value) {}
}

/// Capture events to an in-memory `Vec`. Used by `cfg(test)` callers that
/// want to assert the event stream.
#[cfg(test)]
#[derive(Debug, Default)]
pub struct CapturingEventSink {
    pub events: parking_lot::Mutex<Vec<(String, Value)>>,
}

#[cfg(test)]
impl EventSink for CapturingEventSink {
    fn emit(&self, event_type: &str, payload: Value) {
        self.events.lock().push((event_type.to_string(), payload));
    }
}

#[cfg(test)]
impl CapturingEventSink {
    pub fn snapshot(&self) -> Vec<(String, Value)> {
        self.events.lock().clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn null_sink_swallows_events() {
        let sink = NullEventSink;
        sink.emit("anything", json!({"x": 1}));
        // No way to observe — that's the point. Just verify it compiles
        // and doesn't panic.
    }

    #[test]
    fn capturing_sink_records_events_in_order() {
        let sink = CapturingEventSink::default();
        sink.emit("first", json!({"i": 1}));
        sink.emit("second", json!({"i": 2}));
        let snap = sink.snapshot();
        assert_eq!(snap.len(), 2);
        assert_eq!(snap[0].0, "first");
        assert_eq!(snap[1].0, "second");
        assert_eq!(snap[0].1, json!({"i": 1}));
    }

    #[test]
    fn sinks_are_send_sync() {
        fn check<T: Send + Sync>() {}
        check::<NullEventSink>();
        check::<CapturingEventSink>();
    }
}

//! Adapter that lets `core::*` functions emit events through Tauri's IPC.

use serde_json::Value;
use tauri::{AppHandle, Emitter};

use crate::core::events::EventSink;

#[derive(Clone)]
pub struct TauriEventSink {
    pub app: AppHandle,
}

impl TauriEventSink {
    pub fn new(app: AppHandle) -> Self {
        Self { app }
    }
}

impl EventSink for TauriEventSink {
    fn emit(&self, event_type: &str, payload: Value) {
        let _ = self.app.emit(event_type, payload);
    }
}

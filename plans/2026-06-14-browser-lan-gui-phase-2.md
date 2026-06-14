# Browser/LAN GUI Phase 2 — HTTP Server Skeleton (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Phase goal:** Stand up an axum HTTP server in the existing crate as a **second binary** (`llm-wiki-server`) alongside the existing Tauri `llm-wiki` binary. Both binaries share the existing library code; neither breaks the other. By the end of Phase 2 a developer can run `cargo run --bin llm-wiki-server`, send `curl http://localhost:8080/api/v1/auth/whoami`, and get back a 401 with the uniform error JSON. Login with a valid `users.toml` entry returns a `Set-Cookie`; whoami with the cookie returns the user. The legacy `127.0.0.1:19828` listener also runs (no auth) for backward compat with the bundled MCP server. SSE endpoint opens and holds. No business endpoints yet; those land in Phase 4.

**Architecture:**
- Two binaries in the same crate: `llm-wiki` (existing Tauri shell) and `llm-wiki-server` (new HTTP server).
- Both call into the existing `llm_wiki_lib` crate.
- The new HTTP code lives under `src-tauri/src/http/` and is shared by both binaries (the Tauri binary doesn't use it yet; Phase 7 removes Tauri entirely).
- `AppState` is the shared, cheaply-cloneable state struct holding `Users`, `Sessions`, `UserData`, `SessionBus`, and `ServerConfig`. Every handler receives it via `axum::extract::State<AppState>`.
- Per-session SSE event bus lives in `storage::session_bus`. Empty hookups for now; events get wired in later phases.

**Source spec:** `plans/2026-06-14-browser-lan-gui-design.md` (sections 2 and 4–5 are most relevant).
**Source plan:** `plans/2026-06-14-browser-lan-gui-implementation.md` (Phase 2 outline section).

**Branch:** Continue on `feat/browser-lan-port` (Phase 1 already landed there).

**Environment:** macOS dev. `cargo` lives at `~/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo` — prefix non-interactive shell commands with `export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH"`.

---

## Phase 2 — Lessons absorbed from Phase 1

Two real bugs in the Phase 1 plan reached the implementer and were only caught in code review. Both are corrected here as patterns to use:

1. **Timing-oracle defense pattern**: pre-compute a sentinel and reuse it; never spend more KDFs in the unknown-user path than the known-user path. (Already applied in `Users::verify_password`.)
2. **`safe_segment`-style allowlist**: reject `.` and `..` explicitly *before* the charset check, regardless of whether the charset would have allowed them. (Already applied in `storage::user_data::safe_segment`.)

For Phase 2 specifically:
- **TOCTOU**: prefer `match fs::read(...)` over `if path.exists()` + read.
- **Use `Arc<T>` for shared immutable state**, `Clone`-able handles for mutable persistent state (sled handles already do this).
- **No `Default` derives on types that need a non-empty value invariant.**

---

## Phase 2 file structure

```
src-tauri/
  Cargo.toml                              modified: new bin entry, axum/tower/etc deps
  src/
    bin/
      llm_wiki_server.rs                  NEW — entry point for `cargo run --bin llm-wiki-server`
    config.rs                             NEW — ServerConfig: env vars → struct
    http/
      mod.rs                              NEW — router assembly, AppState
      error.rs                            NEW — ApiError + IntoResponse
      auth.rs                             NEW — login, logout, whoami, session middleware
      events.rs                           NEW — SSE skeleton
      embed.rs                            NEW — rust-embed frontend bundle + SPA fallback
    storage/
      session_bus.rs                      NEW — per-session mpsc broadcaster
      mod.rs                              modified: add `pub mod session_bus;`
    auth/
      users.rs                            modified: add `Users::lookup_user(id) -> Option<User>`
      mod.rs                              already declares users + sessions; no change
    lib.rs                                modified: add `pub mod config;`, `pub mod http;`
```

(The Tauri-specific `src/main.rs` and `src/lib.rs::run()` remain unchanged in Phase 2. They get deleted in Phase 7.)

---

## Phase 2 task overview

| # | Task | Outcome |
|---|---|---|
| 2.1 | Cargo deps + new `[[bin]]` entry | Crate compiles with the new dependencies and registers the second binary. |
| 2.2 | `Users::lookup_user(id)` accessor | Phase-1 retrofit: middleware can resolve `user_id → User` without re-verifying. |
| 2.3 | `config::ServerConfig` (env + TOML) | Server reads `PORT`, `PROJECTS_ROOT`, `DATA_ROOT`, `LEGACY_19828_ENABLED`, `SESSION_COOKIE_NAME` with safe defaults. |
| 2.4 | `storage::session_bus::SessionBus` | Per-session `mpsc::Sender<SseEvent>` registry. Wired by SSE; not yet used. |
| 2.5 | `http::error::ApiError` + IntoResponse | Uniform `{error: {code, message, details}}` JSON shape; works with axum response conversion. |
| 2.6 | `http::AppState` + skeleton router | App-state struct holding everything handlers need; smoke test that `/health` responds. |
| 2.7 | `http::auth` — session middleware + `AuthUser` extractor | Extracts session cookie → looks up Sessions → looks up Users → injects User. Handlers receive `AuthUser` for protected routes. |
| 2.8 | `http::auth` — `/auth/login`, `/auth/logout`, `/auth/whoami` | Login validates password, creates session, sets cookie. Logout clears. Whoami returns user + recently_opened. |
| 2.9 | `http::events` — `GET /events` SSE skeleton | Authenticated; registers session in `SessionBus`; holds open until disconnect; auto-unregister. |
| 2.10 | `http::embed` — rust-embed frontend + SPA fallback | Serves `dist/` from compiled binary; non-API non-asset paths fall back to `index.html`. |
| 2.11 | `bin/llm_wiki_server.rs` — boot + dual listeners | Loads config, builds AppState, starts axum on `0.0.0.0:<port>` with auth + on `127.0.0.1:19828` without (if enabled). |
| 2.12 | End-to-end smoke check | `cargo run --bin llm-wiki-server` → curl exercises 401, login, whoami. Final `cargo test --lib` green. |

---

# Task 2.1 — Cargo deps + new `[[bin]]` entry

**Files:**
- Modify: `src-tauri/Cargo.toml`

**Background:** axum needs: `axum`, `tower`, `tower-http`, `hyper`, `tokio` (already in deps), `tower-cookies` (cookie extraction), `rust-embed` (bundle the frontend), `async-trait` (FromRequestParts), `blake3` (used in later phases for project_id hashing but adding now is harmless and fits the deps PR). `tracing` + `tracing-subscriber` are optional for now — defer unless a later task asks for them.

`tokio` is already a `[dependencies]` member with `["process", "io-util", "sync", "macros", "rt"]`. The server needs `rt-multi-thread` and `signal` (for graceful shutdown). Modify the existing tokio line.

- [ ] **Step 1: Add the new `[[bin]]` entry**

Add this block to `src-tauri/Cargo.toml`, immediately after the existing `[[bin]]` entry for `llm-wiki`:

```toml
[[bin]]
name = "llm-wiki-server"
path = "src/bin/llm_wiki_server.rs"
```

- [ ] **Step 2: Expand `tokio` features**

Find the existing line:

```toml
tokio = { version = "1", features = ["process", "io-util", "sync", "macros", "rt"] }
```

Replace with:

```toml
tokio = { version = "1", features = ["process", "io-util", "sync", "macros", "rt", "rt-multi-thread", "signal", "time"] }
```

- [ ] **Step 3: Add Phase 2 HTTP-server deps**

Add this block under `[dependencies]`, immediately after the Phase 1 deps block (after `parking_lot = "0.12"`):

```toml
# Phase 2 (HTTP server skeleton): axum-based HTTP, cookies, rust-embed for
# bundling the frontend, blake3 for project-id hashing (used later phases),
# async-trait for axum extractor impls.
axum = { version = "0.8", features = ["macros"] }
tower = "0.5"
tower-http = { version = "0.6", features = ["fs", "trace", "cors"] }
tower-cookies = "0.10"
hyper = "1"
rust-embed = "8"
async-trait = "0.1"
blake3 = "1"
```

- [ ] **Step 4: Create the empty bin file so cargo doesn't complain**

Create the file `src-tauri/src/bin/llm_wiki_server.rs` with a placeholder body:

```rust
//! Phase 2 placeholder. Real boot logic lands in Task 2.11.
fn main() {
    panic!("llm-wiki-server is not yet implemented (Phase 2 in progress)");
}
```

- [ ] **Step 5: Verify the workspace builds**

Run:
```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo check)
```

Expected: builds successfully with only warnings about unused deps. The `llm-wiki-server` binary should compile (it's just a panic).

- [ ] **Step 6: Commit**

```bash
git add src-tauri/Cargo.toml src-tauri/Cargo.lock src-tauri/src/bin/llm_wiki_server.rs
git commit -m "build: add axum + http deps and llm-wiki-server bin entry"
```

---

# Task 2.2 — `Users::lookup_user(id)` accessor

**Files:**
- Modify: `src-tauri/src/auth/users.rs`

**Background:** The session middleware will need to turn a `user_id: String` from `Sessions::lookup` into a full `User { id, username }`. Currently the only way to get a `User` is `Users::verify_password`, which does the argon2 work — wasteful on every request. Add a cheap lookup accessor.

**API to add:**

```rust
impl Users {
    /// Look up a user by their lowercased id. Returns `None` if no such user.
    pub fn lookup_user(&self, id: &str) -> Option<User>;
}
```

- [ ] **Step 1: Write the failing test**

Append to the `#[cfg(test)] mod tests` block in `src-tauri/src/auth/users.rs`:

```rust
    #[test]
    fn lookup_user_returns_user_when_present() {
        let hash = hash_password("pw").unwrap();
        let dir = TempDir::new().unwrap();
        let path = write_users_toml(
            &dir,
            &format!("[users.Alice]\npassword_hash = \"{}\"\n", hash),
        );
        let users = Users::load(&path).unwrap();
        let u = users.lookup_user("alice").unwrap();
        assert_eq!(u.id, "alice");
        assert_eq!(u.username, "Alice");
    }

    #[test]
    fn lookup_user_returns_none_for_unknown() {
        let dir = TempDir::new().unwrap();
        let path = write_users_toml(&dir, "");
        let users = Users::load(&path).unwrap();
        assert!(users.lookup_user("nobody").is_none());
    }

    #[test]
    fn lookup_user_is_case_insensitive() {
        let hash = hash_password("pw").unwrap();
        let dir = TempDir::new().unwrap();
        let path = write_users_toml(
            &dir,
            &format!("[users.Bob]\npassword_hash = \"{}\"\n", hash),
        );
        let users = Users::load(&path).unwrap();
        assert_eq!(users.lookup_user("BOB").unwrap().username, "Bob");
    }
```

- [ ] **Step 2: Run the tests, expect failure**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo test --lib auth::users::tests::lookup_user)
```

Expected: compile error — `lookup_user` doesn't exist yet.

- [ ] **Step 3: Implement `lookup_user`**

Inside the existing `impl Users { ... }` block in `src-tauri/src/auth/users.rs` (above the closing `}` of the impl), add:

```rust
    pub fn lookup_user(&self, id: &str) -> Option<User> {
        let lookup_id = id.to_lowercase();
        // Only return Some if the record exists; the display_names map is
        // populated in lockstep at load time, so a record-hit guarantees a
        // display_names hit.
        if !self.by_id.contains_key(&lookup_id) {
            return None;
        }
        let username = self
            .display_names
            .get(&lookup_id)
            .cloned()
            .unwrap_or_else(|| lookup_id.clone());
        Some(User { id: lookup_id, username })
    }
```

- [ ] **Step 4: Run the tests, expect all to pass**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo test --lib auth::users)
```

Expected: 11 passed (8 from Phase 1 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/auth/users.rs
git commit -m "feat(auth): add Users::lookup_user accessor"
```

---

# Task 2.3 — `ServerConfig` (env vars → struct)

**Files:**
- Create: `src-tauri/src/config.rs`
- Modify: `src-tauri/src/lib.rs` (add `pub mod config;`)

**Background:** The HTTP server boots from env vars (no startup TOML for v1 — env vars are enough and simpler). Defaults are sane for local dev. The Phase 1 plan called for a startup TOML, but we punt that to "later if needed"; env vars are easier to script against (systemd, docker, direnv).

**Env vars consumed:**

| Var | Default | Purpose |
|---|---|---|
| `LLM_WIKI_PORT` | `8080` | Main listener port |
| `LLM_WIKI_PROJECTS_ROOT` | `./projects` | Where browsable projects live |
| `LLM_WIKI_DATA_ROOT` | `./data` | Where users.toml, sessions, per-user dirs live |
| `LLM_WIKI_LEGACY_19828_ENABLED` | `true` | Whether to open the back-compat localhost listener |
| `LLM_WIKI_SESSION_COOKIE_NAME` | `llm_wiki_session` | Cookie name (configurable in case of clash on shared dev box) |

**API to land:**

```rust
pub struct ServerConfig {
    pub port: u16,
    pub projects_root: PathBuf,
    pub data_root: PathBuf,
    pub legacy_19828_enabled: bool,
    pub session_cookie_name: String,
}

impl ServerConfig {
    pub fn from_env() -> Result<Self, ConfigError>;
}
```

- [ ] **Step 1: Create the file**

Create `src-tauri/src/config.rs`:

```rust
//! Server configuration loaded from environment variables at startup.
//!
//! Env vars are the only configuration source for v1; a startup TOML can
//! be added later if shell-env limits become a problem. Defaults are tuned
//! for local-dev (relative paths, port 8080, legacy listener enabled).

use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct ServerConfig {
    pub port: u16,
    pub projects_root: PathBuf,
    pub data_root: PathBuf,
    pub legacy_19828_enabled: bool,
    pub session_cookie_name: String,
}

#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error("invalid LLM_WIKI_PORT (must be 1-65535): {0}")]
    InvalidPort(String),
    #[error("invalid LLM_WIKI_LEGACY_19828_ENABLED (must be true|false): {0}")]
    InvalidBool(String),
}

impl ServerConfig {
    pub fn from_env() -> Result<Self, ConfigError> {
        let port = match std::env::var("LLM_WIKI_PORT") {
            Ok(s) => s
                .parse::<u16>()
                .map_err(|_| ConfigError::InvalidPort(s))?,
            Err(_) => 8080,
        };

        let projects_root = std::env::var("LLM_WIKI_PROJECTS_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("./projects"));

        let data_root = std::env::var("LLM_WIKI_DATA_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("./data"));

        let legacy_19828_enabled = match std::env::var("LLM_WIKI_LEGACY_19828_ENABLED") {
            Ok(s) => parse_bool(&s)?,
            Err(_) => true,
        };

        let session_cookie_name = std::env::var("LLM_WIKI_SESSION_COOKIE_NAME")
            .unwrap_or_else(|_| "llm_wiki_session".to_string());

        Ok(ServerConfig {
            port,
            projects_root,
            data_root,
            legacy_19828_enabled,
            session_cookie_name,
        })
    }
}

fn parse_bool(s: &str) -> Result<bool, ConfigError> {
    match s.to_lowercase().as_str() {
        "true" | "1" | "yes" => Ok(true),
        "false" | "0" | "no" => Ok(false),
        _ => Err(ConfigError::InvalidBool(s.to_string())),
    }
}
```

- [ ] **Step 2: Declare the module in `lib.rs`**

Add `pub mod config;` to `src-tauri/src/lib.rs` near the other `pub mod` declarations.

- [ ] **Step 3: Write tests**

Append to `src-tauri/src/config.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    /// Locked global mutex — env vars are process-wide, so tests that mutate
    /// them must serialize.
    static ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    fn with_clean_env<R>(f: impl FnOnce() -> R) -> R {
        let _g = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
        for key in [
            "LLM_WIKI_PORT",
            "LLM_WIKI_PROJECTS_ROOT",
            "LLM_WIKI_DATA_ROOT",
            "LLM_WIKI_LEGACY_19828_ENABLED",
            "LLM_WIKI_SESSION_COOKIE_NAME",
        ] {
            std::env::remove_var(key);
        }
        f()
    }

    #[test]
    fn defaults_when_no_env() {
        let cfg = with_clean_env(|| ServerConfig::from_env().unwrap());
        assert_eq!(cfg.port, 8080);
        assert_eq!(cfg.projects_root, PathBuf::from("./projects"));
        assert_eq!(cfg.data_root, PathBuf::from("./data"));
        assert!(cfg.legacy_19828_enabled);
        assert_eq!(cfg.session_cookie_name, "llm_wiki_session");
    }

    #[test]
    fn port_from_env() {
        let cfg = with_clean_env(|| {
            std::env::set_var("LLM_WIKI_PORT", "9000");
            ServerConfig::from_env().unwrap()
        });
        assert_eq!(cfg.port, 9000);
    }

    #[test]
    fn invalid_port_errors() {
        let result = with_clean_env(|| {
            std::env::set_var("LLM_WIKI_PORT", "not-a-number");
            ServerConfig::from_env()
        });
        assert!(matches!(result, Err(ConfigError::InvalidPort(_))));
    }

    #[test]
    fn legacy_listener_can_be_disabled() {
        let cfg = with_clean_env(|| {
            std::env::set_var("LLM_WIKI_LEGACY_19828_ENABLED", "false");
            ServerConfig::from_env().unwrap()
        });
        assert!(!cfg.legacy_19828_enabled);
    }

    #[test]
    fn invalid_bool_errors() {
        let result = with_clean_env(|| {
            std::env::set_var("LLM_WIKI_LEGACY_19828_ENABLED", "maybe");
            ServerConfig::from_env()
        });
        assert!(matches!(result, Err(ConfigError::InvalidBool(_))));
    }

    #[test]
    fn bool_accepts_aliases() {
        for (v, expected) in [
            ("true", true), ("1", true), ("yes", true), ("TRUE", true),
            ("false", false), ("0", false), ("no", false), ("FALSE", false),
        ] {
            let cfg = with_clean_env(|| {
                std::env::set_var("LLM_WIKI_LEGACY_19828_ENABLED", v);
                ServerConfig::from_env().unwrap()
            });
            assert_eq!(cfg.legacy_19828_enabled, expected, "input: {v}");
        }
    }
}
```

- [ ] **Step 4: Run tests, expect to pass**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo test --lib config)
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/config.rs src-tauri/src/lib.rs
git commit -m "feat(config): add ServerConfig loaded from env vars"
```

---

# Task 2.4 — `SessionBus` (per-session SSE event bus)

**Files:**
- Create: `src-tauri/src/storage/session_bus.rs`
- Modify: `src-tauri/src/storage/mod.rs` (add `pub mod session_bus;`)

**Background:** When a browser opens the SSE endpoint, the handler registers an `mpsc::Sender<SseEvent>` keyed by the user's session ID. When business code (later phases) wants to push an event *to that session*, it calls `bus.send_to(session_id, event)`. On disconnect, the handler calls `bus.unregister(session_id)`. The bus is `Clone` (it's `Arc<Mutex<HashMap<...>>>`).

For Phase 2 we ship the bus and the SSE endpoint that registers connections. We don't yet have any caller that sends events — that comes in later phases.

**API to land:**

```rust
#[derive(Clone, Debug, serde::Serialize)]
pub struct SseEvent {
    pub event_type: String,
    pub data: serde_json::Value,
}

#[derive(Clone, Default)]
pub struct SessionBus {
    inner: Arc<Mutex<HashMap<String, mpsc::Sender<SseEvent>>>>,
}

impl SessionBus {
    pub fn new() -> Self;

    /// Register a session. Returns the receiver to wire to the SSE stream.
    /// If a previous connection for the same session is still registered,
    /// it is replaced (and its receiver will eventually error out).
    pub fn register(&self, session_id: &str) -> mpsc::Receiver<SseEvent>;

    pub fn unregister(&self, session_id: &str);

    /// Best-effort send. Returns true if a receiver was registered AND
    /// the channel had room (or completed the send via try_send). Drops
    /// silently if no session or buffer full — neither is fatal.
    pub fn send_to(&self, session_id: &str, event: SseEvent) -> bool;
}
```

`tokio::sync::mpsc` with a bounded channel (capacity 32) — back-pressure for slow consumers without unbounded memory.

- [ ] **Step 1: Create the file**

Create `src-tauri/src/storage/session_bus.rs`:

```rust
//! Per-session SSE event bus.
//!
//! Each active SSE connection registers an `mpsc::Sender<SseEvent>` keyed by
//! its session id. Business code (LLM streaming, ingest progress, etc.) calls
//! `bus.send_to(session_id, event)` to deliver an event to that session and
//! that session only — no cross-user broadcast.

use std::collections::HashMap;
use std::sync::Arc;

use parking_lot::Mutex;
use tokio::sync::mpsc;

/// Bounded channel size per session. Trades a little latency for an upper
/// bound on memory if a browser pauses an SSE stream. 32 events is plenty
/// for chat-token streaming with reasonable per-tick batching.
const PER_SESSION_BUFFER: usize = 32;

#[derive(Clone, Debug, serde::Serialize)]
pub struct SseEvent {
    pub event_type: String,
    pub data: serde_json::Value,
}

#[derive(Clone, Default)]
pub struct SessionBus {
    inner: Arc<Mutex<HashMap<String, mpsc::Sender<SseEvent>>>>,
}

impl SessionBus {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register(&self, session_id: &str) -> mpsc::Receiver<SseEvent> {
        let (tx, rx) = mpsc::channel(PER_SESSION_BUFFER);
        self.inner.lock().insert(session_id.to_string(), tx);
        rx
    }

    pub fn unregister(&self, session_id: &str) {
        self.inner.lock().remove(session_id);
    }

    pub fn send_to(&self, session_id: &str, event: SseEvent) -> bool {
        let guard = self.inner.lock();
        let Some(sender) = guard.get(session_id) else {
            return false;
        };
        sender.try_send(event).is_ok()
    }

    #[cfg(test)]
    pub(crate) fn registered_count(&self) -> usize {
        self.inner.lock().len()
    }
}
```

- [ ] **Step 2: Declare the module**

Modify `src-tauri/src/storage/mod.rs` to add `pub mod session_bus;` (next to `paths` and `user_data`).

- [ ] **Step 3: Write tests**

Append to `src-tauri/src/storage/session_bus.rs`:

```rust
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
        let mut rx = bus.register("sid-1");
        assert!(bus.send_to("sid-1", evt("ping")));
        let received = rx.recv().await.unwrap();
        assert_eq!(received.event_type, "ping");
    }

    #[tokio::test]
    async fn send_to_unknown_session_returns_false() {
        let bus = SessionBus::new();
        assert!(!bus.send_to("nobody", evt("ping")));
    }

    #[tokio::test]
    async fn unregister_removes_session() {
        let bus = SessionBus::new();
        let _rx = bus.register("sid-1");
        assert_eq!(bus.registered_count(), 1);
        bus.unregister("sid-1");
        assert_eq!(bus.registered_count(), 0);
        assert!(!bus.send_to("sid-1", evt("ping")));
    }

    #[tokio::test]
    async fn re_register_replaces_previous_sender() {
        let bus = SessionBus::new();
        let _rx1 = bus.register("sid-1");
        let mut rx2 = bus.register("sid-1");
        // Send: should go to rx2 (latest)
        assert!(bus.send_to("sid-1", evt("hello")));
        let received = rx2.recv().await.unwrap();
        assert_eq!(received.event_type, "hello");
    }

    #[tokio::test]
    async fn send_drops_silently_when_buffer_full() {
        let bus = SessionBus::new();
        let _rx = bus.register("sid-1");
        // Fill the buffer without draining
        for _ in 0..PER_SESSION_BUFFER {
            assert!(bus.send_to("sid-1", evt("ping")));
        }
        // Next send must fail (buffer full)
        assert!(!bus.send_to("sid-1", evt("overflow")));
    }

    #[tokio::test]
    async fn bus_is_cheaply_cloneable() {
        let bus = SessionBus::new();
        let bus2 = bus.clone();
        let _rx = bus.register("sid-1");
        assert!(bus2.send_to("sid-1", evt("ping")));
    }
}
```

The test module needs `tokio` as a dev-dep with macros and rt — both already enabled in the existing dev-dep line.

- [ ] **Step 4: Run tests**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo test --lib storage::session_bus)
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/storage/session_bus.rs src-tauri/src/storage/mod.rs
git commit -m "feat(storage): add per-session SSE event bus"
```

---

# Task 2.5 — `http::error::ApiError` + IntoResponse

**Files:**
- Create: `src-tauri/src/http/mod.rs` (will be empty for now — Task 2.6 adds AppState/router)
- Create: `src-tauri/src/http/error.rs`
- Modify: `src-tauri/src/lib.rs` (add `pub mod http;`)

**Background:** Every error response from every handler returns the same JSON shape:

```json
{
  "error": {
    "code": "PATH_ESCAPE",
    "message": "Path escapes the projects root",
    "details": { "requested": "../etc/passwd" }
  }
}
```

`code` is a stable string enum. `message` is user-facing. `details` is optional structured data. The HTTP status code carries the broad category.

We expose a single `ApiError` type that implements `axum::response::IntoResponse`, and a small set of constructor helpers for the codes used in Phase 2.

- [ ] **Step 1: Create the empty `http/mod.rs`**

Create `src-tauri/src/http/mod.rs`:

```rust
//! HTTP layer for the LLM Wiki server.
//!
//! Modules:
//! - `error`: uniform error response type used by every handler.
//! - `auth`: login, logout, whoami, session middleware (Task 2.7+).
//! - `events`: per-session SSE stream (Task 2.9).
//! - `embed`: rust-embed frontend serving (Task 2.10).

pub mod error;
```

- [ ] **Step 2: Declare the module in `lib.rs`**

Add `pub mod http;` to `src-tauri/src/lib.rs`.

- [ ] **Step 3: Create the error module**

Create `src-tauri/src/http/error.rs`:

```rust
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
```

- [ ] **Step 4: Write tests**

Append to `src-tauri/src/http/error.rs`:

```rust
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
```

- [ ] **Step 5: Run tests**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo test --lib http::error)
```

Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src-tauri/src/http/ src-tauri/src/lib.rs
git commit -m "feat(http): add uniform ApiError + IntoResponse"
```

---

# Task 2.6 — `AppState` + skeleton router with `/health`

**Files:**
- Modify: `src-tauri/src/http/mod.rs`

**Background:** `AppState` is what every handler receives via `axum::extract::State<AppState>`. It's `Clone`-able cheaply because everything inside is either an `Arc` or already cheap to clone (`sled` handles, `UserData` is `PathBuf`, `SessionBus` is `Arc` internally).

We also add a minimal `/health` endpoint so we can verify the router wires up at all, without needing auth.

- [ ] **Step 1: Extend `http::mod`**

Replace the contents of `src-tauri/src/http/mod.rs` with:

```rust
//! HTTP layer for the LLM Wiki server.
//!
//! Modules:
//! - `error`: uniform error response type used by every handler.
//! - `auth`: login, logout, whoami, session middleware (Task 2.7+).
//! - `events`: per-session SSE stream (Task 2.9).
//! - `embed`: rust-embed frontend serving (Task 2.10).

pub mod error;

use std::sync::Arc;

use axum::routing::get;
use axum::{Json, Router};
use serde_json::json;

use crate::auth::sessions::Sessions;
use crate::auth::users::Users;
use crate::config::ServerConfig;
use crate::storage::session_bus::SessionBus;
use crate::storage::user_data::UserData;

#[derive(Clone)]
pub struct AppState {
    pub users: Arc<Users>,
    pub sessions: Sessions,
    pub user_data: UserData,
    pub session_bus: SessionBus,
    pub config: Arc<ServerConfig>,
}

/// The main authenticated router. Auth middleware is layered on by the
/// caller in `bin/llm_wiki_server.rs` so the same router can be mounted
/// twice — once with auth, once without (legacy 127.0.0.1:19828).
pub fn main_router(state: AppState) -> Router {
    Router::new()
        .route("/api/v1/health", get(health))
        .with_state(state)
}

async fn health() -> Json<serde_json::Value> {
    Json(json!({"status": "ok"}))
}
```

- [ ] **Step 2: Write integration tests**

Create a tests submodule inside `src-tauri/src/http/mod.rs` by appending:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;
    use axum::http::Request;
    use std::path::PathBuf;
    use tempfile::TempDir;
    use tower::ServiceExt; // for `oneshot`

    fn build_state() -> (TempDir, AppState) {
        let dir = TempDir::new().unwrap();
        let users_path = dir.path().join("users.toml");
        std::fs::write(&users_path, "").unwrap();
        let users = Users::load(&users_path).unwrap();
        let sessions = Sessions::open(&dir.path().join("sessions")).unwrap();
        let user_data = UserData::new(dir.path().to_path_buf());
        let bus = SessionBus::new();
        let cfg = ServerConfig {
            port: 8080,
            projects_root: PathBuf::from("./projects"),
            data_root: dir.path().to_path_buf(),
            legacy_19828_enabled: true,
            session_cookie_name: "test_session".into(),
        };
        let state = AppState {
            users: Arc::new(users),
            sessions,
            user_data,
            session_bus: bus,
            config: Arc::new(cfg),
        };
        (dir, state)
    }

    #[tokio::test]
    async fn health_endpoint_returns_ok() {
        let (_dir, state) = build_state();
        let app = main_router(state);
        let resp = app
            .oneshot(Request::builder().uri("/api/v1/health").body(axum::body::Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(resp.status(), 200);
        let body = to_bytes(resp.into_body(), 4096).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(v["status"], "ok");
    }
}
```

- [ ] **Step 3: Run tests**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo test --lib http::tests)
```

Expected: 1 test passes.

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/http/mod.rs
git commit -m "feat(http): add AppState and /health endpoint"
```

---

# Task 2.7 — `http::auth` — session middleware + `AuthUser` extractor

**Files:**
- Create: `src-tauri/src/http/auth.rs`
- Modify: `src-tauri/src/http/mod.rs` (add `pub mod auth;`)

**Background:** Auth lives at two levels:
1. **Middleware** that extracts the session cookie, calls `Sessions::lookup`, looks up the user, and injects `User` into request extensions. This runs for *every* request to the authed router.
2. **`AuthUser` extractor** — handlers that require a logged-in user take `AuthUser` as a parameter; if no `User` is in extensions, they get a 401 automatically.

We use `tower-cookies` for cookie extraction (it's an axum-friendly layer).

**API to land:**

```rust
pub struct AuthUser(pub crate::auth::users::User);

// Middleware function — applied per route group via `.route_layer(from_fn_with_state(...))`.
pub async fn session_middleware(
    State(state): State<AppState>,
    cookies: Cookies,
    mut request: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response;
```

- [ ] **Step 1: Create `http/auth.rs`**

Create `src-tauri/src/http/auth.rs`:

```rust
//! Session cookie middleware + `AuthUser` extractor.

use axum::extract::{FromRequestParts, State};
use axum::http::request::Parts;
use axum::middleware::Next;
use axum::response::Response;
use tower_cookies::Cookies;

use crate::auth::users::User;
use crate::http::error::ApiError;
use crate::http::AppState;

/// Extractor that yields the authenticated user, or 401 if missing.
///
/// `session_middleware` is responsible for placing the `User` into request
/// extensions. Routes mounted under the authed router get the middleware
/// automatically; legacy 127.0.0.1:19828 routes do not.
#[derive(Debug, Clone)]
pub struct AuthUser(pub User);

impl<S> FromRequestParts<S> for AuthUser
where
    S: Send + Sync,
{
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        parts
            .extensions
            .get::<User>()
            .cloned()
            .map(AuthUser)
            .ok_or_else(ApiError::unauthenticated)
    }
}

/// Middleware: read the session cookie, look up the session, look up the
/// user. On hit, inject `User` into request extensions. On miss, do nothing
/// (the request proceeds; only routes that extract `AuthUser` will reject).
pub async fn session_middleware(
    State(state): State<AppState>,
    cookies: Cookies,
    mut request: axum::extract::Request,
    next: Next,
) -> Response {
    if let Some(cookie) = cookies.get(&state.config.session_cookie_name) {
        if let Some(user_id) = state.sessions.lookup(cookie.value()) {
            if let Some(user) = state.users.lookup_user(&user_id) {
                request.extensions_mut().insert(user);
            }
        }
    }
    next.run(request).await
}
```

- [ ] **Step 2: Declare the auth module**

Modify `src-tauri/src/http/mod.rs` to add `pub mod auth;` immediately after `pub mod error;`.

- [ ] **Step 3: Tests come bundled with the next task**

Auth middleware is best tested end-to-end with login/whoami handlers, so we defer tests to Task 2.8 where those handlers exist.

- [ ] **Step 4: Verify it compiles**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo check)
```

Expected: builds with no errors.

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/http/auth.rs src-tauri/src/http/mod.rs
git commit -m "feat(http): add session middleware and AuthUser extractor"
```

---

# Task 2.8 — `/auth/login`, `/auth/logout`, `/auth/whoami`

**Files:**
- Modify: `src-tauri/src/http/auth.rs` (add handlers + router)
- Modify: `src-tauri/src/http/mod.rs` (mount the auth routes)

**Background:** Three handlers:
- `POST /api/v1/auth/login` `{username, password}` → 200 + `Set-Cookie` (HttpOnly; SameSite=Lax; Max-Age=2592000) on success, 401 with `INVALID_CREDENTIALS` on failure.
- `POST /api/v1/auth/logout` → reads cookie, deletes session, returns 204 + `Set-Cookie: …=; Max-Age=0`.
- `GET /api/v1/auth/whoami` → returns `{user_id, username, recently_opened}` from the request's `AuthUser`, or 401 if missing.

`Set-Cookie` is built directly via `tower_cookies::Cookie::build` so we control flags. 30-day Max-Age comes from `DEFAULT_SESSION_TTL_SECS` matching `Sessions::with_ttl(DEFAULT)`.

- [ ] **Step 1: Add the handlers**

Append to `src-tauri/src/http/auth.rs`:

```rust
use axum::extract::Json as ExtractJson;
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::routing::{get, post};
use axum::Json;
use axum::Router;
use serde::Deserialize;
use serde_json::json;
use tower_cookies::Cookie;

use crate::auth::sessions::SessionId;

// 30 days in seconds — matches Sessions DEFAULT_SESSION_TTL_SECS
const COOKIE_MAX_AGE_SECS: i64 = 60 * 60 * 24 * 30;

#[derive(Debug, Deserialize)]
pub struct LoginRequest {
    pub username: String,
    pub password: String,
}

pub fn auth_router() -> Router<AppState> {
    Router::new()
        .route("/api/v1/auth/login", post(login))
        .route("/api/v1/auth/logout", post(logout))
        .route("/api/v1/auth/whoami", get(whoami))
}

async fn login(
    State(state): State<AppState>,
    cookies: Cookies,
    ExtractJson(body): ExtractJson<LoginRequest>,
) -> Result<axum::response::Response, ApiError> {
    let user = state
        .users
        .verify_password(&body.username, &body.password)
        .map_err(|_| ApiError::invalid_credentials())?;

    let session_id = state
        .sessions
        .create(&user.id)
        .map_err(|e| ApiError::internal(format!("could not create session: {e}")))?;

    let cookie = Cookie::build((
        state.config.session_cookie_name.clone(),
        session_id.as_str().to_string(),
    ))
    .http_only(true)
    .same_site(tower_cookies::cookie::SameSite::Lax)
    .max_age(time::Duration::seconds(COOKIE_MAX_AGE_SECS))
    .path("/")
    .build();
    cookies.add(cookie);

    Ok((
        StatusCode::OK,
        Json(json!({"user_id": user.id, "username": user.username})),
    )
        .into_response())
}

async fn logout(
    State(state): State<AppState>,
    cookies: Cookies,
) -> Result<StatusCode, ApiError> {
    if let Some(cookie) = cookies.get(&state.config.session_cookie_name) {
        // Best-effort delete — even if sled errors, we still want to clear
        // the client cookie below.
        let _ = state.sessions.delete(cookie.value());
    }
    let mut empty = Cookie::new(state.config.session_cookie_name.clone(), "");
    empty.set_path("/");
    empty.set_max_age(time::Duration::seconds(0));
    cookies.add(empty);
    Ok(StatusCode::NO_CONTENT)
}

async fn whoami(
    State(state): State<AppState>,
    AuthUser(user): AuthUser,
) -> Json<serde_json::Value> {
    let recently_opened = state.user_data.recently_opened(&user.id);
    Json(json!({
        "user_id": user.id,
        "username": user.username,
        "recently_opened": recently_opened,
    }))
}
```

Note: `tower-cookies` re-exports `time::Duration`, but the explicit `time` dep is not yet in `Cargo.toml`. Verify by trying to compile. If `time` is missing, add it: `time = "0.3"` under `[dependencies]`.

- [ ] **Step 2: Mount the auth router and session middleware**

Modify `src-tauri/src/http/mod.rs`. Replace the `main_router` function with:

```rust
use axum::middleware::from_fn_with_state;
use tower_cookies::CookieManagerLayer;

pub fn main_router(state: AppState) -> Router {
    let authed = Router::new()
        .route("/api/v1/health", get(health))
        .merge(auth::auth_router())
        // Session middleware: extract cookie, inject User if valid.
        .route_layer(from_fn_with_state(state.clone(), auth::session_middleware))
        .with_state(state.clone());

    Router::new()
        .merge(authed)
        // Cookie layer needs to be outermost so cookies are parsed before
        // the session middleware runs.
        .layer(CookieManagerLayer::new())
}
```

- [ ] **Step 3: Write integration tests**

Append to the `#[cfg(test)] mod tests` block in `src-tauri/src/http/mod.rs`:

```rust
    use crate::auth::users::hash_password;
    use tower_cookies::cookie::time::Duration;

    fn build_state_with_user(
        username: &str,
        password: &str,
    ) -> (TempDir, AppState) {
        let dir = TempDir::new().unwrap();
        let hash = hash_password(password).unwrap();
        let users_path = dir.path().join("users.toml");
        std::fs::write(
            &users_path,
            format!("[users.{username}]\npassword_hash = \"{hash}\"\n"),
        )
        .unwrap();
        let users = Users::load(&users_path).unwrap();
        let sessions = Sessions::open(&dir.path().join("sessions")).unwrap();
        let user_data = UserData::new(dir.path().to_path_buf());
        let bus = SessionBus::new();
        let cfg = ServerConfig {
            port: 8080,
            projects_root: PathBuf::from("./projects"),
            data_root: dir.path().to_path_buf(),
            legacy_19828_enabled: true,
            session_cookie_name: "test_session".into(),
        };
        let state = AppState {
            users: Arc::new(users),
            sessions,
            user_data,
            session_bus: bus,
            config: Arc::new(cfg),
        };
        (dir, state)
    }

    fn extract_set_cookie(resp: &axum::response::Response) -> String {
        resp.headers()
            .get(axum::http::header::SET_COOKIE)
            .expect("set-cookie present")
            .to_str()
            .unwrap()
            .to_string()
    }

    #[tokio::test]
    async fn whoami_without_cookie_is_401() {
        let (_dir, state) = build_state_with_user("alice", "pw");
        let app = main_router(state);
        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/api/v1/auth/whoami")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), 401);
    }

    #[tokio::test]
    async fn login_with_wrong_password_is_401() {
        let (_dir, state) = build_state_with_user("alice", "pw");
        let app = main_router(state);
        let body = r#"{"username":"alice","password":"wrong"}"#;
        let resp = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/v1/auth/login")
                    .header("content-type", "application/json")
                    .body(axum::body::Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), 401);
        let body = to_bytes(resp.into_body(), 4096).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(v["error"]["code"], "INVALID_CREDENTIALS");
    }

    #[tokio::test]
    async fn login_then_whoami_with_cookie_works() {
        let (_dir, state) = build_state_with_user("alice", "pw");
        let app = main_router(state.clone());

        let body = r#"{"username":"alice","password":"pw"}"#;
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/v1/auth/login")
                    .header("content-type", "application/json")
                    .body(axum::body::Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), 200);
        let set_cookie = extract_set_cookie(&resp);
        assert!(set_cookie.contains("test_session="));
        assert!(set_cookie.contains("HttpOnly"));
        assert!(set_cookie.contains("SameSite=Lax"));
        let cookie_value = set_cookie.split(';').next().unwrap().to_string();

        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/api/v1/auth/whoami")
                    .header("cookie", cookie_value)
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), 200);
        let body = to_bytes(resp.into_body(), 4096).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(v["user_id"], "alice");
        assert_eq!(v["username"], "alice");
        assert!(v["recently_opened"].is_array());
    }

    #[tokio::test]
    async fn logout_invalidates_session_immediately() {
        let (_dir, state) = build_state_with_user("alice", "pw");
        let app = main_router(state.clone());

        // log in
        let body = r#"{"username":"alice","password":"pw"}"#;
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/v1/auth/login")
                    .header("content-type", "application/json")
                    .body(axum::body::Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();
        let cookie = extract_set_cookie(&resp).split(';').next().unwrap().to_string();

        // log out
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/v1/auth/logout")
                    .header("cookie", &cookie)
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), 204);

        // whoami with the now-revoked cookie → 401
        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/api/v1/auth/whoami")
                    .header("cookie", &cookie)
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), 401);
    }
```

The test imports use `tower_cookies::cookie::time::Duration` which re-exports `time` — confirm that `time` doesn't need to be a direct dep by running `cargo check`.

- [ ] **Step 4: Run tests**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo test --lib http)
```

Expected: all `http::*` tests pass (`error` 4 + `mod::tests` 5).

If you need to add `time = "0.3"` to `[dependencies]` for the explicit `time::Duration` usage, do so and re-run.

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/http/ src-tauri/Cargo.toml src-tauri/Cargo.lock
git commit -m "feat(http): add /auth/login, /auth/logout, /auth/whoami handlers"
```

---

# Task 2.9 — SSE skeleton at `GET /api/v1/events`

**Files:**
- Create: `src-tauri/src/http/events.rs`
- Modify: `src-tauri/src/http/mod.rs` (add `pub mod events;`, mount route)

**Background:** Authenticated SSE endpoint. When a browser opens it:
1. Extract session id from cookie.
2. Register a `SessionBus` receiver keyed by that session id.
3. Convert the receiver into an `axum::response::sse::KeepAlive`-wrapped event stream.
4. On disconnect (when the receiver drops), the bus auto-cleans via Task 2.4's design (replacement on re-register; explicit `unregister` on Drop guard).

We use a small RAII guard struct that calls `unregister` on Drop so leaving the stream cleans up reliably.

- [ ] **Step 1: Create `events.rs`**

Create `src-tauri/src/http/events.rs`:

```rust
//! SSE endpoint: a per-session event stream.
//!
//! The browser opens a long-lived GET to `/api/v1/events` with its session
//! cookie. The handler registers an mpsc receiver in `SessionBus` keyed by
//! the session id, then forwards events to the client. Disconnection drops
//! the guard, which unregisters the session from the bus.
//!
//! For Phase 2 there are no senders yet — events get wired in later phases.

use std::convert::Infallible;

use axum::extract::State;
use axum::http::HeaderMap;
use axum::response::sse::{Event, KeepAlive, Sse};
use futures::stream::Stream;
use tower_cookies::Cookies;

use crate::http::error::ApiError;
use crate::http::AppState;

pub async fn events_handler(
    State(state): State<AppState>,
    cookies: Cookies,
    _headers: HeaderMap,
) -> Result<Sse<impl Stream<Item = Result<Event, Infallible>>>, ApiError> {
    let cookie = cookies
        .get(&state.config.session_cookie_name)
        .ok_or_else(ApiError::unauthenticated)?;
    let session_id = cookie.value().to_string();

    // Confirm the session is valid before opening the long-lived stream.
    if state.sessions.lookup(&session_id).is_none() {
        return Err(ApiError::unauthenticated());
    }

    let rx = state.session_bus.register(&session_id);
    let guard = SessionGuard::new(state.session_bus.clone(), session_id.clone());

    let stream = async_stream::stream! {
        // Move the guard into the stream so it lives as long as the
        // connection. When the client disconnects axum drops the stream,
        // which drops the guard, which unregisters from the bus.
        let _guard = guard;
        let mut rx = rx;
        while let Some(evt) = rx.recv().await {
            let body = serde_json::to_string(&evt.data).unwrap_or_else(|_| "{}".into());
            let event = Event::default()
                .event(evt.event_type)
                .data(body);
            yield Ok::<Event, Infallible>(event);
        }
    };

    Ok(Sse::new(stream).keep_alive(KeepAlive::new()))
}

struct SessionGuard {
    bus: crate::storage::session_bus::SessionBus,
    session_id: String,
}

impl SessionGuard {
    fn new(bus: crate::storage::session_bus::SessionBus, session_id: String) -> Self {
        Self { bus, session_id }
    }
}

impl Drop for SessionGuard {
    fn drop(&mut self) {
        self.bus.unregister(&self.session_id);
    }
}
```

`async_stream` is a new dep. Add `async-stream = "0.3"` and `futures = "0.3"` (already present) to `[dependencies]`. Verify `futures` is already in the Cargo.toml (it is, in Phase 1 deps).

- [ ] **Step 2: Mount the route**

In `src-tauri/src/http/mod.rs`, add `pub mod events;` near the other module declarations, and add the route to the authed router. The relevant section of `main_router` becomes:

```rust
let authed = Router::new()
    .route("/api/v1/health", get(health))
    .merge(auth::auth_router())
    .route("/api/v1/events", get(events::events_handler))
    .route_layer(from_fn_with_state(state.clone(), auth::session_middleware))
    .with_state(state.clone());
```

- [ ] **Step 3: Write a basic integration test**

Append to the `#[cfg(test)] mod tests` block in `src-tauri/src/http/mod.rs`:

```rust
    #[tokio::test]
    async fn events_without_cookie_is_401() {
        let (_dir, state) = build_state_with_user("alice", "pw");
        let app = main_router(state);
        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/api/v1/events")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), 401);
    }

    #[tokio::test]
    async fn events_with_valid_session_registers_in_bus() {
        let (_dir, state) = build_state_with_user("alice", "pw");
        let app = main_router(state.clone());

        // Log in to get a cookie
        let body = r#"{"username":"alice","password":"pw"}"#;
        let resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/v1/auth/login")
                    .header("content-type", "application/json")
                    .body(axum::body::Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();
        let cookie = extract_set_cookie(&resp).split(';').next().unwrap().to_string();

        // We can't really "hold the stream open" in a oneshot test, but we
        // can verify the handler at least starts and reaches the registration
        // step. We use a short timeout and then assert the bus saw the session.
        // Spawn the request in a task we'll cancel.
        let bus = state.session_bus.clone();
        let app_cloned = app.clone();
        let cookie_cloned = cookie.clone();
        let handle = tokio::spawn(async move {
            let _ = app_cloned
                .oneshot(
                    Request::builder()
                        .uri("/api/v1/events")
                        .header("cookie", cookie_cloned)
                        .body(axum::body::Body::empty())
                        .unwrap(),
                )
                .await;
        });

        // Yield a few times to let the handler run far enough to register.
        for _ in 0..10 {
            tokio::task::yield_now().await;
            tokio::time::sleep(std::time::Duration::from_millis(5)).await;
            if bus.registered_count() > 0 {
                break;
            }
        }
        assert!(bus.registered_count() >= 1, "session was not registered in bus");

        handle.abort();
    }
```

- [ ] **Step 4: Run tests**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo test --lib http)
```

Expected: all http tests pass (4 error + 7 mod = 11 total).

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/http/ src-tauri/Cargo.toml src-tauri/Cargo.lock
git commit -m "feat(http): add SSE skeleton at /api/v1/events"
```

---

# Task 2.10 — `rust-embed` frontend bundle + SPA fallback

**Files:**
- Create: `src-tauri/src/http/embed.rs`
- Modify: `src-tauri/src/http/mod.rs` (mount fallback)

**Background:** `rust-embed` bakes the Vite-built `dist/` directory into the binary at compile time. The fallback handler:
1. If the path matches an embedded asset → serve it with the right content-type.
2. Otherwise → serve `index.html` so the SPA can do its own routing.

For Phase 2 the frontend isn't ready yet (Phases 5–6) but we still need the embed shell so we can confirm the binary boots and the route catches non-API URLs.

We tell `rust-embed` to source from `dist/` relative to `Cargo.toml`. In Phase 2 there's no `dist/` to bundle yet — we ship a minimal placeholder `dist/index.html` so the embed succeeds and the binary is testable.

- [ ] **Step 1: Create the placeholder `dist/`**

Create `src-tauri/dist/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>LLM Wiki (server placeholder)</title>
</head>
<body>
  <h1>LLM Wiki server</h1>
  <p>Frontend not yet wired (Phase 5–6 will replace this).</p>
</body>
</html>
```

Note: Phase 5–6 will configure Vite to build into this directory or copy from `dist/` at the repo root.

- [ ] **Step 2: Add a `.gitignore` rule**

Append to `src-tauri/.gitignore` (create if missing):

```
# Phase 2 placeholder; replaced by Phase 5–6 Vite build output
dist/
```

Then `git add -f src-tauri/dist/index.html` so the placeholder is tracked despite the gitignore.

- [ ] **Step 3: Create the embed module**

Create `src-tauri/src/http/embed.rs`:

```rust
//! Bundles the frontend `dist/` into the binary via rust-embed and serves
//! it with an SPA fallback: unknown paths return `index.html`.

use axum::body::Body;
use axum::http::{header, StatusCode, Uri};
use axum::response::{IntoResponse, Response};
use rust_embed::RustEmbed;

#[derive(RustEmbed)]
#[folder = "dist/"]
struct Frontend;

pub async fn spa_fallback(uri: Uri) -> Response {
    let path = uri.path().trim_start_matches('/');
    // API routes already handled by other layers; fallback shouldn't see them
    // but we double-check.
    if path.starts_with("api/") {
        return (StatusCode::NOT_FOUND, "not found").into_response();
    }

    if let Some(asset) = Frontend::get(path) {
        let mime = mime_guess::from_path(path).first_or_octet_stream();
        return Response::builder()
            .header(header::CONTENT_TYPE, mime.as_ref())
            .body(Body::from(asset.data.into_owned()))
            .unwrap();
    }

    // SPA fallback → index.html
    if let Some(index) = Frontend::get("index.html") {
        return Response::builder()
            .header(header::CONTENT_TYPE, "text/html; charset=utf-8")
            .body(Body::from(index.data.into_owned()))
            .unwrap();
    }

    (StatusCode::NOT_FOUND, "not found").into_response()
}
```

`mime_guess` is a new dep. Add `mime_guess = "2"` to `[dependencies]`.

- [ ] **Step 4: Mount the fallback**

Modify `src-tauri/src/http/mod.rs`. Add `pub mod embed;` near other declarations. Modify `main_router`:

```rust
pub fn main_router(state: AppState) -> Router {
    let authed = Router::new()
        .route("/api/v1/health", get(health))
        .merge(auth::auth_router())
        .route("/api/v1/events", get(events::events_handler))
        .route_layer(from_fn_with_state(state.clone(), auth::session_middleware))
        .with_state(state.clone());

    Router::new()
        .merge(authed)
        .fallback(embed::spa_fallback)
        .layer(CookieManagerLayer::new())
}
```

- [ ] **Step 5: Write a test**

Append to the `#[cfg(test)] mod tests` block in `src-tauri/src/http/mod.rs`:

```rust
    #[tokio::test]
    async fn unknown_route_falls_back_to_index_html() {
        let (_dir, state) = build_state_with_user("alice", "pw");
        let app = main_router(state);
        let resp = app
            .oneshot(
                Request::builder()
                    .uri("/some/spa/route")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), 200);
        let body = to_bytes(resp.into_body(), 16384).await.unwrap();
        let s = String::from_utf8_lossy(&body);
        assert!(s.contains("<!DOCTYPE html>"));
        assert!(s.contains("<html"));
    }
```

- [ ] **Step 6: Run tests**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo test --lib http)
```

Expected: all 12 http tests pass.

- [ ] **Step 7: Commit**

```bash
git add src-tauri/src/http/embed.rs src-tauri/src/http/mod.rs src-tauri/dist/ src-tauri/.gitignore src-tauri/Cargo.toml src-tauri/Cargo.lock
git commit -m "feat(http): bundle frontend via rust-embed with SPA fallback"
```

---

# Task 2.11 — `llm-wiki-server` binary: boot + dual listeners

**Files:**
- Modify: `src-tauri/src/bin/llm_wiki_server.rs`

**Background:** Replace the placeholder panic with the real entry point:

1. Build tokio multi-thread runtime.
2. Load `ServerConfig` from env.
3. Create `data_root` if missing (with `0o700` on unix). Same for `projects_root`.
4. Load `Users` (if `users.toml` is missing under `data_root`, write a placeholder file with a comment and exit with a friendly error — admin needs to populate it).
5. Open `Sessions` at `<data_root>/sessions/`.
6. Build `AppState`.
7. Mount the auth-protected router on `0.0.0.0:<port>`.
8. If `legacy_19828_enabled`, mount an unauth router with the same handlers on `127.0.0.1:19828`.
9. `tokio::signal::ctrl_c` for graceful shutdown.

For Phase 2 the **legacy listener** can mount the same `main_router` but without the auth middleware — keeping things simple. In Phase 4 it'll instead mount the `/agent/*` subset; until then "same router minus auth" is fine. We'll add a `legacy_router(AppState)` helper next to `main_router`.

- [ ] **Step 1: Add `legacy_router` to `http/mod.rs`**

Append to `src-tauri/src/http/mod.rs`:

```rust
/// Router for the legacy 127.0.0.1:19828 listener: same handlers as
/// `main_router` but without the session middleware. Phase 4 will narrow
/// this to the agent-facing subset.
pub fn legacy_router(state: AppState) -> Router {
    let r = Router::new()
        .route("/api/v1/health", get(health))
        .with_state(state);
    Router::new().merge(r).layer(CookieManagerLayer::new())
}
```

- [ ] **Step 2: Replace `bin/llm_wiki_server.rs`**

Replace `src-tauri/src/bin/llm_wiki_server.rs` with:

```rust
//! `llm-wiki-server` — the browser/LAN HTTP server entry point.

use std::net::SocketAddr;
use std::path::Path;

use llm_wiki_lib::auth::sessions::Sessions;
use llm_wiki_lib::auth::users::Users;
use llm_wiki_lib::config::ServerConfig;
use llm_wiki_lib::http::{legacy_router, main_router, AppState};
use llm_wiki_lib::storage::session_bus::SessionBus;
use llm_wiki_lib::storage::user_data::UserData;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let config = ServerConfig::from_env()?;

    ensure_dir(&config.data_root)?;
    ensure_dir(&config.projects_root)?;

    let users_path = config.data_root.join("users.toml");
    if !users_path.exists() {
        eprintln!(
            "no users.toml at {} — create it with at least one user before starting the server",
            users_path.display()
        );
        eprintln!("example:");
        eprintln!("  [users.alice]");
        eprintln!("  password_hash = \"<argon2 hash>\"");
        std::process::exit(2);
    }

    let users = Users::load(&users_path)?;
    let sessions = Sessions::open(&config.data_root.join("sessions"))?;
    let user_data = UserData::new(config.data_root.clone());
    let session_bus = SessionBus::new();

    let state = AppState {
        users: std::sync::Arc::new(users),
        sessions,
        user_data,
        session_bus,
        config: std::sync::Arc::new(config.clone()),
    };

    // Main listener: 0.0.0.0:<port> with auth.
    let main_addr: SocketAddr = format!("0.0.0.0:{}", config.port).parse()?;
    let main_app = main_router(state.clone());
    let main_listener = tokio::net::TcpListener::bind(&main_addr).await?;
    eprintln!("listening on http://{main_addr}");

    let mut main_handle = tokio::spawn(async move {
        axum::serve(main_listener, main_app).await
    });

    // Legacy 127.0.0.1:19828 (no auth) — opt-out via config.
    let mut legacy_handle: Option<tokio::task::JoinHandle<std::io::Result<()>>> = None;
    if config.legacy_19828_enabled {
        let legacy_addr: SocketAddr = "127.0.0.1:19828".parse()?;
        let legacy_app = legacy_router(state.clone());
        let legacy_listener = tokio::net::TcpListener::bind(&legacy_addr).await?;
        eprintln!("legacy listener on http://{legacy_addr}");
        legacy_handle = Some(tokio::spawn(async move {
            axum::serve(legacy_listener, legacy_app).await
        }));
    }

    // Graceful shutdown on Ctrl+C
    tokio::select! {
        _ = tokio::signal::ctrl_c() => {
            eprintln!("shutdown signal received");
        }
        r = &mut main_handle => {
            r??;
        }
    }

    main_handle.abort();
    if let Some(h) = legacy_handle {
        h.abort();
    }

    Ok(())
}

fn ensure_dir(path: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let perms = std::fs::Permissions::from_mode(0o700);
        std::fs::set_permissions(path, perms)?;
    }
    Ok(())
}
```

- [ ] **Step 3: Verify the workspace builds**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo build --bin llm-wiki-server)
```

Expected: builds successfully (probably takes a minute since this is the first build that includes axum).

- [ ] **Step 4: Smoke-test the binary**

Run:

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH"
cd /tmp && mkdir -p llm-wiki-smoke/data llm-wiki-smoke/projects && cd llm-wiki-smoke
# Generate a test users.toml with a known password
LLM_WIKI_DATA_ROOT=./data LLM_WIKI_PROJECTS_ROOT=./projects \
  cargo run --manifest-path $REPO/src-tauri/Cargo.toml \
            --bin llm-wiki-server &
SERVER_PID=$!
sleep 3
```

You'll get the "no users.toml" error and exit code 2. Good — that's expected. To actually test login, we need to populate `users.toml` first. For Task 2.11 the success criterion is just "the binary loads, prints the error, and exits cleanly." End-to-end login is verified in Task 2.12.

Don't worry about leftover processes — the `sleep 3` + `wait` pattern below is just for the smoke check.

Actually, simpler smoke: just confirm the binary boots far enough to read config:

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH"
LLM_WIKI_DATA_ROOT=/tmp/nonexistent-llm-wiki cargo run --manifest-path $REPO/src-tauri/Cargo.toml --bin llm-wiki-server
```

Expected: prints "no users.toml at .../users.toml — create it with at least one user before starting the server" and exits with code 2.

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/bin/llm_wiki_server.rs src-tauri/src/http/mod.rs
git commit -m "feat(server): wire llm-wiki-server binary with dual listeners"
```

---

# Task 2.12 — End-to-end smoke test

**Files:**
- Create: `plans/phase-2-smoke.md` (a tiny runbook for what was verified)

**Background:** Final acceptance gate for Phase 2. The binary boots; auth works end-to-end; tests are green; nothing regressed.

- [ ] **Step 1: Run the full lib test suite**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo test --lib)
```

Expected: green (no failures, no regressions vs. Phase 1's 159 tests; new tests bring the total to roughly 159 + 11 http + 6 config + 6 session_bus + 3 lookup_user ≈ 185).

- [ ] **Step 2: Build the binary in release mode**

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" && (cd src-tauri && cargo build --release --bin llm-wiki-server)
```

Expected: builds. Binary at `src-tauri/target/release/llm-wiki-server`.

- [ ] **Step 3: End-to-end auth flow via curl**

In a temp directory:

```bash
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH"
SMOKE=$(mktemp -d)
mkdir -p "$SMOKE/data" "$SMOKE/projects"

# Generate a password hash for "demo-password" using a tiny rust one-liner.
# We'll do this by spawning a temporary cargo run that calls hash_password.
# For Phase 2 — since there's no admin CLI yet — we write a one-shot script:

cat > "$SMOKE/hash.rs" <<'EOF'
use llm_wiki_lib::auth::users::hash_password;
fn main() {
    let pw = std::env::args().nth(1).expect("usage: hash <password>");
    println!("{}", hash_password(&pw).unwrap());
}
EOF
# Since we can't easily run this without a separate cargo target, generate the hash
# via the test crate instead — drop a one-off binary into src/bin/:
cp "$SMOKE/hash.rs" $REPO/src-tauri/src/bin/hash_password_oneshot.rs
HASH=$(cd $REPO/src-tauri && cargo run --bin hash_password_oneshot -- demo-password 2>/dev/null | tail -1)
rm $REPO/src-tauri/src/bin/hash_password_oneshot.rs

cat > "$SMOKE/data/users.toml" <<EOF
[users.alice]
password_hash = "$HASH"
EOF

# Start the server in the background
LLM_WIKI_DATA_ROOT="$SMOKE/data" LLM_WIKI_PROJECTS_ROOT="$SMOKE/projects" \
  cargo run --release --manifest-path $REPO/src-tauri/Cargo.toml --bin llm-wiki-server > "$SMOKE/server.log" 2>&1 &
SERVER_PID=$!
sleep 3

# (a) whoami without cookie → 401
curl -s -o "$SMOKE/whoami-401.json" -w '%{http_code}\n' http://localhost:8080/api/v1/auth/whoami
cat "$SMOKE/whoami-401.json"
# Expected: 401 and body {"error":{"code":"UNAUTHENTICATED",...}}

# (b) login with valid creds → 200 + Set-Cookie
curl -s -c "$SMOKE/cookies.txt" -X POST -H 'content-type: application/json' \
  -d '{"username":"alice","password":"demo-password"}' \
  http://localhost:8080/api/v1/auth/login
# Expected: {"user_id":"alice","username":"alice"}

# (c) whoami with cookie → 200
curl -s -b "$SMOKE/cookies.txt" http://localhost:8080/api/v1/auth/whoami
# Expected: {"user_id":"alice","username":"alice","recently_opened":[]}

# (d) Legacy listener responds without auth
curl -s -o "$SMOKE/legacy.json" -w '%{http_code}\n' http://127.0.0.1:19828/api/v1/health
cat "$SMOKE/legacy.json"
# Expected: 200 and body {"status":"ok"}

kill $SERVER_PID
```

If all four steps return the expected output, Phase 2 is complete.

- [ ] **Step 4: Write the runbook**

Create `plans/phase-2-smoke.md` documenting the above for future reference:

```markdown
# Phase 2 smoke test — manual verification

After Phase 2 lands, this runbook verifies end-to-end behavior.

## Prereqs
- macOS with Rust toolchain at `~/.rustup/...`
- Project at `~/Sync/Scailar/Software/llm_wiki`

## Steps
[paste the curl sequence from Task 2.12 step 3]

## Expected outcomes
1. Whoami without cookie → 401 with `{"error":{"code":"UNAUTHENTICATED"}}`
2. Login with wrong password → 401 with `{"error":{"code":"INVALID_CREDENTIALS"}}`
3. Login with right password → 200 + `Set-Cookie: llm_wiki_session=...; HttpOnly; SameSite=Lax`
4. Whoami with cookie → 200 + `{"user_id":"alice","username":"alice","recently_opened":[]}`
5. Legacy listener `127.0.0.1:19828/api/v1/health` → 200 + `{"status":"ok"}`
```

- [ ] **Step 5: Commit**

```bash
git add plans/phase-2-smoke.md
git commit -m "docs: add Phase 2 smoke test runbook"
```

---

# Phase 2 — Done check

Before moving to Phase 3, verify:

- [ ] `cargo test --lib` — all tests pass (≈ 185 total)
- [ ] `cargo build --release --bin llm-wiki-server` succeeds
- [ ] `cargo build --bin llm-wiki` — the existing Tauri binary STILL builds (Phase 2 didn't break Tauri)
- [ ] `cargo run --bin llm-wiki-server` boots and responds to all 4 curl steps in Task 2.12 step 3
- [ ] No new compiler warnings introduced
- [ ] Each commit cleanly maps to a task in this plan; no squash-worthy noise

---

# Look-ahead to Phase 3

Phase 3 (core extraction) is the next milestone. It's mostly mechanical refactoring: move business logic out of `#[tauri::command]` wrappers in `src-tauri/src/commands/*.rs` into `src-tauri/src/core/*.rs`. Each Tauri command becomes a 3-line wrapper calling `core::*`. The desktop app keeps running unchanged.

When you're ready, ask for the detailed Phase 3 plan and we'll write it with the lessons of Phase 2 baked in.

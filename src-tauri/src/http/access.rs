//! Per-user project access enforcement shared by every project-scoped handler.
//!
//! The rule: a request may touch a project only if the caller (a `User`) is
//! allowed it by `permissions.toml`. When no permissions file exists,
//! enforcement is disabled (allow-all) so existing deployments keep working
//! until the admin panel starts syncing.
//!
//! Handlers should resolve the project through [`resolve_authorized_project_root`]
//! (path is a project reference) or gate an already-resolved filesystem path
//! through [`require_path_access`] (path may point anywhere under
//! `projects_root`). Both fail closed with `403` for unauthorized access.

use std::path::{Path, PathBuf};

use axum::http::StatusCode;

use crate::auth::permissions::Permissions;
use crate::auth::users::User;
use crate::core::project::project_id_from_canonical_path;
use crate::http::error::ApiError;
use crate::http::AppState;
use crate::storage::paths::resolve_project_path;

fn forbidden() -> ApiError {
    ApiError::new(StatusCode::FORBIDDEN, "FORBIDDEN", "no access to this project")
}

/// Server-controlled candidate keys for a project root: canonical id (what the
/// panel stores) plus the directory name for legacy/name-based grants. The
/// caller's raw input is intentionally never used as a key.
fn project_keys(root: &Path) -> (String, String) {
    let canon = root
        .canonicalize()
        .unwrap_or_else(|_| root.to_path_buf());
    let id = project_id_from_canonical_path(&canon);
    let name = canon
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_default();
    (id, name)
}

/// Resolve `project_path` (an id, name, or path referring to a project) to its
/// root directory, enforcing that `user` may access it.
pub fn resolve_authorized_project_root(
    state: &AppState,
    user: &User,
    project_path: &str,
) -> Result<PathBuf, ApiError> {
    let root = resolve_project_path(&state.config.projects_root, project_path).map_err(|e| {
        ApiError::bad_request("PATH_ESCAPE", e.to_string())
            .with_details(serde_json::json!({ "requested": project_path }))
    })?;
    let perms = Permissions::load(&state.config.data_root);
    if perms.enabled() {
        let (id, name) = project_keys(&root);
        if !perms.can_access(&user.id, &[id.as_str(), name.as_str()]) {
            return Err(forbidden());
        }
    }
    Ok(root)
}

/// Enforce that an already-resolved filesystem `path` lives inside a project
/// the `user` may access. `path` must be under `projects_root`.
pub fn require_path_access(
    state: &AppState,
    user: &User,
    path: &Path,
) -> Result<(), ApiError> {
    let perms = Permissions::load(&state.config.data_root);
    // Disabled (no file) or admin: always allowed. The admin short-circuit also
    // lets admins browse the projects_root itself (which has no project dir to
    // key on below).
    if !perms.enabled() || perms.is_admin(&user.id) {
        return Ok(());
    }
    let canon = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    let root = state
        .config
        .projects_root
        .canonicalize()
        .unwrap_or_else(|_| state.config.projects_root.clone());
    // The project directory is the first path component under projects_root.
    let rel = canon.strip_prefix(&root).map_err(|_| forbidden())?;
    let first = rel.components().next().ok_or_else(forbidden)?;
    let project_root = root.join(first.as_os_str());
    let (id, name) = project_keys(&project_root);
    if perms.can_access(&user.id, &[id.as_str(), name.as_str()]) {
        Ok(())
    } else {
        Err(forbidden())
    }
}

/// Constant-time comparison for shared secrets (bridge/admin endpoints).
pub fn secret_eq(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    if a.len() != b.len() {
        return false;
    }
    let mut diff = 0u8;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

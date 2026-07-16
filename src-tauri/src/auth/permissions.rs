//! Per-user project access control, synced from an external admin panel.
//!
//! The source of truth is `<data_root>/permissions.toml`, written by the panel
//! (via `PUT /api/v1/admin/permissions`). Format:
//!
//! ```toml
//! admins = ["user-id-1", "user-id-2"]
//!
//! [access]
//! "user-id-3" = ["project-id-or-name", "another-project"]
//! ```
//!
//! Enforcement is DISABLED when the file is absent, so deploying this build
//! does not change behaviour until the panel starts syncing. Once the file
//! exists, non-admin users see (and can access) only their listed projects.
//!
//! The file is read fresh by `load()` so edits take effect without a restart;
//! callers should `load()` once per request and reuse the result.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use serde::{Deserialize, Serialize};

/// On-disk shape of `permissions.toml`.
#[derive(Debug, Default, Clone, Serialize, Deserialize)]
pub struct PermissionsFile {
    #[serde(default)]
    pub admins: Vec<String>,
    /// `user_id` -> allowed project keys. A key may match a project's id, its
    /// directory name, or its relative path — whichever the panel stored.
    #[serde(default)]
    pub access: HashMap<String, Vec<String>>,
}

/// In-memory access-control snapshot.
#[derive(Debug, Default, Clone)]
pub struct Permissions {
    enabled: bool,
    admins: HashSet<String>,
    access: HashMap<String, HashSet<String>>,
}

impl Permissions {
    fn file_path(data_root: &Path) -> std::path::PathBuf {
        data_root.join("permissions.toml")
    }

    /// Load from `<data_root>/permissions.toml`. An absent or unreadable file
    /// yields a disabled (allow-all) snapshot. A malformed file is treated as
    /// empty-but-enabled (fail closed for non-admins) so a broken sync does not
    /// silently grant everyone access.
    pub fn load(data_root: &Path) -> Self {
        let raw = match std::fs::read_to_string(Self::file_path(data_root)) {
            Ok(raw) => raw,
            // Only an ABSENT file disables enforcement (allow-all). Any other
            // read error (permissions, transient IO) must fail CLOSED so a
            // hiccup can't silently switch off all access control.
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                return Permissions::default();
            }
            Err(e) => {
                eprintln!("[permissions] cannot read permissions.toml (failing closed): {e}");
                return Permissions { enabled: true, ..Permissions::default() };
            }
        };
        let parsed: PermissionsFile = toml::from_str(&raw).unwrap_or_else(|e| {
            // A malformed file fails closed (below); surface it so a broken sync
            // is diagnosable rather than silently locking users out.
            eprintln!("[permissions] failed to parse permissions.toml: {e}");
            PermissionsFile::default()
        });
        Permissions {
            enabled: true,
            admins: parsed.admins.into_iter().collect(),
            access: parsed
                .access
                .into_iter()
                .map(|(k, v)| (k, v.into_iter().collect()))
                .collect(),
        }
    }

    /// True when a permissions file is present and enforcement is active.
    pub fn enabled(&self) -> bool {
        self.enabled
    }

    pub fn is_admin(&self, user_id: &str) -> bool {
        self.admins.contains(user_id)
    }

    /// Whether `user_id` may see/access a project. `keys` are the project's
    /// candidate identifiers (id, name, relative path); a match on any grants
    /// access. Admins and the allow-all (disabled) state always pass.
    pub fn can_access(&self, user_id: &str, keys: &[&str]) -> bool {
        if !self.enabled || self.is_admin(user_id) {
            return true;
        }
        match self.access.get(user_id) {
            Some(allowed) => keys.iter().any(|k| allowed.contains(*k)),
            None => false,
        }
    }

    /// Persist a permissions file atomically.
    pub fn save(data_root: &Path, file: &PermissionsFile) -> std::io::Result<()> {
        let path = Self::file_path(data_root);
        let body = toml::to_string_pretty(file)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let tmp = path.with_extension("toml.tmp");
        std::fs::write(&tmp, body)?;
        std::fs::rename(&tmp, &path)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn absent_file_is_disabled_and_allows_all() {
        let dir = TempDir::new().unwrap();
        let p = Permissions::load(dir.path());
        assert!(!p.enabled());
        assert!(p.can_access("anyone", &["any-project"]));
    }

    #[test]
    fn enforces_access_when_file_present() {
        let dir = TempDir::new().unwrap();
        let file = PermissionsFile {
            admins: vec!["boss".into()],
            access: HashMap::from([("alice".to_string(), vec!["proj-a".to_string()])]),
        };
        Permissions::save(dir.path(), &file).unwrap();

        let p = Permissions::load(dir.path());
        assert!(p.enabled());
        // admin sees everything
        assert!(p.can_access("boss", &["anything"]));
        // alice only her project (by any candidate key)
        assert!(p.can_access("alice", &["proj-a"]));
        assert!(p.can_access("alice", &["some-id", "proj-a"]));
        assert!(!p.can_access("alice", &["proj-b"]));
        // unlisted user sees nothing
        assert!(!p.can_access("stranger", &["proj-a"]));
    }

    #[test]
    fn malformed_file_fails_closed_for_non_admins() {
        let dir = TempDir::new().unwrap();
        std::fs::write(dir.path().join("permissions.toml"), "not valid toml : : :").unwrap();
        let p = Permissions::load(dir.path());
        assert!(p.enabled());
        assert!(!p.can_access("alice", &["proj-a"]));
    }
}

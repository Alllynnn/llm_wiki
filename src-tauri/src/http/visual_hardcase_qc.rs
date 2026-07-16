//! Token-protected visual-hardcase QC job endpoints.

use axum::extract::{Path as AxumPath, State};
use axum::http::{HeaderMap, StatusCode};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use tokio::process::Command;
use uuid::Uuid;

use crate::http::error::ApiError;
use crate::http::visual_hardcase_qc_support::{
    ensure_token_authorized, expand_rows, expected_row_count, non_empty, now, tail, worker_disabled,
};
use crate::http::AppState;

const DEFAULT_HOMEWORK_URL: &str =
    "https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl";
const DEFAULT_SHEET_ID: &str = "eL8Rfl";
pub fn visual_hardcase_qc_router() -> Router<AppState> {
    Router::new()
        .route("/api/v1/visual-hardcase/qc-jobs", post(create_job))
        .route("/api/v1/visual-hardcase/qc-jobs/{job_id}", get(get_job))
}

#[derive(Debug, Deserialize)]
struct CreateJobRequest {
    #[serde(default, alias = "newcomerName")]
    newcomer_name: String,
    #[serde(default)]
    rows: String,
    #[serde(default, alias = "rowNumbers")]
    row_numbers: Vec<u32>,
    #[serde(default, alias = "homeworkUrl")]
    homework_url: String,
    #[serde(default, alias = "sheetId")]
    sheet_id: String,
    #[serde(default, alias = "sessionId")]
    session_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct QcJob {
    ok: bool,
    #[serde(rename = "jobId")]
    job_id: String,
    status: String,
    #[serde(rename = "newcomerName")]
    newcomer_name: String,
    rows: String,
    #[serde(rename = "rowNumbers")]
    row_numbers: Vec<u32>,
    #[serde(rename = "homeworkUrl")]
    homework_url: String,
    #[serde(rename = "sheetId")]
    sheet_id: String,
    #[serde(rename = "sessionId")]
    session_id: String,
    #[serde(rename = "createdAt")]
    created_at: String,
    #[serde(rename = "updatedAt")]
    updated_at: String,
    #[serde(skip_serializing_if = "Option::is_none", rename = "startedAt")]
    started_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "finishedAt")]
    finished_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "returnCode")]
    return_code: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    stdout: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    stderr: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

async fn create_job(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<CreateJobRequest>,
) -> Result<(StatusCode, Json<serde_json::Value>), ApiError> {
    ensure_token_authorized(&headers)?;
    let row_numbers = normalize_rows(&req)?;
    let expected = expected_row_count();
    if expected > 0 && row_numbers.len() != expected {
        return Err(ApiError::bad_request(
            "BAD_REQUEST",
            format!("rows must contain exactly {expected} row numbers"),
        ));
    }

    let rows = if req.rows.trim().is_empty() {
        row_numbers
            .iter()
            .map(u32::to_string)
            .collect::<Vec<_>>()
            .join(",")
    } else {
        req.rows.trim().to_string()
    };
    let now = now();
    let job = QcJob {
        ok: true,
        job_id: Uuid::new_v4().to_string(),
        status: "queued".to_string(),
        newcomer_name: req.newcomer_name.trim().to_string(),
        rows,
        row_numbers,
        homework_url: non_empty(req.homework_url, DEFAULT_HOMEWORK_URL),
        sheet_id: non_empty(req.sheet_id, DEFAULT_SHEET_ID),
        session_id: req.session_id.trim().to_string(),
        created_at: now.clone(),
        updated_at: now,
        started_at: None,
        finished_at: None,
        return_code: None,
        stdout: None,
        stderr: None,
        error: None,
    };

    write_job(&state, &job).await?;
    spawn_worker(state.clone(), job.clone());
    Ok((
        StatusCode::ACCEPTED,
        Json(serde_json::json!({
            "ok": true,
            "jobId": job.job_id,
            "status": job.status,
            "rows": job.rows,
            "rowNumbers": job.row_numbers,
        })),
    ))
}

async fn get_job(
    State(state): State<AppState>,
    headers: HeaderMap,
    AxumPath(job_id): AxumPath<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    ensure_token_authorized(&headers)?;
    let job = read_job(&state, &job_id).await?;
    Ok(Json(
        serde_json::to_value(job).map_err(|e| ApiError::internal(e.to_string()))?,
    ))
}

fn normalize_rows(req: &CreateJobRequest) -> Result<Vec<u32>, ApiError> {
    if !req.row_numbers.is_empty() {
        return Ok(req.row_numbers.clone());
    }
    expand_rows(&req.rows).map_err(|e| ApiError::bad_request("BAD_REQUEST", e))
}

fn job_dir(state: &AppState) -> PathBuf {
    state.config.data_root.join("visual-hardcase-qc-jobs")
}

fn job_path(state: &AppState, job_id: &str) -> PathBuf {
    job_dir(state).join(format!("{job_id}.json"))
}

async fn write_job(state: &AppState, job: &QcJob) -> Result<(), ApiError> {
    tokio::fs::create_dir_all(job_dir(state))
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    let body = serde_json::to_string_pretty(job).map_err(|e| ApiError::internal(e.to_string()))?;
    tokio::fs::write(job_path(state, &job.job_id), body)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))
}

async fn read_job(state: &AppState, job_id: &str) -> Result<QcJob, ApiError> {
    if job_id.contains('/') || job_id.contains('\\') || job_id.contains("..") {
        return Err(ApiError::bad_request("BAD_REQUEST", "invalid job id"));
    }
    let body = tokio::fs::read_to_string(job_path(state, job_id))
        .await
        .map_err(|_| ApiError::new(StatusCode::NOT_FOUND, "NOT_FOUND", "job not found"))?;
    serde_json::from_str(&body).map_err(|e| ApiError::internal(e.to_string()))
}

fn spawn_worker(state: AppState, mut job: QcJob) {
    tokio::spawn(async move {
        if worker_disabled() {
            job.status = "queued_worker_disabled".to_string();
            job.updated_at = now();
            let _ = write_job(&state, &job).await;
            return;
        }
        let Some(script) = worker_script() else {
            job.status = "failed".to_string();
            job.error = Some(
                "QC worker script not found; set VISUAL_HARDCASE_QC_WORKER_SCRIPT".to_string(),
            );
            job.updated_at = now();
            let _ = write_job(&state, &job).await;
            return;
        };
        run_worker(&state, &mut job, script).await;
    });
}

async fn run_worker(state: &AppState, job: &mut QcJob, script: PathBuf) {
    job.status = "running".to_string();
    job.started_at = Some(now());
    job.updated_at = now();
    let _ = write_job(state, job).await;
    let python =
        std::env::var("VISUAL_HARDCASE_QC_PYTHON").unwrap_or_else(|_| "python".to_string());
    let is_legacy = script
        .file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name == "watch_newcomer_sheet.py");
    let mut command = Command::new(python);
    command.arg(script);
    if is_legacy {
        command.arg("--once");
    } else {
        command
            .arg("--job-id")
            .arg(&job.job_id)
            .arg("--job-dir")
            .arg(job_dir(state))
            .arg("--max-rows-per-cycle")
            .arg(job.row_numbers.len().max(1).to_string())
            .arg("--max-image-attachments")
            .arg(
                std::env::var("VISUAL_HARDCASE_QC_MAX_IMAGE_ATTACHMENTS")
                    .unwrap_or_else(|_| "50".to_string()),
            );
    }
    command
        .arg("--rows")
        .arg(&job.rows)
        .arg("--url")
        .arg(&job.homework_url)
        .arg("--sheet-id")
        .arg(&job.sheet_id);
    let output = command.output().await;
    match output {
        Ok(output) => {
            job.status = if output.status.success() {
                "completed"
            } else {
                "failed"
            }
            .to_string();
            job.return_code = output.status.code();
            job.stdout = Some(tail(
                String::from_utf8_lossy(&output.stdout).to_string(),
                8000,
            ));
            job.stderr = Some(tail(
                String::from_utf8_lossy(&output.stderr).to_string(),
                4000,
            ));
        }
        Err(err) => {
            job.status = "failed".to_string();
            job.error = Some(err.to_string());
        }
    }
    job.finished_at = Some(now());
    job.updated_at = now();
    let _ = write_job(state, job).await;
}

fn worker_script() -> Option<PathBuf> {
    let legacy_mode = legacy_worker_mode();
    if let Ok(path) = std::env::var("VISUAL_HARDCASE_QC_WORKER_SCRIPT") {
        let path = PathBuf::from(path);
        if path.exists() && (legacy_mode || !is_legacy_worker_script(&path)) {
            return Some(path);
        }
    }
    if legacy_mode {
        if let Ok(path) = std::env::var("VISUAL_HARDCASE_QC_WATCHER_SCRIPT") {
            let path = PathBuf::from(path);
            if path.exists() {
                return Some(path);
            }
        }
    }
    let script_name = if legacy_mode {
        "watch_newcomer_sheet.py"
    } else {
        "codex_model_pre_qc.py"
    };
    let path = std::env::current_dir()
        .ok()?
        .join(".codex/skills/visual-hardcase-pre-qc/scripts")
        .join(script_name);
    path.exists().then_some(path)
}

fn legacy_worker_mode() -> bool {
    std::env::var("VISUAL_HARDCASE_QC_WORKER_MODE")
        .unwrap_or_default()
        .eq_ignore_ascii_case("legacy-rules")
}

fn is_legacy_worker_script(path: &Path) -> bool {
    path.file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name == "watch_newcomer_sheet.py")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;
    use std::fs;
    use std::sync::{Mutex, MutexGuard};
    use tempfile::TempDir;

    static ENV_LOCK: Mutex<()> = Mutex::new(());

    fn lock_env() -> MutexGuard<'static, ()> {
        ENV_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    struct EnvGuard {
        cwd: PathBuf,
        worker_script: Option<String>,
        watcher_script: Option<String>,
        worker_mode: Option<String>,
    }

    impl EnvGuard {
        fn new() -> Self {
            Self {
                cwd: env::current_dir().expect("current dir"),
                worker_script: env::var("VISUAL_HARDCASE_QC_WORKER_SCRIPT").ok(),
                watcher_script: env::var("VISUAL_HARDCASE_QC_WATCHER_SCRIPT").ok(),
                worker_mode: env::var("VISUAL_HARDCASE_QC_WORKER_MODE").ok(),
            }
        }
    }

    impl Drop for EnvGuard {
        fn drop(&mut self) {
            restore_env(
                "VISUAL_HARDCASE_QC_WORKER_SCRIPT",
                self.worker_script.as_deref(),
            );
            restore_env(
                "VISUAL_HARDCASE_QC_WATCHER_SCRIPT",
                self.watcher_script.as_deref(),
            );
            restore_env(
                "VISUAL_HARDCASE_QC_WORKER_MODE",
                self.worker_mode.as_deref(),
            );
            env::set_current_dir(&self.cwd).expect("restore cwd");
        }
    }

    fn restore_env(key: &str, value: Option<&str>) {
        if let Some(value) = value {
            env::set_var(key, value);
        } else {
            env::remove_var(key);
        }
    }

    fn make_script(root: &Path, name: &str) -> PathBuf {
        let path = root
            .join(".codex")
            .join("skills")
            .join("visual-hardcase-pre-qc")
            .join("scripts")
            .join(name);
        fs::create_dir_all(path.parent().expect("script parent")).expect("create scripts dir");
        fs::write(&path, "").expect("write script");
        path
    }

    fn assert_same_script(actual: Option<PathBuf>, expected: &Path) {
        let actual = actual
            .expect("worker script")
            .canonicalize()
            .expect("canonicalize actual script");
        let expected = expected
            .canonicalize()
            .expect("canonicalize expected script");
        assert_eq!(actual, expected);
    }

    #[test]
    fn worker_script_defaults_to_model_worker() {
        let _lock = lock_env();
        let guard = EnvGuard::new();
        let tmp = TempDir::new().expect("temp dir");
        env::remove_var("VISUAL_HARDCASE_QC_WORKER_SCRIPT");
        env::remove_var("VISUAL_HARDCASE_QC_WATCHER_SCRIPT");
        env::remove_var("VISUAL_HARDCASE_QC_WORKER_MODE");
        let model = make_script(tmp.path(), "codex_model_pre_qc.py");
        env::set_current_dir(tmp.path()).expect("set cwd");

        assert_same_script(worker_script(), &model);
        drop(guard);
    }

    #[test]
    fn worker_script_ignores_watcher_override_outside_legacy_mode() {
        let _lock = lock_env();
        let guard = EnvGuard::new();
        let tmp = TempDir::new().expect("temp dir");
        env::remove_var("VISUAL_HARDCASE_QC_WORKER_SCRIPT");
        env::remove_var("VISUAL_HARDCASE_QC_WORKER_MODE");
        let model = make_script(tmp.path(), "codex_model_pre_qc.py");
        let watcher = make_script(tmp.path(), "watch_newcomer_sheet.py");
        env::set_var("VISUAL_HARDCASE_QC_WATCHER_SCRIPT", watcher);
        env::set_current_dir(tmp.path()).expect("set cwd");

        assert_same_script(worker_script(), &model);
        drop(guard);
    }

    #[test]
    fn worker_script_allows_watcher_in_legacy_mode() {
        let _lock = lock_env();
        let guard = EnvGuard::new();
        let tmp = TempDir::new().expect("temp dir");
        env::remove_var("VISUAL_HARDCASE_QC_WORKER_SCRIPT");
        let watcher = make_script(tmp.path(), "watch_newcomer_sheet.py");
        env::set_var("VISUAL_HARDCASE_QC_WATCHER_SCRIPT", &watcher);
        env::set_var("VISUAL_HARDCASE_QC_WORKER_MODE", "legacy-rules");
        env::set_current_dir(tmp.path()).expect("set cwd");

        assert_same_script(worker_script(), &watcher);
        drop(guard);
    }

    #[test]
    fn worker_script_ignores_worker_script_watcher_without_legacy_mode() {
        let _lock = lock_env();
        let guard = EnvGuard::new();
        let tmp = TempDir::new().expect("temp dir");
        env::remove_var("VISUAL_HARDCASE_QC_WATCHER_SCRIPT");
        env::remove_var("VISUAL_HARDCASE_QC_WORKER_MODE");
        let model = make_script(tmp.path(), "codex_model_pre_qc.py");
        let watcher = make_script(tmp.path(), "watch_newcomer_sheet.py");
        env::set_var("VISUAL_HARDCASE_QC_WORKER_SCRIPT", watcher);
        env::set_current_dir(tmp.path()).expect("set cwd");

        assert_same_script(worker_script(), &model);
        drop(guard);
    }
}

#!/usr/bin/env python3
"""Small token-auth QC job API for visual-hardcase newcomer rows."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_JOB_DIR = Path.home() / "Downloads" / "visual-hardcase-qc-jobs"
DEFAULT_PATH = "/api/v1/visual-hardcase/qc-jobs"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_URL = "https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl"
DEFAULT_SHEET_ID = "eL8Rfl"
DEFAULT_EXPECTED_ROW_COUNT = 5
DEFAULT_WORKER_TIMEOUT_SECONDS = 1800
DEFAULT_MAX_IMAGE_ATTACHMENTS = 50


def load_token() -> str:
    for value in [
        os.environ.get("VISUAL_HARDCASE_QC_API_TOKEN", ""),
        os.environ.get("LLM_WIKI_API_TOKEN", ""),
    ]:
        value = value.strip()
        if value:
            return value
    for path in [
        SKILL_DIR / "config" / "llm_wiki_token.txt",
        SKILL_DIR.parents[2] / ".codex" / "hooks" / "config" / "llm_wiki_token.txt",
    ]:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
    return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve visual-hardcase QC job API.")
    parser.add_argument("--host", default=os.environ.get("VISUAL_HARDCASE_QC_API_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("VISUAL_HARDCASE_QC_API_PORT", DEFAULT_PORT)))
    parser.add_argument("--job-dir", default=os.environ.get("VISUAL_HARDCASE_QC_JOB_DIR", str(DEFAULT_JOB_DIR)))
    parser.add_argument("--path", default=os.environ.get("VISUAL_HARDCASE_QC_API_PATH", DEFAULT_PATH))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--expected-row-count",
        type=int,
        default=int(os.environ.get("VISUAL_HARDCASE_ASSIGNMENT_COUNT", DEFAULT_EXPECTED_ROW_COUNT)),
        help="Required number of rows per newcomer QC job. Use 0 to disable this check.",
    )
    return parser.parse_args()


def expand_rows(rows: str) -> list[int]:
    value = rows.strip().replace("：", ":").replace("，", ",")
    if ":" in value or "-" in value:
        sep = ":" if ":" in value else "-"
        start_text, end_text = value.split(sep, 1)
        start = int(start_text.strip())
        end = int(end_text.strip())
        if end < start:
            raise ValueError("end row is smaller than start row")
        return list(range(start, end + 1))
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def legacy_worker_mode() -> bool:
    return os.environ.get("VISUAL_HARDCASE_QC_WORKER_MODE", "").strip().lower() == "legacy-rules"


def is_legacy_worker_script(path: Path) -> bool:
    return path.name == "watch_newcomer_sheet.py"


def resolve_worker_script() -> Path | None:
    legacy_mode = legacy_worker_mode()
    worker_path = os.environ.get("VISUAL_HARDCASE_QC_WORKER_SCRIPT", "").strip()
    if worker_path:
        path = Path(worker_path).expanduser()
        if path.exists() and (legacy_mode or not is_legacy_worker_script(path)):
            return path
    if legacy_mode:
        watcher_path = os.environ.get("VISUAL_HARDCASE_QC_WATCHER_SCRIPT", "").strip()
        if watcher_path:
            path = Path(watcher_path).expanduser()
            if path.exists():
                return path
    script_name = "watch_newcomer_sheet.py" if legacy_mode else "codex_model_pre_qc.py"
    path = SCRIPT_DIR / script_name
    return path if path.exists() else None


class QcJobStore:
    def __init__(self, root: Path, python: str, expected_row_count: int):
        self.root = root
        self.python = python
        self.expected_row_count = expected_row_count
        self.root.mkdir(parents=True, exist_ok=True)

    def job_path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def write(self, job: dict[str, Any]) -> None:
        self.job_path(job["jobId"]).write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    def read(self, job_id: str) -> dict[str, Any] | None:
        path = self.job_path(job_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def enqueue(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = payload.get("rows") or ""
        if not rows and payload.get("rowNumbers"):
            rows = ",".join(str(row) for row in payload["rowNumbers"])
        row_numbers = expand_rows(str(rows))
        if not row_numbers:
            raise ValueError("rows is required")
        if self.expected_row_count > 0 and len(row_numbers) != self.expected_row_count:
            raise ValueError(f"rows must contain exactly {self.expected_row_count} row numbers")
        job_id = uuid.uuid4().hex
        job = {
            "ok": True,
            "jobId": job_id,
            "status": "queued",
            "newcomerName": payload.get("newcomerName", ""),
            "rows": rows,
            "rowNumbers": row_numbers,
            "homeworkUrl": payload.get("homeworkUrl") or DEFAULT_URL,
            "sheetId": payload.get("sheetId") or DEFAULT_SHEET_ID,
            "sessionId": payload.get("sessionId", ""),
            "createdAt": now(),
            "updatedAt": now(),
        }
        self.write(job)
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return job

    def run_job(self, job_id: str) -> None:
        job = self.read(job_id)
        if not job:
            return
        job["status"] = "running"
        job["startedAt"] = now()
        job["updatedAt"] = now()
        self.write(job)
        script = resolve_worker_script()
        if not script:
            job["status"] = "failed"
            job["error"] = "QC worker script not found; set VISUAL_HARDCASE_QC_WORKER_SCRIPT"
            job["finishedAt"] = now()
            job["updatedAt"] = now()
            self.write(job)
            return
        is_legacy = is_legacy_worker_script(script)
        cmd = [
            self.python,
            str(script),
        ]
        if is_legacy:
            cmd.append("--once")
        else:
            cmd.extend([
                "--job-id",
                str(job["jobId"]),
                "--job-dir",
                str(self.root),
                "--max-rows-per-cycle",
                str(max(1, len(job.get("rowNumbers") or []))),
                "--max-image-attachments",
                os.environ.get("VISUAL_HARDCASE_QC_MAX_IMAGE_ATTACHMENTS", str(DEFAULT_MAX_IMAGE_ATTACHMENTS)),
            ])
        cmd.extend([
            "--rows",
            str(job["rows"]),
            "--url",
            str(job["homeworkUrl"]),
            "--sheet-id",
            str(job["sheetId"]),
        ])
        proc = subprocess.run(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=int(os.environ.get("VISUAL_HARDCASE_QC_WORKER_TIMEOUT_SECONDS", DEFAULT_WORKER_TIMEOUT_SECONDS)),
        )
        job["status"] = "completed" if proc.returncode == 0 else "failed"
        job["returnCode"] = proc.returncode
        job["stdout"] = proc.stdout[-8000:]
        job["stderr"] = proc.stderr[-4000:]
        job["finishedAt"] = now()
        job["updatedAt"] = now()
        self.write(job)


class Handler(BaseHTTPRequestHandler):
    server_version = "VisualHardcaseQcApi/1.0"
    token = ""
    api_path = DEFAULT_PATH
    store: QcJobStore

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            if not self.authorized():
                self.respond(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Unauthorized"})
                return
            self.respond(HTTPStatus.OK, {"ok": True, "status": "running", "authConfigured": bool(self.token)})
            return
        prefix = self.api_path.rstrip("/") + "/"
        if parsed.path.startswith(prefix):
            if not self.authorized():
                self.respond(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Unauthorized"})
                return
            job_id = parsed.path[len(prefix):].strip("/")
            job = self.store.read(job_id)
            if not job:
                self.respond(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Job not found"})
                return
            self.respond(HTTPStatus.OK, job)
            return
        self.respond(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != self.api_path:
            self.respond(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return
        if not self.authorized():
            self.respond(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1024 * 1024:
                raise ValueError("request body too large")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            job = self.store.enqueue(payload)
        except Exception as exc:  # noqa: BLE001 - return API error payload.
            self.respond(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        self.respond(HTTPStatus.ACCEPTED, {
            "ok": True,
            "jobId": job["jobId"],
            "status": job["status"],
            "rows": job["rows"],
            "rowNumbers": job["rowNumbers"],
        })

    def authorized(self) -> bool:
        if not self.token:
            return False
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {self.token}":
            return True
        if self.headers.get("X-Visual-Hardcase-QC-Token", "") == self.token:
            return True
        return False

    def respond(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{now()}] {self.address_string()} {fmt % args}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    token = load_token()
    if not token:
        raise SystemExit("VISUAL_HARDCASE_QC_API_TOKEN or LLM_WIKI_API_TOKEN is required.")
    Handler.token = token
    Handler.api_path = args.path
    Handler.store = QcJobStore(Path(args.job_dir).expanduser(), args.python, args.expected_row_count)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"listening http://{args.host}:{args.port}{args.path}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

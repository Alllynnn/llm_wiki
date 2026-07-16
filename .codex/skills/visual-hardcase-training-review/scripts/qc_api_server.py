#!/usr/bin/env python3
"""Minimal public QC API service for visual hardcase newcomer review."""

from __future__ import annotations

import argparse
import json
import os
import queue
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DB = Path(os.environ.get("VISUAL_HARDCASE_QC_DB", Path.home() / "visual-hardcase-qc" / "jobs.sqlite"))
DEFAULT_REPORT_DIR = Path(os.environ.get("VISUAL_HARDCASE_QC_REPORT_DIR", Path.home() / "visual-hardcase-qc" / "reports"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the visual hardcase QC API service.")
    parser.add_argument("--host", default=os.environ.get("VISUAL_HARDCASE_QC_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("VISUAL_HARDCASE_QC_PORT", "8789")))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--public-base-url", default=os.environ.get("VISUAL_HARDCASE_QC_PUBLIC_BASE_URL", ""))
    parser.add_argument("--token-env", default="VISUAL_HARDCASE_QC_TOKEN")
    parser.add_argument("--allow-unauthenticated", action="store_true")
    parser.add_argument("--disable-lark-review", action="store_true")
    return parser.parse_args()


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def read_json_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              job_id TEXT PRIMARY KEY,
              idempotency_key TEXT UNIQUE,
              status TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              result_json TEXT,
              error_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        init_db(db_path)

    def create_or_get(self, payload: dict[str, Any], idempotency_key: str | None) -> tuple[dict[str, Any], bool]:
        key = idempotency_key or str(payload.get("idempotency_key") or "")
        if key:
            existing = self.get_by_idempotency_key(key)
            if existing:
                return existing, False
        job_id = f"vhq_{datetime.now().strftime('%Y%m%d')}_{secrets.token_hex(6)}"
        now = utc_now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO jobs(job_id,idempotency_key,status,payload_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?)
                """,
                (job_id, key or None, "queued", json_dumps(payload), now, now),
            )
        return self.get(job_id), True

    def get_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT job_id,status,payload_json,result_json,error_json,created_at,updated_at FROM jobs WHERE idempotency_key=?",
                (key,),
            ).fetchone()
        return self._row_to_job(row)

    def get(self, job_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT job_id,status,payload_json,result_json,error_json,created_at,updated_at FROM jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
        job = self._row_to_job(row)
        if not job:
            raise KeyError(job_id)
        return job

    def update(self, job_id: str, status: str, result: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE jobs SET status=?, result_json=?, error_json=?, updated_at=? WHERE job_id=?",
                (
                    status,
                    json_dumps(result) if result is not None else None,
                    json_dumps(error) if error is not None else None,
                    utc_now(),
                    job_id,
                ),
            )

    def _row_to_job(self, row: tuple[Any, ...] | None) -> dict[str, Any] | None:
        if not row:
            return None
        job_id, status, payload_json, result_json, error_json, created_at, updated_at = row
        result = json.loads(result_json) if result_json else None
        error = json.loads(error_json) if error_json else None
        return {
            "job_id": job_id,
            "status": status,
            "payload": json.loads(payload_json),
            "result": result,
            "error": error,
            "created_at": created_at,
            "updated_at": updated_at,
        }


def normalize_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("results", "review_results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    nested = payload.get("review")
    if isinstance(nested, dict) and isinstance(nested.get("results"), list):
        return [item for item in nested["results"] if isinstance(item, dict)]
    return []


def summarize_results(job_id: str, payload: dict[str, Any], review_data: dict[str, Any] | None = None) -> dict[str, Any]:
    results = normalize_results(review_data or payload)
    scores = [int(item["score"]) for item in results if isinstance(item.get("score"), int)]
    conclusions: dict[str, int] = {}
    for item in results:
        conclusion = str(item.get("conclusion") or "未知")
        conclusions[conclusion] = conclusions.get(conclusion, 0) + 1
    average_score = round(sum(scores) / len(scores), 1) if scores else None
    if any(key in conclusions for key in ("不合格", "无法评分")):
        conclusion = "需要人工复核或退回修改"
    elif conclusions.get("需修改"):
        conclusion = "需修改"
    elif conclusions.get("基本合格"):
        conclusion = "基本合格"
    elif conclusions.get("合格"):
        conclusion = "合格"
    else:
        conclusion = "无可汇总结果"
    return {
        "job_id": job_id,
        "status": "completed",
        "score": average_score,
        "conclusion": conclusion,
        "summary": {
            "total": len(results),
            "counts": conclusions,
        },
        "items": results,
    }


class Worker:
    def __init__(self, store: JobStore, report_dir: Path, enable_lark_review: bool) -> None:
        self.store = store
        self.report_dir = report_dir
        self.enable_lark_review = enable_lark_review
        self.jobs: queue.Queue[str] = queue.Queue()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def enqueue(self, job_id: str) -> None:
        self.jobs.put(job_id)

    def _loop(self) -> None:
        while True:
            job_id = self.jobs.get()
            try:
                self._run_job(job_id)
            finally:
                self.jobs.task_done()

    def _run_job(self, job_id: str) -> None:
        try:
            job = self.store.get(job_id)
            payload = job["payload"]
            self.store.update(job_id, "running")
            result = self._review(job_id, payload)
            self.store.update(job_id, "completed", result=result)
        except Exception as exc:
            self.store.update(job_id, "failed", error={"code": "worker_error", "message": str(exc)})

    def _review(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if normalize_results(payload):
            return summarize_results(job_id, payload)
        source = payload.get("source")
        if isinstance(source, dict) and source.get("type") == "feishu_sheet":
            if not self.enable_lark_review:
                raise RuntimeError("lark review backend is disabled")
            return self._run_lark_review(job_id, payload, source)
        raise RuntimeError("payload must include review results or source.type=feishu_sheet")

    def _run_lark_review(self, job_id: str, payload: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        url = str(source.get("url") or "")
        sheet_id = str(source.get("sheet_id") or "")
        rows = str(source.get("rows") or "")
        if not url or not sheet_id or not rows:
            raise RuntimeError("source.url, source.sheet_id, and source.rows are required")
        out_dir = self.report_dir / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "review_lark_sheet.py"),
            "--url",
            url,
            "--sheet-id",
            sheet_id,
            "--rows",
            rows,
            "--out-dir",
            str(out_dir),
        ]
        if payload.get("require_model_validation"):
            cmd.append("--require-model-validation")
        proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError((proc.stdout + proc.stderr).strip()[:2000])
        json_path = None
        report_path = None
        for line in proc.stdout.splitlines():
            if line.startswith("json:"):
                json_path = Path(line.split(":", 1)[1].strip())
            elif line.startswith("report:"):
                report_path = Path(line.split(":", 1)[1].strip())
        if json_path is None:
            raise RuntimeError(f"review_lark_sheet.py did not print a json path: {proc.stdout[:1000]}")
        review_data = read_json_file(json_path)
        result = summarize_results(job_id, payload, review_data)
        result["report_path"] = str(report_path) if report_path else None
        result["review_json_path"] = str(json_path)
        return result


class QCRequestHandler(BaseHTTPRequestHandler):
    server: "QCServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def do_GET(self) -> None:
        if not self._authorized():
            self._send_json({"error": {"code": "unauthorized", "message": "missing or invalid bearer token"}}, HTTPStatus.UNAUTHORIZED)
            return
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._send_json({"ok": True, "status": "running"})
            return
        prefix = "/v1/visual-hardcase/qc/jobs/"
        if parsed.path.startswith(prefix):
            job_id = parsed.path[len(prefix):].strip("/")
            try:
                job = self.server.store.get(job_id)
            except KeyError:
                self._send_json({"error": {"code": "not_found", "message": "job not found"}}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(self._job_response(job))
            return
        self._send_json({"error": {"code": "not_found", "message": "unknown path"}}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if not self._authorized():
            self._send_json({"error": {"code": "unauthorized", "message": "missing or invalid bearer token"}}, HTTPStatus.UNAUTHORIZED)
            return
        parsed = urlparse(self.path)
        if parsed.path != "/v1/visual-hardcase/qc/jobs":
            self._send_json({"error": {"code": "not_found", "message": "unknown path"}}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._send_json({"error": {"code": "bad_request", "message": str(exc)}}, HTTPStatus.BAD_REQUEST)
            return
        job, created = self.server.store.create_or_get(payload, self.headers.get("Idempotency-Key"))
        if created:
            self.server.worker.enqueue(job["job_id"])
        self._send_json(self._job_response(job), HTTPStatus.ACCEPTED if created else HTTPStatus.OK)

    def _authorized(self) -> bool:
        if self.server.allow_unauthenticated:
            return True
        expected = self.server.token
        if not expected:
            return False
        value = self.headers.get("Authorization", "")
        return value == f"Bearer {expected}"

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            raise ValueError("empty request body")
        if length > 2_000_000:
            raise ValueError("request body exceeds 2MB")
        raw = self.rfile.read(length).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def _job_response(self, job: dict[str, Any]) -> dict[str, Any]:
        response: dict[str, Any] = {
            "job_id": job["job_id"],
            "status": job["status"],
            "status_url": f"{self.server.public_base_url.rstrip('/')}/v1/visual-hardcase/qc/jobs/{job['job_id']}",
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        }
        if job.get("result"):
            response.update(job["result"])
            response["status_url"] = f"{self.server.public_base_url.rstrip('/')}/v1/visual-hardcase/qc/jobs/{job['job_id']}"
        if job.get("error"):
            response["error"] = job["error"]
        return response

    def _send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class QCServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        store: JobStore,
        worker: Worker,
        public_base_url: str,
        token: str,
        allow_unauthenticated: bool,
    ) -> None:
        super().__init__(server_address, QCRequestHandler)
        self.store = store
        self.worker = worker
        self.public_base_url = public_base_url or f"http://{server_address[0]}:{server_address[1]}"
        self.token = token
        self.allow_unauthenticated = allow_unauthenticated


def main() -> int:
    args = parse_args()
    token = os.environ.get(args.token_env, "").strip()
    if not args.allow_unauthenticated and not token:
        raise SystemExit(f"Missing {args.token_env}. Set it or use --allow-unauthenticated for local tests.")
    db_path = Path(args.db).expanduser().resolve()
    report_dir = Path(args.report_dir).expanduser().resolve()
    store = JobStore(db_path)
    worker = Worker(store, report_dir, not args.disable_lark_review)
    server = QCServer(
        (args.host, args.port),
        store,
        worker,
        args.public_base_url,
        token,
        args.allow_unauthenticated,
    )
    print(f"visual-hardcase-qc-api listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

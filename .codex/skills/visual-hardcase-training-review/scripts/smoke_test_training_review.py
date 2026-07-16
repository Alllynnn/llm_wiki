#!/usr/bin/env python3
"""Smoke test for the visual hardcase newcomer onboarding skill."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_URL = "https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl"
DEFAULT_SHEET_ID = "eL8Rfl"
DEFAULT_ROWS = "2:6"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run black-box smoke tests for this skill.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument("--rows", default=DEFAULT_ROWS)
    parser.add_argument("--name", default="黑盒测试新人")
    parser.add_argument("--keep-temp", action="store_true")
    return parser.parse_args()


def run(cmd: list[str], env: dict[str, str] | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    final_env = os.environ.copy()
    final_env["PYTHONUTF8"] = "1"
    final_env["PYTHONIOENCODING"] = "utf-8"
    if env:
        final_env.update(env)
    proc = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=final_env,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
    return proc


def load_module(name: str, path: Path) -> Any:
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_http_error(url: str, code: int) -> None:
    try:
        urllib.request.urlopen(url, timeout=5)
    except urllib.error.HTTPError as exc:
        if exc.code == code:
            return
        raise RuntimeError(f"Expected HTTP {code} for {url}, got {exc.code}") from exc
    raise RuntimeError(f"Expected HTTP {code} for {url}, got success")


def parse_session_path(stdout: str) -> Path:
    for line in stdout.splitlines():
        if line.startswith("session_json:"):
            return Path(line.split(":", 1)[1].strip())
    raise RuntimeError("newcomer_session.py did not print session_json")


def smoke_newcomer_flow(tmp: Path, args: argparse.Namespace) -> dict[str, Any]:
    session_dir = tmp / "sessions"
    start = run([
        sys.executable,
        str(SCRIPT_DIR / "newcomer_session.py"),
        "start",
        "--name",
        args.name,
        "--session-dir",
        str(session_dir),
        "--homework-url",
        args.url,
        "--sheet-id",
        args.sheet_id,
        "--now",
        "13:30",
    ])
    if "入项前第一天培训表" not in start.stdout:
        raise RuntimeError("start output did not include day-one training schedule")
    schedule_section = start.stdout.split("13:00-15:00 测试题注意事项：", 1)[0]
    for url in [
        "https://shujufuwubu.feishu.cn/wiki/UW89wjZW0iWdkskxLsWcLTPEnJg",
        "https://shujufuwubu.feishu.cn/wiki/Qx1nw19a2iHc8qkunCqcXDAdnhf",
        "https://shujufuwubu.feishu.cn/wiki/TL0AwaFzaiUByrkGF2IcUwDIn4e",
    ]:
        if url not in schedule_section:
            raise RuntimeError(f"day-one schedule did not include rule document URL: {url}")
    if "https://dcnkm9z3sogt.feishu.cn/minutes/obcnn7x2bffm45zu8co7pr9s" not in start.stdout:
        raise RuntimeError("start output did not include training video URL")
    if "当前阶段：完成5道试标题" not in start.stdout:
        raise RuntimeError("start output did not include the 13:00-15:00 active step")
    if "完成当前阶段后，下一环节为" not in start.stdout:
        raise RuntimeError("start output did not include per-stage next arrangement text")
    if "完成当前阶段后，下一环节为：15:00-15:30 第一轮试标复盘会" not in start.stdout:
        raise RuntimeError("start output did not include the test-title next arrangement")
    if "做题前小提醒" not in start.stdout:
        raise RuntimeError("start output did not include the pre-task reminder")
    for forbidden in ["分配给你的行号", "如果还没有行号", "负责人分配"]:
        if forbidden in start.stdout:
            raise RuntimeError(f"start output included deprecated assignment wording: {forbidden}")
    learning_status = run([
        sys.executable,
        str(SCRIPT_DIR / "newcomer_session.py"),
        "status",
        "--now",
        "10:30",
    ])
    if "规则文档：" not in learning_status.stdout:
        raise RuntimeError("status output did not include rule document links for the learning stage")
    if "完成当前阶段后，下一环节为：11:00-12:00 会议培训" not in learning_status.stdout:
        raise RuntimeError("status output did not include next arrangement text for the learning stage")
    status = run([
        sys.executable,
        str(SCRIPT_DIR / "newcomer_session.py"),
        "status",
        "--now",
        "11:30",
    ])
    if "当前阶段：会议培训" not in status.stdout:
        raise RuntimeError("status output did not include the 11:00-12:00 active step")
    if "飞书妙记" not in status.stdout:
        raise RuntimeError("status output did not include the training video reminder")
    session_path = parse_session_path(start.stdout)
    complete = run([
        sys.executable,
        str(SCRIPT_DIR / "newcomer_session.py"),
        "complete",
        "--session",
        str(session_path),
        "--rows",
        args.rows,
        "--no-submit-qc",
    ])
    data = json.loads(session_path.read_text(encoding="utf-8"))
    if data.get("status") != "completed_without_qc_submit":
        raise RuntimeError(f"completion did not update session status: {data}")
    if "跳过后台 QC 提交" not in complete.stdout:
        raise RuntimeError("completion output did not state the no-submit-qc policy")
    return {
        "session_path": str(session_path),
        "status": data.get("status"),
        "completed_rows": data.get("completed_rows"),
        "schedule_status_checked": True,
        "did_not_read_sheet": True,
        "stdout_tail": complete.stdout.splitlines()[-4:],
    }


def smoke_image_list_mapping() -> dict[str, Any]:
    module = load_module("review_lark_sheet", SCRIPT_DIR / "review_lark_sheet.py")
    row = {
        "_row_number": "9",
        "姓名": "测试新人",
        "日期": "2026/7/6",
        "分类": "ocr-票据",
        "图片列表（URL，一行一张）": "https://example.com/a.png\nhttps://example.com/b.png",
        "prompt": "请只输出金额数字",
        "answer": "123",
        "答案是否唯一": "是",
    }
    mapped = module.map_cloud_row(row)
    if mapped["图片数量"] != "2":
        raise RuntimeError(f"Expected 图片数量=2, got {mapped['图片数量']}")
    return {
        "image_count": mapped["图片数量"],
        "image_links": mapped["图片文件夹或图片链接"].splitlines(),
    }


def smoke_api_auth_and_poll(tmp: Path, args: argparse.Namespace) -> dict[str, Any]:
    module = load_module("qc_api_server", SCRIPT_DIR / "qc_api_server.py")
    token = "test-token-123"
    store = module.JobStore(tmp / "api" / "jobs.sqlite")
    worker = module.Worker(store, tmp / "api" / "reports", enable_lark_review=True)
    server = module.QCServer(("127.0.0.1", 0), store, worker, "http://127.0.0.1:0", token, False)
    port = server.server_address[1]
    server.public_base_url = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    old_token = os.environ.get("VISUAL_HARDCASE_QC_TOKEN")
    os.environ["VISUAL_HARDCASE_QC_TOKEN"] = token
    try:
        expect_http_error(f"http://127.0.0.1:{port}/healthz", 401)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/healthz",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read().decode("utf-8"))
        if not health.get("ok"):
            raise RuntimeError(f"Unexpected health response: {health}")

        payload_path = tmp / "payload.json"
        submit_path = tmp / "submit.json"
        result_path = tmp / "result.json"
        payload_path.write_text(json.dumps({
            "mode": "training_pre_qc",
            "source": {
                "type": "feishu_sheet",
                "url": args.url,
                "sheet_id": args.sheet_id,
                "rows": args.rows,
            },
            "knowledge_base": "visual-understanding-hardcase",
            "idempotency_key": f"smoke:{args.sheet_id}:{args.rows}",
        }, ensure_ascii=False), encoding="utf-8")
        submit = run([
            sys.executable,
            str(SCRIPT_DIR / "submit_qc_job.py"),
            "--submit-url",
            f"http://127.0.0.1:{port}/v1/visual-hardcase/qc/jobs",
            "--payload",
            str(payload_path),
            "--output",
            str(submit_path),
            "--request-timeout",
            "10",
        ])
        status_url = json.loads(submit_path.read_text(encoding="utf-8"))["response"]["status_url"]
        expect_http_error(status_url, 401)
        poll = run([
            sys.executable,
            str(SCRIPT_DIR / "poll_qc_result.py"),
            "--status-url",
            status_url,
            "--interval-seconds",
            "1",
            "--timeout-seconds",
            "30",
            "--output",
            str(result_path),
        ], env={**os.environ, "VISUAL_HARDCASE_QC_TOKEN": token})
        final = json.loads(result_path.read_text(encoding="utf-8"))
        if final.get("status") != "completed":
            raise RuntimeError(f"Expected completed result, got {final}")
        return {
            "health_requires_token": True,
            "status_requires_token": True,
            "submit_stdout": submit.stdout.splitlines(),
            "poll_stdout_tail": poll.stdout.splitlines()[-6:],
            "final_status": final.get("status"),
            "total": final.get("summary", {}).get("total"),
        }
    finally:
        if old_token is None:
            os.environ.pop("VISUAL_HARDCASE_QC_TOKEN", None)
        else:
            os.environ["VISUAL_HARDCASE_QC_TOKEN"] = old_token
        server.shutdown()
        server.server_close()
        time.sleep(0.2)


def smoke_compile() -> dict[str, Any]:
    files = sorted(SKILL_DIR.rglob("scripts/*.py"))
    for path in files:
        py_compile.compile(str(path), doraise=True)
    for cache_dir in SKILL_DIR.rglob("__pycache__"):
        for child in cache_dir.iterdir():
            child.unlink()
        cache_dir.rmdir()
    return {"compiled_files": len(files)}


def main() -> int:
    args = parse_args()
    tmp_context = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    tmp = Path(tmp_context.name)
    try:
        results = {
            "newcomer_flow": smoke_newcomer_flow(tmp, args),
            "image_list_mapping": smoke_image_list_mapping(),
            "api_auth_and_poll": smoke_api_auth_and_poll(tmp, args),
            "compile": smoke_compile(),
        }
        print(json.dumps({"ok": True, "tmp": str(tmp), "results": results}, ensure_ascii=False, indent=2))
        return 0
    finally:
        if args.keep_temp:
            print(f"kept_temp: {tmp}")
        else:
            tmp_context.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

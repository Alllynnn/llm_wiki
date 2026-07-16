#!/usr/bin/env python3
"""Smoke test for the visual hardcase newcomer onboarding skill."""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_URL = "https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl"
DEFAULT_SHEET_ID = "eL8Rfl"
DEFAULT_ROWS = "2:6"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run newcomer onboarding smoke tests.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument("--rows", default=DEFAULT_ROWS)
    parser.add_argument("--name", default="黑盒测试新人")
    return parser.parse_args()


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=env,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
    return proc


def parse_session_path(stdout: str) -> Path:
    for line in stdout.splitlines():
        if line.startswith("session_json:"):
            return Path(line.split(":", 1)[1].strip())
    raise RuntimeError("newcomer_session.py did not print session_json")


def smoke_newcomer_flow(tmp: Path, args: argparse.Namespace) -> dict[str, str | bool]:
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
    if "主动提醒" not in start.stdout:
        raise RuntimeError("start output did not include active reminder section")
    for forbidden in ["分配给你的行号", "如果还没有行号", "负责人分配"]:
        if forbidden in start.stdout:
            raise RuntimeError(f"start output included deprecated assignment wording: {forbidden}")
    reminders = run([
        sys.executable,
        str(SCRIPT_DIR / "newcomer_session.py"),
        "reminders",
        "--name",
        args.name,
        "--date",
        "2026-07-09",
        "--now",
        "13:30",
        "--homework-url",
        args.url,
        "--sheet-id",
        args.sheet_id,
    ])
    reminder_data = json.loads(reminders.stdout)
    reminder_times = [item["time"] for item in reminder_data.get("reminders", [])]
    for expected_time in ["2026-07-09 15:00", "2026-07-09 15:30", "2026-07-09 16:10", "2026-07-09 16:40", "2026-07-09 19:00"]:
        if expected_time not in reminder_times:
            raise RuntimeError(f"reminder plan missed checkpoint: {expected_time}")
    if any("2026-07-09 13:00" == value for value in reminder_times):
        raise RuntimeError("reminder plan should not include past/current checkpoint")
    if not all(item.get("rrule") and item.get("prompt") for item in reminder_data.get("reminders", [])):
        raise RuntimeError("reminder plan did not include rrule and prompt for every reminder")
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
        "status": data.get("status", ""),
        "completed_rows": data.get("completed_rows", ""),
        "schedule_status_checked": True,
        "active_reminders_checked": True,
        "did_not_read_sheet": True,
    }


def smoke_compile() -> dict[str, int]:
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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp = Path(tmp_dir)
        results = {
            "newcomer_flow": smoke_newcomer_flow(tmp, args),
            "compile": smoke_compile(),
        }
        print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Poll a public QC status API until a job is complete."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll QC result API.")
    parser.add_argument("--status-url", required=True, help="Full QC status API URL.")
    parser.add_argument("--method", choices=["GET", "POST"], default="GET")
    parser.add_argument("--body-json", help="JSON body for POST polling.")
    parser.add_argument("--header", action="append", default=[], help="HTTP header as 'Name: value'. Repeatable.")
    parser.add_argument("--token-env", default="VISUAL_HARDCASE_QC_TOKEN")
    parser.add_argument("--auth-header", default="Authorization")
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--request-timeout", type=float, default=20.0)
    parser.add_argument("--status-field", default="status", help="Dot path for status field.")
    parser.add_argument("--score-field", default="score", help="Dot path for score field.")
    parser.add_argument("--done-values", default="done,completed,success,succeeded,finished,passed")
    parser.add_argument("--failed-values", default="failed,error,rejected,canceled,cancelled")
    parser.add_argument("--output", help="Write final JSON response to this path.")
    parser.add_argument("--once", action="store_true", help="Poll once and exit.")
    return parser.parse_args()


def parse_headers(values: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values:
        if ":" not in value:
            raise SystemExit(f"Invalid --header value, expected 'Name: value': {value}")
        name, content = value.split(":", 1)
        headers[name.strip()] = content.strip()
    return headers


def json_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def request_json(args: argparse.Namespace) -> dict[str, Any]:
    headers = parse_headers(args.header)
    token = os.environ.get(args.token_env, "").strip()
    if token and args.auth_header not in headers:
        headers[args.auth_header] = f"Bearer {token}"
    body = None
    if args.method == "POST":
        headers.setdefault("Content-Type", "application/json")
        body = (args.body_json or "{}").encode("utf-8")
    req = urllib.request.Request(args.status_url, data=body, headers=headers, method=args.method)
    try:
        with urllib.request.urlopen(req, timeout=args.request_timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed: {exc.reason}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"API returned non-JSON response: {raw[:1000]}") from exc


def normalize_set(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def main() -> int:
    args = parse_args()
    done_values = normalize_set(args.done_values)
    failed_values = normalize_set(args.failed_values)
    deadline = time.monotonic() + args.timeout_seconds
    last_data: dict[str, Any] | None = None

    while True:
        try:
            data = request_json(args)
        except RuntimeError as exc:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now}] request_error={exc}")
            if args.once:
                return 2
            if time.monotonic() >= deadline:
                raise SystemExit(f"Timed out after {args.timeout_seconds} seconds waiting for QC API. Last error: {exc}")
            time.sleep(args.interval_seconds)
            continue
        last_data = data
        status_value = json_path(data, args.status_field)
        status = "" if status_value is None else str(status_value).lower()
        score = json_path(data, args.score_field)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] status={status_value} score={score}")

        if status in done_values:
            if args.output:
                Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print("# QC Result")
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if status in failed_values:
            if args.output:
                Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print("# QC Failed")
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 2
        if args.once:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if time.monotonic() >= deadline:
            if args.output and last_data is not None:
                Path(args.output).write_text(json.dumps(last_data, ensure_ascii=False, indent=2), encoding="utf-8")
            raise SystemExit(f"Timed out after {args.timeout_seconds} seconds waiting for QC result.")
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Submit a visual hardcase QC job to a configured public API."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit a QC job and save the API response.")
    parser.add_argument("--submit-url", default=os.environ.get("VISUAL_HARDCASE_QC_SUBMIT_URL"))
    parser.add_argument("--payload", required=True, help="JSON payload path.")
    parser.add_argument("--output", help="Output JSON path. Defaults to <payload>-submit-response.json.")
    parser.add_argument("--header", action="append", default=[], help="HTTP header as 'Name: value'. Repeatable.")
    parser.add_argument("--token-env", default="VISUAL_HARDCASE_QC_TOKEN")
    parser.add_argument("--auth-header", default="Authorization")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true", help="Write request preview without sending HTTP.")
    parser.add_argument(
        "--allow-unauthenticated",
        action="store_true",
        help="Allow a real request without auth. Use only for local loopback tests.",
    )
    return parser.parse_args()


def parse_headers(values: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values:
        if ":" not in value:
            raise SystemExit(f"Invalid --header value, expected 'Name: value': {value}")
        name, content = value.split(":", 1)
        headers[name.strip()] = content.strip()
    return headers


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Payload file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Payload file is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Payload root must be a JSON object.")
    return data


def default_output_path(payload_path: Path) -> Path:
    return payload_path.with_name(f"{payload_path.stem}-submit-response.json")


def add_auth_headers(headers: dict[str, str], token_env: str, auth_header: str) -> None:
    token = os.environ.get(token_env, "").strip()
    if token and auth_header not in headers:
        headers[auth_header] = f"Bearer {token}"


def request_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    final_headers = {"Content-Type": "application/json", **headers}
    req = urllib.request.Request(url, data=body, headers=final_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status_code = resp.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed: {exc.reason}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"API returned non-JSON response: {raw[:1000]}") from exc
    if isinstance(data, dict):
        data.setdefault("http_status", status_code)
        return data
    return {"http_status": status_code, "raw": data}


def build_record(
    submit_url: str | None,
    payload_path: Path,
    payload: dict[str, Any],
    headers: dict[str, str],
    response: dict[str, Any] | None,
    dry_run: bool,
) -> dict[str, Any]:
    redacted_headers = {
        key: ("<redacted>" if key.lower() in {"authorization", "x-api-key"} else value)
        for key, value in headers.items()
    }
    return {
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "submit_url": submit_url,
        "payload_path": str(payload_path),
        "request_headers": redacted_headers,
        "payload": payload if dry_run else {"omitted": "payload not duplicated after real submit"},
        "response": response,
    }


def main() -> int:
    args = parse_args()
    payload_path = Path(args.payload).expanduser().resolve()
    payload = load_json(payload_path)
    output_path = Path(args.output).expanduser().resolve() if args.output else default_output_path(payload_path)

    headers = parse_headers(args.header)
    headers.setdefault("Idempotency-Key", args.idempotency_key or payload.get("idempotency_key") or payload_path.stem)
    add_auth_headers(headers, args.token_env, args.auth_header)

    if args.dry_run:
        record = build_record(args.submit_url, payload_path, payload, headers, None, True)
        output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"dry_run_request: {output_path}")
        return 0

    if not args.submit_url:
        raise SystemExit("Missing --submit-url or VISUAL_HARDCASE_QC_SUBMIT_URL.")
    if args.auth_header not in headers and not args.allow_unauthenticated:
        raise SystemExit(
            f"Missing {args.auth_header}. Set {args.token_env}, pass --header "
            f"'{args.auth_header}: Bearer <token>', or use --dry-run."
        )

    try:
        response = request_json(args.submit_url, payload, headers, args.request_timeout)
    except RuntimeError as exc:
        raise SystemExit(f"submit_failed: {exc}") from exc

    record = build_record(args.submit_url, payload_path, payload, headers, response, False)
    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"submit_response: {output_path}")
    for key in ("job_id", "status_url"):
        value = response.get(key)
        if value:
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

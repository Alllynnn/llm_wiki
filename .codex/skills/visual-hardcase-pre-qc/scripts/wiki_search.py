#!/usr/bin/env python3
"""Search the LLM Wiki project API and print compact Markdown evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import quote


DEFAULT_PUBLIC_WIKI_URL = "https://wiki.muchenai.com"
DEFAULT_BASE_URL = os.environ.get("LLM_WIKI_API_BASE_URL", DEFAULT_PUBLIC_WIKI_URL).rstrip("/")
DEFAULT_PROJECT_ID = os.environ.get(
    "LLM_WIKI_PROJECT_ID",
    os.environ.get("LLM_WIKI_PROJECT_PATH", "7ad8995a9c34304f"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search LLM Wiki project evidence.")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--top-k", type=int, default=8, help="Number of results, 1-50")
    parser.add_argument("--include-content", action="store_true", help="Include page content")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LLM Wiki API base URL")
    parser.add_argument(
        "--project-id",
        "--project-path",
        dest="project_id",
        default=DEFAULT_PROJECT_ID,
        help="LLM Wiki project id. --project-path is kept as a compatibility alias.",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout seconds")
    parser.add_argument("--max-content-chars", type=int, default=6000, help="Per-result content limit")
    parser.add_argument("--json", action="store_true", help="Print raw JSON response")
    return parser.parse_args()


def build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("LLM_WIKI_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def public_access_hint() -> str:
    return (
        "LLM Wiki knowledge search is not available. For public access, open "
        f"{DEFAULT_PUBLIC_WIKI_URL}; for API search, configure "
        "LLM_WIKI_API_BASE_URL and LLM_WIKI_API_TOKEN."
    )


def post_json(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers=build_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 401:
            raise SystemExit(
                f"LLM Wiki API returned HTTP 401 for the configured API endpoint.\n"
                f"{public_access_hint()}"
            ) from exc
        raise SystemExit(
            f"LLM Wiki API returned HTTP {exc.code} for {url}\n"
            f"{detail[:1200]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"{public_access_hint()} Details: {exc.reason}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"LLM Wiki API returned invalid JSON from {url}: {exc}") from exc


def shorten(text: object, limit: int) -> str:
    value = "" if text is None else str(text)
    value = value.replace("\r\n", "\n").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n...[truncated]"


def print_markdown(data: dict, query: str, project_id: str, max_content_chars: int) -> None:
    results = data.get("results") or []
    print("# LLM Wiki Search Results")
    print()
    print(f"- Query: `{query}`")
    print(f"- Project: `{project_id}`")
    print(f"- Mode: `{data.get('mode', 'unknown')}`")
    print(f"- Results: {len(results)}")
    print()

    if not results:
        print("No matching wiki pages were returned.")
        return

    for index, item in enumerate(results, start=1):
        title = item.get("title") or item.get("path") or f"Result {index}"
        path = item.get("path") or ""
        score = item.get("score")
        score_text = f"{score:.2f}" if isinstance(score, (int, float)) else str(score or "")
        print(f"## {index}. {title}")
        print()
        print(f"- Path: `{path}`")
        if score_text:
            print(f"- Score: `{score_text}`")
        snippet = shorten(item.get("snippet"), 900)
        if snippet:
            print()
            print("Snippet:")
            print()
            print(snippet)
        content = item.get("content")
        if content:
            print()
            print("Content:")
            print()
            print(shorten(content, max_content_chars))
        print()


def main() -> int:
    args = parse_args()
    top_k = max(1, min(args.top_k, 50))
    project_id = quote(args.project_id.strip(), safe="")
    url = f"{args.base_url.rstrip('/')}/api/v1/projects/{project_id}/search"
    payload = {
        "query": args.query,
        "topK": top_k,
        "includeContent": bool(args.include_content),
    }
    data = post_json(url, payload, args.timeout)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_markdown(data, args.query, args.project_id, args.max_content_chars)
    return 0


if __name__ == "__main__":
    sys.exit(main())

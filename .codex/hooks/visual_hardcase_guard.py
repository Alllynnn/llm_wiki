#!/usr/bin/env python3
"""Project-level guard for visual hardcase skill retrieval."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote


DEFAULT_PUBLIC_WIKI_URL = "https://wiki.muchenai.com"
TOKEN_FILE = Path(__file__).resolve().parent / "config" / "llm_wiki_token.txt"
DEFAULT_BASE_URL = os.environ.get("LLM_WIKI_API_BASE_URL", DEFAULT_PUBLIC_WIKI_URL).rstrip("/")
DEFAULT_PROJECT_ID = os.environ.get(
    "LLM_WIKI_PROJECT_ID",
    os.environ.get("LLM_WIKI_PROJECT_PATH", "7ad8995a9c34304f"),
)

DOMAIN_PATTERNS = [
    r"visual[-_\s]?hardcase",
    r"visual[-_\s]?understanding[-_\s]?hardcase",
    r"视觉理解",
    r"难题构造",
    r"新人培训",
    r"新人总包",
    r"新人流程",
    r"入项",
    r"训练作业",
    r"云表作业",
    r"预质检",
    r"质检",
    r"bad\s*case",
    r"题型",
    r"v3\s*题型",
    r"prompt",
    r"answer",
    r"答案格式",
    r"图片列表",
    r"模板生成",
]

RETRIEVAL_PATTERNS = [
    r"FAQ",
    r"规则",
    r"怎么",
    r"如何",
    r"为什么",
    r"是否",
    r"能不能",
    r"可不可以",
    r"题型",
    r"bad\s*case",
    r"prompt",
    r"answer",
    r"答案",
    r"质检",
    r"评分",
    r"模板",
    r"构造",
    r"审核",
    r"复盘",
]


@dataclass
class GuardDecision:
    matched: bool
    requires_retrieval: bool
    recommended_skill: str
    query: str
    reminder: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect and enforce visual hardcase LLM Wiki retrieval.")
    parser.add_argument("text", nargs="*", help="User request text to inspect")
    parser.add_argument("--text-file", help="Read request text from a UTF-8 file")
    parser.add_argument("--mode", choices=["json", "reminder", "search"], default="json")
    parser.add_argument("--top-k", type=int, default=5, help="Search result count, 1-50")
    parser.add_argument("--include-content", action="store_true", help="Include full result content in search mode")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LLM Wiki API base URL")
    parser.add_argument(
        "--project-id",
        "--project-path",
        dest="project_id",
        default=DEFAULT_PROJECT_ID,
        help="LLM Wiki project id. --project-path is kept as a compatibility alias.",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout seconds")
    return parser.parse_args()


def read_text(args: argparse.Namespace) -> str:
    parts: list[str] = []
    if args.text_file:
        parts.append(Path(args.text_file).read_text(encoding="utf-8"))
    if args.text:
        parts.append(" ".join(args.text))
    return "\n".join(part.strip() for part in parts if part.strip()).strip()


def any_pattern(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def choose_skill(text: str) -> str:
    if re.search(r"新人|培训|训练作业|云表作业|guided|onboarding", text, re.IGNORECASE):
        return "visual-hardcase-newcomer-suite"
    if re.search(r"质检|评分|审核|review|QC", text, re.IGNORECASE):
        return "visual-hardcase-pre-qc"
    if re.search(r"模板|template|Hermes", text, re.IGNORECASE):
        return "visual-hardcase-template-generator"
    return "visual-hardcase-faq"


def make_decision(text: str) -> GuardDecision:
    matched = any_pattern(DOMAIN_PATTERNS, text)
    requires_retrieval = matched and any_pattern(RETRIEVAL_PATTERNS, text)
    skill = choose_skill(text) if matched else ""
    query = text.strip()

    if not matched:
        reminder = "No visual-hardcase trigger detected."
    elif requires_retrieval:
        reminder = (
            "Visual-hardcase request detected. Retrieve LLM Wiki evidence before answering; "
            f"route through {skill}."
        )
    else:
        reminder = (
            "Visual-hardcase context detected. If the user is loading/opening the training skill, "
            "start visual-hardcase-newcomer-suite guided-start instead of summarizing the skill."
        )

    return GuardDecision(
        matched=matched,
        requires_retrieval=requires_retrieval,
        recommended_skill=skill,
        query=query,
        reminder=reminder,
    )


def auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = configured_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def configured_token() -> str:
    token = os.environ.get("LLM_WIKI_API_TOKEN", "").strip()
    if token:
        return token
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def fallback_message() -> str:
    return (
        "知识库检索暂时不可用；你可以先打开 https://wiki.muchenai.com 查看资料。"
        "管理员配置 LLM_WIKI_API_BASE_URL 和 LLM_WIKI_API_TOKEN 后，我会自动从知识库取证。"
    )


def compact_search_data(data: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        results.append(
            {
                "title": item.get("title"),
                "path": item.get("path"),
                "score": item.get("score"),
                "snippet": item.get("snippet"),
            }
        )

    return {
        "mode": data.get("mode"),
        "tokenHits": data.get("tokenHits"),
        "vectorHits": data.get("vectorHits"),
        "results": results,
    }


def post_search(args: argparse.Namespace, query: str) -> dict[str, Any]:
    project_id = quote(args.project_id.strip(), safe="")
    url = f"{args.base_url.rstrip('/')}/api/v1/projects/{project_id}/search"
    payload = {
        "query": query,
        "topK": max(1, min(args.top_k, 50)),
        "includeContent": bool(args.include_content),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=auth_headers(), method="POST")

    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "unavailable",
            "http_status": exc.code,
            "error": detail[:1200],
            "fallback": fallback_message(),
        }
    except (urllib.error.URLError, TimeoutError) as exc:
        return {
            "status": "unavailable",
            "error": str(getattr(exc, "reason", exc)),
            "fallback": fallback_message(),
        }
    except json.JSONDecodeError as exc:
        return {
            "status": "unavailable",
            "error": f"invalid JSON: {exc}",
            "fallback": fallback_message(),
        }

    return {
        "status": "ok",
        "endpoint": url,
        "project_id": args.project_id,
        "result_count": len(data.get("results") or []),
        "data": compact_search_data(data),
    }


def decision_to_dict(decision: GuardDecision) -> dict[str, Any]:
    return {
        "matched": decision.matched,
        "requires_retrieval": decision.requires_retrieval,
        "recommended_skill": decision.recommended_skill,
        "query": decision.query,
        "reminder": decision.reminder,
    }


def main() -> int:
    args = parse_args()
    text = read_text(args)
    decision = make_decision(text)
    output = decision_to_dict(decision)

    if args.mode == "reminder":
        print(decision.reminder)
        return 0

    if args.mode == "search" and decision.requires_retrieval:
        output["search"] = post_search(args, decision.query)
    elif args.mode == "search":
        output["search"] = {"status": "skipped", "reason": "retrieval not required"}

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

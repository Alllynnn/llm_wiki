#!/usr/bin/env python3
"""Run model-backed visual-hardcase pre-QC in a dedicated Codex exec session."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parents[2]
TRAINING_SCRIPTS_DIR = REPO_ROOT / ".codex" / "skills" / "visual-hardcase-training-review" / "scripts"
DEFAULT_SCHEMA_PATH = SKILL_DIR / "references" / "codex-pre-qc-output.schema.json"
DEFAULT_MODEL = os.environ.get("VISUAL_HARDCASE_QC_CODEX_MODEL", "gpt-5.5")
DEFAULT_CODEX_BIN = os.environ.get("VISUAL_HARDCASE_QC_CODEX_BIN", "codex")
DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("VISUAL_HARDCASE_QC_CODEX_TIMEOUT_SECONDS", "900"))
DEFAULT_SESSION_ID_FILE = SKILL_DIR / "config" / "codex_qc_worker_session_id.txt"
DEFAULT_QUEUE_LOCK_FILE = SKILL_DIR / "config" / "codex_qc_worker.lock"
DEFAULT_MAX_IMAGE_ATTACHMENTS = int(os.environ.get("VISUAL_HARDCASE_QC_MAX_IMAGE_ATTACHMENTS", "30"))
SOURCE_REQUIREMENT_CSV = (
    REPO_ROOT
    / "projects"
    / "visual-understanding-hardcase"
    / "raw"
    / "sources"
    / "lark"
    / "题型分类信源表-v3题型.csv"
)
SOURCE_REQUIREMENT_URL = "https://jcnsrten12zb.feishu.cn/wiki/NF2HwptL8i798RkGxtocq47Snfh"
IMAGE_TOKEN_RE = re.compile(r"飞书单元格图片 token:([^\\\s()\"']+)")
DISPLAY_FIELD_LABELS = {
    "答案是否唯一": "S列【答案是否唯一】",
    "prompt": "【prompt】",
    "answer": "【answer】",
    "题型分类": "【分类/题型分类】",
    "图片文件夹或图片链接": "【图片】字段",
    "推理过程": "【推理过程】字段",
    "信源链接或标注图路径": "【信源】字段",
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(TRAINING_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TRAINING_SCRIPTS_DIR))

from review_lark_sheet import attach_float_images, map_cloud_row, read_float_images  # noqa: E402
from review_training_workbook import DEFAULT_BASE_URL, DEFAULT_PROJECT_PATH, search_wiki  # noqa: E402
from watch_newcomer_sheet import (  # noqa: E402
    DEFAULT_RANGE_COLUMNS,
    DEFAULT_RESULT_FIELD,
    DEFAULT_SHEET_ID,
    DEFAULT_TRIGGER_FIELD,
    DEFAULT_TRIGGER_VALUE,
    DEFAULT_URL,
    attach_cell_images,
    count_cell_images,
    expand_rows,
    has_answer_image,
    is_repair_done,
    normalize,
    read_existing_result,
    read_sheet_rows,
    row_allows_result_overwrite,
    row_needs_pre_qc,
    select_candidates,
    write_pre_qc_result,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Codex model pre-QC for newcomer sheet rows.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Feishu sheet/wiki URL.")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID, help="Target sheet id.")
    parser.add_argument("--range-columns", default=DEFAULT_RANGE_COLUMNS, help="Columns to read, e.g. A:AD.")
    parser.add_argument("--trigger-field", default=DEFAULT_TRIGGER_FIELD, help="Header field used to trigger pre-QC.")
    parser.add_argument("--trigger-value", default=DEFAULT_TRIGGER_VALUE, help="Trigger value.")
    parser.add_argument("--result-field", default=DEFAULT_RESULT_FIELD, help="Header field to write pre-QC result.")
    parser.add_argument("--repair-done-field", default="是否返修完成", help="Header field that marks a repaired submission.")
    parser.add_argument("--repair-done-value", default="是", help="Value that marks a repaired submission.")
    parser.add_argument("--no-repair-recheck", action="store_true", help="Do not re-run rows whose repair-done field is marked done.")
    parser.add_argument("--rows", required=True, help="Specific sheet rows to review, e.g. 946:950.")
    parser.add_argument("--job-id", default="", help="Backend QC job id.")
    parser.add_argument("--job-dir", help="Directory for prompt/output/event artifacts.")
    parser.add_argument("--max-rows-per-cycle", type=int, default=10, help="Max rows to review.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing result-field values.")
    parser.add_argument("--dry-run", action="store_true", help="Prepare payload and run model, but do not write.")
    parser.add_argument("--no-write", action="store_true", help="Do not write pre-QC cells.")
    parser.add_argument("--no-float-images", action="store_true", help="Do not attach floating images from the sheet.")
    parser.add_argument("--no-cell-images", action="store_true", help="Do not attach embedded cell images from the sheet.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LLM Wiki API base URL.")
    parser.add_argument("--project-id", "--project-path", dest="project_id", default=DEFAULT_PROJECT_PATH)
    parser.add_argument("--wiki-timeout", type=float, default=8.0, help="LLM Wiki timeout seconds.")
    parser.add_argument("--codex-bin", default=DEFAULT_CODEX_BIN, help="Codex executable.")
    parser.add_argument("--codex-model", default=DEFAULT_MODEL, help="Codex model for model QC.")
    parser.add_argument("--codex-timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA_PATH), help="Output JSON schema for Codex.")
    parser.add_argument("--prompt-output", help="Where to write the generated Codex prompt.")
    parser.add_argument("--model-output", help="Where to write/read the final model JSON.")
    parser.add_argument("--event-log", help="Where to write Codex JSONL event log.")
    parser.add_argument("--mock-model-output", help="Use an existing JSON file instead of calling Codex.")
    parser.add_argument("--session-id-file", default=str(DEFAULT_SESSION_ID_FILE), help="Persistent Codex QC worker session id file.")
    parser.add_argument("--queue-lock-file", default=str(DEFAULT_QUEUE_LOCK_FILE), help="Queue lock for serial worker access.")
    parser.add_argument("--reset-session", action="store_true", help="Ignore and replace the saved Codex worker session id.")
    parser.add_argument("--queue-timeout-seconds", type=int, default=3600, help="Max seconds to wait for the worker queue lock.")
    parser.add_argument("--stale-lock-seconds", type=int, default=1800, help="Remove queue lock after this many seconds.")
    parser.add_argument("--require-model-validation", action="store_true", help="Require target-model failure evidence.")
    parser.add_argument("--no-image-attachments", action="store_true", help="Do not download Feishu image tokens or pass images to Codex.")
    parser.add_argument("--max-image-attachments", type=int, default=DEFAULT_MAX_IMAGE_ATTACHMENTS, help="Max downloaded images to attach to one Codex prompt.")
    return parser.parse_args()


def artifact_dir(args: argparse.Namespace) -> Path:
    base = Path(args.job_dir).expanduser().resolve() if args.job_dir else Path(tempfile.gettempdir())
    if args.job_id:
        path = base / args.job_id
    else:
        path = base / f"visual-hardcase-codex-qc-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def watcher_args(args: argparse.Namespace) -> argparse.Namespace:
    return SimpleNamespace(
        url=args.url,
        sheet_id=args.sheet_id,
        range_columns=args.range_columns,
        trigger_field=args.trigger_field,
        trigger_value=args.trigger_value,
        result_field=args.result_field,
        repair_done_field=args.repair_done_field,
        repair_done_value=args.repair_done_value,
        no_repair_recheck=args.no_repair_recheck,
        rows=args.rows,
        once=True,
        watch=False,
        interval_seconds=120,
        max_rows_per_cycle=args.max_rows_per_cycle,
        dry_run=args.dry_run,
        force=args.force,
        no_float_images=args.no_float_images,
        no_cell_images=args.no_cell_images,
        base_url=args.base_url,
        project_id=args.project_id,
        timeout=args.wiki_timeout,
        require_model_validation=args.require_model_validation,
    )


def clean_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): item
        for key, item in value.items()
        if not str(key).startswith("_") and str(item or "").strip()
    }


def collect_wiki_evidence(mapped_row: dict[str, str], args: argparse.Namespace) -> list[str]:
    task_type = mapped_row.get("题型分类", "").strip()
    query = f"{task_type} 规则 bad case 质检" if task_type else "v3题型 准入 质检"
    try:
        results = search_wiki(args.base_url, args.project_id, query, args.wiki_timeout)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [f"LLM Wiki 检索失败：{type(exc).__name__}"]
    evidence: list[str] = []
    for item in results[:3]:
        title = str(item.get("title") or item.get("path") or "").strip()
        path = str(item.get("path") or "").strip()
        if title and path:
            evidence.append(f"{title} ({path})")
        elif title:
            evidence.append(title)
    return evidence


def normalize_requirement_key(value: str) -> str:
    return re.sub(r"[\s\-_+＋（）()/\\]+", "", value).casefold()


def load_source_requirements() -> dict[str, dict[str, str]]:
    if not SOURCE_REQUIREMENT_CSV.exists():
        return {}
    output: dict[str, dict[str, str]] = {}
    with SOURCE_REQUIREMENT_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            task_type = str(row.get("题型名称") or "").strip()
            requires = str(row.get("是否需要信源") or "").strip()
            difficulty = str(row.get("难易程度") or "").strip()
            if not task_type:
                continue
            item = {
                "taskType": task_type,
                "difficulty": difficulty,
                "requiresSource": requires,
                "sourceTitle": "题型分类信源表",
                "sourceUrl": SOURCE_REQUIREMENT_URL,
            }
            keys = {normalize_requirement_key(task_type)}
            if "-" in task_type:
                keys.add(normalize_requirement_key(task_type.rsplit("-", 1)[-1]))
            for key in keys:
                output[key] = item
    return output


def source_requirement_for(mapped_row: dict[str, str]) -> dict[str, Any]:
    task_type = str(mapped_row.get("题型分类") or "").strip()
    item = load_source_requirements().get(normalize_requirement_key(task_type))
    if item:
        requirement: dict[str, Any] = dict(item)
    else:
        requirement = {
            "taskType": task_type,
            "difficulty": "未知",
            "requiresSource": "未知",
            "sourceTitle": "题型分类信源表",
            "sourceUrl": SOURCE_REQUIREMENT_URL,
        }
    source_text = str(mapped_row.get("信源链接或标注图路径") or "").strip()
    requirement["sourceProvided"] = bool(source_text)
    return requirement


def prepare_rows(args: argparse.Namespace) -> tuple[argparse.Namespace, str, list[dict[str, Any]]]:
    wargs = watcher_args(args)
    requested = expand_rows(args.rows)
    rows, header_to_col = read_sheet_rows(wargs)
    result_col = header_to_col.get(normalize(args.result_field))
    if not result_col:
        raise SystemExit(f"Cannot find result field: {args.result_field}")
    if not requested and normalize(args.trigger_field) not in header_to_col:
        raise SystemExit(f"Cannot find trigger field: {args.trigger_field}")

    if not args.no_float_images:
        attach_float_images(rows, read_float_images(args.url, args.sheet_id))

    candidates = select_candidates(rows, wargs)
    if requested:
        found = {int(row["_row_number"]) for row in candidates}
        missing = sorted(requested - found)
        if missing:
            print(f"warning: requested rows not found or empty: {missing}")

    candidates = [
        row for row in candidates
        if row_needs_pre_qc(wargs, result_col, row)
    ]
    candidates = candidates[: max(0, args.max_rows_per_cycle)]
    if not args.no_cell_images:
        attach_cell_images(candidates, wargs)

    payload_rows: list[dict[str, Any]] = []
    for row in candidates:
        mapped = map_cloud_row(row)
        source_requirement = source_requirement_for(mapped)
        payload_rows.append(
            {
                "rowNumber": int(row["_row_number"]),
                "raw": clean_dict(row),
                "mapped": clean_dict(mapped),
                "imageCountFromCellTokens": count_cell_images(mapped),
                "answerHasCellImage": has_answer_image(mapped),
                "sourceRequirement": source_requirement,
                "wikiEvidence": collect_wiki_evidence(mapped, args),
                "_allowResultOverwrite": row_allows_result_overwrite(wargs, row),
                "_recheckReason": "是否返修完成=是" if is_repair_done(row, wargs) else "",
            }
        )
    return wargs, result_col, payload_rows


def extract_image_tokens(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    seen: set[str] = set()
    tokens: list[str] = []
    for token in IMAGE_TOKEN_RE.findall(text):
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def token_source_hint(row: dict[str, Any], token: str) -> str:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    mapped = row.get("mapped") if isinstance(row.get("mapped"), dict) else {}
    for key, value in {**raw, **mapped}.items():
        if token in str(value):
            return str(key)
    return "unknown"


def field_slug(source: str) -> str:
    source = source.strip()
    match = re.fullmatch(r"图片(\d+)", source)
    if match:
        return f"image{match.group(1)}"
    if source.lower() == "answer":
        return "answer"
    if source in {"图片文件夹或图片链接", "图片链接", "图片材料"}:
        return "image-list"
    safe = re.sub(r"[^0-9A-Za-z_-]+", "-", source).strip("-")
    return safe or "cell"


def download_feishu_image_token(token: str, output_path: Path) -> tuple[bool, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    cmd = [
        resolve_lark_cli_bin(),
        "api",
        "GET",
        f"/open-apis/drive/v1/medias/{token}/download",
        "--output",
        output_path.name,
        "--as",
        "user",
        "--format",
        "json",
    ]
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=60,
        cwd=str(output_path.parent),
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")
        return False, detail[:300] or f"lark-cli exit {proc.returncode}"
    if not output_path.exists() or output_path.stat().st_size <= 0:
        return False, "download command succeeded but output file is missing or empty"
    return True, ""


def resolve_lark_cli_bin() -> str:
    candidate = os.environ.get("VISUAL_HARDCASE_QC_LARK_CLI_BIN", "lark-cli").strip() or "lark-cli"
    if os.name != "nt":
        return candidate
    path = Path(candidate)
    if path.suffix:
        return candidate
    for name in (f"{candidate}.cmd", f"{candidate}.exe", candidate):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return candidate


def prepare_image_attachments(
    args: argparse.Namespace,
    payload_rows: list[dict[str, Any]],
    out_dir: Path,
) -> list[Path]:
    if args.no_image_attachments or args.mock_model_output:
        return []
    max_images = max(0, int(args.max_image_attachments or 0))
    if max_images == 0:
        return []

    image_dir = out_dir / "images"
    attached: list[Path] = []
    token_cache: dict[str, dict[str, Any]] = {}
    for row in payload_rows:
        row_attachments: list[dict[str, Any]] = []
        row["imageAttachments"] = row_attachments
        row_number = int(row.get("rowNumber") or 0)
        for token in extract_image_tokens({"raw": row.get("raw"), "mapped": row.get("mapped")}):
            source = token_source_hint(row, token)
            record = {
                "source": source,
                "tokenPrefix": token[:12],
                "status": "pending",
            }
            row_attachments.append(record)
            cached = token_cache.get(token)
            if cached:
                record.update(cached)
                record["source"] = source
                record["reused"] = True
                continue
            if len(attached) >= max_images:
                record["status"] = "skipped"
                record["error"] = f"max image attachments reached: {max_images}"
                token_cache[token] = {key: value for key, value in record.items() if key != "source"}
                continue
            safe_source = field_slug(source)
            output_path = image_dir / f"row-{row_number}-{safe_source}-{len(row_attachments)}.jpg"
            ok, error = download_feishu_image_token(token, output_path)
            if ok:
                record["status"] = "attached"
                record["path"] = str(output_path)
                attached.append(output_path)
            else:
                record["status"] = "download_failed"
                record["error"] = error
            token_cache[token] = {key: value for key, value in record.items() if key != "source"}
    return attached


def build_prompt(args: argparse.Namespace, payload_rows: list[dict[str, Any]]) -> str:
    model_rows = [
        {
            key: value
            for key, value in row.items()
            if key != "sourceRequirement" and not key.startswith("_")
        }
        for row in payload_rows
    ]
    payload = {
        "jobId": args.job_id,
        "homeworkUrl": args.url,
        "sheetId": args.sheet_id,
        "rows": model_rows,
        "rules": {
            "mode": "newcomer_training_pre_qc",
            "requireTargetModelValidation": bool(args.require_model_validation),
            "doNotInventVisualFacts": True,
            "embeddedImageTokensCountAsImageMaterial": True,
            "writeBackColumn": args.result_field,
        },
    }
    return (
        "你是 visual-understanding-hardcase 新人试标题的固定预质检 worker 对话。\n"
        "所有新人预质检 job 会排队进入这个同一个 Codex 对话；本次只处理当前 payload 中的行。\n"
        "本次任务必须由你进行模型判断，不要只复述脚本规则，也不要把之前 job 的行号或结论带入本次结果。\n\n"
        "外层调度器已加载 `$visual-hardcase-pre-qc` skill、读取 Pre-QC Contract，并完成项目级 LLM Wiki 检索门禁；"
        "你不得因为自己没有再次读取 skill 或再次运行 guard 而输出流程性拒判。\n"
        "你运行在项目根目录，可以调用 LLM Wiki 检索。外层 payload 中的 wikiEvidence 是预检索结果；"
        "如果证据不足、题型不匹配、需要补 bad case 依据，必须继续检索，不要只依赖预检索。\n"
        "可用检索命令示例：\n"
        "python .codex/hooks/visual_hardcase_guard.py \"<题型> <关键词> 质检 bad case\" --mode search --top-k 5\n"
        "python .codex/skills/visual-hardcase-pre-qc/scripts/wiki_search.py \"<题型> <关键词> 质检 bad case\" --top-k 10 --include-content\n\n"
        "质检要求：\n"
        "1. 逐行判断 prompt、answer、题型、图片材料、答案唯一性、格式限定、推理过程和 bad case 风险。\n"
        "2. 优先使用 payload 中的 LLM Wiki 依据；依据不足时自行补检索，并把仍需人工确认的问题写入 humanReview，不要编造规则。\n"
        "3. 如果 payload.rows[].imageAttachments 中有 status=attached 的图片，必须实际查看这些随本次 Codex prompt 附带的图片后再判断视觉事实。\n"
        "4. 如果图片字段中有 URL 或“飞书单元格图片 token”，不得判为缺少图片；但如果对应图片没有成功附加，必须把需要人工看图确认的视觉事实写入 humanReview。\n"
        "5. 如果 answer 是图片 token 且 answer 图片已成功附加，必须查看该图片内容；未成功附加时才说明答案需要人工确认图片内容。\n"
        "6. 新人训练场景不默认要求目标模型验证；只有 requireTargetModelValidation=true 时才把缺少模型验证作为阻断项。\n"
        "7. 输出必须是严格 JSON，必须符合随命令传入的 JSON Schema；不要输出 Markdown、解释或代码块。\n"
        "8. 面向新人和质检负责人输出时，不要引用内部 JSON 路径或键名，例如 mapped、raw、payload.rows[]；"
        "请直接使用云表字段名，例如【答案是否唯一】、【prompt】、【answer】。\n\n"
        "推荐等级定义：通过、退回修改、拒收、待复核。\n"
        "风险级别定义：低、中、高、阻断。\n\n"
        "待质检数据：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
    )


def image_cli_args(image_paths: list[Path] | None) -> list[str]:
    cli_args: list[str] = []
    for path in image_paths or []:
        cli_args.extend(["--image", str(path)])
    return cli_args


def codex_new_command(
    args: argparse.Namespace,
    output_path: Path,
    image_paths: list[Path] | None = None,
) -> list[str]:
    codex_bin = resolve_codex_bin(args.codex_bin)
    return [
        codex_bin,
        "exec",
        "-C",
        str(REPO_ROOT),
        "--sandbox",
        "read-only",
        "--json",
        "--output-schema",
        str(Path(args.schema).expanduser().resolve()),
        "--output-last-message",
        str(output_path),
        "--model",
        args.codex_model,
        *image_cli_args(image_paths),
        "-",
    ]


def codex_resume_command(
    args: argparse.Namespace,
    session_id: str,
    output_path: Path,
    image_paths: list[Path] | None = None,
) -> list[str]:
    codex_bin = resolve_codex_bin(args.codex_bin)
    return [
        codex_bin,
        "exec",
        "resume",
        "--json",
        "--output-schema",
        str(Path(args.schema).expanduser().resolve()),
        "--output-last-message",
        str(output_path),
        "--model",
        args.codex_model,
        *image_cli_args(image_paths),
        session_id,
        "-",
    ]


def resolve_codex_bin(value: str) -> str:
    candidate = value.strip() or "codex"
    if os.name != "nt":
        return candidate
    path = Path(candidate)
    if path.suffix:
        return candidate
    for name in (f"{candidate}.cmd", f"{candidate}.exe", candidate):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return candidate


def parse_json_text(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, flags=re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model output must be a JSON object")
    return data


class FileLock:
    def __init__(self, path: Path, timeout_seconds: int, stale_seconds: int) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.stale_seconds = stale_seconds
        self.fd: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout_seconds
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, f"pid={os.getpid()} created={datetime.now().isoformat()}\n".encode("utf-8"))
                return self
            except FileExistsError:
                if self._is_stale():
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.time() >= deadline:
                    raise TimeoutError(f"timed out waiting for Codex QC worker queue lock: {self.path}")
                time.sleep(2)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _is_stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        return age > self.stale_seconds


def session_id_file(args: argparse.Namespace) -> Path:
    return Path(args.session_id_file).expanduser().resolve()


def read_saved_session_id(args: argparse.Namespace) -> str:
    env_value = os.environ.get("VISUAL_HARDCASE_QC_CODEX_SESSION_ID", "").strip()
    if env_value and not args.reset_session:
        return env_value
    path = session_id_file(args)
    if args.reset_session or not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def save_session_id(args: argparse.Namespace, session_id: str) -> None:
    if not session_id or os.environ.get("VISUAL_HARDCASE_QC_CODEX_SESSION_ID", "").strip():
        return
    path = session_id_file(args)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session_id.strip() + "\n", encoding="utf-8")


def run_codex_once(
    args: argparse.Namespace,
    prompt: str,
    out_dir: Path,
    image_paths: list[Path] | None = None,
) -> tuple[dict[str, Any], str]:
    prompt_path = Path(args.prompt_output).expanduser().resolve() if args.prompt_output else out_dir / "prompt.md"
    output_path = Path(args.model_output).expanduser().resolve() if args.model_output else out_dir / "model-output.json"
    event_log_path = Path(args.event_log).expanduser().resolve() if args.event_log else out_dir / "codex-events.jsonl"
    prompt_path.write_text(prompt, encoding="utf-8")

    if args.mock_model_output:
        text = Path(args.mock_model_output).expanduser().read_text(encoding="utf-8")
        output_path.write_text(text, encoding="utf-8")
        return parse_json_text(text), "mock"

    session_id = read_saved_session_id(args)
    cmd = (
        codex_resume_command(args, session_id, output_path, image_paths)
        if session_id
        else codex_new_command(args, output_path, image_paths)
    )
    proc = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=args.codex_timeout_seconds,
        cwd=str(REPO_ROOT),
        encoding="utf-8",
        errors="replace",
    )
    event_log_path.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(
            "codex exec failed "
            f"(exit={proc.returncode}); stderr={proc.stderr[-2000:]}; event_log={event_log_path}"
        )
    if not output_path.exists():
        raise RuntimeError(f"codex exec did not create output file: {output_path}")
    data = parse_json_text(output_path.read_text(encoding="utf-8"))
    parsed_session_id = extract_session_hint(proc.stdout)
    if parsed_session_id and not session_id:
        save_session_id(args, parsed_session_id)
    return data, session_id or parsed_session_id


def run_codex(
    args: argparse.Namespace,
    prompt: str,
    out_dir: Path,
    image_paths: list[Path] | None = None,
) -> tuple[dict[str, Any], str]:
    lock_path = Path(args.queue_lock_file).expanduser().resolve()
    with FileLock(lock_path, args.queue_timeout_seconds, args.stale_lock_seconds):
        return run_codex_once(args, prompt, out_dir, image_paths)


def extract_session_hint(jsonl: str) -> str:
    for line in jsonl.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key in ("thread_id", "threadId", "session_id", "sessionId", "id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
        payload = item.get("payload")
        if isinstance(payload, dict):
            for key in ("thread_id", "threadId", "session_id", "sessionId", "id"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
    return ""


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value:
        return [str(value).strip()]
    return []


def display_field_label(field_name: str) -> str:
    name = field_name.strip()
    return DISPLAY_FIELD_LABELS.get(name, f"【{name}】字段")


def sanitize_model_text(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""

    def replace_json_field(match: re.Match[str]) -> str:
        return display_field_label(match.group(1))

    value = re.sub(r"\bmapped\s*中\s*[“\"]([^”\"]+)[”\"]", replace_json_field, value)
    value = re.sub(r"\bmapped\s*中的\s*[“\"]([^”\"]+)[”\"]", replace_json_field, value)
    value = re.sub(r"\braw\s*中\s*[“\"]([^”\"]+)[”\"]", replace_json_field, value)
    value = re.sub(r"\braw\s*中的\s*[“\"]([^”\"]+)[”\"]", replace_json_field, value)
    value = value.replace("payload.rows[].mapped", "云表字段")
    value = value.replace("payload.rows[].raw", "云表原始字段")
    value = re.sub(r"\bmapped\b", "云表字段", value)
    value = re.sub(r"\braw\b", "云表原始字段", value)
    return value


def sanitize_model_list(value: Any) -> list[str]:
    return [item for item in (sanitize_model_text(text) for text in normalize_list(value)) if item]


def summarize_image_attachments(attachments: list[dict[str, Any]] | None) -> str:
    if not attachments:
        return ""
    grouped: dict[str, dict[str, int]] = {}
    order: list[str] = []
    for item in attachments:
        source = str(item.get("source") or "unknown").strip() or "unknown"
        status = str(item.get("status") or "unknown").strip() or "unknown"
        if source not in grouped:
            grouped[source] = {}
            order.append(source)
        grouped[source][status] = grouped[source].get(status, 0) + 1

    labels = {
        "attached": "已传给Codex",
        "download_failed": "下载失败",
        "skipped": "未传",
        "pending": "待处理",
    }
    parts: list[str] = []
    for source in order:
        status_parts = [
            f"{labels.get(status, status)}{count}张"
            for status, count in grouped[source].items()
        ]
        parts.append(f"{source}：" + "，".join(status_parts))
    return "；".join(parts)


def risk_at_least(current: str, minimum: str) -> str:
    order = ["低", "中", "高", "阻断"]
    if current not in order:
        current = "中"
    if minimum not in order:
        minimum = "中"
    return order[max(order.index(current), order.index(minimum))]


def source_requirement_summary(source_requirement: dict[str, Any] | None) -> str:
    if not source_requirement:
        return ""
    requires = str(source_requirement.get("requiresSource") or "未知").strip() or "未知"
    provided = bool(source_requirement.get("sourceProvided"))
    task_type = str(source_requirement.get("taskType") or "").strip()
    requirement_text = {
        "是": "需要信源",
        "否": "不需要信源",
    }.get(requires, "信源要求未知")
    current_text = "已填写" if provided else "未填写"
    prefix = f"{task_type}：" if task_type else ""
    return f"{prefix}{requirement_text}；当前：{current_text}；依据：知识库"


def apply_source_requirement_to_result(
    result: dict[str, Any],
    source_requirement: dict[str, Any] | None,
) -> dict[str, Any]:
    if not source_requirement:
        return result
    requires = str(source_requirement.get("requiresSource") or "").strip()
    provided = bool(source_requirement.get("sourceProvided"))
    if requires != "是" or provided:
        return result

    updated = dict(result)
    issues = normalize_list(updated.get("issues"))
    suggestions = normalize_list(updated.get("suggestions"))
    evidence = normalize_list(updated.get("evidence"))
    source_issue = "知识库标记该题型需要信源，但信源链接或标注图路径为空。"
    if source_issue not in issues:
        issues.insert(0, source_issue)
    source_suggestion = "补充可追溯的信源链接、标注图路径或按题型要求上传标注图。"
    if source_suggestion not in suggestions:
        suggestions.insert(0, source_suggestion)
    source_evidence = "知识库信源要求"
    if source_evidence not in evidence:
        evidence.append(source_evidence)

    recommendation = str(updated.get("recommendation") or "待复核")
    if recommendation == "通过":
        updated["recommendation"] = "退回修改"
    updated["riskLevel"] = risk_at_least(str(updated.get("riskLevel") or "中"), "中")
    updated["score"] = min(int(updated.get("score") or 0), 80)
    updated["issues"] = issues
    updated["suggestions"] = suggestions
    updated["evidence"] = evidence
    return updated


def result_by_row(model_output: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows = model_output.get("rows")
    if not isinstance(rows, list):
        raise ValueError("model output missing rows[]")
    output: dict[int, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        row_number = int(item.get("rowNumber") or 0)
        if row_number > 0:
            output[row_number] = item
    return output


def format_model_result(
    result: dict[str, Any],
    mapped_row: dict[str, str],
    session_hint: str,
    image_attachments: list[dict[str, Any]] | None = None,
    source_requirement: dict[str, Any] | None = None,
) -> str:
    result = apply_source_requirement_to_result(result, source_requirement)
    recommendation = str(result.get("recommendation") or "待复核")
    score = int(result.get("score") or 0)
    risk = str(result.get("riskLevel") or "中")
    blockers = sanitize_model_list(result.get("blockers"))
    issues = sanitize_model_list(result.get("issues"))
    suggestions = sanitize_model_list(result.get("suggestions"))
    evidence = normalize_list(result.get("evidence"))
    human_review = sanitize_model_list(result.get("humanReview"))
    bad_case = str(result.get("badCaseCategory") or "未命中已知类别").strip()
    summary = sanitize_model_text(str(result.get("reasoningSummary") or "").strip())

    lines: list[str] = []
    source_summary = source_requirement_summary(source_requirement)
    if source_summary:
        lines.append(f"信源要求：{source_summary}")
    lines.append("阻断项：" + ("；".join(blockers[:3]) if blockers else "无明显阻断项"))
    if issues:
        lines.append("主要风险：" + "；".join(issues[:3]))
    if suggestions:
        lines.append("修改建议：" + "；".join(suggestions[:3]))
    lines.append(f"Bad Case归类：{bad_case}")
    if summary:
        lines.append(f"模型判断摘要：{summary[:240]}")
    if human_review:
        lines.append("人工复核：" + "；".join(human_review[:3]))
    lines.append("规则依据：" + ("；".join(evidence[:3]) if evidence else "未检索到依据，请人工复核"))
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    out_dir = artifact_dir(args)
    wargs, result_col, payload_rows = prepare_rows(args)
    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"codex_model_candidates={len(payload_rows)} result_col={result_col} model={args.codex_model}"
    )
    if not payload_rows:
        return 0

    image_paths = prepare_image_attachments(args, payload_rows, out_dir)
    prompt = build_prompt(args, payload_rows)
    model_output, session_hint = run_codex(args, prompt, out_dir, image_paths)
    by_row = result_by_row(model_output)
    mapped_by_row = {item["rowNumber"]: item["mapped"] for item in payload_rows}
    attachments_by_row = {item["rowNumber"]: item.get("imageAttachments") or [] for item in payload_rows}
    source_requirements_by_row = {item["rowNumber"]: item.get("sourceRequirement") or {} for item in payload_rows}
    overwrite_by_row = {item["rowNumber"]: bool(item.get("_allowResultOverwrite")) for item in payload_rows}

    missing = sorted(set(mapped_by_row) - set(by_row))
    if missing:
        raise RuntimeError(f"model output missing requested rows: {missing}")

    for row_number in sorted(mapped_by_row):
        value = format_model_result(
            by_row[row_number],
            mapped_by_row[row_number],
            session_hint,
            attachments_by_row.get(row_number),
            source_requirements_by_row.get(row_number),
        )
        if args.dry_run or args.no_write:
            print(f"  dry-run row={row_number} recommendation={by_row[row_number].get('recommendation')}")
            continue
        if write_pre_qc_result(
            wargs,
            result_col,
            row_number,
            value,
            allow_overwrite=overwrite_by_row.get(row_number, False),
        ):
            print(
                f"  wrote row={row_number} "
                f"recommendation={by_row[row_number].get('recommendation')} "
                f"score={by_row[row_number].get('score')}"
            )
    print(f"artifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

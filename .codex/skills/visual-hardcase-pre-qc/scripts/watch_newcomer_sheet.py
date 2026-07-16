#!/usr/bin/env python3
"""Watch the newcomer Feishu sheet and write AI pre-QC results."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any


DEFAULT_URL = "https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl"
DEFAULT_SHEET_ID = "eL8Rfl"
DEFAULT_RANGE_COLUMNS = "A:AD"
DEFAULT_TRIGGER_FIELD = "质检类别"
DEFAULT_TRIGGER_VALUE = "测试组"
DEFAULT_RESULT_FIELD = "预质检"
DEFAULT_REPAIR_DONE_FIELD = "是否返修完成"
DEFAULT_REPAIR_DONE_VALUE = "是"
DEFAULT_INTERVAL_SECONDS = 120
DEFAULT_MAX_ROWS_PER_CYCLE = 10
NON_ACTIONABLE_NEWCOMER_ISSUES = (
    "当前云表模式未强制目标模型验证",
)
NEWCOMER_TEXT_REWRITES = {
    "答案唯一性未确认。": "S列【答案是否唯一】未填写“是”；请确认该题只有一个标准答案。",
}

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parents[2]
TRAINING_SCRIPTS_DIR = REPO_ROOT / ".codex" / "skills" / "visual-hardcase-training-review" / "scripts"


def load_embedded_token() -> None:
    if os.environ.get("LLM_WIKI_API_TOKEN", "").strip():
        return
    candidates = [
        SKILL_DIR / "config" / "llm_wiki_token.txt",
        REPO_ROOT / ".codex" / "hooks" / "config" / "llm_wiki_token.txt",
        REPO_ROOT / ".codex" / "skills" / "visual-hardcase-newcomer-onboarding" / "config" / "llm_wiki_token.txt",
        REPO_ROOT / ".codex" / "skills" / "visual-hardcase-faq" / "config" / "llm_wiki_token.txt",
    ]
    for path in candidates:
        if not path.exists():
            continue
        token = path.read_text(encoding="utf-8").strip()
        if token:
            os.environ["LLM_WIKI_API_TOKEN"] = token
            return


if str(TRAINING_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TRAINING_SCRIPTS_DIR))

load_embedded_token()

from review_lark_sheet import IMAGE_ADDRESS_COLUMNS, attach_float_images, map_cloud_row, read_float_images, run_lark_cli  # noqa: E402
from review_training_workbook import DEFAULT_BASE_URL, DEFAULT_PROJECT_PATH, review_row  # noqa: E402

CONTENT_IMAGE_COLUMNS = {
    **IMAGE_ADDRESS_COLUMNS,
    "Q": "answer",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto pre-QC newcomer rows in a Feishu sheet.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Feishu sheet/wiki URL.")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID, help="Target sheet id.")
    parser.add_argument("--range-columns", default=DEFAULT_RANGE_COLUMNS, help="Columns to read, e.g. A:AD.")
    parser.add_argument("--trigger-field", default=DEFAULT_TRIGGER_FIELD, help="Header field used to trigger pre-QC.")
    parser.add_argument("--trigger-value", default=DEFAULT_TRIGGER_VALUE, help="Trigger value.")
    parser.add_argument("--result-field", default=DEFAULT_RESULT_FIELD, help="Header field to write pre-QC result.")
    parser.add_argument("--repair-done-field", default=DEFAULT_REPAIR_DONE_FIELD, help="Header field that marks a repaired submission.")
    parser.add_argument("--repair-done-value", default=DEFAULT_REPAIR_DONE_VALUE, help="Value that marks a repaired submission.")
    parser.add_argument("--no-repair-recheck", action="store_true", help="Do not re-run rows whose repair-done field is marked done.")
    parser.add_argument("--rows", help="Specific sheet rows to review, e.g. 946:950 or 946,947,948,949,950.")
    parser.add_argument("--once", action="store_true", help="Run one scan cycle and exit.")
    parser.add_argument("--watch", action="store_true", help="Poll continuously.")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS, help="Polling interval.")
    parser.add_argument("--max-rows-per-cycle", type=int, default=DEFAULT_MAX_ROWS_PER_CYCLE, help="Max rows to review per cycle.")
    parser.add_argument("--dry-run", action="store_true", help="List candidate rows without calling QC or writing.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing result-field values.")
    parser.add_argument("--no-float-images", action="store_true", help="Do not attach floating images from the sheet.")
    parser.add_argument("--no-cell-images", action="store_true", help="Do not attach embedded cell images from the sheet.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LLM Wiki API base URL.")
    parser.add_argument(
        "--project-id",
        "--project-path",
        dest="project_id",
        default=DEFAULT_PROJECT_PATH,
        help="LLM Wiki project id. --project-path is kept as a compatibility alias.",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="LLM Wiki timeout seconds.")
    parser.add_argument("--require-model-validation", action="store_true", help="Require model-failure validation.")
    return parser.parse_args()


def normalize(value: object) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def expand_rows(value: str | None) -> set[int]:
    if not value:
        return set()
    normalized = value.strip().replace("：", ":").replace("，", ",")
    if ":" in normalized or "-" in normalized:
        sep = ":" if ":" in normalized else "-"
        start_text, end_text = normalized.split(sep, 1)
        start = int(start_text.strip())
        end = int(end_text.strip())
        if end < start:
            raise SystemExit("Invalid --rows: end row is smaller than start row.")
        return set(range(start, end + 1))
    return {int(part.strip()) for part in normalized.split(",") if part.strip()}


def parse_annotated_csv(annotated_csv: str) -> list[tuple[int, list[str]]]:
    logical_records: list[tuple[int, str]] = []
    current_row: int | None = None
    current_text = ""
    for physical_line in annotated_csv.splitlines():
        match = re.match(r"^\[row=(\d+)\]\s?(.*)$", physical_line)
        if match:
            if current_row is not None:
                logical_records.append((current_row, current_text))
            current_row = int(match.group(1))
            current_text = match.group(2)
        elif current_row is not None:
            current_text += "\n" + physical_line
    if current_row is not None:
        logical_records.append((current_row, current_text))

    records: list[tuple[int, list[str]]] = []
    for row_num, record_text in logical_records:
        values = next(csv.reader(io.StringIO(record_text, newline="")), [""])
        records.append((row_num, values))
    return records


def read_sheet_rows(args: argparse.Namespace) -> tuple[list[dict[str, str]], dict[str, str]]:
    end_col = args.range_columns.split(":", 1)[-1]
    data = run_lark_cli([
        "sheets",
        "+workbook-info",
        "--url",
        args.url,
        "--as",
        "user",
        "--format",
        "json",
    ])
    sheet = next((item for item in data.get("data", {}).get("sheets", []) if item.get("sheet_id") == args.sheet_id), None)
    if not sheet:
        raise SystemExit(f"Cannot find sheet_id={args.sheet_id} in workbook.")
    row_count = int(sheet.get("row_count") or 1)

    sheet_data = run_lark_cli([
        "sheets",
        "+csv-get",
        "--url",
        args.url,
        "--sheet-id",
        args.sheet_id,
        "--range",
        f"A1:{end_col}{row_count}",
        "--as",
        "user",
        "--format",
        "json",
    ])
    records = parse_annotated_csv(sheet_data["data"]["annotated_csv"])
    header_row = next((row for row_num, row in records if row_num == 1), None)
    if not header_row:
        raise SystemExit("Cannot find header row 1.")
    col_indices = sheet_data["data"].get("col_indices", [])
    header_to_col = {
        normalize(header): col_indices[index]
        for index, header in enumerate(header_row)
        if header and index < len(col_indices)
    }
    rows: list[dict[str, str]] = []
    for row_num, values in records:
        if row_num == 1:
            continue
        item: dict[str, str] = {"_row_number": str(row_num)}
        for index, header in enumerate(header_row):
            value = values[index].strip() if index < len(values) else ""
            col = col_indices[index] if index < len(col_indices) else str(index)
            item[header] = value
            item[f"_col_{col}"] = value
        if any(value for key, value in item.items() if not key.startswith("_")):
            rows.append(item)
    return rows, header_to_col


def select_candidates(rows: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    target_rows = expand_rows(args.rows)
    trigger_key = args.trigger_field
    for row in rows:
        if target_rows:
            if int(row["_row_number"]) in target_rows:
                candidates.append(row)
            continue
        if normalize(row.get(trigger_key)) != normalize(args.trigger_value):
            continue
        candidates.append(row)
    return candidates


def repair_recheck_enabled(args: argparse.Namespace) -> bool:
    return not bool(getattr(args, "no_repair_recheck", False))


def is_repair_done(row: dict[str, str], args: argparse.Namespace) -> bool:
    if not repair_recheck_enabled(args):
        return False
    field = getattr(args, "repair_done_field", DEFAULT_REPAIR_DONE_FIELD)
    value = getattr(args, "repair_done_value", DEFAULT_REPAIR_DONE_VALUE)
    return normalize(row.get(field)) == normalize(value)


def row_needs_pre_qc(args: argparse.Namespace, result_col: str, row: dict[str, str]) -> bool:
    if getattr(args, "force", False):
        return True
    row_number = int(row["_row_number"])
    if not read_existing_result(args, result_col, row_number):
        return True
    return is_repair_done(row, args)


def row_allows_result_overwrite(args: argparse.Namespace, row: dict[str, str]) -> bool:
    return bool(getattr(args, "force", False) or is_repair_done(row, args))


def extract_embed_image_refs(cell: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for part in cell.get("rich_text") or []:
        if not isinstance(part, dict):
            continue
        image_token = str(part.get("image_token") or "").strip()
        if not image_token:
            continue
        width = part.get("image_width")
        height = part.get("image_height")
        suffix = f" ({width}x{height})" if width and height else ""
        refs.append(f"飞书单元格图片 token:{image_token}{suffix}")
    return refs


def attach_cell_images(rows: list[dict[str, str]], args: argparse.Namespace) -> None:
    if not rows:
        return
    row_numbers = [int(row["_row_number"]) for row in rows if row.get("_row_number", "").isdigit()]
    if not row_numbers:
        return
    start_row, end_row = min(row_numbers), max(row_numbers)
    data = run_lark_cli([
        "sheets",
        "+cells-get",
        "--url",
        args.url,
        "--sheet-id",
        args.sheet_id,
        "--range",
        f"G{start_row}:Q{end_row}",
        "--include",
        "value",
        "--as",
        "user",
        "--format",
        "json",
    ])
    rows_by_number = {int(row["_row_number"]): row for row in rows if row.get("_row_number", "").isdigit()}
    for block in data.get("data", {}).get("ranges", []):
        row_indices = block.get("row_indices") or []
        col_indices = block.get("col_indices") or []
        cells = block.get("cells") or []
        for row_offset, row_cells in enumerate(cells):
            if row_offset >= len(row_indices):
                continue
            row = rows_by_number.get(int(row_indices[row_offset]))
            if row is None:
                continue
            for col_offset, cell in enumerate(row_cells):
                if col_offset >= len(col_indices) or not isinstance(cell, dict):
                    continue
                field = CONTENT_IMAGE_COLUMNS.get(str(col_indices[col_offset]))
                refs = extract_embed_image_refs(cell)
                if not field or not refs:
                    continue
                existing = row.get(field, "").strip()
                combined = "\n".join(refs)
                row[field] = f"{existing}\n{combined}".strip() if existing else combined


def recommendation_for(conclusion: str) -> str:
    if conclusion in {"合格", "基本合格"}:
        return "通过"
    if conclusion == "需修改":
        return "退回修改"
    if conclusion == "不合格":
        return "拒收"
    return "待复核"


def count_cell_images(mapped_row: dict[str, str]) -> int:
    image_text = mapped_row.get("图片文件夹或图片链接", "")
    return len(re.findall(r"飞书单元格图片 token:", image_text))


def count_cell_images_in_raw_row(row: dict[str, str]) -> int:
    return sum(value.count("飞书单元格图片 token:") for key, value in row.items() if key.startswith("图片"))


def has_answer_image(mapped_row: dict[str, str]) -> bool:
    return "飞书单元格图片 token:" in str(mapped_row.get("answer", ""))


def sanitize_newcomer_result(result: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(result)
    issues = list(cleaned.get("issues") or [])
    visible_issues = [
        issue for issue in issues
        if not any(marker in issue for marker in NON_ACTIONABLE_NEWCOMER_ISSUES)
    ]
    removed_count = len(issues) - len(visible_issues)
    cleaned["issues"] = visible_issues
    if removed_count:
        cleaned["score"] = min(100, int(cleaned.get("score") or 0) + 3 * removed_count)
        if not cleaned.get("blockers") and not visible_issues:
            cleaned["conclusion"] = "合格"
        elif not cleaned.get("blockers") and cleaned.get("conclusion") == "需修改" and cleaned["score"] >= 85:
            cleaned["conclusion"] = "基本合格"
    return cleaned


def rewrite_newcomer_text(items: list[str]) -> list[str]:
    return [NEWCOMER_TEXT_REWRITES.get(item, item) for item in items]


def format_result(result: dict[str, Any], mapped_row: dict[str, str]) -> str:
    recommendation = recommendation_for(str(result.get("conclusion", "")))
    blockers = rewrite_newcomer_text(result.get("blockers") or [])
    issues = rewrite_newcomer_text(result.get("issues") or [])
    suggestions = rewrite_newcomer_text(result.get("suggestions") or [])
    evidence = result.get("evidence") or []
    lines = [
        f"AI预质检：{recommendation}（{result.get('conclusion', '未知')}，{result.get('score', 0)}分）",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    image_count = count_cell_images(mapped_row)
    if image_count:
        lines.append(f"图片材料：已检测到 {image_count} 张飞书单元格图片，未判为缺图。")
    if has_answer_image(mapped_row):
        lines.append("答案材料：Q列 answer 已检测到单元格图片，未判为缺少 answer。")
    lines.append("阻断项：" + ("；".join(blockers[:3]) if blockers else "无明显阻断项"))
    if issues:
        lines.append("主要风险：" + "；".join(issues[:3]))
    if suggestions:
        lines.append("修改建议：" + "；".join(suggestions[:3]))
    if evidence:
        lines.append("规则依据：" + "；".join(evidence[:3]))
    if not evidence:
        lines.append("规则依据：未检索到依据，请人工复核")
    return "\n".join(lines)


def read_existing_result(args: argparse.Namespace, result_col: str, row_number: int) -> str:
    data = run_lark_cli([
        "sheets",
        "+csv-get",
        "--url",
        args.url,
        "--sheet-id",
        args.sheet_id,
        "--range",
        f"{result_col}{row_number}:{result_col}{row_number}",
        "--as",
        "user",
        "--format",
        "json",
    ])
    records = parse_annotated_csv(data["data"]["annotated_csv"])
    for found_row, values in records:
        if found_row == row_number and values:
            return values[0].strip()
    return ""


def write_pre_qc_result(
    args: argparse.Namespace,
    result_col: str,
    row_number: int,
    value: str,
    allow_overwrite: bool = False,
) -> bool:
    overwrite = bool(args.force or allow_overwrite)
    if not overwrite and read_existing_result(args, result_col, row_number):
        print(f"  skip row={row_number} because {args.result_field} is no longer empty")
        return False
    payload = json.dumps([[{"value": value}]], ensure_ascii=False)
    cli_args = [
        "sheets",
        "+cells-set",
        "--url",
        args.url,
        "--sheet-id",
        args.sheet_id,
        "--range",
        f"{result_col}{row_number}:{result_col}{row_number}",
        "--cells",
        "-",
        f"--allow-overwrite={'true' if overwrite else 'false'}",
        "--as",
        "user",
        "--format",
        "json",
    ]
    run_lark_cli(cli_args, stdin=payload)
    return True


def run_cycle(args: argparse.Namespace) -> int:
    rows, header_to_col = read_sheet_rows(args)
    result_col = header_to_col.get(normalize(args.result_field))
    if not result_col:
        raise SystemExit(f"Cannot find result field: {args.result_field}")
    if normalize(args.trigger_field) not in header_to_col:
        raise SystemExit(f"Cannot find trigger field: {args.trigger_field}")

    if not args.no_float_images:
        attach_float_images(rows, read_float_images(args.url, args.sheet_id))

    candidates = [
        row for row in select_candidates(rows, args)
        if row_needs_pre_qc(args, result_col, row)
    ]
    candidates = candidates[: max(0, args.max_rows_per_cycle)]
    if not args.no_cell_images:
        attach_cell_images(candidates, args)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] candidates={len(candidates)} result_col={result_col}")
    for row in candidates:
        row_number = int(row["_row_number"])
        print(
            f"  row={row_number} name={row.get('姓名', '')} "
            f"type={row.get('分类', '')} cell_images={count_cell_images_in_raw_row(row)} "
            f"answer_image={str('飞书单元格图片 token:' in row.get('answer', '')).lower()}"
        )

    if args.dry_run or not candidates:
        return len(candidates)

    reviewer_args = SimpleNamespace(
        base_url=args.base_url,
        project_id=args.project_id,
        timeout=args.timeout,
        require_model_validation=args.require_model_validation,
    )
    for row in candidates:
        row_number = int(row["_row_number"])
        mapped = map_cloud_row(row)
        result = sanitize_newcomer_result(review_row(mapped, reviewer_args))
        if write_pre_qc_result(
            args,
            result_col,
            row_number,
            format_result(result, mapped),
            allow_overwrite=row_allows_result_overwrite(args, row),
        ):
            print(f"  wrote row={row_number} recommendation={recommendation_for(result['conclusion'])} score={result['score']}")
    return len(candidates)


def main() -> int:
    args = parse_args()
    if not args.watch and not args.once:
        args.once = True
    while True:
        run_cycle(args)
        if args.once or not args.watch:
            break
        time.sleep(max(10, args.interval_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

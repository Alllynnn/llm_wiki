#!/usr/bin/env python3
"""Review rows from a Feishu/Lark cloud training sheet."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from review_training_workbook import DEFAULT_BASE_URL, DEFAULT_PROJECT_PATH, has_format_constraint, review_row


DEFAULT_URL = "https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl"
DEFAULT_SHEET_ID = "eL8Rfl"
DEFAULT_RANGE_COLUMNS = "A:AB"
DEFAULT_REPORT_DIR = Path.home() / "Downloads" / "visual-hardcase-training-reports"


TASK_TYPE_ALIASES = {
    "ocr-票据": "OCR票据",
    "OCR-票据": "OCR票据",
    "基础感知-读示数": "读示数",
    "基础感知-实物判断": "实物判断",
    "基础感知-多图变化": "多图变化",
    "推理游戏-齿轮": "齿轮",
    "推理游戏-漫画排序": "漫画排序",
    "推理游戏-地图规划": "地图规划",
    "推理游戏-图形关系": "图形关系",
    "推理+感知-多图场景判别": "多图场景判别",
    "推理感知-多图场景判别": "多图场景判别",
    "推理+感知-双目双图结合": "双目双图结合",
    "推理+感知-多图同屋判别": "多图同屋判别",
    "判断与反思-纠错": "判断与反思-纠错",
}


IMAGE_LIST_COLUMNS = [
    "图片列表（URL，一行一张）",
    "图片列表",
    "图片链接列表",
    "图片URL列表",
    "图片URL",
]

IMAGE_ADDRESS_COLUMNS = {
    "G": "图片1",
    "H": "图片2",
    "I": "图片3",
    "J": "图片4",
    "K": "图片5",
    "L": "图片6",
    "M": "图片7",
    "N": "图片8",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review Feishu cloud training sheet rows.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Feishu sheet/wiki URL.")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID, help="Target sheet id.")
    parser.add_argument("--rows", required=True, help="Row range, e.g. 2:20 or 7.")
    parser.add_argument("--out-dir", help=f"Output directory. Defaults to {DEFAULT_REPORT_DIR}.")
    parser.add_argument("--write-back", action="store_true", help="Write result and text notes back to the cloud sheet.")
    parser.add_argument("--require-model-validation", action="store_true", help="Block rows without target-model failure evidence.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LLM Wiki API base URL.")
    parser.add_argument(
        "--project-id",
        "--project-path",
        dest="project_id",
        default=DEFAULT_PROJECT_PATH,
        help="LLM Wiki project id. --project-path is kept as a compatibility alias.",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="LLM Wiki timeout seconds.")
    parser.add_argument("--no-float-images", action="store_true", help="Do not map sheet floating images into image columns.")
    return parser.parse_args()


def parse_rows(value: str) -> tuple[int, int]:
    if ":" in value:
        start, end = value.split(":", 1)
        return int(start), int(end)
    row = int(value)
    return row, row


def run_lark_cli(args: list[str], stdin: str | None = None) -> dict[str, Any]:
    lark_cli = shutil.which("lark-cli") or shutil.which("lark-cli.cmd")
    if not lark_cli and os.name == "nt":
        candidate = Path(os.environ.get("APPDATA", "")) / "npm" / "lark-cli.cmd"
        if candidate.exists():
            lark_cli = str(candidate)
    if not lark_cli:
        raise SystemExit("Cannot find lark-cli. Install lark-cli or add it to PATH.")
    env = os.environ.copy()
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    proc = subprocess.run(
        [lark_cli, *args],
        input=stdin,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stdout + proc.stderr)
    text = proc.stdout.strip()
    start = text.find("{")
    if start < 0:
        raise SystemExit(f"lark-cli returned no JSON: {text[:1000]}")
    return json.loads(text[start:])


def read_cloud_rows(url: str, sheet_id: str, start_row: int, end_row: int) -> list[dict[str, str]]:
    data = run_lark_cli([
        "sheets",
        "+csv-get",
        "--url",
        url,
        "--sheet-id",
        sheet_id,
        "--range",
        f"A1:AB{end_row}",
        "--as",
        "user",
        "--format",
        "json",
    ])
    annotated = data["data"]["annotated_csv"]
    records: list[tuple[int, list[str]]] = []
    logical_records: list[tuple[int, str]] = []
    current_row: int | None = None
    current_text = ""
    for physical_line in annotated.splitlines():
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

    for row_num, record_text in logical_records:
        parsed = next(csv.reader(io.StringIO(record_text, newline="")))
        records.append((row_num, parsed))
    header_row = next((row for row_num, row in records if row_num == 1), None)
    if not header_row:
        raise SystemExit("Cannot find header row 1 in cloud sheet.")
    selected: list[dict[str, str]] = []
    for row_num, values in records:
        if row_num < start_row or row_num > end_row:
            continue
        item = {header_row[index]: (values[index].strip() if index < len(values) else "") for index in range(len(header_row))}
        item["_row_number"] = str(row_num)
        if any(value for key, value in item.items() if key != "_row_number"):
            selected.append(item)
    return selected


def parse_cell_address(address: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"([A-Z]+)(\d+)", address.strip())
    if not match:
        return None
    return match.group(1), int(match.group(2))


def read_float_images(url: str, sheet_id: str) -> list[dict[str, Any]]:
    data = run_lark_cli([
        "sheets",
        "+float-image-list",
        "--url",
        url,
        "--sheet-id",
        sheet_id,
        "--as",
        "user",
        "--format",
        "json",
    ])
    sheets = data.get("data", {}).get("sheets", [])
    images: list[dict[str, Any]] = []
    for sheet in sheets:
        images.extend(sheet.get("float_images", []))
    return images


def attach_float_images(rows: list[dict[str, str]], float_images: list[dict[str, Any]]) -> None:
    rows_by_number = {int(row["_row_number"]): row for row in rows if row.get("_row_number", "").isdigit()}
    for image in float_images:
        address = str(image.get("address", ""))
        parsed = parse_cell_address(address)
        if not parsed:
            continue
        col, row_number = parsed
        field = IMAGE_ADDRESS_COLUMNS.get(col)
        row = rows_by_number.get(row_number)
        url = str(image.get("url", "")).strip()
        if not field or row is None or not url:
            continue
        if row.get(field, "").strip():
            continue
        row[field] = url


def get(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row and row[name].strip():
            return row[name].strip()
    return ""


def normalize_task_type(value: str) -> str:
    value = value.strip()
    return TASK_TYPE_ALIASES.get(value, value.split("-")[-1] if "-" in value else value)


def split_image_list(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[\n\r；;，,]+", value)
    return [part.strip() for part in parts if part.strip()]


def map_cloud_row(row: dict[str, str]) -> dict[str, str]:
    image_list = get(row, *IMAGE_LIST_COLUMNS)
    image_values = split_image_list(image_list)
    image_values.extend(get(row, f"图片{i}") for i in range(1, 9))
    images = [value for value in image_values if value]
    validation = get(row, "验证截图（不填）\n内部试标不用跑模型进行验证")
    return {
        "case_id": f"row-{row['_row_number']}",
        "新人姓名": get(row, "姓名"),
        "训练批次": get(row, "日期"),
        "题型分类": normalize_task_type(get(row, "分类")),
        "图片数量": str(len(images)),
        "图片文件夹或图片链接": "\n".join(images) if images else "云表格图片列未读取到文本；请人工查看单元格图片。",
        "图片编号说明": get(row, "图片顺序是否正确\n（必须正确排序）（可以空着）") or "云表格图片1-8列",
        "prompt": get(row, "prompt"),
        "answer": get(row, "answer"),
        "答案格式限定是否已写入prompt": "是" if has_format_hint(get(row, "prompt")) else "否",
        "答案是否唯一": get(row, "答案是否唯一") or "否",
        "推理过程": get(row, "推理过程（推理过程不能放图片）"),
        "信源链接或标注图路径": "\n".join(filter(None, [get(row, "信源（文字）"), get(row, "信源（图片）")])),
        "是否需要验证结果": "是" if validation else "否",
        "answer(验证结果)": validation,
        "模型是否答错": "待验证" if not validation else "是",
        "初标是否完成": "是",
        "自检备注": get(row, "质检备注（文字）"),
    }


def has_format_hint(prompt: str) -> bool:
    return has_format_constraint(prompt)


def triage_action(result: dict[str, Any]) -> str:
    if result["blockers"] or result["conclusion"] in {"需修改", "不合格", "无法评分"}:
        return "筛出返修：存在阻断项或未达到基本合格，建议先返修后再复审。"
    return "放行到人工预审：机器人未发现需要筛除的硬伤。"


def human_review_focus(result: dict[str, Any]) -> str:
    points: list[str] = []
    points.extend(result["blockers"])
    points.extend(result["issues"])
    filtered = [point for point in points if point]
    if not filtered:
        return "无明显筛除项；人工审核员按正式口径复核即可。"
    return "；".join(filtered)


def markdown_report(results: list[dict[str, Any]], source_url: str, rows: str) -> str:
    counts: dict[str, int] = {}
    for result in results:
        counts[result["conclusion"]] = counts.get(result["conclusion"], 0) + 1
    lines = [
        "# 飞书云表新人训练评审报告",
        "",
        f"- Source: {source_url}",
        f"- Rows: {rows}",
        f"- Total rows: {len(results)}",
        f"- Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 批次概览",
        "",
    ]
    for key in ["合格", "基本合格", "需修改", "不合格", "无法评分"]:
        lines.append(f"- {key}: {counts.get(key, 0)}")
    lines.extend([
        "",
        "## 处理口径",
        "",
        "- 本步骤是机器人粗筛：主要筛除差样本、缺材料、格式明显不合格、答案不唯一等硬伤。",
        "- 合格/基本合格且无阻断项：放行到人工预审；报告只列人工审核员关注点，不默认给新人具体改稿建议。",
        "- 需修改/不合格/无法评分，或存在阻断项：筛出返修，再复审对应行。",
        "- smoke-test 或合成测试行：评语主要用于验证流程，不自动等同于正式训练返修要求。",
        "",
        "## 明细",
        "",
    ])
    for result in results:
        lines.extend([
            f"### {result['case_id']}",
            "",
            f"- 结论: {result['conclusion']}",
            f"- 总分: {result['score']}",
            f"- 阻断项: {'；'.join(result['blockers']) if result['blockers'] else '无明显阻断项'}",
            f"- 筛查动作: {triage_action(result)}",
            f"- 人工预审关注: {human_review_focus(result)}",
            f"- 规则依据: {'；'.join(result['evidence']) if result['evidence'] else '未检索到依据'}",
            "",
        ])
    return "\n".join(lines)


def write_back(url: str, sheet_id: str, results: list[dict[str, Any]]) -> None:
    if not results:
        return
    row_numbers = [int(str(result["case_id"]).replace("row-", "")) for result in results]
    start_row, end_row = min(row_numbers), max(row_numbers)
    cells = []
    by_row = {int(str(result["case_id"]).replace("row-", "")): result for result in results}
    for row_num in range(start_row, end_row + 1):
        result = by_row.get(row_num)
        if not result:
            cells.append([{}, {}, {}, {}])
            continue
        note_parts = [triage_action(result)]
        if result["blockers"]:
            note_parts.append("阻断项：" + "；".join(result["blockers"]))
        note_parts.append("人工预审关注：" + human_review_focus(result))
        note = "\n".join(note_parts)
        cells.append([
            {"value": result["conclusion"]},
            {},
            {},
            {"value": f"Codex预质检 {result['score']}分\n{note}"},
        ])
    payload = json.dumps([[cell for cell in row] for row in cells], ensure_ascii=False)
    run_lark_cli([
        "sheets",
        "+cells-set",
        "--url",
        url,
        "--sheet-id",
        sheet_id,
        "--range",
        f"W{start_row}:Z{end_row}",
        "--cells",
        "-",
        "--as",
        "user",
        "--format",
        "json",
    ], stdin=payload)


def main() -> int:
    args = parse_args()
    start_row, end_row = parse_rows(args.rows)
    rows = read_cloud_rows(args.url, args.sheet_id, start_row, end_row)
    if not args.no_float_images:
        attach_float_images(rows, read_float_images(args.url, args.sheet_id))
    mapped = [map_cloud_row(row) for row in rows]
    reviewer_args = SimpleNamespace(
        base_url=args.base_url,
        project_id=args.project_id,
        timeout=args.timeout,
        require_model_validation=args.require_model_validation,
    )
    results = [review_row(row, reviewer_args) for row in mapped]
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else DEFAULT_REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = out_dir / f"lark-training-review-{stamp}.md"
    json_path = out_dir / f"lark-training-review-{stamp}.json"
    report_path.write_text(markdown_report(results, args.url, args.rows), encoding="utf-8")
    json_path.write_text(json.dumps({"source": args.url, "rows": args.rows, "mapped_rows": mapped, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.write_back:
        write_back(args.url, args.sheet_id, results)
    print(f"report: {report_path}")
    print(f"json: {json_path}")
    print(f"write_back: {args.write_back}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

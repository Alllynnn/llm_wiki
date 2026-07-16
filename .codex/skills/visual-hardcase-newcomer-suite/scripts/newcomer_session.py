#!/usr/bin/env python3
"""Guided newcomer session helper for visual hardcase training."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def default_assignment_count() -> int:
    raw = os.environ.get("VISUAL_HARDCASE_ASSIGNMENT_COUNT", "5")
    try:
        count = int(raw)
    except ValueError:
        return 5
    return count if count > 0 else 5


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SESSION_DIR = Path.home() / "Downloads" / "visual-hardcase-training-sessions"
DEFAULT_HOMEWORK_URL = os.environ.get(
    "VISUAL_HARDCASE_HOMEWORK_URL",
    "https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl",
)
DEFAULT_HOMEWORK_SHEET_ID = os.environ.get("VISUAL_HARDCASE_HOMEWORK_SHEET_ID", "eL8Rfl")
DEFAULT_ASSIGNMENT_COUNT = default_assignment_count()
DEFAULT_WIKI_PUBLIC_URL = os.environ.get("LLM_WIKI_PUBLIC_URL", "https://wiki.muchenai.com")
DEFAULT_QC_API_URL = os.environ.get(
    "VISUAL_HARDCASE_QC_API_URL",
    "https://wiki.muchenai.com/api/v1/visual-hardcase/qc-jobs",
)
TRAINING_VIDEO_URL = "https://dcnkm9z3sogt.feishu.cn/minutes/obcnn7x2bffm45zu8co7pr9s"

RULE_DOCUMENT_LINKS = [
    {
        "title": "视觉理解-难题构造内部规则文档",
        "url": "https://shujufuwubu.feishu.cn/wiki/UW89wjZW0iWdkskxLsWcLTPEnJg",
        "purpose": "先看这个。它是正式规则来源，用来确认红线、字段、题型范围和质检口径。",
    },
    {
        "title": "v3题型作业步骤与构造思路 副本",
        "url": "https://shujufuwubu.feishu.cn/wiki/Qx1nw19a2iHc8qkunCqcXDAdnhf",
        "purpose": "第二个按题型查。用于找图、设计 prompt、写 answer 和处理格式约束。",
    },
    {
        "title": "构造bad case记录&复盘 副本",
        "url": "https://shujufuwubu.feishu.cn/wiki/TL0AwaFzaiUByrkGF2IcUwDIn4e",
        "purpose": "第三个看。它是反例和返工库，用来避开歧义、证据弱、答案不唯一等问题。",
    },
]

LEARNING_LINKS = [
    *RULE_DOCUMENT_LINKS,
    {
        "title": "新人会议培训视频（飞书妙记）",
        "url": TRAINING_VIDEO_URL,
        "purpose": "11:00-12:00 会议培训使用；错过直播或需要复习时打开这个链接。",
    },
]

TRIAL_WORK_NOTES = [
    "参与培训的小伙伴，在【试标作业表-新】末尾自行添加姓名进行内部试标作业。",
    "验证部分不用管也不用填，但题目不能太简单，一眼就能看出答案的也不行；内部试标题主要看构造思路和形式是否符合分类要求。",
    "注意细节：prompt 不能有歧义，answer 必须正确且唯一，并且要有格式限定。",
    "所有测试题完成后，“答案是否唯一”字段填“是”，等待被质检；有疑问可联系 @谭攀。",
]

DAY_ONE_SCHEDULE: list[dict[str, Any]] = [
    {
        "start": "10:00",
        "end": "10:10",
        "content": "项目介绍以及了解培训流程",
        "owner": "谭攀",
        "focus": True,
    },
    {
        "start": "10:10",
        "end": "11:00",
        "content": "学习规则文档",
        "owner": "",
        "focus": True,
        "links": RULE_DOCUMENT_LINKS,
    },
    {
        "start": "11:00",
        "end": "12:00",
        "content": "会议培训",
        "owner": "",
        "focus": True,
        "link": TRAINING_VIDEO_URL,
    },
    {
        "start": "12:00",
        "end": "13:00",
        "content": "午餐+休息",
        "owner": "-",
        "focus": False,
    },
    {
        "start": "13:00",
        "end": "15:00",
        "content": "完成5道试标题（分类任选，但必须为1道简单+4道复杂题）",
        "owner": "培训负责人：谭攀",
        "focus": True,
        "notes": TRIAL_WORK_NOTES,
    },
    {
        "start": "15:00",
        "end": "15:30",
        "content": "第一轮试标复盘会",
        "owner": "",
        "focus": False,
    },
    {
        "start": "15:30",
        "end": "16:10",
        "content": "返修（全体人员）",
        "owner": "",
        "focus": False,
    },
    {
        "start": "16:10",
        "end": "16:40",
        "content": "公布内部试标结果，并注册数据服务部账号，需要在信息收集表中填写对应信息",
        "owner": "",
        "focus": False,
    },
    {
        "start": "16:40",
        "end": "19:00",
        "content": "进入正式试标，正式试标作业培训",
        "owner": "",
        "focus": False,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run guided newcomer training session steps.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Create a newcomer session and print onboarding package.")
    start.add_argument("--name", help="Newcomer name. If omitted, prompt interactively.")
    start.add_argument("--session-dir", default=str(DEFAULT_SESSION_DIR), help="Directory for session JSON.")
    start.add_argument("--homework-url", default=DEFAULT_HOMEWORK_URL, help="Feishu homework sheet URL.")
    start.add_argument("--sheet-id", default=DEFAULT_HOMEWORK_SHEET_ID, help="Homework sheet id.")
    start.add_argument("--now", help="Override current time as HH:MM for deterministic schedule output.")
    start.add_argument(
        "--assignment-count",
        type=int,
        default=DEFAULT_ASSIGNMENT_COUNT,
        help="Default newcomer workload in questions/rows.",
    )

    complete = subparsers.add_parser(
        "complete",
        help="Record that the newcomer finished and submit row numbers to backend QC.",
    )
    complete.add_argument("--session", required=True, help="Session JSON path from start mode.")
    complete.add_argument("--rows", help="Completed cloud sheet row range, e.g. 946:950.")
    complete.add_argument("--note", help="Optional handoff note for the trainer.")
    complete.add_argument("--qc-api-url", default=DEFAULT_QC_API_URL, help="Backend QC job API URL.")
    complete.add_argument(
        "--no-submit-qc",
        dest="submit_qc",
        action="store_false",
        help="Only record local completion; do not submit rows to backend QC.",
    )
    complete.set_defaults(submit_qc=True)

    status = subparsers.add_parser("status", help="Print the current day-one training step.")
    status.add_argument("--now", help="Override current time as HH:MM for deterministic schedule output.")

    reminders = subparsers.add_parser("reminders", help="Print same-day active reminder plan as JSON.")
    reminders.add_argument("--name", required=True, help="Newcomer name for reminder prompts.")
    reminders.add_argument("--date", help="Target date as YYYY-MM-DD. Defaults to today.")
    reminders.add_argument("--now", help="Override current time as HH:MM for deterministic reminder filtering.")
    reminders.add_argument("--homework-url", default=DEFAULT_HOMEWORK_URL, help="Feishu homework sheet URL.")
    reminders.add_argument("--sheet-id", default=DEFAULT_HOMEWORK_SHEET_ID, help="Homework sheet id.")
    reminders.add_argument(
        "--assignment-count",
        type=int,
        default=DEFAULT_ASSIGNMENT_COUNT,
        help="Default newcomer workload in questions/rows.",
    )

    return parser.parse_args()


def ask_name(name: str | None) -> str:
    if name:
        return name.strip()
    entered = input("请输入新人姓名: ").strip()
    if not entered:
        raise SystemExit("新人姓名不能为空。")
    return entered


def safe_slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "newcomer"


def save_session(
    name: str,
    session_dir: Path,
    homework_url: str,
    sheet_id: str,
    assignment_count: int,
) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = session_dir / f"{stamp}-{safe_slug(name)}.json"
    payload: dict[str, Any] = {
        "name": name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "learning_links": LEARNING_LINKS,
        "training_video": {
            "title": "新人会议培训视频（飞书妙记）",
            "url": TRAINING_VIDEO_URL,
        },
        "day_one_schedule": DAY_ONE_SCHEDULE,
        "homework_url": homework_url,
        "sheet_id": sheet_id,
        "assignment_count": assignment_count,
        "assignment_policy": "shared_sheet_self_added_rows",
        "newcomer_flow_policy": "no_sheet_read_submit_rows_to_backend_qc",
        "status": "learning",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def clock_to_minutes(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("时间必须是 HH:MM 格式。")
    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("时间必须在 00:00 到 23:59 之间。")
    return hour * 60 + minute


def active_minute(now: str | None) -> int:
    if now:
        return clock_to_minutes(now)
    current = datetime.now()
    return current.hour * 60 + current.minute


def format_minute(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def current_schedule_slot(minute: int) -> dict[str, Any] | None:
    for item in DAY_ONE_SCHEDULE:
        if clock_to_minutes(item["start"]) <= minute < clock_to_minutes(item["end"]):
            return item
    return None


def next_schedule_slot(minute: int) -> dict[str, Any] | None:
    for item in DAY_ONE_SCHEDULE:
        if minute < clock_to_minutes(item["start"]):
            return item
    return None


def schedule_item_label(item: dict[str, Any]) -> str:
    return f"{item['start']}-{item['end']} {item['content']}"


def next_item_after(item: dict[str, Any]) -> dict[str, Any] | None:
    for index, candidate in enumerate(DAY_ONE_SCHEDULE):
        if candidate is item:
            return DAY_ONE_SCHEDULE[index + 1] if index + 1 < len(DAY_ONE_SCHEDULE) else None
    for index, candidate in enumerate(DAY_ONE_SCHEDULE):
        if candidate["start"] == item["start"] and candidate["end"] == item["end"]:
            return DAY_ONE_SCHEDULE[index + 1] if index + 1 < len(DAY_ONE_SCHEDULE) else None
    return None


def next_arrangement_text(item: dict[str, Any]) -> str:
    next_item = next_item_after(item)
    if next_item:
        return f"完成当前阶段后，下一环节为：{schedule_item_label(next_item)}"
    return "完成当前阶段后，今日第一天培训流程结束"


def format_current_training_status(now: str | None = None) -> str:
    minute = active_minute(now)
    current_time = format_minute(minute)
    slot = current_schedule_slot(minute)
    if slot:
        lines = [
            f"当前时间提醒：现在是 {current_time}，当前阶段：{slot['content']}（{slot['start']}-{slot['end']}）。"
        ]
        owner = slot.get("owner", "")
        if owner and owner != "-":
            lines.append(f"负责人：{owner}。")
        content = slot["content"]
        if content == "学习规则文档":
            lines.append("当前动作：按顺序阅读内部规则、v3 题型作业步骤、bad case 复盘；有问题直接问 Codex。")
            lines.append(f"规则文档：{format_markdown_links(RULE_DOCUMENT_LINKS)}")
        elif content == "会议培训":
            lines.append(f"当前动作：参加会议培训；需要复习或错过直播时打开飞书妙记：{TRAINING_VIDEO_URL}")
        elif content.startswith("完成5道"):
            lines.append("当前动作：完成 5 道测试题，分类任选，但必须为 1 道简单 + 4 道复杂题。")
            lines.append("作业提醒：验证部分不用填；prompt 无歧义，answer 正确唯一并有格式限定；“答案是否唯一”填“是”。")
        elif content == "午餐+休息":
            lines.append("当前动作：休息。13:00 回来进入 5 道测试题构造。")
        elif slot.get("focus"):
            lines.append("当前动作：按培训负责人安排推进；Codex 可继续答疑和提示下一步。")
        else:
            lines.append("当前动作：按培训负责人安排推进；10:00-15:00 的 Codex 重点陪跑阶段已结束或暂未开始。")
        lines.append(f"{next_arrangement_text(slot)}。")
        return "\n".join(lines)

    next_slot = next_schedule_slot(minute)
    if next_slot:
        return (
            f"当前时间提醒：现在是 {current_time}，培训还未进入下一阶段。"
            f"下一环节为：{schedule_item_label(next_slot)}。"
        )
    return "当前时间提醒：今日第一天培训流程已结束；如果 5 道测试题已经完成，请提交 5 行行号触发后台 QC。"


def reminder_rrule(target_date: str, time_text: str) -> str:
    date_token = target_date.replace("-", "")
    time_token = time_text.replace(":", "")
    return f"DTSTART;TZID=Asia/Shanghai:{date_token}T{time_token}00\nRRULE:FREQ=DAILY;COUNT=1"


def reminder_prompt_for(
    name: str,
    item: dict[str, Any],
    homework_url: str,
    sheet_id: str,
    assignment_count: int,
) -> str:
    content = item["content"]
    lines = [
        "这是 visual-understanding-hardcase 新人培训主动提醒。",
        f"请提醒 {name}：现在进入 {schedule_item_label(item)}。",
    ]
    if content == "学习规则文档":
        lines.append("当前动作：按顺序阅读内部规则、v3 题型作业步骤、bad case 复盘；有问题直接问 Codex。")
        lines.append(f"规则文档：{format_markdown_links(RULE_DOCUMENT_LINKS)}")
    elif content == "会议培训":
        lines.append(f"当前动作：参加会议培训；需要复习或错过直播时打开飞书妙记：{TRAINING_VIDEO_URL}")
    elif content == "午餐+休息":
        lines.append("当前动作：午餐和休息。13:00 回来进入 5 道测试题构造。")
    elif content.startswith("完成5道"):
        lines.append(f"当前动作：在作业表完成 {assignment_count} 道测试题，必须包含 1 道简单题 + 4 道复杂题。")
        lines.append(f"作业表：{homework_url}；sheet_id：{sheet_id}")
        lines.append("做题前提醒：验证部分不用填；prompt 无歧义，answer 正确唯一并有格式限定；完成后“答案是否唯一”填“是”。")
    elif content == "第一轮试标复盘会":
        lines.append("当前动作：参加第一轮试标复盘会；如果 5 道测试题已完成，可以回到 Codex 提交 5 行行号触发后台 QC。")
    elif content.startswith("返修"):
        lines.append("当前动作：按复盘意见返修；有规则疑问可以继续问 Codex，Codex 会先检索 LLM Wiki。")
    elif content.startswith("公布内部试标结果"):
        lines.append("当前动作：关注内部试标结果，并按负责人安排注册数据服务部账号、填写信息收集表。")
    elif content.startswith("进入正式试标"):
        lines.append("当前动作：进入正式试标培训，按正式作业口径推进。")
    else:
        owner = item.get("owner", "")
        if owner and owner != "-":
            lines.append(f"负责人：{owner}。")
        lines.append("当前动作：按培训负责人安排推进。")
    lines.append(f"{next_arrangement_text(item)}。")
    lines.append("边界：不要读取云表、不要本地预质检、不要评分；新人提交完成行号时再调用 complete 流程。")
    return "\n".join(lines)


def flow_end_prompt(name: str) -> str:
    return (
        "这是 visual-understanding-hardcase 新人培训主动提醒。\n"
        f"请提醒 {name}：今日第一天培训流程已结束；如果 5 道测试题已经完成，请回到 Codex 提交 5 行行号触发后台 QC。"
    )


def reminder_plan(
    name: str,
    target_date: str | None = None,
    now: str | None = None,
    homework_url: str = DEFAULT_HOMEWORK_URL,
    sheet_id: str = DEFAULT_HOMEWORK_SHEET_ID,
    assignment_count: int = DEFAULT_ASSIGNMENT_COUNT,
) -> dict[str, Any]:
    current_minute = active_minute(now)
    date_value = target_date or datetime.now().date().isoformat()
    reminders: list[dict[str, str]] = []
    for item in DAY_ONE_SCHEDULE:
        if clock_to_minutes(item["start"]) <= current_minute:
            continue
        label = schedule_item_label(item)
        reminders.append({
            "name": f"视觉理解新人培训提醒：{item['start']} {item['content']}",
            "time": f"{date_value} {item['start']}",
            "rrule": reminder_rrule(date_value, item["start"]),
            "prompt": reminder_prompt_for(name, item, homework_url, sheet_id, assignment_count),
            "stage": label,
        })
    end_time = DAY_ONE_SCHEDULE[-1]["end"]
    if current_minute < clock_to_minutes(end_time):
        reminders.append({
            "name": f"视觉理解新人培训提醒：{end_time} 今日流程结束",
            "time": f"{date_value} {end_time}",
            "rrule": reminder_rrule(date_value, end_time),
            "prompt": flow_end_prompt(name),
            "stage": f"{end_time} 今日第一天培训流程结束",
        })
    return {
        "name": name,
        "date": date_value,
        "timezone": "Asia/Shanghai",
        "kind": "heartbeat",
        "destination": "thread",
        "reminders": reminders,
    }


def format_markdown_links(items: list[dict[str, str]]) -> str:
    return " / ".join(f"[{item['title']}]({item['url']})" for item in items)


def format_day_one_schedule(now: str | None = None) -> str:
    lines = [
        "## 入项前第一天培训表",
        "",
        "| 时间 | 内容 | 注意事项/培训负责人 |",
        "|---|---|---|",
    ]
    for item in DAY_ONE_SCHEDULE:
        owner = item.get("owner", "")
        note = owner if owner else ""
        if item.get("link"):
            note = f"{note}；培训视频：{item['link']}" if note else f"培训视频：{item['link']}"
        if item.get("links"):
            links = format_markdown_links(item["links"])
            note = f"{note}；规则文档：{links}" if note else f"规则文档：{links}"
        if item.get("notes"):
            note = f"{note}；详见下方注意事项" if note else "详见下方注意事项"
        next_text = next_arrangement_text(item)
        note = f"{note}；{next_text}" if note else next_text
        lines.append(f"| {item['start']}-{item['end']} | {item['content']} | {note} |")
    lines.extend([
        "",
        "13:00-15:00 测试题注意事项：",
    ])
    lines.extend(f"- {note}" for note in TRIAL_WORK_NOTES)
    lines.extend([
        "",
        "Codex 重点陪跑时段：10:00-15:00。每次你回到 Codex 继续流程时，我会按当前时间提示当前动作和下一环节。",
        "",
        "## 当前时间推进",
        "",
        format_current_training_status(now),
    ])
    return "\n".join(lines)


def print_onboarding(
    name: str,
    session_path: Path,
    homework_url: str,
    sheet_id: str,
    assignment_count: int,
    now: str | None = None,
) -> None:
    print("# 视觉理解难题构造新人训练")
    print()
    print(f"新人姓名：{name}")
    print()
    print(format_day_one_schedule(now))
    print()
    print("## 第一步：学习资料")
    print()
    for item in LEARNING_LINKS:
        print(f"- [{item['title']}]({item['url']})")
        print(f"  - 用途：{item['purpose']}")
    print()
    print("阅读时可以直接问 Codex：题型规则、bad case 原因、prompt/answer 格式、质检口径都可以问。")
    print(f"项目知识库公网入口：{DEFAULT_WIKI_PUBLIC_URL}")
    print("Codex 回答 FAQ 时会优先通过已配置的 LLM Wiki API 取证；如果 API token 未配置，会明确说明“知识库检索暂不可用”，不会把本机调试地址当作新人操作链接。")
    print("读完第 1 步后，回复“继续第二步”，或者直接提出你的规则/题型问题。")
    print()
    print("## 第二步：填写新人作业")
    print()
    print("- 作业方式：使用统一共享训练云表，不会默认新建一个以新人姓名命名的表。")
    print(f"- 默认题量：{assignment_count} 题，对应 {assignment_count} 行。")
    print(f"- 作业表：{homework_url}")
    print(f"- sheet_id：{sheet_id}")
    print("- 在【试标作业表-新】末尾自行添加姓名并填写 5 行测试题；不要改动别人已有内容。")
    print()
    print("### 做题前小提醒")
    print()
    print("- 验证部分不用填；内部试标题主要看构造思路和形式是否符合分类要求。")
    print("- 题目不能太简单，不能是一眼就能看出答案的题。")
    print("- prompt 不能有歧义，answer 必须正确且唯一，并且要写清格式限定。")
    print("- 所有测试题完成后，“答案是否唯一”字段填“是”，等待被质检即可。")
    print()
    print("- 填写完成后，回到 Codex 说“我做完了”，并带上你实际填写的 5 行范围，例如：我做完了，946:950。")
    print("- Codex 会把新人姓名和完成行号提交给后台 QC API；后台负责读取云表并触发预质检。")
    print()
    print("## 第三步：完成后交接")
    print()
    print("完成后回到 Codex 提交 5 行行号；系统会提交后台 QC API。")
    print("后台 QC 完成后，结果会写入云表的“预质检”字段。")
    print()
    print("## 主动提醒")
    print()
    print("支持后台提醒的 Codex 客户端会为今天剩余培训节点创建主动提醒；如果客户端不支持后台提醒，每次你回到 Codex 时仍会按当前时间提示当前阶段和下一环节。")
    print()
    print(f"session_json: {session_path}")


def token_candidates(session_path: Path) -> list[str]:
    session_dir = session_path.resolve().parents
    skill_dir = Path(__file__).resolve().parents[1]
    return [
        os.environ.get("VISUAL_HARDCASE_QC_API_TOKEN", ""),
        os.environ.get("LLM_WIKI_API_TOKEN", ""),
        (skill_dir / "config" / "llm_wiki_token.txt").read_text(encoding="utf-8").strip()
        if (skill_dir / "config" / "llm_wiki_token.txt").exists()
        else "",
        *[
            (parent / "config" / "llm_wiki_token.txt").read_text(encoding="utf-8").strip()
            for parent in session_dir
            if (parent / "config" / "llm_wiki_token.txt").exists()
        ],
    ]


def qc_api_token(session_path: Path) -> str:
    for token in token_candidates(session_path):
        token = token.strip()
        if token:
            return token
    return ""


def expand_rows(rows: str) -> list[int]:
    value = rows.strip().replace("：", ":").replace("，", ",")
    if not value:
        return []
    if ":" in value or "-" in value:
        sep = ":" if ":" in value else "-"
        start_text, end_text = value.split(sep, 1)
        start = int(start_text.strip())
        end = int(end_text.strip())
        if end < start:
            raise ValueError("结束行号不能小于开始行号。")
        return list(range(start, end + 1))
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def submit_qc_job(session: dict[str, Any], session_path: Path, rows: str, qc_api_url: str) -> dict[str, Any]:
    row_numbers = validate_completed_rows(session, rows)
    token = qc_api_token(session_path)
    if not token:
        raise RuntimeError("未配置 QC API token，无法提交后台质检。")
    payload = {
        "newcomerName": session.get("name", ""),
        "rows": rows,
        "rowNumbers": row_numbers,
        "homeworkUrl": session.get("homework_url", DEFAULT_HOMEWORK_URL),
        "sheetId": session.get("sheet_id", DEFAULT_HOMEWORK_SHEET_ID),
        "sessionId": session_path.stem,
        "submittedAt": datetime.now().isoformat(timespec="seconds"),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        qc_api_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            response = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"QC API HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"QC API 连接失败：{exc.reason}") from exc
    if not response.get("ok"):
        raise RuntimeError(f"QC API 返回失败：{json.dumps(response, ensure_ascii=False)[:500]}")
    return response


def validate_completed_rows(session: dict[str, Any], rows: str | None) -> list[int]:
    if not rows:
        raise ValueError("缺少完成行号，无法提交后台 QC。")
    row_numbers = expand_rows(rows)
    expected = int(session.get("assignment_count") or DEFAULT_ASSIGNMENT_COUNT)
    if len(row_numbers) != expected:
        raise ValueError(f"完成行号必须正好是 {expected} 行；当前收到 {len(row_numbers)} 行。")
    return row_numbers


def mark_complete(
    session_path: Path,
    rows: str | None,
    note: str | None,
    submit_qc: bool,
    qc_api_url: str,
) -> int:
    session = json.loads(session_path.read_text(encoding="utf-8"))
    session["status"] = "completed_pending_backend_qc"
    session["completed_at"] = datetime.now().isoformat(timespec="seconds")
    if rows:
        session["completed_rows"] = rows
    if note:
        session["handoff_note"] = note
    qc_submission: dict[str, Any] | None = None
    qc_error = ""
    if rows:
        try:
            validate_completed_rows(session, rows)
        except ValueError as exc:
            qc_error = str(exc)
            session["status"] = "completion_row_validation_failed"
    if not submit_qc:
        if not qc_error:
            session["status"] = "completed_without_qc_submit"
    elif submit_qc:
        if qc_error:
            session["qc_submission"] = {
                "ok": False,
                "error": qc_error,
                "apiUrl": qc_api_url,
                "attemptedAt": datetime.now().isoformat(timespec="seconds"),
            }
        else:
            try:
                qc_submission = submit_qc_job(session, session_path, rows, qc_api_url)
                session["status"] = "submitted_to_backend_qc"
                session["qc_submission"] = qc_submission
            except Exception as exc:  # noqa: BLE001 - CLI should preserve the local completion record.
                qc_error = str(exc)
                session["status"] = "backend_qc_submit_failed"
                session["qc_submission"] = {
                    "ok": False,
                    "error": qc_error,
                    "apiUrl": qc_api_url,
                    "attemptedAt": datetime.now().isoformat(timespec="seconds"),
                }
    session_path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    print("# 新人作业完成记录")
    print()
    print(f"新人姓名：{session.get('name', '')}")
    print(f"作业表：{session.get('homework_url', '')}")
    print(f"sheet_id：{session.get('sheet_id', '')}")
    if rows:
        print(f"完成行号：{rows}")
    if note:
        print(f"备注：{note}")
    print()
    if qc_submission:
        print(f"后台 QC 已提交：job_id={qc_submission.get('jobId', '')}")
        print("已记录完成；后续预质检结果会写入云表的“预质检”字段。")
    elif qc_error:
        print(f"后台 QC 未提交：{qc_error}")
        print("请检查完成行号或后台 API 配置后重新提交；行号应为你实际填写的 5 行范围，例如：946:950。")
    elif submit_qc:
        print(f"后台 QC 提交失败：{qc_error}")
        print("已记录完成；请检查 token/API 配置后重试提交。")
    else:
        print("已记录完成；本次按 --no-submit-qc 跳过后台 QC 提交。")
    print()
    print(f"session_json: {session_path}")
    return 1 if qc_error else 0


def main() -> int:
    args = parse_args()
    if args.command == "start":
        name = ask_name(args.name)
        assignment_count = max(1, args.assignment_count)
        session_path = save_session(
            name,
            Path(args.session_dir).expanduser(),
            args.homework_url,
            args.sheet_id,
            assignment_count,
        )
        print_onboarding(name, session_path, args.homework_url, args.sheet_id, assignment_count, args.now)
        return 0
    if args.command == "status":
        print(format_day_one_schedule(args.now))
        return 0
    if args.command == "reminders":
        print(json.dumps(
            reminder_plan(
                args.name,
                args.date,
                args.now,
                args.homework_url,
                args.sheet_id,
                max(1, args.assignment_count),
            ),
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    if args.command == "complete":
        return mark_complete(
            Path(args.session).expanduser(),
            args.rows,
            args.note,
            args.submit_qc,
            args.qc_api_url,
        )
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

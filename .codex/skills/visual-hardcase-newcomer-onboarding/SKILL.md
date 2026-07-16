---
name: visual-hardcase-newcomer-onboarding
description: Use when onboarding newcomers for visual-understanding-hardcase, sending learning links, guiding shared Feishu sheet homework, answering guided FAQ, or recording human handoff completion.
---

# Visual Hardcase Newcomer Onboarding

## Core Rule

This skill is for newcomers. It sends learning materials, guides shared-sheet homework, routes questions to LLM Wiki evidence, records completion, and submits completed row numbers to the backend QC API.

It must not read Feishu cloud-sheet rows, run local pre-QC, score submissions, rewrite answers, or write back to any sheet. It may submit the newcomer's completed row numbers to the configured backend QC API. If a trainer asks for direct review or pre-QC in the current Codex session, switch to `visual-hardcase-pre-qc`.

For the exact newcomer flow, read `references/onboarding-flow.md`.

## LLM Wiki Access

User-facing Wiki entry: `https://wiki.muchenai.com`.

For any FAQ, rule, task-type, bad-case, prompt/answer format, or template question, retrieve LLM Wiki evidence before answering. Do not rely on conversation memory as the source of truth.

Defaults:

```bash
LLM_WIKI_API_BASE_URL=https://wiki.muchenai.com
LLM_WIKI_API_TOKEN=<optional-env-override>
LLM_WIKI_PROJECT_ID=7ad8995a9c34304f
```

The distributed newcomer package includes `config/llm_wiki_token.txt`. Scripts use environment variable token first, then fall back to this file. Never print or paste the token value.

If search is unavailable, say:

```text
知识库检索暂时不可用；你可以先打开 https://wiki.muchenai.com 查看资料。管理员配置 LLM_WIKI_API_BASE_URL 和 LLM_WIKI_API_TOKEN 后，我会自动从知识库取证。
```

## Activation Behavior

When a newcomer opens, installs, loads, or asks to use this skill, treat it as `guided-start`. Do not just summarize this file.

First response must:

1. Say you will guide the newcomer step by step.
2. Show the "入项前第一天培训表" first, including the 10:00-19:00 schedule and current time-based reminder.
   - The `10:10-11:00 学习规则文档` row must include the three rule-document links.
   - The `11:00-12:00 会议培训` row must include the Feishu minutes video link.
   - Each schedule row and current-stage reminder must include the next arrangement wording: `完成当前阶段后，下一环节为：...`.
3. Show four modules:
   - `学习资料`: read the required rule, task-step, and bad-case links.
   - `作业填写`: open the shared cloud sheet, add the newcomer's own rows at the end, and complete 5 test questions.
   - `规则答疑`: ask FAQ/rule/bad-case questions; answers use LLM Wiki evidence.
   - `完成交接`: record completion and hand off to trainer/human review.
4. Start with the learning package.
5. Ask for exactly one next input: the newcomer's name, unless already provided.

The 11:00-12:00 meeting training video is:

```text
https://dcnkm9z3sogt.feishu.cn/minutes/obcnn7x2bffm45zu8co7pr9s
```

The skill focuses on the 10:00-15:00 onboarding window while still showing the full 10:00-19:00 day-one schedule. Every time the newcomer returns to Codex, use the current local time to state the current stage, next stage, and immediate action.

## Active Reminder Behavior

After the newcomer's name is known and `start` succeeds, create active same-day reminders for the remaining training checkpoints.

1. Generate the reminder plan:

```bash
python scripts/newcomer_session.py reminders --name "<新人姓名>"
```

2. If the Codex app `automation_update` tool is available, create one `heartbeat` reminder in the current thread for each item in the returned `reminders[]` list:
   - `name`: use the item `name`
   - `rrule`: use the item `rrule`
   - `prompt`: use the item `prompt`
   - `destination`: `thread`
   - `status`: `ACTIVE`

3. Do not show raw RRULE strings to the newcomer. After successful creation, say that active reminders have been set for today's remaining checkpoints.
4. If the app does not expose background reminder tools, say: `当前 Codex 客户端暂不支持后台主动提醒；我会在你每次回到对话时按当前时间提示当前阶段和下一环节。`
5. Never create reminders for past checkpoints; the `reminders` command already filters them by current local time.

Use:

```bash
python scripts/newcomer_session.py start --name "<新人姓名>"
```

To print the day-one schedule and current stage without creating a new session:

```bash
python scripts/newcomer_session.py status
```

To generate same-day active reminder jobs after the name is known:

```bash
python scripts/newcomer_session.py reminders --name "<新人姓名>"
```

When the newcomer says the work is done, only record completion:

```bash
python scripts/newcomer_session.py complete --session "<session.json>" --rows "<start:end>"
```

The completion command updates local session JSON, validates that the completed rows match the expected 5-row workload, and submits the row numbers to the backend QC API. It must not read the cloud sheet locally.

## Newcomer Boundaries

Do not do any of the following in this skill:

- Read the newcomer cloud sheet.
- Run `review_lark_sheet.py` or `review_training_workbook.py`.
- Score, grade, screen out, or rewrite the newcomer's work.
- Write back to Feishu.

Use this handoff wording when the newcomer finishes:

```text
已记录你完成新人作业，并已把完成行号提交给后台 QC。后续预质检结果会写入云表的“预质检”字段。
```

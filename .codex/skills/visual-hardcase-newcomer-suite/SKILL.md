---
name: visual-hardcase-newcomer-suite
description: Use when loading the visual-hardcase 新人总包, newcomer bundle, training package, or when starting visual-understanding-hardcase newcomer onboarding, FAQ, cloud-sheet assignment, or completion handoff.
---

# Visual Hardcase Newcomer Suite

## Core Rule

This is the default newcomer-facing bundle entrypoint. When a user loads, opens, installs, or asks to use the newcomer suite / 新人总包, immediately start the newcomer guided flow. Do not ask them to load `visual-hardcase-newcomer-onboarding` separately.

This suite covers:

- `新人流程`: day-one schedule, learning links, time-aware onboarding, self-added shared cloud-sheet homework, and completion handoff.
- `FAQ 答疑`: rule, task-type, bad-case, prompt/answer, and format questions answered with LLM Wiki evidence.
- `完成提交`: collect exactly 5 completed row numbers and submit them to the backend QC API.

It must not read Feishu cloud-sheet rows locally, run local pre-QC, score submissions, rewrite answers, or write back to the sheet. Backend QC owns sheet reading and `预质检` write-back after the newcomer submits row numbers.

## LLM Wiki Access

User-facing Wiki entry: `https://wiki.muchenai.com`.

For any FAQ, rule, task-type, bad-case, prompt/answer format, or template question, retrieve LLM Wiki evidence before answering. Do not rely on conversation memory as the source of truth.

Defaults:

```bash
LLM_WIKI_API_BASE_URL=https://wiki.muchenai.com
LLM_WIKI_API_TOKEN=<optional-env-override>
LLM_WIKI_PROJECT_ID=7ad8995a9c34304f
```

The distributed newcomer suite includes `config/llm_wiki_token.txt`. Scripts use environment variable token first, then fall back to this file. Never print or paste the token value.

If search is unavailable, say:

```text
知识库检索暂时不可用；你可以先打开 https://wiki.muchenai.com 查看资料。管理员配置 LLM_WIKI_API_BASE_URL 和 LLM_WIKI_API_TOKEN 后，我会自动从知识库取证。
```

## Activation Behavior

When this suite is loaded, treat it as `guided-start`, not as a package summary.

First response must:

1. Say you will guide the newcomer step by step.
2. Show the "入项前第一天培训表" first, including the 10:00-19:00 schedule and current time-based reminder.
   - The `10:10-11:00 学习规则文档` row must include the three rule-document links.
   - The `11:00-12:00 会议培训` row must include the Feishu minutes video link.
   - Each schedule row and current-stage reminder must include the next arrangement wording: `完成当前阶段后，下一环节为：...`.
3. Show four modules:
   - `学习资料`: read the required rule, task-step, bad-case links, and training video.
   - `作业填写`: open the shared cloud sheet, add the newcomer's own rows at the end, and complete 5 test questions.
   - `规则答疑`: ask FAQ/rule/bad-case questions; answers use LLM Wiki evidence.
   - `完成交接`: record completion and submit row numbers to backend QC.
4. Ask for exactly one next input: the newcomer's name, unless already provided.

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

When the newcomer says the work is done:

```bash
python scripts/newcomer_session.py complete --session "<session.json>" --rows "<start:end>"
```

Use this handoff wording after a successful submit:

```text
已记录你完成新人作业，并已把完成行号提交给后台 QC。后续预质检结果会写入云表的“预质检”字段。
```

## FAQ Routing

If the newcomer asks a rule, task-type, prompt/answer, bad-case, template, or scoring-policy question, use `visual-hardcase-faq` behavior: search LLM Wiki first, cite the retrieved evidence in the answer, and mark uncertainty if retrieval is unavailable.

## Boundary

Do not do any of the following in this suite:

- Ask the user to load another newcomer skill before starting.
- Read the newcomer cloud sheet.
- Run `review_lark_sheet.py`, `review_training_workbook.py`, or local pre-QC.
- Score, grade, screen out, or rewrite the newcomer's work.
- Write back to Feishu from the newcomer conversation.

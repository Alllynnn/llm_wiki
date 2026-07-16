---
name: visual-hardcase-training-review
description: Use when running newcomer onboarding, learning-material delivery, Feishu cloud-sheet assignment guidance, guided FAQ, and human handoff for visual-understanding-hardcase.
---

# Visual Hardcase Training Review

## Core Rule

The newcomer workflow is guided onboarding, shared cloud-sheet assignment, and backend QC submission. It must not read Feishu cloud-sheet rows locally, run local pre-QC, score submissions, rewrite answers, or write back to the sheet.

When a newcomer reports completion, submit only the newcomer name and completed row numbers to the configured backend QC API. The backend service owns sheet reading, pre-QC, and writing the `预质检` field. If a trainer asks for direct review or manual machine review in the current Codex session, switch to `visual-hardcase-pre-qc`.

For suite distribution, role split, and newcomer operating instructions, read `references/skill-distribution.md`.

## LLM Wiki Access Rule

User-facing LLM Wiki entry: `https://wiki.muchenai.com`.

This rule is part of the distributable skill, not only a local project `AGENTS.md` rule. For any visual-understanding-hardcase FAQ, rule, task-type, bad-case, or template answer, retrieve LLM Wiki evidence first. Do not rely on long conversation context or memory as the source of truth.

The skill's knowledge search uses the LLM Wiki project API. Default API base URL is `https://wiki.muchenai.com`; scripts call `/api/v1/projects/{id}/search`. Public API access requires an API token configured in `LLM_WIKI_API_TOKEN`; optional overrides are:

```bash
LLM_WIKI_API_BASE_URL=https://wiki.muchenai.com
LLM_WIKI_API_TOKEN=<configured-by-admin>
LLM_WIKI_PROJECT_ID=7ad8995a9c34304f
```

Do not show loopback/debug URLs such as `127.0.0.1:19828` to newcomers as an action link. If knowledge search is unavailable, say:

```text
知识库检索暂时不可用；你可以先打开 https://wiki.muchenai.com 查看资料。管理员配置 LLM_WIKI_API_BASE_URL 和 LLM_WIKI_API_TOKEN 后，我会自动从知识库取证。
```

## Activation Behavior

When the user says they loaded, opened, installed, or wants to use this skill, do **not** stop at "skill loaded" or a summary of this file. Treat that as `guided-start` and begin an interactive onboarding session.

First response must:

1. Say that you will guide the newcomer step by step.
2. Show the "入项前第一天培训表" first, including the 10:00-19:00 schedule and the current time-based reminder.
   - The `10:10-11:00 学习规则文档` row must include the three rule-document links.
   - The `11:00-12:00 会议培训` row must include the Feishu minutes video link.
   - Each schedule row and current-stage reminder must include the next arrangement wording: `完成当前阶段后，下一环节为：...`.
3. Show the available modules in plain language:
   - `学习资料`: read the required rule, task-step, and bad-case links.
   - `作业填写`: open the cloud sheet, add the newcomer's own rows at the end, and complete 5 test questions.
   - `规则答疑`: answer task-type, FAQ, and bad-case questions via `visual-hardcase-faq`.
   - `完成交接`: record that the newcomer finished and send the work to the trainer/human reviewer.
4. State the current step: start with the learning package and collect the newcomer name.
5. Ask for exactly one next input: the newcomer's name, unless the name is already provided.

The 11:00-12:00 meeting training video is:

```text
https://dcnkm9z3sogt.feishu.cn/minutes/obcnn7x2bffm45zu8co7pr9s
```

The skill focuses on the 10:00-15:00 onboarding window. Every time the newcomer returns to Codex, use the current local time to state the current stage, next stage, and immediate action. If the Codex client supports background reminders and the newcomer asks for them, create reminders for the same-day checkpoints; otherwise provide time-aware status when the conversation continues.

Use this starter shape instead of a generic summary:

```text
OK，我会一步一步带你完成视觉难题构造新人训练。

我们先分 4 个模块：
1. 学习资料：按顺序读内部规则、题型步骤和 bad case 复盘。
2. 作业填写：到统一训练云表末尾自行添加姓名并填写 5 行训练题。
3. 规则答疑：阅读或做题时遇到题型、规则、bad case 问题可以直接问我；我会先查项目知识库。
4. 完成交接：你完成后告诉我行号，我会提交给后台触发预质检。

我会先发入项前第一天培训表，并按当前时间提示你现在该做什么。

第 1 步我先给你学习资料。请告诉我你的新人姓名。
```

If the user already provided a name, run:

```bash
python scripts/newcomer_session.py start --name "<新人姓名>"
```

Then paste the generated learning package, assignment sheet, and session path into the reply. If the user is the trainer rather than the newcomer, still show the modules first, then ask whether they want `guided-start` for onboarding or want to switch to `visual-hardcase-pre-qc` for separate review.

To print the day-one schedule and current stage without creating a new session:

```bash
python scripts/newcomer_session.py status
```

## Guided Step Contract

The onboarding must behave like a tutor, not a static manual. At the end of each step:

1. State what the newcomer has just received or finished.
2. State the next step in one sentence.
3. Ask for exactly one next action, such as reading questions, assignment confirmation, or completion notice.

After sending step 1 learning materials, explicitly say:

```text
看完任何一段都有问题都可以直接问我。这个项目的知识库入口是 https://wiki.muchenai.com；我会优先按 visual-hardcase FAQ、规则文档和 bad case 记录取证回答。不确定或 API 未配置的地方我会标出来，不会硬编。

你读完第 1 步后，回复“继续第二步”，或者直接问你的规则/题型问题。
```

For step 2 assignments, do not imply that a new Feishu sheet will be created for each newcomer, and do not say that the trainer must assign row numbers before the newcomer starts. The default flow uses the shared training sheet: the newcomer adds their name and 5 test-question rows at the end of `试标作业表-新`, without changing other people's existing rows. Create or copy a newcomer-specific sheet only when the trainer explicitly asks for that.

## Newcomer QC Submission Policy

Newcomer onboarding stops after the newcomer receives materials, fills their own 5 rows at the end of the shared sheet, reports the actual completed row range, and Codex submits the completed row numbers to the backend QC API.

Do not do any of the following inside this skill's newcomer flow:

- Read Feishu cloud-sheet rows.
- Run `review_lark_sheet.py` or `review_training_workbook.py`.
- Score, grade, screen out, or rewrite the newcomer's work.
- Write back to the cloud sheet.

Use this handoff wording when the newcomer says they are done:

```text
已记录你完成新人作业，并已把完成行号提交给后台 QC。后续预质检结果会写入云表的“预质检”字段。
```

## Learning Package Guidance

When sending the learning links, explain what each document is for and recommend this reading order:

1. **视觉理解-难题构造内部规则文档**: read first. Treat it as the rule source. Use it to confirm core annotation fields, common easy mistakes, allowed v3 task types, stopped historical task types, rule updates, and model-validation workflow.
2. **v3题型作业步骤与构造思路 副本**: read second, task-type by task-type. Use it as the operational manual for finding images, designing prompts, writing answers, and applying answer-format constraints for the specific task type the newcomer is constructing.
3. **构造bad case记录&复盘 副本**: read last. Treat it as the anti-pattern and rework library. Use it after the rules are understood, so the newcomer can see why cases are rejected and how to avoid ambiguity, weak image evidence, prompt loopholes, and non-unique answers.

Use this concise explanation when the newcomer asks how to read the package:

```text
建议先看内部规则确认红线，然后按题型查 v3 作业步骤，最后看 bad case 复盘避坑。

实际做题时：
- 先用内部规则确认准入范围和硬性红线；
- 选题型时查 v3 题型作业步骤；
- 不确定是否允许时查内部规则文档；
- 被退回或想避坑时查 bad case 复盘。
```

## Newcomer Guided Flow

Use this flow when a newcomer installs or opens this skill.

1. Send the learning package:
   - 视觉理解-难题构造内部规则文档: `https://shujufuwubu.feishu.cn/wiki/UW89wjZW0iWdkskxLsWcLTPEnJg`
   - v3题型作业步骤与构造思路 副本: `https://shujufuwubu.feishu.cn/wiki/Qx1nw19a2iHc8qkunCqcXDAdnhf`
   - 构造bad case记录&复盘 副本: `https://shujufuwubu.feishu.cn/wiki/TL0AwaFzaiUByrkGF2IcUwDIn4e`
   - 新人会议培训视频（飞书妙记）: `https://dcnkm9z3sogt.feishu.cn/minutes/obcnn7x2bffm45zu8co7pr9s`
2. Tell the newcomer they can ask Codex questions while reading. For rule/FAQ questions, use `visual-hardcase-faq`; answer from LLM Wiki evidence first. If API search is unavailable, point them to `https://wiki.muchenai.com` and ask the admin to configure `LLM_WIKI_API_TOKEN`.
3. Ask for the newcomer name.
4. Send the shared assignment cloud sheet and ask them to add their name and 5 test-question rows at the end:
   - default test sheet: `https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl`
   - default sheet id: `eL8Rfl`
   - override with `VISUAL_HARDCASE_HOMEWORK_URL` and `VISUAL_HARDCASE_HOMEWORK_SHEET_ID` if the production sheet changes.
   - default workload: 5 questions / 5 rows, configurable with `VISUAL_HARDCASE_ASSIGNMENT_COUNT` or `--assignment-count`.
   - this is a shared training sheet, not a per-newcomer sheet created automatically.
5. During the 13:00-15:00 test-title stage, the 5 rows must include 1 simple question and 4 complex questions; categories are otherwise optional.
6. The newcomer does not need to fill validation fields, but prompt must be unambiguous, answer must be correct and unique, and answer format must be constrained. After all test titles are completed, fill `答案是否唯一` as `是`.
7. When the newcomer says the work is done, collect the completed row range. It must cover exactly 5 rows, for example `946:950`.
8. Submit the newcomer name and row numbers to the backend QC API. Do not read, preview, score, or rewrite rows locally.
9. Tell the newcomer that the training flow is complete and backend QC has been triggered.
10. Do not return score, conclusion, blockers, or rewrite suggestions from this newcomer flow.

Recommended starter command:

```bash
python scripts/newcomer_session.py start --name "<新人姓名>"
```

## Modes

- `guided-start`: send learning links, ask/record name, and provide the assignment cloud sheet.
- `guided-complete`: record that the newcomer finished, submit completed rows to backend QC, and print the backend handoff note.

Out of scope for this newcomer skill:

- `guided-review`, `cloud-review`, `cloud-writeback`, local scoring, and rewrite feedback.
- If the trainer wants these, route to `visual-hardcase-pre-qc` or a separate maintainer tool, not this newcomer flow.

## Required Input

For `generate`, collect only an optional output directory. Default to `~/Downloads/visual-hardcase-training/<timestamp>/`.

For completion, collect the completed row range. Do not collect task content, image material, prompt, answer, or model validation evidence inside this newcomer flow.

## Workflow

### Run Full Smoke Test

Use this before distributing the skill or after changing onboarding behavior:

```bash
python scripts/smoke_test_training_review.py
```

The smoke test starts a newcomer session, records completion without reading the sheet, skips real backend submit, and compiles all Python scripts.

### Start a Guided Newcomer Session

1. Confirm LLM Wiki API search is available:
   `python scripts/wiki_search.py "v3题型 作业流程 FAQ" --top-k 3`
   If it returns 401 or cannot connect, do not expose local debug URLs to the newcomer. Use the unavailable wording from **LLM Wiki Access Rule** and continue with the learning links.
2. Start the session:
   `python scripts/newcomer_session.py start --name "<新人姓名>"`
3. Copy the generated learning package into the Codex reply.
4. Route questions during reading to `visual-hardcase-faq`.
5. When the newcomer finishes, record completion and submit row numbers to backend QC:

```bash
python scripts/newcomer_session.py complete --session "<session.json>" --rows "<start:end>"
```

This command validates the expected 5-row range, updates the local session JSON, submits rows to the backend QC API, and prints a backend handoff note. It must not read the cloud sheet locally.

To refresh the schedule and current stage mid-session:

```bash
python scripts/newcomer_session.py status
```

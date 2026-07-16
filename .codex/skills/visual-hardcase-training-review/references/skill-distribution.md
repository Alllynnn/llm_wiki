# Visual Hardcase Skill Distribution

This file defines how to distribute and operate the visual-understanding-hardcase skill suite.

## Skill Suite

| Skill | Audience | Responsibility |
|---|---|---|
| `visual-hardcase-newcomer-suite` | Newcomer | Default newcomer bundle entrypoint. Loading this skill starts the day-one newcomer flow directly and routes FAQ/completion handoff without requiring the user to load a separate newcomer-flow skill. |
| `visual-hardcase-faq` | Newcomer, trainer, QC reviewer | Answer rules, task-type, FAQ, and bad-case questions from LLM Wiki evidence. |
| `visual-hardcase-training-review` | Newcomer and trainer | Start onboarding, send learning links, guide Feishu cloud-sheet assignment, and submit completed row numbers to backend QC. It does not read sheets or locally pre-QC newcomer work. |
| `visual-hardcase-pre-qc` | Trainer and QC reviewer | Perform strict pre-QC, blocker detection, pass/rework/reject recommendation, and batch issue summary. |
| `visual-hardcase-template-generator` | Template owner | Generate standardized construction templates, prompt/answer templates, and rule summaries. |

## Newcomer Entry Flow

Recommended newcomer entrypoint:

```text
visual-hardcase-newcomer-suite
```

When a newcomer opens the suite or training skill:

1. Show the day-one training schedule before the document links:
   - 10:00-10:10 项目介绍以及了解培训流程（谭攀）
   - 10:10-11:00 学习规则文档；links:
     - 视觉理解-难题构造内部规则文档: `https://shujufuwubu.feishu.cn/wiki/UW89wjZW0iWdkskxLsWcLTPEnJg`
     - v3题型作业步骤与构造思路 副本: `https://shujufuwubu.feishu.cn/wiki/Qx1nw19a2iHc8qkunCqcXDAdnhf`
     - 构造bad case记录&复盘 副本: `https://shujufuwubu.feishu.cn/wiki/TL0AwaFzaiUByrkGF2IcUwDIn4e`
   - 11:00-12:00 会议培训；training video: `https://dcnkm9z3sogt.feishu.cn/minutes/obcnn7x2bffm45zu8co7pr9s`
   - 12:00-13:00 午餐+休息
   - 13:00-15:00 完成 5 道试标题，分类任选，但必须为 1 道简单 + 4 道复杂题
   - 15:00-15:30 第一轮试标复盘会
   - 15:30-16:10 返修（全体人员）
   - 16:10-16:40 公布内部试标结果，并注册数据服务部账号，需要在信息收集表中填写对应信息
   - 16:40-19:00 进入正式试标，正式试标作业培训
2. For the 10:00-15:00 Codex focus window, state the current stage and next action from the current local time. Use `python scripts/newcomer_session.py status` to refresh the schedule and active step without creating a new session.
3. Every schedule row and current-stage reminder must include next arrangement wording, for example `完成当前阶段后，下一环节为：11:00-12:00 会议培训`.
4. Send the learning links:
   - 视觉理解-难题构造内部规则文档: `https://shujufuwubu.feishu.cn/wiki/UW89wjZW0iWdkskxLsWcLTPEnJg`
   - v3题型作业步骤与构造思路 副本: `https://shujufuwubu.feishu.cn/wiki/Qx1nw19a2iHc8qkunCqcXDAdnhf`
   - 构造bad case记录&复盘 副本: `https://shujufuwubu.feishu.cn/wiki/TL0AwaFzaiUByrkGF2IcUwDIn4e`
   - 新人会议培训视频（飞书妙记）: `https://dcnkm9z3sogt.feishu.cn/minutes/obcnn7x2bffm45zu8co7pr9s`
5. Explain the reading order: internal rules first as the source of truth, v3 task steps second as the operational manual, and bad-case review last as the anti-pattern library.
6. Tell the newcomer they can ask Codex questions during reading. The project knowledge base public entry is `https://wiki.muchenai.com`; answer rule and FAQ questions from LLM Wiki evidence first when API search is configured, and mark uncertainty instead of guessing when it is not.
7. Ask for the newcomer name.
8. Send the assignment cloud sheet. This default flow uses a shared training sheet, not a newly created newcomer-named sheet:
   - `https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl`
   - default sheet id: `eL8Rfl`
9. Default workload is 5 questions / 5 rows. During the 13:00-15:00 test-title stage, the 5 rows must include 1 simple question and 4 complex questions; categories are otherwise optional.
10. The newcomer adds their name and 5 test-question rows at the end of `试标作业表-新`, without changing other people's existing rows.
11. Before writing questions, remind the newcomer: validation fields do not need to be filled; questions must not be too easy; prompt must be unambiguous; answer must be correct and unique; answer format must be constrained. After all test titles are completed, fill `答案是否唯一` as `是`.
12. Ask the newcomer to return when finished with exactly 5 completed rows, for example `946:950`.
13. Submit the newcomer name and completed row numbers to the backend QC API.
14. Tell the newcomer the training flow is complete and backend QC has been triggered.
15. Do not read the cloud sheet locally, score, write back, or give rewrite instructions from the newcomer flow.

Starter command:

```bash
python scripts/newcomer_session.py start --name "<新人姓名>"
```

Completion handoff command:

```bash
python scripts/newcomer_session.py complete --session "<session.json>" --rows "<start:end>"
```

Status-only command:

```bash
python scripts/newcomer_session.py status
```

## LLM Wiki Knowledge Access

Use `https://wiki.muchenai.com` as the public Wiki entry and default API base. API search calls `/api/v1/projects/{id}/search` and requires `LLM_WIKI_API_TOKEN` unless the admin explicitly enables unauthenticated API access.

This gate must be included in the distributed skills, not only in a local project `AGENTS.md` file. Any FAQ, rule, task-type, bad-case, pre-QC, scoring, or template answer must rerun LLM Wiki search before giving a factual conclusion. If API search is unavailable, mark the answer as unverified instead of relying on memory.

Recommended environment:

```bash
LLM_WIKI_API_BASE_URL=https://wiki.muchenai.com
LLM_WIKI_API_TOKEN=<configured-by-admin>
LLM_WIKI_PROJECT_ID=7ad8995a9c34304f
```

Loopback URLs such as `127.0.0.1:19828` are maintainer-only debug addresses. Do not show them to newcomers as action links. If API search is unavailable, tell the newcomer to use the public Wiki entry and say that admin API configuration is pending.

## Separate Pre-QC / QC Flow

Local pre-QC is not part of the newcomer onboarding flow. The newcomer skill only submits completed row numbers to the backend QC API. If a trainer asks for direct review in the current Codex session, switch to `visual-hardcase-pre-qc` or a maintainer-operated QC service.

For maintainer reference only, the async service shape is:

```text
Newcomer skill -> POST /api/v1/visual-hardcase/qc-jobs -> jobId/status
Backend service -> codex_model_pre_qc.py --job-id <jobId> --job-dir <jobDir> --rows <rows> -> writes 预质检
```

Backend command:

```bash
python scripts/qc_api_server.py --host 127.0.0.1 --port 8765
```

The minimal service implementation is `scripts/qc_api_server.py`. It must run with token auth; do not expose a no-auth endpoint.

## Image Handling Policy

Visual tasks cannot receive a clean pass unless the reviewer can inspect image evidence.

Current Feishu `+csv-get` text extraction does not expose embedded cell images as readable URLs. Therefore cloud-sheet rows where image columns are embedded images but not exported as accessible links must be blocked with:

```text
图片材料缺失或未被脚本读取，不能确认视觉证据。
```

Acceptable ways to unblock:

- Fill `图片列表（URL，一行一张）` with one accessible image URL per line. This is the preferred cloud-sheet format.
- Put readable image URLs in the image columns.
- Put a readable Drive folder/doc link in the image/source field.
- Add a dedicated image-export step that converts cell images to accessible Drive URLs before review.
- Let the public QC service run with a Feishu API capability that can download cell images and pass them to the model reviewer.

Do not use a placeholder such as `云表格图片列未读取到文本` as proof of visual evidence.

## Write-Back Policy

Newcomer onboarding never writes back and this distribution note does not expose a write-back command. Any future write-back must live in a separate trainer/QC workflow with explicit authorization.

## Deployment States

| State | Meaning |
|---|---|
| Local only | Newcomer flow sends learning links and assignment sheet; completion can be smoke-tested with `--no-submit-qc` without reading the sheet. |
| Local API | `qc_api_server.py` runs on loopback; Codex submits row-number jobs and backend writes `预质检`. |
| Public API | Cloudflare or another DNS provider points `https://<QC_DOMAIN>` to the selected public host or edge proxy. |
| Full central QC | Public service has Feishu read permissions, model credentials, LLM Wiki access, durable job storage, and optional write-back policy. |

Current verified state for newcomer onboarding: local guided start, 5-row completion validation, and backend job submission path. Cloud review still runs only in the backend/QC workflow.

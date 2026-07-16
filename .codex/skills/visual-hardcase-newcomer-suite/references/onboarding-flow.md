# Visual Hardcase Newcomer Flow

## Newcomer Entry Flow

When a newcomer opens the skill:

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
2. For the 10:00-15:00 Codex focus window, state the current stage and next action from the current local time. The helper command is `python scripts/newcomer_session.py status`.
3. Every schedule row and current-stage reminder must include next arrangement wording, for example `完成当前阶段后，下一环节为：11:00-12:00 会议培训`.
4. After the newcomer's name is known, create active same-day heartbeat reminders for the remaining checkpoints when the Codex app exposes the automation tool. Generate the plan with `python scripts/newcomer_session.py reminders --name "<新人姓名>"`; create one heartbeat per returned item; do not show raw RRULE strings to the newcomer. If the client cannot create reminders, state the fallback clearly and continue with time-aware status on every return.
5. Send the learning links:
   - 视觉理解-难题构造内部规则文档: `https://shujufuwubu.feishu.cn/wiki/UW89wjZW0iWdkskxLsWcLTPEnJg`
   - v3题型作业步骤与构造思路 副本: `https://shujufuwubu.feishu.cn/wiki/Qx1nw19a2iHc8qkunCqcXDAdnhf`
   - 构造bad case记录&复盘 副本: `https://shujufuwubu.feishu.cn/wiki/TL0AwaFzaiUByrkGF2IcUwDIn4e`
   - 新人会议培训视频（飞书妙记）: `https://dcnkm9z3sogt.feishu.cn/minutes/obcnn7x2bffm45zu8co7pr9s`
6. Explain the reading order:
   - Read the internal rules first as the source of truth.
   - Read v3 task steps second by task type.
   - Read bad-case review last as the anti-pattern library.
7. Tell the newcomer they can ask Codex rule questions during reading.
8. Ask for the newcomer name.
9. Send the shared assignment cloud sheet:
   - `https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl`
   - default sheet id: `eL8Rfl`
10. Default workload is 5 questions / 5 rows. In the 13:00-15:00 test-title stage, the 5 rows must include 1 simple question and 4 complex questions; categories are otherwise optional.
11. The newcomer adds their name and 5 test-question rows at the end of `试标作业表-新`, without changing other people's existing rows.
12. Before writing questions, remind the newcomer: validation fields do not need to be filled; questions must not be too easy; prompt must be unambiguous; answer must be correct and unique; answer format must be constrained. After all test titles are completed, fill `答案是否唯一` as `是`.
13. Ask the newcomer to return when finished with exactly 5 row numbers, for example `946:950`.
14. Submit the newcomer name and completed row numbers to the backend QC API. The newcomer skill does not read the sheet, score, write back, or give rewrite instructions; backend QC handles the row review.

## Commands

Start:

```bash
python scripts/newcomer_session.py start --name "<新人姓名>"
```

Complete:

```bash
python scripts/newcomer_session.py complete --session "<session.json>" --rows "<start:end>"
```

Status only:

```bash
python scripts/newcomer_session.py status
```

Active reminder plan:

```bash
python scripts/newcomer_session.py reminders --name "<新人姓名>"
```

Completion submits to `VISUAL_HARDCASE_QC_API_URL` when configured, defaulting to:

```text
https://wiki.muchenai.com/api/v1/visual-hardcase/qc-jobs
```

The request uses `VISUAL_HARDCASE_QC_API_TOKEN`, `LLM_WIKI_API_TOKEN`, or the packaged `config/llm_wiki_token.txt` as a Bearer token. Do not print the token.

## Knowledge Access

FAQ and rule answers must use LLM Wiki evidence when configured:

```bash
python scripts/wiki_search.py "用户问题或关键词" --top-k 8 --include-content
```

The public Wiki entry is `https://wiki.muchenai.com`.

The package includes `config/llm_wiki_token.txt` for API authentication. Environment variable `LLM_WIKI_API_TOKEN` overrides it. Never display the token value to the newcomer.

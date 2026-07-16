---
name: visual-hardcase-pre-qc
description: Use when performing pre-QC or quality inspection on visual-understanding-hardcase submissions before formal review, including blocker detection, bad-case classification, pass/fail recommendation, and rework guidance.
---

# Visual Hardcase Pre-QC

## Core Rule

Pre-QC is stricter than training review. Prefer blocking risky submissions when the evidence is incomplete, ambiguous, or conflicts with the LLM Wiki rules.

This retrieval rule must travel with the distributed skill. Do not issue pass/rework/reject recommendations from memory or stale chat context; retrieve LLM Wiki evidence first, then inspect the submitted material.

## Workflow

1. Search LLM Wiki for the submitted task type, prompt pattern, and possible bad-case category.
2. Read `references/pre-qc-contract.md`.
3. Check blockers first; a blocker overrides partial strengths.
4. Produce a pass / rework / reject recommendation with cited evidence.
5. For batch work, summarize repeated issues and list samples that need human audit.

Command:

```bash
python scripts/wiki_search.py "<题型> <关键词> 质检 bad case" --top-k 10 --include-content
```

If the LLM Wiki API is unavailable, do not issue a clean pass. Report `待复核: 无法连接 LLM Wiki API`.

## Newcomer Sheet Watcher

Use this only as the legacy rule fallback for the internal newcomer training entry sheet:

```bash
python scripts/watch_newcomer_sheet.py --once --dry-run
python scripts/watch_newcomer_sheet.py --once
python scripts/watch_newcomer_sheet.py --watch --interval-seconds 120
```

Default behavior:

- Sheet: `https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl`
- Trigger: `质检类别` equals `测试组`
- Result field: write AI pre-QC text to `预质检`
- Safety: skip rows where `预质检` is already non-empty; use `--force` only for deliberate overwrite
- Rework loop: if `是否返修完成` equals `是`, re-run pre-QC even when `预质检` is non-empty and overwrite only that repaired row's `预质检`
- Knowledge-base collection: only collect rows whose `预质检` was empty before the current job and was written by the current job; rows with existing `预质检` may be reported as skipped, but must not be added as real QC case samples.
- Scope: only writes the `预质检` cell for each triggered row
- Images: reads both floating images and `rich_text` embedded cell images in `图片1`-`图片8`; embedded image tokens count as existing image material and must not be reported as missing images
- Answer material: reads `rich_text` embedded cell images in Q column `answer`; an embedded answer image must not be reported as missing answer
- Newcomer output: hide internal pipeline notices such as "current cloud-sheet mode does not force target-model validation"; only show actionable issues that the newcomer or reviewer can fix; when a field is missing, name the field instead of presenting it as an AI factual verdict
- Auth: uses `lark-cli --as user`; LLM Wiki token comes from env or the local skill/project config token file

For formal hardcase scoring, add `--require-model-validation`. Newcomer training sheet pre-QC does not require model validation by default because the sheet is used as a training gate before full formal review.

## Codex Model QC Worker

Production newcomer pre-QC must call a Codex model worker, not only the legacy Python rule scorer.

Default worker:

```bash
python scripts/codex_model_pre_qc.py --rows 946:950
```

Behavior:

- One persistent Codex worker conversation is used for queued pre-QC jobs.
- The worker session id is stored in `config/codex_qc_worker_session_id.txt`.
- Concurrent jobs are serialized with `config/codex_qc_worker.lock`.
- First job creates the Codex session; later jobs run `codex exec resume <session_id>` so the same conversation handles the queue.
- The Python script prepares row data and LLM Wiki evidence, calls the Codex model with a JSON schema, then writes the model result to `预质检`.
- Rows with existing `预质检` are skipped unless `是否返修完成=是`; repaired rows are sent to the same queued Codex model worker and their `预质检` cell is overwritten with the latest model result.
- The Codex worker prompt explicitly invokes `$visual-hardcase-pre-qc` and tells the worker to run LLM Wiki search when the pre-collected evidence is insufficient or mismatched.
- The pre-collected `wikiEvidence` is a warm start, not the only allowed evidence source.
- Embedded Feishu image tokens count as existing image material; if the model cannot inspect the actual image content, it must put that point under `人工复核` instead of claiming the image is missing.

Key environment variables:

- `VISUAL_HARDCASE_QC_CODEX_MODEL`: model for the worker, default `gpt-5.5`.
- `VISUAL_HARDCASE_QC_CODEX_SESSION_ID`: optional fixed session id override.
- `VISUAL_HARDCASE_QC_CODEX_BIN`: Codex executable, default `codex`.
- `VISUAL_HARDCASE_QC_WORKER_MODE=legacy-rules`: temporarily use the old rule-only watcher.

## Backend QC Job API

Use this when the newcomer skill submits completed row numbers and the backend should trigger QC:

```bash
python scripts/qc_api_server.py --host 127.0.0.1 --port 8765
```

Endpoint:

```text
POST /api/v1/visual-hardcase/qc-jobs
GET  /api/v1/visual-hardcase/qc-jobs/{job_id}
```

Auth is required:

```text
Authorization: Bearer <VISUAL_HARDCASE_QC_API_TOKEN>
```

Auth is required for job submission, job status, and `/health`. If `VISUAL_HARDCASE_QC_API_TOKEN` is not set, the server falls back to `LLM_WIKI_API_TOKEN` or the local skill/project token file. Do not print the token.

Request shape:

```json
{
  "newcomerName": "张三",
  "rows": "946:950",
  "homeworkUrl": "https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl",
  "sheetId": "eL8Rfl",
  "sessionId": "20260708-..."
}
```

The API stores a job file and runs `codex_model_pre_qc.py --rows <rows>` asynchronously. The newcomer skill only submits row numbers; backend QC reads the sheet, sends the job into the queued Codex model worker conversation, and writes the model result to the `预质检` field.

The legacy `watch_newcomer_sheet.py --once --rows <rows>` path is only used when `VISUAL_HARDCASE_QC_WORKER_MODE=legacy-rules` is explicitly configured. A stale `VISUAL_HARDCASE_QC_WATCHER_SCRIPT` value must not affect normal API row-number jobs.

By default, the API requires exactly 5 row numbers per newcomer job. Override with `VISUAL_HARDCASE_ASSIGNMENT_COUNT` or `--expected-row-count`; use `0` only for maintainer testing.

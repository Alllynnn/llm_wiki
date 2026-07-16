# Public QC API Deployment Runbook

This runbook exposes the newcomer QC job API through the existing LLM Wiki backend.

## Cloudflare Domain Constraint

The Cloudflare-managed zone is `touf.shop`. Do not assume that `muchenai.com` is available in Cloudflare for new DNS records.

If a new Cloudflare DNS/custom-domain entry is needed for this QC API, use a subdomain under `touf.shop`, for example:

```text
visual-qc.touf.shop
```

The current documented production route may still use an already-existing public Wiki entry such as `wiki.muchenai.com`. Treat that as an existing service endpoint, not as a request to create a new Cloudflare zone or DNS record.

## Recommended Topology

The preferred production topology is the existing `wiki.muchenai.com` LLM Wiki Rust backend:

```text
https://wiki.muchenai.com
  -> existing LLM Wiki backend
  -> POST /api/v1/visual-hardcase/qc-jobs
  -> codex_model_pre_qc.py --job-id <jobId> --job-dir <jobDir> --rows <rows>
```

Run the backend on the machine that has the needed Feishu read credentials, `lark-cli` user auth, LLM Wiki token, and model access.

## Backend Environment

Set these in the LLM Wiki service environment:

```bash
VISUAL_HARDCASE_QC_API_TOKEN=<redacted>
LLM_WIKI_API_TOKEN=<redacted>
VISUAL_HARDCASE_ASSIGNMENT_COUNT=5
VISUAL_HARDCASE_QC_WORKER_SCRIPT=/path/to/codex_model_pre_qc.py
VISUAL_HARDCASE_QC_MAX_IMAGE_ATTACHMENTS=50
VISUAL_HARDCASE_QC_PYTHON=/path/to/python
```

If `VISUAL_HARDCASE_QC_API_TOKEN` is absent, the endpoint falls back to `LLM_WIKI_API_TOKEN`. Do not run production without at least one token.

Job JSON files are stored under:

```text
<LLM_WIKI_DATA_ROOT>/visual-hardcase-qc-jobs/*.json
```

## Local Development

The skill-local Python API is still available for maintainer loopback tests:

```bash
python .codex/skills/visual-hardcase-pre-qc/scripts/qc_api_server.py --host 127.0.0.1 --port 8765
```

Do not expose the Python loopback service publicly unless it is explicitly supervised and token-protected.

## Public Endpoints

- `POST /api/v1/visual-hardcase/qc-jobs`
- `GET /api/v1/visual-hardcase/qc-jobs/{job_id}`

Every endpoint requires:

```text
Authorization: Bearer <VISUAL_HARDCASE_QC_API_TOKEN or LLM_WIKI_API_TOKEN>
```
Verify after backend restart:

```bash
curl -i -X POST \
  -H "Authorization: Bearer <redacted>" \
  -H "Content-Type: application/json" \
  -d '{"newcomerName":"测试","rows":"946:950","homeworkUrl":"https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl","sheetId":"eL8Rfl"}' \
  https://wiki.muchenai.com/api/v1/visual-hardcase/qc-jobs
```

Unauthenticated requests should return `401`.

## Production Guardrails

- Do not expose the API without token auth.
- Do not put tokens in query parameters.
- Store service tokens in a root/user-private env file, not in the skill directory.
- Backend worker writes only the `预质检` field.
- Existing `预质检` rows remain idempotent-skip by default; if `是否返修完成=是`, the backend re-runs QC and overwrites only that row's `预质检`.
- `VISUAL_HARDCASE_QC_WATCHER_SCRIPT` is legacy-only. It is ignored unless `VISUAL_HARDCASE_QC_WORKER_MODE=legacy-rules` is explicitly set.
- If the API host cannot read Feishu sheets, the job will fail and the job JSON will contain stderr/error details.

# Public QC API Contract Draft

The newcomer-facing production endpoint is the LLM Wiki backend route:

```text
POST /api/v1/visual-hardcase/qc-jobs
GET  /api/v1/visual-hardcase/qc-jobs/{job_id}
```

Do not call production without a configured Bearer token.

## Recommended Deployment

Use the existing public Linux edge host from Linux memory as the public entrypoint:

- Public entry: `https://wiki.muchenai.com`
- Cloudflare-managed DNS zone for new records: `touf.shop`; use `visual-qc.touf.shop` if a new QC subdomain is required.
- Runtime: existing LLM Wiki Rust backend
- Worker: backend spawns `codex_model_pre_qc.py --job-id <jobId> --job-dir <jobDir> --rows <rows>`
- Job store: `LLM_WIKI_DATA_ROOT/visual-hardcase-qc-jobs/*.json`
- Rework behavior: rows with existing `预质检` are skipped unless `是否返修完成=是`; repaired rows are re-QCed and only their `预质检` cell is overwritten.

Deploying the API directly on the public edge is acceptable only if the service has no LAN-only dependencies and secrets are isolated. The safer first version is an internal service exposed through the existing reverse-tunnel pattern.

## API

### Submit Job

`POST /api/v1/visual-hardcase/qc-jobs`

Auth is required:

```text
Authorization: Bearer <VISUAL_HARDCASE_QC_API_TOKEN or LLM_WIKI_API_TOKEN>
Content-Type: application/json
```

Request:

```json
{
  "newcomerName": "张三",
  "rows": "946:950",
  "rowNumbers": [946, 947, 948, 949, 950],
  "homeworkUrl": "https://shujufuwubu.feishu.cn/wiki/Ed6uwoItXiSYsqkID4pcLR8Wnjc?sheet=eL8Rfl",
  "sheetId": "eL8Rfl",
  "sessionId": "20260708-..."
}
```

Response:

```json
{
  "ok": true,
  "jobId": "7a9c...",
  "status": "queued",
  "rows": "946:950",
  "rowNumbers": [946, 947, 948, 949, 950]
}
```

The API requires exactly 5 row numbers by default. Override `VISUAL_HARDCASE_ASSIGNMENT_COUNT` only when the training policy changes.

### Query Job

`GET /api/v1/visual-hardcase/qc-jobs/{job_id}`

Response while running:

```json
{
  "ok": true,
  "jobId": "7a9c...",
  "status": "running",
  "rows": "946:950"
}
```

Response when completed:

```json
{
  "ok": true,
  "jobId": "7a9c...",
  "status": "completed",
  "returnCode": 0,
  "stdout": "...",
  "stderr": ""
}
```

Failure response:

```json
{
  "ok": true,
  "jobId": "7a9c...",
  "status": "failed",
  "error": "QC worker script not found; set VISUAL_HARDCASE_QC_WORKER_SCRIPT"
}
```

## Client Commands

Submit from the newcomer session helper:

```powershell
$env:VISUAL_HARDCASE_QC_API_URL = "https://wiki.muchenai.com/api/v1/visual-hardcase/qc-jobs"
python scripts/newcomer_session.py complete --session "<session.json>" --rows "946:950"
```

Query status if needed:

```bash
curl -H "Authorization: Bearer <redacted>" \
  "https://wiki.muchenai.com/api/v1/visual-hardcase/qc-jobs/<jobId>"
```

## Required Production Decisions

| Item | Default | Needs confirmation |
|---|---|---|
| Domain | `wiki.muchenai.com` | No |
| Runtime location | Existing LLM Wiki backend | No |
| Auth | `VISUAL_HARDCASE_QC_API_TOKEN` or `LLM_WIKI_API_TOKEN` | Yes |
| Worker script | `VISUAL_HARDCASE_QC_WORKER_SCRIPT` or repo default `codex_model_pre_qc.py` | Yes in production |
| Write-back | Backend worker writes only `预质检`; repaired rows overwrite that cell when `是否返修完成=是` | No |

## Current Behavior

The production API stores a job JSON and triggers the Codex model QC worker asynchronously. The newcomer skill still does not read the sheet locally.
Default idempotency is preserved: existing `预质检` rows are skipped, except repaired rows where `是否返修完成=是`.

```json
{
  "api_status": "enabled_when_backend_env_is_configured",
  "endpoint": "/api/v1/visual-hardcase/qc-jobs",
  "expected_rows": 5
}
```

# Visual Hardcase Project Hooks

This directory contains project-level guard scripts for the visual hardcase skills.

## Guard

Run:

```bash
python .codex/hooks/visual_hardcase_guard.py "OCR票据题型怎么构造？" --mode json
python .codex/hooks/visual_hardcase_guard.py "OCR票据题型怎么构造？" --mode search --top-k 3
```

The guard detects visual-understanding-hardcase requests and reminds the agent to retrieve project evidence from LLM Wiki before answering. In `search` mode it calls:

```text
POST https://wiki.muchenai.com/api/v1/projects/{id}/search
```

Environment overrides:

```bash
LLM_WIKI_API_BASE_URL=https://wiki.muchenai.com
LLM_WIKI_API_TOKEN=<optional-env-override>
LLM_WIKI_PROJECT_ID=7ad8995a9c34304f
```

The newcomer package also includes `.codex/hooks/config/llm_wiki_token.txt`. The guard uses `LLM_WIKI_API_TOKEN` first and falls back to this file. Do not print the token value.

If API search is unavailable, the guard returns a fallback message and the agent must avoid presenting unverified memory as project rules.

For newcomer-only distribution, route onboarding/training triggers to `visual-hardcase-newcomer-suite`. FAQ/rule questions still route to `visual-hardcase-faq`; pre-QC remains a separate trainer workflow.

## Current Integration

The project-level `AGENTS.md` is the active soft hook loaded by Codex in this repository. A verified Codex automatic hook schema was not present in the local config, so this script is kept as the hard guard entry point for manual checks and future hook wiring.

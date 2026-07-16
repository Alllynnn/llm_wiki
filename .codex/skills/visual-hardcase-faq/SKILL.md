---
name: visual-hardcase-faq
description: Use when answering FAQ, rule, task-type, bad-case, or construction-standard questions about the visual-understanding-hardcase LLM Wiki knowledge base, including v3 visual understanding hardcase work.
---

# Visual Hardcase FAQ

## Core Rule

Answer from LLM Wiki evidence first. Do not rely on memory when the local API can be queried.

This retrieval rule must travel with the distributed skill. Even if a long Codex conversation already contains earlier visual-hardcase context, rerun LLM Wiki search before giving factual rule, task-type, FAQ, or bad-case conclusions.

## Workflow

1. Run `scripts/wiki_search.py` from this skill directory against the user's question.
2. If the question is broad, run 2-4 focused searches: project overview, the named task type, quality rules, and bad case review.
3. Read `references/answer-contract.md` before composing the final answer.
4. Answer in Chinese unless the user asks otherwise.
5. Cite the retrieved wiki page titles and paths. If the API is unavailable or evidence is missing, say that explicitly and ask for the relevant wiki snippet or for the LLM Wiki API to be started.

## Search Command

```bash
python scripts/wiki_search.py "用户问题或关键词" --top-k 8 --include-content
```

Defaults:

- Public Wiki entry: `https://wiki.muchenai.com`
- `LLM_WIKI_API_BASE_URL`: `https://wiki.muchenai.com`
- `LLM_WIKI_API_TOKEN`: optional override. The distributed newcomer package also includes `config/llm_wiki_token.txt` for direct use.
- `LLM_WIKI_PROJECT_ID`: `7ad8995a9c34304f`

Override these environment variables only when the user gives a different LLM Wiki API address or project id.
Never print or paste the token value from environment variables or `config/llm_wiki_token.txt`.
Do not show local loopback/debug URLs such as `127.0.0.1:19828` to newcomers. If the API is unavailable, point the user to the public Wiki entry and say the API token needs to be configured.

# FAQ Answer Contract

Use this contract after gathering LLM Wiki search results.

## Required Output

1. Direct answer in 1-3 sentences.
2. Rule basis with cited wiki titles and paths.
3. Practical action or example when the question is about how to construct or fix a submission.
4. Uncertainty note if evidence is missing, contradictory, or API access failed.

## Search Guidance

- For broad questions, search both the general rule document and bad-case review records.
- For task-type questions, search the exact task type name plus `规则`, `构造`, and `bad case`.
- For process questions, search `步骤`, `作业`, `质检`, `复盘`, and `模板`.

## Guardrails

- Do not treat the robot answer as the final business judgment.
- Do not claim a rule exists unless it appears in retrieved wiki evidence or in user-provided source text.
- Do not answer image-specific facts unless the user supplied the image or a reliable image description.

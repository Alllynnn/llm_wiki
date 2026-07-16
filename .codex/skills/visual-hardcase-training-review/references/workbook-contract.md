# Newcomer Training Workbook Contract

The workbook is the local handoff between the template generator, newcomer, and pre-QC review.

## Sheets

| Sheet | Purpose |
|---|---|
| `填写说明` | Project workflow, v3 formula, model validation, and red lines. |
| `训练题填写` | Newcomer input rows. One row is one constructed case. |
| `题型规则速查` | Active v3 task types and key constraints from LLM Wiki. |
| `自检清单` | Yes/no checklist before submission. |
| `质检结果` | Script-generated scoring output. |

## Cloud Sheet Mapping

For the Feishu sheet `试标作业表-新`, map columns into the same review contract:

| Cloud Column | Review Field |
|---|---|
| `姓名` | `新人姓名` |
| `日期` | `训练批次` |
| `分类` | `题型分类` |
| `图片列表（URL，一行一张）` | preferred `图片文件夹或图片链接` source; one image URL per line |
| `图片1`-`图片8` | `图片文件夹或图片链接` and inferred `图片数量` |
| `图片顺序是否正确（必须正确排序）（可以空着）` | `图片编号说明` supplement |
| `prompt` | `prompt` |
| `answer` | `answer` |
| `推理过程（推理过程不能放图片）` | `推理过程` |
| `答案是否唯一` | `答案是否唯一` |
| `信源（文字）` / `信源（图片）` | `信源链接或标注图路径` |
| `验证截图（不填）内部试标不用跑模型进行验证` | optional model-validation evidence |
| `质检结果` / `质检备注（文字）` | optional write-back targets |

## Required Columns

`case_id`, `新人姓名`, `训练批次`, `题型分类`, `图片数量`, `图片文件夹或图片链接`, `图片编号说明`, `prompt`, `answer`, `答案格式限定是否已写入prompt`, `答案是否唯一`, `推理过程`, `信源链接或标注图路径`, `是否需要验证结果`, `answer(验证结果)`, `模型是否答错`, `初标是否完成`, `自检备注`

## Review Policy

- Do not score image facts that are not visible or not provided.
- A row cannot receive a clean pass if LLM Wiki evidence is unreachable.
- For formal hardcase qualification and strict pre-QC, `模型是否答错` should be `是`; absent model validation is a blocker.
- For current newcomer cloud-sheet training rows, the internal trial table says model-validation screenshots may be omitted. In that mode, missing model validation is an advisory issue unless the reviewer passes `--require-model-validation`.
- Missing answer-format constraints, non-v3 task types, and non-unique answers are blockers.
- Public API upload remains disabled until `public-api-contract.md` is filled from real API documentation.
- Cloud-sheet write-back must target test copies unless the user explicitly authorizes writing to the production sheet.
- Prefer a text image-list column with accessible URLs over embedded sheet images. Embedded images are blocked unless a service can download and inspect them.

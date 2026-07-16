# Training Review Rubric

Use this rubric after retrieving task-type and bad-case evidence from LLM Wiki.

## Score Bands

- `85-100`: Can be shown to the training lead as a strong submission, with minor edits.
- `70-84`: Usable for training after targeted fixes.
- `50-69`: Major revision needed before it should count as a qualified training case.
- `<50`: Not acceptable as a training case.
- `无法评分`: Required material is missing or LLM Wiki evidence cannot be reached.

## Action Semantics

- This review is a coarse screening gate. Its main job is to filter bad submissions before human pre-review, not to replace the human reviewer's detailed edit suggestions.
- `合格` / `基本合格` without blockers means the row can proceed to human pre-review. Issues are reviewer attention points, not required rewrite instructions.
- `需修改` / `不合格` / `无法评分`, or any row with blockers, means the row is screened out and should be revised before focused re-review.
- Do not tell a newcomer they must fix a `基本合格` row before continuing. Use "人工预审关注" wording instead of "修改建议" wording by default.
- Give concrete rewrite suggestions only when the user explicitly asks Codex to propose edits.
- For smoke-test or synthetic rows, state that comments validate pipeline behavior and are not production training requirements by themselves.

## 100-Point Rubric

| Area | Points | What to Check |
|---|---:|---|
| Task-type fit | 15 | The submission matches the chosen v3 task type and does not drift into another category. |
| Image/material quality | 20 | Image is safe, clear, inspectable, source-traceable, and contains enough evidence. |
| Prompt clarity | 20 | Question is unambiguous, constrained, not subjective, and requests the right reasoning depth. |
| Answer uniqueness and format | 20 | Expected answer is unique, verifiable, and formatted exactly as requested. |
| Reasoning/source/model validation | 15 | Reasoning is not perfunctory, source is traceable, and model validation supports hardcase value. |
| Bad-case prevention | 10 | Known traps for the task type have been checked. |

## Common Task-Type Search Anchors

Use these names as search anchors when the user gives only a rough description:

`实物判断`, `多图变化`, `多图场景判别`, `室内方位推理`, `多图动态排序`, `漫画排序`, `多图去重计数`, `判断与反思-纠错`, `双目双图结合`, `多图同屋判别`, `地图规划`, `读示数`, `齿轮`, `OCR票据`.

## Output Format

```markdown
## 训练评分

结论: [合格/需修改/不合格/无法评分]
总分: [0-100 或 无法评分]

### 分项评分
| 项目 | 分数 | 依据 |
|---|---:|---|

### 关键问题
- [按影响排序]

### 筛查动作
- [放行到人工预审/筛出返修/无法评分]

### 人工预审关注
- [只列风险点或需人工确认的点，不默认给具体改稿建议]

### 规则依据
- [wiki title] (`path`)

### 人工复核重点
- [训练负责人需要看什么]
```

## Blockers

Return `无法评分` or very low score when any blocker appears:

- Missing image/material needed to judge the visual task.
- Prompt allows multiple valid answers.
- Expected answer is unsupported by the visible evidence.
- The task type requires model failure but the model validation is absent or shows the target model answered correctly.
- Known bad-case pattern appears and cannot be repaired by a small wording change.

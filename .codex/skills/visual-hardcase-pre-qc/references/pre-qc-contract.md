# Pre-QC Contract

Use this contract after retrieving LLM Wiki evidence for the task type and possible bad-case category.

## Recommendation Levels

- `通过`: No blocker found; only minor improvements remain.
- `退回修改`: There is a fixable issue that could affect validity or review efficiency.
- `拒收`: Core evidence, task type, prompt, answer, or validation is invalid.
- `待复核`: API/source/image evidence is incomplete; human review is required.

## Blocking Checks

Check blockers before assigning strengths:

1. Image/material is missing, unsafe, blurry, cropped, or not source-traceable.
2. Prompt is ambiguous, subjective, leading, or mismatched with the task type.
3. Expected answer is not unique, not supported by image evidence, or has wrong format.
4. Reasoning is absent where reasoning is required, or the explanation only restates the answer.
5. Model validation is missing for hardcase value, or the target model did not fail.
6. Known bad-case trap appears for the task type.
7. The construction depends on private assumptions not stated in the prompt.

## Output Format

```markdown
## 预质检结论

建议: [通过/退回修改/拒收/待复核]
风险级别: [低/中/高/阻断]

### 阻断项
- [没有则写“无明显阻断项”]

### 主要风险
- [按严重程度排序]

### 退回修改建议
- [具体修改动作]

### Bad Case 归类
- [类别或“未命中已知类别”]

### 规则依据
- [wiki title] (`path`)

### 人工复核
- [需要人工确认的视觉事实或规则点]
```

## Batch Summary

For multiple submissions, add:

```markdown
## 批次概览

总数:
通过:
退回修改:
拒收:
待复核:
高频问题:
抽检样本:
```

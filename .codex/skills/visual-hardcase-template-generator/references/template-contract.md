# Visual Hardcase Template Contract

Use this output contract for generated construction templates.

```markdown
---
template_name: "[题型] 构造模板"
task_type: "[题型]"
version: "YYYY-MM-DD"
source_basis:
  - title: "[wiki title]"
    path: "[wiki path]"
status: "[可使用/待知识库确认]"
---

# [题型] 构造模板

## 适用场景
[说明这个模板适合什么视觉难题，不适合什么情况]

## 必填字段
| 字段 | 要求 | 示例/说明 |
|---|---|---|
| 图片/素材 | [清晰度、来源、数量、视角等] | |
| 题目目标 | [要考察的能力] | |
| Prompt | [用户可见问题] | |
| 标准答案 | [唯一答案与格式] | |
| 推理依据 | [需要引用的视觉证据] | |
| 模型验证 | [目标模型错误记录] | |

## Prompt 模板

```text
[可直接复用的题目模板，保留变量占位符]
```

## 答案格式

```text
[严格答案格式]
```

## 构造步骤

1. [选图/素材]
2. [确定考点]
3. [写 prompt]
4. [写标准答案]
5. [跑模型验证]
6. [预质检]

## 自检清单

- [ ] 图片证据足够且可检查
- [ ] Prompt 不依赖隐含假设
- [ ] 标准答案唯一
- [ ] 答案格式严格
- [ ] 模型验证证明 hardcase 价值
- [ ] 已排查该题型常见 bad case

## 常见 Bad Case

- [来自 LLM Wiki 的题型风险]

## 规则依据

- [wiki title] (`path`)
```

If LLM Wiki evidence is unavailable, set `status: "待知识库确认"` and do not fill task-specific rules as facts.

# Upstream PR 独立审查合同

只审查 `Alllynnn/llm_wiki` 中同时带 `automation:upstream-sync` 和
`codex:review-ready` 的开放 PR。审查使用独立 worktree，不修改应用代码、不提交、
不 push，也不向自己的 PR 发送形式上的 APPROVE。

每轮绑定 PR 当前 head SHA。检查 upstream 功能、冲突解决、浏览器服务、多用户登录、
中文界面、问答、共享模型配置、Embedding、Agent 检索和 visual-hardcase；读取当前
SHA 的跨平台 CI，并运行必要的本地验证。

发现问题时，以严重度、文件位置、原因、预期修复和验证方式发布 findings；将当前
SHA 的 `codex/review` commit status 设为 failure，添加 `codex:changes-requested`，
移除 `codex:reviewed`。没有问题时将当前 SHA 的 `codex/review` 设为 success，添加
`codex:reviewed`，然后使用 merge commit 开启 auto-merge。

状态写入前再次读取 PR head；SHA 变化时放弃旧结论并重新审查。存在失败 CI、冲突、
`codex:blocked` 或未解决 finding 时不能通过。没有待审查 PR 时安静结束。

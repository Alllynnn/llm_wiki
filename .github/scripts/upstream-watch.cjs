const ISSUE_MARKER = "<!-- codex-upstream-sync -->";
const LABEL = "codex:sync-needed";

function buildIssueBody(state) {
  return `${ISSUE_MARKER}
## Upstream 更新待处理

- fork base: \`${state.baseSha}\`
- upstream head: \`${state.upstreamSha}\`
- 待合入提交数: ${state.commitCount}
- compare: ${state.compareUrl}

该 Issue 由 upstream watcher 维护。执行对话处理后，由合并结果自动关闭。`;
}

async function ensureLabel(github, owner, repo) {
  try {
    await github.rest.issues.createLabel({
      owner,
      repo,
      name: LABEL,
      color: "1d76db",
      description: "检测到尚未进入 fork 的 upstream 更新",
    });
  } catch (error) {
    if (error.status !== 422) throw error;
  }
}

async function reconcileIssue({ github, owner, repo, state }) {
  const response = await github.rest.issues.listForRepo({
    owner,
    repo,
    state: "all",
    per_page: 100,
  });
  const issue = response.data.find(
    (item) => !item.pull_request && item.body?.includes(ISSUE_MARKER),
  );

  if (!state.needed) {
    if (issue?.state === "open") {
      await github.rest.issues.update({
        owner,
        repo,
        issue_number: issue.number,
        state: "closed",
      });
    }
    return;
  }

  await ensureLabel(github, owner, repo);
  const payload = {
    owner,
    repo,
    title: `[upstream-sync] ${state.upstreamSha.slice(0, 12)}`,
    body: buildIssueBody(state),
    labels: [LABEL],
  };

  if (issue) {
    await github.rest.issues.update({
      ...payload,
      issue_number: issue.number,
      state: "open",
    });
  } else {
    await github.rest.issues.create(payload);
  }
}

async function run({ github, context, input }) {
  await reconcileIssue({
    github,
    owner: context.repo.owner,
    repo: context.repo.repo,
    state: input,
  });
}

module.exports = {
  ISSUE_MARKER,
  buildIssueBody,
  reconcileIssue,
  run,
};

const REVIEW_CONTEXT = "codex/review";
const GATE_CONTEXT = "automation/gate";

function isSynchronizationPull(labels, headRef) {
  return (
    labels.includes("automation:upstream-sync") ||
    headRef === "sync-upstream" ||
    headRef.startsWith("codex/upstream-sync-")
  );
}

function evaluateGate(input) {
  if (!input.isSync) {
    return { state: "success", description: "普通 PR 不进入 upstream 自动审查门禁" };
  }
  if (!input.isOwnHead) {
    return { state: "failure", description: "同步 PR 必须来自 Alllynnn/llm_wiki" };
  }
  if (input.isDraft) {
    return { state: "pending", description: "同步 PR 仍为草稿" };
  }

  const labels = new Set(input.labels || []);
  if (labels.has("codex:blocked") || labels.has("codex:changes-requested")) {
    return { state: "failure", description: "同步 PR 处于阻塞或待修改状态" };
  }
  if (!labels.has("automation:upstream-sync")) {
    return { state: "pending", description: "同步 PR 缺少自动化识别标签" };
  }
  if (!labels.has("codex:review-ready") || !labels.has("codex:reviewed")) {
    return { state: "pending", description: "等待当前提交的独立 Codex 审查" };
  }
  if (input.reviewState !== "success") {
    return { state: "pending", description: "当前提交尚无成功的 codex/review 状态" };
  }
  return { state: "success", description: "当前提交已通过 upstream 自动审查门禁" };
}

async function removeReviewedLabel(github, owner, repo, number, labels) {
  if (!labels.includes("codex:reviewed")) return labels;
  try {
    await github.rest.issues.removeLabel({
      owner,
      repo,
      issue_number: number,
      name: "codex:reviewed",
    });
  } catch (error) {
    if (error.status !== 404) throw error;
  }
  return labels.filter((label) => label !== "codex:reviewed");
}

async function disableAutoMerge(github, pull) {
  if (!pull.auto_merge) return;
  await github.graphql(
    "mutation($id:ID!){disablePullRequestAutoMerge(input:{pullRequestId:$id}){clientMutationId}}",
    { id: pull.node_id },
  );
}

async function run({ github, context }) {
  const { owner, repo } = context.repo;
  const number = context.payload.pull_request.number;
  const response = await github.rest.pulls.get({
    owner,
    repo,
    pull_number: number,
  });
  const pull = response.data;
  let labels = pull.labels.map((label) => label.name);
  const isSync = isSynchronizationPull(labels, pull.head.ref);

  if (isSync && context.payload.action === "synchronize") {
    labels = await removeReviewedLabel(github, owner, repo, number, labels);
  }

  const statuses = await github.rest.repos.getCombinedStatusForRef({
    owner,
    repo,
    ref: pull.head.sha,
  });
  const reviewState = statuses.data.statuses.find(
    (status) => status.context === REVIEW_CONTEXT,
  )?.state;
  const result = evaluateGate({
    isSync,
    isOwnHead: pull.head.repo.full_name === `${owner}/${repo}`,
    isDraft: pull.draft,
    labels,
    reviewState,
  });

  if (isSync && result.state !== "success") {
    await disableAutoMerge(github, pull);
  }

  await github.rest.repos.createCommitStatus({
    owner,
    repo,
    sha: pull.head.sha,
    state: result.state,
    context: GATE_CONTEXT,
    description: result.description,
    target_url: pull.html_url,
  });
}

module.exports = {
  REVIEW_CONTEXT,
  GATE_CONTEXT,
  evaluateGate,
  isSynchronizationPull,
  run,
};

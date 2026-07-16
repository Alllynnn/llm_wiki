const test = require("node:test");
const assert = require("node:assert/strict");
const {
  evaluateGate,
  isSynchronizationPull,
  run,
} = require("./automation-gate.cjs");

test("ordinary pull requests pass without codex review", () => {
  assert.equal(evaluateGate({ isSync: false }).state, "success");
});

test("sync branches remain gated when the routing label is removed", () => {
  assert.equal(isSynchronizationPull([], "sync-upstream"), true);
  assert.equal(
    isSynchronizationPull([], "codex/upstream-sync-03e46fc"),
    true,
  );
  const result = evaluateGate({
    isSync: true,
    isOwnHead: true,
    isDraft: false,
    labels: ["codex:review-ready", "codex:reviewed"],
    reviewState: "success",
  });
  assert.equal(result.state, "pending");
});

test("sync pull request waits for a review bound to current sha", () => {
  const result = evaluateGate({
    isSync: true,
    isOwnHead: true,
    isDraft: false,
    labels: ["automation:upstream-sync", "codex:review-ready"],
    reviewState: undefined,
  });
  assert.equal(result.state, "pending");
});

test("blocked sync pull request fails closed", () => {
  const result = evaluateGate({
    isSync: true,
    isOwnHead: true,
    isDraft: false,
    labels: ["automation:upstream-sync", "codex:blocked"],
    reviewState: "success",
  });
  assert.equal(result.state, "failure");
});

test("reviewed sync pull request passes only on current sha", () => {
  const result = evaluateGate({
    isSync: true,
    isOwnHead: true,
    isDraft: false,
    labels: [
      "automation:upstream-sync",
      "codex:review-ready",
      "codex:reviewed",
    ],
    reviewState: "success",
  });
  assert.equal(result.state, "success");
});

test("new sync commit invalidates reviewed label and auto merge", async () => {
  const calls = [];
  const github = {
    graphql: async () => calls.push(["disableAutoMerge"]),
    rest: {
      pulls: {
        get: async () => ({
          data: {
            number: 1,
            node_id: "PR_node",
            draft: false,
            html_url: "https://github.com/Alllynnn/llm_wiki/pull/1",
            auto_merge: { enabled_by: { login: "Alllynnn" } },
            head: {
              sha: "new-head-sha",
              ref: "sync-upstream",
              repo: { full_name: "Alllynnn/llm_wiki" },
            },
            labels: [
              { name: "automation:upstream-sync" },
              { name: "codex:review-ready" },
              { name: "codex:reviewed" },
            ],
          },
        }),
      },
      issues: {
        removeLabel: async () => calls.push(["removeReviewedLabel"]),
      },
      repos: {
        getCombinedStatusForRef: async () => ({
          data: { statuses: [{ context: "codex/review", state: "success" }] },
        }),
        createCommitStatus: async (args) =>
          calls.push(["createGateStatus", args.state]),
      },
    },
  };
  const context = {
    repo: { owner: "Alllynnn", repo: "llm_wiki" },
    payload: { action: "synchronize", pull_request: { number: 1 } },
  };

  await run({ github, context });

  assert.deepEqual(calls, [
    ["removeReviewedLabel"],
    ["disableAutoMerge"],
    ["createGateStatus", "pending"],
  ]);
});

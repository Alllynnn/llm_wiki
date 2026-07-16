const test = require("node:test");
const assert = require("node:assert/strict");
const { buildIssueBody, reconcileIssue } = require("./upstream-watch.cjs");

function githubMock(existing = []) {
  const calls = [];
  return {
    calls,
    rest: {
      issues: {
        listForRepo: async () => ({ data: existing }),
        createLabel: async (args) => calls.push(["createLabel", args]),
        create: async (args) => calls.push(["create", args]),
        update: async (args) => calls.push(["update", args]),
      },
    },
  };
}

const state = {
  needed: true,
  upstreamSha: "03e46fc1234567890",
  baseSha: "144237b1234567890",
  commitCount: 61,
  compareUrl:
    "https://github.com/Alllynnn/llm_wiki/compare/main...nashsu:llm_wiki:main",
};

test("buildIssueBody records immutable synchronization evidence", () => {
  const body = buildIssueBody(state);
  assert.match(body, /<!-- codex-upstream-sync -->/);
  assert.match(body, /03e46fc1234567890/);
  assert.match(body, /61/);
});

test("creates one issue when upstream work is needed", async () => {
  const github = githubMock();
  await reconcileIssue({ github, owner: "Alllynnn", repo: "llm_wiki", state });
  assert.equal(
    github.calls.filter(([name]) => name === "create").length,
    1,
  );
});

test("updates the marker issue instead of creating a duplicate", async () => {
  const github = githubMock([
    { number: 8, state: "open", body: "<!-- codex-upstream-sync -->" },
  ]);
  await reconcileIssue({ github, owner: "Alllynnn", repo: "llm_wiki", state });
  assert.equal(
    github.calls.filter(([name]) => name === "create").length,
    0,
  );
  assert.equal(
    github.calls.filter(([name]) => name === "update").length,
    1,
  );
});

test("closes the marker issue when fork main contains upstream", async () => {
  const github = githubMock([
    { number: 8, state: "open", body: "<!-- codex-upstream-sync -->" },
  ]);
  await reconcileIssue({
    github,
    owner: "Alllynnn",
    repo: "llm_wiki",
    state: { ...state, needed: false },
  });
  const update = github.calls.find(([name]) => name === "update");
  assert.equal(update[1].state, "closed");
});

import { beforeEach, describe, expect, it, vi } from "vitest"

const { apiCall } = vi.hoisted(() => ({ apiCall: vi.fn() }))
vi.mock("@/lib/api", () => ({ apiCall }))

import { searchFaithfulSources } from "./faithful-source-search"

describe("searchFaithfulSources", () => {
  beforeEach(() => apiCall.mockReset())

  it("requests raw-source-only content and normalizes returned paths", async () => {
    apiCall.mockResolvedValue({
      results: [{
        path: "raw/sources/notes.org",
        title: "notes.org",
        snippet: "exact wording",
        titleMatch: false,
        score: 12,
        content: "Exact wording from the source.",
      }],
    })

    await expect(searchFaithfulSources("/projects/demo/", "exact wording", 8)).resolves.toEqual([
      expect.objectContaining({ path: "/projects/demo/raw/sources/notes.org" }),
    ])
    expect(apiCall).toHaveBeenCalledWith("POST", "/api/v1/sources/search", {
      project_path: "/projects/demo",
      query: "exact wording",
      top_k: 8,
      include_content: true,
    })
  })

  it("does not call the server for an empty query", async () => {
    await expect(searchFaithfulSources("/projects/demo", "  ")).resolves.toEqual([])
    expect(apiCall).not.toHaveBeenCalled()
  })

  it("forwards cancellation to the authenticated source request", async () => {
    apiCall.mockResolvedValue({ results: [] })
    const controller = new AbortController()

    await searchFaithfulSources("/projects/demo", "policy", 10, controller.signal)

    expect(apiCall).toHaveBeenCalledWith(
      "POST",
      "/api/v1/sources/search",
      expect.objectContaining({ query: "policy" }),
      { signal: controller.signal },
    )
  })

  it("rejects truncated scans instead of presenting partial evidence as complete", async () => {
    apiCall.mockResolvedValueOnce({
      results: [],
      truncated: true,
      truncationReason: "byte_budget",
    })

    await expect(searchFaithfulSources("/projects/demo", "policy", 10)).rejects.toThrow(
      "Original source search stopped at its byte budget",
    )
  })
})

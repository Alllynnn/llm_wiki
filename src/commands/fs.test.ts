import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiCall: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
  apiCall: mocks.apiCall,
  fileRawUrl: (projectPath: string, filePath: string) =>
    `/api/v1/files/raw?project_path=${encodeURIComponent(projectPath)}&path=${encodeURIComponent(filePath)}`,
}))

import { createDirectory, writeFile, writeFileAtomic } from "./fs"

describe("fs command path guards", () => {
  beforeEach(() => {
    mocks.apiCall.mockReset()
  })

  it("rejects relative write paths before calling apiCall", async () => {
    await expect(writeFile("wiki/sources/stray.md", "content")).rejects.toThrow(
      /absolute path/i,
    )

    expect(mocks.apiCall).not.toHaveBeenCalled()
  })

  it("rejects relative atomic write paths before calling apiCall", async () => {
    await expect(writeFileAtomic("wiki/sources/stray.md", "content")).rejects.toThrow(
      /absolute path/i,
    )

    expect(mocks.apiCall).not.toHaveBeenCalled()
  })

  it("rejects relative directory paths before calling apiCall", async () => {
    await expect(createDirectory("wiki/sources")).rejects.toThrow(/absolute path/i)

    expect(mocks.apiCall).not.toHaveBeenCalled()
  })

  it("allows absolute write paths via the browser HTTP API", async () => {
    await writeFile("/tmp/project/wiki/sources/page.md", "content")
    expect(mocks.apiCall).toHaveBeenCalledWith("POST", "/api/v1/fs/write", {
      path: "/tmp/project/wiki/sources/page.md",
      content: "content",
    })
  })
})

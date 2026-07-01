import { describe, expect, it } from "vitest"
import {
  isLarkSourcePath,
  larkSourceManifestPath,
  parseLarkSourceManifestLine,
  validateLarkSourceRecord,
} from "./lark-source-contract"

describe("lark source handoff contract", () => {
  it("recognizes project-relative Lark source paths", () => {
    expect(isLarkSourcePath("raw/sources/lark/doc-1/index.md")).toBe(true)
    expect(isLarkSourcePath("raw/sources/manual.md")).toBe(false)
  })

  it("builds a project-local manifest path", () => {
    expect(larkSourceManifestPath("C:\\wiki\\project")).toBe(
      "C:/wiki/project/.llm-wiki/sources/lark-sources.jsonl",
    )
  })

  it("validates and normalizes a skill-produced source record", () => {
    const result = validateLarkSourceRecord({
      channel: "lark",
      sourcePath: "/raw/sources/lark/doc-1/page.md",
      contentHash: "abc123",
      importedAt: "2026-06-26T10:00:00.000Z",
      originalUrl: " https://example.feishu.cn/wiki/abc ",
      resourceType: "wiki",
      exporter: { name: "codex-lark-export", version: "1.0.0" },
    })

    expect(result.ok).toBe(true)
    expect(result.record).toMatchObject({
      channel: "lark",
      sourcePath: "raw/sources/lark/doc-1/page.md",
      originalUrl: "https://example.feishu.cn/wiki/abc",
      resourceType: "wiki",
    })
  })

  it("rejects invalid or unsafe skill output without throwing", () => {
    const result = validateLarkSourceRecord({
      channel: "lark",
      sourcePath: "raw/sources/lark/../outside.md",
      contentHash: "",
      importedAt: "not-a-date",
    })

    expect(result.ok).toBe(false)
    expect(result.errors.length).toBeGreaterThan(0)
  })

  it("rejects malformed manifest lines", () => {
    expect(parseLarkSourceManifestLine("{nope").ok).toBe(false)
  })
})

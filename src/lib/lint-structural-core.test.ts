import { describe, expect, it } from "vitest"
import { computeStructuralLint, type StructuralLintPage } from "./lint-structural-core"

function page(index: number, total: number): StructuralLintPage {
  return {
    shortName: `entities/page-${index}.md`,
    slug: `entities/page-${index}`,
    title: `Page ${index}`,
    outlinks: index + 1 < total ? [`entities/page-${index + 1}`] : ["entities/page-0"],
    tokens: ["shared", `topic-${index}`],
  }
}

describe("computeStructuralLint", () => {
  it("finds typo candidates without scanning unrelated page names", () => {
    const pages = [
      { ...page(0, 2), shortName: "transformer.md", slug: "transformer", title: "Transformer", outlinks: [] },
      { ...page(1, 2), shortName: "attention.md", slug: "attention", title: "Attention", outlinks: ["transfomer"] },
    ]
    const broken = computeStructuralLint(pages).find((finding) => finding.type === "broken-link")
    expect(broken?.suggestedTarget).toBe("transformer.md")
  })

  it("does not prune a closer typo candidate behind 64 containing decoys", () => {
    const source = {
      ...page(0, 1),
      shortName: "source.md",
      slug: "source",
      title: "Source",
      outlinks: ["alpha-betx"],
    }
    const decoys = Array.from({ length: 65 }, (_, index) => ({
      ...page(index + 1, 67),
      shortName: `alpha-betx-long-${index}.md`,
      slug: `alpha-betx-long-${index}`,
      title: `Alpha Betx Long ${index}`,
      outlinks: [],
    }))
    const closest = {
      ...page(66, 67),
      shortName: "alpha-beta.md",
      slug: "alpha-beta",
      title: "Alpha Beta",
      outlinks: [],
    }

    const broken = computeStructuralLint([source, ...decoys, closest])
      .find((finding) => finding.type === "broken-link" && finding.brokenTarget === "alpha-betx")

    expect(broken?.suggestedTarget).toBe("alpha-beta.md")
  })

  it("indexes title basenames with the same representation used for scoring", () => {
    const source = {
      ...page(0, 2),
      shortName: "source.md",
      slug: "source",
      title: "Source",
      outlinks: ["transfomer"],
    }
    const titledCandidate = {
      ...page(1, 2),
      shortName: "unrelated-model.md",
      slug: "unrelated-model",
      title: "docs/transformer",
      outlinks: [],
    }

    const broken = computeStructuralLint([source, titledCandidate])
      .find((finding) => finding.type === "broken-link")

    expect(broken?.suggestedTarget).toBe("unrelated-model.md")
  })

  it("keeps exact short-title matches available without fuzzy short-name matching", () => {
    const source = {
      ...page(0, 2),
      shortName: "source.md",
      slug: "source",
      title: "Source",
      outlinks: ["RoPE"],
    }
    const titledCandidate = {
      ...page(1, 2),
      shortName: "rotary-embedding.md",
      slug: "rotary-embedding",
      title: "RoPE",
      outlinks: [],
    }

    const broken = computeStructuralLint([source, titledCandidate])
      .find((finding) => finding.type === "broken-link")

    expect(broken?.suggestedTarget).toBe("rotary-embedding.md")
  })

  it("handles 5,000 pages without quadratic candidate expansion", () => {
    const pages = Array.from({ length: 5_000 }, (_, index) => page(index, 5_000))
    const started = performance.now()
    const findings = computeStructuralLint(pages)
    const elapsed = performance.now() - started

    expect(findings).toEqual([])
    // A generous ceiling catches accidental restoration of the old all-pairs
    // scan while remaining stable on slower CI runners.
    expect(elapsed).toBeLessThan(5_000)
  })

  it("keeps 5,000 common-fragment broken links bounded", () => {
    const pages = Array.from({ length: 5_000 }, (_, index) => ({
      ...page(index, 5_000),
      shortName: `common-target-page-${index}.md`,
      slug: `common-target-page-${index}`,
      title: `Common Target Page ${index}`,
      outlinks: ["common-target-typo"],
    }))
    const started = performance.now()
    const findings = computeStructuralLint(pages)
    const elapsed = performance.now() - started

    expect(findings.filter((finding) => finding.type === "broken-link")).toHaveLength(5_000)
    expect(elapsed).toBeLessThan(5_000)
  })

  it("can disable orphan and no-outlinks findings independently", () => {
    const pages = [
      { ...page(0, 1), shortName: "leaf.md", slug: "leaf", outlinks: [] },
    ]

    expect(computeStructuralLint(pages, undefined, { ignoreOrphan: true }))
      .toEqual([expect.objectContaining({ type: "no-outlinks" })])
    expect(computeStructuralLint(pages, undefined, { ignoreNoOutlinks: true }))
      .toEqual([expect.objectContaining({ type: "orphan" })])
  })

  it("suppresses all findings for ignored pages while retaining them as link targets", () => {
    const pages = [
      { ...page(0, 2), shortName: "folder/ignored.md", slug: "folder/ignored", outlinks: ["missing"] },
      { ...page(1, 2), shortName: "source.md", slug: "source", outlinks: ["folder/ignored"] },
    ]
    const findings = computeStructuralLint(pages, undefined, {
      ignorePages: ["wiki/folder/ignored.md"],
    })

    expect(findings.some((finding) => finding.page === "folder/ignored.md")).toBe(false)
    expect(findings.some((finding) => finding.type === "broken-link" && finding.brokenTarget === "folder/ignored")).toBe(false)
  })

  it("does not apply a top-level ignored slug to same-named nested pages", () => {
    const pages = [
      { ...page(0, 2), shortName: "foo.md", slug: "foo", outlinks: [] },
      { ...page(1, 2), shortName: "archive/foo.md", slug: "archive/foo", outlinks: [] },
    ]
    const findings = computeStructuralLint(pages, undefined, { ignorePages: ["foo"] })

    expect(findings.some((finding) => finding.page === "foo.md")).toBe(false)
    expect(findings.some((finding) => finding.page === "archive/foo.md")).toBe(true)
  })
})

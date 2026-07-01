import { describe, expect, it } from "vitest"
import {
  buildProjectPurposeContext,
  buildProjectSchemaContext,
  groupProjectsByCategory,
  normalizeProjectMetadata,
} from "./knowledge-platform"
import type { WikiProject } from "@/types/wiki"

describe("knowledge platform metadata", () => {
  it("normalizes missing metadata to the general category", () => {
    expect(normalizeProjectMetadata(null)).toMatchObject({
      categoryId: "general",
      projectKindId: "general",
    })
  })

  it("falls back to a category-compatible project kind", () => {
    expect(normalizeProjectMetadata({
      categoryId: "annotation",
      projectKindId: "web-crawler",
      businessContext: "  audio collection  ",
      sourcePolicy: "",
    })).toMatchObject({
      categoryId: "annotation",
      projectKindId: "language-audio",
      businessContext: "audio collection",
    })
  })

  it("keeps rubric annotation projects in the annotation category", () => {
    expect(normalizeProjectMetadata({
      categoryId: "annotation",
      projectKindId: "rubric",
    })).toMatchObject({
      categoryId: "annotation",
      projectKindId: "rubric",
    })
  })

  it("groups legacy and categorized projects without requiring migration first", () => {
    const projects: WikiProject[] = [
      { id: "legacy", name: "Legacy", path: "/legacy" },
      {
        id: "crawler",
        name: "Crawler",
        path: "/crawler",
        metadata: normalizeProjectMetadata({
          categoryId: "crawler",
          projectKindId: "web-crawler",
        }),
      },
    ]

    const grouped = groupProjectsByCategory(projects)

    expect(grouped.general.map((project) => project.id)).toEqual(["legacy"])
    expect(grouped.crawler.map((project) => project.id)).toEqual(["crawler"])
  })

  it("normalizes removed pilot category metadata to the general category", () => {
    const legacyPilotMetadata = {
      categoryId: "dogfooding",
      projectKindId: "internal-pilot",
    } as unknown as Parameters<typeof normalizeProjectMetadata>[0]

    expect(normalizeProjectMetadata(legacyPilotMetadata)).toMatchObject({
      categoryId: "general",
      projectKindId: "general",
    })
  })

  it("seeds purpose and schema with business-specific guidance", () => {
    const metadata = normalizeProjectMetadata({
      categoryId: "annotation",
      projectKindId: "video",
      businessContext: "Video annotation delivery",
    })

    expect(buildProjectPurposeContext(metadata)).toContain("标注项目沉淀重点")
    expect(buildProjectPurposeContext(metadata)).toContain("Video annotation delivery")
    expect(buildProjectSchemaContext(metadata)).toContain("标注项目知识类型")
  })
})

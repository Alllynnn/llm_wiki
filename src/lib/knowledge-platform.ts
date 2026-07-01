import type { WikiProject } from "@/types/wiki"

export type KnowledgeCategoryId =
  | "annotation"
  | "crawler"
  | "project-assets"
  | "general"

export type KnowledgeProjectKindId =
  | "language-audio"
  | "video"
  | "image-text"
  | "rubric"
  | "web-crawler"
  | "project-ops"
  | "general"

export interface KnowledgeCategory {
  id: KnowledgeCategoryId
  labelKey: string
  descriptionKey: string
}

export interface KnowledgeProjectKind {
  id: KnowledgeProjectKindId
  categoryId: KnowledgeCategoryId
  labelKey: string
}

export interface BusinessProjectMetadata {
  categoryId: KnowledgeCategoryId
  projectKindId: KnowledgeProjectKindId
  businessContext: string
  sourcePolicy: string
}

interface BusinessSeed {
  purpose: string
  schema: string
}

export type NormalizedWikiProject = WikiProject & {
  metadata: BusinessProjectMetadata
}

export const DEFAULT_PROJECT_METADATA: BusinessProjectMetadata = {
  categoryId: "general",
  projectKindId: "general",
  businessContext: "",
  sourcePolicy: "原始项目资料统一保留在 raw/sources/，可复用知识沉淀到 wiki/。",
}

export const KNOWLEDGE_CATEGORIES: KnowledgeCategory[] = [
  {
    id: "annotation",
    labelKey: "knowledge.categories.annotation.name",
    descriptionKey: "knowledge.categories.annotation.description",
  },
  {
    id: "crawler",
    labelKey: "knowledge.categories.crawler.name",
    descriptionKey: "knowledge.categories.crawler.description",
  },
  {
    id: "project-assets",
    labelKey: "knowledge.categories.projectAssets.name",
    descriptionKey: "knowledge.categories.projectAssets.description",
  },
  {
    id: "general",
    labelKey: "knowledge.categories.general.name",
    descriptionKey: "knowledge.categories.general.description",
  },
]

export const KNOWLEDGE_PROJECT_KINDS: KnowledgeProjectKind[] = [
  { id: "language-audio", categoryId: "annotation", labelKey: "knowledge.kinds.languageAudio" },
  { id: "video", categoryId: "annotation", labelKey: "knowledge.kinds.video" },
  { id: "image-text", categoryId: "annotation", labelKey: "knowledge.kinds.imageText" },
  { id: "rubric", categoryId: "annotation", labelKey: "knowledge.kinds.rubric" },
  { id: "web-crawler", categoryId: "crawler", labelKey: "knowledge.kinds.webCrawler" },
  { id: "project-ops", categoryId: "project-assets", labelKey: "knowledge.kinds.projectOps" },
  { id: "general", categoryId: "general", labelKey: "knowledge.kinds.general" },
]

const BUSINESS_SEEDS: Record<KnowledgeCategoryId, BusinessSeed> = {
  annotation: {
    purpose: [
      "## 标注项目沉淀重点",
      "",
      "- 项目目标、客户口径、标注范围和交付标准。",
      "- 采标/标注规则、质检规则、返工原因和边界样例。",
      "- 可复用 SOP、质检 checklist、培训材料和项目复盘。",
    ].join("\n"),
    schema: [
      "## 标注项目知识类型",
      "",
      "- `wiki/workflows/`：采标、标注、质检、返工、交付流程。",
      "- `wiki/rules/`：标注规则、验收规则、客户口径。",
      "- `wiki/risks/`：高频风险、争议样例、返工原因。",
      "- `wiki/synthesis/`：可复用 SOP、培训总结和复盘。",
    ].join("\n"),
  },
  crawler: {
    purpose: [
      "## 爬虫项目沉淀重点",
      "",
      "- 目标站点、字段口径、采集范围、数据清洗和交付约束。",
      "- 反爬策略、补跑记录、异常样例和质量校验规则。",
      "- 可复用采集方案、字段映射、问题定位路径和项目复盘。",
    ].join("\n"),
    schema: [
      "## 爬虫项目知识类型",
      "",
      "- `wiki/workflows/`：采集、清洗、校验、补跑、交付流程。",
      "- `wiki/entities/`：目标站点、字段、接口、数据集和工具。",
      "- `wiki/risks/`：反爬、字段漂移、缺失、重复和合规风险。",
      "- `wiki/synthesis/`：可复用方案、排障手册和复盘。",
    ].join("\n"),
  },
  "project-assets": {
    purpose: [
      "## 项目资产沉淀重点",
      "",
      "- 项目管理流程、交付模板、客户沟通口径和复盘材料。",
      "- 可跨项目复用的检查清单、会议纪要结构和风险清单。",
    ].join("\n"),
    schema: [
      "## 项目资产知识类型",
      "",
      "- `wiki/templates/`：交付模板、沟通模板和会议模板。",
      "- `wiki/checklists/`：启动、执行、质检、交付和复盘检查清单。",
      "- `wiki/stakeholders/`：客户、团队、角色和协作关系。",
      "- `wiki/synthesis/`：跨项目方法论和经验总结。",
    ].join("\n"),
  },
  general: {
    purpose: [
      "## 通用知识库沉淀重点",
      "",
      "- 明确资料范围、核心问题、可复用结论和后续行动。",
      "- 将原始资料整理为可检索、可追溯、可复用的 wiki 知识。",
    ].join("\n"),
    schema: [
      "## 通用知识类型",
      "",
      "- 优先沉淀实体、概念、资料、问题、对比和综合总结。",
      "- 对不确定内容建立 query 页面，并在后续资料中持续更新。",
    ].join("\n"),
  },
}

export function normalizeProjectMetadata(
  metadata: Partial<BusinessProjectMetadata> | null | undefined,
): BusinessProjectMetadata {
  const categoryId = isCategoryId(metadata?.categoryId)
    ? metadata.categoryId
    : DEFAULT_PROJECT_METADATA.categoryId
  const allowedKinds = getProjectKindsForCategory(categoryId)
  const projectKindId = allowedKinds.some((kind) => kind.id === metadata?.projectKindId)
    ? metadata?.projectKindId as KnowledgeProjectKindId
    : allowedKinds[0]?.id ?? DEFAULT_PROJECT_METADATA.projectKindId
  return {
    categoryId,
    projectKindId,
    businessContext: typeof metadata?.businessContext === "string"
      ? metadata.businessContext.trim()
      : DEFAULT_PROJECT_METADATA.businessContext,
    sourcePolicy: typeof metadata?.sourcePolicy === "string" && metadata.sourcePolicy.trim().length > 0
      ? metadata.sourcePolicy.trim()
      : DEFAULT_PROJECT_METADATA.sourcePolicy,
  }
}

export function getProjectKindsForCategory(
  categoryId: KnowledgeCategoryId,
): KnowledgeProjectKind[] {
  const kinds = KNOWLEDGE_PROJECT_KINDS.filter((kind) => kind.categoryId === categoryId)
  return kinds.length > 0 ? kinds : KNOWLEDGE_PROJECT_KINDS.filter((kind) => kind.id === "general")
}

export function attachNormalizedMetadata(project: WikiProject): NormalizedWikiProject {
  return {
    ...project,
    metadata: normalizeProjectMetadata(project.metadata),
  }
}

export function groupProjectsByCategory(
  projects: WikiProject[],
): Record<KnowledgeCategoryId, NormalizedWikiProject[]> {
  const grouped = emptyCategoryGroups()
  for (const project of projects.map(attachNormalizedMetadata)) {
    grouped[project.metadata.categoryId].push(project)
  }
  return grouped
}

export function buildProjectPurposeContext(
  metadata: BusinessProjectMetadata,
): string {
  const normalized = normalizeProjectMetadata(metadata)
  const seed = businessSeedForMetadata(normalized)
  return [
    "# LLM Wiki 平台上下文",
    "",
    `- 知识库分类：${normalized.categoryId}`,
    `- 项目类型：${normalized.projectKindId}`,
    `- 资料策略：${normalized.sourcePolicy}`,
    normalized.businessContext ? `- 业务上下文：${normalized.businessContext}` : "",
    "",
    seed.purpose,
  ].join("\n")
}

export function buildProjectSchemaContext(
  metadata: BusinessProjectMetadata,
): string {
  const normalized = normalizeProjectMetadata(metadata)
  const seed = businessSeedForMetadata(normalized)
  return [
    "# LLM Wiki 平台业务规则",
    "",
    "本项目是通用 LLM Wiki 平台中的一个业务知识库。知识提取时必须保留原始资料来源，并优先沉淀能跨项目复用的流程、规则、风险和经验。",
    "",
    seed.schema,
  ].join("\n")
}

function businessSeedForMetadata(metadata: BusinessProjectMetadata): BusinessSeed {
  return BUSINESS_SEEDS[metadata.categoryId] ?? BUSINESS_SEEDS.general
}

function emptyCategoryGroups(): Record<KnowledgeCategoryId, NormalizedWikiProject[]> {
  return {
    annotation: [],
    crawler: [],
    "project-assets": [],
    general: [],
  }
}

function isCategoryId(value: unknown): value is KnowledgeCategoryId {
  return KNOWLEDGE_CATEGORIES.some((category) => category.id === value)
}

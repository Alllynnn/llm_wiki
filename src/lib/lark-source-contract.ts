import { normalizePath } from "@/lib/path-utils"

export const LARK_SOURCE_CHANNEL = "lark"
export const LARK_SOURCE_ROOT = "raw/sources/lark"
export const LARK_SOURCE_MANIFEST = ".llm-wiki/sources/lark-sources.jsonl"

export type LarkSourceResourceType =
  | "doc"
  | "wiki"
  | "message"
  | "file"
  | "export"
  | "unknown"

export interface LarkSourceExporterInfo {
  name?: string
  version?: string
}

export interface LarkSourceManifestRecord {
  channel: typeof LARK_SOURCE_CHANNEL
  sourcePath: string
  contentHash: string
  importedAt: string
  originalUrl?: string
  originalId?: string
  title?: string
  resourceType?: LarkSourceResourceType
  exporter?: LarkSourceExporterInfo
}

export interface LarkSourceValidationResult {
  ok: boolean
  errors: string[]
  record?: LarkSourceManifestRecord
}

export function larkSourceManifestPath(projectPath: string): string {
  return `${normalizePath(projectPath).replace(/\/+$/, "")}/${LARK_SOURCE_MANIFEST}`
}

export function isLarkSourcePath(path: string): boolean {
  const normalized = normalizePath(path).replace(/^\/+/, "")
  return normalized === LARK_SOURCE_ROOT || normalized.startsWith(`${LARK_SOURCE_ROOT}/`)
}

export function validateLarkSourceRecord(value: unknown): LarkSourceValidationResult {
  if (!value || typeof value !== "object") {
    return { ok: false, errors: ["record must be an object"] }
  }

  const input = value as Record<string, unknown>
  const errors: string[] = []
  const channel = input.channel
  const sourcePath = typeof input.sourcePath === "string"
    ? normalizePath(input.sourcePath).replace(/^\/+/, "")
    : ""
  const contentHash = typeof input.contentHash === "string" ? input.contentHash.trim() : ""
  const importedAt = typeof input.importedAt === "string" ? input.importedAt.trim() : ""

  if (channel !== LARK_SOURCE_CHANNEL) {
    errors.push(`channel must be "${LARK_SOURCE_CHANNEL}"`)
  }
  if (!sourcePath || sourcePath === LARK_SOURCE_ROOT || !isLarkSourcePath(sourcePath) || hasTraversalSegment(sourcePath)) {
    errors.push(`sourcePath must be under ${LARK_SOURCE_ROOT}/`)
  }
  if (!contentHash) {
    errors.push("contentHash is required")
  }
  if (!importedAt || Number.isNaN(Date.parse(importedAt))) {
    errors.push("importedAt must be an ISO-compatible date string")
  }

  if (errors.length > 0) {
    return { ok: false, errors }
  }

  return {
    ok: true,
    errors: [],
    record: {
      channel: LARK_SOURCE_CHANNEL,
      sourcePath,
      contentHash,
      importedAt,
      originalUrl: optionalString(input.originalUrl),
      originalId: optionalString(input.originalId),
      title: optionalString(input.title),
      resourceType: normalizeResourceType(input.resourceType),
      exporter: normalizeExporter(input.exporter),
    },
  }
}

export function parseLarkSourceManifestLine(line: string): LarkSourceValidationResult {
  try {
    return validateLarkSourceRecord(JSON.parse(line))
  } catch {
    return { ok: false, errors: ["manifest line must be valid JSON"] }
  }
}

function hasTraversalSegment(path: string): boolean {
  return normalizePath(path).split("/").some((segment) => segment === "..")
}

function optionalString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : undefined
}

function normalizeResourceType(value: unknown): LarkSourceResourceType | undefined {
  if (
    value === "doc" ||
    value === "wiki" ||
    value === "message" ||
    value === "file" ||
    value === "export" ||
    value === "unknown"
  ) {
    return value
  }
  return undefined
}

function normalizeExporter(value: unknown): LarkSourceExporterInfo | undefined {
  if (!value || typeof value !== "object") return undefined
  const input = value as Record<string, unknown>
  const exporter = {
    name: optionalString(input.name),
    version: optionalString(input.version),
  }
  return exporter.name || exporter.version ? exporter : undefined
}

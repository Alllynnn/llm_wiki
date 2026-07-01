/**
 * Project identity: stable UUID per project + global registry mapping
 * `UUID → current filesystem path`.
 *
 * Why: absolute paths are unstable (users move / rename project folders).
 * Queue tasks reference projects by UUID and look up the current path
 * via the registry at run time, so a moved folder doesn't orphan tasks.
 *
 * Storage:
 * - Per-project identity: `{project}/.llm-wiki/project.json`
 *     `{ "id": "<uuid>", "createdAt": <ms> }`
 * - Global registry: Tauri plugin-store `app-state.json` key `projectRegistry`
 *     `{ [id]: { id, path, name, lastOpened } }`
 */

import { getConfigKey, setConfigKey } from "@/lib/user-config"
import { readFile, writeFile } from "@/commands/fs"
import { normalizePath } from "@/lib/path-utils"
import {
  normalizeProjectMetadata,
  type BusinessProjectMetadata,
} from "@/lib/knowledge-platform"

const REGISTRY_KEY = "projectRegistry"

export interface ProjectIdentity {
  id: string
  createdAt: number
  metadata?: Partial<BusinessProjectMetadata>
}

export interface ProjectRegistryEntry {
  id: string
  path: string       // latest known filesystem path (normalized forward slashes)
  name: string
  lastOpened: number
  metadata: BusinessProjectMetadata
}

export type ProjectRegistry = Record<string, ProjectRegistryEntry>

// ── Per-project identity (reads/creates `.llm-wiki/project.json`) ─────────

function identityPath(projectPath: string): string {
  return `${normalizePath(projectPath)}/.llm-wiki/project.json`
}

/**
 * Return the project's stable UUID. Generates + writes one on first call
 * for a project that doesn't have `.llm-wiki/project.json` yet.
 */
export async function ensureProjectId(projectPath: string): Promise<string> {
  const path = identityPath(projectPath)
  try {
    const raw = await readFile(path)
    const parsed = JSON.parse(raw) as ProjectIdentity
    if (parsed?.id && typeof parsed.id === "string") {
      return parsed.id
    }
  } catch {
    // missing or corrupt — fall through to create
  }
  const identity: ProjectIdentity = {
    id: crypto.randomUUID(),
    createdAt: Date.now(),
  }
  try {
    await writeFile(path, JSON.stringify(identity, null, 2))
  } catch (err) {
    console.warn("[project-identity] failed to write identity file:", err)
  }
  return identity.id
}

export async function loadProjectMetadata(
  projectPath: string,
): Promise<BusinessProjectMetadata> {
  try {
    const raw = await readFile(identityPath(projectPath))
    const parsed = JSON.parse(raw) as ProjectIdentity
    return normalizeProjectMetadata(parsed.metadata)
  } catch {
    return normalizeProjectMetadata(null)
  }
}

export async function saveProjectMetadata(
  projectPath: string,
  metadata: BusinessProjectMetadata,
): Promise<BusinessProjectMetadata> {
  const path = identityPath(projectPath)
  const normalized = normalizeProjectMetadata(metadata)
  let identity: ProjectIdentity = {
    id: crypto.randomUUID(),
    createdAt: Date.now(),
  }
  try {
    identity = JSON.parse(await readFile(path)) as ProjectIdentity
  } catch {
    // Missing or invalid identity is repaired below.
  }
  const next: ProjectIdentity = {
    id: typeof identity.id === "string" ? identity.id : crypto.randomUUID(),
    createdAt: typeof identity.createdAt === "number" ? identity.createdAt : Date.now(),
    metadata: normalized,
  }
  await writeFile(path, JSON.stringify(next, null, 2))
  return normalized
}

// ── Global registry (user-config via /api/v1/config) ─────────────────────

export async function loadRegistry(): Promise<ProjectRegistry> {
  try {
    const registry = await getConfigKey<ProjectRegistry>(REGISTRY_KEY)
    return registry ?? {}
  } catch {
    return {}
  }
}

async function saveRegistry(registry: ProjectRegistry): Promise<void> {
  await setConfigKey(REGISTRY_KEY, registry)
}

/**
 * Create or update the registry entry for this project. Call on open /
 * create / switch so the path always reflects the latest known location.
 */
export async function upsertProjectInfo(
  id: string,
  path: string,
  name: string,
  metadata?: BusinessProjectMetadata,
): Promise<void> {
  const registry = await loadRegistry()
  const normalized = normalizeProjectMetadata(
    metadata ?? registry[id]?.metadata ?? await loadProjectMetadata(path),
  )
  registry[id] = {
    id,
    path: normalizePath(path),
    name,
    lastOpened: Date.now(),
    metadata: normalized,
  }
  await saveRegistry(registry)
}

/**
 * Look up the current filesystem path by UUID. Returns null if the
 * project isn't in the registry (e.g. was deleted or never opened).
 */
export async function getProjectPathById(id: string): Promise<string | null> {
  const registry = await loadRegistry()
  return registry[id]?.path ?? null
}

/**
 * Reverse lookup: given a path, find the UUID of a known project at
 * that exact location. Used by the clip watcher to translate
 * clip-server-supplied paths back to stable project ids.
 */
export async function getProjectIdByPath(path: string): Promise<string | null> {
  const normalized = normalizePath(path)
  const registry = await loadRegistry()
  for (const entry of Object.values(registry)) {
    if (entry.path === normalized) return entry.id
  }
  return null
}

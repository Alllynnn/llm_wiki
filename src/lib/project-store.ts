import { getConfigKey, setConfigKey, deleteConfigKey } from "@/lib/user-config"
import type { WikiProject } from "@/types/wiki"
import type { ApiConfig, GeneralConfig, LlmConfig, SearchApiConfig, EmbeddingConfig, MineruConfig, MultimodalConfig, OutputLanguage, ProviderConfigs, ProxyConfig, ScheduledImportConfig, SourceWatchConfig } from "@/stores/wiki-store"
import { normalizeSourceWatchConfig } from "@/lib/source-watch-config"
import { normalizePath } from "@/lib/path-utils"
import { DEFAULT_ZOOM_LEVEL, clampZoomLevel } from "@/stores/zoom-store"
import { attachNormalizedMetadata } from "@/lib/knowledge-platform"

const RECENT_PROJECTS_KEY = "recentProjects"
const LAST_PROJECT_KEY = "lastProject"

export async function getRecentProjects(): Promise<WikiProject[]> {
  const projects = await getConfigKey<WikiProject[]>(RECENT_PROJECTS_KEY)
  return (projects ?? []).map(normalizeStoredProject)
}

export async function getLastProject(): Promise<WikiProject | null> {
  const project = await getConfigKey<WikiProject>(LAST_PROJECT_KEY)
  return project ? normalizeStoredProject(project) : null
}

export async function saveLastProject(project: WikiProject): Promise<void> {
  const normalized = normalizeStoredProject(project)
  await setConfigKey(LAST_PROJECT_KEY, normalized)
  await addToRecentProjects(normalized)
}

export async function addToRecentProjects(
  project: WikiProject
): Promise<void> {
  const existing = (await getConfigKey<WikiProject[]>(RECENT_PROJECTS_KEY)) ?? []
  const filtered = existing.filter((p) => p.path !== project.path)
  const updated = [normalizeStoredProject(project), ...filtered.map(normalizeStoredProject)].slice(0, 10)
  await setConfigKey(RECENT_PROJECTS_KEY, updated)
}

const LLM_CONFIG_KEY = "llmConfig"
const PROVIDER_CONFIGS_KEY = "providerConfigs"
const ACTIVE_PRESET_KEY = "activePresetId"

export async function saveLlmConfig(config: LlmConfig): Promise<void> {
  await setConfigKey(LLM_CONFIG_KEY, config)
}

export async function loadLlmConfig(): Promise<LlmConfig | null> {
  return (await getConfigKey<LlmConfig>(LLM_CONFIG_KEY)) ?? null
}

export async function saveProviderConfigs(configs: ProviderConfigs): Promise<void> {
  await setConfigKey(PROVIDER_CONFIGS_KEY, configs)
}

export async function loadProviderConfigs(): Promise<ProviderConfigs | null> {
  return (await getConfigKey<ProviderConfigs>(PROVIDER_CONFIGS_KEY)) ?? null
}

export async function saveActivePresetId(id: string | null): Promise<void> {
  await setConfigKey(ACTIVE_PRESET_KEY, id)
}

export async function loadActivePresetId(): Promise<string | null> {
  return (await getConfigKey<string | null>(ACTIVE_PRESET_KEY)) ?? null
}

const SEARCH_API_KEY = "searchApiConfig"

export async function saveSearchApiConfig(config: SearchApiConfig): Promise<void> {
  await setConfigKey(SEARCH_API_KEY, config)
}

export async function loadSearchApiConfig(): Promise<SearchApiConfig | null> {
  return (await getConfigKey<SearchApiConfig>(SEARCH_API_KEY)) ?? null
}

const EMBEDDING_KEY = "embeddingConfig"

export async function saveEmbeddingConfig(config: EmbeddingConfig): Promise<void> {
  await setConfigKey(EMBEDDING_KEY, config)
}

export async function loadEmbeddingConfig(): Promise<EmbeddingConfig | null> {
  return (await getConfigKey<EmbeddingConfig>(EMBEDDING_KEY)) ?? null
}

const MULTIMODAL_KEY = "multimodalConfig"

export async function saveMultimodalConfig(config: MultimodalConfig): Promise<void> {
  await setConfigKey(MULTIMODAL_KEY, config)
}

export async function loadMultimodalConfig(): Promise<MultimodalConfig | null> {
  return (await getConfigKey<MultimodalConfig>(MULTIMODAL_KEY)) ?? null
}

const MINERU_KEY = "mineruConfig"

function normalizeMineruConfig(config: MineruConfig): MineruConfig {
  return {
    enabled: config.enabled === true,
    token: typeof config.token === "string" ? config.token : "",
    modelVersion: config.modelVersion === "pipeline" ? "pipeline" : "vlm",
  }
}

function normalizeZoomLevel(level: unknown): number {
  return typeof level === "number" && Number.isFinite(level)
    ? clampZoomLevel(level)
    : DEFAULT_ZOOM_LEVEL
}

export const __projectStoreTest = {
  normalizeMineruConfig,
  normalizeZoomLevel,
  normalizeStoredProject,
}

function normalizeStoredProject(project: WikiProject): WikiProject {
  return attachNormalizedMetadata(project)
}

export async function saveMineruConfig(config: MineruConfig): Promise<void> {
  await setConfigKey(MINERU_KEY, normalizeMineruConfig(config))
}

export async function loadMineruConfig(): Promise<MineruConfig | null> {
  const config = await getConfigKey<MineruConfig>(MINERU_KEY)
  return config ? normalizeMineruConfig(config) : null
}

// IMPORTANT: Keep this key in sync with the Rust setup hook
// (src-tauri/src/proxy.rs), which reads this exact field name from
// the same `app-state.json` store at app launch to translate the
// config into HTTP_PROXY / HTTPS_PROXY / NO_PROXY env vars.
const PROXY_CONFIG_KEY = "proxyConfig"

export async function saveProxyConfig(config: ProxyConfig): Promise<void> {
  await setConfigKey(PROXY_CONFIG_KEY, config)
  // Note: the server persists immediately on every PUT — no explicit flush needed.
}

export async function loadProxyConfig(): Promise<ProxyConfig | null> {
  return (await getConfigKey<ProxyConfig>(PROXY_CONFIG_KEY)) ?? null
}

// Local API server config. KEY MUST stay `apiConfig` — the Rust
// `api_server` module reads `parsed.get("apiConfig")` from this same
// `app-state.json` on every request (5s cache). Rename one side and
// the API silently goes back to "no token configured = 401 forever".
const API_CONFIG_KEY = "apiConfig"

export async function saveApiConfig(config: ApiConfig): Promise<void> {
  await setConfigKey(API_CONFIG_KEY, normalizeApiConfig(config))
  // Note: the server persists immediately on every PUT — no explicit flush needed.
}

export async function loadApiConfig(): Promise<ApiConfig | null> {
  const config = await getConfigKey<Partial<ApiConfig>>(API_CONFIG_KEY)
  return config ? normalizeApiConfig(config) : null
}

export function normalizeApiConfig(config?: Partial<ApiConfig> | null): ApiConfig {
  return {
    enabled: typeof config?.enabled === "boolean" ? config.enabled : true,
    allowUnauthenticated:
      typeof config?.allowUnauthenticated === "boolean"
        ? config.allowUnauthenticated
        : false,
    allowLanAccess:
      typeof config?.allowLanAccess === "boolean" ? config.allowLanAccess : false,
    mcpEnabled: typeof config?.mcpEnabled === "boolean" ? config.mcpEnabled : false,
    token: typeof config?.token === "string" ? config.token : "",
  }
}

const GENERAL_CONFIG_KEY = "generalConfig"

export const DEFAULT_GENERAL_CONFIG: GeneralConfig = {
  autostart: false,
  closeBehavior: "minimize",
}

export function normalizeGeneralConfig(config?: Partial<GeneralConfig> | null): GeneralConfig {
  const closeBehavior = config?.closeBehavior
  return {
    autostart: typeof config?.autostart === "boolean" ? config.autostart : false,
    closeBehavior:
      closeBehavior === "ask" || closeBehavior === "minimize" || closeBehavior === "exit"
        ? closeBehavior
        : DEFAULT_GENERAL_CONFIG.closeBehavior,
  }
}

export async function saveGeneralConfig(config: GeneralConfig): Promise<void> {
  await setConfigKey(GENERAL_CONFIG_KEY, normalizeGeneralConfig(config))
}

export async function loadGeneralConfig(): Promise<GeneralConfig> {
  const config = await getConfigKey<Partial<GeneralConfig>>(GENERAL_CONFIG_KEY)
  return normalizeGeneralConfig(config)
}

const SCHEDULED_IMPORT_KEY_PREFIX = "scheduledImportConfig:"
const SCHEDULED_IMPORT_GLOBAL_KEY = "scheduledImportConfig"

function scheduledImportKey(projectPath: string): string {
  return `${SCHEDULED_IMPORT_KEY_PREFIX}${normalizePath(projectPath)}`
}

export async function saveScheduledImportConfig(
  projectPath: string,
  config: ScheduledImportConfig,
): Promise<void> {
  await setConfigKey(scheduledImportKey(projectPath), config)
}

export async function loadScheduledImportConfig(
  projectPath: string,
): Promise<ScheduledImportConfig | null> {
  const perProject = await getConfigKey<ScheduledImportConfig>(
    scheduledImportKey(projectPath),
  )
  if (perProject) return perProject

  // Migrate from legacy global key (pre-0.4.8 official desktop behavior).
  const legacy = await getConfigKey<ScheduledImportConfig>(SCHEDULED_IMPORT_GLOBAL_KEY)
  if (!legacy) return null
  await setConfigKey(scheduledImportKey(projectPath), legacy)
  await deleteConfigKey(SCHEDULED_IMPORT_GLOBAL_KEY)
  return legacy
}

export async function removeFromRecentProjects(
  path: string
): Promise<void> {
  const existing = (await getConfigKey<WikiProject[]>(RECENT_PROJECTS_KEY)) ?? []
  const updated = existing.filter((p) => p.path !== path)
  await setConfigKey(RECENT_PROJECTS_KEY, updated)
  // ALSO clear the last-project pointer if it points at the project
  // we just removed. Without this, App.tsx's startup auto-open
  // (`getLastProject()` → `openProject()` → `saveLastProject()`)
  // re-adds the removed entry back to recents on the next launch,
  // making the delete look like it didn't take. Reported by user
  // as "deleted project comes back after restart."
  const last = await getConfigKey<WikiProject>(LAST_PROJECT_KEY)
  if (last && last.path === path) {
    await deleteConfigKey(LAST_PROJECT_KEY)
  }
}

const LANGUAGE_KEY = "language"

export async function saveLanguage(lang: string): Promise<void> {
  await setConfigKey(LANGUAGE_KEY, lang)
}

export async function loadLanguage(): Promise<string | null> {
  return (await getConfigKey<string>(LANGUAGE_KEY)) ?? null
}

const THEME_KEY = "theme"

export async function saveTheme(theme: "light" | "dark" | "system"): Promise<void> {
  await setConfigKey(THEME_KEY, theme)
}

export async function loadTheme(): Promise<"light" | "dark" | "system" | null> {
  return (await getConfigKey<"light" | "dark" | "system">(THEME_KEY)) ?? null
}

const OUTPUT_LANGUAGE_KEY = "outputLanguage"
const PROJECT_OUTPUT_LANGUAGE_KEY = "projectOutputLanguages"
const PROJECT_FILE_SYNC_KEY = "projectFileSyncEnabled"
const SOURCE_WATCH_CONFIG_KEY = "sourceWatchConfig"

export async function saveOutputLanguage(lang: OutputLanguage, projectId?: string): Promise<void> {
  if (projectId) {
    const existing = (await getConfigKey<Record<string, OutputLanguage>>(PROJECT_OUTPUT_LANGUAGE_KEY)) ?? {}
    await setConfigKey(PROJECT_OUTPUT_LANGUAGE_KEY, { ...existing, [projectId]: lang })
  }
  await setConfigKey(OUTPUT_LANGUAGE_KEY, lang)
}

export async function loadOutputLanguage(projectId?: string): Promise<OutputLanguage | null> {
  if (projectId) {
    const projectLanguages = await getConfigKey<Record<string, OutputLanguage>>(PROJECT_OUTPUT_LANGUAGE_KEY)
    return projectLanguages?.[projectId] ?? null
  }
  return (await getConfigKey<OutputLanguage>(OUTPUT_LANGUAGE_KEY)) ?? null
}

export async function saveProjectFileSyncEnabled(enabled: boolean, projectId?: string): Promise<void> {
  if (projectId) {
    const existing = (await getConfigKey<Record<string, boolean>>(PROJECT_FILE_SYNC_KEY)) ?? {}
    await setConfigKey(PROJECT_FILE_SYNC_KEY, { ...existing, [projectId]: enabled })
    return
  }
  const existing = (await getConfigKey<Record<string, boolean>>(PROJECT_FILE_SYNC_KEY)) ?? {}
  await setConfigKey(PROJECT_FILE_SYNC_KEY, { ...existing, default: enabled })
}

export async function loadProjectFileSyncEnabled(projectId?: string): Promise<boolean> {
  const settings = await getConfigKey<Record<string, boolean>>(PROJECT_FILE_SYNC_KEY)
  if (projectId && settings && typeof settings[projectId] === "boolean") {
    return settings[projectId]
  }
  if (settings && typeof settings.default === "boolean") {
    return settings.default
  }
  return true
}

export async function saveSourceWatchConfig(config: SourceWatchConfig, projectId?: string): Promise<void> {
  const normalized = normalizeSourceWatchConfig(config)
  const existing = (await getConfigKey<Record<string, SourceWatchConfig>>(SOURCE_WATCH_CONFIG_KEY)) ?? {}
  await setConfigKey(SOURCE_WATCH_CONFIG_KEY, {
    ...existing,
    [projectId ?? "default"]: normalized,
  })
}

export async function loadSourceWatchConfig(projectId?: string): Promise<SourceWatchConfig> {
  const settings = await getConfigKey<Record<string, SourceWatchConfig>>(SOURCE_WATCH_CONFIG_KEY)
  const config = projectId ? settings?.[projectId] : undefined
  if (config) return normalizeSourceWatchConfig(config)
  if (settings?.default) return normalizeSourceWatchConfig(settings.default)

  const legacyEnabled = await loadProjectFileSyncEnabled(projectId)
  return normalizeSourceWatchConfig({ enabled: legacyEnabled })
}

// ── Update-check persistence ──────────────────────────────────────────────
// Small slice of state the UI-layer update store hydrates from on boot.
// Only fields that should persist across launches: the user's "enable
// auto-check" toggle, the timestamp we last checked (so the 6-hour cache
// survives restarts), and the version the user explicitly dismissed
// (so we don't re-nag on every restart until a newer version is out).

const UPDATE_CHECK_STATE_KEY = "updateCheckState"

export interface PersistedUpdateCheckState {
  enabled: boolean
  lastCheckedAt: number | null
  dismissedVersion: string | null
}

export async function saveUpdateCheckState(
  state: PersistedUpdateCheckState,
): Promise<void> {
  await setConfigKey(UPDATE_CHECK_STATE_KEY, state)
}

export async function loadUpdateCheckState(): Promise<PersistedUpdateCheckState | null> {
  return (await getConfigKey<PersistedUpdateCheckState>(UPDATE_CHECK_STATE_KEY)) ?? null
}

const ZOOM_LEVEL_KEY = "zoomLevel"

export async function saveZoomLevel(level: number): Promise<void> {
  await setConfigKey(ZOOM_LEVEL_KEY, normalizeZoomLevel(level))
}

export async function loadZoomLevel(): Promise<number> {
  const level = await getConfigKey<number>(ZOOM_LEVEL_KEY)
  return normalizeZoomLevel(level)
}

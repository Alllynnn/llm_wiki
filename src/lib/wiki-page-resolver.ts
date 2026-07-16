import type { FileNode } from "@/types/wiki"

export interface ProjectPathIndexEntry {
  name: string
  path: string
}

export interface ProjectPathIndex {
  byPath: ReadonlyMap<string, ProjectPathIndexEntry>
  filesByName: ReadonlyMap<string, readonly ProjectPathIndexEntry[]>
}

export function createEmptyProjectPathIndex(): ProjectPathIndex {
  return { byPath: new Map(), filesByName: new Map() }
}

export function buildProjectPathIndexFromTree(tree: FileNode[]): ProjectPathIndex {
  const byPath = new Map<string, ProjectPathIndexEntry>()
  const filesByName = new Map<string, ProjectPathIndexEntry[]>()

  function walk(nodes: FileNode[]) {
    for (const node of nodes) {
      if (!byPath.has(node.path)) {
        const entry: ProjectPathIndexEntry = { name: node.name, path: node.path }
        byPath.set(node.path, entry)
        if (!node.is_dir) {
          const bucket = filesByName.get(node.name)
          if (bucket) bucket.push(entry)
          else filesByName.set(node.name, [entry])
        }
      }
      if (node.is_dir && node.children) walk(node.children)
    }
  }

  walk(tree)
  return { byPath, filesByName }
}

type PathLookup = FileNode[] | ProjectPathIndex

function isProjectPathIndex(input: PathLookup): input is ProjectPathIndex {
  return !Array.isArray(input)
}

/**
 * Strip Obsidian-style `[[target]]` or `[[target|alias]]` wrapping
 * from a value, returning `{ slug, label }`. Frontmatter authors
 * (humans and the LLM) sometimes write related entries as
 * wikilinks instead of bare slugs; we want to display the alias
 * (or target) without the bracket noise and look up by target.
 *
 * Non-wikilink input is returned with `slug === label === input`.
 */
export function unwrapWikilink(s: string): { slug: string; label: string } {
  const m = s.match(/^\[\[([^\]|]+)(?:\|([^\]]*))?\]\]$/)
  if (!m) return { slug: s, label: s }
  const target = m[1].trim()
  const alias = m[2]?.trim()
  return { slug: target, label: alias && alias.length > 0 ? alias : target }
}

export type SourceReferenceResolution =
  | { kind: "external"; url: string }
  | { kind: "local"; path: string }
  | { kind: "missing" }

export function resolveSourceReference(
  treeOrIndex: PathLookup,
  ref: string,
  sourcesRoot: string | null,
): SourceReferenceResolution {
  const trimmedRef = ref.trim()
  const externalUrl = normalizeHttpUrl(trimmedRef)
  if (externalUrl) return { kind: "external", url: externalUrl }
  if (!sourcesRoot) return { kind: "missing" }
  const path = resolveSourceName(treeOrIndex, trimmedRef, sourcesRoot)
  return path ? { kind: "local", path } : { kind: "missing" }
}

/**
 * Walk a FileNode tree and return the absolute path of the first
 * file whose name matches `targetName`, restricted to subtrees that
 * sit underneath any directory whose absolute path contains
 * `pathContains`. Returns null when nothing matches.
 *
 * Used by the frontmatter panel to resolve `related: [slug]` to a
 * concrete `wiki/.../<slug>.md` path so a chip can navigate, and
 * `sources: [name.pdf]` to a `raw/sources/.../name.pdf` path so a
 * card can open the raw file. We intentionally take the first
 * match — duplicate basenames across subfolders are a wiki-author
 * collision the user sees in the file tree anyway, and resolving
 * arbitrarily is no worse than the prior text-only display.
 */
export function findInTreeByName(
  treeOrIndex: PathLookup,
  targetName: string,
  pathContains: string,
): string | null {
  if (isProjectPathIndex(treeOrIndex)) {
    for (const entry of treeOrIndex.filesByName.get(targetName) ?? []) {
      if (entry.path.includes(pathContains)) return entry.path
    }
    return null
  }

  function walk(nodes: FileNode[]): string | null {
    for (const node of nodes) {
      if (node.is_dir) {
        if (node.children) {
          const r = walk(node.children)
          if (r) return r
        }
        continue
      }
      if (node.name === targetName && node.path.includes(pathContains)) {
        return node.path
      }
    }
    return null
  }
  return walk(treeOrIndex)
}

/**
 * Resolve a `related:` reference to an absolute wiki page path.
 * Accepts three shapes the wiki has historically written:
 *   1. project-relative path:  `wiki/entities/dpao.md`
 *   2. bare filename with .md: `dpao.md`
 *   3. bare slug:              `dpao`
 * Returns the absolute path of an existing file, or null if none
 * matches. Always restricts the lookup to `wiki/` to avoid pulling
 * in a same-named file from `raw/sources/`.
 */
export function resolveRelatedSlug(
  treeOrIndex: PathLookup,
  ref: string,
  wikiRoot: string,
): string | null {
  // Path-like → resolve relative to project root (one segment up
  // from wikiRoot).
  if (ref.includes("/")) {
    const projectRoot = wikiRoot.replace(/\/wiki$/, "")
    const target = `${projectRoot}/${ref}`
    const found = findInTreeByPath(treeOrIndex, target)
    return found && found.includes(`${wikiRoot}/`) ? found : null
  }

  const filename = ref.endsWith(".md") ? ref : `${ref}.md`
  return findInTreeByName(treeOrIndex, filename, `${wikiRoot}/`)
}

/**
 * Resolve a normal Markdown page link (`[title](synthesis/foo.md)`) to an
 * existing wiki page. Unlike `related:` frontmatter, Markdown links are often
 * relative to the file currently being rendered.
 */
export function resolveMarkdownPageHref(
  treeOrIndex: PathLookup,
  href: string,
  wikiRoot: string,
  currentFilePath?: string | null,
): string | null {
  const pathPart = markdownHrefPath(href)
  if (!pathPart) return null

  if (currentFilePath && isRelativeHrefPath(pathPart)) {
    const currentRel = projectRelativeWikiPath(currentFilePath, wikiRoot)
    if (currentRel) {
      const currentDir = currentRel.includes("/")
        ? currentRel.slice(0, currentRel.lastIndexOf("/"))
        : ""
      const relativeTarget = normalizeRelativePath(
        currentDir ? `${currentDir}/${pathPart}` : pathPart,
      )
      const found = findInTreeByPath(treeOrIndex, `${wikiRoot}/${relativeTarget}`)
      if (found && found.includes(`${wikiRoot}/`)) return found
    }
  }

  const normalized = normalizeRelativePath(pathPart.replace(/^\/+/, ""))
  const candidates = new Set<string>()
  if (normalized.startsWith("wiki/")) {
    candidates.add(normalized)
  } else {
    candidates.add(`wiki/${normalized}`)
  }
  candidates.add(lastPathSegment(normalized))

  for (const candidate of candidates) {
    const found = resolveRelatedSlug(treeOrIndex, candidate, wikiRoot)
    if (found) return found
  }
  return null
}

/**
 * Resolve browser deep links such as `/synthesis/foo.md` or accidental nested
 * URLs like `/concepts/faq/synthesis/foo.md` back into the current project's
 * wiki tree. The suffix search handles old full-page navigations caused by
 * relative Markdown links.
 */
export function resolveWikiPathFromBrowserPath(
  treeOrIndex: PathLookup,
  browserPath: string,
  wikiRoot: string,
): string | null {
  const pathPart = markdownHrefPath(browserPath)
  if (!pathPart) return null

  const normalized = normalizeRelativePath(pathPart.replace(/^\/+/, ""))
  const segments = normalized.split("/").filter(Boolean)
  const candidates = new Set<string>()

  if (normalized.startsWith("wiki/")) {
    candidates.add(normalized)
  } else {
    candidates.add(`wiki/${normalized}`)
  }

  for (let i = 0; i < segments.length; i++) {
    const suffix = segments.slice(i).join("/")
    if (suffix) candidates.add(`wiki/${suffix}`)
  }
  candidates.add(lastPathSegment(normalized))

  for (const candidate of candidates) {
    const found = resolveRelatedSlug(treeOrIndex, candidate, wikiRoot)
    if (found) return found
  }
  return null
}

/**
 * Resolve a `sources:` reference. Accepts:
 *   1. project-relative path:  `wiki/sources/foo.md` or
 *                              `raw/sources/year-2025/q1.pdf`
 *   2. bare filename with ext: `q1.pdf`
 *   3. wiki source-summary:    `foo.md` (in wiki/sources/)
 * Tries wiki/sources/ first when the ref is a bare .md filename
 * (the ingest pipeline writes summary pages there), then falls
 * back to raw/sources/. Returns null if nothing matches.
 */
export function resolveSourceName(
  treeOrIndex: PathLookup,
  ref: string,
  sourcesRoot: string,
): string | null {
  // sourcesRoot is `<project>/raw/sources` — derive project root
  // and wiki/ root from it.
  const projectRoot = sourcesRoot.replace(/\/raw\/sources$/, "")
  const wikiSources = `${projectRoot}/wiki/sources`

  if (ref.includes("/")) {
    const normalizedRef = ref.replace(/\\/g, "/").replace(/^\/+/, "")
    const candidates = normalizedRef.startsWith("raw/sources/") ||
      normalizedRef.startsWith("wiki/")
      ? [`${projectRoot}/${normalizedRef}`]
      : [
          `${sourcesRoot}/${normalizedRef}`,
          `${projectRoot}/${normalizedRef}`,
    ]

    for (const target of candidates) {
      const found = findInTreeByPath(treeOrIndex, target)
      if (found) return found
    }
    return null
  }

  // Bare .md filename → look in wiki/sources/ first (ingest's
  // canonical home for source-summary pages).
  if (ref.endsWith(".md")) {
    const inWiki = findInTreeByName(treeOrIndex, ref, `${wikiSources}/`)
    if (inWiki) return inWiki
  }

  // Otherwise, search raw/sources/.
  return findInTreeByName(treeOrIndex, ref, `${sourcesRoot}/`)
}

function findInTreeByPath(treeOrIndex: PathLookup, targetPath: string): string | null {
  if (isProjectPathIndex(treeOrIndex)) {
    return treeOrIndex.byPath.get(targetPath)?.path ?? null
  }

  function walk(nodes: FileNode[]): string | null {
    for (const node of nodes) {
      if (node.path === targetPath) return node.path
      if (node.is_dir && node.children) {
        const r = walk(node.children)
        if (r) return r
      }
    }
    return null
  }
  return walk(treeOrIndex)
}

function markdownHrefPath(href: string): string | null {
  const raw = href.trim()
  if (!raw || raw.startsWith("#")) return null
  if (raw.startsWith("//") || /^[A-Za-z][A-Za-z0-9+.-]*:/.test(raw)) return null
  const path = safeDecodeURIComponent(raw.split("#")[0].split("?")[0])
    .replace(/\\/g, "/")
    .trim()
  return path.toLowerCase().endsWith(".md") ? path : null
}

function safeDecodeURIComponent(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function isRelativeHrefPath(path: string): boolean {
  return !path.startsWith("/") && !path.startsWith("\\") && !/^[A-Za-z]:[\\/]/.test(path)
}

function projectRelativeWikiPath(filePath: string, wikiRoot: string): string | null {
  const normalizedFile = filePath.replace(/\\/g, "/")
  const normalizedRoot = wikiRoot.replace(/\\/g, "/").replace(/\/+$/, "")
  return normalizedFile.startsWith(`${normalizedRoot}/`)
    ? normalizedFile.slice(normalizedRoot.length + 1)
    : null
}

function normalizeRelativePath(path: string): string {
  const out: string[] = []
  for (const part of path.replace(/\\/g, "/").split("/")) {
    if (!part || part === ".") continue
    if (part === "..") {
      out.pop()
      continue
    }
    out.push(part)
  }
  return out.join("/")
}

function lastPathSegment(path: string): string {
  const parts = path.split("/").filter(Boolean)
  return parts[parts.length - 1] ?? path
}

function normalizeHttpUrl(ref: string): string | null {
  if (/[\u0000-\u001f\u007f]/u.test(ref)) return null
  try {
    const url = new URL(ref)
    if (url.protocol !== "http:" && url.protocol !== "https:") return null
    if (!url.hostname || url.username || url.password) return null
    return url.href
  } catch {
    return null
  }
}

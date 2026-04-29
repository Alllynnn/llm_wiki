import yaml from "js-yaml"

export type FrontmatterValue = string | string[]

export interface FrontmatterParseResult {
  frontmatter: Record<string, FrontmatterValue> | null
  body: string
  /**
   * The literal frontmatter block (opening `---`, YAML payload,
   * closing `---`, plus the newlines that separate it from the
   * body) as it appears in the input. Empty string when there is
   * no frontmatter. Callers that edit only the body — e.g. the
   * WikiEditor — write back `rawBlock + body` so user-managed YAML
   * survives untouched.
   */
  rawBlock: string
}

// Single, generic detector. Both fence lines must be on their own
// line (anchored with `^...$` under the `m` flag); content between
// is delegated to a real YAML parser. We do NOT try to special-case
// trailing whitespace, BOMs, alternative fence markers, or LLM
// corruption patterns here — that path leads to ever-growing regex
// patches with no real progress. If the file isn't a standard
// `---\n…\n---` document, we treat it as "no frontmatter" and let
// the body render in full.
const FM_BLOCK_RE = /^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)/

export function parseFrontmatter(content: string): FrontmatterParseResult {
  const match = content.match(FM_BLOCK_RE)
  if (!match) return { frontmatter: null, body: content, rawBlock: "" }

  const yamlPayload = match[1]
  const rawBlock = match[0]
  const body = content.slice(rawBlock.length)

  let parsed: unknown
  try {
    parsed = yaml.load(yamlPayload, { schema: yaml.JSON_SCHEMA })
  } catch {
    // Malformed YAML — degrade gracefully. Treat the file as having
    // no parseable frontmatter, but keep stripping the fence block
    // so the user doesn't see a wall of `key: value` text in the
    // rendered body.
    return { frontmatter: null, body, rawBlock }
  }

  return {
    frontmatter: normalize(parsed),
    body,
    rawBlock,
  }
}

/**
 * Coerce js-yaml's output into the shape FrontmatterPanel consumes:
 * a flat `Record<string, string | string[]>`. Nested objects and
 * scalars that aren't strings are stringified so unusual YAML
 * still surfaces in the UI rather than silently disappearing.
 */
function normalize(parsed: unknown): Record<string, FrontmatterValue> | null {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null
  const out: Record<string, FrontmatterValue> = {}
  for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
    if (Array.isArray(value)) {
      out[key] = value.map((v) => stringifyScalar(v))
      continue
    }
    out[key] = stringifyScalar(value)
  }
  return out
}

function stringifyScalar(v: unknown): string {
  if (v === null || v === undefined) return ""
  if (typeof v === "string") return v
  if (typeof v === "number" || typeof v === "boolean") return String(v)
  if (v instanceof Date) return v.toISOString().slice(0, 10)
  // Object / nested array → JSON so the user still sees something.
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

import { readFile, writeFile } from "@/commands/fs"
import { streamChat } from "./llm-client"
import { useWikiStore, type LlmConfig } from "@/stores/wiki-store"
import { buildLanguageDirective } from "./output-language"
import { normalizePath } from "@/lib/path-utils"

/**
 * Lightweight post-save enrichment: ask LLM to add [[wikilinks]] to a saved wiki page.
 * Much cheaper than full auto-ingest — no new pages created, just cross-references added.
 */
export async function enrichWithWikilinks(
  projectPath: string,
  filePath: string,
  llmConfig: LlmConfig,
): Promise<void> {
  const pp = normalizePath(projectPath)
  const fp = normalizePath(filePath)
  const [content, index] = await Promise.all([
    readFile(fp),
    readFile(`${pp}/wiki/index.md`).catch(() => ""),
  ])

  if (!content || !index) return

  // Quick LLM call: just add wikilinks, don't change content
  let enriched = ""

  await streamChat(
    llmConfig,
    [
      {
        role: "system",
        content: [
          "You are a wiki cross-referencing assistant. Your ONLY job: add",
          "[[wikilinks]] around existing words that match entries in the wiki",
          "index. You do NOT rewrite, summarize, or expand the page.",
          "",
          buildLanguageDirective(content),
          "",
          `## Wiki Index (link to these pages)\n${index}`,
          "",
          "## Output Requirements (STRICT — violations will cause rejection)",
          "",
          "1. Return the COMPLETE original text with [[wikilinks]] inserted.",
          "2. PRESERVE the YAML frontmatter block (--- ... ---) at the top EXACTLY,",
          "   byte-for-byte. Do not modify, reorder, or remove any frontmatter fields.",
          "3. DO NOT add new sentences, paragraphs, summaries, or explanations.",
          "4. DO NOT remove or rewrite any existing text.",
          "5. Only wrap existing words with [[ and ]] where they match a wiki",
          "   index entry. First mention per page only.",
          "6. Your output length MUST be close to the input length; adding",
          "   [[brackets]] changes length by only a handful of characters.",
          "",
          "If you would need to materially change the page to improve it, emit",
          "the ORIGINAL TEXT UNCHANGED. Rewriting is explicitly forbidden.",
        ].join("\n"),
      },
      {
        role: "user",
        content: `Add [[wikilinks]] to this wiki page:\n\n${content}`,
      },
    ],
    {
      onToken: (token) => { enriched += token },
      onDone: () => {},
      onError: () => {},
    },
  )

  if (!enriched || enriched.length < content.length * 0.5) {
    // LLM returned too little — probably an error, don't overwrite
    return
  }
  if (enriched.length > content.length * 2) {
    // LLM rewrote the page instead of just adding links — reject to avoid
    // destroying user content. Adding [[ ]] at most ~4 chars per link, so
    // a reasonable enrichment stays well under 2× the original length.
    console.warn(
      `[enrich-wikilinks] LLM output too long (${enriched.length} vs ${content.length}) — rejecting`,
    )
    return
  }

  // Frontmatter guard: if the input started with YAML frontmatter, the
  // enriched output MUST too. Otherwise we'd silently lose metadata.
  if (content.startsWith("---\n") && !enriched.startsWith("---\n")) {
    console.warn(
      `[enrich-wikilinks] LLM dropped YAML frontmatter — rejecting`,
    )
    return
  }

  // Write the enriched version back
  await writeFile(fp, enriched)

  // Refresh graph
  useWikiStore.getState().bumpDataVersion()
}

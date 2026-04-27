/**
 * Image extraction orchestration for the ingest pipeline.
 *
 * Pure dispatch + path-shaping layer over the Rust commands
 * `extract_and_save_pdf_images_cmd` / `extract_and_save_office_images_cmd`.
 * Decides which command to call based on file extension, computes the
 * destination directory (`wiki/media/<source-slug>/`), and gives back
 * a small markdown snippet ready to paste into the LLM's source
 * context.
 *
 * NOTE: this layer does NOT call any LLM (no captions yet — that's
 * Phase 3a). The alt text on each image is a placeholder; once
 * captioning lands, the same helper grows a `caption` field per
 * image and the markdown line uses that instead.
 */
import { invoke } from "@tauri-apps/api/core"
import { getFileName, normalizePath } from "@/lib/path-utils"

/** Mirrors `commands::extract_images::SavedImage` on the Rust side. */
export interface SavedImage {
  index: number
  mimeType: string
  /** PDF page or PPTX slide number (1-based). DOCX always null. */
  page: number | null
  width: number
  height: number
  /** Path relative to the wiki/ root, e.g. `media/rope-paper/img-1.png`. */
  relPath: string
  /** Absolute filesystem path — used by `convertFileSrc` for preview. */
  absPath: string
  sha256: string
}

/** File extensions we currently extract images from. Excludes XLS/XLSX
 *  because spreadsheets generally don't have charts as images (charts
 *  are XML-rendered shapes, not embedded raster). Adding them later is
 *  a one-line change here. */
const SUPPORTED_PDF_EXTS = ["pdf"] as const
const SUPPORTED_OFFICE_EXTS = ["pptx", "docx", "ppt", "doc"] as const
// Note: ppt / doc (legacy binary formats) won't actually work — they
// aren't ZIP. Listed for completeness; Rust side will return Err which
// the caller treats as "no images" gracefully.

/**
 * Extract every embedded image from `sourcePath` and save them to
 * `<projectPath>/wiki/media/<slug>/`. Returns metadata only — image
 * bytes never traverse JS (the Rust command writes directly).
 *
 * Returns `[]` for unsupported file types or when the source has no
 * extractable images. Errors during extraction are logged and returned
 * as an empty array — image extraction failure must NEVER abort the
 * ingest pipeline (which is why this isn't `throws`).
 *
 * `slug` is the basename of the source file without extension. Same
 * convention the rest of ingest uses (see `wiki/sources/<slug>.md`).
 */
export async function extractAndSaveSourceImages(
  projectPath: string,
  sourcePath: string,
): Promise<SavedImage[]> {
  const pp = normalizePath(projectPath)
  const sp = normalizePath(sourcePath)
  const fileName = getFileName(sp)
  const ext = fileName.split(".").pop()?.toLowerCase() ?? ""

  const isPdf = (SUPPORTED_PDF_EXTS as readonly string[]).includes(ext)
  const isOffice = (SUPPORTED_OFFICE_EXTS as readonly string[]).includes(ext)
  if (!isPdf && !isOffice) return []

  const slug = fileName.replace(/\.[^.]+$/, "")
  const destDir = `${pp}/wiki/media/${slug}`
  const relTo = `${pp}/wiki`

  try {
    const images = await invoke<unknown[]>(
      isPdf ? "extract_and_save_pdf_images_cmd" : "extract_and_save_office_images_cmd",
      { sourcePath: sp, destDir, relTo },
    )
    // Rust serializes with snake_case-ish field names per the struct
    // shape. Tauri's IPC layer with serde converts to camelCase
    // automatically. Validate the shape defensively in case the
    // contract drifts.
    return images
      .filter((it): it is SavedImage => {
        if (!it || typeof it !== "object") return false
        const obj = it as Record<string, unknown>
        return (
          typeof obj.index === "number" &&
          typeof obj.relPath === "string" &&
          typeof obj.absPath === "string"
        )
      })
  } catch (err) {
    console.warn(
      `[ingest:images] extraction failed for "${fileName}":`,
      err instanceof Error ? err.message : err,
    )
    return []
  }
}

/**
 * Build the markdown section to splice into `sourceContent` so the
 * generation LLM sees the available images. Each image is referenced
 * once by its rel_path with a placeholder alt-text (Phase 3a will
 * replace this with VLM-generated captions).
 *
 * Returns an empty string when there are no images — no leading
 * separator gets inserted, which keeps the prompt size unchanged for
 * pure-text documents.
 *
 * Placement: caller appends this AFTER the source's text content so
 * the LLM still reads the document linearly, then sees images at the
 * end with their page numbers as positional anchors. A future
 * refinement (per the plan) is to insert per-page image listings
 * inline at page breaks; that requires the text extractor to emit
 * page boundaries, which it doesn't yet.
 */
export function buildImageMarkdownSection(images: SavedImage[]): string {
  if (images.length === 0) return ""

  const lines: string[] = ["", "", "## Embedded Images", ""]
  // Group by page so the LLM can correlate "Figure 3 mentioned on
  // page 5" with the right image. DOCX images have page=null; they
  // get grouped under "Document":
  const byPage = new Map<string, SavedImage[]>()
  for (const img of images) {
    const key = img.page == null ? "Document" : `Page ${img.page}`
    const bucket = byPage.get(key)
    if (bucket) bucket.push(img)
    else byPage.set(key, [img])
  }

  // Page-keyed order, with "Document" (DOCX) last when present.
  const ordered = [...byPage.keys()].sort((a, b) => {
    if (a === "Document") return 1
    if (b === "Document") return -1
    const numA = parseInt(a.replace(/\D/g, ""), 10) || 0
    const numB = parseInt(b.replace(/\D/g, ""), 10) || 0
    return numA - numB
  })

  for (const key of ordered) {
    lines.push(`### ${key}`, "")
    for (const img of byPage.get(key) ?? []) {
      // Empty alt text on purpose — we don't have a caption yet, and
      // making one up here would just feed the LLM noise. The image
      // SOURCE (rel_path) carries enough information for the LLM to
      // refer to it by page number.
      lines.push(`![](${img.relPath})`)
    }
    lines.push("")
  }

  return lines.join("\n")
}

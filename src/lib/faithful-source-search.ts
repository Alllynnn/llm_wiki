import { apiCall } from "@/lib/api"
import { normalizePath } from "@/lib/path-utils"

export interface FaithfulSourceResult {
  path: string
  title: string
  snippet: string
  titleMatch: boolean
  score: number
  content?: string
}

interface FaithfulSourceSearchResponse {
  results: FaithfulSourceResult[]
  truncated?: boolean
  truncationReason?: string
}

/**
 * Search only original project sources. The server deliberately excludes
 * generated wiki pages, graph/vector expansion, hidden files, and stale
 * binary extraction caches from this endpoint.
 */
export async function searchFaithfulSources(
  projectPath: string,
  query: string,
  topK = 10,
  signal?: AbortSignal,
): Promise<FaithfulSourceResult[]> {
  if (!query.trim()) return []
  const pp = normalizePath(projectPath).replace(/\/+$/, "")
  const body = {
    project_path: pp,
    query,
    top_k: topK,
    include_content: true,
  }
  const response = signal
    ? await apiCall<FaithfulSourceSearchResponse>(
        "POST",
        "/api/v1/sources/search",
        body,
        { signal },
      )
    : await apiCall<FaithfulSourceSearchResponse>("POST", "/api/v1/sources/search", body)
  if (response.truncated) {
    const reason = response.truncationReason?.replace(/_/g, " ") ?? "safety budget"
    throw new Error(`Original source search stopped at its ${reason}; results may be incomplete`)
  }
  return response.results.map((result) => ({
    ...result,
    path: `${pp}/${normalizePath(result.path).replace(/^\/+/, "")}`,
  }))
}

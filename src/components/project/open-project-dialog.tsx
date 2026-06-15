import { useCallback, useEffect, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { apiCall } from "@/lib/api"
import { FolderOpen, Loader2 } from "lucide-react"
import { FolderBrowserDialog } from "@/components/layout/folder-browser-dialog"

interface FsEntry {
  name: string
  is_dir: boolean
  is_project: boolean
}

interface FsListResponse {
  entries: FsEntry[]
}

export interface OpenProjectDialogProps {
  open: boolean
  onClose: () => void
  onSelect: (path: string) => void
}

export function OpenProjectDialog({ open, onClose, onSelect }: OpenProjectDialogProps) {
  const [projects, setProjects] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string>("")
  const [browseOpen, setBrowseOpen] = useState(false)

  const loadProjects = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await apiCall<FsListResponse>("GET", "/api/v1/fs/list?path=")
      const names = (resp.entries ?? [])
        .filter((e) => e.is_dir && e.is_project)
        .map((e) => e.name)
        .sort((a, b) => a.localeCompare(b))
      setProjects(names)
      setSelected(names[0] ?? "")
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setProjects([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) void loadProjects()
  }, [open, loadProjects])

  function handleOpenSelected() {
    if (!selected) return
    onSelect(selected)
    onClose()
  }

  function handleBrowsePicked(path: string) {
    setBrowseOpen(false)
    onSelect(path)
    onClose()
  }

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
        <DialogContent className="max-w-md" showCloseButton>
          <DialogHeader>
            <DialogTitle>Open project</DialogTitle>
          </DialogHeader>

          <div className="flex flex-col gap-2">
            <label className="text-xs text-muted-foreground" htmlFor="project-select">
              Existing projects in your projects root
            </label>

            {loading ? (
              <div className="flex items-center gap-2 px-3 py-6 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Scanning…
              </div>
            ) : error ? (
              <p className="text-xs text-destructive">{error}</p>
            ) : projects.length === 0 ? (
              <p className="px-3 py-4 text-sm text-muted-foreground">
                No projects found. Use "Browse…" to pick a folder elsewhere, or
                create a new project from the welcome screen.
              </p>
            ) : (
              <select
                id="project-select"
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleOpenSelected() }}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                size={Math.min(projects.length, 8)}
              >
                {projects.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setBrowseOpen(true)}>
              <FolderOpen className="size-3.5" />
              Browse…
            </Button>
            <span className="flex-1" />
            <Button variant="outline" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleOpenSelected} disabled={!selected || loading}>
              Open
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <FolderBrowserDialog
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        onSelect={handleBrowsePicked}
        title="Browse for project folder"
      />
    </>
  )
}

import { useEffect, useState } from "react"
import { FolderOpen, Plus, Clock, X, Layers3 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { getRecentProjects, removeFromRecentProjects } from "@/lib/project-store"
import type { WikiProject } from "@/types/wiki"
import { useTranslation } from "react-i18next"
import {
  groupProjectsByCategory,
  KNOWLEDGE_CATEGORIES,
  KNOWLEDGE_PROJECT_KINDS,
  type KnowledgeCategoryId,
} from "@/lib/knowledge-platform"

interface WelcomeScreenProps {
  onCreateProject: () => void
  onOpenProject: () => void
  onSelectProject: (project: WikiProject) => void
}

export function WelcomeScreen({
  onCreateProject,
  onOpenProject,
  onSelectProject,
}: WelcomeScreenProps) {
  const { t } = useTranslation()
  const [recentProjects, setRecentProjects] = useState<WikiProject[]>([])
  const [selectedCategory, setSelectedCategory] = useState<KnowledgeCategoryId | "all">("all")

  useEffect(() => {
    getRecentProjects().then(setRecentProjects).catch(() => {})
  }, [])

  async function handleRemoveRecent(e: React.MouseEvent, path: string) {
    e.stopPropagation()
    await removeFromRecentProjects(path)
    const updated = await getRecentProjects()
    setRecentProjects(updated)
  }

  const groupedProjects = groupProjectsByCategory(recentProjects)
  const visibleProjects = selectedCategory === "all"
    ? recentProjects
    : groupedProjects[selectedCategory]

  return (
    <div className="flex h-full overflow-y-auto bg-background">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-6 py-10">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-md border bg-muted/50">
              <Layers3 className="h-5 w-5 text-muted-foreground" />
            </div>
            <h1 className="text-3xl font-bold">{t("app.title")}</h1>
            <p className="mt-2 max-w-2xl text-muted-foreground">
              {t("app.subtitle")}
            </p>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              {t("welcome.platformSubtitle")}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-3">
            <Button onClick={onCreateProject}>
              <Plus className="mr-2 h-4 w-4" />
              {t("welcome.newProject")}
            </Button>
            <Button variant="outline" onClick={onOpenProject}>
              <FolderOpen className="mr-2 h-4 w-4" />
              {t("welcome.openProject")}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            aria-pressed={selectedCategory === "all"}
            onClick={() => setSelectedCategory("all")}
            className={categoryButtonClass(selectedCategory === "all")}
          >
            {t("knowledge.allCategories")}
            <span className="text-xs opacity-70">{recentProjects.length}</span>
          </button>
          {KNOWLEDGE_CATEGORIES.map((category) => (
            <button
              key={category.id}
              type="button"
              aria-pressed={selectedCategory === category.id}
              onClick={() => setSelectedCategory(category.id)}
              className={categoryButtonClass(selectedCategory === category.id)}
            >
              {t(category.labelKey)}
              <span className="text-xs opacity-70">
                {groupedProjects[category.id].length}
              </span>
            </button>
          ))}
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {KNOWLEDGE_CATEGORIES.map((category) => (
            <div key={category.id} className="rounded-md border bg-background p-4">
              <div className="text-sm font-medium">{t(category.labelKey)}</div>
              <div className="mt-1 text-xs leading-5 text-muted-foreground">
                {t(category.descriptionKey)}
              </div>
            </div>
          ))}
        </div>

        <div className="w-full">
          <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            {t("welcome.recentProjects")}
          </div>
          {visibleProjects.length > 0 ? (
            <div className="overflow-hidden rounded-md border">
              {visibleProjects.map((proj) => {
                const category = KNOWLEDGE_CATEGORIES.find((item) => item.id === proj.metadata?.categoryId)
                const kind = KNOWLEDGE_PROJECT_KINDS.find((item) => item.id === proj.metadata?.projectKindId)
                return (
                  <div key={proj.path} className="group flex items-stretch border-b last:border-b-0">
                    <button
                      type="button"
                      onClick={() => onSelectProject(proj)}
                      className="min-w-0 flex-1 cursor-pointer px-4 py-3 text-left transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <div className="truncate text-sm font-medium">{proj.name}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        {category && <span>{t(category.labelKey)}</span>}
                        {kind && <span>{t(kind.labelKey)}</span>}
                      </div>
                      <div className="mt-1 truncate text-xs text-muted-foreground">
                        {proj.path}
                      </div>
                    </button>
                    <button
                      type="button"
                      aria-label={t("welcome.removeRecent", { name: proj.name })}
                      onClick={(e) => handleRemoveRecent(e, proj.path)}
                      className="flex w-11 shrink-0 cursor-pointer items-center justify-center text-muted-foreground opacity-70 transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="rounded-md border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
              {t("welcome.noProjectsInCategory")}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function categoryButtonClass(active: boolean): string {
  const base = "inline-flex h-9 cursor-pointer items-center gap-2 rounded-md border px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
  return active
    ? `${base} border-primary bg-accent text-accent-foreground`
    : `${base} border-border bg-background text-muted-foreground hover:bg-accent/50 hover:text-foreground`
}

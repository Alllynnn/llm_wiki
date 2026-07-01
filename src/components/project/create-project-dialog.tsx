import { useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { createProject, writeFile, createDirectory } from "@/commands/fs"
import { getTemplate } from "@/lib/templates"
import { TemplatePicker } from "@/components/project/template-picker"
import type { WikiProject } from "@/types/wiki"
import { normalizePath } from "@/lib/path-utils"
import { OUTPUT_LANGUAGE_OPTIONS } from "@/lib/output-language-options"
import { useWikiStore, type OutputLanguage } from "@/stores/wiki-store"
import { saveOutputLanguage } from "@/lib/project-store"
import {
  buildProjectSchemaContext,
  buildProjectPurposeContext,
  DEFAULT_PROJECT_METADATA,
  getProjectKindsForCategory,
  KNOWLEDGE_CATEGORIES,
  type BusinessProjectMetadata,
  type KnowledgeCategoryId,
  type KnowledgeProjectKindId,
} from "@/lib/knowledge-platform"
import { saveProjectMetadata, upsertProjectInfo } from "@/lib/project-identity"

interface CreateProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (project: WikiProject) => void
}

export function CreateProjectDialog({ open: isOpen, onOpenChange, onCreated }: CreateProjectDialogProps) {
  const { t } = useTranslation()
  const [name, setName] = useState("")
  const [categoryId, setCategoryId] = useState<KnowledgeCategoryId>("annotation")
  const [projectKindId, setProjectKindId] = useState<KnowledgeProjectKindId>("language-audio")
  const [businessContext, setBusinessContext] = useState("")
  const [sourcePolicy, setSourcePolicy] = useState(DEFAULT_PROJECT_METADATA.sourcePolicy)
  const [selectedTemplate, setSelectedTemplate] = useState("general")
  // Empty string = "user hasn't picked yet"; we validate this on
  // submit so a fresh project never starts in implicit auto-detect
  // mode. Once chosen, the value is one of OUTPUT_LANGUAGE_OPTIONS
  // (`auto` is a valid explicit choice — the user is then opting
  // INTO auto-detect rather than getting it by accident).
  const [language, setLanguage] = useState<string>("")
  const [error, setError] = useState("")
  const [creating, setCreating] = useState(false)
  const setOutputLanguage = useWikiStore((s) => s.setOutputLanguage)

  async function handleCreate() {
    if (!name.trim()) {
      setError(t("project.errorNameRequired"))
      return
    }
    if (!language) {
      setError(t("project.errorLanguageRequired"))
      return
    }
    const metadata: BusinessProjectMetadata = {
      categoryId,
      projectKindId,
      businessContext,
      sourcePolicy,
    }
    setCreating(true)
    setError("")
    try {
      // Second arg (`path`) is ignored by the HTTP backend; the server
      // creates the project directly under LLM_WIKI_PROJECTS_ROOT. We pass
      // an empty string for backward-compatibility with the wrapper signature.
      const project = await createProject(name.trim(), "")
      const pp = normalizePath(project.path)

      const template = getTemplate(selectedTemplate)
      const platformContext = buildProjectPurposeContext(metadata)
      const platformSchema = buildProjectSchemaContext(metadata)
      await writeFile(`${pp}/schema.md`, `${platformSchema}\n\n${template.schema}`)
      await writeFile(`${pp}/purpose.md`, `${platformContext}\n\n${template.purpose}`)
      for (const dir of template.extraDirs) {
        await createDirectory(`${pp}/${dir}`)
      }
      const normalizedMetadata = await saveProjectMetadata(pp, metadata)
      const projectWithMetadata: WikiProject = {
        ...project,
        metadata: normalizedMetadata,
      }
      await upsertProjectInfo(project.id, project.path, project.name, normalizedMetadata)

      // Persist the user's language choice. The store / disk
      // mirror is what the rest of the app reads via
      // `getOutputLanguage()` — without this write the choice
      // wouldn't survive past the dialog closing.
      const lang = language as OutputLanguage
      setOutputLanguage(lang)
      await saveOutputLanguage(lang, project.id)

      onCreated(projectWithMetadata)
      onOpenChange(false)
      setName("")
      setCategoryId("annotation")
      setProjectKindId("language-audio")
      setBusinessContext("")
      setSourcePolicy(DEFAULT_PROJECT_METADATA.sourcePolicy)
      setSelectedTemplate("general")
      setLanguage("")
    } catch (err) {
      setError(String(err))
    } finally {
      setCreating(false)
    }
  }

  function handleCategoryChange(nextCategory: KnowledgeCategoryId) {
    const kinds = getProjectKindsForCategory(nextCategory)
    setCategoryId(nextCategory)
    setProjectKindId(kinds[0].id)
  }

  const projectKinds = getProjectKindsForCategory(categoryId)

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] grid-rows-[auto_1fr_auto] overflow-hidden">
        <DialogHeader>
          <DialogTitle>{t("project.createTitle")}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4 py-4 overflow-y-auto min-h-0">
          <div className="flex flex-col gap-2">
            <Label htmlFor="name">{t("project.name")}</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("project.namePlaceholder")} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="knowledge-category">{t("project.knowledgeCategory")}</Label>
              <select
                id="knowledge-category"
                value={categoryId}
                onChange={(e) => handleCategoryChange(e.target.value as KnowledgeCategoryId)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {KNOWLEDGE_CATEGORIES.map((category) => (
                  <option key={category.id} value={category.id}>
                    {t(category.labelKey)}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="project-kind">{t("project.projectKind")}</Label>
              <select
                id="project-kind"
                value={projectKindId}
                onChange={(e) => setProjectKindId(e.target.value as KnowledgeProjectKindId)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {projectKinds.map((kind) => (
                  <option key={kind.id} value={kind.id}>
                    {t(kind.labelKey)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="business-context">{t("project.businessContext")}</Label>
            <textarea
              id="business-context"
              value={businessContext}
              onChange={(e) => setBusinessContext(e.target.value)}
              placeholder={t("project.businessContextPlaceholder")}
              rows={3}
              className="min-h-24 w-full resize-y rounded-md border bg-background px-3 py-2 text-sm leading-6 focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="source-policy">{t("project.sourcePolicy")}</Label>
            <textarea
              id="source-policy"
              value={sourcePolicy}
              onChange={(e) => setSourcePolicy(e.target.value)}
              rows={2}
              className="min-h-20 w-full resize-y rounded-md border bg-background px-3 py-2 text-sm leading-6 focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>{t("project.template")}</Label>
            <TemplatePicker selected={selectedTemplate} onSelect={setSelectedTemplate} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="language">
              {t("project.aiOutputLanguage")} <span className="text-destructive">{t("project.aiOutputLanguageRequired")}</span>
            </Label>
            <select
              id="language"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="" disabled>
                {t("project.pickLanguage")}
              </option>
              {/*
                * "auto" is intentionally filtered out at project
                * creation time. Auto-detect is a fine post-hoc
                * setting (Settings → Output) for users who later
                * decide they want it, but at create time we force
                * an explicit commitment so the project never starts
                * in the implicit-detect mode that was the source
                * of "wiki content showed up in a language I didn't
                * expect" surprises.
                */}
              {OUTPUT_LANGUAGE_OPTIONS.filter((l) => l.value !== "auto").map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              {t("project.aiOutputLanguageHint")}
            </p>
          </div>
          {/*
            * The parent directory is fixed server-side via the
            * LLM_WIKI_PROJECTS_ROOT environment variable. The new project
            * always lands at <projects_root>/<name>. No path picker is
            * needed in the browser model. (The desktop UI's "Parent
            * Directory" field is intentionally omitted here.)
            */}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("project.cancel")}</Button>
          <Button onClick={handleCreate} disabled={creating}>{creating ? t("project.creating") : t("project.create")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

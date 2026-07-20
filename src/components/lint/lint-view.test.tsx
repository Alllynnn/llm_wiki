import { renderToStaticMarkup } from "react-dom/server"
import { AlertTriangle, Info } from "lucide-react"
import { describe, expect, it, vi } from "vitest"
import { createLintOperationGate, LintCard, type LintOperation } from "./lint-view"
import type { LintItem } from "@/stores/lint-store"

const item: LintItem = {
  id: "lint-1",
  type: "orphan",
  severity: "info",
  page: "alpha.md",
  detail: "No other pages link to this page.",
  createdAt: 1,
}

describe("LintCard mutation locking", () => {
  it("blocks a lint scan until an active batch write finishes", async () => {
    const transitions: Array<LintOperation | null> = []
    const gate = createLintOperationGate((operation) => transitions.push(operation))
    let finishWrite!: () => void
    const writePending = new Promise<void>((resolve) => { finishWrite = resolve })

    expect(gate.begin({ kind: "batch" })).toBe(true)
    const batchWrite = writePending.finally(() => gate.finish())
    expect(gate.begin({ kind: "lint" })).toBe(false)
    expect(transitions).toEqual([{ kind: "batch" }])

    finishWrite()
    await batchWrite
    expect(transitions.at(-1)).toBeNull()
    expect(gate.begin({ kind: "lint" })).toBe(true)
    expect(gate.begin({ kind: "fix", itemId: "lint-1" })).toBe(false)
  })

  it("disables fix and delete while another lint mutation is running", () => {
    const markup = renderToStaticMarkup(
      <LintCard
        item={item}
        fixing={false}
        operationsDisabled
        selected={false}
        onSelectedChange={vi.fn()}
        onOpenPage={vi.fn()}
        onFix={vi.fn()}
        onDelete={vi.fn()}
        typeConfig={{
          orphan: { icon: Info, label: "Orphan" },
          semantic: { icon: AlertTriangle, label: "Semantic" },
        }}
        t={(key) => key}
      />,
    )

    expect(markup).toMatch(/<button(?=[^>]*aria-label="lint\.fix")(?=[^>]*\sdisabled="")[^>]*>/)
    expect(markup).toMatch(/<button(?=[^>]*aria-label="lint\.delete")(?=[^>]*\sdisabled="")[^>]*>/)
  })
})

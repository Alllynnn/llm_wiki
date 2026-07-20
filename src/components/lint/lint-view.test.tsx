import { renderToStaticMarkup } from "react-dom/server"
import { AlertTriangle, Info } from "lucide-react"
import { describe, expect, it, vi } from "vitest"
import { createLintMutationGate, LintCard, type LintMutation } from "./lint-view"
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
  it("publishes delete busy state and rejects an overlapping fix", () => {
    const transitions: Array<LintMutation | null> = []
    const gate = createLintMutationGate((mutation) => transitions.push(mutation))

    expect(gate.begin({ kind: "delete", itemId: "lint-1" })).toBe(true)
    expect(gate.begin({ kind: "fix", itemId: "lint-1" })).toBe(false)
    expect(transitions).toEqual([{ kind: "delete", itemId: "lint-1" }])

    gate.finish()
    expect(transitions.at(-1)).toBeNull()
    expect(gate.begin({ kind: "batch" })).toBe(true)
  })

  it("disables fix and delete while another lint mutation is running", () => {
    const markup = renderToStaticMarkup(
      <LintCard
        item={item}
        fixing={false}
        mutationsDisabled
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

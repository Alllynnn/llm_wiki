import { describe, expect, it } from "vitest"
import { NAV_ITEMS } from "./icon-sidebar"

describe("icon sidebar navigation", () => {
  it("keeps Q&A as a primary navigation entry", () => {
    expect(NAV_ITEMS[0]).toMatchObject({
      view: "chat",
      labelKey: "nav.chat",
    })
  })
})

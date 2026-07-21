import { describe, expect, it, vi } from "vitest"

vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>()
  return {
    ...actual,
    useState: <T,>(initial: T) => [initial, vi.fn()],
    useRef: <T,>(initial: T) => ({ current: initial }),
    useEffect: (effect: () => void | (() => void)) => effect(),
    useCallback: <T,>(callback: T) => callback,
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { ChatInput } from "./chat-input"

describe("ChatInput mount retrieval preference", () => {
  it("does not write the browser smart fallback into the shared Agent preference", () => {
    const onRetrievalModeChange = vi.fn()

    ChatInput({
      onSend: vi.fn(),
      onStop: vi.fn(),
      isStreaming: false,
      retrievalMode: "smart",
      onRetrievalModeChange,
    })

    expect(onRetrievalModeChange).not.toHaveBeenCalled()
  })
})

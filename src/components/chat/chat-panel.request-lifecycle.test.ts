import { beforeEach, describe, expect, it, vi } from "vitest"

const hookHarness = vi.hoisted(() => {
  type EffectSlot = {
    kind: "effect"
    deps?: readonly unknown[]
    cleanup?: void | (() => void)
  }
  type RefSlot = { kind: "ref"; value: { current: unknown } }
  type CallbackSlot = { kind: "callback" }
  type Slot = EffectSlot | RefSlot | CallbackSlot
  let cursor = 0
  let slots: Slot[] = []

  const depsEqual = (left?: readonly unknown[], right?: readonly unknown[]) =>
    Boolean(left && right && left.length === right.length && left.every((value, index) => Object.is(value, right[index])))

  return {
    reset() {
      for (const slot of slots) {
        if (slot.kind === "effect") slot.cleanup?.()
      }
      slots = []
      cursor = 0
    },
    beginRender() {
      cursor = 0
    },
    useRef<T>(initial: T) {
      const index = cursor++
      const existing = slots[index]
      if (existing?.kind === "ref") return existing.value as { current: T }
      const value = { current: initial }
      slots[index] = { kind: "ref", value: value as { current: unknown } }
      return value
    },
    useEffect(effect: () => void | (() => void), deps?: readonly unknown[]) {
      const index = cursor++
      const existing = slots[index]
      if (existing?.kind === "effect" && depsEqual(existing.deps, deps)) return
      if (existing?.kind === "effect") existing.cleanup?.()
      slots[index] = { kind: "effect", deps, cleanup: effect() }
    },
    useCallback<T>(callback: T) {
      slots[cursor++] = { kind: "callback" }
      return callback
    },
  }
})

const { searchFaithfulSourcesMock, streamChatMock, searchWikiMock } = vi.hoisted(() => ({
  searchFaithfulSourcesMock: vi.fn(),
  streamChatMock: vi.fn(),
  searchWikiMock: vi.fn(),
}))

vi.mock("react", async (importOriginal) => ({
  ...await importOriginal<typeof import("react")>(),
  useRef: hookHarness.useRef,
  useEffect: hookHarness.useEffect,
  useCallback: hookHarness.useCallback,
}))

vi.mock("react-i18next", async (importOriginal) => ({
  ...await importOriginal<typeof import("react-i18next")>(),
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("./chat-input", () => ({ ChatInput: "mock-chat-input" }))
vi.mock("./chat-message", () => ({
  ChatMessage: "mock-chat-message",
  StreamingMessage: "mock-streaming-message",
  useSourceFiles: () => undefined,
}))

vi.mock("@/lib/faithful-source-search", () => ({
  searchFaithfulSources: searchFaithfulSourcesMock,
}))

vi.mock("@/lib/llm-client", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/llm-client")>(),
  streamChat: streamChatMock,
}))

vi.mock("@/lib/search", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/search")>(),
  searchWiki: searchWikiMock,
}))

vi.mock("@/stores/chat-store", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/stores/chat-store")>()
  const store = actual.useChatStore
  const hook = Object.assign(
    <T,>(selector: (state: ReturnType<typeof store.getState>) => T) => selector(store.getState()),
    {
      getState: store.getState,
      setState: store.setState,
      subscribe: store.subscribe,
    },
  )
  return { ...actual, useChatStore: hook }
})

vi.mock("@/stores/wiki-store", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/stores/wiki-store")>()
  const store = actual.useWikiStore
  const hook = Object.assign(
    <T,>(selector: (state: ReturnType<typeof store.getState>) => T) => selector(store.getState()),
    {
      getState: store.getState,
      setState: store.setState,
      subscribe: store.subscribe,
    },
  )
  return { ...actual, useWikiStore: hook }
})

import { ChatPanel, getLastQueryPages } from "./chat-panel"
import { useChatStore } from "@/stores/chat-store"
import { useWikiStore } from "@/stores/wiki-store"
import type { ChatSendOptions } from "./chat-input"

interface ElementLike {
  type?: unknown
  props?: Record<string, unknown> & { children?: unknown }
}

interface ChatInputTestProps {
  onSend: (text: string, images: never[], options: ChatSendOptions) => Promise<void>
  onStop: () => void
}

interface StreamCallbacks {
  onToken: (token: string) => void
  onDone: () => void
}

function findElement(node: unknown, type: unknown): ElementLike | null {
  if (Array.isArray(node)) {
    for (const child of node) {
      const match = findElement(child, type)
      if (match) return match
    }
    return null
  }
  if (!node || typeof node !== "object") return null
  const element = node as ElementLike
  if (element.type === type) return element
  return findElement(element.props?.children, type)
}

function renderPanel(): ChatInputTestProps {
  hookHarness.beginRender()
  const tree = ChatPanel()
  const input = findElement(tree, "mock-chat-input")
  if (!input) throw new Error("ChatInput not found")
  return input.props as unknown as ChatInputTestProps
}

function project(path: string) {
  return { id: path, name: path, path }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((settle) => { resolve = settle })
  return { promise, resolve }
}

const faithfulOptions: ChatSendOptions = {
  retrievalMode: "faithful",
  useWebSearch: false,
  useAnyTxtSearch: false,
}

beforeEach(() => {
  hookHarness.reset()
  searchFaithfulSourcesMock.mockReset()
  streamChatMock.mockReset()
  searchWikiMock.mockReset()
  searchWikiMock.mockResolvedValue([])
  useChatStore.setState({
    conversations: [],
    activeConversationId: null,
    messages: [],
    isStreaming: false,
    streamingContent: "",
    streamingRequestId: null,
    streamingConversationId: null,
    retrievalMode: "faithful",
  })
  useWikiStore.setState({ project: project("/projects/A") })
})

describe("ChatPanel request lifecycle", () => {
  it("keeps retrieval output in the conversation that started the request", async () => {
    const first = useChatStore.getState().createConversation()
    const second = useChatStore.getState().createConversation()
    useChatStore.getState().setActiveConversation(first)
    const search = deferred<Array<{ path: string; title: string; snippet: string; content: string }>>()
    searchFaithfulSourcesMock.mockReturnValueOnce(search.promise)
    let callbacks!: StreamCallbacks
    let settleStream!: () => void
    streamChatMock.mockImplementationOnce((
      _config: unknown,
      _messages: unknown,
      nextCallbacks: StreamCallbacks,
    ) => new Promise<void>((resolve) => {
      callbacks = nextCallbacks
      settleStream = resolve
    }))
    const input = renderPanel()

    const send = input.onSend("question", [], faithfulOptions)
    useChatStore.getState().setActiveConversation(second)
    search.resolve([{
      path: "/projects/A/raw/sources/notes.txt",
      title: "notes.txt",
      snippet: "evidence",
      content: "evidence",
    }])
    await vi.waitFor(() => expect(streamChatMock).toHaveBeenCalledOnce())
    callbacks.onToken("bound answer")
    expect(useChatStore.getState()).toEqual(expect.objectContaining({
      activeConversationId: second,
      streamingConversationId: first,
      streamingContent: "bound answer",
    }))
    callbacks.onDone()
    settleStream()
    await send

    expect(useChatStore.getState().messages.filter((message) => message.conversationId === first))
      .toEqual(expect.arrayContaining([
        expect.objectContaining({
          role: "assistant",
          content: "bound answer",
          references: [expect.objectContaining({ path: "raw/sources/notes.txt" })],
        }),
      ]))
    expect(useChatStore.getState().messages.filter(
      (message) => message.conversationId === second && message.role === "assistant",
    )).toEqual([])
    expect(getLastQueryPages("/projects/A", first)).toEqual([
      { title: "notes.txt", path: "raw/sources/notes.txt" },
    ])
    expect(getLastQueryPages("/projects/A", second)).toEqual([])
  })

  it("aborts and discards late retrieval output after a project switch", async () => {
    useChatStore.getState().createConversation()
    const search = deferred<Array<{ path: string; title: string; snippet: string; content: string }>>()
    searchFaithfulSourcesMock.mockReturnValueOnce(search.promise)
    const input = renderPanel()
    const send = input.onSend("question", [], faithfulOptions)
    useWikiStore.setState({ project: project("/projects/B") })
    renderPanel()
    search.resolve([{
      path: "/projects/A/raw/sources/secret.txt",
      title: "secret.txt",
      snippet: "secret",
      content: "secret",
    }])
    await send

    expect(streamChatMock).not.toHaveBeenCalled()
    expect(useChatStore.getState().isStreaming).toBe(false)
    expect(useChatStore.getState().messages.filter((message) => message.role === "assistant")).toEqual([])
    expect(getLastQueryPages("/projects/B", useChatStore.getState().activeConversationId ?? ""))
      .toEqual([])
  })

  it("does not let a delayed cancelled request settle a newer request", async () => {
    useChatStore.getState().createConversation()
    searchFaithfulSourcesMock.mockResolvedValue([])
    const streams: Array<{
      callbacks: StreamCallbacks
      signal: AbortSignal
      resolve: () => void
    }> = []
    streamChatMock.mockImplementation((
      _config: unknown,
      _messages: unknown,
      callbacks: StreamCallbacks,
      signal: AbortSignal,
    ) => new Promise<void>((resolve) => streams.push({ callbacks, signal, resolve })))
    const input = renderPanel()

    const first = input.onSend("first", [], faithfulOptions)
    await vi.waitFor(() => expect(streams).toHaveLength(1))
    input.onStop()
    const second = input.onSend("second", [], faithfulOptions)
    await vi.waitFor(() => expect(streams).toHaveLength(2))
    const secondRequestId = useChatStore.getState().streamingRequestId

    streams[0].callbacks.onDone()
    streams[0].resolve()
    await first
    expect(useChatStore.getState().streamingRequestId).toBe(secondRequestId)
    expect(useChatStore.getState().isStreaming).toBe(true)

    input.onStop()
    expect(streams[1].signal.aborted).toBe(true)
    streams[1].callbacks.onDone()
    streams[1].resolve()
    await second
    expect(useChatStore.getState().isStreaming).toBe(false)
    expect(useChatStore.getState().messages.filter((message) => message.role === "assistant")).toEqual([])
  })

  it("aborts an in-flight request when ChatPanel unmounts", async () => {
    useChatStore.getState().createConversation()
    searchFaithfulSourcesMock.mockResolvedValue([])
    let callbacks!: StreamCallbacks
    let signal!: AbortSignal
    let settle!: () => void
    streamChatMock.mockImplementationOnce((
      _config: unknown,
      _messages: unknown,
      nextCallbacks: StreamCallbacks,
      nextSignal: AbortSignal,
    ) => new Promise<void>((resolve) => {
      callbacks = nextCallbacks
      signal = nextSignal
      settle = resolve
    }))
    const input = renderPanel()

    const send = input.onSend("question", [], faithfulOptions)
    await vi.waitFor(() => expect(streamChatMock).toHaveBeenCalledOnce())
    hookHarness.reset()
    expect(signal.aborted).toBe(true)

    callbacks.onDone()
    settle()
    await send
    expect(useChatStore.getState().isStreaming).toBe(false)
  })

  it("releases the request when standard retrieval preparation throws", async () => {
    useChatStore.getState().createConversation()
    searchWikiMock.mockRejectedValueOnce(new Error("search index offline"))
    const input = renderPanel()

    await input.onSend("question", [], {
      retrievalMode: "standard",
      useWebSearch: false,
      useAnyTxtSearch: false,
    })

    expect(useChatStore.getState().isStreaming).toBe(false)
    expect(useChatStore.getState().messages.filter((message) => message.role === "assistant"))
      .toEqual([expect.objectContaining({ content: "Error: search index offline" })])
  })
})

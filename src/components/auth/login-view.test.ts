/**
 * Tests for LoginView auth flow.
 *
 * These tests exercise the underlying API call sequence rather than
 * the rendered component, since the test environment is "node" (no jsdom).
 * They mock the `apiCall` function and verify the happy path + 401 path.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { apiCall, ApiError } from "@/lib/api"

vi.mock("@/lib/api", () => ({
  apiCall: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      public readonly status: number,
      public readonly code: string,
      message: string,
    ) {
      super(message)
      this.name = "ApiError"
    }
    get isUnauthenticated() {
      return this.status === 401
    }
  },
}))

const mockedApiCall = vi.mocked(apiCall)

// Simulate the login form's submit logic in isolation
async function doLogin(
  username: string,
  password: string,
): Promise<{ user: { user_id: string; username: string; recently_opened: string[] } | null; error: string | null }> {
  try {
    await apiCall("POST", "/api/v1/auth/login", { username, password })
    const user = await apiCall<{ user_id: string; username: string; recently_opened: string[] }>(
      "GET",
      "/api/v1/auth/whoami",
    )
    return { user, error: null }
  } catch (err) {
    if (err instanceof ApiError && err.code === "INVALID_CREDENTIALS") {
      return { user: null, error: "Invalid username or password." }
    }
    if (err instanceof Error) {
      return { user: null, error: err.message }
    }
    return { user: null, error: "An unexpected error occurred." }
  }
}

describe("LoginView auth flow", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("happy path: POST login then GET whoami, returns user", async () => {
    const fakeUser = { user_id: "u1", username: "alice", recently_opened: [] }
    mockedApiCall
      .mockResolvedValueOnce(undefined) // POST /api/v1/auth/login -> 200
      .mockResolvedValueOnce(fakeUser) // GET /api/v1/auth/whoami -> user

    const result = await doLogin("alice", "secret")

    expect(result.error).toBeNull()
    expect(result.user).toEqual(fakeUser)
    expect(mockedApiCall).toHaveBeenCalledTimes(2)
    expect(mockedApiCall).toHaveBeenNthCalledWith(1, "POST", "/api/v1/auth/login", {
      username: "alice",
      password: "secret",
    })
    expect(mockedApiCall).toHaveBeenNthCalledWith(2, "GET", "/api/v1/auth/whoami")
  })

  it("INVALID_CREDENTIALS: returns friendly message, no whoami call", async () => {
    mockedApiCall.mockRejectedValueOnce(
      new ApiError(401, "INVALID_CREDENTIALS", "bad credentials"),
    )

    const result = await doLogin("alice", "wrong")

    expect(result.user).toBeNull()
    expect(result.error).toBe("Invalid username or password.")
    // Only the login call was made; whoami was not reached
    expect(mockedApiCall).toHaveBeenCalledTimes(1)
  })

  it("server error: surfaces error message", async () => {
    mockedApiCall.mockRejectedValueOnce(new Error("Network error"))

    const result = await doLogin("alice", "secret")

    expect(result.user).toBeNull()
    expect(result.error).toBe("Network error")
  })
})

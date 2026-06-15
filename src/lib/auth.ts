/**
 * Minimal auth state for the browser/LAN build.
 *
 * Wraps whoami result in a single module-level ref so callers get
 * consistent state without a heavyweight global store.
 */

export interface AuthUser {
  user_id: string
  username: string
  recently_opened: string[]
}

// Module-level singleton — avoids a full Zustand slice for a single boolean.
let currentUser: AuthUser | null = null

export function setAuthUser(user: AuthUser | null): void {
  currentUser = user
}

export function getAuthUser(): AuthUser | null {
  return currentUser
}

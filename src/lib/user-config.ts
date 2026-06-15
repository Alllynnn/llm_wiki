//! Per-user JSON config backed by /api/v1/config.
//!
//! Mirrors the plugin-store API surface (get/set by key) so callers can
//! migrate with minimal changes. Internally, the entire config is a single
//! opaque JSON object owned by the server.

import { apiCall } from "./api";

let cached: Record<string, unknown> | null = null;
let pending: Promise<Record<string, unknown>> | null = null;

async function load(): Promise<Record<string, unknown>> {
  if (cached !== null) return cached;
  if (pending) return pending;
  pending = (async () => {
    const cfg = await apiCall<Record<string, unknown>>("GET", "/api/v1/config");
    cached = cfg ?? {};
    return cached;
  })();
  try {
    return await pending;
  } finally {
    pending = null;
  }
}

async function save(cfg: Record<string, unknown>): Promise<void> {
  await apiCall("PUT", "/api/v1/config", cfg);
  cached = cfg;
}

/** Returns the full config object. */
export async function loadConfig(): Promise<Record<string, unknown>> {
  return await load();
}

/** Replaces the full config object. */
export async function saveConfig(
  cfg: Record<string, unknown>,
): Promise<void> {
  await save(cfg);
}

/** Reads a single key from the config (or undefined). */
export async function getConfigKey<T = unknown>(
  key: string,
): Promise<T | undefined> {
  const cfg = await load();
  return cfg[key] as T | undefined;
}

/** Updates a single key in the config (load + merge + save). */
export async function setConfigKey(
  key: string,
  value: unknown,
): Promise<void> {
  const cfg = await load();
  cfg[key] = value;
  await save(cfg);
}

/** Removes a key from the config. */
export async function deleteConfigKey(key: string): Promise<void> {
  const cfg = await load();
  delete cfg[key];
  await save(cfg);
}

/** Clears the in-memory cache. Useful for testing or after logout. */
export function clearConfigCache(): void {
  cached = null;
}

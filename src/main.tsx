import React from "react";
import ReactDOM from "react-dom/client";
import { sha256 } from "@noble/hashes/sha2";
import App from "./App";
import { LlmWikiArchitecturePage } from "@/components/architecture/llm-wiki-architecture-page";
import "./index.css";
import "@/i18n";
import { loadAndApplyTheme, watchSystemTheme } from "@/lib/theme";
import { AppDialogHost } from "@/components/app-dialog-host";

// crypto.randomUUID() and crypto.subtle are only defined in secure contexts
// (https / localhost / 127.0.0.1). Over plain http on a LAN IP they're
// undefined, which breaks project creation (randomUUID) and the entire
// ingest pipeline (subtle.digest for source-content hashing).
if (typeof crypto !== "undefined" && typeof crypto.randomUUID !== "function") {
  (crypto as Crypto & { randomUUID: () => `${string}-${string}-${string}-${string}-${string}` }).randomUUID = () => {
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const hex = Array.from(b, (n) => n.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  };
}

if (typeof crypto !== "undefined" && !crypto.subtle) {
  // Provide just enough of SubtleCrypto for the codebase's actual usage: a
  // SHA-256 digest wrapped in a resolved Promise. Other algorithms / ops
  // are not stubbed, so a future caller of (e.g.) AES-GCM hits a clear
  // "method missing" instead of a silent wrong result.
  const toBytes = (data: BufferSource): Uint8Array => {
    if (data instanceof Uint8Array) return data;
    if (data instanceof ArrayBuffer) return new Uint8Array(data);
    return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  };
  const subtleShim: Partial<SubtleCrypto> = {
    digest: async (algorithm: AlgorithmIdentifier, data: BufferSource): Promise<ArrayBuffer> => {
      const name = typeof algorithm === "string" ? algorithm : algorithm.name;
      if (name.toUpperCase().replace("-", "") !== "SHA256") {
        throw new Error(`crypto.subtle shim: unsupported digest algorithm "${name}" (only SHA-256 is polyfilled for insecure-context use)`);
      }
      const out = sha256(toBytes(data));
      return out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength) as ArrayBuffer;
    },
  };
  Object.defineProperty(crypto, "subtle", {
    value: subtleShim,
    configurable: true,
  });
}

function applyPlatformClass() {
  const isTauri = "__TAURI_INTERNALS__" in window || "__TAURI__" in window;
  if (isTauri && navigator.userAgent.includes("Mac OS X")) {
    document.documentElement.classList.add("platform-macos");
  }
}

// Apply theme before render to avoid flash
async function initApp() {
  try {
    applyPlatformClass();
    await loadAndApplyTheme();
    watchSystemTheme();
    const isArchitectureRoute = window.location.pathname === "/architecture";

    ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
      <React.StrictMode>
        {isArchitectureRoute ? <LlmWikiArchitecturePage /> : <App />}
        <AppDialogHost />
      </React.StrictMode>
    );
  } catch (err) {
    console.error("[startup] failed to initialize LLM Wiki:", err);
    const root = document.getElementById("root");
    if (root) {
      const message = err instanceof Error ? (err.stack ?? err.message) : String(err);
      root.innerHTML = `
        <div style="font-family: system-ui, sans-serif; padding: 24px; color: #111; color: light-dark(#111, #f5f5f5); background: #fff; background: light-dark(#fff, #111); min-height: 100vh; color-scheme: light dark;">
          <h1 style="font-size: 18px; margin: 0 0 12px;">LLM Wiki failed to start</h1>
          <p style="margin: 0 0 12px;">The frontend startup code threw an error before React could render.</p>
          <pre style="white-space: pre-wrap; border: 1px solid light-dark(#ddd, #333); border-radius: 8px; padding: 12px; background: light-dark(#f7f7f7, #1d1d1d);">${message.replace(/[&<>"']/g, (ch) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          }[ch] ?? ch))}</pre>
        </div>
      `;
    }
  }
}

initApp();

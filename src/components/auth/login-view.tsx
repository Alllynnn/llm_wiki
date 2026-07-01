import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiCall, ApiError } from "@/lib/api"
import { useTranslation } from "react-i18next"

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AuthUser {
  user_id: string
  username: string
  recently_opened: string[]
}

export interface LoginViewProps {
  /** Called when login succeeds with the authenticated user object. */
  onLogin: (user: AuthUser) => void
}

// ─── Component ────────────────────────────────────────────────────────────────

export function LoginView({ onLogin }: LoginViewProps) {
  const { t } = useTranslation()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      await apiCall("POST", "/api/v1/auth/login", { username, password })
      const user = await apiCall<AuthUser>("GET", "/api/v1/auth/whoami")
      onLogin(user)
    } catch (err) {
      if (err instanceof ApiError && err.code === "INVALID_CREDENTIALS") {
        setError(t("auth.invalidCredentials"))
      } else if (err instanceof Error) {
        setError(err.message)
      } else {
        setError(t("auth.unexpectedError"))
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm rounded-xl border bg-popover p-8 shadow-sm ring-1 ring-foreground/10">
        {/* App title */}
        <div className="mb-6 text-center">
          <h1 className="font-heading text-xl font-semibold tracking-tight">{t("app.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("auth.signInPrompt")}</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="username">{t("auth.username")}</Label>
            <Input
              id="username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={submitting}
              required
              placeholder={t("auth.usernamePlaceholder")}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">{t("auth.password")}</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              required
              placeholder={t("auth.passwordPlaceholder")}
            />
          </div>

          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" disabled={submitting} className="mt-1 w-full">
            {submitting ? t("auth.signingIn") : t("auth.login")}
          </Button>
        </form>
      </div>
    </div>
  )
}

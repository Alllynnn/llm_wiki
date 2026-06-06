import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { SettingsDraft, DraftSetter } from "../settings-types"
import type { MineruModelVersion } from "@/stores/wiki-store"
import { testMineruConnection } from "@/lib/mineru"

interface Props {
  draft: SettingsDraft
  setDraft: DraftSetter
}

type TestState = "idle" | "running" | "success" | "failed"

export function MineruSection({ draft, setDraft }: Props) {
  const { t } = useTranslation()
  const [testState, setTestState] = useState<TestState>("idle")
  const [testError, setTestError] = useState("")

  const handleTest = async () => {
    if (!draft.mineruToken.trim()) return
    setTestState("running")
    setTestError("")
    try {
      await testMineruConnection(draft.mineruToken.trim())
      setTestState("success")
    } catch (err) {
      setTestState("failed")
      setTestError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">
          {t("settings.mineru", { defaultValue: "MinerU PDF Parser" })}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {t("settings.mineruDescription", {
            defaultValue:
              "Use MinerU cloud API for higher quality PDF parsing (tables, formulas, complex layouts)",
          })}
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Checkbox
          id="mineru-enabled"
          checked={draft.mineruEnabled}
          onCheckedChange={(checked) =>
            setDraft("mineruEnabled", checked === true)
          }
        />
        <Label htmlFor="mineru-enabled">
          {t("settings.mineruEnabled", { defaultValue: "Enable MinerU" })}
        </Label>
      </div>

      {draft.mineruEnabled && (
        <div className="space-y-4 pl-1">
          <div className="space-y-2">
            <Label htmlFor="mineru-token">
              {t("settings.mineruToken", { defaultValue: "API Token" })}
            </Label>
            <Input
              id="mineru-token"
              type="password"
              value={draft.mineruToken}
              onChange={(e) => {
                setDraft("mineruToken", e.target.value)
                setTestState("idle")
              }}
              placeholder={t("settings.mineruTokenHint", {
                defaultValue: "Get your token from mineru.net",
              })}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="mineru-model">
              {t("settings.mineruModel", { defaultValue: "Model Version" })}
            </Label>
            <Select
              value={draft.mineruModelVersion}
              onValueChange={(v) =>
                setDraft("mineruModelVersion", v as MineruModelVersion)
              }
            >
              <SelectTrigger id="mineru-model">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="vlm">
                  {t("settings.mineruModelVlm", {
                    defaultValue: "VLM (Recommended, best for complex layouts)",
                  })}
                </SelectItem>
                <SelectItem value="pipeline">
                  {t("settings.mineruModelPipeline", {
                    defaultValue: "Pipeline (Faster)",
                  })}
                </SelectItem>
                <SelectItem value="mineru-html">
                  {t("settings.mineruModelHtml", {
                    defaultValue: "MinerU-HTML",
                  })}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={handleTest}
              disabled={
                !draft.mineruToken.trim() || testState === "running"
              }
            >
              {testState === "running"
                ? t("settings.mineruTesting", { defaultValue: "Testing..." })
                : t("settings.mineruTest", {
                    defaultValue: "Test Connection",
                  })}
            </Button>
            {testState === "success" && (
              <span className="text-sm text-green-600">
                {t("settings.mineruTestSuccess", {
                  defaultValue: "Connection successful",
                })}
              </span>
            )}
            {testState === "failed" && (
              <span className="text-sm text-red-600">
                {t("settings.mineruTestFailed", {
                  defaultValue: "Test failed",
                })}
                : {testError}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

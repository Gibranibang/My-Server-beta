import { useEffect, useRef, useState, type FormEvent } from "react"
import { AlertCircle, CheckCircle2, LoaderCircle } from "lucide-react"
import { getCompanionApi } from "../api"
import { getTranslation } from "../i18n"
import type { WizardStepProps } from "./StepConnection"

export function validateWanUrl(raw: string): { valid: boolean; normalized: string } {
  const trimmed = raw.trim()
  if (!trimmed) {
    return { valid: true, normalized: "" }
  }
  if (/\s/.test(trimmed)) {
    return { valid: false, normalized: trimmed }
  }

  try {
    const parsed = new URL(trimmed)
    if ((parsed.protocol !== "https:" && parsed.protocol !== "http:") || !parsed.hostname) {
      return { valid: false, normalized: trimmed }
    }
    return { valid: true, normalized: trimmed.replace(/\/+$/, "") }
  } catch {
    return { valid: false, normalized: trimmed }
  }
}

export function StepWanDomain({
  draft,
  onPatchDraft,
  onNext,
  onBack,
  language,
  onNotify,
  onErrorChange,
}: WizardStepProps) {
  const t = getTranslation(language)
  const [testing, setTesting] = useState(false)
  const [probeError, setProbeError] = useState("")
  const [probeOkMsg, setProbeOkMsg] = useState("")

  const onErrorChangeRef = useRef(onErrorChange)
  onErrorChangeRef.current = onErrorChange

  const urlCheck = validateWanUrl(draft.wanUrl)
  const validationError = !urlCheck.valid ? t("wiz_wan_invalid") : ""

  useEffect(() => {
    onErrorChangeRef.current?.(Boolean(validationError))
  }, [validationError])

  const hasInput = draft.wanUrl.trim().length > 0
  const canTest = Boolean(hasInput && urlCheck.valid && !testing)

  const handleChange = (value: string) => {
    setProbeError("")
    setProbeOkMsg("")
    onPatchDraft({ wanUrl: value })
  }

  const handleTestDomain = async () => {
    if (!canTest) return
    const api = getCompanionApi()
    setTesting(true)
    setProbeError("")
    setProbeOkMsg("")

    try {
      const res = api.probeUrl ? await api.probeUrl(urlCheck.normalized) : { reachable: false }
      if (res?.reachable) {
        setProbeOkMsg(t("wiz_wan_ok"))
        onNotify?.(t("wiz_wan_ok"), "success")
      } else {
        setProbeError(res?.error || t("wiz_wan_err"))
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t("wiz_wan_err")
      setProbeError(message || t("wiz_wan_err"))
    } finally {
      setTesting(false)
    }
  }

  const handleSkip = () => {
    setProbeError("")
    setProbeOkMsg("")
    onErrorChangeRef.current?.(false)
    onPatchDraft({ wanUrl: "" })
    onNext()
  }

  const handleContinue = () => {
    if (testing || !urlCheck.valid) return
    onPatchDraft({ wanUrl: urlCheck.normalized })
    onNext()
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    handleContinue()
  }

  return (
    <form className="wiz-card" onSubmit={handleSubmit} noValidate>
      <div className="wiz-card-header">
        <div>
          <h2 className="wiz-step-title">{t("wiz_step2_title")}</h2>
          <p className="wiz-step-sub">{t("wiz_step2_sub")}</p>
        </div>
        <span className="wiz-opt-badge">{t("wiz_optional_badge")}</span>
      </div>

      <div className="wiz-field">
        <label htmlFor="wiz-wan-url">{t("wiz_wan_label")}</label>
        <div className="input-action-row">
          <input
            id="wiz-wan-url"
            type="url"
            className="wiz-input is-mono"
            placeholder={t("wiz_wan_placeholder")}
            value={draft.wanUrl}
            onChange={e => handleChange(e.target.value)}
            aria-invalid={Boolean(validationError)}
          />
          <button
            type="button"
            className="wiz-btn wiz-btn-secondary"
            disabled={!canTest}
            onClick={() => void handleTestDomain()}
          >
            {testing ? (
              <>
                <LoaderCircle size={14} className="wiz-spin" aria-hidden="true" />
                <span>{t("wiz_testing_conn")}</span>
              </>
            ) : (
              <span>{t("wiz_test_domain")}</span>
            )}
          </button>
        </div>
      </div>

      {validationError && (
        <div className="status-line is-err" role="alert">
          <AlertCircle size={14} aria-hidden="true" />
          <span>{validationError}</span>
        </div>
      )}

      {!validationError && probeError && (
        <div className="status-line is-err" role="alert">
          <AlertCircle size={14} aria-hidden="true" />
          <span>{probeError}</span>
        </div>
      )}

      {!validationError && !probeError && probeOkMsg && (
        <div className="status-line is-ok" role="status">
          <CheckCircle2 size={14} aria-hidden="true" />
          <span>{probeOkMsg}</span>
        </div>
      )}

      <div className="wiz-footer">
        <div className="wiz-footer-left">
          <button
            type="button"
            className="wiz-btn wiz-btn-secondary"
            onClick={onBack}
            disabled={testing}
          >
            {t("wiz_back")}
          </button>
          <button
            type="button"
            className="wiz-btn wiz-btn-ghost"
            onClick={handleSkip}
            disabled={testing}
          >
            {t("wiz_skip")}
          </button>
        </div>
        <button
          type="submit"
          className="wiz-btn wiz-btn-primary"
          disabled={testing || Boolean(validationError)}
        >
          {t("wiz_next")}
        </button>
      </div>
    </form>
  )
}

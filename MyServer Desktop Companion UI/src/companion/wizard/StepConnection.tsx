import { useEffect, useRef, useState, type FormEvent } from "react"
import { AlertCircle, CheckCircle2, Globe, LoaderCircle, Wifi } from "lucide-react"
import { getCompanionApi } from "../api"
import { getTranslation, type Language } from "../i18n"
import type { WizardDraft } from "../types"
import { cx } from "../ui"

export interface WizardStepProps {
  draft: WizardDraft
  onPatchDraft: (patch: Partial<WizardDraft>) => void
  onNext: () => void
  onBack: () => void
  language: Language
  onNotify?: (msg: string, type?: "info" | "success" | "error" | "warning") => void
  onErrorChange?: (hasError: boolean) => void
}

const REMOTE_ID_RE = /^[0-9a-fA-F]{16}$/

export function normalizeLanUrl(raw: string): string | null {
  const trimmed = raw.trim()
  if (!trimmed) return ""
  if (/\s/.test(trimmed)) return null

  const hasScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(trimmed)
  const candidate = hasScheme ? trimmed : `http://${trimmed}`

  try {
    const parsed = new URL(candidate)
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null
    }
    if (!parsed.hostname) {
      return null
    }
    const clean = candidate.replace(/\/+$/, "")
    return clean
  } catch {
    return null
  }
}

export function StepConnection({
  draft,
  onPatchDraft,
  onNext,
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

  const isLan = draft.connectionMode === "lan"
  const trimmedLan = draft.lanUrl.trim()
  const normalizedLan = isLan ? normalizeLanUrl(draft.lanUrl) : ""
  const trimmedRemote = draft.remoteId.trim()

  const validationError = isLan
    ? trimmedLan !== "" && normalizedLan === null
      ? t("wiz_lan_invalid")
      : ""
    : trimmedRemote !== "" && !REMOTE_ID_RE.test(trimmedRemote)
      ? t("wiz_remote_invalid")
      : ""

  const hasError = Boolean(validationError || probeError)
  useEffect(() => {
    onErrorChangeRef.current?.(hasError)
  }, [hasError])

  const canTest = isLan
    ? Boolean(trimmedLan && normalizedLan)
    : REMOTE_ID_RE.test(trimmedRemote)

  const handleModeChange = (mode: "lan" | "remote") => {
    if (mode === draft.connectionMode || testing) return
    setProbeError("")
    setProbeOkMsg("")
    onPatchDraft({ connectionMode: mode, connectionVerified: false })
  }

  const handleLanChange = (value: string) => {
    setProbeError("")
    setProbeOkMsg("")
    onPatchDraft({ lanUrl: value, connectionVerified: false })
  }

  const handleRemoteChange = (value: string) => {
    setProbeError("")
    setProbeOkMsg("")
    onPatchDraft({ remoteId: value, connectionVerified: false })
  }

  const handleTestConnection = async () => {
    if (testing || !canTest) return
    const api = getCompanionApi()
    setTesting(true)
    setProbeError("")
    setProbeOkMsg("")

    try {
      if (isLan) {
        const targetUrl = normalizeLanUrl(draft.lanUrl)
        if (!targetUrl) {
          setProbeError(t("wiz_lan_invalid"))
          onPatchDraft({ connectionVerified: false })
          return
        }
        onPatchDraft({ lanUrl: targetUrl, connectionVerified: false })

        const res = api.probeUrl ? await api.probeUrl(targetUrl) : { reachable: false }
        if (res?.reachable) {
          const latencySuffix =
            typeof res.latency_ms === "number" && Number.isFinite(res.latency_ms)
              ? ` (${Math.round(res.latency_ms)} ms)`
              : ""
          onPatchDraft({ lanUrl: targetUrl, connectionVerified: true })
          setProbeOkMsg(`${t("wiz_conn_ok")}${latencySuffix}`)
          onNotify?.(t("wiz_conn_ok"), "success")
        } else {
          onPatchDraft({ connectionVerified: false })
          setProbeError(res?.error || t("wiz_conn_err"))
        }
        return
      }

      const cleanId = trimmedRemote.toLowerCase()
      if (!REMOTE_ID_RE.test(cleanId)) {
        setProbeError(t("wiz_remote_invalid"))
        onPatchDraft({ connectionVerified: false })
        return
      }

      onPatchDraft({ remoteId: cleanId, connectionVerified: false })

      const startRes = api.startEasyTier
        ? await api.startEasyTier({ remote_id: cleanId })
        : { success: false, message: t("wiz_conn_err") }

      if (startRes && startRes.success === false) {
        onPatchDraft({ connectionVerified: false })
        setProbeError(startRes.message || t("wiz_conn_err"))
        return
      }

      const remoteStatus = api.getRemoteStatus ? await api.getRemoteStatus() : null
      const et = remoteStatus?.easytier
      const running = remoteStatus
        ? Boolean(et?.running ?? remoteStatus?.running)
        : Boolean(startRes?.status?.running ?? startRes?.success)

      if (running) {
        onPatchDraft({ remoteId: cleanId, connectionVerified: true })
        const serverIp = et?.server_peer_ip || null
        const okMsg = serverIp ? `${t("wiz_conn_ok")} (${serverIp})` : t("wiz_conn_ok")
        setProbeOkMsg(okMsg)
        onNotify?.(okMsg, "success")
      } else {
        onPatchDraft({ connectionVerified: false })
        setProbeError(startRes?.message || t("wiz_conn_err"))
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t("wiz_conn_err")
      onPatchDraft({ connectionVerified: false })
      setProbeError(message || t("wiz_conn_err"))
    } finally {
      setTesting(false)
    }
  }

  const canAdvance = Boolean(draft.connectionVerified && !testing && !validationError)

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (canAdvance) {
      onNext()
    } else if (canTest) {
      void handleTestConnection()
    }
  }

  return (
    <form className="wiz-card" onSubmit={handleSubmit} noValidate>
      <div className="wiz-card-header">
        <div>
          <h2 className="wiz-step-title">{t("wiz_step1_title")}</h2>
          <p className="wiz-step-sub">{t("wiz_step1_sub")}</p>
        </div>
        <span className="wiz-req-badge">{t("wiz_required_badge")}</span>
      </div>

      <div className="wiz-seg" role="group" aria-label={t("wiz_step1_title")}>
        <button
          type="button"
          className={cx("wiz-seg-btn", isLan && "is-active")}
          aria-pressed={isLan}
          onClick={() => handleModeChange("lan")}
        >
          <Wifi size={14} aria-hidden="true" />
          <span>{t("wiz_conn_lan")}</span>
        </button>
        <button
          type="button"
          className={cx("wiz-seg-btn", !isLan && "is-active")}
          aria-pressed={!isLan}
          onClick={() => handleModeChange("remote")}
        >
          <Globe size={14} aria-hidden="true" />
          <span>{t("wiz_conn_remote")}</span>
        </button>
      </div>

      {isLan ? (
        <div className="wiz-field">
          <label htmlFor="wiz-lan-url">{t("wiz_lan_label")}</label>
          <input
            id="wiz-lan-url"
            type="text"
            className="wiz-input is-mono"
            placeholder={t("wiz_lan_placeholder")}
            value={draft.lanUrl}
            onChange={e => handleLanChange(e.target.value)}
            onBlur={() => {
              if (normalizedLan && normalizedLan !== draft.lanUrl) {
                onPatchDraft({ lanUrl: normalizedLan })
              }
            }}
            aria-invalid={Boolean(validationError)}
          />
        </div>
      ) : (
        <div className="wiz-field">
          <label htmlFor="wiz-remote-id">{t("wiz_remote_label")}</label>
          <input
            id="wiz-remote-id"
            type="text"
            maxLength={16}
            className="wiz-input is-mono wiz-mono"
            placeholder={t("wiz_remote_placeholder")}
            value={draft.remoteId}
            onChange={e => handleRemoteChange(e.target.value)}
            aria-invalid={Boolean(validationError)}
          />
          <div className="trust-note wiz-uac-note">
            <span>{t("wiz_uac_notice")}</span>
          </div>
        </div>
      )}

      {(validationError || probeError) && (
        <div className="status-line is-err" role="alert">
          <AlertCircle size={14} aria-hidden="true" />
          <span>{validationError || probeError}</span>
        </div>
      )}

      {!validationError && !probeError && (probeOkMsg || draft.connectionVerified) && (
        <div className="status-line is-ok" role="status">
          <CheckCircle2 size={14} aria-hidden="true" />
          <span>{probeOkMsg || t("wiz_conn_ok")}</span>
        </div>
      )}

      <div className="wiz-footer">
        <div className="wiz-footer-left">
          <button
            type="button"
            className="wiz-btn wiz-btn-secondary"
            disabled={testing || !canTest}
            onClick={() => void handleTestConnection()}
          >
            {testing ? (
              <>
                <LoaderCircle size={14} className="wiz-spin" aria-hidden="true" />
                <span>{t("wiz_testing_conn")}</span>
              </>
            ) : (
              <span>{t("wiz_test_conn")}</span>
            )}
          </button>
        </div>
        <button
          type="submit"
          className="wiz-btn wiz-btn-primary"
          disabled={!canAdvance}
        >
          {t("wiz_next")}
        </button>
      </div>
    </form>
  )
}

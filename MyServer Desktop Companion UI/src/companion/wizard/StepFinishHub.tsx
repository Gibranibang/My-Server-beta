import React, { useEffect, useRef, useState } from "react"
import { getTranslation, type Language } from "../i18n"
import type { WizardDraft } from "../types"

export interface StepFinishHubProps {
  draft: WizardDraft
  language: Language
  onOpenSubStep: (sub: "5a" | "5b") => void
  onComplete: () => Promise<void> | void
  onBack: () => void
  onNotify?: (msg: string, type?: "info" | "success" | "error" | "warning") => void
  onErrorChange?: (hasError: boolean) => void
}

function parseServerSummary(draft: WizardDraft): string {
  if (draft.serverName.trim()) {
    return draft.serverName.trim()
  }
  if (draft.lanUrl.trim()) {
    try {
      const normalized = /^https?:\/\//i.test(draft.lanUrl.trim())
        ? draft.lanUrl.trim()
        : `http://${draft.lanUrl.trim()}`
      const parsed = new URL(normalized)
      if (parsed.hostname) return parsed.hostname
    } catch {
      return draft.lanUrl.trim()
    }
  }
  if (draft.remoteId.trim()) {
    return draft.remoteId.trim()
  }
  return "MyServer"
}

export const StepFinishHub: React.FC<StepFinishHubProps> = ({
  draft,
  language,
  onOpenSubStep,
  onComplete,
  onBack,
  onNotify,
  onErrorChange,
}) => {
  const t = getTranslation(language)
  const [completing, setCompleting] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const completingRef = useRef(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const handleComplete = async () => {
    if (completingRef.current) return
    completingRef.current = true
    setCompleting(true)
    setErrorMsg(null)
    onErrorChange?.(false)

    try {
      await Promise.resolve(onComplete())
    } catch (err) {
      const raw = err instanceof Error ? err.message : String(err ?? "")
      const clean = raw && raw.length < 180 && !/[\\/]/.test(raw)
        ? raw
        : t("wiz_conn_err", "Gagal menyelesaikan setup")
      if (mountedRef.current) {
        setErrorMsg(clean)
      }
      onErrorChange?.(true)
      onNotify?.(clean, "error")
    } finally {
      completingRef.current = false
      if (mountedRef.current) {
        setCompleting(false)
      }
    }
  }

  const serverLabel = parseServerSummary(draft)
  const backendStatus = draft.backendInstalled
    ? t("wiz_backend_installed", "Terpasang")
    : t("wiz_backend_not_installed", "Dilewati")

  return (
    <div className="wiz-step wiz-step-hub" data-testid="wizard-step-5">
      <div className="wiz-step-header">
        <h2 className="wiz-step-title">
          {t("wiz_step5_title", "Selesai! Konfigurasi Tambahan?")}
        </h2>
        <p className="wiz-step-sub">
          {t(
            "wiz_step5_sub",
            "Server dan backend sudah siap. Anda dapat langsung membuka MyServer atau menambahkan tools berikut kapan saja."
          )}
        </p>
      </div>

      <div className="wiz-kv-list" aria-label={t("wiz_kv_status", "Status")}>
        <div className="wiz-kv-item">
          <span className="wiz-kv-key">{t("wiz_kv_server", "Server")}</span>
          <span className="wiz-kv-val">{serverLabel}</span>
        </div>
        <div className="wiz-kv-item">
          <span className="wiz-kv-key">Login ZimaOS</span>
          <span className="wiz-kv-val">{draft.username.trim() || "—"}</span>
        </div>
        <div className="wiz-kv-item">
          <span className="wiz-kv-key">Backend</span>
          <span className="wiz-kv-val">{backendStatus}</span>
        </div>
      </div>

      <div className="wiz-hub-cards action-cards">
        <button
          type="button"
          className={`wiz-hub-card action-card${draft.syncthingDone ? " is-done" : ""}`}
          data-testid="hub-card-5a"
          onClick={() => onOpenSubStep("5a")}
          disabled={completing}
        >
          <div className="wiz-card-head">
            <span className="wiz-card-title">
              {t("wiz_card_syncthing_title", "Konfigurasi Syncthing")}
            </span>
            <span className={`wiz-badge${draft.syncthingDone ? " is-done" : ""}`}>
              {draft.syncthingDone
                ? t("wiz_configured_badge", "Selesai")
                : t("wiz_optional_badge", "Opsional")}
            </span>
          </div>
          <p className="wiz-card-desc">
            {t(
              "wiz_card_syncthing_desc",
              "Sinkronisasi folder otomatis laptop ↔ server via LAN, ZeroTier, atau domain."
            )}
          </p>
          <span className="wiz-card-cta">
            {t("wiz_configure_btn", "Konfigurasi")} →
          </span>
        </button>

        <button
          type="button"
          className={`wiz-hub-card action-card${draft.vmDone ? " is-done" : ""}`}
          data-testid="hub-card-5b"
          onClick={() => onOpenSubStep("5b")}
          disabled={completing}
        >
          <div className="wiz-card-head">
            <span className="wiz-card-title">
              {t("wiz_card_vm_title", "Tambah Virtual Machine")}
            </span>
            <span className={`wiz-badge${draft.vmDone ? " is-done" : ""}`}>
              {draft.vmDone
                ? t("wiz_configured_badge", "Selesai")
                : t("wiz_optional_badge", "Opsional")}
            </span>
          </div>
          <p className="wiz-card-desc">
            {t(
              "wiz_card_vm_desc",
              "Sambungkan InstaBox MicroVM atau SSH VPS kustom ke panel kontrol."
            )}
          </p>
          <span className="wiz-card-cta">
            {t("wiz_configure_btn", "Konfigurasi")} →
          </span>
        </button>
      </div>

      {errorMsg && (
        <div className="wiz-banner wiz-banner-error" role="alert">
          {errorMsg}
        </div>
      )}

      <div className="wiz-actions">
        <button
          type="button"
          className="wiz-btn wiz-btn-secondary"
          onClick={onBack}
          disabled={completing}
        >
          {t("wiz_back", "Kembali")}
        </button>
        <button
          type="button"
          className="wiz-btn wiz-btn-primary"
          data-testid="wizard-complete-btn"
          onClick={handleComplete}
          disabled={completing}
        >
          {completing ? "..." : t("wiz_open_myserver", "Buka MyServer")}
        </button>
      </div>
    </div>
  )
}

export default StepFinishHub

import { useEffect, useRef, useState, type FormEvent } from "react"
import { AlertCircle, CheckCircle2, Eye, EyeOff, LoaderCircle, Lock } from "lucide-react"
import { getCompanionApi } from "../api"
import { getTranslation } from "../i18n"
import type { WizardStepProps } from "./StepConnection"

export function StepZimaLogin({
  draft,
  onPatchDraft,
  onNext,
  onBack,
  language,
  onNotify,
  onErrorChange,
}: WizardStepProps) {
  const t = getTranslation(language)
  const [password, setPassword] = useState(() => draft.password || "")
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [authError, setAuthError] = useState("")
  const [authSuccess, setAuthSuccess] = useState("")

  const onErrorChangeRef = useRef(onErrorChange)
  onErrorChangeRef.current = onErrorChange

  useEffect(() => {
    onErrorChangeRef.current?.(Boolean(authError))
  }, [authError])

  const trimmedUser = draft.username.trim()
  const canSubmit = Boolean(!submitting && trimmedUser && password)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return

    const api = getCompanionApi()
    setSubmitting(true)
    setAuthError("")
    setAuthSuccess("")

    const lanUrl = draft.lanUrl.trim()
    const wanUrl = draft.wanUrl.trim()
    const remoteId = draft.remoteId.trim()
    const effectiveUrl =
      lanUrl ||
      wanUrl ||
      (draft.connectionMode === "remote"
        ? draft.zerotierIp.trim()
          ? `http://${draft.zerotierIp.trim()}`
          : "http://10.126.126.1"
        : "")

    try {
      const verifyRes = await api.verifyZimaLogin({
        url: effectiveUrl || undefined,
        remoteId: remoteId || undefined,
        wanUrl: wanUrl || undefined,
        username: trimmedUser,
        password,
      })

      if (!verifyRes?.success) {
        setAuthError(verifyRes?.error || verifyRes?.message || t("wiz_auth_err"))
        return
      }

      const resolvedName = draft.serverName.trim() || t("wiz_server_name_default")
      const resolvedLocalUrl = verifyRes.resolvedUrl || lanUrl || effectiveUrl

      const commitRes = await api.commitWizardServer({
        serverId: draft.serverId || undefined,
        name: resolvedName,
        url: resolvedLocalUrl || undefined,
        localUrl: lanUrl || verifyRes.resolvedUrl || undefined,
        remoteId: remoteId || undefined,
        wanUrl: wanUrl || undefined,
        username: trimmedUser,
        password,
        sshUser: trimmedUser,
        setActive: true,
      })

      if (!commitRes?.success) {
        setAuthError(commitRes?.error || commitRes?.message || t("wiz_auth_err"))
        return
      }

      const ztNet =
        verifyRes.zerotierNetworkId ||
        commitRes.zerotierNetworkId ||
        draft.zerotierNetworkId ||
        ""
      const ztIp =
        verifyRes.zerotierIp ||
        commitRes.zerotierVirtualIp ||
        draft.zerotierIp ||
        ""

      setPassword("")
      onPatchDraft({
        serverId: commitRes.serverId || draft.serverId,
        serverName: commitRes.name || resolvedName,
        username: trimmedUser,
        password: "",
        zerotierNetworkId: ztNet,
        zerotierIp: ztIp,
        step1And3Done: true,
      })

      const okMsg = ztNet || ztIp ? `${t("wiz_auth_ok")} ${t("wiz_zt_discovered")}` : t("wiz_auth_ok")
      setAuthSuccess(okMsg)
      onNotify?.(t("wiz_auth_ok"), "success")
      onNext()
    } catch (err) {
      const message = err instanceof Error ? err.message : t("wiz_auth_err")
      setAuthError(message || t("wiz_auth_err"))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="wiz-card" onSubmit={e => void handleSubmit(e)} noValidate>
      <div className="wiz-card-header">
        <div>
          <h2 className="wiz-step-title">{t("wiz_step3_title")}</h2>
          <p className="wiz-step-sub">{t("wiz_step3_sub")}</p>
        </div>
        <span className="wiz-req-badge">{t("wiz_required_badge")}</span>
      </div>

      <div className="grid-2">
        <div className="wiz-field">
          <label htmlFor="wiz-server-name">{t("wiz_server_name_label")}</label>
          <input
            id="wiz-server-name"
            type="text"
            className="wiz-input"
            placeholder={t("wiz_server_name_default")}
            value={draft.serverName}
            disabled={submitting}
            onChange={e => {
              setAuthError("")
              onPatchDraft({ serverName: e.target.value })
            }}
          />
        </div>

        <div className="wiz-field">
          <label htmlFor="wiz-username">{t("wiz_username_label")}</label>
          <input
            id="wiz-username"
            type="text"
            autoComplete="username"
            className="wiz-input"
            value={draft.username}
            disabled={submitting}
            onChange={e => {
              setAuthError("")
              onPatchDraft({ username: e.target.value })
            }}
          />
        </div>
      </div>

      <div className="wiz-field">
        <label htmlFor="wiz-password">{t("wiz_password_label")}</label>
        <div className="wiz-input-wrap">
          <input
            id="wiz-password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            className="wiz-input"
            value={password}
            disabled={submitting}
            onChange={e => {
              setAuthError("")
              setPassword(e.target.value)
            }}
          />
          <button
            type="button"
            className="wiz-eye-btn"
            aria-label={showPassword ? t("wiz_hide_password") : t("wiz_show_password")}
            aria-pressed={showPassword}
            onClick={() => setShowPassword(prev => !prev)}
            disabled={submitting}
          >
            {showPassword ? (
              <EyeOff size={16} aria-hidden="true" />
            ) : (
              <Eye size={16} aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      <div className="wiz-trust-note">
        <Lock size={14} aria-hidden="true" />
        <span>{t("wiz_dpapi_note")}</span>
      </div>

      {authError && (
        <div className="status-line is-err" role="alert">
          <AlertCircle size={14} aria-hidden="true" />
          <span>{authError}</span>
        </div>
      )}

      {!authError && authSuccess && (
        <div className="status-line is-ok" role="status">
          <CheckCircle2 size={14} aria-hidden="true" />
          <span>{authSuccess}</span>
        </div>
      )}

      <div className="wiz-footer">
        <button
          type="button"
          className="wiz-btn wiz-btn-secondary"
          onClick={onBack}
          disabled={submitting}
        >
          {t("wiz_back")}
        </button>
        <button
          type="submit"
          className="wiz-btn wiz-btn-primary"
          disabled={!canSubmit}
        >
          {submitting ? (
            <>
              <LoaderCircle size={14} className="wiz-spin" aria-hidden="true" />
              <span>{t("wiz_verifying_login")}</span>
            </>
          ) : (
            <span>{t("wiz_login_btn")}</span>
          )}
        </button>
      </div>
    </form>
  )
}

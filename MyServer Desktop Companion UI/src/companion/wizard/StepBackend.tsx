import { useEffect, useRef, useState } from "react"
import {
  AlertCircle,
  CheckCircle2,
  Eye,
  EyeOff,
  LoaderCircle,
  Package,
  RefreshCw,
  Server,
} from "lucide-react"
import { getCompanionApi } from "../api"
import { getTranslation } from "../i18n"
import type { BackendDeploySource, WizardDraft } from "../types"
import { cx } from "../ui"
import type { WizardStepProps } from "./StepConnection"

type BackendInstallState = "checking" | "installed" | "update_available" | "not_installed"

const DEPLOY_STAGE_KEYS = [
  "wiz_backend_stage_connect",
  "wiz_backend_stage_upload",
  "wiz_backend_stage_start",
  "wiz_backend_stage_verify",
] as const

export function compareSemver(a: string, b: string): number {
  const pa = a.replace(/^v/i, "").split(".").map(n => parseInt(n, 10) || 0)
  const pb = b.replace(/^v/i, "").split(".").map(n => parseInt(n, 10) || 0)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const na = pa[i] || 0
    const nb = pb[i] || 0
    if (na > nb) return 1
    if (na < nb) return -1
  }
  return 0
}

function deriveDefaultHost(draft: WizardDraft): string {
  const candidates = [draft.lanUrl.trim(), draft.wanUrl.trim()]
  for (const raw of candidates) {
    if (!raw) continue
    try {
      const u = new URL(raw.includes("://") ? raw : `http://${raw}`)
      if (u.hostname) return u.hostname
    } catch {
      // Fall back to next candidate
    }
  }
  if (draft.zerotierIp.trim()) return draft.zerotierIp.trim()
  return "192.168.1.50"
}

export function StepBackend({
  draft,
  onPatchDraft,
  onNext,
  onBack,
  language,
  onNotify,
  onErrorChange,
}: WizardStepProps) {
  const t = getTranslation(language)
  const defaultHost = deriveDefaultHost(draft)

  const [installState, setInstallState] = useState<BackendInstallState>("checking")
  const [detectedVersion, setDetectedVersion] = useState(() => draft.backendVersion || "")
  const [latestVersion, setLatestVersion] = useState("")

  const [showSshEdit, setShowSshEdit] = useState(false)
  const [sshHost, setSshHost] = useState(defaultHost)
  const [sshPort, setSshPort] = useState("22")
  const [sshUser, setSshUser] = useState(() => draft.username.trim() || "admin")
  const [sshPassword, setSshPassword] = useState("")
  const [showSshPassword, setShowSshPassword] = useState(false)

  const [deploying, setDeploying] = useState(false)
  const [stageIndex, setStageIndex] = useState(0)
  const [deployOkMsg, setDeployOkMsg] = useState("")
  const [deployError, setDeployError] = useState("")

  const deployingRef = useRef(false)
  const onPatchRef = useRef(onPatchDraft)
  onPatchRef.current = onPatchDraft
  const onErrorChangeRef = useRef(onErrorChange)
  onErrorChangeRef.current = onErrorChange

  useEffect(() => {
    let active = true
    const api = getCompanionApi()

    if (!api.getBackendStatus) {
      setInstallState("not_installed")
      return
    }

    setInstallState("checking")
    api
      .getBackendStatus(draft.serverId || undefined)
      .then(status => {
        if (!active) return
        if (status?.online) {
          const currentVer = status.version || ""
          const latestVer = status.latestVersion || ""
          setDetectedVersion(currentVer)
          setLatestVersion(latestVer)
          if (currentVer && latestVer && compareSemver(currentVer, latestVer) < 0) {
            setInstallState("update_available")
          } else {
            setInstallState("installed")
          }
          onPatchRef.current({
            backendInstalled: true,
            backendVersion: currentVer,
          })
        } else {
          setInstallState("not_installed")
        }
      })
      .catch(() => {
        if (!active) return
        setInstallState("not_installed")
      })

    return () => {
      active = false
    }
  }, [draft.serverId])

  useEffect(() => {
    if (!deploying) {
      setStageIndex(0)
      return
    }
    const timer = window.setInterval(() => {
      setStageIndex(prev => (prev < DEPLOY_STAGE_KEYS.length - 1 ? prev + 1 : prev))
    }, 1200)
    return () => window.clearInterval(timer)
  }, [deploying])

  const parsedPort = Number(sshPort.trim())
  const sshValidationError = showSshEdit
    ? !sshHost.trim() || !sshUser.trim()
      ? t("wiz_backend_auth_err")
      : !Number.isInteger(parsedPort) || parsedPort < 1 || parsedPort > 65535
        ? `${t("wiz_ssh_port_label")}: 1 - 65535`
        : ""
    : ""

  const hasError = Boolean(sshValidationError || deployError)
  useEffect(() => {
    onErrorChangeRef.current?.(hasError)
  }, [hasError])

  const handleToggleSshEdit = () => {
    if (deploying) return
    setDeployError("")
    setShowSshEdit(prev => {
      const next = !prev
      if (!next) {
        setSshPassword("")
        setShowSshPassword(false)
      }
      return next
    })
  }

  const handleSourceChange = (source: BackendDeploySource) => {
    if (deploying || source === draft.backendSource) return
    setDeployError("")
    onPatchDraft({ backendSource: source })
  }

  const handleDeploy = async (action: "install" | "update") => {
    if (deploying || deployingRef.current || sshValidationError) return
    const api = getCompanionApi()
    if (!api.triggerBackendAction) return

    deployingRef.current = true
    setDeploying(true)
    setStageIndex(0)
    setDeployError("")
    setDeployOkMsg("")

    const options: {
      source: BackendDeploySource
      sshHost?: string
      sshPort?: number
      sshUser?: string
      sshPassword?: string
    } = {
      source: draft.backendSource,
    }

    if (showSshEdit) {
      options.sshHost = sshHost.trim()
      options.sshPort = parsedPort
      options.sshUser = sshUser.trim()
      options.sshPassword = sshPassword
    }

    try {
      const res = await api.triggerBackendAction(
        action,
        draft.serverId || undefined,
        options
      )

      if (res?.success) {
        const nextVer = res.version || detectedVersion || draft.backendVersion
        setDetectedVersion(nextVer)
        if (res.latestVersion) setLatestVersion(res.latestVersion)
        setInstallState(res.updateAvailable ? "update_available" : "installed")
        onPatchDraft({
          backendInstalled: true,
          backendVersion: nextVer,
        })
        const okText = nextVer ? `${t("wiz_backend_ok")} (v${nextVer})` : t("wiz_backend_ok")
        setDeployOkMsg(okText)
        onNotify?.(t("wiz_backend_ok"), "success")
      } else if (res?.authFailed) {
        setShowSshEdit(true)
        setDeployError(t("wiz_backend_auth_err"))
      } else if (res?.busy) {
        setDeployError(t("wiz_backend_busy_err"))
      } else {
        const safeMsg =
          res?.message &&
          !res.message.includes("\n") &&
          !/chmod|systemctl|sudo|tar\s|stdout|stderr/i.test(res.message) &&
          res.message.length < 180
            ? res.message
            : t("wiz_conn_err")
        setDeployError(safeMsg)
      }
    } catch {
      setDeployError(t("wiz_conn_err"))
    } finally {
      setSshPassword("")
      setShowSshPassword(false)
      deployingRef.current = false
      setDeploying(false)
    }
  }

  const displayServer = `${draft.serverName || t("wiz_server_name_default")} (${defaultHost})`
  const displaySsh = `${sshUser.trim() || "admin"}@${sshHost.trim() || defaultHost}:${sshPort.trim() || "22"}`

  const statusText = (() => {
    if (installState === "checking") return t("wiz_testing_conn")
    if (installState === "update_available") {
      return detectedVersion && latestVersion
        ? `${t("wiz_backend_update_avail")} (v${detectedVersion} -> v${latestVersion})`
        : t("wiz_backend_update_avail")
    }
    if (installState === "installed") {
      return detectedVersion
        ? `${t("wiz_backend_installed")} (v${detectedVersion})`
        : t("wiz_backend_installed")
    }
    return t("wiz_backend_not_installed")
  })()

  return (
    <div className="wiz-card">
      <div className="wiz-card-header">
        <div>
          <h2 className="wiz-step-title">{t("wiz_step4_title")}</h2>
          <p className="wiz-step-sub">{t("wiz_step4_sub")}</p>
        </div>
        <span className="wiz-opt-badge">{t("wiz_optional_badge")}</span>
      </div>

      <div className="kv-list">
        <div className="kv-row">
          <span className="kv-key">{t("wiz_kv_server")}</span>
          <span className="kv-val">{displayServer}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">{t("wiz_kv_ssh")}</span>
          <span className="kv-val-wrap">
            <span className="kv-val wiz-mono">{displaySsh}</span>
            <button
              type="button"
              className="link-quiet"
              onClick={handleToggleSshEdit}
              disabled={deploying}
            >
              {showSshEdit ? t("wiz_cancel_edit") : t("wiz_edit_ssh")}
            </button>
          </span>
        </div>
        <div className="kv-row" role="status">
          <span className="kv-key">{t("wiz_kv_status")}</span>
          <span className="kv-val">{statusText}</span>
        </div>
      </div>

      {showSshEdit && (
        <div className="wiz-ssh-edit">
          <div className="wiz-ssh-grid">
            <div className="wiz-field">
              <label htmlFor="wiz-ssh-host">{t("wiz_ssh_host_label")}</label>
              <input
                id="wiz-ssh-host"
                type="text"
                className="wiz-input"
                value={sshHost}
                disabled={deploying}
                onChange={e => {
                  setDeployError("")
                  setSshHost(e.target.value)
                }}
              />
            </div>
            <div className="wiz-field">
              <label htmlFor="wiz-ssh-port">{t("wiz_ssh_port_label")}</label>
              <input
                id="wiz-ssh-port"
                type="number"
                min={1}
                max={65535}
                className="wiz-input"
                value={sshPort}
                disabled={deploying}
                onChange={e => {
                  setDeployError("")
                  setSshPort(e.target.value)
                }}
              />
            </div>
          </div>

          <div className="wiz-ssh-grid">
            <div className="wiz-field">
              <label htmlFor="wiz-ssh-user">{t("wiz_ssh_user_label")}</label>
              <input
                id="wiz-ssh-user"
                type="text"
                className="wiz-input"
                value={sshUser}
                disabled={deploying}
                onChange={e => {
                  setDeployError("")
                  setSshUser(e.target.value)
                }}
              />
            </div>
            <div className="wiz-field">
              <label htmlFor="wiz-ssh-pass">{t("wiz_ssh_pass_label")}</label>
              <div className="wiz-input-wrap">
                <input
                  id="wiz-ssh-pass"
                  type={showSshPassword ? "text" : "password"}
                  autoComplete="new-password"
                  className="wiz-input"
                  value={sshPassword}
                  disabled={deploying}
                  onChange={e => {
                    setDeployError("")
                    setSshPassword(e.target.value)
                  }}
                />
                <button
                  type="button"
                  className="wiz-eye-btn"
                  aria-label={
                    showSshPassword ? t("wiz_hide_password") : t("wiz_show_password")
                  }
                  aria-pressed={showSshPassword}
                  onClick={() => setShowSshPassword(prev => !prev)}
                  disabled={deploying}
                >
                  {showSshPassword ? (
                    <EyeOff size={16} aria-hidden="true" />
                  ) : (
                    <Eye size={16} aria-hidden="true" />
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="wiz-field">
        <span className="wiz-field-label">{t("wiz_source_label")}</span>
        <div className="wiz-seg" role="group" aria-label={t("wiz_source_label")}>
          <button
            type="button"
            className={cx(
              "wiz-seg-btn",
              draft.backendSource === "github" && "is-active"
            )}
            aria-pressed={draft.backendSource === "github"}
            disabled={deploying}
            onClick={() => handleSourceChange("github")}
          >
            <Server size={14} aria-hidden="true" />
            <span>{t("wiz_source_github")}</span>
          </button>
          <button
            type="button"
            className={cx(
              "wiz-seg-btn",
              draft.backendSource === "bundle" && "is-active"
            )}
            aria-pressed={draft.backendSource === "bundle"}
            disabled={deploying}
            onClick={() => handleSourceChange("bundle")}
          >
            <Package size={14} aria-hidden="true" />
            <span>{t("wiz_source_bundle")}</span>
          </button>
        </div>
      </div>

      {deploying && (
        <div className="wiz-stages" aria-live="polite">
          {DEPLOY_STAGE_KEYS.map((stageKey, idx) => (
            <div
              key={stageKey}
              className={cx(
                "wiz-stage-item",
                idx === stageIndex && "is-active",
                idx < stageIndex && "is-done"
              )}
            >
              {idx === stageIndex ? (
                <LoaderCircle size={13} className="wiz-spin" aria-hidden="true" />
              ) : (
                <CheckCircle2 size={13} aria-hidden="true" />
              )}
              <span>{t(stageKey)}</span>
            </div>
          ))}
        </div>
      )}

      {(sshValidationError || deployError) && (
        <div className="status-line is-err" role="alert">
          <AlertCircle size={14} aria-hidden="true" />
          <span>{sshValidationError || deployError}</span>
        </div>
      )}

      {!sshValidationError && !deployError && deployOkMsg && (
        <div className="status-line is-ok" role="status">
          <CheckCircle2 size={14} aria-hidden="true" />
          <span>{deployOkMsg}</span>
        </div>
      )}

      <div className="wiz-footer">
        <div className="wiz-footer-left">
          <button
            type="button"
            className="wiz-btn wiz-btn-secondary"
            onClick={onBack}
            disabled={deploying}
          >
            {t("wiz_back")}
          </button>
          <button
            type="button"
            className="wiz-btn wiz-btn-ghost"
            onClick={onNext}
            disabled={deploying}
          >
            {t("wiz_skip")}
          </button>
        </div>

        <div className="wiz-footer-right">
          {installState === "installed" ? (
            <>
              <button
                type="button"
                className="wiz-btn wiz-btn-secondary"
                disabled={deploying || Boolean(sshValidationError)}
                onClick={() => void handleDeploy("install")}
              >
                <RefreshCw size={14} aria-hidden="true" />
                <span>{t("wiz_reinstall_backend")}</span>
              </button>
              <button
                type="button"
                className="wiz-btn wiz-btn-primary"
                disabled={deploying}
                onClick={onNext}
              >
                {t("wiz_next")}
              </button>
            </>
          ) : (
            <button
              type="button"
              className="wiz-btn wiz-btn-primary"
              disabled={
                deploying ||
                installState === "checking" ||
                Boolean(sshValidationError)
              }
              onClick={() =>
                void handleDeploy(
                  installState === "update_available" ? "update" : "install"
                )
              }
            >
              {deploying ? (
                <>
                  <LoaderCircle size={14} className="wiz-spin" aria-hidden="true" />
                  <span>{t("wiz_deploying")}</span>
                </>
              ) : (
                <span>
                  {installState === "update_available"
                    ? t("wiz_update_backend")
                    : t("wiz_install_backend")}
                </span>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

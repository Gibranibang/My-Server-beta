import React, { useEffect, useRef, useState } from "react"
import { Eye, EyeOff } from "lucide-react"
import { getCompanionApi } from "../api"
import { getTranslation, type Language } from "../i18n"
import type { VirtualMachine, WizardDraft } from "../types"

export interface SubStepVmProps {
  draft: WizardDraft
  onPatchDraft: (patch: Partial<WizardDraft>) => void
  onDoneSubStep: () => void
  onSkip?: () => void
  onBack: () => void
  language: Language
  onNotify?: (msg: string, type?: "info" | "success" | "error" | "warning") => void
  onErrorChange?: (hasError: boolean) => void
}

function parseLanHost(lanUrl: string): string {
  const trimmed = lanUrl.trim()
  if (!trimmed) return ""
  try {
    const normalized = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`
    return new URL(normalized).hostname || ""
  } catch {
    return ""
  }
}

function sanitizeVmError(err: unknown, fallback: string, secrets: string[] = []): string {
  const raw = err instanceof Error ? err.message : String(err ?? "")
  const firstLine = raw.split(/\r?\n/)[0]?.trim() ?? ""
  if (!firstLine) return fallback
  if (/(?:[A-Za-z]:\\|\/(?:home|Users|etc|var|opt|root|tmp|Library|AppData|usr)\/|config\.xml)/i.test(firstLine)) {
    return fallback
  }
  for (const s of secrets) {
    if (s && s.length >= 6 && firstLine.includes(s)) {
      return fallback
    }
  }
  return firstLine.length > 180 ? `${firstLine.slice(0, 177)}...` : firstLine
}

export const SubStepVm: React.FC<SubStepVmProps> = ({
  draft,
  onPatchDraft,
  onDoneSubStep,
  onSkip,
  onBack,
  language,
  onNotify,
  onErrorChange,
}) => {
  const t = getTranslation(language)
  const api = getCompanionApi()
  const defaultManualHost = parseLanHost(draft.lanUrl)

  const [provider, setProvider] = useState<'instabox' | 'manual'>('instabox')
  const [scope, setScope] = useState<'server' | 'local'>('server')
  const [name, setName] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [showApiKey, setShowApiKey] = useState(false)
  const [sshHost, setSshHost] = useState("")
  const [sshPort, setSshPort] = useState("22")
  const [sshUser, setSshUser] = useState("")
  const [tokenExpiry, setTokenExpiry] = useState("")
  const [webPort, setWebPort] = useState("")
  const [screenUrl, setScreenUrl] = useState("")
  const [screenOpenTarget, setScreenOpenTarget] = useState<'ask' | 'window' | 'browser'>('ask')

  const [saving, setSaving] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Stable deterministic VM ID per form instance ensures retries/double-submits remain idempotent
  const vmIdRef = useRef<string>(`vm-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`)
  const savingRef = useRef(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const handleSelectProvider = (nextProvider: 'instabox' | 'manual') => {
    if (saving || nextProvider === provider) return
    setProvider(nextProvider)
    setErrorMsg(null)
    onErrorChange?.(false)
  }

  const handleSave = async () => {
    if (savingRef.current) return
    setErrorMsg(null)
    onErrorChange?.(false)

    const cleanName = name.trim()
    const cleanApiKey = apiKey.trim()
    let cleanHost = sshHost.trim()
    let cleanUser = sshUser.trim()

    if (provider === 'manual') {
      if (!cleanName) {
        const msg = t("wiz_vm_err_name", "Nama VM wajib diisi untuk Manual SSH.")
        setErrorMsg(msg)
        onErrorChange?.(true)
        onNotify?.(msg, "error")
        return
      }
      if (cleanHost.includes("@")) {
        const atIdx = cleanHost.indexOf("@")
        if (!cleanUser) {
          cleanUser = cleanHost.slice(0, atIdx).trim()
        }
        cleanHost = cleanHost.slice(atIdx + 1).trim()
      }
      if (cleanUser.includes("@")) {
        const parts = cleanUser.split("@")
        cleanUser = parts[0].trim()
        if (!cleanHost && parts[1]) {
          cleanHost = parts.slice(1).join("@").trim()
        }
      }
      if (!cleanHost) {
        const msg = t("wiz_vm_err_host", "Host Gateway / IP wajib diisi untuk Manual SSH.")
        setErrorMsg(msg)
        onErrorChange?.(true)
        onNotify?.(msg, "error")
        return
      }
    } else {
      if (cleanUser.includes("@")) {
        cleanUser = cleanUser.split("@")[0].trim()
      }
      if (!cleanApiKey && !screenUrl.trim()) {
        const msg = t("wiz_vm_err_key", "Masukkan InstaBox API Key (ibk_...) terlebih dahulu.")
        setErrorMsg(msg)
        onErrorChange?.(true)
        onNotify?.(msg, "error")
        return
      }
    }

    savingRef.current = true
    setSaving(true)

    try {
      const parsedSshPort = Number.parseInt(sshPort.trim(), 10)
      const validSshPort =
        Number.isFinite(parsedSshPort) && parsedSshPort > 0 && parsedSshPort <= 65535
          ? parsedSshPort
          : 22

      const parsedWebPort = Number.parseInt(webPort.trim(), 10)
      const validWebPort =
        provider === 'manual' &&
        Number.isFinite(parsedWebPort) &&
        parsedWebPort > 0 &&
        parsedWebPort <= 65535
          ? parsedWebPort
          : undefined

      const finalName = cleanName || "InstaBox-MicroVM"
      const vmId = vmIdRef.current
      const targetServerId = scope === 'server' ? draft.serverId || undefined : undefined

      const newVm: VirtualMachine = {
        id: vmId,
        name: finalName,
        provider,
        status: "sleeping",
        scope,
        serverId: targetServerId,
        serverName: scope === 'server' ? draft.serverName || undefined : undefined,
        sshHost: provider === 'instabox' ? "ssh.instabox.sh" : cleanHost,
        sshUser: cleanUser || undefined,
        sshPort: provider === 'instabox' ? 2222 : validSshPort,
        tokenExpiry: provider === 'manual' ? tokenExpiry.trim() || undefined : undefined,
        webPort: validWebPort,
        screenUrl: screenUrl.trim() || undefined,
        screenOpenTarget,
        apiKey: provider === 'instabox' && cleanApiKey ? cleanApiKey : undefined,
        maxRuntimeMinutes: provider === 'instabox' ? 480 : undefined,
        idleTimeoutMinutes: provider === 'instabox' ? 30 : undefined,
      }

      const existingRaw = api.loadVms ? await api.loadVms() : []
      if (!Array.isArray(existingRaw)) {
        throw new Error(t("wiz_conn_err", "Gagal memuat daftar Virtual Machine"))
      }
      const existing = existingRaw
      const existingIdx = existing.findIndex((item) => item.id === vmId)
      const nextList =
        existingIdx >= 0
          ? existing.map((item, idx) => (idx === existingIdx ? { ...item, ...newVm } : item))
          : [...existing, newVm]

      const saveRes = await api.saveVms?.(nextList)
      if (saveRes && (saveRes.status === "error" || saveRes.success === false)) {
        throw new Error(
          saveRes.message || saveRes.error || t("wiz_conn_err", "Gagal menyimpan Virtual Machine")
        )
      }

      if (provider === 'instabox' && cleanApiKey) {
        const syncRes = await api.syncInstaBoxVm({
          apiKey: cleanApiKey,
          vmName: finalName,
          vmId,
          scope,
          serverId: targetServerId,
        })
        if (syncRes && syncRes.success && api.updateVm) {
          const stateStr = String(syncRes.state || "").toLowerCase()
          const isRunning =
            stateStr === "running" ||
            stateStr === "active" ||
            stateStr === "starting" ||
            stateStr === "resuming"
          const syncPatch: Partial<VirtualMachine> = {
            status: isRunning ? "running" : "sleeping",
          }
          let hasMetadata = isRunning
          if (syncRes.machineId) {
            syncPatch.machineId = syncRes.machineId
            hasMetadata = true
          }
          if (syncRes.screenUrl && !screenUrl.trim()) {
            syncPatch.screenUrl = syncRes.screenUrl
            hasMetadata = true
          }
          if (syncRes.sshHost) {
            syncPatch.sshHost = syncRes.sshHost
            hasMetadata = true
          }
          const resolvedUser = cleanUser || syncRes.sshUser || syncRes.machineId
          if (resolvedUser && resolvedUser !== newVm.sshUser) {
            syncPatch.sshUser = resolvedUser
            hasMetadata = true
          }
          if (syncRes.sshPort) {
            syncPatch.sshPort = syncRes.sshPort
            hasMetadata = true
          }
          if (typeof syncRes.runtimeMinutes === "number") {
            syncPatch.runtimeMinutes = syncRes.runtimeMinutes
            hasMetadata = true
          }
          if (syncRes.maxRuntimeMinutes != null) {
            syncPatch.maxRuntimeMinutes = syncRes.maxRuntimeMinutes
          }
          if (syncRes.idleTimeoutMinutes != null) {
            syncPatch.idleTimeoutMinutes = syncRes.idleTimeoutMinutes
          }
          if (hasMetadata) {
            await api.updateVm(vmId, syncPatch, targetServerId).catch((err) => {
              console.warn("[SubStepVm] updateVm metadata sync failed:", err)
            })
          }
        }
      }

      onErrorChange?.(false)
      onPatchDraft({ vmDone: true })
      onDoneSubStep()
    } catch (err) {
      const msg = sanitizeVmError(
        err,
        t("wiz_conn_err", "Gagal menyimpan Virtual Machine"),
        [apiKey]
      )
      if (mountedRef.current) {
        setErrorMsg(msg)
      }
      onErrorChange?.(true)
      onNotify?.(msg, "error")
    } finally {
      savingRef.current = false
      if (mountedRef.current) {
        setSaving(false)
      }
    }
  }

  return (
    <div className="wiz-step wiz-substep-vm" data-testid="wizard-substep-5b">
      <div className="wiz-step-header">
        <h2 className="wiz-step-title">
          {t("wiz_5b_title", "Layar Virtual / VM")}
        </h2>
        <p className="wiz-step-sub">
          {t(
            "wiz_5b_sub",
            "Hubungkan akun InstaBox atau masukkan URL VM web secara manual."
          )}
        </p>
      </div>

      <div className="wiz-sub-card">
        <div className="wiz-chip-group" role="tablist" aria-label="Provider Virtual Machine">
          <button
            type="button"
            role="tab"
            aria-selected={provider === 'instabox'}
            data-testid="vm-provider-instabox"
            className={`wiz-chip-toggle${provider === 'instabox' ? " is-active" : ""}`}
            onClick={() => handleSelectProvider('instabox')}
            disabled={saving}
          >
            {t("wiz_5b_provider_instabox", "InstaBox Cloud")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={provider === 'manual'}
            data-testid="vm-provider-manual"
            className={`wiz-chip-toggle${provider === 'manual' ? " is-active" : ""}`}
            onClick={() => handleSelectProvider('manual')}
            disabled={saving}
          >
            {t("wiz_5b_provider_manual", "Manual SSH")}
          </button>
        </div>

        <div className="wiz-chip-group" role="radiogroup" aria-label="Scope Virtual Machine">
          <button
            type="button"
            role="radio"
            aria-checked={scope === 'server'}
            data-testid="vm-scope-server"
            className={`wiz-chip-toggle${scope === 'server' ? " is-active" : ""}`}
            onClick={() => setScope('server')}
            disabled={saving}
          >
            {t("wiz_5b_scope_server", "Di Server")}
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={scope === 'local'}
            data-testid="vm-scope-local"
            className={`wiz-chip-toggle${scope === 'local' ? " is-active" : ""}`}
            onClick={() => setScope('local')}
            disabled={saving}
          >
            {t("wiz_5b_scope_local", "Di Laptop")}
          </button>
        </div>

        <div className="wiz-form-grid">
          {provider === 'instabox' ? (
            <>
              <div className="grid-2">
                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-api-key">
                    {t("wiz_5b_instabox_key", "API Key InstaBox (ibk_...)")}
                  </label>
                  <div className="wiz-input-wrap">
                    <input
                      id="vm-api-key"
                      className="wiz-input is-mono"
                      type={showApiKey ? "text" : "password"}
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder="e.g. ibk_examplekey..."
                      disabled={saving}
                    />
                    <button
                      type="button"
                      className="wiz-eye-btn"
                      aria-pressed={showApiKey}
                      onClick={() => setShowApiKey((v) => !v)}
                      aria-label={
                        showApiKey
                          ? t("wiz_hide_password", "Sembunyikan")
                          : t("wiz_show_password", "Tampilkan")
                      }
                    >
                      {showApiKey ? (
                        <EyeOff size={15} aria-hidden="true" />
                      ) : (
                        <Eye size={15} aria-hidden="true" />
                      )}
                    </button>
                  </div>
                </div>

                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-name">
                    {t("wiz_5b_name_optional", "Nama VM (Opsional)")}
                  </label>
                  <input
                    id="vm-name"
                    className="wiz-input"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Linux-Dev-Server"
                    disabled={saving}
                  />
                </div>
              </div>

              <div className="grid-2">
                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-ssh-user">
                    {t("wiz_5b_temp_ssh_token", "Token SSH Sementara (Opsional)")}
                  </label>
                  <input
                    id="vm-ssh-user"
                    className="wiz-input is-mono"
                    type="text"
                    value={sshUser}
                    onChange={(e) => setSshUser(e.target.value)}
                    placeholder="e.g. ibssh_exampletoken..."
                    disabled={saving}
                  />
                </div>

                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-screen-url">
                    {t("wiz_5b_url", "URL Layar Virtual (Opsional)")}
                  </label>
                  <input
                    id="vm-screen-url"
                    className="wiz-input is-mono"
                    type="text"
                    value={screenUrl}
                    onChange={(e) => setScreenUrl(e.target.value)}
                    placeholder="https://instabox.sh/app/..."
                    disabled={saving}
                  />
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="grid-2">
                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-name">
                    {t("wiz_5b_name", "Nama VM")}
                  </label>
                  <input
                    id="vm-name"
                    className="wiz-input"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Ubuntu Server"
                    disabled={saving}
                  />
                </div>

                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-ssh-host">
                    {t("wiz_5b_ssh_host", "Host Gateway / IP")}
                  </label>
                  <input
                    id="vm-ssh-host"
                    className="wiz-input is-mono"
                    type="text"
                    value={sshHost}
                    onChange={(e) => setSshHost(e.target.value)}
                    placeholder={defaultManualHost || "zimaos.local"}
                    disabled={saving}
                  />
                </div>
              </div>

              <div className="grid-vm-ssh">
                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-ssh-port">
                    {t("wiz_5b_ssh_port", "Port SSH")}
                  </label>
                  <input
                    id="vm-ssh-port"
                    className="wiz-input is-mono"
                    type="text"
                    value={sshPort}
                    onChange={(e) => setSshPort(e.target.value)}
                    placeholder="22"
                    disabled={saving}
                  />
                </div>

                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-token-expiry">
                    {t("wiz_5b_token_expiry", "Masa Berlaku (Opsional)")}
                  </label>
                  <input
                    id="vm-token-expiry"
                    className="wiz-input"
                    type="text"
                    value={tokenExpiry}
                    onChange={(e) => setTokenExpiry(e.target.value)}
                    placeholder={language === "id" ? "e.g. 24 jam" : "e.g. 24 hours"}
                    disabled={saving}
                  />
                </div>

                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-ssh-user">
                    {t("wiz_5b_ssh_user", "User SSH (Opsional)")}
                  </label>
                  <input
                    id="vm-ssh-user"
                    className="wiz-input is-mono"
                    type="text"
                    value={sshUser}
                    onChange={(e) => setSshUser(e.target.value)}
                    placeholder="e.g. root / ubuntu"
                    disabled={saving}
                  />
                </div>
              </div>

              <div className="grid-2">
                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-web-port">
                    {t("wiz_5b_web_port", "Port Web Layanan (Opsional)")}
                  </label>
                  <input
                    id="vm-web-port"
                    className="wiz-input is-mono"
                    type="text"
                    value={webPort}
                    onChange={(e) => setWebPort(e.target.value)}
                    placeholder="6080"
                    disabled={saving}
                  />
                </div>

                <div className="wiz-field">
                  <label className="wiz-label" htmlFor="vm-screen-url">
                    {t("wiz_5b_url", "URL Layar Virtual (Opsional)")}
                  </label>
                  <input
                    id="vm-screen-url"
                    className="wiz-input is-mono"
                    type="text"
                    value={screenUrl}
                    onChange={(e) => setScreenUrl(e.target.value)}
                    placeholder="https://vnc.local:6080"
                    disabled={saving}
                  />
                </div>
              </div>
            </>
          )}

          <div className="wiz-field">
            <label className="wiz-label" htmlFor="vm-screen-target">
              {t("vm_screen_target_label", "Mode Buka Layar Virtual")}
            </label>
            <select
              id="vm-screen-target"
              className="wiz-select"
              value={screenOpenTarget}
              onChange={(e) =>
                setScreenOpenTarget(e.target.value as 'ask' | 'window' | 'browser')
              }
              disabled={saving}
            >
              <option value="ask">
                {t("vm_screen_target_ask", "Tanyakan Setiap Membuka")}
              </option>
              <option value="window">
                {t("vm_screen_target_window", "Jendela MyServer (Sesi Terisolasi)")}
              </option>
              <option value="browser">
                {t("vm_screen_target_browser", "Browser Bawaan")}
              </option>
            </select>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="wiz-banner wiz-banner-error" role="alert">
          {errorMsg}
        </div>
      )}

      <div className="wiz-actions">
        <div className="wiz-footer-left">
          <button
            type="button"
            className="wiz-btn wiz-btn-secondary"
            onClick={onBack}
            disabled={saving}
          >
            {t("wiz_back", "Kembali")}
          </button>
          <button
            type="button"
            className="wiz-btn wiz-btn-ghost"
            onClick={onSkip ?? onBack}
            disabled={saving}
          >
            {t("wiz_skip", "Lewati")}
          </button>
        </div>
        <button
          type="button"
          className="wiz-btn wiz-btn-primary"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? "..." : t("wiz_5b_save", "Simpan VM")}
        </button>
      </div>
    </div>
  )
}

export default SubStepVm

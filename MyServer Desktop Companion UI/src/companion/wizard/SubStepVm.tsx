import React, { useEffect, useRef, useState } from "react"
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
  if (!trimmed) return "127.0.0.1"
  try {
    const normalized = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`
    return new URL(normalized).hostname || "127.0.0.1"
  } catch {
    return "127.0.0.1"
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
  const [sshHost, setSshHost] = useState("ssh.instabox.sh")
  const [sshPort, setSshPort] = useState("2222")
  const [sshUser, setSshUser] = useState("root")
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
    if (nextProvider === 'manual') {
      if (!sshHost.trim() || sshHost.trim() === "ssh.instabox.sh") {
        setSshHost(defaultManualHost)
      }
      if (!sshPort.trim() || sshPort.trim() === "2222") {
        setSshPort("22")
      }
    } else {
      if (!sshHost.trim() || sshHost.trim() === defaultManualHost || sshHost.trim() === "127.0.0.1") {
        setSshHost("ssh.instabox.sh")
      }
      if (!sshPort.trim() || sshPort.trim() === "22") {
        setSshPort("2222")
      }
    }
  }

  const handleSave = async () => {
    if (savingRef.current) return
    savingRef.current = true
    setSaving(true)
    setErrorMsg(null)
    onErrorChange?.(false)

    try {
      const parsedSshPort = Number.parseInt(sshPort.trim(), 10)
      const validSshPort =
        Number.isFinite(parsedSshPort) && parsedSshPort > 0 && parsedSshPort <= 65535
          ? parsedSshPort
          : provider === 'instabox'
            ? 2222
            : 22

      const parsedWebPort = Number.parseInt(webPort.trim(), 10)
      const validWebPort =
        Number.isFinite(parsedWebPort) && parsedWebPort > 0 && parsedWebPort <= 65535
          ? parsedWebPort
          : undefined

      const finalName =
        name.trim() || (provider === 'instabox' ? "InstaBox-MicroVM" : "Linux-VPS")
      const vmId = vmIdRef.current

      const newVm: VirtualMachine = {
        id: vmId,
        name: finalName,
        provider,
        status: "stopped",
        scope,
        serverId: scope === 'server' ? draft.serverId || undefined : undefined,
        serverName: scope === 'server' ? draft.serverName || undefined : undefined,
        sshHost: sshHost.trim() || undefined,
        sshUser: sshUser.trim() || undefined,
        sshPort: validSshPort,
        webPort: validWebPort,
        screenUrl: screenUrl.trim() || undefined,
        screenOpenTarget,
        apiKey: provider === 'instabox' && apiKey.trim() ? apiKey.trim() : undefined,
      }

      const existing = (await api.loadVms?.()) ?? []
      const existingIdx = existing.findIndex((item) => item.id === vmId)
      const nextList =
        existingIdx >= 0
          ? existing.map((item, idx) => (idx === existingIdx ? { ...item, ...newVm } : item))
          : [...existing, newVm]

      await api.saveVms?.(nextList)

      if (provider === 'instabox' && apiKey.trim()) {
        await api.syncInstaBoxVm({
          apiKey: apiKey.trim(),
          vmName: finalName,
          vmId,
          scope,
          serverId: scope === 'server' ? draft.serverId || undefined : undefined,
        })
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
            {t("wiz_5b_provider_instabox", "InstaBox")}
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
            {t("wiz_5b_provider_manual", "URL Manual")}
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
              placeholder={provider === 'instabox' ? "InstaBox-MicroVM" : "Linux-VPS"}
              disabled={saving}
            />
          </div>

          {provider === 'instabox' && (
            <div className="wiz-field">
              <label className="wiz-label" htmlFor="vm-api-key">
                {t("wiz_5b_instabox_key", "API Key InstaBox")}
              </label>
              <div className="wiz-input-row">
                <input
                  id="vm-api-key"
                  className="wiz-input"
                  type={showApiKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="ibx_..."
                  disabled={saving}
                />
                <button
                  type="button"
                  className="wiz-chip-toggle"
                  onClick={() => setShowApiKey((v) => !v)}
                  aria-label={
                    showApiKey
                      ? t("wiz_hide_password", "Sembunyikan")
                      : t("wiz_show_password", "Tampilkan")
                  }
                >
                  {showApiKey
                    ? t("wiz_hide_password", "Sembunyikan")
                    : t("wiz_show_password", "Tampilkan")}
                </button>
              </div>
            </div>
          )}

          <div className="wiz-field-pair">
            <div className="wiz-field">
              <label className="wiz-label" htmlFor="vm-ssh-host">
                SSH Host
              </label>
              <input
                id="vm-ssh-host"
                className="wiz-input"
                type="text"
                value={sshHost}
                onChange={(e) => setSshHost(e.target.value)}
                placeholder={provider === 'instabox' ? "ssh.instabox.sh" : defaultManualHost}
                disabled={saving}
              />
            </div>
            <div className="wiz-field wiz-field-port">
              <label className="wiz-label" htmlFor="vm-ssh-port">
                SSH Port
              </label>
              <input
                id="vm-ssh-port"
                className="wiz-input"
                type="text"
                value={sshPort}
                onChange={(e) => setSshPort(e.target.value)}
                placeholder={provider === 'instabox' ? "2222" : "22"}
                disabled={saving}
              />
            </div>
          </div>

          <div className="wiz-field-pair">
            <div className="wiz-field">
              <label className="wiz-label" htmlFor="vm-ssh-user">
                Username SSH
              </label>
              <input
                id="vm-ssh-user"
                className="wiz-input"
                type="text"
                value={sshUser}
                onChange={(e) => setSshUser(e.target.value)}
                placeholder="root"
                disabled={saving}
              />
            </div>
            <div className="wiz-field wiz-field-port">
              <label className="wiz-label" htmlFor="vm-web-port">
                Web Port
              </label>
              <input
                id="vm-web-port"
                className="wiz-input"
                type="text"
                value={webPort}
                onChange={(e) => setWebPort(e.target.value)}
                placeholder="6080"
                disabled={saving}
              />
            </div>
          </div>

          <div className="wiz-field">
            <label className="wiz-label" htmlFor="vm-screen-url">
              {t("wiz_5b_url", "URL VM Web")}
            </label>
            <input
              id="vm-screen-url"
              className="wiz-input"
              type="text"
              value={screenUrl}
              onChange={(e) => setScreenUrl(e.target.value)}
              placeholder="https://..."
              disabled={saving}
            />
          </div>

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

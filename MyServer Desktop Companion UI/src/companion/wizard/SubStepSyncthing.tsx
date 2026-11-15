import React, { useEffect, useRef, useState } from "react"
import { Eye, EyeOff } from "lucide-react"
import { getCompanionApi } from "../api"
import { getTranslation, type Language } from "../i18n"
import type { WizardDraft } from "../types"

export interface SubStepSyncthingProps {
  draft: WizardDraft
  onPatchDraft: (patch: Partial<WizardDraft>) => void
  onDoneSubStep: () => void
  onSkip?: () => void
  onBack: () => void
  language: Language
  onNotify?: (msg: string, type?: "info" | "success" | "error" | "warning") => void
  onErrorChange?: (hasError: boolean) => void
}

function parseHostAndPort(
  rawUrl: string | undefined,
  defaultPort: string,
  defaultHttps = false
): { host: string; port: string; https: boolean } {
  const trimmed = (rawUrl ?? "").trim()
  if (!trimmed) {
    return { host: "", port: defaultPort, https: defaultHttps }
  }
  try {
    const hasScheme = /^https?:\/\//i.test(trimmed)
    const normalized = hasScheme ? trimmed : `http://${trimmed}`
    const parsed = new URL(normalized)
    const isHttps = hasScheme ? parsed.protocol === "https:" : defaultHttps
    return {
      host: parsed.hostname || "",
      port: parsed.port || defaultPort,
      https: isHttps,
    }
  } catch {
    return { host: trimmed, port: defaultPort, https: defaultHttps }
  }
}

function sanitizeUserMessage(errOrMsg: unknown, fallback: string, secrets: string[] = []): string {
  const raw = errOrMsg instanceof Error ? errOrMsg.message : String(errOrMsg ?? "")
  const firstLine = raw.split(/\r?\n/)[0]?.trim() ?? ""
  if (!firstLine) return fallback
  // Never surface local filesystem paths (e.g. config.xml or binary_path) or API secrets in DOM (T-03-08)
  if (/(?:[A-Za-z]:\\|\/(?:home|Users|etc|var|opt|root|tmp|Library|AppData|usr)\/|config\.xml|binary_path)/i.test(firstLine)) {
    return fallback
  }
  for (const s of secrets) {
    if (s && s.length >= 6 && firstLine.includes(s)) {
      return fallback
    }
  }
  return firstLine.length > 180 ? `${firstLine.slice(0, 177)}...` : firstLine
}

function formatTargetUrl(hostRaw: string, portRaw: string, useHttps: boolean, fallbackPort: string): string {
  const trimmedHost = hostRaw.trim().replace(/\/+$/, "")
  if (!trimmedHost) return ""
  if (/^https?:\/\//i.test(trimmedHost)) {
    return trimmedHost
  }
  const cleanPort = portRaw.trim() || fallbackPort
  const scheme = useHttps ? "https" : "http"
  if (trimmedHost.includes(":") && !trimmedHost.startsWith("[")) {
    return `${scheme}://${trimmedHost}`
  }
  return cleanPort ? `${scheme}://${trimmedHost}:${cleanPort}` : `${scheme}://${trimmedHost}`
}

export const SubStepSyncthing: React.FC<SubStepSyncthingProps> = ({
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

  const initialLan = parseHostAndPort(draft.lanUrl, "8384", false)
  const initialWanHttps = draft.wanUrl ? !/^http:\/\//i.test(draft.wanUrl.trim()) : true
  const initialWan = parseHostAndPort(draft.wanUrl, initialWanHttps ? "443" : "8384", initialWanHttps)

  const [localPort, setLocalPort] = useState("8384")
  const [localApiKey, setLocalApiKey] = useState("")
  const [serverApiKey, setServerApiKey] = useState("")
  const [showLocalKey, setShowLocalKey] = useState(false)
  const [showServerKey, setShowServerKey] = useState(false)

  const [lanIp, setLanIp] = useState(initialLan.host)
  const [lanPort, setLanPort] = useState(initialLan.port || "8384")
  const [lanHttps, setLanHttps] = useState(false)

  const [remoteIp, setRemoteIp] = useState(draft.zerotierIp || "")
  const [remotePort, setRemotePort] = useState("8384")
  const [remoteHttps, setRemoteHttps] = useState(false)

  const [wanHost, setWanHost] = useState(initialWan.host)
  const [wanPort, setWanPort] = useState(initialWan.port || (initialWanHttps ? "443" : "8384"))
  const [wanHttps, setWanHttps] = useState(initialWanHttps)

  const [autoSwitch, setAutoSwitch] = useState(true)
  const [manualRoute, setManualRoute] = useState<"lan" | "wan">("lan")
  const [autoStart, setAutoStart] = useState(false)
  const [autoPair, setAutoPair] = useState(true)

  const [loadingConfig, setLoadingConfig] = useState(true)
  const [detecting, setDetecting] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)

  const [detectStatus, setDetectStatus] = useState<{ tone: "info" | "success"; text: string } | null>(null)
  const [probeStatus, setProbeStatus] = useState<{ tone: "success" | "error"; text: string } | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const mountedRef = useRef(true)
  const savingRef = useRef(false)

  useEffect(() => {
    mountedRef.current = true
    let cancelled = false

    const hydrate = async () => {
      try {
        const cfg = await api.getSyncthingConfig()
        if (cancelled || !mountedRef.current || !cfg) return

        if (cfg.local) {
          if (cfg.local.port) setLocalPort(cfg.local.port)
          if (cfg.local.api_key) setLocalApiKey(cfg.local.api_key)
          if (typeof cfg.local.auto_start === "boolean") {
            setAutoStart(cfg.local.auto_start)
          }
        }

        if (cfg.server) {
          if (cfg.server.api_key) setServerApiKey(cfg.server.api_key)

          const parsedDraftLan = parseHostAndPort(draft.lanUrl, "8384", false)
          const cfgLanIp = cfg.server.lan_ip || parsedDraftLan.host
          if (cfgLanIp) setLanIp(cfgLanIp)
          setLanPort(cfg.server.lan_port || cfg.server.port || "8384")
          setLanHttps(Boolean(cfg.server.lan_https))

          const cfgRemoteIp = cfg.server.remote_ip || draft.zerotierIp || ""
          setRemoteIp(cfgRemoteIp)
          setRemotePort(cfg.server.remote_port || "8384")
          setRemoteHttps(Boolean(cfg.server.remote_https ?? false))

          const parsedDraftWan = parseHostAndPort(draft.wanUrl, "443", true)
          const effectiveWanHttps =
            cfg.server.wan_https ??
            (draft.wanUrl ? !/^http:\/\//i.test(draft.wanUrl.trim()) : true)
          setWanHttps(Boolean(effectiveWanHttps))
          setWanHost(cfg.server.wan_url || parsedDraftWan.host)
          setWanPort(cfg.server.wan_port || (effectiveWanHttps ? "443" : "8384"))

          const routeMode = cfg.server.route_mode ?? "auto"
          setAutoSwitch(routeMode === "auto")
          setManualRoute(routeMode === "wan" ? "wan" : "lan")
        }
      } catch {
        // Pre-fill stays usable with Step 1-3 draft defaults even if backend config is unavailable
      } finally {
        if (!cancelled && mountedRef.current) {
          setLoadingConfig(false)
        }
      }
    }

    void hydrate()

    return () => {
      cancelled = true
      mountedRef.current = false
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleAutoDetect = async () => {
    if (detecting || saving) return
    setDetecting(true)
    setErrorMsg(null)
    setDetectStatus(null)
    onErrorChange?.(false)

    try {
      const res = await api.detectLocalSyncthing()
      if (!mountedRef.current) return
      if (res.detected) {
        if (res.localPort) setLocalPort(res.localPort)
        if (res.localApiKey) setLocalApiKey(res.localApiKey)
        if (res.serverApiKey) setServerApiKey(res.serverApiKey)
        const okText = t("wiz_5a_detect_ok", "Syncthing terdeteksi di laptop ini")
        setDetectStatus({
          tone: "success",
          text: res.localPort ? `${okText} (Port ${res.localPort})` : okText,
        })
      } else {
        setDetectStatus({
          tone: "info",
          text: sanitizeUserMessage(
            res.message,
            t("wiz_5a_detect_none", "Syncthing lokal belum terdeteksi — Anda dapat mengisi manual."),
            [localApiKey, serverApiKey]
          ),
        })
      }
    } catch (err) {
      if (!mountedRef.current) return
      const msg = sanitizeUserMessage(
        err,
        t("wiz_5a_detect_none", "Syncthing lokal belum terdeteksi — Anda dapat mengisi manual."),
        [localApiKey, serverApiKey]
      )
      setDetectStatus({ tone: "info", text: msg })
    } finally {
      if (mountedRef.current) setDetecting(false)
    }
  }

  const handleTestConnection = async () => {
    if (testing || saving) return
    setProbeStatus(null)
    setErrorMsg(null)
    onErrorChange?.(false)

    let targetHost = ""
    let targetPort = "8384"
    let targetHttps = false

    if (!autoSwitch && manualRoute === "wan") {
      targetHost = wanHost
      targetPort = wanPort || (wanHttps ? "443" : "8384")
      targetHttps = wanHttps
    } else if (!autoSwitch && manualRoute === "lan") {
      targetHost = lanIp
      targetPort = lanPort || "8384"
      targetHttps = lanHttps
    } else if (lanIp.trim()) {
      targetHost = lanIp
      targetPort = lanPort || "8384"
      targetHttps = lanHttps
    } else if (remoteIp.trim()) {
      targetHost = remoteIp
      targetPort = remotePort || "8384"
      targetHttps = remoteHttps
    } else if (wanHost.trim()) {
      targetHost = wanHost
      targetPort = wanPort || (wanHttps ? "443" : "8384")
      targetHttps = wanHttps
    }

    const url = formatTargetUrl(targetHost, targetPort, targetHttps, targetHttps ? "443" : "8384")
    if (!url) {
      const msg = "Isi minimal satu host Syncthing server terlebih dahulu."
      setProbeStatus({ tone: "error", text: msg })
      onErrorChange?.(true)
      return
    }

    setTesting(true)
    try {
      const res = await api.testSyncthingTarget(url, targetHttps)
      if (!mountedRef.current) return
      if (res.success && res.online) {
        onErrorChange?.(false)
        setProbeStatus({
          tone: "success",
          text: `Terhubung ke Syncthing (${res.latency_ms} ms)`,
        })
      } else {
        const msg = sanitizeUserMessage(
          res.message,
          t("wiz_conn_err", "Tidak dapat menjangkau Syncthing server"),
          [localApiKey, serverApiKey]
        )
        setProbeStatus({ tone: "error", text: msg })
        onErrorChange?.(true)
      }
    } catch (err) {
      if (!mountedRef.current) return
      const msg = sanitizeUserMessage(
        err,
        t("wiz_conn_err", "Tidak dapat menjangkau Syncthing server"),
        [localApiKey, serverApiKey]
      )
      setProbeStatus({ tone: "error", text: msg })
      onErrorChange?.(true)
    } finally {
      if (mountedRef.current) setTesting(false)
    }
  }

  const handleSaveAndActivate = async () => {
    if (savingRef.current) return
    savingRef.current = true
    setSaving(true)
    setErrorMsg(null)
    onErrorChange?.(false)

    try {
      const localSave = await api.saveSyncthingLocalConfig({
        port: localPort.trim() || "8384",
        api_key: localApiKey.trim(),
        auto_start: autoStart,
      })
      if (localSave && localSave.success === false) {
        throw new Error("Gagal menyimpan konfigurasi Syncthing lokal.")
      }

      const routeSave = await api.saveSyncthingServerRoute({
        route_mode: autoSwitch ? "auto" : manualRoute,
        lan_mode: "manual",
        lan_ip: lanIp.trim(),
        lan_port: lanPort.trim() || "8384",
        lan_https: lanHttps,
        remote_ip: remoteIp.trim(),
        remote_port: remotePort.trim() || "8384",
        remote_https: remoteHttps,
        wan_url: wanHost.trim(),
        wan_port: wanPort.trim() || (wanHttps ? "443" : "8384"),
        wan_https: wanHttps,
        api_key: serverApiKey.trim(),
      })
      if (routeSave && routeSave.success === false) {
        throw new Error("Gagal menyimpan konfigurasi rute Syncthing server.")
      }

      if (autoStart) {
        const daemonRes = await api.toggleLocalSyncthingDaemon("start")
        if (daemonRes && daemonRes.success === false) {
          onNotify?.("Syncthing tersimpan, namun daemon lokal belum berjalan otomatis.", "warning")
        }
      }

      if (autoPair) {
        const pairRes = await api.pairLaptopAndServer()
        if (pairRes && pairRes.success === false) {
          onNotify?.(
            sanitizeUserMessage(
              pairRes.error,
              "Pairing otomatis belum selesai — Anda dapat mengulanginya di Backup.",
              [localApiKey, serverApiKey]
            ),
            "warning"
          )
        }
      }

      onErrorChange?.(false)
      onPatchDraft({ syncthingDone: true })
      onDoneSubStep()
    } catch (err) {
      const msg = sanitizeUserMessage(
        err,
        t("wiz_conn_err", "Gagal menyimpan konfigurasi Syncthing"),
        [localApiKey, serverApiKey]
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
    <div className="wiz-step wiz-substep-syncthing" data-testid="wizard-substep-5a">
      <div className="wiz-step-header">
        <div className="wiz-sub-card-head">
          <h2 className="wiz-step-title">
            {t("wiz_5a_title", "Konfigurasi Syncthing")}
          </h2>
          <button
            type="button"
            className="wiz-btn wiz-btn-secondary wiz-btn-sm"
            onClick={handleAutoDetect}
            disabled={detecting || saving || loadingConfig}
          >
            {detecting ? "..." : t("wiz_5a_autodetect", "Cek Otomatis")}
          </button>
        </div>
        <p className="wiz-step-sub">
          {t(
            "wiz_5a_sub",
            "Hubungkan Syncthing laptop Anda dengan server untuk sinkronisasi file otomatis."
          )}
        </p>
      </div>

      {detectStatus && (
        <div
          className={`wiz-banner wiz-banner-${detectStatus.tone}`}
          role="status"
        >
          {detectStatus.text}
        </div>
      )}

      <div className="wiz-sub-card">
        <div className="grid-syncthing-keys">
          <div className="wiz-field">
            <label className="wiz-label" htmlFor="st-local-port">
              {t("wiz_5a_local_port", "Port Lokal")}
            </label>
            <input
              id="st-local-port"
              className="wiz-input is-mono"
              type="text"
              value={localPort}
              onChange={(e) => setLocalPort(e.target.value)}
              placeholder="8384"
              disabled={saving}
            />
          </div>

          <div className="wiz-field">
            <label className="wiz-label" htmlFor="st-local-key">
              {t("wiz_5a_local_key", "API Key Lokal")}
            </label>
            <div className="wiz-input-wrap">
              <input
                id="st-local-key"
                className="wiz-input is-mono"
                type={showLocalKey ? "text" : "password"}
                value={localApiKey}
                onChange={(e) => setLocalApiKey(e.target.value)}
                placeholder="API Key Syncthing Laptop"
                disabled={saving}
              />
              <button
                type="button"
                className="wiz-eye-btn"
                aria-pressed={showLocalKey}
                onClick={() => setShowLocalKey((v) => !v)}
                aria-label={
                  showLocalKey
                    ? t("wiz_hide_password", "Sembunyikan")
                    : t("wiz_show_password", "Tampilkan")
                }
              >
                {showLocalKey ? (
                  <EyeOff size={15} aria-hidden="true" />
                ) : (
                  <Eye size={15} aria-hidden="true" />
                )}
              </button>
            </div>
          </div>

          <div className="wiz-field">
            <label className="wiz-label" htmlFor="st-server-key">
              {t("wiz_5a_server_key", "API Key Server")}
            </label>
            <div className="wiz-input-wrap">
              <input
                id="st-server-key"
                className="wiz-input is-mono"
                type={showServerKey ? "text" : "password"}
                value={serverApiKey}
                onChange={(e) => setServerApiKey(e.target.value)}
                placeholder="API Key Syncthing Server"
                disabled={saving}
              />
              <button
                type="button"
                className="wiz-eye-btn"
                aria-pressed={showServerKey}
                onClick={() => setShowServerKey((v) => !v)}
                aria-label={
                  showServerKey
                    ? t("wiz_hide_password", "Sembunyikan")
                    : t("wiz_show_password", "Tampilkan")
                }
              >
                {showServerKey ? (
                  <EyeOff size={15} aria-hidden="true" />
                ) : (
                  <Eye size={15} aria-hidden="true" />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="wiz-sub-card">
        <div className="wiz-switch-row">
          <span className="wiz-switch-label" id="label-auto-switch-route">
            {t("wiz_5a_route_auto", "Auto-Switch Rute")}
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={autoSwitch}
            aria-labelledby="label-auto-switch-route"
            className={`wiz-switch${autoSwitch ? " is-on" : ""}`}
            onClick={() => setAutoSwitch((v) => !v)}
            disabled={saving}
          />
        </div>

        {!autoSwitch && (
          <div className="wiz-chip-group" role="radiogroup" aria-label="Rute Manual Syncthing">
            <button
              type="button"
              role="radio"
              aria-checked={manualRoute === "lan"}
              className={`wiz-chip-toggle${manualRoute === "lan" ? " is-active" : ""}`}
              onClick={() => setManualRoute("lan")}
              disabled={saving}
            >
              {t("wiz_5a_route_lan", "Selalu Gunakan LAN")}
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={manualRoute === "wan"}
              className={`wiz-chip-toggle${manualRoute === "wan" ? " is-active" : ""}`}
              onClick={() => setManualRoute("wan")}
              disabled={saving}
            >
              {t("wiz_5a_route_wan", "Selalu Gunakan Domain / WAN")}
            </button>
          </div>
        )}

        <div className="wiz-route-fields">
          <div className="wiz-field-pair">
            <div className="wiz-field">
              <label className="wiz-label" htmlFor="st-lan-ip">
                {t("wiz_5a_lan_host", "LAN Host / IP")}
              </label>
              <input
                id="st-lan-ip"
                className="wiz-input"
                type="text"
                value={lanIp}
                onChange={(e) => setLanIp(e.target.value)}
                placeholder="zimaos.local"
                disabled={saving}
              />
            </div>
            <div className="wiz-field wiz-field-port">
              <label className="wiz-label" htmlFor="st-lan-port">
                Port LAN
              </label>
              <input
                id="st-lan-port"
                className="wiz-input"
                type="text"
                value={lanPort}
                onChange={(e) => setLanPort(e.target.value)}
                placeholder="8384"
                disabled={saving}
              />
            </div>
            <button
              type="button"
              className={`wiz-chip-toggle${lanHttps ? " is-active" : ""}`}
              aria-pressed={lanHttps}
              onClick={() => setLanHttps((v) => !v)}
              disabled={saving}
            >
              LAN HTTPS
            </button>
          </div>

          <div className="wiz-field-pair">
            <div className="wiz-field">
              <label className="wiz-label" htmlFor="st-remote-ip">
                {t("wiz_5a_remote_host", "Remote / ZeroTier IP")}
              </label>
              <input
                id="st-remote-ip"
                className="wiz-input"
                type="text"
                value={remoteIp}
                onChange={(e) => setRemoteIp(e.target.value)}
                placeholder="192.0.2.20"
                disabled={saving}
              />
            </div>
            <div className="wiz-field wiz-field-port">
              <label className="wiz-label" htmlFor="st-remote-port">
                Port Remote
              </label>
              <input
                id="st-remote-port"
                className="wiz-input"
                type="text"
                value={remotePort}
                onChange={(e) => setRemotePort(e.target.value)}
                placeholder="8384"
                disabled={saving}
              />
            </div>
            <button
              type="button"
              className={`wiz-chip-toggle${remoteHttps ? " is-active" : ""}`}
              aria-pressed={remoteHttps}
              onClick={() => setRemoteHttps((v) => !v)}
              disabled={saving}
            >
              Remote HTTPS
            </button>
          </div>

          <div className="wiz-field-pair">
            <div className="wiz-field">
              <label className="wiz-label" htmlFor="st-wan-host">
                {t("wiz_5a_wan_host", "Domain / WAN")}
              </label>
              <input
                id="st-wan-host"
                className="wiz-input"
                type="text"
                value={wanHost}
                onChange={(e) => setWanHost(e.target.value)}
                placeholder="sync.example.com"
                disabled={saving}
              />
            </div>
            <div className="wiz-field wiz-field-port">
              <label className="wiz-label" htmlFor="st-wan-port">
                Port WAN
              </label>
              <input
                id="st-wan-port"
                className="wiz-input"
                type="text"
                value={wanPort}
                onChange={(e) => setWanPort(e.target.value)}
                placeholder="443"
                disabled={saving}
              />
            </div>
            <button
              type="button"
              className={`wiz-chip-toggle${wanHttps ? " is-active" : ""}`}
              aria-pressed={wanHttps}
              onClick={() => setWanHttps((v) => !v)}
              disabled={saving}
            >
              WAN HTTPS
            </button>
          </div>
        </div>
      </div>

      <div className="wiz-sub-card wiz-switch-pair">
        <div className="wiz-switch-row">
          <span className="wiz-switch-label" id="label-st-autostart">
            {t("wiz_5a_autostart", "Auto-Start Startup")}
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={autoStart}
            aria-labelledby="label-st-autostart"
            className={`wiz-switch${autoStart ? " is-on" : ""}`}
            onClick={() => setAutoStart((v) => !v)}
            disabled={saving}
          />
        </div>

        <div className="wiz-switch-row">
          <span className="wiz-switch-label" id="label-st-autopair">
            {t("wiz_5a_autopair", "Pair Otomatis")}
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={autoPair}
            aria-labelledby="label-st-autopair"
            className={`wiz-switch${autoPair ? " is-on" : ""}`}
            onClick={() => setAutoPair((v) => !v)}
            disabled={saving}
          />
        </div>
      </div>

      {probeStatus && (
        <div
          className={`wiz-probe-bar wiz-probe-${probeStatus.tone}`}
          role="status"
        >
          {probeStatus.text}
        </div>
      )}

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
        <div className="wiz-footer-right">
          <button
            type="button"
            className="wiz-btn wiz-btn-secondary"
            onClick={handleTestConnection}
            disabled={testing || saving}
          >
            {testing ? "..." : t("wiz_5a_test_conn", "Test Koneksi")}
          </button>
          <button
            type="button"
            className="wiz-btn wiz-btn-primary"
            onClick={handleSaveAndActivate}
            disabled={saving}
          >
            {saving ? "..." : t("wiz_5a_save_activate", "Simpan & Aktifkan")}
          </button>
        </div>
      </div>
    </div>
  )
}

export default SubStepSyncthing

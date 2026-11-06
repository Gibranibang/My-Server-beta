import { useId, useState, useEffect } from "react"
import {
  AppWindow,
  Archive,
  Check,
  ClipboardCopy,
  Download,
  ExternalLink,
  FileText,
  Folder,
  FolderOpen,
  HardDrive,
  Languages,
  Lock,
  Network,
  PanelTopOpen,
  RefreshCw,
  Rocket,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from "lucide-react"
import { FooterStatus, TrayChip } from "../FlyoutShell"
import { getCompanionApi } from "../api"
import { errorText, useAsyncAction, useCompanion, useNotice } from "../store"
import {
  AccordionSection,
  Button,
  Card,
  Chip,
  Mono,
  TextAction,
  Toggle,
  cx,
} from "../ui"
import type { Settings, ServerDetails } from "../types"
import { ViewBody } from "./shared"
import { APP_VERSION, APP_CHANNEL } from "../version"
import { getTranslation, type I18N } from "../i18n"

type TranslationKey = keyof (typeof I18N)["en"]

function SettingToggleRow({
  icon: Icon,
  label,
  caption,
  settingKey,
}: {
  icon: LucideIcon
  label: string
  caption?: string
  settingKey: keyof Settings
}) {
  const { settings, setSetting } = useCompanion()
  const { notify } = useNotice()
  const id = useId()
  const on = Boolean(settings[settingKey])

  return (
    <div className="flex items-center gap-2.5 px-3 py-2 transition-colors duration-150 hover:bg-surface-sunken">
      <Icon
        className="size-4 shrink-0 text-ink-subtle"
        strokeWidth={2}
        aria-hidden
      />
      <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer">
        <span className="block text-label font-medium text-ink">
          {label}
        </span>
        {caption && (
          <span className="block text-micro text-ink-subtle">
            {caption}
          </span>
        )}
      </label>
      <Toggle
        id={id}
        label={label}
        checked={on}
        onChange={(next) =>
          void setSetting(settingKey, next).catch((e) =>
            notify(errorText(e), "danger"),
          )
        }
      />
    </div>
  )
}

export default function SettingsView() {
  const api = getCompanionApi()
  const { settings, setSetting, resetSettings } = useCompanion()
  const { notify } = useNotice()
  const [updateState, runUpdate] = useAsyncAction(api.checkForUpdate)
  const [checkingUpdate, setCheckingUpdate] = useState(false)
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(() => {
    if (typeof window !== "undefined" && window.location.search.includes("mock_update=1")) {
      return {
        upToDate: false,
        version: "4.1.0-beta",
        htmlUrl: "https://github.com/Gibranibang/My-Server-beta/releases/latest",
        downloadUrl: "https://github.com/Gibranibang/My-Server-beta/releases/download/v4.1.0-beta/MyServer-v4.1.0-Beta-Setup.exe"
      }
    }
    return null
  })
  const [installingUpdate, setInstallingUpdate] = useState(false)
  const [downloadProgress, setDownloadProgress] = useState("")
  const [zipUpdateState, setZipUpdateState] = useState<"idle" | "busy" | "done">("idle")
  const [cacheBusy, setCacheBusy] = useState(false)
  const [copyLogBusy, setCopyLogBusy] = useState(false)
  const [saveLogBusy, setSaveLogBusy] = useState(false)
  const [changeLogBusy, setChangeLogBusy] = useState(false)
  const [logDirInfo, setLogDirInfo] = useState<{ logDirectory: string; defaultDirectory: string; isCustom: boolean }>({
    logDirectory: "",
    defaultDirectory: "",
    isCustom: false,
  })
  const [details, setDetails] = useState<ServerDetails | null>(null)
  const [easyTierStatus, setEasyTierStatus] = useState<any>(() => {
    if (typeof window !== "undefined" && window.location.search.includes("mock_easytier=1")) {
      return {
        running: true,
        version: "2.6.4-8428a89d",
        network_name: "myserver-mesh",
        virtual_ip: "10.144.144.12",
        peer_id: 12345678,
        peers_count: 2,
        direct_peers: 1,
        relay_peers: 1,
        peers: [
          { id: "1001", hostname: "Ubuntu-Server", ipv4: "10.144.144.1", cost: "Direct", lat_ms: "8ms", rx_bytes: "1.2 MB", tx_bytes: "450 KB", tunnel_proto: "udp", nat_type: "Cone" }
        ],
        routes: [],
        error: null,
      }
    }
    return null
  })
  const [etNetName, setEtNetName] = useState(() => {
    if (typeof window !== "undefined" && window.location.search.includes("mock_easytier=1")) {
      return "myserver-mesh"
    }
    return ""
  })
  const [etSecret, setEtSecret] = useState("")
  const [etBusy, setEtBusy] = useState(false)

  const t = getTranslation(settings?.language)
  const isId = settings?.language === "id"
  const activeVersion = APP_VERSION
  const activeChannel = details?.appChannel || APP_CHANNEL

  useEffect(() => {
    api.getServerDetails().then(setDetails).catch(() => {})
    if (api.getEasyTierStatus) {
      api.getEasyTierStatus().then((st: any) => {
        if (st && st.running) {
          setEasyTierStatus(st)
          if (st.network_name) setEtNetName(st.network_name)
        }
      }).catch(() => {})
    }
  }, [api])

  const handleConnectEasyTier = async () => {
    if (!etNetName.trim() || !etSecret.trim()) {
      notify(isId ? "Network Name dan Secret wajib diisi!" : "Network Name and Secret are required!", "danger")
      return
    }
    setEtBusy(true)
    try {
      if (api.startEasyTier) {
        const res = await api.startEasyTier({
          network_name: etNetName.trim(),
          network_secret: etSecret.trim(),
        })
        if (res?.success) {
          notify(isId ? "EasyTier P2P Mesh terhubung!" : "EasyTier P2P Mesh connected!", "success")
          setEasyTierStatus(res.status)
        } else {
          notify(res?.message || (isId ? "Gagal terhubung" : "Connection failed"), "danger")
        }
      }
    } catch (e: any) {
      notify(e.message || "Error", "danger")
    } finally {
      setEtBusy(false)
    }
  }

  const handleDisconnectEasyTier = async () => {
    setEtBusy(true)
    try {
      if (api.stopEasyTier) {
        const res = await api.stopEasyTier()
        setEasyTierStatus(res?.status || { running: false })
        notify(isId ? "EasyTier diputuskan" : "EasyTier disconnected", "neutral")
      }
    } catch (e: any) {
      notify(e.message || "Error", "danger")
    } finally {
      setEtBusy(false)
    }
  }

  const handleCheckUpdate = async () => {
    setCheckingUpdate(true)
    try {
      const info = await api.checkForUpdate()
      setUpdateInfo(info)
      if (info.upToDate) {
        notify(
          isId
            ? `MyServer v${info.version} sudah menggunakan versi terbaru!`
            : `MyServer v${info.version} is already up to date!`,
          "neutral"
        )
      } else {
        notify(
          isId
            ? `Pembaruan Tersedia: MyServer v${info.version}!`
            : `Update Available: MyServer v${info.version}!`,
          "info"
        )
      }
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setCheckingUpdate(false)
    }
  }

  const handleDownloadAndInstall = async () => {
    if (!updateInfo) return
    setInstallingUpdate(true)
    setDownloadProgress(isId ? "Mengunduh pembaruan..." : "Downloading update...")
    try {
      if (typeof api.downloadAndInstallUpdate === "function") {
        const res = await api.downloadAndInstallUpdate(updateInfo.downloadUrl)
        if (res.success) {
          notify(
            res.message || (isId ? "Installer pembaruan berhasil diluncurkan!" : "Update installer launched!"),
            "success"
          )
        } else {
          notify(res.error || (isId ? "Gagal mengunduh pembaruan" : "Failed to download update"), "danger")
        }
      } else {
        const targetUrl = updateInfo.downloadUrl || updateInfo.htmlUrl || "https://github.com/Gibranibang/My-Server-beta/releases/latest"
        await api.openExternalBrowser(targetUrl)
        notify(isId ? "Membuka link unduhan di peramban web..." : "Opening download link in browser...", "info")
      }
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setInstallingUpdate(false)
      setDownloadProgress("")
    }
  }

  const handleZipUpdate = async () => {
    setZipUpdateState("busy")
    try {
      const res = await api.installUpdateFromZip()
      if (res.cancelled) {
        notify(t("zip_update_cancelled"), "neutral")
        setZipUpdateState("idle")
        return
      }
      if (res.success) {
        setZipUpdateState("done")
        notify(t("zip_update_success"), "success")
      } else {
        setZipUpdateState("idle")
        notify(res.error || t("zip_update_failed"), "danger")
      }
    } catch (err) {
      setZipUpdateState("idle")
      notify(errorText(err), "danger")
    }
  }

  const handleCopyLog = async () => {
    setCopyLogBusy(true)
    try {
      const res = await api.copyLogToClipboard()
      if (res.success) {
        notify(t("copy_log_success"), "success")
      } else {
        notify(t("copy_log_failed"), "danger")
      }
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setCopyLogBusy(false)
    }
  }

  const handleSaveLog = async () => {
    setSaveLogBusy(true)
    try {
      const res = await api.saveLogToFile()
      if (res.cancelled) {
        notify(t("save_log_cancelled"), "neutral")
      } else if (res.success && res.path) {
        notify(`${t("save_log_success")}${res.path}`, "success")
      } else {
        notify(res.error || t("save_log_cancelled"), "danger")
      }
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setSaveLogBusy(false)
    }
  }

  const handleCleanCache = async () => {
    setCacheBusy(true)
    try {
      if (typeof api.cleanBrowserCache === "function") {
        await api.cleanBrowserCache()
      } else {
        await api.clearCache()
      }
      notify(t("clean_cache_success"), "success")
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setCacheBusy(false)
    }
  }

  const handleChangeLogFolder = async () => {
    setChangeLogBusy(true)
    try {
      const res = await api.chooseLogFolder()
      if (res.cancelled) {
        // user cancelled
      } else if (res.success && res.logDirectory) {
        setLogDirInfo({
          logDirectory: res.logDirectory,
          defaultDirectory: res.defaultDirectory || logDirInfo.defaultDirectory,
          isCustom: !!res.isCustom,
        })
        notify(`${t("change_log_folder_success")}${res.logDirectory}`, "success")
      } else if (res.error) {
        notify(res.error, "danger")
      }
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setChangeLogBusy(false)
    }
  }

  const handleResetLogFolder = async () => {
    setChangeLogBusy(true)
    try {
      const res = await api.resetLogDirectory()
      if (res.success && res.logDirectory) {
        setLogDirInfo({
          logDirectory: res.logDirectory,
          defaultDirectory: res.defaultDirectory || res.logDirectory,
          isCustom: false,
        })
        notify(t("reset_log_folder_success"), "success")
      } else if (res.error) {
        notify(res.error, "danger")
      }
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setChangeLogBusy(false)
    }
  }

  const toggleLanguage = () => {
    const nextLang = settings?.language === "id" ? "en" : "id"
    void setSetting("language", nextLang).then(() => {
      notify(
        nextLang === "id"
          ? "Bahasa diubah ke Bahasa Indonesia"
          : "Language changed to English",
        "success",
      )
    })
  }

  const isDpapiActive = details?.dpapiActive ?? settings.dpapiActive ?? true

  return (
    <>
      <ViewBody className="space-y-3 pb-6">
        {/* ========================================================= */}
        {/* HERO HEADER: Official App Icon + Version Details (Poin 6) */}
        {/* ========================================================= */}
        <Card className="flex flex-col items-center justify-center p-4 text-center">
          <div className="relative mb-2.5">
            <img
              src="/favicon.png"
              alt="MyServer"
              className="size-16 rounded-2xl shadow-control transition-transform duration-300 hover:scale-105 select-none"
            />
            <span
              className="absolute -bottom-1 -right-1 flex size-5 items-center justify-center rounded-full border-2 border-surface bg-brand text-brand-ink shadow-xs"
              title="Official Companion"
            >
              <Check className="size-3" strokeWidth={3} />
            </span>
          </div>

          <div className="flex flex-col items-center">
            <h2 className="text-base font-bold tracking-tight text-ink">
              MyServer Desktop
            </h2>
            <div className="mt-0.5 flex items-center gap-1.5 text-caption font-semibold">
              <span className="text-ink">
                v<Mono>{activeVersion}</Mono>
              </span>
              <span className="rounded-full bg-info-soft px-2 py-0.5 text-micro font-bold text-info-ink">
                {activeChannel}
              </span>
            </div>
            <p className="mt-0.5 text-micro text-ink-subtle">
              {activeChannel} Channel · Windows x64 Architecture
            </p>
          </div>

          {/* Theme Quick Selector */}
          <div className="mt-3 flex w-full items-center justify-between rounded-control border border-line bg-surface-sunken px-3 py-1.5">
            <div className="flex items-center gap-1.5 text-micro font-semibold text-ink">
              <Sparkles className="size-3.5 text-brand" />
              <span>{t("theme_label", "Tema Tampilan")}</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => {
                  void setSetting("theme", "dark")
                  notify(isId ? "Tema Gelap diaktifkan" : "Dark theme activated", "success")
                }}
                className={cx(
                  "rounded-full px-2.5 py-0.5 text-nano font-semibold transition cursor-pointer border",
                  settings?.theme !== "light"
                    ? "bg-brand text-brand-ink border-transparent shadow-xs"
                    : "bg-surface text-ink-subtle border-line hover:text-ink",
                )}
              >
                Dark
              </button>
              <button
                type="button"
                onClick={() => {
                  void setSetting("theme", "light")
                  notify(isId ? "Tema Terang diaktifkan" : "Light theme activated", "success")
                }}
                className={cx(
                  "rounded-full px-2.5 py-0.5 text-nano font-semibold transition cursor-pointer border",
                  settings?.theme === "light"
                    ? "bg-brand text-brand-ink border-transparent shadow-xs"
                    : "bg-surface text-ink-subtle border-line hover:text-ink",
                )}
              >
                Light
              </button>
            </div>
          </div>

          {/* Auto Check Update Preference (Native Checkbox) */}
          <div className="mt-1.5 flex w-full items-center justify-between rounded-control border border-line bg-surface-sunken px-3 py-1.5">
            <div className="flex items-center gap-1.5 text-micro font-semibold text-ink">
              <RefreshCw className="size-3.5 text-brand" />
              <span>{t("auto_check_update_label", "Check for Updates Automatically")}</span>
            </div>
            <button
              type="button"
              role="checkbox"
              aria-checked={settings?.autoCheckUpdate ?? true}
              onClick={() => {
                const nextVal = !(settings?.autoCheckUpdate ?? true)
                void setSetting("autoCheckUpdate", nextVal).then(() => {
                  notify(
                    nextVal
                      ? (isId ? "Pemeriksaan pembaruan otomatis diaktifkan" : "Automatic update check enabled")
                      : (isId ? "Pemeriksaan pembaruan otomatis dinonaktifkan" : "Automatic update check disabled"),
                    "neutral",
                  )
                })
              }}
              className={cx(
                "size-4 rounded border flex items-center justify-center transition cursor-pointer select-none",
                (settings?.autoCheckUpdate ?? true)
                  ? "bg-brand text-brand-ink border-transparent shadow-xs"
                  : "bg-surface border-line hover:border-line-strong text-transparent",
              )}
              title={t("auto_check_update_desc", "Automatically check for updates on startup")}
            >
              {(settings?.autoCheckUpdate ?? true) && <Check className="size-3 text-brand-ink" strokeWidth={3} />}
            </button>
          </div>

          {/* Action Update Buttons - Tata Letak Bersih Bebas Tabrakan */}
          <div className="mt-3 flex flex-col gap-2 w-full">
            <Button
              size="sm"
              variant={updateInfo && !updateInfo.upToDate ? "primary" : "secondary"}
              icon={RefreshCw}
              block
              state={checkingUpdate ? "busy" : "idle"}
              busyLabel={t("checking_update")}
              onClick={handleCheckUpdate}
            >
              {updateInfo && !updateInfo.upToDate
                ? (isId ? `Pembaruan Ada (v${updateInfo.version})` : `Update Available (v${updateInfo.version})`)
                : t("check_update")}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              icon={Archive}
              block
              state={zipUpdateState}
              busyLabel={t("installing_zip")}
              onClick={handleZipUpdate}
            >
              {t("install_zip")}
            </Button>
          </div>

          {/* Update Available Card Banner */}
          {updateInfo && !updateInfo.upToDate && (
            <div className="mt-3 w-full rounded-tile border border-brand/30 bg-brand/5 p-3 text-left">
              <div className="flex items-start justify-between gap-2">
                <div className="flex flex-col">
                  <div className="flex items-center gap-1.5">
                    <Sparkles className="size-4 text-brand shrink-0" />
                    <span className="text-micro font-bold text-ink">
                      {isId ? `Pembaruan Tersedia: v${updateInfo.version}` : `Update Available: v${updateInfo.version}`}
                    </span>
                    <span className="rounded-full bg-brand/10 px-1.5 py-0.5 text-[9px] font-bold text-brand">
                      {isId ? "Baru" : "New"}
                    </span>
                  </div>
                  <p className="mt-1 text-nano text-ink-subtle">
                    {isId
                      ? `Versi saat ini v${activeVersion} dapat diperbarui ke v${updateInfo.version}.`
                      : `Current version v${activeVersion} can be updated to v${updateInfo.version}.`}
                  </p>
                </div>
              </div>

              {/* Action Buttons: Clean & Perfectly Contained (Zero Overflow) */}
              <div className="mt-3 flex flex-col gap-2 w-full">
                <Button
                  size="sm"
                  variant="primary"
                  icon={Download}
                  block
                  state={installingUpdate ? "busy" : "idle"}
                  busyLabel={downloadProgress || (isId ? "Mengunduh..." : "Downloading...")}
                  onClick={handleDownloadAndInstall}
                  className="h-8 rounded-control text-micro font-semibold shadow-xs justify-center"
                >
                  {isId ? "Unduh & Pasang Sekarang" : "Download & Install Now"}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={ExternalLink}
                  block
                  onClick={() => {
                    const targetUrl = updateInfo.htmlUrl || updateInfo.downloadUrl || "https://github.com/Gibranibang/My-Server-beta/releases/latest"
                    api.openExternalBrowser(targetUrl)
                  }}
                  className="h-7 rounded-control text-micro font-medium text-ink-subtle hover:text-ink justify-center"
                >
                  {isId ? "Buka di Browser" : "Open in Browser"}
                </Button>
              </div>
            </div>
          )}
        </Card>

        {/* ========================================================= */}
        {/* ACCORDION 1: Sistem & Startup (Poin 5)                    */}
        {/* ========================================================= */}
        <AccordionSection
          title={t("sec_system_title")}
          subtitle={t("sec_system_desc")}
          icon={Rocket}
          defaultOpen={true}
        >
          <div className="divide-y divide-line overflow-hidden rounded-tile border border-line bg-surface">
            <SettingToggleRow
              icon={Rocket}
              label={t("autostart_label")}
              caption={t(settings.autostart ? "autostart_on" : "autostart_off")}
              settingKey="autostart"
            />
            <SettingToggleRow
              icon={AppWindow}
              label={t("openDashboard_label")}
              caption={t(settings.openDashboard ? "openDashboard_on" : "openDashboard_off")}
              settingKey="openDashboard"
            />
            <SettingToggleRow
              icon={PanelTopOpen}
              label={t("autoOpenMiniTray_label")}
              caption={t(settings.autoOpenMiniTray ? "autoOpenMiniTray_on" : "autoOpenMiniTray_off")}
              settingKey="autoOpenMiniTray"
            />
            <SettingToggleRow
              icon={RefreshCw}
              label={t("auto_check_update_label", "Check for Updates Automatically")}
              caption={t((settings.autoCheckUpdate ?? true) ? "auto_check_update_on" : "auto_check_update_off")}
              settingKey="autoCheckUpdate"
            />
          </div>
        </AccordionSection>

        {/* ========================================================= */}
        {/* ACCORDION 2: Bahasa & Keamanan Vault (Poin 5)             */}
        {/* ========================================================= */}
        <AccordionSection
          title={t("sec_lang_vault_title")}
          subtitle={t("sec_lang_vault_desc")}
          icon={Languages}
          badge={
            <Chip
              tone={isDpapiActive ? "success" : "warning"}
              size="sm"
              icon={isDpapiActive ? ShieldCheck : Lock}
            >
              {isDpapiActive ? "DPAPI Vault" : "Vault Plain"}
            </Chip>
          }
        >
          <div className="flex flex-col gap-3">
            {/* Language Selector */}
            <div className="flex flex-col gap-1.5 rounded-tile border border-line bg-surface p-2.5">
              <span className="text-micro font-semibold text-ink">
                {t("language_title")}
              </span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => {
                    void setSetting("language", "en")
                    notify(t("lang_switched_en"), "success")
                  }}
                  className={cx(
                    "flex items-center justify-center gap-1.5 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border",
                    (settings.language || "en") === "en"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <span>{t("lang_en")}</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void setSetting("language", "id")
                    notify(t("lang_switched_id"), "success")
                  }}
                  className={cx(
                    "flex items-center justify-center gap-1.5 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border",
                    settings?.language === "id"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <span>{t("lang_id")}</span>
                </button>
              </div>
            </div>

            {/* Theme Selector (Dark / Light) */}
            <div className="flex items-center justify-between rounded-tile border border-line bg-surface p-2.5">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 text-brand shrink-0" />
                <div className="flex flex-col">
                  <span className="text-micro font-semibold text-ink">
                    {t("theme_label", "Tema Tampilan")}
                  </span>
                  <span className="text-nano text-ink-subtle">
                    {settings?.theme === "light"
                      ? t("theme_light", "Light (Classic Silver)")
                      : t("theme_dark", "Dark (Obsidian Console)")}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    void setSetting("theme", "dark")
                    notify(isId ? "Tema Gelap diaktifkan" : "Dark theme activated", "success")
                  }}
                  className={cx(
                    "flex items-center justify-center gap-1.5 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border",
                    settings?.theme !== "light"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <span>Dark</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void setSetting("theme", "light")
                    notify(isId ? "Tema Terang diaktifkan" : "Light theme activated", "success")
                  }}
                  className={cx(
                    "flex items-center justify-center gap-1.5 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border",
                    settings?.theme === "light"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <span>Light</span>
                </button>
              </div>
            </div>

            {/* DPAPI Security Info */}
            <div className="flex items-center justify-between rounded-tile border border-line bg-surface p-2.5 text-micro">
              <div className="flex items-center gap-2">
                <ShieldCheck
                  className={cx(
                    "size-4 shrink-0",
                    isDpapiActive ? "text-success" : "text-warning",
                  )}
                />
                <div className="flex flex-col">
                  <span className="font-semibold text-ink">
                    Windows DPAPI Enkripsi Kredensial
                  </span>
                  <span className="text-ink-subtle">
                    {isDpapiActive
                      ? "Kunci token dan konfigurasi dilindungi Windows DPAPI hardware vault"
                      : "DPAPI fallback mode standar"}
                  </span>
                </div>
              </div>
              <Chip tone={isDpapiActive ? "success" : "neutral"} size="sm">
                {isDpapiActive ? t("dpapi_active") : t("dpapi_inactive")}
              </Chip>
            </div>
          </div>
        </AccordionSection>

        {/* ========================================================= */}
        {/* ACCORDION 3: Integrasi Storage & Jaringan (Poin 5)        */}
        {/* ========================================================= */}
        <AccordionSection
          title={t("sec_storage_net_title")}
          subtitle={t("sec_storage_net_desc")}
          icon={HardDrive}
        >
          <div className="flex flex-col gap-2.5">
            {/* File Manager Target Selection */}
            <div className="flex flex-col gap-1.5 rounded-tile border border-line bg-surface p-2.5">
              <span className="text-micro font-semibold text-ink">
                {t("fm_click_title")}
              </span>
              <span className="text-micro text-ink-subtle">
                {t("fm_click_subtitle")}
              </span>
              <div className="grid grid-cols-2 gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    void setSetting("fileManagerClickTarget", "explorer")
                    notify(t("fm_target_set_explorer"), "success")
                  }}
                  className={cx(
                    "flex items-center justify-center gap-1.5 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border",
                    (settings.fileManagerClickTarget || "explorer") === "explorer"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <HardDrive className="size-3.5" />
                  <span>{t("fm_target_explorer")}</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void setSetting("fileManagerClickTarget", "zimaos")
                    notify(t("fm_target_set_zimaos"), "success")
                  }}
                  className={cx(
                    "flex items-center justify-center gap-1.5 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border",
                    settings.fileManagerClickTarget === "zimaos"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <Folder className="size-3.5" />
                  <span>{t("fm_target_zimaos")}</span>
                </button>
              </div>
            </div>

            {/* EasyTier P2P Mesh Card */}
            <div className="flex flex-col gap-2 rounded-tile border border-line bg-surface p-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Network className="size-4 text-brand" />
                  <span className="text-micro font-semibold text-ink">
                    {t("easytier_title")}
                  </span>
                </div>
                {easyTierStatus?.running ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                    <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    {(easyTierStatus.direct_peers && easyTierStatus.direct_peers > 0) ? t("easytier_status_connected") : t("easytier_status_relay")}
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded-full border border-line bg-surface-sunken px-2 py-0.5 text-[10px] font-medium text-ink-subtle">
                    {t("easytier_status_disconnected")}
                  </span>
                )}
              </div>

              <span className="text-micro text-ink-subtle leading-relaxed">
                {t("easytier_desc")}
              </span>

              {easyTierStatus?.running ? (
                <div className="flex flex-col gap-1.5 rounded-control bg-surface-sunken border border-line p-2 text-micro">
                  <div className="flex justify-between items-center text-ink">
                    <span className="text-ink-subtle">Network:</span>
                    <span className="font-mono font-medium">{easyTierStatus.network_name || etNetName}</span>
                  </div>
                  {easyTierStatus.virtual_ip && (
                    <div className="flex justify-between items-center text-ink">
                      <span className="text-ink-subtle">Virtual IP:</span>
                      <span className="font-mono font-medium">{easyTierStatus.virtual_ip}</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center text-ink">
                    <span className="text-ink-subtle">Peers:</span>
                    <span className="font-medium">{easyTierStatus.peers_count || 0} node</span>
                  </div>
                  <div className="pt-1">
                    <button
                      type="button"
                      disabled={etBusy}
                      onClick={handleDisconnectEasyTier}
                      className="w-full flex items-center justify-center gap-1.5 rounded-control border border-line bg-surface px-2.5 py-1.5 text-micro font-medium text-ink hover:bg-surface-elevated transition cursor-pointer disabled:opacity-50"
                    >
                      {t("easytier_btn_disconnect")}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-2 pt-0.5">
                  <div className="flex flex-col gap-1">
                    <label className="text-[11px] font-medium text-ink-subtle">
                      {t("easytier_net_name_label")}
                    </label>
                    <input
                      type="text"
                      value={etNetName}
                      onChange={(e) => setEtNetName(e.target.value)}
                      placeholder={t("easytier_net_name_placeholder")}
                      className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-micro text-ink focus:border-brand focus:outline-none"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[11px] font-medium text-ink-subtle">
                      {t("easytier_secret_label")}
                    </label>
                    <input
                      type="password"
                      value={etSecret}
                      onChange={(e) => setEtSecret(e.target.value)}
                      placeholder={t("easytier_secret_placeholder")}
                      className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-micro text-ink focus:border-brand focus:outline-none"
                    />
                  </div>
                  <button
                    type="button"
                    disabled={etBusy}
                    onClick={handleConnectEasyTier}
                    className="flex items-center justify-center gap-1.5 rounded-control bg-brand px-2.5 py-1.5 text-micro font-semibold text-brand-ink transition cursor-pointer hover:opacity-90 disabled:opacity-50"
                  >
                    {etBusy ? <RefreshCw className="size-3.5 animate-spin" /> : <Network className="size-3.5" />}
                    <span>{t("easytier_btn_connect")}</span>
                  </button>
                </div>
              )}
            </div>

            {/* Storage & Network Startup Toggles */}
            <div className="divide-y divide-line overflow-hidden rounded-tile border border-line bg-surface">
              <SettingToggleRow
                icon={HardDrive}
                label={t("autoMountSmb_label")}
                caption={t(settings.autoMountSmb ? "autoMountSmb_on" : "autoMountSmb_off")}
                settingKey="autoMountSmb"
              />
              <SettingToggleRow
                icon={Network}
                label={t("autoZeroTier_label")}
                caption={t(settings.autoZeroTier ? "autoZeroTier_on" : "autoZeroTier_off")}
                settingKey="autoZeroTier"
              />
            </div>
          </div>
        </AccordionSection>

        {/* ========================================================= */}
        {/* ACCORDION 4: Diagnostik, Log & Pemeliharaan (Poin 7)     */}
        {/* ========================================================= */}
        <AccordionSection
          title={t("sec_diag_logs_title")}
          subtitle={t("sec_diag_logs_desc")}
          icon={FileText}
        >
          <div className="flex flex-col gap-2.5">
            {/* Primary Log Action Buttons (Copy & Change Directory) */}
            <div className="grid grid-cols-2 gap-2">
              <Button
                size="sm"
                variant="secondary"
                icon={ClipboardCopy}
                block
                state={copyLogBusy ? "busy" : "idle"}
                busyLabel="Menyalin..."
                onClick={handleCopyLog}
                title={t("copy_log_desc")}
              >
                {t("copy_log_btn")}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                icon={FolderOpen}
                block
                state={changeLogBusy ? "busy" : "idle"}
                busyLabel="Mengubah..."
                onClick={handleChangeLogFolder}
                title={t("change_log_folder_desc")}
              >
                {t("change_log_folder_btn")}
              </Button>
            </div>

            {/* Active Log Directory Badge & Reset Option */}
            <div className="flex flex-col gap-1.5 rounded-tile border border-line bg-surface p-2.5 text-micro">
              <div className="flex items-center justify-between">
                <span className="font-medium text-ink-subtle">{t("log_folder_active")}</span>
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${logDirInfo.isCustom ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300" : "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400"}`}>
                  {logDirInfo.isCustom ? t("log_folder_custom_badge") : t("log_folder_default_badge")}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-nano text-ink select-all" title={logDirInfo.logDirectory}>
                  {logDirInfo.logDirectory || "Default App Folder"}
                </span>
                {logDirInfo.isCustom && (
                  <button
                    type="button"
                    onClick={handleResetLogFolder}
                    disabled={changeLogBusy}
                    className="shrink-0 text-nano text-brand hover:underline font-medium"
                    title={t("reset_log_folder_btn")}
                  >
                    {t("reset_log_folder_btn")}
                  </button>
                )}
              </div>
            </div>

            {/* Log Explorer & Notepad Links */}
            <div className="flex flex-wrap items-center justify-between rounded-tile border border-line bg-surface p-2.5 text-micro">
              <div className="flex items-center gap-3">
                <TextAction
                  icon={FileText}
                  tone="neutral"
                  onClick={() => {
                    api.openLogFile()
                    notify(t("opening_log_notepad"), "info")
                  }}
                >
                  {t("open_log_file")}
                </TextAction>
                <span className="text-line-strong">|</span>
                <TextAction
                  icon={FolderOpen}
                  tone="neutral"
                  onClick={() => {
                    api.openLogFolder()
                    notify(t("opening_log_folder"), "info")
                  }}
                >
                  {t("open_log_folder")}
                </TextAction>
              </div>
            </div>

            {/* Maintenance & Cache Cleanup */}
            <div className="flex items-center justify-between rounded-tile border border-line bg-surface p-2.5">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 shrink-0 text-brand" />
                <div className="flex flex-col">
                  <span className="text-micro font-semibold text-ink">
                    {t("clean_cache_btn")}
                  </span>
                  <span className="text-nano text-ink-subtle">
                    {t("clean_cache_desc")}
                  </span>
                </div>
              </div>
              <Button
                size="sm"
                variant="soft"
                state={cacheBusy ? "busy" : "idle"}
                busyLabel="Membersihkan..."
                onClick={handleCleanCache}
                className="h-7 text-micro px-2.5"
              >
                {t("clean_cache_btn")}
              </Button>
            </div>
          </div>
        </AccordionSection>
      </ViewBody>

      <FooterStatus
        showNoticePill={false}
        title={t("client_status")}
        chips={
          <>
            <TrayChip
              onClick={toggleLanguage}
              title={t("lang_chip")}
            >
              {t("lang_chip")}
            </TrayChip>
            <TrayChip
              tone={isDpapiActive ? "success" : "danger"}
              title={isDpapiActive ? t("dpapi_tooltip_active") : t("dpapi_tooltip_inactive")}
            >
              {isDpapiActive ? t("dpapi_active") : t("dpapi_inactive")}
            </TrayChip>
            <TrayChip
              icon={RotateCcw}
              title={t("reset_default")}
              onClick={() => {
                resetSettings()
                  .then(() =>
                    notify(t("reset_success"), "neutral"),
                  )
                  .catch((e) => notify(errorText(e), "danger"))
              }}
            >
              Reset
            </TrayChip>
          </>
        }
      />
    </>
  )
}

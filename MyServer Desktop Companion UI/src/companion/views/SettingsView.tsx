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
  Info,
  Languages,
  Lock,
  Network,
  PanelTopOpen,
  RefreshCw,
  Rocket,
  RotateCcw,
  Share2,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from "lucide-react"
import { FooterStatus, TrayChip } from "../FlyoutShell"
import { getCompanionApi, type UpdateInfo } from "../api"
import { errorText, useAsyncAction, useCompanion, useNotice } from "../store"
import {
  AccordionSection,
  Button,
  Card,
  Chip,
  Mono,
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
  const { settings, setSetting, resetSettings, openWizard } = useCompanion()
  const { notify } = useNotice()
  const [updateState, runUpdate] = useAsyncAction(api.checkForUpdate)
  const [checkingUpdate, setCheckingUpdate] = useState(false)
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(() => {
    if (typeof window !== "undefined" && window.location.search.includes("mock_update=1")) {
      return {
        upToDate: false,
        version: APP_VERSION,
        htmlUrl: "https://github.com/Gibranibang/My-Server-beta/releases/latest",
        downloadUrl: "https://github.com/Gibranibang/My-Server-beta/releases/latest"
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
  const explorerCtxId = useId()
  const explorerHotkeyId = useId()
  const [contextMenuBusy, setContextMenuBusy] = useState(false)
  const [contextMenuChecked, setContextMenuChecked] = useState(
    Boolean(settings.explorerContextMenuEnabled),
  )
  const [explorerHotkeyBusy, setExplorerHotkeyBusy] = useState(false)
  const [explorerHotkeyChecked, setExplorerHotkeyChecked] = useState(
    settings.explorerHotkeyEnabled ?? true,
  )

  useEffect(() => {
    setContextMenuChecked(Boolean(settings.explorerContextMenuEnabled))
  }, [settings.explorerContextMenuEnabled])

  useEffect(() => {
    setExplorerHotkeyChecked(settings.explorerHotkeyEnabled ?? true)
  }, [settings.explorerHotkeyEnabled])

  const t = getTranslation(settings?.language)
  const isId = settings?.language === "id"
  const activeVersion = APP_VERSION
  const activeChannel = details?.appChannel || APP_CHANNEL

  const handleToggleExplorerContextMenu = async (next: boolean) => {
    if (contextMenuBusy) return
    const prev = contextMenuChecked
    setContextMenuBusy(true)
    setContextMenuChecked(next)
    try {
      const res = await getCompanionApi().setExplorerContextMenuEnabled(next)
      if (res?.success === false) {
        throw new Error(res.error || "Registry error")
      }
      const settled = res?.enabled !== undefined ? Boolean(res.enabled) : next
      setContextMenuChecked(settled)
      void setSetting("explorerContextMenuEnabled", settled).catch(() => undefined)
      notify(
        t(settled ? "explorer_ctx_enabled_toast" : "explorer_ctx_disabled_toast"),
        "success",
      )
    } catch (err) {
      setContextMenuChecked(prev)
      notify(
        t("explorer_ctx_error_toast").replace(
          "{error}",
          errorText(err, settings?.language),
        ),
        "danger",
      )
    } finally {
      setContextMenuBusy(false)
    }
  }

  const handleToggleExplorerHotkey = async (next: boolean) => {
    if (explorerHotkeyBusy) return
    const prev = explorerHotkeyChecked
    setExplorerHotkeyBusy(true)
    setExplorerHotkeyChecked(next)
    try {
      const res = await getCompanionApi().setExplorerHotkeyEnabled(next)
      if (res?.success === false) {
        throw new Error(res.error || "Hotkey error")
      }
      const settled = res?.enabled !== undefined ? Boolean(res.enabled) : next
      setExplorerHotkeyChecked(settled)
      void setSetting("explorerHotkeyEnabled", settled).catch(() => undefined)
      notify(
        t(settled ? "xfer_hotkey_enabled_toast" : "xfer_hotkey_disabled_toast"),
        "success",
      )
    } catch (err) {
      setExplorerHotkeyChecked(prev)
      notify(errorText(err, settings?.language), "danger")
    } finally {
      setExplorerHotkeyBusy(false)
    }
  }

  useEffect(() => {
    api.getLogDirectory?.().then((info) => {
      if (info) setLogDirInfo(info)
    }).catch(() => {})
    api.getServerDetails().then((d) => {
      setDetails(d)
    }).catch(() => {})
  }, [api])



  const handleCheckUpdate = async () => {
    setCheckingUpdate(true)
    try {
      const info = await api.checkForUpdate()
      const parseVer = (v: string) => {
        const parts = (v || "").match(/\d+/g)
        return parts ? parts.map(Number) : [0, 0, 0]
      }
      const remote = parseVer(info.version)
      const current = parseVer(activeVersion)
      const isActuallyNewer =
        remote[0] > current[0] ||
        (remote[0] === current[0] && remote[1] > current[1]) ||
        (remote[0] === current[0] && remote[1] === current[1] && remote[2] > current[2])

      const effectiveInfo: UpdateInfo = {
        ...info,
        upToDate: !isActuallyNewer ? true : Boolean(info.upToDate)
      }
      setUpdateInfo(effectiveInfo)
      if (effectiveInfo.upToDate) {
        notify(
          isId
            ? `MyServer v${activeVersion} sudah menggunakan versi terbaru!`
            : `MyServer v${activeVersion} is already up to date!`,
          "neutral"
        )
      } else {
        notify(
          isId
            ? `Pembaruan Tersedia: MyServer v${effectiveInfo.version}!`
            : `Update Available: MyServer v${effectiveInfo.version}!`,
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

          {/* Unified Software Update Section (Single Auto-Check Toggle + Unified Check/Download Flow) */}
          {updateInfo && !updateInfo.upToDate ? (
            <div
              data-testid="unified-update-available"
              className="mt-3 w-full rounded-tile border border-brand/30 bg-brand/5 p-3 text-left"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex flex-col min-w-0">
                  <div className="flex items-center gap-1.5">
                    <Sparkles className="size-4 text-brand shrink-0" />
                    <span className="text-micro font-bold text-ink truncate">
                      {isId ? `Pembaruan Tersedia: v${updateInfo.version}` : `Update Available: v${updateInfo.version}`}
                    </span>
                    <span className="rounded-full bg-brand/15 px-1.5 py-0.5 text-[9px] font-bold text-brand shrink-0">
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

              <div className="mt-2.5 flex flex-col gap-1.5 w-full">
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
                  {isId ? `Unduh & Pasang v${updateInfo.version}` : `Download & Install v${updateInfo.version}`}
                </Button>
                <div className="grid grid-cols-2 gap-1.5">
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={RefreshCw}
                    block
                    state={checkingUpdate ? "busy" : "idle"}
                    busyLabel={t("checking_update")}
                    onClick={handleCheckUpdate}
                    className="h-7 rounded-control text-nano font-medium justify-center"
                  >
                    {isId ? "Periksa Ulang" : "Re-check"}
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
                    className="h-7 rounded-control text-nano font-medium text-ink-subtle hover:text-ink justify-center"
                  >
                    {isId ? "Buka Link" : "Open Link"}
                  </Button>
                </div>
                <Button
                  size="sm"
                  variant="soft"
                  icon={Archive}
                  block
                  state={zipUpdateState}
                  busyLabel={t("installing_zip")}
                  onClick={handleZipUpdate}
                  className="h-7 rounded-control text-nano font-medium justify-center"
                >
                  {t("install_zip")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-3 flex flex-col gap-2 w-full">
              <Button
                size="sm"
                variant="secondary"
                icon={RefreshCw}
                block
                state={checkingUpdate ? "busy" : "idle"}
                busyLabel={t("checking_update")}
                onClick={handleCheckUpdate}
              >
                {t("check_update")}
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
          )}

          {/* Single Unified Auto-Check Update Row */}
          <div className="mt-2.5 flex w-full items-center justify-between gap-2 rounded-control border border-line bg-surface-sunken px-3 py-2 text-left">
            <div className="flex min-w-0 items-center gap-2">
              <RefreshCw className="size-3.5 shrink-0 text-brand" />
              <div className="min-w-0 flex flex-col">
                <span className="truncate text-micro font-semibold text-ink">
                  {t("auto_check_update_label", "Check for Updates Automatically")}
                </span>
                <span className="truncate text-nano text-ink-subtle">
                  {t((settings?.autoCheckUpdate ?? true) ? "auto_check_update_on" : "auto_check_update_off")}
                </span>
              </div>
            </div>
            <Toggle
              label={t("auto_check_update_label", "Check for Updates Automatically")}
              checked={settings?.autoCheckUpdate ?? true}
              onChange={(nextVal) => {
                void setSetting("autoCheckUpdate", nextVal).then(() => {
                  notify(
                    nextVal
                      ? (isId ? "Pemeriksaan pembaruan otomatis diaktifkan" : "Automatic update check enabled")
                      : (isId ? "Pemeriksaan pembaruan otomatis dinonaktifkan" : "Automatic update check disabled"),
                    "neutral",
                  )
                })
              }}
            />
          </div>
        </Card>

        {/* ========================================================= */}
        {/* ACCORDION 1: Sistem & Startup                             */}
        {/* ========================================================= */}
        <AccordionSection
          title={t("sec_system_title")}
          subtitle={t("sec_system_desc")}
          icon={Rocket}
          defaultOpen={true}
        >
          <div className="flex flex-col gap-2.5">
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
            </div>

            {/* Top-Left Home Dashboard Button Target */}
            <div className="flex flex-col gap-1.5 rounded-tile border border-line bg-surface p-2.5">
              <span className="text-micro font-semibold text-ink">
                {t("dashboard_click_title", "Top-Left Dashboard Shortcut on Home")}
              </span>
              <span className="text-nano text-ink-subtle">
                {t("dashboard_click_subtitle", "Choose which web dashboard opens from the home shortcut icon")}
              </span>
              <div className="grid grid-cols-2 gap-1.5 pt-1">
                <button
                  type="button"
                  data-testid="dashboard-target-zimaos"
                  onClick={() => {
                    void setSetting("dashboardClickTarget", "zimaos")
                    notify(t("dashboard_target_set_zimaos", "Dashboard shortcut set to ZimaOS Dashboard"), "success")
                  }}
                  className={cx(
                    "flex items-center justify-center gap-1.5 rounded-control px-2 py-1.5 text-nano font-medium transition cursor-pointer border min-w-0",
                    (settings.dashboardClickTarget || "zimaos") === "zimaos"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <ExternalLink className="size-3 shrink-0" />
                  <span className="truncate">{t("dashboard_target_zimaos", "ZimaOS Dashboard")}</span>
                </button>
                <button
                  type="button"
                  data-testid="dashboard-target-backend"
                  onClick={() => {
                    void setSetting("dashboardClickTarget", "backend")
                    notify(t("dashboard_target_set_backend", "Dashboard shortcut set to Backend Dashboard"), "success")
                  }}
                  className={cx(
                    "flex items-center justify-center gap-1.5 rounded-control px-2 py-1.5 text-nano font-medium transition cursor-pointer border min-w-0",
                    settings.dashboardClickTarget === "backend"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <AppWindow className="size-3 shrink-0" />
                  <span className="truncate">{t("dashboard_target_backend", "Backend Dashboard")}</span>
                </button>
              </div>
            </div>

            {/* Setup Wizard re-entry */}
            <div className="flex items-center justify-between gap-2 rounded-tile border border-line bg-surface p-2.5">
              <div className="flex min-w-0 flex-col">
                <span className="text-micro font-semibold text-ink">
                  {t("wiz_settings_launch_title", "Setup Wizard")}
                </span>
                <span className="text-nano text-ink-subtle">
                  {t("wiz_settings_launch_desc", "Re-run guided connection, login, backend, Syncthing, and VM setup")}
                </span>
              </div>
              <button
                type="button"
                data-testid="settings-open-wizard"
                onClick={() => void openWizard()}
                className="shrink-0 cursor-pointer rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-micro font-semibold text-ink transition hover:text-brand"
              >
                {t("wiz_settings_launch_btn", "Setup Wizard")}
              </button>
            </div>
          </div>
        </AccordionSection>

        {/* ========================================================= */}
        {/* ACCORDION 2: Tampilan, Bahasa & Keamanan Vault            */}
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
            {/* File Manager Target Selection (3 Options: Explorer, ZimaOS, Backend File Manager) */}
            <div className="flex flex-col gap-1.5 rounded-tile border border-line bg-surface p-2.5">
              <span className="text-micro font-semibold text-ink">
                {t("fm_click_title")}
              </span>
              <span className="text-nano text-ink-subtle">
                {t("fm_click_subtitle")}
              </span>
              <div className="flex flex-col gap-1.5 pt-1">
                <button
                  type="button"
                  data-testid="fm-target-explorer"
                  onClick={() => {
                    void setSetting("fileManagerClickTarget", "explorer")
                    notify(t("fm_target_set_explorer"), "success")
                  }}
                  className={cx(
                    "flex items-center justify-between gap-2 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border",
                    (settings.fileManagerClickTarget || "explorer") === "explorer"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <HardDrive className="size-3.5 shrink-0" />
                    <span className="truncate">{t("fm_target_explorer")}</span>
                  </span>
                  {(settings.fileManagerClickTarget || "explorer") === "explorer" && (
                    <Check className="size-3.5 shrink-0" strokeWidth={2.5} />
                  )}
                </button>
                <button
                  type="button"
                  data-testid="fm-target-zimaos"
                  onClick={() => {
                    void setSetting("fileManagerClickTarget", "zimaos")
                    notify(t("fm_target_set_zimaos"), "success")
                  }}
                  className={cx(
                    "flex items-center justify-between gap-2 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border",
                    settings.fileManagerClickTarget === "zimaos"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Folder className="size-3.5 shrink-0" />
                    <span className="truncate">{t("fm_target_zimaos")}</span>
                  </span>
                  {settings.fileManagerClickTarget === "zimaos" && (
                    <Check className="size-3.5 shrink-0" strokeWidth={2.5} />
                  )}
                </button>
                <button
                  type="button"
                  data-testid="fm-target-backend"
                  onClick={() => {
                    void setSetting("fileManagerClickTarget", "backend")
                    notify(t("fm_target_set_backend", "File Manager click action set to Backend File Manager"), "success")
                  }}
                  className={cx(
                    "flex items-center justify-between gap-2 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border",
                    settings.fileManagerClickTarget === "backend"
                      ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                      : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
                  )}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <FolderOpen className="size-3.5 shrink-0" />
                    <span className="truncate">{t("fm_target_backend", "Backend File Manager")}</span>
                  </span>
                  {settings.fileManagerClickTarget === "backend" && (
                    <Check className="size-3.5 shrink-0" strokeWidth={2.5} />
                  )}
                </button>
              </div>
            </div>

            {/* Storage & Network Startup Toggles */}
            <div className="divide-y divide-line overflow-hidden rounded-tile border border-line bg-surface">
              <SettingToggleRow
                icon={HardDrive}
                label={t("autoMountSmb_label")}
                caption={t(settings.autoMountSmb ? "autoMountSmb_on" : "autoMountSmb_off")}
                settingKey="autoMountSmb"
              />
              <div className="flex items-center gap-2.5 px-3 py-2 transition-colors duration-150 hover:bg-surface-sunken">
                <Share2
                  className="size-4 shrink-0 text-ink-subtle"
                  strokeWidth={2}
                  aria-hidden
                />
                <label htmlFor={explorerCtxId} className="min-w-0 flex-1 cursor-pointer">
                  <span className="block text-label font-medium text-ink">
                    {t("explorer_ctx_label")}
                  </span>
                  <span className="block text-micro text-ink-subtle">
                    {t(contextMenuChecked ? "explorer_ctx_on" : "explorer_ctx_off")}
                  </span>
                </label>
                <Toggle
                  id={explorerCtxId}
                  label={t("explorer_ctx_label")}
                  checked={contextMenuChecked}
                  disabled={contextMenuBusy}
                  onChange={(next) => void handleToggleExplorerContextMenu(next)}
                />
              </div>
              <div
                data-testid="explorer-ctx-win11-hint"
                className="border-t border-line/60 bg-surface-sunken px-4 py-2 flex items-start gap-2"
              >
                <Info className="size-4 shrink-0 text-info-ink" aria-hidden />
                <p className="text-caption font-normal text-ink-subtle">
                  {t("explorer_ctx_win11_hint")}
                </p>
              </div>
              <div className="flex items-center gap-2.5 px-3 py-2 transition-colors duration-150 hover:bg-surface-sunken">
                <ClipboardCopy
                  className="size-4 shrink-0 text-ink-subtle"
                  strokeWidth={2}
                  aria-hidden
                />
                <label htmlFor={explorerHotkeyId} className="min-w-0 flex-1 cursor-pointer">
                  <span className="block text-label font-medium text-ink">
                    {t("xfer_hotkey_label")}
                  </span>
                  <span className="block text-micro text-ink-subtle">
                    {t(explorerHotkeyChecked ? "xfer_hotkey_on" : "xfer_hotkey_off")}
                  </span>
                </label>
                <Toggle
                  id={explorerHotkeyId}
                  label={t("xfer_hotkey_label")}
                  checked={explorerHotkeyChecked}
                  disabled={explorerHotkeyBusy}
                  onChange={(next) => void handleToggleExplorerHotkey(next)}
                />
              </div>
              <div className="border-t border-line/60 bg-surface-sunken px-4 py-2 flex items-start gap-2">
                <Info className="size-4 shrink-0 text-info-ink" aria-hidden />
                <p className="text-caption font-normal text-ink-subtle">
                  {t("xfer_hotkey_hint")}
                </p>
              </div>
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
                className="min-w-0 truncate text-[11px] px-2"
              >
                <span className="truncate">{t("copy_log_btn")}</span>
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
                className="min-w-0 truncate text-[11px] px-2"
              >
                <span className="truncate">{t("change_log_folder_btn")}</span>
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

            {/* Log Explorer & Notepad Actions (Auto-Layout Contained Grid, Zero Overflow) */}
            <div className="grid grid-cols-2 gap-2">
              <Button
                size="sm"
                variant="secondary"
                icon={FileText}
                block
                onClick={() => {
                  api.openLogFile()
                  notify(t("opening_log_notepad"), "info")
                }}
                title={t("open_log_file_desc")}
                className="min-w-0 truncate text-[11px] px-2"
              >
                <span className="truncate">{t("open_log_file")}</span>
              </Button>
              <Button
                size="sm"
                variant="secondary"
                icon={FolderOpen}
                block
                onClick={() => {
                  api.openLogFolder()
                  notify(t("opening_log_folder"), "info")
                }}
                title={t("open_log_folder_desc")}
                className="min-w-0 truncate text-[11px] px-2"
              >
                <span className="truncate">{t("open_log_folder")}</span>
              </Button>
            </div>

            {/* Maintenance & Cache Cleanup */}
            <div className="flex items-center justify-between gap-2 rounded-tile border border-line bg-surface p-2.5">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <Sparkles className="size-4 shrink-0 text-brand" />
                <div className="flex min-w-0 flex-col">
                  <span className="truncate text-micro font-semibold text-ink">
                    {t("clean_cache_btn")}
                  </span>
                  <span className="text-nano text-ink-subtle leading-snug">
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
                className="h-7 shrink-0 text-micro px-2.5"
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

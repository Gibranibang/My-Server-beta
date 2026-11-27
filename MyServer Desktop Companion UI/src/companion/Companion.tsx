import { useState, useEffect, useRef, Component, type ComponentType, type ErrorInfo, type ReactNode } from "react"
import {
  ArrowLeft,
  ExternalLink,
  Minus,
  Moon,
  PanelTopOpen,
  Power,
  Share2,
  Sun,
  WifiOff,
  X,
} from "lucide-react"
import FlyoutShell, { FlyoutHeader, HeaderTitle } from "./FlyoutShell"
import TrayDock from "./TrayDock"
import { NoticeProvider, SERVER_IP, SERVER_URL, useCompanion, useNotice } from "./store"
import { getTranslation } from "./i18n"
import { Button, IconBadge, IconButton } from "./ui"
import type { MiniTrayDragDropDetail, ShareErrorCode, ViewId } from "./types"
import AppsView from "./views/AppsView"
import BackupView from "./views/BackupView"
import FilesView from "./views/FilesView"
import HomeView from "./views/HomeView"
import PowerView from "./views/PowerView"
import SettingsView from "./views/SettingsView"
import ServerView from "./views/ServerView"
import VmManagerView from "./views/VmManagerView"
import type { ViewProps } from "./views/shared"
import { getCompanionApi } from "./api"

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
}

class ViewErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ViewErrorBoundary] Error:", error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      const t = getTranslation()
      return (
        <div className="flex flex-col items-center justify-center p-6 text-center text-ink my-auto">
          <div className="h-10 w-10 rounded-full bg-danger-ink/10 flex items-center justify-center text-danger-ink mb-2">
            <X className="h-5 w-5" />
          </div>
          <h3 className="text-body font-bold text-danger-ink">{getTranslation()("view_error_title", "Gagal Memuat Tampilan")}</h3>
          <p className="mt-1 text-micro text-ink-subtle max-w-[240px]">
            {this.state.error?.message || getTranslation()("view_error_desc", "Terjadi kendala saat merender komponen.")}
          </p>
          <Button
            size="sm"
            variant="soft"
            className="mt-3 font-medium"
            onClick={() => this.setState({ hasError: false })}
          >
            {t("reload_view_btn", "Reload View")}
          </Button>
        </div>
      )
    }
    return this.props.children
  }
}

const VIEWS: Record<ViewId, ComponentType<ViewProps>> = {
  home: HomeView,
  files: FilesView,
  backup: BackupView,
  apps: AppsView,
  settings: SettingsView,
  power: PowerView,
  server: ServerView,
  vm: VmManagerView,
}

function getViewHeader(view: Exclude<ViewId, "home">, t: (k: string, f?: string) => string) {
  switch (view) {
    case "files":
      return {
        title: t("view_files_title", "Storage & Files"),
        subtitle: t("view_files_sub", "Samba SMB Network Storage"),
      }
    case "backup":
      return {
        title: t("view_backup_title", "Backup & Sync"),
        subtitle: t("view_backup_sub", "Atomic Backup & Syncthing Core"),
      }
    case "apps":
      return {
        title: t("view_apps_title", "Services & Web Apps"),
        subtitle: t("view_apps_sub", "Docker · ZimaOS Containers"),
      }
    case "settings":
      return {
        title: t("view_settings_title", "Settings & Preferences"),
        subtitle: t("view_settings_sub", "Desktop Companion Configuration"),
      }
    case "power":
      return {
        title: t("view_power_title", "Server Power Control"),
        subtitle: t("view_power_sub", "Reboot · Shutdown · Wake-on-LAN"),
      }
    case "server":
      return {
        title: t("view_server_title", "Server & Network"),
        subtitle: t("view_server_sub", "Access Routes · Accounts · Remote"),
      }
    case "vm":
      return {
        title: t("view_vm_title", "VM Manager"),
        subtitle: t("view_vm_sub", "InstaBox & Antigravity Remote"),
      }
  }
}

type WindowState = "open" | "minimized" | "closed"

function TrayPlaceholder({
  state,
  onRestore,
}: {
  state: Exclude<WindowState, "open">
  onRestore: () => void
}) {
  return (
    <div className="flex h-companion w-[calc(var(--spacing-dock)+var(--spacing-flyout)+1rem)] shrink-0 flex-col items-center justify-center gap-4 rounded-panel border border-dashed border-canvas-line bg-canvas-raised/30 p-8 text-center">
      <span className="inline-flex size-11 items-center justify-center rounded-full border border-canvas-line bg-canvas-raised text-canvas-muted">
        {state === "minimized" ? (
          <Minus className="size-5" aria-hidden />
        ) : (
          <X className="size-5" aria-hidden />
        )}
      </span>
      <div>
        <p className="text-body font-semibold text-canvas-ink">
          {state === "minimized"
            ? "Flyout diminimalkan"
            : "Ditutup ke System Tray"}
        </p>
        <p className="mt-1 text-label text-canvas-muted">
          MyServer tetap berjalan di latar belakang. Mini tray disembunyikan
          sampai dibuka kembali dari ikon system tray.
        </p>
      </div>
      <Button
        variant="secondary"
        size="sm"
        icon={PanelTopOpen}
        onClick={onRestore}
      >
        Tampilkan Kembali
      </Button>
    </div>
  )
}

function mapShareErrorCodeToI18nKey(code?: ShareErrorCode | string): string {
  switch (code) {
    case "LOCAL_DRIVE":
      return "share_err_local_drive"
    case "FOREIGN_NAS":
      return "share_err_foreign_nas"
    case "SHARE_NOT_MOUNTED_IN_BACKEND":
      return "share_err_unmounted"
    case "MULTI_ITEM_DROP":
      return "share_err_multi_item"
    case "SERVER_OFFLINE":
    case "BACKEND_OFFLINE":
      return "share_err_offline"
    case "UNAUTHENTICATED_SESSION":
      return "share_err_unauthenticated"
    case "FORBIDDEN_PATH":
      return "share_err_forbidden"
    default:
      return "share_err_invalid_path"
  }
}

export function CompanionFrame({
  view,
  onViewChange,
}: {
  view: ViewId
  onViewChange: (view: ViewId) => void
}) {
  const api = getCompanionApi()
  const { settings, setSetting, isOnline, wizardOpen } = useCompanion()
  const t = getTranslation(settings?.language)
  const isId = settings?.language === "id"
  const activeTheme = settings?.theme === "light" ? "light" : "dark"
  const [windowState, setWindowState] = useState<WindowState>("open")
  const [dragHoverActive, setDragHoverActive] = useState(false)
  const resolvingDropRef = useRef(false)
  const { notify } = useNotice()
  const isOnlineRef = useRef(isOnline)
  isOnlineRef.current = isOnline
  const notifyRef = useRef(notify)
  notifyRef.current = notify
  const languageRef = useRef(settings?.language)
  languageRef.current = settings?.language
  const open = windowState === "open"

  const isNativeTauriMain =
    typeof window !== "undefined" &&
    Boolean((window as any).__TAURI_INTERNALS__ || (window as any).__TAURI__) &&
    (() => {
      const params = new URLSearchParams(window.location.search)
      return (
        params.get("window") !== "share" &&
        params.get("canvas") !== "1" &&
        params.get("board") !== "1"
      )
    })()

  useEffect(() => {
    if (!open || wizardOpen || !isNativeTauriMain) {
      setDragHoverActive(false)
      return
    }

    const handleBlur = () => {
      setDragHoverActive(false)
    }

    const handleDragDrop = (event: Event) => {
      const detail = (event as CustomEvent<MiniTrayDragDropDetail | undefined>).detail
      if (!detail || typeof detail !== "object") return

      if (detail.type === "enter") {
        setDragHoverActive(true)
        return
      }

      if (detail.type === "leave") {
        setDragHoverActive(false)
        return
      }

      if (detail.type === "drop") {
        setDragHoverActive(false)
        const paths = Array.isArray(detail.paths) ? detail.paths.filter(Boolean) : []
        if (paths.length === 0) {
          return
        }

        const translate = getTranslation(languageRef.current)
        if (paths.length > 1) {
          notifyRef.current(translate("share_err_multi_item"), "danger")
          return
        }

        if (!isOnlineRef.current) {
          notifyRef.current(translate("share_err_offline"), "danger")
          return
        }

        if (resolvingDropRef.current) {
          return
        }

        resolvingDropRef.current = true
        void (async () => {
          try {
            const companionApi = getCompanionApi()
            const res = await companionApi.resolveSharePath(paths[0])
            if (res?.ok && res.target) {
              await companionApi.openShareWindow(res.target)
            } else {
              const key = mapShareErrorCodeToI18nKey(res?.code)
              notifyRef.current(getTranslation(languageRef.current)(key), "danger")
            }
          } catch {
            notifyRef.current(getTranslation(languageRef.current)("share_err_invalid_path"), "danger")
          } finally {
            resolvingDropRef.current = false
          }
        })()
      }
    }

    window.addEventListener("myserver:drag-drop", handleDragDrop)
    window.addEventListener("blur", handleBlur)
    return () => {
      window.removeEventListener("myserver:drag-drop", handleDragDrop)
      window.removeEventListener("blur", handleBlur)
      setDragHoverActive(false)
    }
  }, [open, wizardOpen, isNativeTauriMain])

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", activeTheme)
    document.documentElement.setAttribute("data-server-status", isOnline ? "online" : "offline")
  }, [activeTheme, isOnline])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const testNotif = params.get("testNotif")
    if (testNotif) {
      const timer = setTimeout(() => {
        notify(decodeURIComponent(testNotif), "info")
      }, 600)
      return () => clearTimeout(timer)
    }
  }, [notify])

  const toggleTheme = () => {
    const next = activeTheme === "dark" ? "light" : "dark"
    void setSetting("theme", next)
    try {
      localStorage.setItem("myserver_theme", next)
      document.documentElement.setAttribute("data-theme", next)
    } catch {}
    notify(
      next === "dark"
        ? (isId ? "Tema Gelap diaktifkan" : "Dark theme activated")
        : (isId ? "Tema Terang diaktifkan" : "Light theme activated"),
      "neutral"
    )
  }

  const go = (next: ViewId) => {
    onViewChange(next)
    setWindowState("open")
  }

  const windowControls = (
    <>
      <IconButton
        icon={activeTheme === "dark" ? Sun : Moon}
        label={
          activeTheme === "dark"
            ? (isId ? "Ganti ke Tema Terang" : "Switch to Light Mode")
            : (isId ? "Ganti ke Tema Gelap" : "Switch to Dark Mode")
        }
        onClick={toggleTheme}
      />
      <IconButton
        icon={Minus}
        label={t("nav_minimize", "Minimize")}
        onClick={() => {
          void api.minimizeWindow()
        }}
      />
      <IconButton
        icon={X}
        label={t("nav_close", "Close Companion")}
        onClick={() => {
          onViewChange("home")
          void api.hideFlyout()
        }}
      />
    </>
  )

  let header
  if (view === "home") {
    const isBackendDashboard = settings?.dashboardClickTarget === "backend"
    header = (
      <FlyoutHeader
        leading={
          <IconButton
            icon={ExternalLink}
            label={
              isBackendDashboard
                ? t("dashboard_target_backend_tooltip", isId ? "Buka Dashboard Backend" : "Open Backend Dashboard")
                : t("open_in_browser", "Open console in browser")
            }
            onClick={async () => {
              if (isBackendDashboard && typeof api.openBackendFileManager === "function") {
                const res = await api.openBackendFileManager()
                if (res && res.success === false) {
                  notify(res.error || (isId ? "Backend tidak dapat dijangkau." : "Backend unreachable."), "danger")
                }
              } else {
                void api.openUrl(SERVER_URL || `http://${SERVER_IP}`)
              }
            }}
          />
        }
        trailing={windowControls}
      />
    )
  } else if (view === "power") {
    header = (
      <FlyoutHeader
        leading={
          <>
            <IconBadge icon={Power} tone="danger" size="sm" />
            <HeaderTitle {...getViewHeader("power", t)} />
          </>
        }
        trailing={
          <IconButton
            icon={X}
            label={t("nav_close", "Close power control")}
            onClick={() => go("home")}
          />
        }
      />
    )
  } else {
    header = (
      <FlyoutHeader
        leading={
          <>
            <IconButton
              icon={ArrowLeft}
              label={t("nav_back", "Back to Home")}
              onClick={() => go("home")}
            />
            <HeaderTitle {...getViewHeader(view as Exclude<ViewId, "home">, t)} />
          </>
        }
        trailing={windowControls}
      />
    )
  }

  const View = VIEWS[view]

  return (
    <div
      data-theme={activeTheme}
      data-server-status={isOnline ? "online" : "offline"}
      className="relative flex items-start gap-[13.1px] companion-fit bg-[#0E100A] data-[theme=light]:bg-white rounded-[16px] overflow-hidden select-none border border-[#262626] data-[theme=light]:border-[#E2E8F0] shadow-2xl p-0"
    >
      {open ? (
        <>
          <TrayDock powerActive={view === "power"} onNavigate={go} />
          <FlyoutShell header={header}>
            <div
              key={view}
              className="flex min-h-0 flex-1 flex-col motion-safe:animate-view-in"
            >
              <ViewErrorBoundary>
                <View go={go} />
              </ViewErrorBoundary>
            </div>
          </FlyoutShell>
        </>
      ) : (
        <TrayPlaceholder
          state={windowState}
          onRestore={() => setWindowState("open")}
        />
      )}
      {open && !wizardOpen && dragHoverActive && (
        <div
          data-testid="mini-tray-drop-overlay"
          className="absolute inset-0 z-50 rounded-[16px] bg-surface/92 backdrop-blur-xs p-4 flex items-center justify-center"
        >
          <div
            className={`flex h-full w-full flex-col items-center justify-center gap-4 rounded-card border-2 border-dashed p-6 text-center transition-colors duration-150 ${
              isOnline
                ? "border-brand bg-brand/5"
                : "border-danger bg-danger-soft/40"
            }`}
          >
            <span
              className={`flex size-12 items-center justify-center rounded-full ${
                isOnline
                  ? "bg-brand/15 text-brand"
                  : "bg-danger-soft text-danger-ink"
              }`}
            >
              {isOnline ? (
                <Share2 className="size-6" aria-hidden />
              ) : (
                <WifiOff className="size-6" aria-hidden />
              )}
            </span>
            <div className="space-y-1">
              <p
                className={`text-heading font-semibold ${
                  isOnline ? "text-ink" : "text-danger-ink"
                }`}
              >
                {t(isOnline ? "drop_title_online" : "drop_title_offline")}
              </p>
              <p className="text-caption font-normal text-ink-subtle">
                {t(isOnline ? "drop_sub_online" : "drop_sub_offline")}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** One tray + flyout pairing. Each instance owns its view and notices; server state is shared globally. */
export default function Companion(props: {
  view: ViewId
  onViewChange: (view: ViewId) => void
}) {
  return (
    <NoticeProvider>
      <CompanionFrame {...props} />
    </NoticeProvider>
  )
}

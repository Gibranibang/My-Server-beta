import { useState, Component, type ComponentType, type ErrorInfo, type ReactNode } from "react"
import {
  ArrowLeft,
  ExternalLink,
  Minus,
  PanelTopOpen,
  Power,
  X,
} from "lucide-react"
import FlyoutShell, { FlyoutHeader, HeaderTitle } from "./FlyoutShell"
import TrayDock from "./TrayDock"
import { NoticeProvider, SERVER_IP, useCompanion, useNotice } from "./store"
import { getTranslation } from "./i18n"
import { Button, IconBadge, IconButton } from "./ui"
import type { ViewId } from "./types"
import AppsView from "./views/AppsView"
import BackupView from "./views/BackupView"
import FilesView from "./views/FilesView"
import HomeView from "./views/HomeView"
import PowerView from "./views/PowerView"
import SettingsView from "./views/SettingsView"
import ServerView from "./views/ServerView"
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

function CompanionFrame({
  view,
  onViewChange,
}: {
  view: ViewId
  onViewChange: (view: ViewId) => void
}) {
  const api = getCompanionApi()
  const { settings } = useCompanion()
  const t = getTranslation(settings?.language)
  const [windowState, setWindowState] = useState<WindowState>("open")
  const { notify } = useNotice()
  const open = windowState === "open"

  const go = (next: ViewId) => {
    onViewChange(next)
    setWindowState("open")
  }

  const windowControls = (
    <>
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
    header = (
      <FlyoutHeader
        leading={
          <IconButton
            icon={ExternalLink}
            label={t("open_in_browser", "Open console in browser")}
            onClick={() => {
              void api.openUrl(`http://${SERVER_IP}`)
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
    <div className="flex items-stretch gap-4 companion-fit rounded-2xl bg-surface overflow-hidden">
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

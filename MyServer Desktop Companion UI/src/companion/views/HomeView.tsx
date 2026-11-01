import { getTranslation } from "../i18n"
import { APP_VERSION } from "../version"
import { useEffect, useState } from "react"
import {
  MoreVertical,
  Check,
  ChevronDown,
  ChevronRight,
  CloudUpload,
  FolderOpen,
  LayoutGrid,
  Plus,
  Radio,
  SlidersHorizontal,
  Wifi,
  Eye,
  EyeOff,
  User,
  Network,
  Globe,
  Zap,
  type LucideIcon,
} from "lucide-react"
import { ChipGlow, FooterStatus } from "../FlyoutShell"
import { SERVER_IP, errorText, useCompanion, useNotice } from "../store"
import { getCompanionApi } from "../api"
import { Chip, Mono, cx } from "../ui"
import Wordmark from "../Wordmark"
import type { ServerDetails, ViewId } from "../types"
import type { ViewProps } from "./shared"

const FEATURES: {
  view: ViewId
  title: string
  titleKey?: string
  hintKey?: string
  hint: string
  icon: LucideIcon
}[] = [
  {
    view: "backup",
    title: "Backup",
    hintKey: "feat_backup_sub" as const,
    hint: "Atomic Backup & Syncthing",
    icon: CloudUpload,
  },
  {
    view: "files",
    title: "File Manager",
    hintKey: "feat_storage_sub" as const,
    hint: "Penyimpanan SMB & Web Files",
    icon: FolderOpen,
  },
  {
    view: "apps",
    title: "Apps",
    hintKey: "feat_apps_sub" as const,
    hint: "Layanan & Web Apps",
    icon: LayoutGrid,
  },
  {
    view: "settings",
    title: "Options",
    titleKey: "feat_options_title" as const,
    hintKey: "feat_settings_sub" as const,
    hint: "Pengaturan & Preferensi Sistem",
    icon: SlidersHorizontal,
  },
]

function FeatureCard({
  title,
  titleKey,
  hint,
  hintKey,
  icon: Icon,
  onClick,
  extraAction,
}: typeof FEATURES[number] & {
  onClick: () => void
  extraAction?: { label: string; onClick: () => void; title: string }
}) {
  const { settings } = useCompanion()
  const t = getTranslation(settings?.language)
  const dynamicTitle = titleKey ? t(titleKey, title) : title
  const dynamicHint = hintKey ? t(hintKey, hint) : hint
  return (
    <div
      onClick={onClick}
      title={dynamicHint}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onClick()
        }
      }}
      className="group relative isolate min-h-0 overflow-hidden rounded-card border border-line bg-surface text-left shadow-card transition-[border-color,box-shadow,translate] duration-200 ease-glide outline-none hover:-translate-y-0.5 hover:border-line-strong hover:shadow-card-hover focus-visible:ring-2 focus-visible:ring-info/45 focus-visible:ring-offset-2 active:translate-y-0 cursor-pointer"
    >
      <span className="absolute top-3.5 left-3.5 text-title font-semibold text-ink">
        {dynamicTitle}
      </span>
      {extraAction && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            extraAction.onClick()
          }}
          title={extraAction.title}
          aria-label={extraAction.title}
          className="absolute top-3 right-3 z-10 flex size-6 items-center justify-center rounded-control bg-surface-sunken/50 text-ink-subtle hover:bg-surface-sunken hover:text-ink transition cursor-pointer"
        >
          <MoreVertical className="size-3.5" />
        </button>
      )}
      <span
        aria-hidden
        className="absolute right-1.5 bottom-1.5 flex size-[82px] items-end justify-end text-brand transition-transform duration-300 ease-glide group-hover:scale-105"
      >
        <Icon className="size-16" strokeWidth={1.25} fill="none" />
      </span>
    </div>
  )
}

export default function HomeView({ go }: ViewProps) {
  const api = getCompanionApi()
  const { isOnline, settings, startTransition, endTransition, runWithTransition, isInitialLoading, homeLoading } = useCompanion()
  const t = getTranslation(settings?.language)
  const { notify } = useNotice()
  const [details, setDetails] = useState<ServerDetails | null>(null)
  const [showAccountMenu, setShowAccountMenu] = useState(false)
  const [showRouteMenu, setShowRouteMenu] = useState(false)
  const [maskedRoutes, setMaskedRoutes] = useState<Record<string, boolean>>({})

  // Safe translation helper (Pasal 6 Guarantee)
  const safeT = (k: string, d?: string) => (t ? t(k, d) : (d || k))

  useEffect(() => {
    const refresh = () => {
      api
        .getServerDetails()
        .then(setDetails)
        .catch(() => {})
    }
    refresh()
    window.addEventListener("myserver:refresh", refresh)
    window.addEventListener("focus", refresh)
    return () => {
      window.removeEventListener("myserver:refresh", refresh)
      window.removeEventListener("focus", refresh)
    }
  }, [api, isOnline])

  // Helper klasifikasi rute ringkas & ikon: LAN, Remote, WAN
  const classifyRoute = (r?: { name?: string; url?: string; isZeroTier?: boolean }) => {
    const name = (r?.name || "").toLowerCase()
    const url = (r?.url || "").toLowerCase()
    const isZt = Boolean(r?.isZeroTier) || url.includes("172.24.") || url.includes("10.147.") || name.includes("zerotier")
    if (isZt) {
      return { type: "Remote" as const, label: "Remote", icon: Wifi, descKey: "route_remote_desc" }
    }
    const isLan = url.includes("192.168.") || url.includes("10.") || url.includes(".local") || url.includes("127.0.0.1") || url.includes("localhost") || /172\.(1[6-9]|2[0-9]|3[0-1])\./.test(url) || name.includes("lan") || name.includes("lokal")
    if (isLan) {
      return { type: "LAN" as const, label: "LAN", icon: Network, descKey: "route_lan_desc" }
    }
    return { type: "WAN" as const, label: "WAN", icon: Globe, descKey: "route_wan_desc" }
  }

  const isRouteMasked = (id: string) => maskedRoutes[id] !== false
  const toggleRouteMask = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setMaskedRoutes((prev) => ({ ...prev, [id]: !isRouteMasked(id) }))
  }
  const maskUrl = (url: string) => {
    return url.replace(/^(https?:\/\/)?([^\/:]+)/, (_m, proto = "", host = "") => {
      if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) {
        return `${proto}${host.split(".")[0]}.•••.•••.•••`
      }
      return `${proto}••••••••••••`
    })
  }

  const onSwitchProfileQuick = (profile: string) => {
    if (details?.activeProfile === profile) {
      setShowAccountMenu(false)
      return
    }
    setShowAccountMenu(false)
    runWithTransition(
      t("switching_profile_title", "Beralih Profil Akun..."),
      t("switching_profile_desc", "Memasang penyimpanan share akun..."),
      async () => {
        const updated = await api.switchProfile(profile)
        setDetails(updated)
        window.dispatchEvent(new CustomEvent("myserver:refresh"))
        notify(`Beralih ke akun: ${profile}`, "success")
        return updated
      },
      { resetMetrics: false }
    ).catch((err) => {
      notify(errorText(err), "danger")
    })
  }

  const onAddProfileQuick = async () => {
    setShowAccountMenu(false)
    try {
      await api.addProfile()
      const updated = await api.getServerDetails()
      setDetails(updated)
      window.dispatchEvent(new CustomEvent("myserver:refresh"))
    } catch (err) {
      notify(errorText(err), "danger")
    }
  }

  if (homeLoading || isInitialLoading) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-3 px-4 pb-2 overflow-hidden">
        {/* Cold-Start Header Skeleton */}
        <div className="flex h-10 shrink-0 items-center justify-between pr-1 pl-1.5">
          <div className="h-6 w-32 rounded bg-surface-sunken animate-pulse" />
          <div className="h-4 w-12 rounded bg-surface-sunken animate-pulse" />
        </div>
        {/* Cold-Start 4 Feature Cards Grid Skeleton */}
        <div className="grid min-h-0 flex-1 grid-cols-2 grid-rows-2 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="flex h-full flex-col justify-between rounded-card border border-line bg-surface p-3"
            >
              <div className="flex items-start justify-between">
                <div className="size-8 rounded-lg bg-surface-sunken animate-pulse" />
                <div className="size-4 rounded bg-surface-sunken animate-pulse" />
              </div>
              <div className="flex flex-col gap-1.5">
                <div className="h-3.5 w-20 rounded bg-surface-sunken animate-pulse" />
                <div className="h-2.5 w-28 rounded bg-surface-sunken animate-pulse" />
              </div>
            </div>
          ))}
        </div>
        {/* Cold-Start Footer Card Skeleton */}
        <FooterStatus
          title={<div className="h-5 w-28 rounded bg-surface-sunken animate-pulse" />}
          chips={
            <>
              <div className="h-6 w-16 rounded-full bg-surface-sunken animate-pulse" />
              <div className="h-6 w-20 rounded-full bg-surface-sunken animate-pulse" />
            </>
          }
        />
      </div>
    )
  }


  const serverName = details?.serverName || t("server_default")
  const activeRouteObj = details?.routes?.find((r) => r.active)
  const currentRouteMeta = classifyRoute(activeRouteObj || { url: details?.activeHost })

  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col gap-3 px-4 pb-2">
        <div className="flex h-10 shrink-0 items-center justify-between pr-1 pl-1.5">
          <div className="flex items-center gap-3">
            <Wordmark />
            <Chip tone="info" size="sm">
              BETA
            </Chip>
          </div>
          <Mono className="text-micro text-ink-faint">v{details?.appVersion || APP_VERSION}</Mono>
        </div>
        <nav
          aria-label="Fitur MyServer"
          className="grid min-h-0 flex-1 grid-cols-2 grid-rows-2 gap-3"
        >
          {FEATURES.map((feature) => {
            const isFiles = feature.view === "files"
            return (
              <FeatureCard
                key={feature.view}
                {...feature}
                onClick={() => {
                  if (isFiles) {
                    api.openFileManager()
                    notify("Membuka Windows File Explorer...", "info")
                  } else {
                    go(feature.view)
                  }
                }}
                extraAction={
                  isFiles
                    ? {
                        label: "Menu",
                        title: "Buka Menu File Manager (Kelola Disk & SMB)",
                        onClick: () => go("files"),
                      }
                    : undefined
                }
              />
            )
          })}
        </nav>
      </div>

      <FooterStatus
        title={
          <div className="flex items-center gap-2">
            <span>{serverName}</span>
            <ChevronRight className="size-4 text-ink-faint" />
          </div>
        }
        onClick={() => go("server")}
        chips={
          <>
            <Chip
              tone={isOnline ? "success" : "neutral"}
              icon={currentRouteMeta.icon}
              leading={isOnline && <ChipGlow />}
              onClick={() => {
                setShowRouteMenu((prev) => !prev)
                setShowAccountMenu(false)
              }}
              className="cursor-pointer hover:border-info-line transition"
              title={t("switch_route_title", "Ganti Rute Akses")}
            >
              <span className="flex items-center gap-1">
                <span className="font-semibold">{currentRouteMeta.label}</span>
                <ChevronDown className="size-3 text-ink-muted shrink-0" />
              </span>
            </Chip>
            <Chip
              tone="info"
              icon={User}
              onClick={() => {
                setShowAccountMenu((prev) => !prev)
                setShowRouteMenu(false)
              }}
              className="cursor-pointer hover:border-info-line transition"
            >
              <span className="flex items-center gap-1">
                <span>{details?.activeProfile || details?.profiles?.[0] || t("user_profile_default")}</span>
                <ChevronDown className="size-3 text-info shrink-0" />
              </span>
            </Chip>
          </>
        }
      />

      {/* QUICK ACCESS ROUTE SWITCHER MODAL */}
      {showRouteMenu && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-3 backdrop-blur-xs"
          onClick={() => setShowRouteMenu(false)}
        >
          <div
            className="flex w-full max-w-[300px] flex-col gap-2.5 rounded-card border border-line bg-surface p-3.5 shadow-panel motion-safe:animate-flyout-in"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-line pb-2">
              <span className="flex items-center gap-1.5 text-label font-bold text-ink">
                <Radio className="size-4 text-brand" />
                {t("switch_route_title", "Ganti Rute Akses")}
              </span>
              <button
                type="button"
                onClick={() => setShowRouteMenu(false)}
                className="rounded p-1 text-ink-subtle hover:bg-surface-sunken hover:text-ink transition cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Active Route Summary Card */}
            <div className="flex items-center justify-between rounded-tile border border-line bg-surface-sunken p-2 text-caption">
              <div className="flex items-center gap-2 min-w-0">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand">
                  <currentRouteMeta.icon className="size-3.5" />
                </div>
                <div className="flex flex-col min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-micro font-bold text-ink truncate">{currentRouteMeta.label}</span>
                    {activeRouteObj?.pingMs !== undefined && activeRouteObj.pingMs !== null && (
                      <span className="text-micro font-mono text-ink-muted">{activeRouteObj.pingMs}ms</span>
                    )}
                  </div>
                  <span className="text-micro text-ink-subtle truncate">
                    {details?.activeRoute === "auto" ? t("route_auto_active", "Mode otomatis aktif") : (activeRouteObj?.name || currentRouteMeta.label)}
                  </span>
                </div>
              </div>
              <span className="rounded bg-success/15 px-1.5 py-0.5 text-micro font-semibold text-success shrink-0">
                {t("route_active_badge", "Active")}
              </span>
            </div>

            {/* Route Selection List */}
            <div className="flex flex-col gap-1 max-h-48 overflow-y-auto pr-0.5">
              <span className="text-micro font-semibold text-ink-subtle">{t("select_route_mode", "Pilihan Rute Akses:")}</span>

              {/* Entri 1: Auto Failover */}
              <button
                type="button"
                onClick={async () => {
                  setShowRouteMenu(false)
                  try {
                    await runWithTransition(
                      t("switching_route_title", "Beralih Rute..."),
                      t("switching_route_desc", "Menghubungkan ke jalur akses server..."),
                      async () => {
                        const updated = await api.switchRoute("auto")
                        setDetails(updated)
                        notify(t("route_switched_notice", "Rute dialihkan ke: ") + t("route_mode_auto", "Otomatis"), "info")
                        window.dispatchEvent(new CustomEvent("myserver:refresh"))
                        return updated
                      }
                    )
                  } catch (err: any) {
                    notify(err?.message || "Gagal mengganti rute", "danger")
                  }
                }}
                className={cx(
                  "flex items-center justify-between rounded-control px-2.5 py-2 text-left transition cursor-pointer border",
                  details?.activeRoute === "auto"
                    ? "border-brand bg-brand/10 text-ink"
                    : "border-line bg-surface-sunken/60 hover:bg-surface-sunken text-ink-soft",
                )}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Zap className="size-3.5 text-brand shrink-0" />
                  <div className="flex flex-col min-w-0">
                    <span className="text-micro font-bold text-ink">{t("route_mode_auto", "Otomatis (Rute Tercepat)")}</span>
                    <span className="text-micro text-ink-subtle truncate">{t("route_mode_auto_desc", "Beralih dinamis ke jalur tercepat")}</span>
                  </div>
                </div>
                {details?.activeRoute === "auto" && <Check className="size-3.5 text-brand shrink-0" />}
              </button>

              {/* Entri 2..N: Specific Routes */}
              {(details?.routes || []).map((route) => {
                const meta = classifyRoute(route)
                const isSelected = details?.activeRoute === route.id
                const masked = isRouteMasked(route.id)
                const displayUrl = masked ? maskUrl(route.url) : route.url

                return (
                  <div
                    key={route.id}
                    onClick={async () => {
                      setShowRouteMenu(false)
                      try {
                        await runWithTransition(
                          t("switching_route_title", "Beralih Rute..."),
                          t("switching_route_desc", "Menghubungkan ke jalur akses server..."),
                          async () => {
                            const updated = await api.switchRoute(route.id)
                            setDetails(updated)
                            notify(t("route_switched_notice", "Rute dialihkan ke: ") + meta.label, "info")
                            window.dispatchEvent(new CustomEvent("myserver:refresh"))
                            return updated
                          }
                        )
                      } catch (err: any) {
                        notify(err?.message || "Gagal mengganti rute", "danger")
                      }
                    }}
                    className={cx(
                      "flex flex-col gap-1 rounded-control p-2 text-left transition cursor-pointer border",
                      isSelected
                        ? "border-brand bg-brand/10"
                        : "border-line bg-surface-sunken/60 hover:bg-surface-sunken",
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <meta.icon className="size-3 text-info shrink-0" />
                        <span className="text-micro font-bold text-ink">{meta.label}</span>
                        {route.name && route.name !== meta.label && (
                          <span className="text-micro text-ink-muted truncate">({route.name})</span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {route.pingMs !== undefined && route.pingMs !== null && (
                          <span className="text-micro font-mono text-ink-muted">{route.pingMs}ms</span>
                        )}
                        {isSelected && <Check className="size-3.5 text-brand shrink-0" />}
                      </div>
                    </div>
                    {/* URL Row with Eye Toggle (Default Masked) */}
                    <div className="flex items-center justify-between text-micro font-mono text-ink-subtle">
                      <span className="truncate">{displayUrl}</span>
                      <button
                        type="button"
                        onClick={(e) => toggleRouteMask(route.id, e)}
                        className="rounded p-0.5 text-ink-muted hover:text-ink transition cursor-pointer ml-1 shrink-0"
                        title={masked ? "Tampilkan URL" : "Sembunyikan URL"}
                      >
                        {masked ? <Eye className="size-3" /> : <EyeOff className="size-3" />}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Modal Bottom Actions */}
            <div className="flex items-center justify-between border-t border-line pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowRouteMenu(false)
                  go("server")
                }}
                className="inline-flex items-center gap-1 text-micro font-semibold text-info hover:underline cursor-pointer"
              >
                <Plus className="size-3" />
                {t("add_route_btn", "+ Tambah Rute")}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowRouteMenu(false)
                  go("server")
                }}
                className="text-micro text-ink-subtle hover:text-ink transition cursor-pointer"
              >
                {t("manage_network_link", "Kelola Jaringan →")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* QUICK ACCESS ACCOUNT SWITCHER MODAL */}
      {showAccountMenu && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-3 backdrop-blur-xs"
          onClick={() => setShowAccountMenu(false)}
        >
          <div
            className="flex w-full max-w-[280px] flex-col gap-2.5 rounded-card border border-line bg-surface p-3.5 shadow-panel motion-safe:animate-flyout-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-line pb-2">
              <span className="flex items-center gap-1.5 text-label font-bold text-ink">
                <User className="size-4 text-info" />
                {t("switch_account_title", "Ganti Akun Server")}
              </span>
              <button
                type="button"
                onClick={() => setShowAccountMenu(false)}
                className="rounded p-1 text-ink-subtle hover:bg-surface-sunken hover:text-ink transition cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Current Account Card */}
            <div className="flex items-center justify-between rounded-tile border border-line bg-surface-sunken p-2 text-caption">
              <div className="flex items-center gap-2 min-w-0">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-info-soft text-info">
                  <User className="size-3.5" />
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="text-micro font-bold text-ink truncate">{details?.activeProfile || details?.profiles?.[0] || t("user_profile_default")}</span>
                  <span className="text-micro text-ink-subtle">
                    {details?.isAdmin ? t("role_admin", "Administrator") : t("role_standard", "Standard User")}
                  </span>
                </div>
              </div>
              <span className="rounded bg-success-soft px-1.5 py-0.5 text-micro font-semibold text-success-ink shrink-0">
                {t("account_active", "Active")}
              </span>
            </div>

            {/* Profiles List */}
            <div className="flex flex-col gap-1 max-h-36 overflow-y-auto">
              <span className="text-micro font-semibold text-ink-subtle">{t("select_other_account", "Pilih Akun Lain:")}</span>
              {details?.profiles && details.profiles.length > 0 ? (
                details.profiles.map((p) => {
                  const isCurrent = details.activeProfile === p
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => onSwitchProfileQuick(p)}
                      className={cx(
                        "flex items-center justify-between rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer text-left",
                        isCurrent
                          ? "bg-info-soft text-info font-semibold"
                          : "bg-surface-sunken/60 text-ink hover:bg-surface-sunken"
                      )}
                    >
                      <span className="truncate">{p}</span>
                      {isCurrent && <Check className="size-3.5 text-info shrink-0" />}
                    </button>
                  )
                })
              ) : (
                <div className="py-2 text-center text-micro text-ink-muted">Belum ada akun lain tersimpan.</div>
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between border-t border-line pt-2">
              <button
                type="button"
                onClick={onAddProfileQuick}
                className="inline-flex items-center gap-1 text-micro font-semibold text-info hover:underline cursor-pointer"
              >
                <Plus className="size-3" />
                + Tambah Akun
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowAccountMenu(false)
                  go("server")
                }}
                className="text-micro text-ink-subtle hover:text-ink transition cursor-pointer"
              >
                Kelola Server →
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

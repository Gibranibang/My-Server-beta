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
import HeaderLogo from "../HeaderLogo"
import SkeuoMatrixGrid from "../SkeuoMatrixGrid"
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
  const classifyRoute = (r?: { name?: string; url?: string; isZeroTier?: boolean; isEasyTier?: boolean; isRemoteDynamic?: boolean }) => {
    const name = (r?.name || "").toLowerCase()
    const url = (r?.url || "").toLowerCase()
    // Prioritaskan klasifikasi Remote (ZeroTier / EasyTier / Virtual P2P) terlebih dahulu
    const isRemote =
      Boolean(r?.isZeroTier) ||
      Boolean(r?.isEasyTier) ||
      Boolean(r?.isRemoteDynamic) ||
      url.includes("172.24.") ||
      url.includes("172.25.") ||
      url.includes("10.147.") ||
      url.includes("10.126.126.") ||
      name.includes("remote") ||
      name.includes("zerotier") ||
      name.includes("easytier") ||
      name.includes("p2p")
    if (isRemote) {
      return { type: "Remote" as const, label: "Remote", icon: Wifi, descKey: "route_remote_desc" }
    }
    const isLan =
      url.includes("192.168.") ||
      (url.includes("10.") && !url.includes("10.126.126.")) ||
      url.includes(".local") ||
      url.includes("127.0.0.1") ||
      url.includes("localhost") ||
      /172\.(1[6-9]|2[0-9]|3[0-1])\./.test(url) ||
      name.includes("lan") ||
      name.includes("lokal")
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
  const maskUrl = (_url: string) => "••••"

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
      <div className="flex flex-col items-center px-[16px] pt-0 pb-0 w-full overflow-hidden">
        {/* Cold-Start Header Skeleton */}
        <div className="flex h-[33.59px] w-[252px] shrink-0 items-center justify-between pr-0.5">
          <div className="h-6 w-28 rounded bg-surface-sunken animate-pulse" />
          <div className="h-3 w-10 rounded bg-surface-sunken animate-pulse" />
        </div>
        <div className="h-[10px] shrink-0" aria-hidden />
        {/* Cold-Start 4 Feature Cards Grid Skeleton */}
        <div className="w-[252px] h-[225.5px] mx-auto grid grid-cols-2 gap-x-[8px] gap-y-[5.5px]">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="w-[122px] h-[110px] flex flex-col justify-between rounded-[8px] border border-line bg-surface p-2.5"
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
        <div className="h-[9.18px] shrink-0" aria-hidden />
        {/* Cold-Start Footer Card Skeleton — Selaras dengan skeleton card lain (border-line, bg-surface, bg-surface-sunken) */}
        <div className="w-[252px] h-[70px] mx-auto rounded-[10px] border border-line bg-surface px-[7px] pt-[6.5px] pb-[6px] flex flex-col justify-between shrink-0 select-none shadow-card">
          {/* Row 1: Server Name LCD & Status Pill */}
          <div className="flex items-center justify-between w-full h-[21px] shrink-0">
            <div className="h-[20px] w-[171px] rounded-[4px] bg-surface-sunken animate-pulse" />
            <div className="h-[20px] w-[55px] rounded-[4px] bg-surface-sunken animate-pulse" />
          </div>
          {/* Row 2: Route / Account Chips & Notification Pill */}
          <div className="flex items-center justify-between w-full h-[24px] shrink-0">
            <div className="flex items-center gap-[6px]">
              <div className="h-[20px] w-[64px] rounded-full bg-surface-sunken animate-pulse" />
              <div className="h-[20px] w-[68px] rounded-full bg-surface-sunken animate-pulse" />
            </div>
            <div className="h-[24px] w-[56px] rounded-full bg-surface-sunken animate-pulse" />
          </div>
        </div>
      </div>
    )
  }

  const serverName = details?.serverName || t("server_default")
  const activeRouteObj = details?.routes?.find((r) => r.active)
  const currentRouteMeta = classifyRoute(activeRouteObj || { url: details?.activeHost })

  return (
    <>
      <div className="flex flex-col items-center px-[16px] pt-0 pb-0 w-full select-none">
        {/* 1:1 Official Figma div.flex.svg Header Lockup with dynamic V{APP_VERSION} */}
        <HeaderLogo isOnline={isOnline} />
        <div className="h-[10px] shrink-0" aria-hidden />
        <SkeuoMatrixGrid
          isOnline={isOnline}
          go={go}
          onOpenExplorer={() => {
            api.openFileManager()
            notify("Membuka Windows File Explorer...", "info")
          }}
          safeT={safeT}
        />
        <div className="h-[9.19px] shrink-0" aria-hidden />

        <FooterStatus
        title={
          <div className="flex items-center justify-between w-full">
            <span className="truncate">{serverName}</span>
            <ChevronRight className={cx("size-3.5 shrink-0 ml-1", isOnline ? "text-[#7BC504]" : "text-[#E60004]")} />
          </div>
        }
        onClick={() => go("server")}
        chips={
          <>
            <button
              type="button"
              onClick={() => {
                setShowRouteMenu((prev) => !prev)
                setShowAccountMenu(false)
              }}
              style={{
                boxShadow: isOnline 
                  ? "0px 4px 6px 0px rgba(80,130,0,0.20), inset 4px 4px 8px 0px rgba(50,81,2,0.30)"
                  : "0px 4px 6px 0px rgba(230,0,4,0.20), inset 4px 4px 8px 0px rgba(180,0,3,0.30)",
              }}
              className="h-[20.16px] shrink-0 justify-center rounded-full bg-white border border-[#DDD] px-[6.39px] flex items-center gap-[3.36px] cursor-pointer hover:bg-slate-50 transition outline-none relative select-none"
              title={t("switch_route_title", "Ganti Rute Akses")}
            >
              <Globe className={cx("size-[10.07px] shrink-0", isOnline ? "text-[#047857]" : "text-[#E60004]")} strokeWidth={1.8} />
              <span className={cx("text-[8.4px] font-semibold leading-[11.76px] whitespace-nowrap", isOnline ? "text-[#047857]" : "text-[#E60004]")}>
                {currentRouteMeta.label}
              </span>
              <ChevronDown className="size-[10.07px] text-[#475569] shrink-0" strokeWidth={1.8} />
            </button>
            <button
              type="button"
              onClick={() => {
                setShowAccountMenu((prev) => !prev)
                setShowRouteMenu(false)
              }}
              style={{
                boxShadow: "0px 4px 6px 0px rgba(0,52,101,0.15), inset 4px 4px 8px 0px rgba(3,38,138,0.30)",
              }}
              className="h-[20px] w-auto shrink-0 justify-center rounded-full bg-white border border-[#DDD] px-[6.39px] flex items-center gap-[3.36px] cursor-pointer hover:bg-slate-50 transition outline-none relative select-none"
              title={t("switch_account_title", "Ganti Akun")}
            >
              <User className="size-[10.07px] text-[#1D4ED8] shrink-0" strokeWidth={1.8} />
              <span className="text-[8.4px] font-semibold text-[#1D4ED8] leading-[11.76px] whitespace-nowrap">
                {details?.activeProfile || details?.profiles?.[0] || "–"}
              </span>
              <ChevronDown className="size-[10.07px] text-[#2563EB] shrink-0" strokeWidth={1.8} />
            </button>
          </>
        }
      />
      </div>

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

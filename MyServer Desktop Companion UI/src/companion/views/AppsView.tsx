import { getTranslation } from "../i18n"
import { APP_VERSION, APP_CHANNEL } from "../version"
import { useState, useMemo, useEffect, useRef } from "react"
import {
  Boxes,
  Clapperboard,
  Cloud,
  Copy,
  ExternalLink,
  Globe,
  HardDrive,
  MoreVertical,
  Play,
  Plus,
  RefreshCw,
  Shield,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react"
import { FooterStatus, TrayChip } from "../FlyoutShell"
import { SERVER_IP, SERVER_URL, useCompanion, useNotice } from "../store"
import { Button, Card, Chip, IconBadge, Mono, StatusDot, cx } from "../ui"
import { ViewBody } from "./shared"
import type { WebApp } from "../types"

function isPrivateOrLocalHost(hostname: string): boolean {
  const h = hostname.toLowerCase().trim()
  if (!h || h === "localhost" || h === "127.0.0.1" || h === "::1" || h.endsWith(".local") || h.endsWith(".lan")) {
    return true
  }
  if (/^10\./.test(h) || /^192\.168\./.test(h) || /^172\.(1[6-9]|2[0-9]|3[0-1])\./.test(h) || /^100\.(6[4-9]|[7-9][0-9]|1[0-1][0-9]|12[0-7])\./.test(h)) {
    return true
  }
  return false
}

export function resolveWebAppIconCandidates(rawUrl?: string, explicitIcon?: string): string[] {
  const candidates: string[] = []
  if (explicitIcon && explicitIcon.trim()) {
    candidates.push(explicitIcon.trim())
  }
  const clean = (rawUrl || "").trim()
  if (!clean) return candidates
  try {
    const withProto = /^https?:\/\//i.test(clean) ? clean : `https://${clean}`
    const parsed = new URL(withProto)
    const originFavicon = `${parsed.origin}/favicon.ico`
    if (!candidates.includes(originFavicon)) {
      candidates.push(originFavicon)
    }
    if (parsed.hostname && !isPrivateOrLocalHost(parsed.hostname)) {
      const gFavicon = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(parsed.hostname)}&sz=64`
      const ddgFavicon = `https://icons.duckduckgo.com/ip3/${encodeURIComponent(parsed.hostname)}.ico`
      if (!candidates.includes(gFavicon)) candidates.push(gFavicon)
      if (!candidates.includes(ddgFavicon)) candidates.push(ddgFavicon)
    }
  } catch {
    // ignore invalid URL while typing
  }
  return candidates
}

function getAppFallbackVisuals(name: string): {
  icon: LucideIcon
  tone: "info" | "warning" | "violet" | "success"
} {
  const lower = name.toLowerCase()
  if (
    lower.includes("cloud") ||
    lower.includes("drive") ||
    lower.includes("nextcloud") ||
    lower.includes("owncloud")
  ) {
    return { icon: Cloud, tone: "info" }
  }
  if (
    lower.includes("plex") ||
    lower.includes("media") ||
    lower.includes("video") ||
    lower.includes("youtube")
  ) {
    return { icon: Play, tone: "warning" }
  }
  if (
    lower.includes("jellyfin") ||
    lower.includes("cinema") ||
    lower.includes("tv") ||
    lower.includes("stream") ||
    lower.includes("emby")
  ) {
    return { icon: Clapperboard, tone: "violet" }
  }
  if (
    lower.includes("guard") ||
    lower.includes("shield") ||
    lower.includes("pihole") ||
    lower.includes("dns") ||
    lower.includes("vpn") ||
    lower.includes("adguard")
  ) {
    return { icon: Shield, tone: "success" }
  }
  if (lower.includes("sync") || lower.includes("backup")) {
    return { icon: RefreshCw, tone: "info" }
  }
  if (
    lower.includes("disk") ||
    lower.includes("smb") ||
    lower.includes("samba") ||
    lower.includes("storage")
  ) {
    return { icon: HardDrive, tone: "info" }
  }
  return { icon: Globe, tone: "info" }
}

export default function AppsView() {
  const {
    isOnline,
    webApps,
    serverUrl,
    refreshWebApps,
    addWebApp,
    deleteWebApp,
    openUrl,
    openExternalBrowser,
    settings,
  } = useCompanion()
  const t = getTranslation(settings?.language)
  const { notify } = useNotice()

  const [filter, setFilter] = useState<"all" | "active" | "zima" | "custom">(() =>
    typeof window !== "undefined" && window.location.search.includes("apps_tab=custom")
      ? "custom"
      : "all",
  )
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)

  useEffect(() => {
    void refreshWebApps()
  }, [refreshWebApps])
  const menuRef = useRef<HTMLDivElement | null>(null)
  const [isAdding, setIsAdding] = useState(false)
  const [name, setName] = useState("")
  const [url, setUrl] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [failedIconIdx, setFailedIconIdx] = useState<Record<string, number>>({})

  const safeWebApps = useMemo(() => (Array.isArray(webApps) ? webApps : []), [webApps])

  // Hitung jumlah kategori
  const activeCount = useMemo(
    () => safeWebApps.filter((a) => a.status === "running" || (!a.is_zima_container && isOnline)).length,
    [safeWebApps, isOnline],
  )
  const zimaCount = useMemo(
    () => safeWebApps.filter((a) => a.is_zima_container).length,
    [safeWebApps],
  )
  const customCount = useMemo(
    () => safeWebApps.filter((a) => !a.is_zima_container).length,
    [safeWebApps],
  )

  // Filter daftar aplikasi
  const filteredApps = useMemo(() => {
    if (filter === "active") {
      return safeWebApps.filter((a) => a.status === "running" || (!a.is_zima_container && isOnline))
    }
    if (filter === "zima") {
      return safeWebApps.filter((a) => a.is_zima_container)
    }
    if (filter === "custom") {
      return safeWebApps.filter((a) => !a.is_zima_container)
    }
    return safeWebApps
  }, [safeWebApps, filter, isOnline])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmedName = name.trim()
    const trimmedUrl = url.trim()
    if (!trimmedName || !trimmedUrl) {
      notify("Nama dan URL Web App tidak boleh kosong.", "danger")
      return
    }
    setIsSubmitting(true)
    try {
      await addWebApp(trimmedName, trimmedUrl)
      notify(`Web App '${trimmedName}' berhasil disimpan.`, "success")
      setName("")
      setUrl("")
      setIsAdding(false)
    } catch {
      notify("Gagal menyimpan Web App baru.", "danger")
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (app: WebApp) => {
    setDeletingId(app.id)
    try {
      await deleteWebApp(app.id)
      notify(`Web App '${app.name}' berhasil dihapus.`, "info")
    } catch {
      notify("Gagal menghapus Web App.", "danger")
    } finally {
      setDeletingId(null)
    }
  }

  const handleOpen = (targetUrl: string, appName: string) => {
    if (!targetUrl) {
      notify(`URL untuk ${appName} belum tersedia.`, "warning")
      return
    }
    void openUrl(targetUrl, `${appName} - [MyServer v${APP_VERSION} ${APP_CHANNEL}]`).catch((_err: any) => {
      void openExternalBrowser(targetUrl)
      notify(`Membuka ${appName} di peramban web...`, "info")
    })
    notify(`Membuka ${appName}...`, "info")
  }

  useEffect(() => {
    if (!menuOpenId) return
    const onMouseDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null)
      }
    }
    document.addEventListener("mousedown", onMouseDown)
    return () => document.removeEventListener("mousedown", onMouseDown)
  }, [menuOpenId])

  const handleCopyUrl = async (targetUrl: string, appName: string) => {
    if (!targetUrl) {
      notify(`URL untuk ${appName} belum tersedia.`, "warning")
      return
    }
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(targetUrl)
      } else {
        const textArea = document.createElement("textarea")
        textArea.value = targetUrl
        document.body.appendChild(textArea)
        textArea.select()
        document.execCommand("copy")
        document.body.removeChild(textArea)
      }
      notify(`URL ${appName} disalin ke clipboard!`, "success")
    } catch {
      notify(`Gagal menyalin URL ${appName}.`, "danger")
    }
  }

  const handleOpenExternal = (targetUrl: string, appName: string) => {
    if (!targetUrl) {
      notify(`URL untuk ${appName} belum tersedia.`, "warning")
      return
    }
    void openExternalBrowser(targetUrl)
    notify(`Membuka ${appName} di browser default…`, "info")
  }

  return (
    <>
      <ViewBody>
        {/* Header Bar */}
        <div className="flex items-center justify-between pl-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-[10px] font-bold tracking-wider text-ink-muted uppercase truncate">
              {t("apps_section_title", "SERVICES & CONTAINERS")}
            </span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={() => setIsAdding(!isAdding)}
              className="h-[23px] px-2.5 flex items-center gap-1 rounded-full bg-info-ink/15 hover:bg-info-ink/25 text-info-ink text-[10.5px] font-semibold transition cursor-pointer select-none"
            >
              {isAdding ? <X className="size-3" /> : <Plus className="size-3" />}
              <span>{isAdding ? t("close_btn", "Close") : t("add_app_btn", "Add App")}</span>
            </button>
          </div>
        </div>

        {/* Filter Bar Chips */}
        {safeWebApps.length > 0 && !isAdding && (
          <div className="flex items-center gap-1 overflow-x-auto pb-1 text-micro scrollbar-none">
            <button
              type="button"
              onClick={() => setFilter("all")}
              className={cx(
                "rounded-full px-2.5 py-0.5 font-medium transition cursor-pointer",
                filter === "all"
                  ? "bg-ink text-surface font-semibold shadow-xs"
                  : "bg-surface text-ink-subtle hover:text-ink",
              )}
            >
              {t("filter_all", "Semua")} ({webApps.length})
            </button>
            <button
              type="button"
              onClick={() => setFilter("active")}
              className={cx(
                "rounded-full px-2.5 py-0.5 font-medium transition cursor-pointer",
                filter === "active"
                  ? "bg-success-ink text-white font-semibold shadow-xs"
                  : "bg-surface text-ink-subtle hover:text-ink",
              )}
            >
              {t("filter_active", "Aktif")} ({activeCount})
            </button>
            {zimaCount > 0 && (
              <button
                type="button"
                onClick={() => setFilter("zima")}
                className={cx(
                  "rounded-full px-2.5 py-0.5 font-medium transition cursor-pointer",
                  filter === "zima"
                    ? "bg-info-ink text-white font-semibold shadow-xs"
                    : "bg-surface text-ink-subtle hover:text-ink",
                )}
              >
                ZimaOS ({zimaCount})
              </button>
            )}
            {customCount > 0 && (
              <button
                type="button"
                onClick={() => setFilter("custom")}
                className={cx(
                  "rounded-full px-2.5 py-0.5 font-medium transition cursor-pointer",
                  filter === "custom"
                    ? "bg-violet-600 text-white font-semibold shadow-xs"
                    : "bg-surface text-ink-subtle hover:text-ink",
                )}
              >
                {t("filter_custom", "Kustom")} ({customCount})
              </button>
            )}
          </div>
        )}

        {/* Inline Drawer Form Tambah Web App */}
        {isAdding && (
          <Card className="flex flex-col gap-2.5 border-dashed border-info-ink/30 bg-info-ink/5 p-3 animate-in fade-in duration-200">
            <div className="flex items-center justify-between">
              <span className="text-micro font-bold uppercase tracking-wider text-info-ink">{t("add_custom_app_title", "Add Custom Web App")}</span>
              <button
                type="button"
                className="text-ink-subtle hover:text-ink cursor-pointer"
                onClick={() => setIsAdding(false)}
                aria-label={t("close_form_aria", "Close form")}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="flex flex-col gap-2">
              <div>
                <label className="block text-nano font-semibold text-ink-subtle mb-1">{t("app_name_label", "Application Name")}</label>
                <input
                  type="text"
                  placeholder={t("app_name_ph", "e.g. Jellyfin, Portainer, Nextcloud")}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-md border border-ink-subtle/20 bg-surface-sunken px-2.5 py-1 text-micro text-ink placeholder:text-ink-faint focus:border-info-ink focus:outline-none"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-nano font-semibold text-ink-subtle mb-1">{t("app_url_label", "Web App URL / Domain")}</label>
                <input
                  type="text"
                  placeholder={t("app_url_ph", "e.g. http://192.168.1.100:8096")}
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  className="w-full rounded-md border border-ink-subtle/20 bg-surface-sunken px-2.5 py-1 text-micro text-ink placeholder:text-ink-faint focus:border-info-ink focus:outline-none"
                />
              </div>
              <div className="mt-1 flex items-center justify-end gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  type="button"
                  onClick={() => setIsAdding(false)}
                >{t("cancel_btn", "Cancel")}</Button>
                <Button
                  size="sm"
                  variant="info"
                  type="submit"
                  disabled={isSubmitting || !name.trim() || !url.trim()}
                >
                  {isSubmitting ? t("saving_app_busy", "Saving…") : t("save_app_btn", "Save App")}
                </Button>
              </div>
            </form>
          </Card>
        )}

        {/* State Kosong */}
        {!isAdding && filteredApps.length === 0 && (
          <Card className="flex flex-col items-center justify-center py-6 px-4 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-ink-subtle/10 text-ink-muted">
              <Boxes className="h-5 w-5" />
            </div>
            <div className="mt-2.5 text-body font-semibold text-ink">
              {filter === "all" ? t("no_apps_found_title", "No Applications Found") : t("no_apps_found_filter_title", "No Applications in this Filter")}
            </div>
            <p className="mt-1 max-w-[240px] text-micro text-ink-subtle">
              {filter === "all"
                ? t("no_apps_found_desc", "Ensure ZimaOS is online or add custom web application bookmarks.")
                : t("no_apps_found_filter_desc", "Try selecting another filter to view available applications.")}
            </p>
            <div className="mt-3.5 flex gap-2">
              <Button
                size="sm"
                variant="info"
                icon={Plus}
                onClick={() => setIsAdding(true)}
              >{t("add_web_app_btn", "Add Web App")}</Button>
            </div>
          </Card>
        )}

        {/* Grid Daftar Web Apps Dinamis & Kontainer ZimaOS */}
        {filteredApps.length > 0 && (
          <ul className="grid grid-cols-2 gap-2.5">
            {filteredApps.map((app) => {
              const fallback = getAppFallbackVisuals(app.name)
              const isDeleting = deletingId === app.id
              const iconCandidates = resolveWebAppIconCandidates(app.url, app.icon)
              const currentCandidateIdx = failedIconIdx[app.id] ?? 0
              const activeIconUrl = iconCandidates[currentCandidateIdx] || ""
              const hasCustomIcon = Boolean(activeIconUrl)

              // Status penentuan (Running vs Exited vs Custom)
              const isRunning =
                app.status === "running" || (!app.is_zima_container && isOnline)
              const isExited = app.status === "exited"

              return (
                <li key={app.id}>
                  <Card className="group relative flex flex-col justify-between p-2.5 min-h-[112px]">
                    <div>
                      <div className="flex items-start justify-between gap-1.5">
                        {hasCustomIcon ? (
                          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface/80 p-0.5 border border-ink-subtle/15 shrink-0">
                            <img
                              src={activeIconUrl}
                              alt={app.name}
                              className="h-full w-full object-contain rounded-xs"
                              onError={() =>
                                setFailedIconIdx((prev) => ({
                                  ...prev,
                                  [app.id]: (prev[app.id] ?? 0) + 1,
                                }))
                              }
                            />
                          </div>
                        ) : (
                          <div className="shrink-0 scale-90 origin-top-left">
                            <IconBadge icon={fallback.icon} tone={fallback.tone} size="sm" />
                          </div>
                        )}

                        <span
                          className={cx(
                            "inline-flex items-center gap-1 text-[9px] font-semibold shrink-0 pt-0.5",
                            isRunning
                              ? "text-success-ink"
                              : isExited
                                ? "text-ink-subtle"
                                : "text-info-ink",
                          )}
                        >
                          <StatusDot
                            tone={isRunning ? "success" : isExited ? "neutral" : "info"}
                            pulse={isRunning}
                          />
                          {isRunning ? "Active" : isExited ? "Stopped" : "Web"}
                        </span>
                      </div>

                      <div className="mt-1.5 truncate text-[12px] font-semibold leading-tight text-ink" title={app.name}>
                        {app.name}
                      </div>

                      <div className="truncate text-[9.5px] text-ink-subtle mt-0.5">
                        {app.port ? (
                          <>
                            Port <Mono className="text-ink-muted font-medium">{app.port}</Mono>
                          </>
                        ) : (
                          <span className="truncate opacity-80" title={app.url}>
                            {app.url ? app.url.replace(/^https?:\/\//, "") : "Web Service"}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Auto-Layout Action Panel (Inline & Zero Clipping) */}
                    {menuOpenId === app.id ? (
                      <div
                        ref={menuRef}
                        className="mt-2 flex flex-col gap-1 rounded-xl border border-ink-subtle/20 bg-surface/90 p-1.5 shadow-sm animate-in fade-in duration-150"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex items-center justify-between px-1.5 py-0.5 border-b border-ink-subtle/10 mb-0.5">
                          <span className="text-nano font-bold uppercase tracking-wider text-ink-subtle truncate">
                            {t("options_for", "Options for")} {app.name}
                          </span>
                          <button
                            type="button"
                            onClick={() => setMenuOpenId(null)}
                            className="rounded p-0.5 text-ink-subtle hover:text-ink transition cursor-pointer"
                            aria-label={t("close_options_menu", "Close options menu")}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>

                        <button
                          type="button"
                          onClick={() => {
                            setMenuOpenId(null)
                            handleOpenExternal(app.url, app.name)
                          }}
                          className="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-micro font-medium text-ink hover:bg-surface transition cursor-pointer text-left"
                        >
                          <Globe className="h-3 w-3 text-info-ink shrink-0" />
                          <span className="truncate">{t("open_in_browser_action", "External Browser")}</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            setMenuOpenId(null)
                            handleCopyUrl(app.url, app.name)
                          }}
                          className="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-micro font-medium text-ink hover:bg-surface transition cursor-pointer text-left"
                        >
                          <Copy className="h-3 w-3 text-ink-muted shrink-0" />
                          <span className="truncate">{t("copy_url_action", "Copy URL")}</span>
                        </button>

                        {!app.is_zima_container && (
                          <button
                            type="button"
                            onClick={() => {
                              setMenuOpenId(null)
                              handleDelete(app)
                            }}
                            className="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-micro font-medium text-danger-ink hover:bg-danger-ink/10 transition cursor-pointer text-left border-t border-ink-subtle/10 pt-1"
                          >
                            <Trash2 className="h-3 w-3 shrink-0" />
                            <span className="truncate">{t("delete_app_action", "Delete App")}</span>
                          </button>
                        )}
                      </div>
                    ) : (
                      <div className="mt-2.5 flex items-center gap-1">
                        <button
                          type="button"
                          disabled={isDeleting}
                          aria-label={`${t("open_window_for", "Open window for")} ${app.name}`}
                          title={t("open_independent_window", "Open in independent MyServer window")}
                          onClick={() => handleOpen(app.url, app.name)}
                          className="flex-1 h-[23px] rounded-md px-2 flex items-center justify-center gap-1 bg-surface-sunken hover:bg-line border border-line text-[10.5px] font-semibold text-ink transition cursor-pointer select-none active:scale-[0.98]"
                        >
                          <ExternalLink className="size-3 text-ink-muted shrink-0" />
                          <span className="truncate">{t("open_btn", "Open")}</span>
                        </button>

                        <button
                          type="button"
                          aria-label={`${t("more_options_for", "More options for")} ${app.name}`}
                          title={t("more_options_title", "More options")}
                          onClick={(e) => {
                            e.stopPropagation()
                            setMenuOpenId(app.id)
                          }}
                          className="size-[23px] shrink-0 rounded-md flex items-center justify-center bg-surface-sunken hover:bg-line border border-line text-ink-subtle hover:text-ink transition cursor-pointer"
                        >
                          <MoreVertical className="size-3" />
                        </button>
                      </div>
                    )}
                  </Card>
                </li>
              )
            })}
          </ul>
        )}
      </ViewBody>

      <FooterStatus
        showNoticePill={false}
        title="ZimaOS Docker"
        chips={
          <>
            <TrayChip tone={activeCount > 0 ? "success" : "neutral"} icon={Boxes}>
              {activeCount} {t("filter_active", "Aktif")} / {safeWebApps.length} {t("total_label", "Total")}
            </TrayChip>
            <TrayChip tone={isOnline ? "success" : "neutral"}>
              Engine: {isOnline ? "Online" : "Offline"}
            </TrayChip>
          </>
        }
      />
    </>
  )
}

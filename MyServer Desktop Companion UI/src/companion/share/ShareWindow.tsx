import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react"
import {
  Check,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  FileText,
  Folder,
  Link2,
  LoaderCircle,
  Lock,
  Trash2,
  X,
} from "lucide-react"
import { getCompanionApi } from "../api"
import { assets } from "../assets"
import { getTranslation, type Language } from "../i18n"
import type { PublicShareItem, ShareErrorCode, ShareTargetInfo } from "../types"
import { Button, Chip, IconBadge, Mono, SectionLabel, StatusDot, TextAction, cx } from "../ui"
import { QrCodeSvg } from "./QrCodeSvg"

export interface ShareWindowProps {
  initialTarget?: ShareTargetInfo | null
}

type ExpiryMode = "unlimited" | "1h" | "24h" | "168h" | "custom"

type ShareToast = {
  text: string
  tone: "info" | "success" | "error" | "warning"
} | null

function backdropFor(theme: "dark" | "light", isOffline: boolean): string {
  if (theme === "light") return isOffline ? assets.flyoutBgLightOffline : assets.flyoutBgLight
  return isOffline ? assets.flyoutBgDarkOffline : assets.flyoutBgDark
}

function isValidHttpUrl(raw: string): boolean {
  const trimmed = raw.trim()
  if (!trimmed) return true
  if (!/^https?:\/\/\S+$/i.test(trimmed)) return false
  try {
    const parsed = new URL(trimmed)
    return parsed.protocol === "http:" || parsed.protocol === "https:"
  } catch {
    return false
  }
}

function isValidCustomHours(raw: string): boolean {
  const trimmed = raw.trim()
  if (!/^\d+$/.test(trimmed)) return false
  const n = Number(trimmed)
  return Number.isInteger(n) && n >= 1 && n <= 8760
}

function formatExpiryLabel(expiresAt: string, language: Language): string {
  const ms = Date.parse(expiresAt)
  if (!Number.isFinite(ms)) return expiresAt
  const diffMs = Math.max(0, ms - Date.now())
  const hours = diffMs / 3600000
  if (hours < 48) {
    const rounded = Math.max(1, Math.round(hours))
    return language === "id" ? `${rounded} jam` : `${rounded}h`
  }
  const days = Math.max(1, Math.round(hours / 24))
  return language === "id" ? `${days} hari` : `${days}d`
}

function mapShareErrorMessage(
  code: ShareErrorCode | string | undefined,
  fallback: string | undefined,
  t: (key: string, fallbackText?: string) => string,
): string {
  switch (code) {
    case "LOCAL_DRIVE":
      return t("share_err_local_drive")
    case "FOREIGN_NAS":
      return t("share_err_foreign_nas")
    case "SHARE_NOT_MOUNTED_IN_BACKEND":
      return t("share_err_unmounted")
    case "MULTI_ITEM_DROP":
      return t("share_err_multi_item")
    case "SERVER_OFFLINE":
    case "BACKEND_OFFLINE":
      return t("share_err_offline")
    case "UNAUTHENTICATED_SESSION":
      return t("share_err_unauthenticated")
    case "FORBIDDEN_PATH":
      return t("share_err_forbidden")
    case "INVALID_PATH":
      return t("share_err_invalid_path")
    default:
      return fallback && fallback.trim() ? fallback : t("share_active_fetch_error")
  }
}

export function ShareWindow({ initialTarget }: ShareWindowProps = {}) {
  const [theme, setTheme] = useState<"dark" | "light">("dark")
  const [language, setLanguage] = useState<Language>("en")
  const [isOnline, setIsOnline] = useState<boolean>(true)
  const [target, setTarget] = useState<ShareTargetInfo | null>(initialTarget ?? null)
  const [targetLoading, setTargetLoading] = useState<boolean>(!initialTarget)
  const [targetError, setTargetError] = useState<string | null>(null)

  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [expiryMode, setExpiryMode] = useState<ExpiryMode>("unlimited")
  const [customHours, setCustomHours] = useState("48")

  const [isAdmin, setIsAdmin] = useState<boolean | null>(null)
  const [publicBaseUrl, setPublicBaseUrl] = useState("")
  const [baseUrlError, setBaseUrlError] = useState<string | null>(null)
  const [savingBaseUrl, setSavingBaseUrl] = useState(false)

  const [creating, setCreating] = useState(false)
  const [justCopied, setJustCopied] = useState(false)
  const [generatedLink, setGeneratedLink] = useState<{
    token: string
    url: string
    isLanFallback: boolean
    copied: boolean
  } | null>(null)

  const [shares, setShares] = useState<PublicShareItem[]>([])
  const [sharesLoading, setSharesLoading] = useState<boolean>(false)
  const [sharesError, setSharesError] = useState<string | null>(null)
  const [revokeConfirmToken, setRevokeConfirmToken] = useState<string | null>(null)
  const [revokingToken, setRevokingToken] = useState<string | null>(null)

  const [toast, setToast] = useState<ShareToast>(null)
  const toastTimerRef = useRef<number | null>(null)
  const copiedTimerRef = useRef<number | null>(null)
  const currentTargetRelRef = useRef<string | null>(initialTarget?.canonical_rel ?? null)

  const passwordId = useId()
  const baseUrlId = useId()
  const t = useMemo(() => getTranslation(language), [language])
  const tRef = useRef(t)
  tRef.current = t
  const fetchSeqRef = useRef(0)

  const showToast = useCallback((text: string, tone: "info" | "success" | "error" | "warning" = "info") => {
    setToast({ text, tone })
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current)
    }
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null)
      toastTimerRef.current = null
    }, 3200)
  }, [])

  useEffect(() => {
    return () => {
      if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current)
      if (copiedTimerRef.current !== null) window.clearTimeout(copiedTimerRef.current)
    }
  }, [])

  // Sync theme and language once on mount (never invokes setWizardMode or 4s telemetry polling)
  useEffect(() => {
    let active = true
    void getCompanionApi()
      .loadSettings()
      .then((s) => {
        if (!active || !s) return
        setTheme(s.theme === "light" ? "light" : "dark")
        setLanguage(s.language === "id" ? "id" : "en")
      })
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [])

  // Hydrate initial target from Tauri ShareWindowState or ?path= query param
  useEffect(() => {
    if (initialTarget) {
      currentTargetRelRef.current = initialTarget.canonical_rel
      setTarget(initialTarget)
      setTargetLoading(false)
      setTargetError(null)
      return
    }

    let active = true
    const api = getCompanionApi()

    async function hydrateTarget() {
      setTargetLoading(true)
      setTargetError(null)
      try {
        const winTarget = await api.getShareWindowTarget()
        if (!active) return
        if (winTarget && winTarget.canonical_rel) {
          currentTargetRelRef.current = winTarget.canonical_rel
          setTarget(winTarget)
          setTargetLoading(false)
          return
        }

        const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null
        const rawPath = params?.get("path")
        if (rawPath) {
          const resolved = await api.resolveSharePath(rawPath)
          if (!active) return
          if (resolved.ok && resolved.target) {
            currentTargetRelRef.current = resolved.target.canonical_rel
            setTarget(resolved.target)
            setTargetLoading(false)
            return
          }
          if (resolved.code === "SERVER_OFFLINE" || resolved.code === "BACKEND_OFFLINE") {
            setIsOnline(false)
          }
          setTargetError(mapShareErrorMessage(resolved.code, resolved.message, tRef.current))
          setTargetLoading(false)
          return
        }

        setTargetLoading(false)
      } catch (err) {
        if (!active) return
        setTargetError(err instanceof Error ? err.message : tRef.current("share_win_no_target"))
        setTargetLoading(false)
      }
    }

    void hydrateTarget()
    return () => {
      active = false
    }
  }, [initialTarget])

  const fetchShares = useCallback(
    async (activeTarget: ShareTargetInfo | null) => {
      if (!activeTarget) return
      const seq = ++fetchSeqRef.current
      setSharesLoading(true)
      setSharesError(null)
      try {
        const res = await getCompanionApi().listShares({
          serverId: activeTarget.server_id,
          targetPath: activeTarget.canonical_rel,
        })
        if (seq !== fetchSeqRef.current) return
        if (res.success) {
          setIsOnline(true)
          setShares(Array.isArray(res.shares) ? res.shares : [])
          setIsAdmin(res.is_admin === true)
          setPublicBaseUrl(typeof res.public_base_url === "string" ? res.public_base_url : "")
          setBaseUrlError(null)
        } else {
          setIsAdmin(false)
          setShares([])
          setSharesError(res.error || tRef.current("share_active_fetch_error"))
        }
      } catch (err) {
        if (seq !== fetchSeqRef.current) return
        setIsAdmin(false)
        setShares([])
        setSharesError(err instanceof Error ? err.message : tRef.current("share_active_fetch_error"))
      } finally {
        if (seq === fetchSeqRef.current) {
          setSharesLoading(false)
        }
      }
    },
    [],
  )

  useEffect(() => {
    if (!target) return
    void fetchShares(target)
  }, [target, fetchShares])

  // Re-target in-place when Tauri reuses an already-open share-window without re-centering
  useEffect(() => {
    const onShareTarget = (event: Event) => {
      const detail = (event as CustomEvent<ShareTargetInfo>).detail
      if (!detail || typeof detail !== "object" || !detail.canonical_rel) return
      const changed = currentTargetRelRef.current !== detail.canonical_rel
      currentTargetRelRef.current = detail.canonical_rel
      setTarget(detail)
      setTargetLoading(false)
      setTargetError(null)
      setRevokeConfirmToken(null)
      if (changed) {
        setGeneratedLink(null)
        setJustCopied(false)
      }
    }

    window.addEventListener("myserver:share-target", onShareTarget)
    return () => {
      window.removeEventListener("myserver:share-target", onShareTarget)
    }
  }, [])

  // Escape closes ONLY share-window
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        void getCompanionApi().closeShareWindow().catch(() => undefined)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  const handleHeaderMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    const el = e.target as HTMLElement
    if (el.closest("button, input, select, textarea, a")) return
    void getCompanionApi().startDrag().catch(() => undefined)
  }

  const isCustomExpiryValid = expiryMode !== "custom" || isValidCustomHours(customHours)

  const handleSaveBaseUrl = async () => {
    if (savingBaseUrl || isAdmin !== true) return
    const trimmed = publicBaseUrl.trim()
    if (!isValidHttpUrl(trimmed)) {
      setBaseUrlError(t("share_public_base_invalid"))
      return
    }
    setBaseUrlError(null)
    setSavingBaseUrl(true)
    try {
      const res = await getCompanionApi().updateShareSettings(trimmed, target?.server_id)
      if (res.success) {
        const saved = typeof res.public_base_url === "string" ? res.public_base_url : trimmed.replace(/\/+$/, "")
        setPublicBaseUrl(saved)
        showToast(t("share_public_base_saved"), "success")
        if (target) {
          void fetchShares(target)
        }
      } else {
        const errMsg = res.error || t("share_public_base_invalid")
        setBaseUrlError(errMsg)
        showToast(errMsg, "error")
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : t("share_public_base_invalid")
      showToast(errMsg, "error")
    } finally {
      setSavingBaseUrl(false)
    }
  }

  const handleCopyUrl = async (url: string) => {
    if (!url) return
    const ok = await getCompanionApi().copyShareClipboard(url)
    if (ok) {
      setGeneratedLink((prev) => (prev && prev.url === url ? { ...prev, copied: true } : prev))
      showToast(t("share_copied_toast"), "success")
    } else {
      showToast(t("share_copy_failed_toast"), "warning")
    }
  }

  const handleCreateShare = async (e: React.FormEvent) => {
    e.preventDefault()
    if (creating || !target || !isCustomExpiryValid) return

    let expiresInHours: number | null = null
    if (expiryMode === "1h") expiresInHours = 1
    else if (expiryMode === "24h") expiresInHours = 24
    else if (expiryMode === "168h") expiresInHours = 168
    else if (expiryMode === "custom") expiresInHours = Number.parseInt(customHours.trim(), 10)

    setCreating(true)
    try {
      const api = getCompanionApi()
      const res = await api.createShare({
        path: target.canonical_rel,
        server_id: target.server_id,
        password: password.trim() ? password : null,
        expires_in_hours: expiresInHours,
        label: target.basename,
        copy_to_clipboard: true,
      })

      const url = res.share_url || res.share?.share_url || res.share?.resolved_url || ""
      if (!res.success || !url) {
        if (res.code === "SERVER_OFFLINE" || res.code === "BACKEND_OFFLINE") {
          setIsOnline(false)
        }
        showToast(mapShareErrorMessage(res.code, res.error, t), "error")
        return
      }

      setIsOnline(true)
      let copied = res.clipboard_copied === true
      if (!copied) {
        copied = await api.copyShareClipboard(url)
      }

      const token = res.share?.token || ""
      const isLanFallback = Boolean(res.is_lan_fallback ?? res.share?.is_lan_fallback)
      setGeneratedLink({ token, url, isLanFallback, copied })

      if (res.share) {
        setShares((prev) => [res.share!, ...prev.filter((s) => s.token !== res.share!.token)])
      }

      if (copiedTimerRef.current !== null) {
        window.clearTimeout(copiedTimerRef.current)
        copiedTimerRef.current = null
      }
      if (copied) {
        setJustCopied(true)
        copiedTimerRef.current = window.setTimeout(() => {
          setJustCopied(false)
          copiedTimerRef.current = null
        }, 2000)
        showToast(t("share_copied_toast"), "success")
      } else {
        setJustCopied(false)
        showToast(t("share_copy_failed_toast"), "warning")
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : t("share_err_offline"), "error")
    } finally {
      setCreating(false)
    }
  }

  const handleConfirmRevoke = async (token: string) => {
    if (revokingToken) return
    setRevokingToken(token)
    try {
      const res = await getCompanionApi().revokeShare(token, target?.server_id)
      if (!res.success && !res.already_revoked) {
        showToast(res.error || t("share_active_fetch_error"), "error")
        return
      }
      setShares((prev) => prev.filter((s) => s.token !== token))
      setGeneratedLink((prev) => (prev && prev.token === token ? null : prev))
      setRevokeConfirmToken(null)
      showToast(t("share_revoked_toast"), "success")
    } catch (err) {
      showToast(err instanceof Error ? err.message : t("share_active_fetch_error"), "error")
    } finally {
      setRevokingToken(null)
    }
  }

  const activeItemShares = useMemo(() => {
    if (!target) return []
    const now = Date.now()
    return shares
      .filter(
        (s) =>
          !s.revoked &&
          (!s.expires_at || Date.parse(s.expires_at) > now) &&
          s.target_path === target.canonical_rel,
      )
      .sort((a, b) => {
        if (generatedLink && a.token === generatedLink.token) return -1
        if (generatedLink && b.token === generatedLink.token) return 1
        const ta = a.created_at ? Date.parse(a.created_at) : 0
        const tb = b.created_at ? Date.parse(b.created_at) : 0
        return tb - ta
      })
  }, [shares, target, generatedLink])

  const expiryOptions: Array<{ mode: ExpiryMode; label: string }> = [
    { mode: "unlimited", label: t("share_expiry_unlimited") },
    { mode: "1h", label: t("share_expiry_1h") },
    { mode: "24h", label: t("share_expiry_24h") },
    { mode: "168h", label: t("share_expiry_7d") },
    { mode: "custom", label: t("share_expiry_custom") },
  ]

  const serverDiskLabel = target ? `${target.server_name} · ${target.disk_name}` : ""

  return (
    <div
      className="wizard-win w-[400px] h-[560px] p-0 flex flex-col overflow-hidden rounded-[16px]"
      data-theme={theme}
      data-server-status={isOnline ? "online" : "offline"}
      data-testid="share-window"
      style={{
        width: 400,
        height: 560,
        padding: 0,
        backgroundImage: `url("${backdropFor(theme, !isOnline)}")`,
      }}
    >
      {/* Fixed Draggable Header */}
      <div
        className="wiz-header h-12 shrink-0 px-4 mb-0 border-b border-[var(--line)] flex items-center justify-between gap-2"
        style={{ marginBottom: 0 }}
        data-tauri-drag-region
        data-testid="share-drag-bar"
        onMouseDown={handleHeaderMouseDown}
      >
        <div className="flex items-center gap-2 min-w-0">
          <img
            src={theme === "light" ? assets.logoLightMark : assets.logoDarkMark}
            alt="MyServer"
            className="h-6 w-auto shrink-0 select-none"
            draggable={false}
          />
          <span className="bg-[var(--accent-soft)] border border-[var(--accent-border)] text-[var(--ink)] text-caption font-semibold px-2 py-1 rounded-full truncate">
            {t("share_win_title")}
          </span>
          <StatusDot tone={isOnline ? "success" : "danger"} />
        </div>
        <button
          type="button"
          className="wiz-icon-btn wiz-close size-8 shrink-0"
          style={{ width: 32, height: 32 }}
          aria-label={t("share_win_close_aria")}
          title={t("share_win_close_aria")}
          onClick={() => void getCompanionApi().closeShareWindow().catch(() => undefined)}
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>

      {/* Floating In-Window Status Toast */}
      {toast ? (
        <div
          className={cx(
            "wiz-toast",
            toast.tone === "error" && "is-error",
            toast.tone === "success" && "is-success",
            toast.tone === "warning" && "is-warning",
          )}
          style={{ top: 54 }}
          role="status"
        >
          {toast.text}
        </div>
      ) : null}

      {/* Scrollable Body */}
      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-slim p-4 space-y-4">
        {targetLoading && !target ? (
          <div className="rounded-card border border-[var(--line)] bg-[var(--surface-elevated)] backdrop-blur-xs p-4 text-center text-body font-normal text-[var(--ink-muted)]">
            {t("share_win_loading")}
          </div>
        ) : !target ? (
          <div className="rounded-card border border-[var(--danger-border)] bg-[var(--danger-bg)] p-4 text-center text-body font-normal text-[var(--danger-ink)]">
            {targetError || t("share_win_no_target")}
          </div>
        ) : (
          <>
            {/* A. Target Item Header Card (E1) */}
            <div className="rounded-card border border-[var(--line)] bg-[var(--surface-elevated)] backdrop-blur-xs p-4 flex items-center gap-4">
              <span className={target.is_dir ? "[&_svg]:text-warning" : "[&_svg]:text-[var(--ink-muted)]"}>
                <IconBadge icon={target.is_dir ? Folder : FileText} />
              </span>
              <div className="min-w-0 flex-1">
                <div
                  className="text-body font-semibold text-[var(--ink)] truncate"
                  title={target.basename}
                >
                  {target.basename}
                </div>
                <Mono
                  className="block truncate text-caption font-normal text-[var(--ink-subtle)]"
                  title={target.canonical_rel}
                >
                  {target.canonical_rel}
                </Mono>
              </div>
              <Chip size="sm" tone="neutral" className="max-w-[120px]">
                <span className="truncate" title={serverDiskLabel}>
                  {serverDiskLabel}
                </span>
              </Chip>
            </div>

            {/* B. Share Configuration Card (E2) */}
            <form
              onSubmit={handleCreateShare}
              className="rounded-card border border-[var(--line)] bg-[var(--surface-elevated)] backdrop-blur-xs p-4 space-y-4"
            >
              {/* Optional Password */}
              <div className="space-y-2">
                <label
                  htmlFor={passwordId}
                  className="block text-caption font-semibold text-[var(--ink)]"
                >
                  {t("share_password_label")}
                </label>
                <div className="relative flex items-center min-w-0">
                  <input
                    id={passwordId}
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={t("share_password_placeholder")}
                    className="min-w-0 flex-1 rounded-control border border-[var(--input-border)] bg-[var(--input-bg)] py-2 pl-2 pr-8 text-body font-normal text-[var(--ink)] placeholder:text-[var(--ink-subtle)] outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_3px_var(--input-focus)]"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    aria-label={showPassword ? t("share_password_hide_aria") : t("share_password_show_aria")}
                    title={showPassword ? t("share_password_hide_aria") : t("share_password_show_aria")}
                    className="absolute right-0 top-0 inline-flex size-8 items-center justify-center text-[var(--ink-muted)] hover:text-[var(--ink)] cursor-pointer"
                  >
                    {showPassword ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                  </button>
                </div>
              </div>

              {/* Expiration Segmented Control */}
              <div className="space-y-2">
                <span className="block text-caption font-semibold text-[var(--ink)]">
                  {t("share_expiry_label")}
                </span>
                <div
                  role="radiogroup"
                  aria-label={t("share_expiry_label")}
                  className="grid grid-cols-5 gap-1 p-1 rounded-tile border border-[var(--line)] bg-[var(--seg-track)]"
                >
                  {expiryOptions.map((opt) => {
                    const selected = expiryMode === opt.mode
                    return (
                      <button
                        key={opt.mode}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => setExpiryMode(opt.mode)}
                        className={
                          selected
                            ? "rounded-control border border-[var(--seg-active-border)] bg-[var(--seg-active)] text-[var(--seg-active-ink)] px-2 py-2 text-caption font-semibold shadow-xs cursor-pointer truncate"
                            : "rounded-control border border-transparent bg-transparent text-[var(--ink-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--ink)] px-2 py-2 text-caption font-normal cursor-pointer truncate"
                        }
                      >
                        {opt.label}
                      </button>
                    )
                  })}
                </div>

                {expiryMode === "custom" ? (
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min={1}
                        max={8760}
                        step={1}
                        aria-label={t("share_expiry_custom")}
                        value={customHours}
                        onChange={(e) => setCustomHours(e.target.value)}
                        className="w-24 rounded-control border border-[var(--input-border)] bg-[var(--input-bg)] px-2 py-2 text-body font-normal text-[var(--ink)] outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_3px_var(--input-focus)]"
                      />
                      <span className="text-caption font-normal text-[var(--ink-subtle)]">
                        {t("share_expiry_custom_unit")}
                      </span>
                    </div>
                    {!isCustomExpiryValid ? (
                      <p role="alert" className="text-caption font-normal text-[var(--danger-ink)]">
                        {t("share_expiry_invalid")}
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>

              {/* STRICT SECH-03 Admin-Only Public Base URL (omitted from DOM when loading or non-admin) */}
              {isAdmin === true ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <label
                      htmlFor={baseUrlId}
                      className="text-caption font-semibold text-[var(--ink)]"
                    >
                      {t("share_public_base_label")}
                    </label>
                    <Chip size="sm" tone="info">
                      {t("share_public_base_admin_chip")}
                    </Chip>
                  </div>
                  <div className="flex items-center gap-2 min-w-0">
                    <input
                      id={baseUrlId}
                      type="url"
                      aria-label={t("share_public_base_label")}
                      placeholder={t("share_public_base_placeholder")}
                      value={publicBaseUrl}
                      onChange={(e) => {
                        setPublicBaseUrl(e.target.value)
                        if (baseUrlError) setBaseUrlError(null)
                      }}
                      className="min-w-0 flex-1 rounded-control border border-[var(--input-border)] bg-[var(--input-bg)] px-2 py-2 text-body font-normal text-[var(--ink)] placeholder:text-[var(--ink-subtle)] outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_3px_var(--input-focus)]"
                    />
                    <button
                      type="button"
                      disabled={savingBaseUrl}
                      aria-busy={savingBaseUrl || undefined}
                      onClick={() => void handleSaveBaseUrl()}
                      className="shrink-0 inline-flex items-center gap-1 rounded-control border border-[var(--btn-sec-border)] bg-[var(--btn-sec-bg)] text-[var(--btn-sec-ink)] hover:bg-[var(--btn-sec-hover-bg)] hover:border-[var(--btn-sec-hover-border)] disabled:opacity-50 px-2 py-2 text-caption font-semibold cursor-pointer"
                    >
                      {savingBaseUrl ? <LoaderCircle className="size-3.5 animate-spin" aria-hidden /> : null}
                      {t("share_public_base_save")}
                    </button>
                  </div>
                  {baseUrlError ? (
                    <p role="alert" className="text-caption font-normal text-[var(--danger-ink)]">
                      {baseUrlError}
                    </p>
                  ) : null}
                  <p className="text-caption font-normal text-[var(--ink-subtle)]">
                    {t("share_public_base_help")}
                  </p>
                </div>
              ) : null}

              {/* Primary CTA */}
              <button
                type="submit"
                disabled={creating || !target || !isCustomExpiryValid}
                aria-busy={creating || undefined}
                className="w-full inline-flex items-center justify-center gap-2 rounded-control px-4 py-2 text-body font-semibold border border-[var(--btn-primary-border)] bg-[image:var(--btn-primary-bg)] text-[var(--btn-primary-ink)] shadow-[var(--btn-primary-shadow)] hover:brightness-105 active:translate-y-px disabled:bg-[var(--btn-primary-disabled-bg)] disabled:bg-none disabled:border-[var(--btn-primary-disabled-border)] disabled:text-[var(--btn-primary-disabled-ink)] disabled:shadow-none cursor-pointer"
              >
                {creating ? (
                  <>
                    <LoaderCircle className="size-4 animate-spin shrink-0" aria-hidden />
                    <span>{t("share_cta_creating")}</span>
                  </>
                ) : justCopied ? (
                  <>
                    <Check className="size-4 shrink-0" aria-hidden />
                    <span>{t("share_cta_copied")}</span>
                  </>
                ) : (
                  <>
                    <Link2 className="size-4 shrink-0" aria-hidden />
                    <span>{t("share_cta_create")}</span>
                  </>
                )}
              </button>
            </form>

            {/* C. Generated Share Link Result Card (E3) */}
            {generatedLink ? (
              <div
                data-testid="generated-share-card"
                className="rounded-card border border-[var(--ok-border)] bg-[var(--surface-elevated)] backdrop-blur-xs p-4 space-y-4"
              >
                <SectionLabel
                  trailing={
                    generatedLink.copied ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-[var(--ok-border)] bg-[var(--ok-bg)] text-[var(--ok-ink)] px-2 py-1 text-caption font-semibold">
                        <Check className="size-4" aria-hidden />
                        {t("share_copied_badge")}
                      </span>
                    ) : undefined
                  }
                >
                  {t("share_generated_section")}
                </SectionLabel>

                <div className="rounded-control border border-[var(--input-border)] bg-[var(--input-bg)] px-2 py-2 flex items-center justify-between gap-2 min-w-0">
                  <Mono
                    className="truncate text-caption font-normal text-[var(--ink)] select-all"
                    title={generatedLink.url}
                  >
                    {generatedLink.url}
                  </Mono>
                </div>

                {generatedLink.isLanFallback ? (
                  <div
                    role="note"
                    className="rounded-control border border-[var(--warn-border)] bg-[var(--warn-bg)] px-2 py-2 text-caption font-normal text-[var(--warn-ink)]"
                  >
                    {isAdmin === true ? t("share_lan_warn_admin") : t("share_lan_warn_non_admin")}
                  </div>
                ) : null}

                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => void handleCopyUrl(generatedLink.url)}
                    className="inline-flex items-center justify-center gap-1.5 rounded-control border border-[var(--btn-sec-border)] bg-[var(--btn-sec-bg)] text-[var(--btn-sec-ink)] hover:bg-[var(--btn-sec-hover-bg)] hover:border-[var(--btn-sec-hover-border)] px-2 py-2 text-caption font-semibold cursor-pointer"
                  >
                    <Copy className="size-4 shrink-0" aria-hidden />
                    <span className="truncate">{t("share_btn_copy_link")}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void getCompanionApi().openExternalBrowser(generatedLink.url)}
                    className="inline-flex items-center justify-center gap-1.5 rounded-control border border-[var(--btn-sec-border)] bg-[var(--btn-sec-bg)] text-[var(--btn-sec-ink)] hover:bg-[var(--btn-sec-hover-bg)] hover:border-[var(--btn-sec-hover-border)] px-2 py-2 text-caption font-semibold cursor-pointer"
                  >
                    <ExternalLink className="size-4 shrink-0 text-info" aria-hidden />
                    <span className="truncate">{t("share_btn_open_browser")}</span>
                  </button>
                </div>

                <div className="flex items-center gap-4 rounded-tile border border-[var(--line)] bg-[var(--input-bg)] p-2">
                  <QrCodeSvg
                    url={generatedLink.url}
                    ariaLabel={t("share_qr_aria")}
                    fallbackText={t("share_qr_fallback")}
                  />
                  <p className="text-caption font-normal text-[var(--ink-subtle)]">
                    {t("share_qr_guidance")}
                  </p>
                </div>
              </div>
            ) : null}

            {/* D. Active Links for This Item (E4) */}
            <div className="space-y-2">
              <SectionLabel trailing={String(activeItemShares.length)}>
                {t("share_active_section")}
              </SectionLabel>

              {sharesLoading ? (
                <div data-testid="active-links-skeleton" className="space-y-2">
                  <div className="h-16 rounded-tile border border-[var(--line)] bg-[var(--surface-elevated)] animate-pulse" />
                  <div className="h-16 rounded-tile border border-[var(--line)] bg-[var(--surface-elevated)] animate-pulse" />
                </div>
              ) : sharesError ? (
                <div className="rounded-tile border border-[var(--danger-border)] bg-[var(--danger-bg)] p-3 flex items-center justify-between gap-2">
                  <span className="text-caption font-normal text-[var(--danger-ink)]">
                    {sharesError}
                  </span>
                  <TextAction tone="neutral" onClick={() => void fetchShares(target)}>
                    {t("share_btn_refresh_links")}
                  </TextAction>
                </div>
              ) : activeItemShares.length === 0 ? (
                <div className="rounded-tile border border-[var(--line)] bg-[var(--surface-elevated)] backdrop-blur-xs p-6 text-center space-y-2">
                  <p className="text-body font-semibold text-[var(--ink)]">
                    {t("share_active_empty_title")}
                  </p>
                  <p className="text-caption font-normal text-[var(--ink-subtle)]">
                    {t("share_active_empty_body")}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {activeItemShares.map((share) => {
                    const count = share.download_count ?? 0
                    const downloadsLabel =
                      count === 1
                        ? t("share_downloads_singular")
                        : t("share_downloads_plural").replace("{count}", String(count))
                    const shareUrl = share.resolved_url || share.share_url
                    const isConfirming = revokeConfirmToken === share.token
                    const isRevoking = revokingToken === share.token

                    return (
                      <div
                        key={share.token}
                        data-testid={`active-share-row-${share.token}`}
                        className="rounded-tile border border-[var(--line)] bg-[var(--surface-elevated)] backdrop-blur-xs p-2 space-y-2"
                      >
                        <div className="flex flex-wrap items-center gap-2 min-w-0">
                          <Mono
                            className="truncate max-w-full text-caption font-semibold text-[var(--ink)]"
                            title={`/s/${share.token}`}
                          >
                            {`/s/${share.token}`}
                          </Mono>
                          <Chip size="sm" tone="neutral">
                            <span title={share.expires_at || undefined}>
                              {share.expires_at
                                ? formatExpiryLabel(share.expires_at, language)
                                : t("share_expiry_unlimited")}
                            </span>
                          </Chip>
                          {share.password_protected ? (
                            <Chip size="sm" tone="info" icon={Lock}>
                              {t("share_chip_password")}
                            </Chip>
                          ) : null}
                          <span className="text-caption font-normal text-[var(--ink-subtle)]">
                            {downloadsLabel}
                          </span>
                        </div>

                        {isConfirming ? (
                          <div className="rounded-control border border-[var(--danger-border)] bg-[var(--danger-bg)] p-2 flex items-center justify-between gap-2">
                            <span className="text-caption font-semibold text-[var(--danger-ink)]">
                              {t("share_revoke_confirm_prompt")}
                            </span>
                            <div className="flex items-center gap-2 shrink-0">
                              <TextAction
                                tone="neutral"
                                disabled={isRevoking}
                                onClick={() => setRevokeConfirmToken(null)}
                              >
                                {t("share_btn_keep_link")}
                              </TextAction>
                              <Button
                                size="sm"
                                variant="danger"
                                state={isRevoking ? "busy" : "idle"}
                                disabled={isRevoking}
                                onClick={() => void handleConfirmRevoke(share.token)}
                              >
                                {t("share_btn_revoke_link")}
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              aria-label={t("share_btn_copy_aria")}
                              onClick={() => void handleCopyUrl(shareUrl)}
                              className="inline-flex items-center gap-1 rounded-control border border-[var(--btn-sec-border)] bg-[var(--btn-sec-bg)] text-[var(--btn-sec-ink)] hover:bg-[var(--btn-sec-hover-bg)] hover:border-[var(--btn-sec-hover-border)] px-2 py-1 text-caption font-semibold cursor-pointer"
                            >
                              <Copy className="size-4 shrink-0" aria-hidden />
                              <span>{t("share_btn_copy")}</span>
                            </button>
                            <button
                              type="button"
                              aria-label={t("share_btn_open_aria")}
                              onClick={() => void getCompanionApi().openExternalBrowser(shareUrl)}
                              className="inline-flex items-center gap-1 rounded-control border border-[var(--btn-subtle-border)] bg-[var(--btn-subtle-bg)] text-[var(--btn-subtle-ink)] hover:bg-[var(--surface-hover)] px-2 py-1 text-caption font-semibold cursor-pointer"
                            >
                              <ExternalLink className="size-4 shrink-0 text-info" aria-hidden />
                              <span>{t("share_btn_open")}</span>
                            </button>
                            <button
                              type="button"
                              aria-label={t("share_btn_revoke_aria")}
                              onClick={() => setRevokeConfirmToken(share.token)}
                              className="inline-flex items-center gap-1 rounded-control px-2 py-1 text-caption font-semibold text-[var(--danger-ink)] hover:bg-[var(--danger-bg)] cursor-pointer"
                            >
                              <Trash2 className="size-4 shrink-0" aria-hidden />
                              <span>{t("share_btn_revoke")}</span>
                            </button>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default ShareWindow

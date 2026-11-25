import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardCopy,
  Copy,
  FileText,
  Folder,
  FolderOpen,
  HardDrive,
  LoaderCircle,
  Pause,
  Play,
  RefreshCw,
  ShieldAlert,
  Trash2,
  Users,
  X,
  XCircle,
} from "lucide-react"
import { getCompanionApi } from "../api"
import { assets } from "../assets"
import { getTranslation, type Language } from "../i18n"
import type {
  ExplorerClipboardState,
  QuickPickerBrowseResponse,
  QuickPickerEntry,
  TransferConflictAction,
  TransferStatusResponse,
  TransferWindowMode,
} from "../types"
import { Button, Chip, IconBadge, Mono, ProgressBar, SectionLabel, StatusDot, cx } from "../ui"

export interface TransferWindowProps {
  initialMode?: TransferWindowMode
}

type BrowseSource = "disks" | "shared"

type TransferToast = {
  text: string
  tone: "info" | "success" | "error" | "warning"
} | null

function backdropFor(theme: "dark" | "light", isOffline: boolean): string {
  if (theme === "light") return isOffline ? assets.flyoutBgLightOffline : assets.flyoutBgLight
  return isOffline ? assets.flyoutBgDarkOffline : assets.flyoutBgDark
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB", "TB"]
  let value = bytes
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${idx === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[idx]}`
}

function formatSpeed(bps: number): string {
  if (!Number.isFinite(bps) || bps <= 0) return "0 B/s"
  return `${formatBytes(bps)}/s`
}

function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "--"
  const s = Math.round(seconds)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  if (m < 60) return `${m}m ${rem}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function parseMode(raw: unknown): TransferWindowMode | null {
  if (raw === "progress" || raw === "quick_picker" || raw === "browse") return raw
  return null
}

function roleLabelKey(role: string | undefined): string {
  switch ((role || "").toLowerCase()) {
    case "owner":
      return "xfer_qp_role_owner"
    case "admin":
    case "system_admin":
    case "administrator":
      return "xfer_qp_role_admin"
    case "editor":
      return "xfer_qp_role_editor"
    default:
      return "xfer_qp_role_viewer"
  }
}

function roleTone(role: string | undefined): "success" | "info" | "warning" | "neutral" {
  switch ((role || "").toLowerCase()) {
    case "owner":
    case "admin":
    case "system_admin":
    case "administrator":
      return "success"
    case "editor":
      return "info"
    case "viewer":
      return "warning"
    default:
      return "neutral"
  }
}

export function TransferWindow({ initialMode }: TransferWindowProps = {}) {
  const [theme, setTheme] = useState<"dark" | "light">("dark")
  const [language, setLanguage] = useState<Language>("en")
  const [isOnline, setIsOnline] = useState<boolean>(true)

  const [mode, setMode] = useState<TransferWindowMode>(() => {
    if (initialMode) return initialMode
    if (typeof window !== "undefined") {
      const fromUrl = parseMode(new URLSearchParams(window.location.search).get("mode"))
      if (fromUrl) return fromUrl
    }
    return "progress"
  })

  const [transferStatus, setTransferStatus] = useState<TransferStatusResponse | null>(null)
  const [clipboard, setClipboard] = useState<ExplorerClipboardState | null>(null)
  const [statusBusy, setStatusBusy] = useState(false)

  // Conflict modal state
  const [applyToAll, setApplyToAll] = useState(false)
  const [resolvingConflict, setResolvingConflict] = useState(false)

  // Quick Picker / Browse state
  const [browseSource, setBrowseSource] = useState<BrowseSource>("disks")
  const [browsePath, setBrowsePath] = useState<string>("")
  const [browseData, setBrowseData] = useState<QuickPickerBrowseResponse | null>(null)
  const [browseLoading, setBrowseLoading] = useState(false)
  const [browseError, setBrowseError] = useState<string | null>(null)
  const [pasting, setPasting] = useState(false)
  const [copyingPath, setCopyingPath] = useState<string | null>(null)

  const [toast, setToast] = useState<TransferToast>(null)
  const toastTimerRef = useRef<number | null>(null)
  const mountedRef = useRef(true)
  const browseSeqRef = useRef(0)

  const t = useMemo(() => getTranslation(language), [language])

  const showToast = useCallback((text: string, tone: "info" | "success" | "error" | "warning" = "info") => {
    setToast({ text, tone })
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current)
    }
    toastTimerRef.current = window.setTimeout(() => {
      if (mountedRef.current) {
        setToast(null)
      }
      toastTimerRef.current = null
    }, 3200)
  }, [])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (toastTimerRef.current !== null) {
        window.clearTimeout(toastTimerRef.current)
      }
    }
  }, [])

  // Sync theme and language once on mount (never invokes setWizardMode or subscribeMetrics)
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

  const refreshStatus = useCallback(async () => {
    const api = getCompanionApi()
    try {
      const [statusRes, clipRes] = await Promise.all([
        api.getTransferStatus(),
        api.getExplorerClipboard().catch(() => null),
      ])
      if (!mountedRef.current) return
      if (statusRes) {
        setTransferStatus(statusRes)
        setIsOnline(true)
        if (statusRes.clipboard) {
          setClipboard(statusRes.clipboard)
        }
      }
      if (clipRes) {
        setClipboard(clipRes)
      }
    } catch {
      if (!mountedRef.current) return
      setIsOnline(false)
    }
  }, [])

  const loadDirectory = useCallback(async (source: BrowseSource, path: string) => {
    const seq = ++browseSeqRef.current
    setBrowseLoading(true)
    setBrowseError(null)
    try {
      const res = await getCompanionApi().browseTransferDirectory({
        source,
        path,
      })
      if (!mountedRef.current || seq !== browseSeqRef.current) return
      if (!res.success) {
        setBrowseError(res.error || "Failed to load directory")
      }
      setBrowseData(res)
      setBrowsePath(res.current_path ?? path)
      setIsOnline(true)
    } catch (err) {
      if (!mountedRef.current || seq !== browseSeqRef.current) return
      setBrowseError(err instanceof Error ? err.message : String(err))
    } finally {
      if (mountedRef.current && seq === browseSeqRef.current) {
        setBrowseLoading(false)
      }
    }
  }, [])

  // Hydrate initial window state + status
  useEffect(() => {
    let active = true
    const api = getCompanionApi()

    async function hydrate() {
      if (!initialMode) {
        try {
          const winState = await api.getTransferWindowState()
          if (!active) return
          const stateMode = parseMode(winState?.mode)
          if (stateMode) setMode(stateMode)
        } catch {
          // Ignore optional window state errors
        }
      }
      await refreshStatus()
    }

    void hydrate()
    return () => {
      active = false
    }
  }, [initialMode, refreshStatus])

  // Load directory whenever entering quick_picker or browse
  useEffect(() => {
    if (mode === "quick_picker" || mode === "browse") {
      void loadDirectory(browseSource, browsePath)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, browseSource])

  // Listen to Rust/Tauri myserver:transfer-event for instant mode/status updates
  useEffect(() => {
    const onTransferEvent = (event: Event) => {
      const detail = (event as CustomEvent<Record<string, unknown>>).detail
      if (!detail || typeof detail !== "object") {
        void refreshStatus()
        return
      }
      const nextMode = parseMode(detail.mode)
      if (nextMode) {
        setMode(nextMode)
      }
      if (typeof detail.status === "string" && Array.isArray(detail.items)) {
        setTransferStatus(detail as unknown as TransferStatusResponse)
      } else {
        void refreshStatus()
      }
    }

    window.addEventListener("myserver:transfer-event", onTransferEvent)
    return () => {
      window.removeEventListener("myserver:transfer-event", onTransferEvent)
    }
  }, [refreshStatus])

  // Poll getTransferStatus() every 300ms ONLY while active
  const activeJobStatus = transferStatus?.status
  useEffect(() => {
    const shouldPoll =
      activeJobStatus === "scanning" ||
      activeJobStatus === "running" ||
      activeJobStatus === "awaiting_conflict"
    if (!shouldPoll) return

    const timer = window.setInterval(() => {
      void getCompanionApi()
        .getTransferStatus()
        .then((res) => {
          if (!mountedRef.current || !res) return
          setTransferStatus(res)
          if (res.clipboard) setClipboard(res.clipboard)
        })
        .catch(() => undefined)
    }, 300)

    return () => {
      window.clearInterval(timer)
    }
  }, [activeJobStatus])

  // Escape closes ONLY transfer-window
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        void getCompanionApi().closeTransferWindow().catch(() => undefined)
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

  const handlePause = async () => {
    setStatusBusy(true)
    try {
      const res = await getCompanionApi().pauseTransferJob(transferStatus?.job_id)
      if (mountedRef.current) setTransferStatus(res)
    } finally {
      if (mountedRef.current) setStatusBusy(false)
    }
  }

  const handleResume = async () => {
    setStatusBusy(true)
    try {
      const res = await getCompanionApi().resumeTransferJob(transferStatus?.job_id)
      if (mountedRef.current) setTransferStatus(res)
    } finally {
      if (mountedRef.current) setStatusBusy(false)
    }
  }

  const handleCancel = async () => {
    setStatusBusy(true)
    try {
      const res = await getCompanionApi().cancelTransferJob(transferStatus?.job_id)
      if (mountedRef.current) setTransferStatus(res)
    } finally {
      if (mountedRef.current) setStatusBusy(false)
    }
  }

  const handleClear = async () => {
    setStatusBusy(true)
    try {
      await getCompanionApi().clearTransferHistory()
      await refreshStatus()
    } finally {
      if (mountedRef.current) setStatusBusy(false)
    }
  }

  const handleResolveConflict = async (action: TransferConflictAction) => {
    const conflict = transferStatus?.conflict
    if (!conflict || resolvingConflict) return
    setResolvingConflict(true)
    try {
      const res = await getCompanionApi().resolveTransferConflict({
        jobId: conflict.job_id,
        action,
        applyToAll,
      })
      if (mountedRef.current) {
        setTransferStatus(res)
        setApplyToAll(false)
      }
    } finally {
      if (mountedRef.current) setResolvingConflict(false)
    }
  }

  const handlePasteHere = async () => {
    if (!browseData || !browseData.writable || pasting) return
    setPasting(true)
    try {
      const res = await getCompanionApi().startTransferPaste({
        serverId: browseData.server_id,
        destRel: browseData.current_path,
      })
      if (!mountedRef.current) return
      setTransferStatus(res)
      setMode("progress")
    } catch (err) {
      if (mountedRef.current) {
        showToast(err instanceof Error ? err.message : String(err), "error")
      }
    } finally {
      if (mountedRef.current) setPasting(false)
    }
  }

  const handleCopyEntryToDesktop = async (entry: QuickPickerEntry) => {
    if (copyingPath) return
    setCopyingPath(entry.relative_path)
    try {
      const res = await getCompanionApi().copyServerItemsToClipboard({
        serverId: browseData?.server_id,
        items: [
          {
            relative_path: entry.relative_path,
            name: entry.name,
            is_dir: entry.is_dir,
            size: entry.size,
          },
        ],
      })
      if (!mountedRef.current) return
      if (res.success) {
        if (res.clipboard) setClipboard(res.clipboard)
        showToast(t("xfer_qp_copied_toast").replace("{count}", "1"), "success")
      } else {
        showToast(res.error || "Copy failed", "error")
      }
    } catch (err) {
      if (mountedRef.current) {
        showToast(err instanceof Error ? err.message : String(err), "error")
      }
    } finally {
      if (mountedRef.current) setCopyingPath(null)
    }
  }

  const headerTitle =
    mode === "quick_picker"
      ? t("xfer_title_quick_picker")
      : mode === "browse"
        ? t("xfer_title_browse")
        : t("xfer_title_progress")

  const statusText = (() => {
    switch (transferStatus?.status) {
      case "scanning":
        return t("xfer_status_scanning")
      case "running":
        return t("xfer_status_running")
      case "paused":
        return t("xfer_status_paused")
      case "completed":
        return t("xfer_status_completed")
      case "cancelled":
        return t("xfer_status_cancelled")
      case "error":
        return t("xfer_status_error")
      case "awaiting_conflict":
        return t("xfer_status_conflict")
      default:
        return t("xfer_status_idle")
    }
  })()

  const statusTone: "success" | "info" | "warning" | "danger" | "neutral" = (() => {
    switch (transferStatus?.status) {
      case "running":
      case "scanning":
        return "info"
      case "completed":
        return "success"
      case "awaiting_conflict":
      case "paused":
        return "warning"
      case "error":
      case "cancelled":
        return "danger"
      default:
        return "neutral"
    }
  })()

  const progressPct = useMemo(() => {
    if (!transferStatus) return 0
    if (transferStatus.bytes_total > 0) {
      return Math.min(100, Math.round((transferStatus.bytes_done / transferStatus.bytes_total) * 100))
    }
    if (transferStatus.total_files > 0) {
      return Math.min(
        100,
        Math.round((transferStatus.completed_files / transferStatus.total_files) * 100),
      )
    }
    return transferStatus.status === "completed" ? 100 : 0
  }, [transferStatus])

  const clipboardLabel = useMemo(() => {
    if (!clipboard || clipboard.kind === "empty" || clipboard.items.length === 0) {
      return t("xfer_clipboard_empty")
    }
    const count = String(clipboard.items.length)
    return clipboard.kind === "local"
      ? t("xfer_clipboard_local").replace("{count}", count)
      : t("xfer_clipboard_server").replace("{count}", count)
  }, [clipboard, t])

  const conflict = transferStatus?.status === "awaiting_conflict" ? transferStatus.conflict : null
  const isViewerLocked = Boolean(browseData && (!browseData.writable || browseData.effective_role === "viewer"))

  return (
    <div
      className="wizard-win w-[400px] h-[560px] p-0 flex flex-col overflow-hidden rounded-[16px]"
      data-theme={theme}
      data-server-status={isOnline ? "online" : "offline"}
      data-testid="transfer-window"
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
        data-testid="transfer-drag-bar"
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
            {headerTitle}
          </span>
          <StatusDot tone={isOnline ? "success" : "danger"} />
        </div>
        <button
          type="button"
          className="wiz-icon-btn wiz-close size-8 shrink-0"
          style={{ width: 32, height: 32 }}
          aria-label={t("xfer_close_aria")}
          title={t("xfer_close_aria")}
          onClick={() => void getCompanionApi().closeTransferWindow().catch(() => undefined)}
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>

      {/* Mode Switcher */}
      <div className="px-4 pt-3 shrink-0">
        <div
          role="tablist"
          aria-label="Transfer Window Mode"
          className="grid grid-cols-3 gap-1 p-1 rounded-[10px] border border-[var(--line)] bg-[var(--seg-track)]"
        >
          {(["progress", "quick_picker", "browse"] as const).map((tabMode) => {
            const selected = mode === tabMode
            const label =
              tabMode === "progress"
                ? t("xfer_title_progress")
                : tabMode === "quick_picker"
                  ? t("xfer_title_quick_picker")
                  : t("xfer_title_browse")
            return (
              <button
                key={tabMode}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => setMode(tabMode)}
                className={
                  selected
                    ? "rounded-control border border-[var(--seg-active-border)] bg-[var(--seg-active)] text-[var(--seg-active-ink)] px-2 py-1.5 text-micro font-semibold shadow-xs cursor-pointer truncate"
                    : "rounded-control border border-transparent bg-transparent text-[var(--ink-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--ink)] px-2 py-1.5 text-micro font-normal cursor-pointer truncate"
                }
              >
                {label}
              </button>
            )
          })}
        </div>
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
      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-slim p-4 space-y-3 relative">
        {/* Windows-Style Conflict Modal Overlay */}
        {conflict ? (
          <div
            data-testid="transfer-conflict-modal"
            role="dialog"
            aria-modal="true"
            aria-label={t("xfer_conflict_title")}
            className="rounded-card border border-[var(--warning-border)] bg-[var(--surface-elevated)] backdrop-blur-md p-4 space-y-3 shadow-lg"
          >
            <div className="flex items-start gap-3">
              <IconBadge icon={AlertTriangle} tone="warning" />
              <div className="min-w-0 flex-1">
                <div className="text-body font-semibold text-[var(--ink)]">
                  {t("xfer_conflict_title")}
                </div>
                <p className="text-caption text-[var(--ink-muted)] mt-0.5 break-words">
                  {(conflict.is_dir ? t("xfer_conflict_body_dir") : t("xfer_conflict_body_file")).replace(
                    "{name}",
                    conflict.item_name,
                  )}
                </p>
                <Mono className="block text-micro text-[var(--ink-subtle)] truncate mt-1">
                  {conflict.dest_path}
                </Mono>
                {typeof conflict.remaining_conflicts_hint === "number" &&
                conflict.remaining_conflicts_hint > 0 ? (
                  <div className="text-micro text-[var(--warning-ink)] mt-1">
                    {t("xfer_conflict_remaining").replace(
                      "{count}",
                      String(conflict.remaining_conflicts_hint),
                    )}
                  </div>
                ) : null}
              </div>
            </div>

            <label className="flex items-center gap-2 text-caption text-[var(--ink)] cursor-pointer select-none pt-1">
              <input
                type="checkbox"
                checked={applyToAll}
                onChange={(e) => setApplyToAll(e.target.checked)}
                className="rounded border-[var(--line)] accent-[var(--accent)]"
              />
              <span>{t("xfer_conflict_apply_all")}</span>
            </label>

            <div className="flex flex-col gap-2 pt-1">
              <Button
                variant="primary"
                block
                disabled={resolvingConflict}
                onClick={() => void handleResolveConflict("overwrite")}
              >
                {t("xfer_conflict_overwrite")}
              </Button>
              <Button
                variant="secondary"
                block
                disabled={resolvingConflict}
                onClick={() => void handleResolveConflict("rename")}
              >
                {t("xfer_conflict_rename")}
              </Button>
              <Button
                variant="ghost"
                block
                disabled={resolvingConflict}
                onClick={() => void handleResolveConflict("skip")}
              >
                {t("xfer_conflict_skip")}
              </Button>
            </div>
          </div>
        ) : null}

        {/* Mode 1: Floating Transfer Progress Queue */}
        {mode === "progress" ? (
          <>
            {/* Clipboard Summary */}
            <div className="rounded-card border border-[var(--line)] bg-[var(--surface-elevated)] backdrop-blur-xs px-3 py-2.5 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <ClipboardCopy className="size-4 shrink-0 text-[var(--ink-muted)]" aria-hidden />
                <span className="text-caption font-medium text-[var(--ink)] truncate">
                  {clipboardLabel}
                </span>
              </div>
              <Chip size="sm" tone={clipboard && clipboard.kind !== "empty" ? "info" : "neutral"}>
                {t("xfer_clipboard_badge")}
              </Chip>
            </div>

            {!transferStatus ||
            (transferStatus.status === "idle" && transferStatus.items.length === 0) ? (
              <div className="rounded-card border border-[var(--line)] bg-[var(--surface-elevated)] backdrop-blur-xs p-5 text-center space-y-2">
                <div className="text-body font-semibold text-[var(--ink)]">
                  {t("xfer_empty_title")}
                </div>
                <p className="text-caption text-[var(--ink-muted)]">{t("xfer_empty_body")}</p>
              </div>
            ) : (
              <div className="rounded-card border border-[var(--line)] bg-[var(--surface-elevated)] backdrop-blur-xs p-3.5 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Chip size="sm" tone={statusTone}>
                      {statusText}
                    </Chip>
                    {transferStatus.dest_label ? (
                      <Mono className="text-micro text-[var(--ink-subtle)] truncate">
                        {transferStatus.dest_label}
                      </Mono>
                    ) : null}
                  </div>
                  <span className="text-caption font-semibold tabular-nums text-[var(--ink)]">
                    {progressPct}%
                  </span>
                </div>

                <ProgressBar
                  value={progressPct}
                  tone={statusTone}
                  label={statusText}
                />

                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-control border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5">
                    <div className="text-micro text-[var(--ink-subtle)]">
                      {t("xfer_speed_label")}
                    </div>
                    <div className="text-caption font-semibold tabular-nums text-[var(--ink)]">
                      {formatSpeed(transferStatus.speed_bps)}
                    </div>
                  </div>
                  <div className="rounded-control border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5">
                    <div className="text-micro text-[var(--ink-subtle)]">
                      {t("xfer_workers_label")}
                    </div>
                    <div
                      data-testid="transfer-workers-pill"
                      className="text-caption font-semibold tabular-nums text-[var(--ink)]"
                    >
                      {transferStatus.active_workers}/{transferStatus.max_workers}
                    </div>
                  </div>
                  <div className="rounded-control border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5">
                    <div className="text-micro text-[var(--ink-subtle)]">
                      {t("xfer_eta_label")}
                    </div>
                    <div className="text-caption font-semibold tabular-nums text-[var(--ink)]">
                      {formatEta(transferStatus.eta_seconds)}
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between text-micro text-[var(--ink-muted)] tabular-nums">
                  <span>
                    {t("xfer_files_progress")
                      .replace("{done}", String(transferStatus.completed_files))
                      .replace("{total}", String(transferStatus.total_files))}
                  </span>
                  <span>
                    {formatBytes(transferStatus.bytes_done)} / {formatBytes(transferStatus.bytes_total)}
                  </span>
                </div>

                {/* Controls */}
                <div className="flex items-center gap-2 pt-1">
                  {transferStatus.status === "running" || transferStatus.status === "scanning" ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={Pause}
                      disabled={statusBusy}
                      onClick={() => void handlePause()}
                    >
                      {t("xfer_btn_pause")}
                    </Button>
                  ) : null}

                  {transferStatus.status === "paused" ? (
                    <Button
                      variant="primary"
                      size="sm"
                      icon={Play}
                      disabled={statusBusy}
                      onClick={() => void handleResume()}
                    >
                      {t("xfer_btn_resume")}
                    </Button>
                  ) : null}

                  {transferStatus.status === "running" ||
                  transferStatus.status === "scanning" ||
                  transferStatus.status === "paused" ||
                  transferStatus.status === "awaiting_conflict" ? (
                    <Button
                      variant="danger"
                      size="sm"
                      icon={XCircle}
                      disabled={statusBusy}
                      onClick={() => void handleCancel()}
                    >
                      {t("xfer_btn_cancel")}
                    </Button>
                  ) : null}

                  {transferStatus.status === "completed" ||
                  transferStatus.status === "cancelled" ||
                  transferStatus.status === "error" ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={Trash2}
                      disabled={statusBusy}
                      onClick={() => void handleClear()}
                    >
                      {t("xfer_btn_clear")}
                    </Button>
                  ) : null}
                </div>

                {/* Queue Items */}
                {transferStatus.items.length > 0 ? (
                  <div className="space-y-1.5 pt-1 max-h-[180px] overflow-y-auto scrollbar-slim">
                    {transferStatus.items.map((item) => {
                      const itemPct =
                        item.bytes_total > 0
                          ? Math.min(100, Math.round((item.bytes_done / item.bytes_total) * 100))
                          : item.status === "done"
                            ? 100
                            : 0
                      return (
                        <div
                          key={item.id}
                          className="rounded-control border border-[var(--line)] bg-[var(--surface)] px-2.5 py-2 flex items-center gap-2"
                        >
                          {item.status === "done" ? (
                            <CheckCircle2 className="size-3.5 shrink-0 text-success-ink" aria-hidden />
                          ) : item.status === "active" ? (
                            <LoaderCircle className="size-3.5 shrink-0 animate-spin text-info-ink" aria-hidden />
                          ) : item.status === "error" ? (
                            <AlertTriangle className="size-3.5 shrink-0 text-danger-ink" aria-hidden />
                          ) : (
                            <FileText className="size-3.5 shrink-0 text-[var(--ink-muted)]" aria-hidden />
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="text-caption font-medium text-[var(--ink)] truncate">
                              {item.name}
                            </div>
                            <div className="text-micro text-[var(--ink-subtle)] tabular-nums">
                              {formatBytes(item.bytes_done)} / {formatBytes(item.bytes_total)}
                            </div>
                          </div>
                          <span className="text-micro font-semibold tabular-nums text-[var(--ink-muted)]">
                            {itemPct}%
                          </span>
                        </div>
                      )
                    })}
                  </div>
                ) : null}
              </div>
            )}
          </>
        ) : (
          /* Mode 2 & 3: Quick Picker / HTTP Server Browser */
          <div className="space-y-3">
            {/* Source Tabs: Disks vs Shared with Me */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <Button
                  variant={browseSource === "disks" ? "primary" : "secondary"}
                  size="sm"
                  icon={HardDrive}
                  onClick={() => {
                    setBrowseSource("disks")
                    setBrowsePath("")
                    void loadDirectory("disks", "")
                  }}
                >
                  {t("xfer_qp_root_disks")}
                </Button>
                <Button
                  variant={browseSource === "shared" ? "primary" : "secondary"}
                  size="sm"
                  icon={Users}
                  onClick={() => {
                    setBrowseSource("shared")
                    setBrowsePath("")
                    void loadDirectory("shared", "")
                  }}
                >
                  {t("xfer_qp_shared_with_me")}
                </Button>
              </div>
              <Button
                variant="ghost"
                size="sm"
                icon={RefreshCw}
                aria-label={t("xfer_qp_btn_refresh")}
                disabled={browseLoading}
                onClick={() => void loadDirectory(browseSource, browsePath)}
              >
                {t("xfer_qp_btn_refresh")}
              </Button>
            </div>

            {/* Breadcrumb + Role Chip */}
            <div className="rounded-card border border-[var(--line)] bg-[var(--surface-elevated)] px-3 py-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                {browseData?.current_path ? (
                  <button
                    type="button"
                    aria-label="Back"
                    onClick={() => void loadDirectory(browseSource, browseData.parent_path || "")}
                    className="p-1 rounded hover:bg-[var(--surface-hover)] text-[var(--ink-muted)] cursor-pointer shrink-0"
                  >
                    <ArrowLeft className="size-3.5" aria-hidden />
                  </button>
                ) : (
                  <FolderOpen className="size-3.5 shrink-0 text-[var(--ink-muted)]" aria-hidden />
                )}
                <Mono className="text-caption text-[var(--ink)] truncate">
                  {browseData?.current_path || (browseSource === "shared" ? t("xfer_qp_shared_with_me") : "/")}
                </Mono>
              </div>
              {browseData ? (
                <Chip
                  size="sm"
                  tone={roleTone(browseData.effective_role)}
                  data-testid="quick-picker-role-chip"
                >
                  {t(roleLabelKey(browseData.effective_role))}
                </Chip>
              ) : null}
            </div>

            {/* Viewer Role Lock Banner (T-13-13) */}
            {mode === "quick_picker" && Boolean(browseData?.current_path) && isViewerLocked ? (
              <div
                data-testid="quick-picker-viewer-banner"
                role="alert"
                className="rounded-card border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-2 flex items-center gap-2 text-caption text-[var(--warning-ink)]"
              >
                <ShieldAlert className="size-4 shrink-0" aria-hidden />
                <span>{t("xfer_qp_viewer_locked")}</span>
              </div>
            ) : null}

            {browseError ? (
              <div className="rounded-card border border-[var(--danger-border)] bg-[var(--danger-bg)] px-3 py-2 text-caption text-[var(--danger-ink)]">
                {browseError}
              </div>
            ) : null}

            {/* Directory Entries */}
            <div className="rounded-card border border-[var(--line)] bg-[var(--surface-elevated)] divide-y divide-[var(--line)] overflow-hidden">
              {browseLoading && !browseData ? (
                <div className="p-4 text-center text-caption text-[var(--ink-muted)]">
                  <LoaderCircle className="size-4 animate-spin inline mr-1.5" aria-hidden />
                  Loading...
                </div>
              ) : !browseData || browseData.items.length === 0 ? (
                <div className="p-4 text-center text-caption text-[var(--ink-muted)]">
                  {t("xfer_qp_empty_folder")}
                </div>
              ) : (
                browseData.items.map((entry) => (
                  <div
                    key={entry.relative_path}
                    className="px-3 py-2 flex items-center justify-between gap-2 hover:bg-[var(--surface-hover)]"
                  >
                    <button
                      type="button"
                      disabled={!entry.is_dir}
                      onClick={() => {
                        if (entry.is_dir) {
                          void loadDirectory(browseSource, entry.relative_path)
                        }
                      }}
                      className={cx(
                        "flex items-center gap-2 min-w-0 flex-1 text-left",
                        entry.is_dir ? "cursor-pointer" : "cursor-default",
                      )}
                    >
                      {entry.is_dir ? (
                        <Folder className="size-4 shrink-0 text-warning" aria-hidden />
                      ) : (
                        <FileText className="size-4 shrink-0 text-[var(--ink-muted)]" aria-hidden />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="text-caption font-medium text-[var(--ink)] truncate">
                          {entry.name}
                        </div>
                        {entry.owner_username ? (
                          <div className="text-micro text-[var(--ink-subtle)] truncate">
                            {entry.owner_username}
                          </div>
                        ) : !entry.is_dir && typeof entry.size === "number" ? (
                          <div className="text-micro text-[var(--ink-subtle)] tabular-nums">
                            {formatBytes(entry.size)}
                          </div>
                        ) : null}
                      </div>
                    </button>

                    {entry.effective_role ? (
                      <Chip size="sm" tone={roleTone(entry.effective_role)}>
                        {t(roleLabelKey(entry.effective_role))}
                      </Chip>
                    ) : null}

                    {mode === "browse" ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={Copy}
                        disabled={copyingPath === entry.relative_path}
                        onClick={() => void handleCopyEntryToDesktop(entry)}
                      >
                        {t("xfer_qp_btn_copy_desktop")}
                      </Button>
                    ) : null}
                  </div>
                ))
              )}
            </div>

            {/* Quick Picker Paste Here Action */}
            {mode === "quick_picker" ? (
              <div className="pt-1">
                <SectionLabel>{t("xfer_title_quick_picker")}</SectionLabel>
                <Button
                  variant="primary"
                  block
                  className="mt-1.5"
                  disabled={!browseData || !browseData.writable || browseLoading || pasting}
                  onClick={() => void handlePasteHere()}
                >
                  {t("xfer_qp_btn_paste_here")}
                </Button>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}

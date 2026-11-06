import { getTranslation } from "../i18n"
import { useCallback, useEffect, useId, useState } from "react"
import {
  ArchiveRestore,
  ArrowUpDown,
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Copy,
  Download,
  Eraser,
  ExternalLink,
  FileArchive,
  Folder,
  FolderPlus,
  FolderSync,
  Inbox,
  Key,
  Laptop,
  LoaderCircle,
  Pause,
  Play,
  Plus,
  Power,
  RefreshCw,
  Server,
  Settings2,
  Trash2,
  Upload,
  Globe,
  Wifi,
  Eye,
  EyeOff,
  Radio,
  Network,
  type LucideIcon,
} from "lucide-react"
import { FooterStatus, TrayChip } from "../FlyoutShell"
import { getCompanionApi } from "../api"
import { errorText, useAsyncAction, useCompanion, useNotice } from "../store"
import type { SyncthingFolderTask, SyncthingFullStatus, ServerItem, Tone } from "../types"
import {
  Button,
  Card,
  Chip,
  IconBadge,
  Mono,
  StatusDot,
  TextAction,
  Toggle,
  cx,
} from "../ui"
import { LaunchTile, ViewBody, tileSurface } from "./shared"

type AsyncState = "idle" | "busy" | "done"

function ActionRow({
  icon,
  tone,
  title,
  caption,
  busyCaption,
  doneCaption,
  tag,
  state,
  onClick,
}: {
  icon: LucideIcon
  tone: "success" | "warning"
  title: string
  caption: string
  busyCaption: string
  doneCaption: string
  tag?: string
  state: AsyncState
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-busy={state === "busy" || undefined}
      className="group flex w-full items-center gap-2.5 rounded-tile px-2 py-2 text-left transition-colors duration-150 outline-none hover:bg-surface-sunken focus-visible:ring-2 focus-visible:ring-info/45"
    >
      <IconBadge icon={icon} tone={tone} size="sm" />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-caption font-semibold text-ink">
          <span className="truncate">{title}</span>
          {tag && (
            <Chip size="sm" tone="warning" className="shrink-0 text-nano py-0 px-1.5">
              {tag}
            </Chip>
          )}
        </span>
        <span
          className={cx(
            "block text-micro",
            state === "done" ? "text-success-ink" : "text-ink-subtle",
          )}
        >
          {state === "busy"
            ? busyCaption
            : state === "done"
              ? doneCaption
              : caption}
        </span>
      </span>
      {state === "busy" ? (
        <LoaderCircle
          className="size-4 shrink-0 animate-spin text-info"
          aria-hidden
        />
      ) : state === "done" ? (
        <CircleCheck className="size-4 shrink-0 text-success" aria-hidden />
      ) : (
        <ChevronRight
          className="size-4 shrink-0 text-ink-faint transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-ink-muted"
          aria-hidden
        />
      )}
    </button>
  )
}

const SYNC_DOT_COLS = 42
const SYNC_DOT_ROWS = 3

const SYNC_FILL_TONES: Record<Tone, string> = {
  success: "fill-success",
  warning: "fill-warning",
  danger: "fill-danger",
  info: "fill-info",
  neutral: "fill-line-strong",
}

function SyncDotBar({
  syncPct,
  syncDirection,
  active,
}: {
  syncPct: number
  syncDirection: "upload" | "download" | "both" | "idle"
  active: boolean
}) {
  const colStep = 6
  const rowStep = 6
  const r = 2.1
  const totalDots = SYNC_DOT_COLS * SYNC_DOT_ROWS
  const totalLit = active
    ? Math.round((Math.max(0, Math.min(100, syncPct)) / 100) * totalDots)
    : 0

  const tone: Tone = !active
    ? "neutral"
    : syncDirection === "download"
      ? "success"
      : "info"

  return (
    <svg
      viewBox={`0 0 ${SYNC_DOT_COLS * colStep} ${SYNC_DOT_ROWS * rowStep}`}
      className="w-full h-[18px] block overflow-visible"
      aria-hidden="true"
    >
      {Array.from({ length: SYNC_DOT_COLS }, (_, col) => {
        const colLitCount = Math.min(
          SYNC_DOT_ROWS,
          Math.max(0, totalLit - col * SYNC_DOT_ROWS),
        )
        return Array.from({ length: SYNC_DOT_ROWS }, (_, row) => {
          const heightFromBottom = SYNC_DOT_ROWS - row
          const lit = heightFromBottom <= colLitCount
          const dotX = 3 + col * colStep
          const dotY = 3 + row * rowStep
          return (
            <circle
              key={`${col}-${row}`}
              cx={dotX}
              cy={dotY}
              r={r}
              className={cx(
                "transition-colors duration-300",
                lit ? SYNC_FILL_TONES[tone] : "fill-line",
              )}
            />
          )
        })
      })}
    </svg>
  )
}

export default function BackupView() {
  const api = getCompanionApi()
  const {
    metrics,
    settings,
    setSetting,
    isOnline,
  } = useCompanion()
  const t = getTranslation(settings?.language)
  const { notify } = useNotice()

  // Full Syncthing Status & Tasks
  const [fullStatus, setFullStatus] = useState<SyncthingFullStatus | null>(null)
  const [tasks, setTasks] = useState<SyncthingFolderTask[]>([])
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [showAddDevice, setShowAddDevice] = useState(false)
  const [newDevId, setNewDevId] = useState("")
  const [newDevName, setNewDevName] = useState("")
  const [isAddingDev, setIsAddingDev] = useState(false)
  const [deviceTab, setDeviceTab] = useState<"local" | "server">("local")
  const [deviceActionBusy, setDeviceActionBusy] = useState<string | null>(null)
  const [pairingBusy, setPairingBusy] = useState(false)
  const [daemonBusy, setDaemonBusy] = useState(false)
  const [rescanAllBusy, setRescanAllBusy] = useState(false)
  const [creatingTask, setCreatingTask] = useState(false)

  // New Task Modal State
  const [showCreateTaskModal, setShowCreateTaskModal] = useState(false)
  const [newTaskPath, setNewTaskPath] = useState("")
  const [newTaskLabel, setNewTaskLabel] = useState("")
  const [newTaskServerPath, setNewTaskServerPath] = useState("")
  const [newSyncMode, setNewSyncMode] = useState<"sendonly" | "sendreceive">("sendonly")
  const [pickingFolder, setPickingFolder] = useState(false)
  const [filterActiveServerOnly, setFilterActiveServerOnly] = useState(false)
  // Target Server Selection for Multi-Server Setup
  const [availableServers, setAvailableServers] = useState<ServerItem[]>([])
  const [selectedServerId, setSelectedServerId] = useState<string>("")
  const [modalTargetServerId, setModalTargetServerId] = useState<string>("")
  const [activeServerId, setActiveServerId] = useState<string>("")

  // REST API Key Config Modal State
  const [apiModal, setApiModal] = useState<"none" | "local" | "server">("none")
  const [apiLocalPort, setApiLocalPort] = useState("8384")
  const [apiLocalKey, setApiLocalKey] = useState("")
  const [apiServerPort, setApiServerPort] = useState("8384")
  const [apiServerKey, setApiServerKey] = useState("")
  const [apiServerName, setApiServerName] = useState("Server")
  const [savingApiKey, setSavingApiKey] = useState(false)
  const [serverRouteMode, setServerRouteMode] = useState<"auto" | "lan" | "wan">("auto")
  const [serverLanMode, setServerLanMode] = useState<"inherit" | "custom">("inherit")
  const [serverLanIp, setServerLanIp] = useState("")
  const [serverLanPort, setServerLanPort] = useState("8384")
  const [serverLanHttps, setServerLanHttps] = useState(false)
  const [serverWanUrl, setServerWanUrl] = useState("")
  const [serverWanPort, setServerWanPort] = useState("8384")
  const [serverWanHttps, setServerWanHttps] = useState(false)
  const [localAutoStart, setLocalAutoStart] = useState(true)
  const [localBinPath, setLocalBinPath] = useState("")
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "online" | "offline">("idle")
  const [testMessage, setTestMessage] = useState("")
  const [showPassword, setShowPassword] = useState(false)

  const autoCleanId = useId()

  // Poller untuk Syncthing telemetry, daftar tasks & server list
  const refreshStatus = useCallback(async () => {
    try {
      const [st, tk, srvDetails] = await Promise.all([
        api.getSyncthingFullStatus(),
        api.getSyncthingTasks(),
        api.getServerDetails().catch(() => null),
      ])
      if (st) setFullStatus(st)
      if (tk) setTasks(tk)
      if (srvDetails) {
        if (Array.isArray(srvDetails.servers)) {
          setAvailableServers(srvDetails.servers)
        }
        const actId = srvDetails.serverId || srvDetails.servers?.find((s: ServerItem) => s.active)?.id || ""
        setActiveServerId(actId)
        setSelectedServerId((prev) => prev || actId)
      }
    } catch (err) {
      // background silent fallback
    }
  }, [api])

  useEffect(() => {
    void refreshStatus()
    const timer = window.setInterval(() => {
      void refreshStatus()
    }, 2500)
    return () => window.clearInterval(timer)
  }, [refreshStatus])

  // Reset copied tooltip
  useEffect(() => {
    if (!copiedId) return
    const timer = window.setTimeout(() => setCopiedId(null), 1600)
    return () => window.clearTimeout(timer)
  }, [copiedId])

  const copyText = (txt: string, label: string) => {
    if (!txt) return
    navigator.clipboard?.writeText(txt).catch(() => undefined)
    setCopiedId(txt)
    notify(`${label} disalin`)
  }

  // Backup & Restore Actions
  const [backupState, setBackupState] = useState<AsyncState>("idle")
  const [restoreState, setRestoreState] = useState<AsyncState>("idle")
  const [cacheState, runCache] = useAsyncAction(api.clearCache)

  const handleRunBackup = async () => {
    setBackupState("busy")
    try {
      const res = await api.executeBackupDialog()
      if (res && res.cancelled) {
        setBackupState("idle")
        return
      }
      if (res && res.success) {
        setBackupState("done")
        notify(`Backup tersimpan · ${res.file || "myserver-backup.zip"}`, "success")
        window.setTimeout(() => setBackupState("idle"), 2500)
      } else {
        setBackupState("idle")
        notify(res?.error || "Gagal membuat cadangan.", "danger")
      }
    } catch (err) {
      setBackupState("idle")
      notify(errorText(err), "danger")
    }
  }

  const handleRunRestore = async () => {
    setRestoreState("busy")
    try {
      const res = await api.executeRestoreDialog()
      if (res && res.cancelled) {
        setRestoreState("idle")
        return
      }
      if (res && res.success) {
        setRestoreState("done")
        notify(`Data dipulihkan · Aplikasi memulai ulang otomatis…`, "success")
      } else {
        setRestoreState("idle")
        notify(res?.error || "Gagal memulihkan cadangan.", "danger")
      }
    } catch (err) {
      setRestoreState("idle")
      notify(errorText(err), "danger")
    }
  }

  // Pairing 1-Click
  const handlePairing = async () => {
    setPairingBusy(true)
    try {
      const res = await api.pairLaptopAndServer()
      if (res && res.success) {
        notify("Laptop & Server berhasil di-pair! Sinkronisasi siap.", "success")
        await refreshStatus()
      } else {
        notify(res?.error || "Gagal menghubungkan Laptop dan Server.", "warning")
      }
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setPairingBusy(false)
    }
  }

  // Toggle Daemon
  const handleToggleDaemon = async () => {
    setDaemonBusy(true)
    try {
      const res = await api.toggleLocalSyncthingDaemon("toggle")
      notify(
        res.running
          ? "Daemon Syncthing lokal berhasil dijalankan"
          : "Daemon Syncthing lokal dihentikan",
        res.running ? "success" : "neutral",
      )
      await refreshStatus()
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setDaemonBusy(false)
    }
  }

  // Open Task Creation Form
  const handleOpenCreateTask = () => {
    setNewTaskPath("")
    setNewTaskLabel("")
    setNewTaskServerPath("")
    setNewSyncMode("sendonly")
    const defId = activeServerId || (availableServers[0]?.id ?? "")
    setModalTargetServerId(defId)
    setSelectedServerId(defId)
    setShowCreateTaskModal(true)
  }

  // Browse Folder via native / backend dialog
  const handlePickFolder = async () => {
    setPickingFolder(true)
    try {
      const res = await api.chooseFolder("Pilih Folder di Laptop yang Ingin Dicadangkan ke Server")
      if (res && res.path) {
        const p = res.path.replace(/\\/g, "/")
        setNewTaskPath(p)
        const parts = p.split("/").filter(Boolean)
        const name = parts.length > 0 ? parts[parts.length - 1] : "Folder"
        if (!newTaskLabel.trim()) {
          setNewTaskLabel(name)
        }
        if (!newTaskServerPath.trim() || newTaskServerPath.startsWith("/DATA/Backups/")) {
          setNewTaskServerPath(`/DATA/Backups/${name}`)
        }
      }
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setPickingFolder(false)
    }
  }

  // Create Task Submit
  const handleConfirmCreateTask = async () => {
    const cleanLocal = newTaskPath.trim()
    if (!cleanLocal) {
      notify("Folder Laptop lokal wajib dipilih atau dimasukkan", "warning")
      return
    }
    const cleanLabel = newTaskLabel.trim() || cleanLocal.split(/[\\/]/).filter(Boolean).pop() || "Backup"
    const cleanServer = newTaskServerPath.trim() || `/DATA/Backups/${cleanLabel}`

    setCreatingTask(true)
    try {
      const res = await api.createSyncTask({
        folder_path: cleanLocal,
        task_label: cleanLabel,
        server_path: cleanServer,
        sync_mode: newSyncMode,
        target_server_id: modalTargetServerId || selectedServerId || activeServerId || undefined,
      })
      if (res && res.cancelled) {
        return
      }
      if (res && res.success) {
        notify(`Jalur backup '${res.label || cleanLabel}' berhasil dibuat! Sinkronisasi dimulai.`, "success")
        setShowCreateTaskModal(false)
        await refreshStatus()
      } else {
        notify(res?.error || "Gagal membuat jalur backup.", "danger")
      }
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setCreatingTask(false)
    }
  }

  // Rescan All Tasks
  const handleRescanAll = async () => {
    setRescanAllBusy(true)
    try {
      await api.rescanTask()
      notify("Pemindaian ulang seluruh folder diaktifkan", "info")
      await refreshStatus()
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setRescanAllBusy(false)
    }
  }

  // Add Device Submit
  const handleAddDeviceSubmit = async () => {
    if (!newDevId.trim()) {
      notify("Device ID wajib diisi", "warning")
      return
    }
    setIsAddingDev(true)
    try {
      const res = await api.addSyncthingDevice(newDevId.trim(), newDevName.trim(), "both")
      if (res && res.success) {
        notify("Perangkat berhasil didaftarkan ke Syncthing", "success")
        setNewDevId("")
        setNewDevName("")
        setShowAddDevice(false)
        await refreshStatus()
      } else {
        notify(res?.error || "Gagal mendaftarkan perangkat", "danger")
      }
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setIsAddingDev(false)
    }
  }

  // Toggle Pause/Resume Device
  const handleTogglePauseDevice = async (devId: string, currentPaused: boolean) => {
    setDeviceActionBusy(devId)
    try {
      await api.setDevicePaused(devId, !currentPaused, deviceTab)
      notify(currentPaused ? "Perangkat dilanjutkan" : "Perangkat dijeda", "info")
      await refreshStatus()
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setDeviceActionBusy(null)
    }
  }

  // Remove Device
  const handleRemoveDevice = async (devId: string, devName: string) => {
    if (!window.confirm(`Hapus perangkat '${devName || devId.slice(0, 7)}' dari daftar sinkronisasi ${deviceTab === "local" ? "Laptop" : "Server"}?`)) {
      return
    }
    setDeviceActionBusy(devId)
    try {
      await api.removeSyncthingDevice(devId, deviceTab)
      notify(`Perangkat '${devName || devId.slice(0, 7)}' dihapus`, "success")
      await refreshStatus()
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setDeviceActionBusy(null)
    }
  }

  // Open API Key Setup Modal
  const openApiSetup = async (target: "local" | "server") => {
    try {
      const cfg = await api.getSyncthingConfig()
      if (cfg) {
        if (cfg.local) {
          setApiLocalPort(cfg.local.port || "8384")
          setApiLocalKey(cfg.local.api_key || "")
          setLocalAutoStart(cfg.local.auto_start ?? true)
          setLocalBinPath(cfg.local.binary_path || "")
        }
        if (cfg.server) {
          setApiServerName(cfg.server.server_name || "Server")
          setApiServerPort(cfg.server.port || cfg.server.lan_port || "8384")
          setApiServerKey(cfg.server.api_key || "")
          setServerRouteMode((cfg.server.route_mode as any) || "auto")
          setServerLanMode((cfg.server.lan_mode as any) || "inherit")
          setServerLanIp(cfg.server.lan_ip || "")
          setServerLanPort(cfg.server.lan_port || cfg.server.port || "8384")
          setServerLanHttps(Boolean(cfg.server.lan_https))
          setServerWanUrl(cfg.server.wan_url || "")
          setServerWanPort(cfg.server.wan_port || "8384")
          setServerWanHttps(Boolean(cfg.server.wan_https))
        }
      }
    } catch (err) {
      console.warn("[BackupView] Failed to load Syncthing config:", err)
    }
    setTestStatus("idle")
    setTestMessage("")
    setShowPassword(false)
    setApiModal(target)
  }

  const handleSaveServerRoute = async () => {
    setSavingApiKey(true)
    try {
      await api.saveSyncthingServerRoute({
        route_mode: serverRouteMode,
        lan_mode: serverLanMode,
        lan_ip: serverLanIp.trim(),
        lan_port: serverLanPort.trim() || "8384",
        lan_https: serverLanHttps,
        wan_url: serverWanUrl.trim(),
        wan_port: serverWanPort.trim() || "8384",
        wan_https: serverWanHttps,
        api_key: apiServerKey.trim(),
      })
      notify(t("syncthing_save_btn", "Konfigurasi rute server berhasil disimpan"), "success")
      setApiModal("none")
      window.dispatchEvent(new CustomEvent("myserver:refresh"))
      await refreshStatus()
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setSavingApiKey(false)
    }
  }

  const handleSaveLocalConfig = async () => {
    setSavingApiKey(true)
    try {
      await api.saveSyncthingLocalConfig({
        port: apiLocalPort.trim() || "8384",
        api_key: apiLocalKey.trim(),
        auto_start: localAutoStart,
        binary_path: localBinPath.trim(),
      })
      notify(t("syncthing_save_btn", "Konfigurasi Syncthing lokal berhasil disimpan"), "success")
      setApiModal("none")
      window.dispatchEvent(new CustomEvent("myserver:refresh"))
      await refreshStatus()
    } catch (err) {
      notify(errorText(err), "danger")
    } finally {
      setSavingApiKey(false)
    }
  }

  const handleTestConnection = async () => {
    setTestStatus("testing")
    setTestMessage(t("syncthing_testing", "Menguji…"))
    try {
      let targetHost = ""
      let targetPort = "8384"
      let useHttps = false
      if (serverRouteMode === "wan" || (!serverLanIp && serverWanUrl)) {
        targetHost = serverWanUrl.trim()
        targetPort = serverWanPort.trim() || "8384"
        useHttps = serverWanHttps
      } else {
        targetHost = serverLanIp.trim() || (fullStatus?.server?.address || "127.0.0.1")
        targetPort = serverLanPort.trim() || "8384"
        useHttps = serverLanHttps
      }
      if (!targetHost) {
        setTestStatus("offline")
        setTestMessage("Target URL atau host kosong")
        return
      }
      const testUrl = `${useHttps ? "https" : "http"}://${targetHost}:${targetPort}`
      const res = await api.testSyncthingTarget(testUrl, useHttps)
      if (res && res.online) {
        setTestStatus("online")
        setTestMessage(res.message || `Online (${res.latency_ms}ms)`)
      } else {
        setTestStatus("offline")
        setTestMessage(res?.message || t("syncthing_test_failed", "Koneksi gagal"))
      }
    } catch (err: any) {
      setTestStatus("offline")
      setTestMessage(err?.message || "Koneksi gagal")
    }
  }

  const locNode = fullStatus?.local
  const srvNode = fullStatus?.server
  const daemon = fullStatus?.daemon
  const isPaired = fullStatus?.paired ?? false
  const locId = locNode?.device_id || ""
  const srvId = srvNode?.device_id || ""

  // Pending devices count & items
  const locPending = locNode?.pending_devices || {}
  const srvPending = srvNode?.pending_devices || {}
  const totalPending = Object.keys(locPending).length + Object.keys(srvPending).length

  // Metrics extraction
  const syncMetrics = locNode?.metrics?.active ? locNode.metrics : srvNode?.metrics
  const isSyncActive = Boolean(syncMetrics?.active)
  const syncPct = syncMetrics?.percentage ?? 100
  const syncDirection = syncMetrics?.direction || "none"

  const locDevices = locNode?.devices || []
  const srvDevices = srvNode?.devices || []
  const activeDevices = deviceTab === "local" ? locDevices : srvDevices

  const activeServerTasks = tasks.filter((t) => t.isActiveServer || (t.targetServerId && t.targetServerId === activeServerId))
  const otherServerTasks = tasks.filter((t) => !t.isActiveServer && (!t.targetServerId || t.targetServerId !== activeServerId))
  const displayedTasks = filterActiveServerOnly && otherServerTasks.length > 0 ? activeServerTasks : tasks

  const displayUpSpeed =
    isSyncActive && locNode?.metrics?.out_speed
      ? locNode.metrics.out_speed
      : "0 B/s"

  const displayDownSpeed =
    isSyncActive && locNode?.metrics?.in_speed
      ? locNode.metrics.in_speed
      : "0 B/s"

  return (
    <>
      <ViewBody>
        {/* ATOMIC BACKUP & RESTORE */}
        <Card className="p-1.5">
          <div className="flex items-center justify-between px-2 pt-1 pb-0.5">
            <span className="text-nano font-bold tracking-[0.12em] text-ink-subtle uppercase">
              {t("atomic_backup_title", "Atomic Backup & Maintenance")}
            </span>
            <span className="font-mono text-nano text-ink-faint">
              clean-zip / .bak
            </span>
          </div>
          <ActionRow
            icon={FileArchive}
            tone="success"
            title={t("backup_config_title", "Backup Configuration (.zip)")}
            caption={t("backup_config_caption", "Clean export without browser cache")}
            busyCaption={t("backup_config_busy", "Filtering & compressing configuration…")}
            doneCaption={t("backup_config_done", "Saved · myserver-backup.zip")}
            state={backupState}
            onClick={handleRunBackup}
          />
          <div className="mx-2 h-px bg-line" />
          <ActionRow
            icon={ArchiveRestore}
            tone="warning"
            title={t("restore_config_title", "Restore Configuration (.zip)")}
            tag=".bak"
            caption={t("restore_config_caption", "Automatic rollback if restore fails")}
            busyCaption={t("restore_config_busy", "Validating archive & creating rollback…")}
            doneCaption={t("restore_config_done", "Data restored · Ready to restart")}
            state={restoreState}
            onClick={handleRunRestore}
          />
        </Card>

        {/* WEBVIEW CACHE & AUTO-CLEAN */}
        <div className="grid grid-cols-2 gap-2.5">
          <LaunchTile
            icon={Eraser}
            tone="danger"
            title={t("clear_cache_title", "Clear WebView2 Cache")}
            caption="WebView2"
            state={cacheState}
            onClick={() =>
              runCache((r) =>
                notify(`${t("cache_cleared_notice", "WebView2 cache cleared")} · ${r.freedMb} MB`),
              )
            }
          />
          <div className={cx("flex items-center gap-2 p-2.5", tileSurface)}>
            <label
              htmlFor={autoCleanId}
              className="min-w-0 flex-1 cursor-pointer text-label font-semibold text-ink"
            >{t("auto_clean_exit_title", "Auto-Clean on Exit")}</label>
            <Toggle
              id={autoCleanId}
              label={t("auto_clean_exit_title", "Auto-Clean on Exit")}
              checked={settings.autoCleanOnExit}
              onChange={(next) => {
                void setSetting("autoCleanOnExit", next).catch((e) =>
                  notify(errorText(e), "danger"),
                )
                notify(
                  next
                    ? t("auto_clean_active_notice", "Auto-Clean enabled on exit")
                    : t("auto_clean_inactive_notice", "Auto-Clean disabled"),
                  next ? "success" : "neutral",
                )
              }}
            />
          </div>
        </div>

        {/* SYNCTHING HUB CARD */}
        <Card className="flex flex-col gap-2.5 p-3">
          {/* Header Bar */}
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-label font-semibold text-ink">
              <FolderSync
                className="size-4 text-info"
                strokeWidth={2.2}
                aria-hidden />{t("syncthing_mgr_title", "Syncthing Manager")}</span>
            <div className="flex items-center gap-1.5">
              <Button
                variant={daemon?.running ? "soft" : "primary"}
                size="sm"
                icon={Power}
                state={daemonBusy ? "busy" : "idle"}
                onClick={handleToggleDaemon}
                className="h-6 text-micro px-2"
                title={daemon?.running ? t("stop_daemon_btn", "Stop Daemon") : t("start_daemon_btn", "Start Daemon")}
              >
                {daemon?.running ? "Stop Daemon" : "Start Daemon"}
              </Button>
            </div>
          </div>

          {/* Device Pairing Chips */}
          <div className="flex flex-wrap items-center gap-1.5">
            <Chip
              tone={locNode?.online ? "success" : "neutral"}
              icon={Laptop}
              onClick={() => copyText(locId, "Device ID Laptop")}
              title="Klik untuk menyalin Device ID Laptop"
            >
              Laptop: {locNode?.online ? (locId ? `${locId.slice(0, 7)}…` : "Online") : "Offline"}
            </Chip>

            <Chip
              tone={srvNode?.online ? "success" : "neutral"}
              icon={Server}
              onClick={() => copyText(srvId, "Device ID Server")}
              title="Klik untuk menyalin Device ID Server"
            >
              Server: {srvNode?.online ? (srvId ? `${srvId.slice(0, 7)}…` : "Online") : "Offline"}
            </Chip>

            {isPaired ? (
              <Chip tone="success" icon={Check} size="sm">
                {t("paired_status", "Terhubung (Paired)")}
              </Chip>
            ) : (
              <Button
                variant="info"
                size="sm"
                icon={FolderSync}
                state={pairingBusy ? "busy" : "idle"}
                onClick={handlePairing}
                className="h-6 text-micro px-2"
              >
                {t("pair_device_btn", "Pair Device")}
              </Button>
            )}
          </div>

          {/* REST API KEYS INPUT BUTTONS ROW */}
          <div className="flex flex-wrap items-center justify-between gap-1.5 rounded-tile border border-info-line/50 bg-info-soft/25 px-2.5 py-1.5">
            <span className="text-micro font-semibold text-info-ink flex items-center gap-1">
              <Key className="size-3" />
              REST API Key:
            </span>
            <div className="flex items-center gap-1.5">
              <Button
                variant="secondary"
                size="sm"
                icon={Laptop}
                onClick={() => void openApiSetup("local")}
                className="h-6 px-2 text-micro bg-surface"
                title="Masukkan atau ubah REST API Key Syncthing Laptop"
              >
                API Laptop
              </Button>
              <Button
                variant={srvNode?.online ? "secondary" : "primary"}
                size="sm"
                icon={Server}
                onClick={() => void openApiSetup("server")}
                className="h-6 px-2 text-micro"
                title="Masukkan REST API Key Syncthing Server"
              >
                API Server
              </Button>
            </div>
          </div>



          {/* Live Throughput Bar */}
          <div className="flex flex-col gap-2 rounded-tile border border-line bg-surface-sunken p-2.5">
            <div className="flex items-center justify-between text-caption text-ink-subtle">
              <div className="flex items-center gap-2">
                <ArrowUpDown
                  className="size-3.5 shrink-0 text-info"
                  strokeWidth={2.4}
                  aria-label="Throughput"
                />
                <span className="flex items-center gap-1">
                  <Upload className="size-3 text-info" />
                  <Mono className="font-semibold text-ink">
                    {displayUpSpeed}
                  </Mono>
                </span>
                <span className="h-3 w-px bg-line-strong" aria-hidden />
                <span className="flex items-center gap-1">
                  <Download className="size-3 text-success" />
                  <Mono className="font-semibold text-ink">
                    {displayDownSpeed}
                  </Mono>
                </span>
              </div>
              <span className="text-micro font-medium text-ink-muted">
                {isSyncActive
                  ? `${syncDirection === "upload" ? "Mengunggah" : syncDirection === "download" ? "Mengunduh" : "Sinkronisasi"} · ${syncPct}%`
                  : "Idle · Up-to-date"}
              </span>
            </div>

            {/* Sync Progress 3-Row LED Dot Bar */}
            <div className="w-full px-0.5 pt-0.5">
              <SyncDotBar
                syncPct={syncPct}
                syncDirection={syncDirection}
                active={isSyncActive}
              />
            </div>
          </div>

          {/* Global Quick Action Links */}
          <div className="flex flex-wrap items-center justify-between border-t border-line pt-2 text-micro">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void api.openSyncthingWebGui("server")}
                className="inline-flex items-center gap-1 text-ink-muted hover:text-ink hover:underline"
              >
                <ExternalLink className="size-3" />
                GUI Server
              </button>
              <span className="text-ink-faint">·</span>
              <button
                type="button"
                onClick={() => void api.openSyncthingWebGui("local")}
                className="inline-flex items-center gap-1 text-ink-muted hover:text-ink hover:underline"
              >
                <ExternalLink className="size-3" />
                GUI Laptop
              </button>
            </div>

            <Button
              variant="soft"
              size="sm"
              icon={RefreshCw}
              state={rescanAllBusy ? "busy" : "idle"}
              onClick={handleRescanAll}
              className="h-6 text-micro px-2"
              title={t("rescan_all_title", "Rescan all directory paths")}
            >
              {t("rescan_all_btn", "Rescan All")}
            </Button>
          </div>
        </Card>

        {/* INCOMING DEVICE REQUESTS (PENDING APPROVAL) */}
        {totalPending > 0 && (
          <Card className="flex flex-col gap-2 border-warning-line/70 bg-warning-soft/30 p-2.5">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-label font-semibold text-warning-ink">
                <CircleAlert className="size-4 shrink-0 text-warning" />
                {t("pending_device_requests", "Permintaan Sambungan Perangkat")} ({totalPending})
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              {Object.entries(locPending).map(([devId, devInfo]) => (
                <div
                  key={`loc-${devId}`}
                  className="flex items-center justify-between rounded-tile border border-line bg-surface p-2 text-caption"
                >
                  <div className="min-w-0 flex-1 pr-2">
                    <span className="block truncate font-semibold text-ink">
                      {devInfo.name || t("new_device_label", "Perangkat Baru")} (Laptop)
                    </span>
                    <Mono className="text-micro text-ink-subtle">
                      {devId.slice(0, 15)}…
                    </Mono>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="primary"
                      size="sm"
                      className="h-6 px-2 text-micro"
                      onClick={() => {
                        void api
                          .resolvePendingDevice(devId, "accept", "local", devInfo.name)
                          .then(() => {
                            notify("Perangkat diterima di Laptop", "success")
                            void refreshStatus()
                          })
                      }}
                    >
                      Terima
                    </Button>
                    <Button
                      variant="soft"
                      size="sm"
                      className="h-6 px-2 text-micro text-danger-ink"
                      onClick={() => {
                        void api
                          .resolvePendingDevice(devId, "reject", "local")
                          .then(() => {
                            notify("Permintaan sambungan ditolak", "neutral")
                            void refreshStatus()
                          })
                      }}
                    >
                      Tolak
                    </Button>
                  </div>
                </div>
              ))}

              {Object.entries(srvPending).map(([devId, devInfo]) => (
                <div
                  key={`srv-${devId}`}
                  className="flex items-center justify-between rounded-tile border border-line bg-surface p-2 text-caption"
                >
                  <div className="min-w-0 flex-1 pr-2">
                    <span className="block truncate font-semibold text-ink">
                      {devInfo.name || t("new_device_label", "Perangkat Baru")} (Server)
                    </span>
                    <Mono className="text-micro text-ink-subtle">
                      {devId.slice(0, 15)}…
                    </Mono>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="primary"
                      size="sm"
                      className="h-6 px-2 text-micro"
                      onClick={() => {
                        void api
                          .resolvePendingDevice(devId, "accept", "server", devInfo.name)
                          .then(() => {
                            notify("Perangkat diterima di Server", "success")
                            void refreshStatus()
                          })
                      }}
                    >
                      Terima
                    </Button>
                    <Button
                      variant="soft"
                      size="sm"
                      className="h-6 px-2 text-micro text-danger-ink"
                      onClick={() => {
                        void api
                          .resolvePendingDevice(devId, "reject", "server")
                          .then(() => {
                            notify("Permintaan sambungan ditolak", "neutral")
                            void refreshStatus()
                          })
                      }}
                    >
                      Tolak
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* SYNC TASKS (BACKUP FOLDERS) LIST */}
        <Card className="flex flex-col gap-2.5 p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="flex items-center gap-1.5 text-label font-semibold text-ink">
                <Folder className="size-4 text-info" strokeWidth={2.2} />
                {t("backup_paths", "Backup Paths")} ({displayedTasks.length})
              </span>
              {otherServerTasks.length > 0 && (
                <button
                  type="button"
                  onClick={() => setFilterActiveServerOnly(!filterActiveServerOnly)}
                  className="rounded-full bg-surface-sunken border border-line px-2 py-0.5 text-micro font-medium text-ink-subtle hover:text-ink hover:border-line-strong transition cursor-pointer"
                  title={t("filter_active_server_title", "Click to switch server path display filter")}
                >
                  {filterActiveServerOnly ? `${t("filter_active_server_badge", "Active Server")} (${activeServerTasks.length})` : `${t("filter_all_servers_badge", "All")} (${tasks.length})`}
                </button>
              )}
            </div>
            <Button
              variant="secondary"
              size="sm"
              icon={FolderPlus}
              state={creatingTask ? "busy" : "idle"}
              onClick={handleOpenCreateTask}
              className="h-6 px-2 text-micro font-medium"
            >
              {t("add_path_btn", "+ Add Path")}
            </Button>
          </div>

          {/* INLINE MODAL / WIZARD: TAMBAH JALUR BACKUP BARU */}
          {showCreateTaskModal && (
            <div className="flex flex-col gap-2.5 rounded-tile border border-info-line bg-surface p-3 text-caption shadow-sm">
              <div className="flex items-center justify-between border-b border-line pb-1.5">
                <span className="flex items-center gap-1.5 font-semibold text-ink text-label">
                  <FolderPlus className="size-4 text-info" />
                  {t("modal_add_path_title", "Add New Backup Path")}
                </span>
                <button
                  type="button"
                  onClick={() => setShowCreateTaskModal(false)}
                  className="text-micro text-ink-muted hover:text-ink"
                >
                  ✕ {t("cancel_modal", "Cancel")}
                </button>
              </div>

              {/* Warning if Server API key missing */}
              {(!apiServerKey.trim() && !srvNode?.online) && (
                <div className="flex items-start justify-between rounded-card border border-warning-line/80 bg-warning-soft/30 p-2 text-micro text-warning-ink">
                  <div className="flex items-center gap-1.5">
                    <CircleAlert className="size-3.5 shrink-0 text-warning" />
                    <span>REST API Key Server belum terkonfigurasi.</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setShowCreateTaskModal(false)
                      void openApiSetup("server")
                    }}
                    className="font-semibold underline hover:text-ink shrink-0 ml-2"
                  >
                    Atur Sekarang
                  </button>
                </div>
              )}

              {/* Target Server Selector (Multi-Server Setup) */}
              {availableServers.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-micro font-semibold text-ink-subtle">
                      {t("sync_target_server", "Pilih Server Tujuan:")}
                    </label>
                    <span className="text-[10px] text-ink-muted">
                      {t("sync_target_server_hint", "Folder cadangan akan disinkronkan langsung ke server ini")}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {availableServers.map((s) => {
                      const isSelected = (modalTargetServerId || selectedServerId || activeServerId) === s.id
                      const isActiveGlobal = s.active || activeServerId === s.id
                      return (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => {
                            setModalTargetServerId(s.id)
                            setSelectedServerId(s.id)
                          }}
                          className={cx(
                            "flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-caption font-medium transition-all cursor-pointer",
                            isSelected
                              ? "border-brand bg-brand/10 text-brand font-semibold shadow-xs"
                              : "border-line bg-surface hover:border-line-strong text-ink-subtle"
                          )}
                        >
                          <Server className="size-3.5" />
                          <span>{s.name}</span>
                          {isActiveGlobal && (
                            <span className="text-[9px] bg-brand/20 text-brand px-1 py-0.2 rounded font-mono font-medium">
                              {t("sync_active_server_badge", "Aktif")}
                            </span>
                          )}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Folder Laptop (Lokal) with Browse Button */}
              <div className="flex flex-col gap-1">
                <label className="text-micro font-semibold text-ink-subtle">
                  {t("laptop_local_folder", "Folder Laptop (Lokal):")}
                </label>
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={newTaskPath}
                    onChange={(e) => {
                      const p = e.target.value
                      setNewTaskPath(p)
                      const parts = p.split(/[\\/]/).filter(Boolean)
                      const name = parts.length > 0 ? parts[parts.length - 1] : ""
                      if (name && (!newTaskLabel || newTaskLabel === "")) {
                        setNewTaskLabel(name)
                      }
                      if (name && (!newTaskServerPath || newTaskServerPath.startsWith("/DATA/Backups/"))) {
                        setNewTaskServerPath(`/DATA/Backups/${name}`)
                      }
                    }}
                    placeholder="Contoh: D:\Data Kerja atau C:\Users\NamaUser\Documents"
                    className="flex-1 rounded-control border border-line bg-surface-sunken px-2 py-1 text-micro font-mono text-ink outline-none focus:border-info"
                  />
                  <Button
                    variant="soft"
                    size="sm"
                    icon={Folder}
                    state={pickingFolder ? "busy" : "idle"}
                    onClick={handlePickFolder}
                    className="h-6 shrink-0 px-2 text-micro"
                    title="Pilih folder melalui Windows Explorer"
                  >
                    Pilih...
                  </Button>
                </div>
              </div>

              {/* Nama Jalur & Server Target Path */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-micro font-semibold text-ink-subtle mb-0.5">
                    Nama Jalur (Label):
                  </label>
                  <input
                    type="text"
                    value={newTaskLabel}
                    onChange={(e) => {
                      const val = e.target.value
                      setNewTaskLabel(val)
                      if (!newTaskServerPath || newTaskServerPath.startsWith("/DATA/Backups/")) {
                        setNewTaskServerPath(`/DATA/Backups/${val}`)
                      }
                    }}
                    placeholder="Contoh: Dokumen Kerja"
                    className="w-full rounded-control border border-line bg-surface-sunken px-2 py-1 text-micro text-ink outline-none focus:border-info"
                  />
                </div>
                <div>
                  <label className="block text-micro font-semibold text-ink-subtle mb-0.5">
                    Lokasi di Server:
                  </label>
                  <input
                    type="text"
                    value={newTaskServerPath}
                    onChange={(e) => setNewTaskServerPath(e.target.value)}
                    placeholder="/DATA/Backups/..."
                    className="w-full rounded-control border border-line bg-surface-sunken px-2 py-1 text-micro font-mono text-ink outline-none focus:border-info"
                  />
                </div>
              </div>

              {/* Mode Sinkronisasi */}
              <div className="flex flex-col gap-1">
                <label className="text-micro font-semibold text-ink-subtle">
                  Mode Sinkronisasi:
                </label>
                <div className="grid grid-cols-2 gap-1.5">
                  <button
                    type="button"
                    onClick={() => setNewSyncMode("sendonly")}
                    className={`flex flex-col gap-0.5 rounded-tile border p-2 text-left transition-all ${
                      newSyncMode === "sendonly"
                        ? "border-info bg-info-soft/40 text-ink"
                        : "border-line bg-surface-sunken text-ink-muted hover:border-line-strong"
                    }`}
                  >
                    <span className="text-caption font-semibold flex items-center gap-1">
                      <Upload className="size-3 text-info" />
                      Mirroring (Send Only)
                    </span>
                    <span className="text-nano text-ink-subtle">
                      {t("mode_mirror_desc", "Send backup from Laptop to Server (safe one-way)")}
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setNewSyncMode("sendreceive")}
                    className={`flex flex-col gap-0.5 rounded-tile border p-2 text-left transition-all ${
                      newSyncMode === "sendreceive"
                        ? "border-success bg-success-soft/40 text-ink"
                        : "border-line bg-surface-sunken text-ink-muted hover:border-line-strong"
                    }`}
                  >
                    <span className="text-caption font-semibold flex items-center gap-1">
                      <ArrowUpDown className="size-3 text-success" />
                      {t("mode_twoway", "2-Way (Sync)")}
                    </span>
                    <span className="text-nano text-ink-subtle">
                      {t("mode_twoway_desc", "Send & receive file changes bidirectionally")}
                    </span>
                  </button>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-1.5 pt-1 border-t border-line">
                <Button
                  variant="soft"
                  size="sm"
                  onClick={() => setShowCreateTaskModal(false)}
                  className="h-6 px-2 text-micro"
                >
                  {t("cancel_modal", "Cancel")}
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  icon={FolderPlus}
                  state={creatingTask ? "busy" : "idle"}
                  onClick={handleConfirmCreateTask}
                  className="h-6 px-2.5 text-micro font-medium"
                >
                  {t("create_path_btn", "+ Create Backup Path")}
                </Button>
              </div>
            </div>
          )}

          {displayedTasks.length === 0 ? (
            <div className="rounded-tile border border-dashed border-line p-3 text-center text-caption text-ink-subtle">
              <p>{t("empty_backup_tasks_title", "No folder backup paths configured.")}</p>
              <p className="text-micro text-ink-faint mt-0.5">
                {t("empty_backup_tasks_desc", "Click '+ Add Path' to select a folder on Laptop and link it automatically to Server.")}
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {displayedTasks.map((task) => {
                const isMirror = task.type === "sendonly"
                const modeLabel = isMirror ? t("mode_mirror", "Mirroring (Send Only)") : t("mode_twoway", "2-Way (Sync)")
                return (
                  <div
                    key={task.id}
                    className="flex flex-col gap-1.5 rounded-tile border border-line bg-surface-sunken p-2.5 transition-colors hover:border-line-strong"
                  >
                    {/* Title & Mode */}
                    <div className="flex items-center justify-between gap-1.5">
                      <div className="flex items-center gap-1.5 min-w-0 flex-1 truncate">
                        <span className="truncate text-caption font-semibold text-ink" title={task.label}>
                          {task.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Chip size="sm" tone={isMirror ? "info" : "success"}>
                          {modeLabel}
                        </Chip>
                        <Chip size="sm" tone={task.paused ? "warning" : "neutral"}>
                          {task.paused ? "Jeda" : `${task.completion}%`}
                        </Chip>
                      </div>
                    </div>

                    {/* Path mapping */}
                    <div className="text-nano text-ink-muted">
                      <div className="truncate" title={task.localPath}>
                        💻 {task.localPath}
                      </div>
                      <div className="truncate text-ink-faint" title={task.serverPath || "/DATA/Backups"}>
                        🖥️ {task.serverPath || "/DATA/Backups"}
                      </div>
                    </div>

                    {/* Task Actions */}
                    <div className="flex items-center justify-between gap-1.5 border-t border-line/60 pt-1.5">
                      <div className="min-w-0 flex items-center">
                        {task.targetServerName && (
                          <span
                            className={cx(
                              "truncate rounded px-1.5 py-0.5 text-micro font-medium",
                              task.isActiveServer ? "bg-info-soft text-info" : "bg-neutral-soft text-ink-muted",
                            )}
                            title={task.targetServerName}
                          >
                            🎯 {task.targetServerName}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                        type="button"
                        onClick={() => {
                          void api
                            .openTaskFolder(task.localPath)
                            .then((res) => {
                              if (!res.success) notify("Folder tidak ditemukan", "warning")
                            })
                            .catch((e) => notify(errorText(e), "danger"))
                        }}
                        className="inline-flex size-6 items-center justify-center rounded-control text-ink-muted hover:bg-surface hover:text-ink cursor-pointer"
                        title={t("open_in_file_explorer", "Open in File Explorer")}
                      >
                        <Folder className="size-3.5" />
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          void api
                            .rescanTask(task.id)
                            .then(() => notify(`Pemindaian ulang '${task.label}' dimulai`, "info"))
                            .catch((e) => notify(errorText(e), "danger"))
                        }}
                        className="inline-flex size-6 items-center justify-center rounded-control text-ink-muted hover:bg-surface hover:text-ink cursor-pointer"
                        title={t("rescan_folder_title", "Pindai Ulang Folder")}
                      >
                        <RefreshCw className="size-3.5" />
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          void api
                            .setTaskPaused(task.id, !task.paused)
                            .then(() => {
                              notify(
                                task.paused
                                  ? `'${task.label}' dilanjutkan`
                                  : `'${task.label}' dijeda`,
                                "neutral",
                              )
                              void refreshStatus()
                            })
                            .catch((e) => notify(errorText(e), "danger"))
                        }}
                        className="inline-flex size-6 items-center justify-center rounded-control text-ink-muted hover:bg-surface hover:text-ink cursor-pointer"
                        title={task.paused ? "Lanjutkan Sinkronisasi" : "Jeda Sinkronisasi"}
                      >
                        {task.paused ? <Play className="size-3.5 text-success" /> : <Pause className="size-3.5" />}
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`Hapus jalur backup '${task.label}' dari Syncthing?`)) {
                            void api
                              .deleteSyncTask(task.id)
                              .then(() => {
                                notify(`Jalur '${task.label}' dihapus`, "neutral")
                                void refreshStatus()
                              })
                              .catch((e) => notify(errorText(e), "danger"))
                          }
                        }}
                        className="inline-flex size-6 items-center justify-center rounded-control text-ink-muted hover:bg-danger-soft hover:text-danger-ink cursor-pointer"
                        title={t("delete_backup_path_title", "Delete Backup Path")}
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        {/* DEVICE MANAGEMENT & COPY ID CARD */}
        <Card className="flex flex-col gap-2 p-3">
          <div className="flex items-center justify-between">
            <span className="text-label font-semibold text-ink">{t("connected_devices_title", "Perangkat Terhubung")}</span>
            <button
              type="button"
              onClick={() => setShowAddDevice(!showAddDevice)}
              className="inline-flex items-center gap-1 text-micro text-info font-medium hover:underline"
            >
              <Plus className="size-3" />
              {showAddDevice ? t("close_form_btn", "Tutup Form") : t("add_device_btn", "Tambah Perangkat")}
            </button>
          </div>

          {/* Form Tambah Perangkat Baru */}
          {showAddDevice && (
            <div className="flex flex-col gap-2 rounded-tile border border-info-line/60 bg-info-soft/20 p-2.5 text-caption">
              <div>
                <label className="block text-micro font-semibold text-ink-subtle mb-0.5">
                  Device ID Syncthing:
                </label>
                <input
                  type="text"
                  placeholder="Contoh: AAAAAAA-BBBBBBB-CCCCCC..."
                  value={newDevId}
                  onChange={(e) => setNewDevId(e.target.value)}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-micro font-mono text-ink outline-none focus:border-info"
                />
              </div>
              <div>
                <label className="block text-micro font-semibold text-ink-subtle mb-0.5">
                  {t("device_name_optional", "Nama Perangkat (Opsional):")}
                </label>
                <input
                  type="text"
                  placeholder="Contoh: HP Android / Laptop Kantor"
                  value={newDevName}
                  onChange={(e) => setNewDevName(e.target.value)}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-micro text-ink outline-none focus:border-info"
                />
              </div>
              <div className="flex justify-end gap-1.5 pt-1">
                <Button
                  variant="soft"
                  size="sm"
                  onClick={() => setShowAddDevice(false)}
                  className="h-6 px-2 text-micro"
                >
                  {t("cancel_modal", "Cancel")}
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  state={isAddingDev ? "busy" : "idle"}
                  onClick={handleAddDeviceSubmit}
                  className="h-6 px-2.5 text-micro"
                >
                  {t("save_device_btn", "Simpan Perangkat")}
                </Button>
              </div>
            </div>
          )}

          {/* Segmented Tab Laptop / Server */}
          <div className="flex items-center gap-1 rounded-lg border border-line bg-surface-sunken p-0.5 text-micro">
            <button
              type="button"
              onClick={() => setDeviceTab("local")}
              className={cx(
                "flex-1 rounded-md py-1 px-2 font-medium transition-colors text-center",
                deviceTab === "local"
                  ? "bg-surface text-ink font-semibold shadow-xs"
                  : "text-ink-subtle hover:text-ink"
              )}
            >
              Laptop ({locDevices.length})
            </button>
            <button
              type="button"
              onClick={() => setDeviceTab("server")}
              className={cx(
                "flex-1 rounded-md py-1 px-2 font-medium transition-colors text-center",
                deviceTab === "server"
                  ? "bg-surface text-ink font-semibold shadow-xs"
                  : "text-ink-subtle hover:text-ink"
              )}
            >
              Server ({srvDevices.length})
            </button>
          </div>

          {/* Device Items List */}
          {activeDevices.length === 0 ? (
            <div className="py-2.5 text-center text-micro text-ink-muted">
              Belum ada perangkat terdaftar di {deviceTab === "local" ? "Laptop" : "Server"}.
            </div>
          ) : (
            <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto pr-0.5">
              {activeDevices.map((d) => {
                const isSelf = d.is_self || (deviceTab === "local" ? d.deviceID === locId : d.deviceID === srvId)
                const isConnected = Boolean(d.connected)
                const isPaused = Boolean(d.paused)
                const isBusy = deviceActionBusy === d.deviceID
                const shortId = d.deviceID ? `${d.deviceID.slice(0, 7)}…${d.deviceID.slice(-5)}` : "—"

                return (
                  <div
                    key={d.deviceID}
                    className="flex items-center justify-between gap-2 rounded-tile border border-line bg-surface-sunken/60 p-2 text-caption"
                  >
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <div
                        className={cx(
                          "flex size-7 shrink-0 items-center justify-center rounded-control",
                          isConnected
                            ? "bg-success-soft text-success-ink"
                            : isPaused
                              ? "bg-warning-soft text-warning-ink"
                              : "bg-neutral-soft text-ink-subtle"
                        )}
                      >
                        {deviceTab === "local" ? (
                          isSelf ? <Laptop className="size-3.5" /> : <Server className="size-3.5" />
                        ) : (
                          isSelf ? <Server className="size-3.5" /> : <Laptop className="size-3.5" />
                        )}
                      </div>

                      <div className="flex flex-col min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-semibold text-ink text-micro truncate" title={d.name || d.deviceID}>
                            {d.name || shortId}
                          </span>

                          {isSelf && (
                            <span className="rounded bg-primary-soft/80 px-1 py-0.2 text-micro font-medium text-primary">
                              {t("this_device_label", "Perangkat Ini")}
                            </span>
                          )}

                          {!isSelf && isConnected && (
                            <span className="inline-flex items-center gap-1 rounded bg-success-soft px-1 py-0.2 text-micro font-medium text-success-ink">
                              <span className="size-1.5 rounded-full bg-success" />
                              Terhubung
                            </span>
                          )}

                          {!isSelf && !isConnected && isPaused && (
                            <span className="inline-flex items-center gap-1 rounded bg-warning-soft px-1 py-0.2 text-micro font-medium text-warning-ink">
                              <span className="size-1.5 rounded-full bg-warning" />
                              Dijeda
                            </span>
                          )}

                          {!isSelf && !isConnected && !isPaused && (
                            <span className="inline-flex items-center gap-1 rounded bg-neutral-soft px-1 py-0.2 text-micro font-medium text-ink-muted">
                              <span className="size-1.5 rounded-full bg-ink-subtle" />
                              Terputus
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-1.5 text-[11px] text-ink-subtle">
                          <span className="font-mono text-micro text-ink-muted">{shortId}</span>
                          {d.address && (
                            <>
                              <span className="text-line-strong">·</span>
                              <span className="truncate max-w-[130px]" title={d.address}>
                                {d.address}
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => copyText(d.deviceID, "Device ID")}
                        className="inline-flex size-6 items-center justify-center rounded-control text-ink-muted hover:bg-surface hover:text-ink"
                        title="Salin Device ID Lengkap"
                      >
                        {copiedId === d.deviceID ? <Check className="size-3 text-success" /> : <Copy className="size-3" />}
                      </button>

                      {!isSelf && (
                        <>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => handleTogglePauseDevice(d.deviceID, isPaused)}
                            className="inline-flex size-6 items-center justify-center rounded-control text-ink-muted hover:bg-surface hover:text-ink"
                            title={isPaused ? "Lanjutkan Sinkronisasi" : "Jeda Sinkronisasi"}
                          >
                            {isPaused ? <Play className="size-3 text-success" /> : <Pause className="size-3" />}
                          </button>
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => handleRemoveDevice(d.deviceID, d.name)}
                            className="inline-flex size-6 items-center justify-center rounded-control text-ink-muted hover:bg-danger-soft hover:text-danger-ink"
                            title={t("delete_device_title", "Hapus Perangkat")}
                          >
                            <Trash2 className="size-3" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Device ID Actions */}
          <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5 border-t border-line pt-2">
            <TextAction
              icon={copiedId === locId ? Check : Copy}
              tone={copiedId === locId ? "success" : "info"}
              onClick={() => copyText(locId, "Device ID Laptop")}
            >
              {copiedId === locId ? "Tersalin" : "Salin ID Laptop"}
            </TextAction>

            {srvId && (
              <TextAction
                icon={copiedId === srvId ? Check : Copy}
                tone={copiedId === srvId ? "success" : "info"}
                onClick={() => copyText(srvId, "Device ID Server")}
              >
                {copiedId === srvId ? "Tersalin" : "Salin ID Server"}
              </TextAction>
            )}
          </div>
        </Card>
      </ViewBody>

      <FooterStatus
        showNoticePill={false}
        title={t("data_sync_footer", "Data Synchronization")}
        chips={
          <>
            <TrayChip tone={daemon?.running ? "success" : "neutral"}>
              <span>
                Daemon: <Mono>{daemon?.running ? "8384" : "Off"}</Mono>
              </span>
            </TrayChip>
            <TrayChip tone={isPaired ? "success" : "warning"}>
              {isPaired ? "Pair: Ready" : "Unpaired"}
            </TrayChip>
            <TrayChip tone={isOnline ? "success" : "neutral"}>
              <span>
                Sync: <Mono>{isSyncActive ? `${syncPct}%` : "100%"}</Mono>
              </span>
            </TrayChip>
          </>
        }
      />
      {/* MODERN IN-APP MODAL: SERVER SYNCTHING DUAL-ROUTE */}
      {apiModal === "server" && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-3 backdrop-blur-xs motion-safe:animate-fade-in"
          onClick={() => setApiModal("none")}
        >
          <div
            className="flex w-full max-w-[340px] max-h-[92vh] flex-col gap-3 rounded-card border border-line bg-surface p-4 shadow-panel overflow-y-auto motion-safe:animate-flyout-in"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-line pb-2">
              <div className="flex items-center gap-2">
                <div className="flex size-7 items-center justify-center rounded-lg bg-info-soft text-info">
                  <Server className="size-4" />
                </div>
                <div>
                  <h3 className="text-caption font-bold text-ink">
                    {t("modal_server_syncthing_title", "Pengaturan Rute Ganda Backup Server")}
                  </h3>
                  <p className="text-nano text-ink-subtle">
                    {apiServerName}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setApiModal("none")}
                className="rounded p-1 text-ink-subtle hover:bg-surface-sunken hover:text-ink cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Route Selection Mode */}
            <div className="flex flex-col gap-1">
              <label className="text-micro font-semibold text-ink-subtle">
                {t("syncthing_route_mode", "Mode Pemilihan Rute:")}
              </label>
              <div className="grid grid-cols-3 gap-1 rounded-tile border border-line bg-surface-sunken p-1">
                {(["auto", "lan", "wan"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setServerRouteMode(mode)}
                    className={cx(
                      "rounded px-2 py-1 text-micro font-semibold transition-all cursor-pointer",
                      serverRouteMode === mode
                        ? "bg-surface text-ink shadow-xs"
                        : "text-ink-subtle hover:text-ink"
                    )}
                  >
                    {mode === "auto"
                      ? t("syncthing_route_auto", "Otomatis")
                      : mode === "lan"
                        ? t("syncthing_route_lan_only", "Hanya LAN")
                        : t("syncthing_route_wan_only", "Hanya WAN")}
                  </button>
                ))}
              </div>
            </div>

            {/* LAN Configuration Card */}
            <div className="flex flex-col gap-2 rounded-tile border border-line bg-surface-sunken p-2.5">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1 text-micro font-bold text-ink">
                  <Network className="size-3 text-info" />
                  Jalur Akses LAN (Lokal)
                </span>
                <label className="flex items-center gap-1 text-nano text-ink-muted cursor-pointer">
                  <input
                    type="checkbox"
                    checked={serverLanHttps}
                    onChange={(e) => setServerLanHttps(e.target.checked)}
                    className="size-3 rounded border-line text-info"
                  />
                  HTTPS
                </label>
              </div>

              {/* LAN Mode Radio */}
              <div className="grid grid-cols-2 gap-1">
                <button
                  type="button"
                  onClick={() => setServerLanMode("inherit")}
                  className={cx(
                    "rounded border px-1.5 py-1 text-nano font-medium transition cursor-pointer text-center",
                    serverLanMode === "inherit"
                      ? "border-info bg-info-soft/40 text-ink"
                      : "border-line bg-surface text-ink-muted hover:text-ink"
                  )}
                >
                  {t("syncthing_lan_inherit", "Mewarisi IP Server")}
                </button>
                <button
                  type="button"
                  onClick={() => setServerLanMode("custom")}
                  className={cx(
                    "rounded border px-1.5 py-1 text-nano font-medium transition cursor-pointer text-center",
                    serverLanMode === "custom"
                      ? "border-info bg-info-soft/40 text-ink"
                      : "border-line bg-surface text-ink-muted hover:text-ink"
                  )}
                >
                  {t("syncthing_lan_manual", "IP Manual")}
                </button>
              </div>

              {serverLanMode === "custom" && (
                <div className="flex flex-col gap-0.5">
                  <label className="text-nano text-ink-subtle">IP / Host LAN:</label>
                  <input
                    type="text"
                    value={serverLanIp}
                    onChange={(e) => setServerLanIp(e.target.value)}
                    placeholder="Contoh: 192.168.1.10"
                    className="w-full rounded-control border border-line bg-surface px-2 py-1 text-micro font-mono text-ink outline-none focus:border-info"
                  />
                </div>
              )}

              <div className="flex items-center justify-between gap-2">
                <label className="text-nano text-ink-subtle">{t("syncthing_lan_port", "Port LAN:")}</label>
                <input
                  type="text"
                  value={serverLanPort}
                  onChange={(e) => setServerLanPort(e.target.value)}
                  placeholder="8384"
                  className="w-20 rounded-control border border-line bg-surface px-2 py-0.5 text-micro font-mono text-ink outline-none focus:border-info text-right"
                />
              </div>
            </div>

            {/* WAN Configuration Card */}
            <div className="flex flex-col gap-2 rounded-tile border border-line bg-surface-sunken p-2.5">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1 text-micro font-bold text-ink">
                  <Globe className="size-3 text-info" />
                  Jalur Akses WAN / Remote (Subdomain / IP)
                </span>
                <label className="flex items-center gap-1 text-nano text-ink-muted cursor-pointer">
                  <input
                    type="checkbox"
                    checked={serverWanHttps}
                    onChange={(e) => setServerWanHttps(e.target.checked)}
                    className="size-3 rounded border-line text-info"
                  />
                  HTTPS
                </label>
              </div>

              <div className="flex flex-col gap-0.5">
                <label className="text-nano text-ink-subtle">
                  {t("syncthing_wan_url", "URL atau IP WAN / Subdomain:")}
                </label>
                <input
                  type="text"
                  value={serverWanUrl}
                  onChange={(e) => setServerWanUrl(e.target.value)}
                  placeholder="Contoh: 172.24.0.1 atau sync.algitha.my.id"
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-micro font-mono text-ink outline-none focus:border-info"
                />
              </div>

              <div className="flex items-center justify-between gap-2">
                <label className="text-nano text-ink-subtle">{t("syncthing_wan_port", "Port WAN:")}</label>
                <input
                  type="text"
                  value={serverWanPort}
                  onChange={(e) => setServerWanPort(e.target.value)}
                  placeholder="8384"
                  className="w-20 rounded-control border border-line bg-surface px-2 py-0.5 text-micro font-mono text-ink outline-none focus:border-info text-right"
                />
              </div>
            </div>

            {/* Syncthing REST API Key */}
            <div className="flex flex-col gap-1">
              <label className="text-micro font-semibold text-ink-subtle">
                {t("syncthing_api_key", "REST API Key Syncthing:")}
              </label>
              <div className="relative flex items-center">
                <input
                  type={showPassword ? "text" : "password"}
                  value={apiServerKey}
                  onChange={(e) => setApiServerKey(e.target.value)}
                  placeholder="Tempelkan API Key Syncthing Server..."
                  className="w-full rounded-control border border-line bg-surface-sunken px-2 py-1 pr-7 text-micro font-mono text-ink outline-none focus:border-info"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-1.5 text-ink-muted hover:text-ink cursor-pointer"
                >
                  {showPassword ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                </button>
              </div>
            </div>

            {/* Test Connection Bar */}
            <div className="flex items-center justify-between gap-2 rounded-tile border border-line bg-surface-sunken px-2.5 py-1.5">
              <Button
                variant="soft"
                size="sm"
                icon={Radio}
                state={testStatus === "testing" ? "busy" : "idle"}
                onClick={handleTestConnection}
                className="h-6 px-2 text-nano"
              >
                {t("syncthing_test_btn", "Uji Koneksi Target")}
              </Button>
              <span
                className={cx(
                  "truncate text-nano font-medium",
                  testStatus === "online" && "text-success",
                  testStatus === "offline" && "text-danger-bright",
                  testStatus === "testing" && "text-info",
                  testStatus === "idle" && "text-ink-faint"
                )}
              >
                {testMessage || "Belum diuji"}
              </span>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 border-t border-line pt-2">
              <Button
                variant="soft"
                size="sm"
                onClick={() => setApiModal("none")}
                className="h-7 px-3 text-micro"
              >
                {t("syncthing_cancel_btn", "Batal")}
              </Button>
              <Button
                variant="primary"
                size="sm"
                state={savingApiKey ? "busy" : "idle"}
                onClick={handleSaveServerRoute}
                className="h-7 px-3.5 text-micro font-semibold"
              >
                {t("syncthing_save_btn", "Simpan Konfigurasi")}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODERN IN-APP MODAL: LOCAL SYNCTHING CONFIG */}
      {apiModal === "local" && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-3 backdrop-blur-xs motion-safe:animate-fade-in"
          onClick={() => setApiModal("none")}
        >
          <div
            className="flex w-full max-w-[320px] max-h-[92vh] flex-col gap-3 rounded-card border border-line bg-surface p-4 shadow-panel overflow-y-auto motion-safe:animate-flyout-in"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-line pb-2">
              <div className="flex items-center gap-2">
                <div className="flex size-7 items-center justify-center rounded-lg bg-info-soft text-info">
                  <Laptop className="size-4" />
                </div>
                <div>
                  <h3 className="text-caption font-bold text-ink">
                    {t("modal_local_syncthing_title", "Pengaturan Syncthing Lokal (Laptop)")}
                  </h3>
                  <p className="text-nano text-ink-subtle">
                    Klien Sinkronisasi Perangkat Ini
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setApiModal("none")}
                className="rounded p-1 text-ink-subtle hover:bg-surface-sunken hover:text-ink cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Port Lokal */}
            <div className="flex items-center justify-between gap-2">
              <label className="text-micro font-semibold text-ink-subtle">
                Port Syncthing Lokal:
              </label>
              <input
                type="text"
                value={apiLocalPort}
                onChange={(e) => setApiLocalPort(e.target.value)}
                placeholder="8384"
                className="w-24 rounded-control border border-line bg-surface-sunken px-2 py-1 text-micro font-mono text-ink outline-none focus:border-info text-right"
              />
            </div>

            {/* API Key Lokal */}
            <div className="flex flex-col gap-1">
              <label className="text-micro font-semibold text-ink-subtle">
                {t("syncthing_api_key", "REST API Key Syncthing:")}
              </label>
              <div className="relative flex items-center">
                <input
                  type={showPassword ? "text" : "password"}
                  value={apiLocalKey}
                  onChange={(e) => setApiLocalKey(e.target.value)}
                  placeholder="Tempelkan API Key Syncthing Laptop..."
                  className="w-full rounded-control border border-line bg-surface-sunken px-2 py-1 pr-7 text-micro font-mono text-ink outline-none focus:border-info"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-1.5 text-ink-muted hover:text-ink cursor-pointer"
                >
                  {showPassword ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                </button>
              </div>
            </div>

            {/* Auto Start Checkbox */}
            <label className="flex items-center gap-2 rounded-tile border border-line bg-surface-sunken p-2 text-micro text-ink cursor-pointer">
              <input
                type="checkbox"
                checked={localAutoStart}
                onChange={(e) => setLocalAutoStart(e.target.checked)}
                className="size-3.5 rounded border-line text-info"
              />
              <span className="text-nano">
                {t("syncthing_auto_start", "Jalankan Syncthing otomatis saat MyServer startup")}
              </span>
            </label>

            {/* Local Binary Path */}
            <div className="flex flex-col gap-1">
              <label className="text-micro font-semibold text-ink-subtle">
                {t("syncthing_bin_path", "Jalur Binary Syncthing Lokal:")}
              </label>
              <input
                type="text"
                value={localBinPath}
                onChange={(e) => setLocalBinPath(e.target.value)}
                placeholder="Otomatis / syncthing.exe"
                className="w-full rounded-control border border-line bg-surface-sunken px-2 py-1 text-micro font-mono text-ink outline-none focus:border-info"
              />
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 border-t border-line pt-2">
              <Button
                variant="soft"
                size="sm"
                onClick={() => setApiModal("none")}
                className="h-7 px-3 text-micro"
              >
                {t("syncthing_cancel_btn", "Batal")}
              </Button>
              <Button
                variant="primary"
                size="sm"
                state={savingApiKey ? "busy" : "idle"}
                onClick={handleSaveLocalConfig}
                className="h-7 px-3.5 text-micro font-semibold"
              >
                {t("syncthing_save_btn", "Simpan Konfigurasi")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

import { useState, useMemo, useEffect, useRef } from "react"
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  ExternalLink,
  Folder,
  Globe,
  HardDrive,
  Key,
  Monitor,
  Pencil,
  Plus,
  Power,
  RotateCcw,
  Server,
  Terminal,
  Trash2,
  X,
} from "lucide-react"
import { getTranslation } from "../i18n"
import { useCompanion, useNotice } from "../store"
import { getCompanionApi } from "../api"
import { Button, Card, Chip, IconBadge, Mono, StatusDot, cx } from "../ui"
import { ViewBody, type ViewProps } from "./shared"
import type { Tone, VirtualMachine, VmAutoRestartSchedule, VmTelemetry } from "../types"

const INITIAL_VMS: VirtualMachine[] = []

// Style Dot Bar 42x3 SVG dari FilesView.tsx (StorageDotBar)
const RUNTIME_DOT_COLS = 42
const RUNTIME_DOT_ROWS = 3

const SVG_FILL_TONES: Record<Tone, string> = {
  success: "fill-success",
  warning: "fill-warning",
  danger: "fill-danger",
  info: "fill-info",
  neutral: "fill-line-strong",
}

const getVmRuntimeTone = (usedPct: number, live: boolean): Tone => {
  if (!live) return "neutral"
  return usedPct < 70 ? "success" : usedPct < 85 ? "warning" : "danger"
}

function VmRuntimeDotBar({ usedPct, tone, live = false }: { usedPct: number; tone: Tone; live?: boolean }) {
  const colStep = 6
  const rowStep = 6
  const r = 2.1
  const totalDots = RUNTIME_DOT_COLS * RUNTIME_DOT_ROWS
  let totalLit = Math.round((Math.max(0, Math.min(100, usedPct)) / 100) * totalDots)
  if (live && usedPct > 0 && totalLit === 0) {
    totalLit = 1
  }

  return (
    <svg
      viewBox={`0 0 ${RUNTIME_DOT_COLS * colStep} ${RUNTIME_DOT_ROWS * rowStep}`}
      className="w-full h-[18px] block overflow-visible"
      aria-hidden="true"
    >
      {Array.from({ length: RUNTIME_DOT_COLS }, (_, col) => {
        const colLitCount = Math.min(
          RUNTIME_DOT_ROWS,
          Math.max(0, totalLit - col * RUNTIME_DOT_ROWS),
        )
        return Array.from({ length: RUNTIME_DOT_ROWS }, (_, row) => {
          const heightFromBottom = RUNTIME_DOT_ROWS - row
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
                lit ? SVG_FILL_TONES[tone] : "fill-line",
              )}
            />
          )
        })
      })}
    </svg>
  )
}

export default function VmManagerView({ go }: ViewProps) {
  const api = getCompanionApi()
  const { isOnline, settings } = useCompanion()
  const t = getTranslation(settings?.language)
  const { notify } = useNotice()

  // State: list of VMs with localStorage persistence
  const [vms, setVms] = useState<VirtualMachine[]>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      if (params.get("vm_mode") === "single_test") {
        return [
          {
            id: "vm-test-instabox",
            name: "Debian-Dev-Node",
            provider: "instabox",
            status: "running",
            sshHost: "ssh.instabox.sh",
            sshUser: "ibssh_demoexampleuser012345",
            sshPort: 2222,
            tokenExpiry: "6d",
            ip: "ssh.instabox.sh",
            lastActive: "Just now",
            screenUrl: "https://instabox.sh/app/machines/m_demo",
            runtimeMinutes: 184, // 3h 04m / 8h
            maxRuntimeMinutes: 480,
            idleTimeoutMinutes: 30,
            telemetry: {
              cpuPct: 14,
              ramUsedBytes: 2576980377, // ~2.4 GB
              ramTotalBytes: 8589934592, // 8.0 GB
              diskUsedBytes: 5583457484, // ~5.2 GB
              diskTotalBytes: 21474836480, // 20.0 GB
            },
          },
        ]
      }
      if (params.get("vm_mode") === "multi_test") {
        return [
          {
            id: "vm-test-instabox-1",
            name: "Debian-Dev-Node",
            provider: "instabox",
            status: "running",
            sshHost: "ssh.instabox.sh",
            sshUser: "ibssh_demoexampleuser012345",
            sshPort: 2222,
            tokenExpiry: "6d",
            ip: "ssh.instabox.sh",
            screenUrl: "https://instabox.sh/app/machines/m_demo",
            runtimeMinutes: 184,
            maxRuntimeMinutes: 480,
            idleTimeoutMinutes: 30,
            telemetry: {
              cpuPct: 14,
              ramUsedBytes: 2576980377,
              ramTotalBytes: 8589934592,
              diskUsedBytes: 5583457484,
              diskTotalBytes: 21474836480,
            },
          },
          {
            id: "vm-test-custom-2",
            name: "Ubuntu-Worker-VPS",
            provider: "custom",
            status: "running",
            sshHost: "vps.example.com",
            sshUser: "root",
            sshPort: 22,
            ip: "vps.example.com",
            webPort: 8080,
            screenUrl: "http://vps.example.com:6080/vnc.html",
            telemetry: {
              cpuPct: 6,
              ramUsedBytes: 1288490188,
              ramTotalBytes: 4294967296,
              diskUsedBytes: 8589934592,
              diskTotalBytes: 42949672960,
            },
          },
        ]
      }
      if (params.get("vm_mode") === "empty") {
        return []
      }
      try {
        const saved = localStorage.getItem("myserver_vms")
        if (saved) {
          const parsed = JSON.parse(saved)
          if (Array.isArray(parsed)) return parsed
        }
      } catch {}
    }
    return INITIAL_VMS
  })

  // Save to localStorage whenever vms change
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("myserver_vms", JSON.stringify(vms))
      } catch {}
    }
  }, [vms])

  // Periodic InstaBox Sync & Local Runtime Counter
  useEffect(() => {
    const syncActiveInstaboxVms = () => {
      vms.forEach((vm) => {
        if (vm.provider === "instabox" && vm.apiKey) {
          api.syncInstaBoxVm({ apiKey: vm.apiKey, machineId: vm.machineId, vmName: vm.name }).then((res: any) => {
            if (res && res.success) {
              setVms((prev) =>
                prev.map((v) =>
                  v.id === vm.id
                    ? {
                        ...v,
                        machineId: res.machineId || v.machineId,
                        status: res.state === "running" ? "running" : v.status,
                        runtimeMinutes: res.runtimeMinutes ?? v.runtimeMinutes,
                        maxRuntimeMinutes: res.maxRuntimeMinutes || 480,
                        idleTimeoutMinutes: res.idleTimeoutMinutes || 30,
                        screenUrl: v.screenUrl || res.screenUrl,
                        telemetry: res.telemetry || v.telemetry,
                      }
                    : v
                )
              )
            }
          }).catch(() => {})
        }
      })
    }

    syncActiveInstaboxVms()
    const syncInterval = setInterval(syncActiveInstaboxVms, 30000)

    // Local runtime increment: increment runtime by 1 minute every 60 seconds if running
    const timerInterval = setInterval(() => {
      setVms((prev) =>
        prev.map((vm) => {
          if (vm.status === "running") {
            const currentMins = vm.runtimeMinutes || 0
            const maxMins = vm.maxRuntimeMinutes || 480
            return {
              ...vm,
              runtimeMinutes: Math.min(maxMins, currentMins + 1),
            }
          }
          return vm
        })
      )
    }, 60000)

    return () => {
      clearInterval(syncInterval)
      clearInterval(timerInterval)
    }
  }, [vms.length])

  // Accordion state
  const [expandedId, setExpandedId] = useState<string | null>(vms[0]?.id || null)

  // Modals state
  const [vmToDelete, setVmToDelete] = useState<VirtualMachine | null>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      if (params.get("vm_modal") === "delete") {
        return vms[0] || null
      }
    }
    return null
  })

  const [editingVm, setEditingVm] = useState<VirtualMachine | null>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      if (params.get("vm_modal") === "edit") {
        return vms[0] || null
      }
    }
    return null
  })

  const [isAddingVm, setIsAddingVm] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      return params.get("vm_modal") === "add"
    }
    return false
  })

  // Modal Auto-Restart Scheduler state
  const [schedulingVm, setSchedulingVm] = useState<VirtualMachine | null>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      if (params.get("vm_modal") === "schedule") {
        return vms[0] || null
      }
    }
    return null
  })

  // Modal 2-Tab state: "instabox" | "manual"
  const [addVmTab, setAddVmTab] = useState<"instabox" | "manual">("instabox")

  // Form fields (Clean and empty by default)
  const [formName, setFormName] = useState("")
  const [formSshHost, setFormSshHost] = useState("")
  const [formSshUser, setFormSshUser] = useState("")
  const [formSshPort, setFormSshPort] = useState<number | string>(2222)
  const [formTokenExpiry, setFormTokenExpiry] = useState("")
  const [formWebPort, setFormWebPort] = useState<number | string>("")
  const [formScreenUrl, setFormScreenUrl] = useState("")
  const [formApiKey, setFormApiKey] = useState("")
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // Schedule modal form fields
  const [schedEnabled, setSchedEnabled] = useState(false)
  const [schedMode, setSchedMode] = useState<"interval" | "clock">("interval")
  const [schedIntervalVal, setSchedIntervalVal] = useState<number | string>(6)
  const [schedIntervalUnit, setSchedIntervalUnit] = useState<"seconds" | "minutes" | "hours">("hours")
  const [schedClockTime, setSchedClockTime] = useState("04:00")
  const [schedResetMode, setSchedResetMode] = useState<"pause_resume" | "cold_restart">("pause_resume")

  // Copy helper
  const copyToClipboard = async (text: string, label: string, vmId?: string) => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const textArea = document.createElement("textarea")
        textArea.value = text
        document.body.appendChild(textArea)
        textArea.select()
        document.execCommand("copy")
        document.body.removeChild(textArea)
      }
      if (vmId) {
        setCopiedId(vmId)
        setTimeout(() => setCopiedId(null), 1800)
      }
      notify(`${label} disalin ke papan klip!`, "success")
    } catch {
      notify(`Gagal menyalin ${label}.`, "danger")
    }
  }

  // Generate full SSH command
  const getSshCommand = (vm: VirtualMachine) => {
    const port = vm.sshPort || 2222
    const user = vm.sshUser ? `${vm.sshUser}@` : ""
    const host = vm.sshHost || vm.ip || "ssh.instabox.sh"
    return `ssh -p ${port} ${user}${host}`
  }

  // Toggle Power (Wake / Sleep)
  const handleTogglePower = (vm: VirtualMachine) => {
    if (!isOnline) {
      notify(t("server_offline_warning", "Server sedang offline."), "warning")
      return
    }
    const nextStatus = vm.status === "running" ? "sleeping" : "running"
    setVms((prev) =>
      prev.map((item) =>
        item.id === vm.id ? { ...item, status: nextStatus } : item
      )
    )
    notify(
      nextStatus === "running"
        ? `${vm.name}: ${t("wake_vm_btn", "VM Dibangunkan")}`
        : `${vm.name}: ${t("sleep_vm_btn", "VM Masuk Mode Tidur")}`,
      "neutral"
    )
  }

  // Delete execution
  const handleDeleteConfirm = () => {
    if (!vmToDelete) return
    const targetId = vmToDelete.id
    setVms((prev) => prev.filter((v) => v.id !== targetId))
    notify(`${vmToDelete.name} berhasil dihapus.`, "neutral")
    setVmToDelete(null)
  }

  // Open Edit Modal
  const handleOpenEdit = (vm: VirtualMachine) => {
    setEditingVm(vm)
    setAddVmTab(vm.provider === "instabox" ? "instabox" : "manual")
    setFormName(vm.name)
    setFormSshHost(vm.sshHost || vm.ip || "")
    setFormSshUser(vm.sshUser || "")
    setFormSshPort(vm.sshPort || 2222)
    setFormTokenExpiry(vm.tokenExpiry || "")
    setFormWebPort(vm.webPort || "")
    setFormScreenUrl(vm.screenUrl || "")
    setFormApiKey(vm.apiKey || "")
  }

  // Save Add/Edit
  const handleSaveForm = (e: React.FormEvent) => {
    e.preventDefault()
    const cleanName = formName.trim()
    if (!cleanName && addVmTab === "manual") {
      notify("Nama Virtual Machine wajib diisi.", "danger")
      return
    }

    let cleanUser = formSshUser.trim()
    let cleanHost = formSshHost.trim()
    if (cleanUser.includes("@")) {
      const parts = cleanUser.split("@")
      cleanUser = parts[0]
      if (!cleanHost && parts[1]) {
        cleanHost = parts[1]
      }
    }

    const finalApiKey = formApiKey.trim()
    const targetId = editingVm ? editingVm.id : `vm-${Date.now()}`

    if (editingVm) {
      setVms((prev) =>
        prev.map((item) =>
          item.id === editingVm.id
            ? {
                ...item,
                name: cleanName || item.name,
                provider: addVmTab,
                sshHost: cleanHost || (addVmTab === "instabox" ? "ssh.instabox.sh" : ""),
                sshUser: cleanUser,
                sshPort: Number(formSshPort) || (addVmTab === "instabox" ? 2222 : 22),
                tokenExpiry: formTokenExpiry.trim(),
                webPort: formWebPort ? Number(formWebPort) : undefined,
                screenUrl: formScreenUrl.trim() || undefined,
                apiKey: finalApiKey || undefined,
                ip: cleanHost || (addVmTab === "instabox" ? "ssh.instabox.sh" : ""),
              }
            : item
        )
      )
      notify(`${cleanName || editingVm.name} berhasil diperbarui!`, "success")
      setEditingVm(null)
    } else {
      const finalName = cleanName || (addVmTab === "instabox" ? "InstaBox-MicroVM" : "Linux-VPS")
      const newVm: VirtualMachine = {
        id: targetId,
        name: finalName,
        provider: addVmTab,
        status: "running",
        sshHost: cleanHost || (addVmTab === "instabox" ? "ssh.instabox.sh" : "127.0.0.1"),
        sshUser: cleanUser,
        sshPort: Number(formSshPort) || (addVmTab === "instabox" ? 2222 : 22),
        tokenExpiry: formTokenExpiry.trim() || (addVmTab === "instabox" ? "7d" : ""),
        webPort: formWebPort ? Number(formWebPort) : undefined,
        screenUrl: formScreenUrl.trim() || undefined,
        apiKey: finalApiKey || undefined,
        ip: cleanHost || (addVmTab === "instabox" ? "ssh.instabox.sh" : "127.0.0.1"),
        runtimeMinutes: 0,
        maxRuntimeMinutes: addVmTab === "instabox" ? 480 : undefined,
        idleTimeoutMinutes: addVmTab === "instabox" ? 30 : undefined,
        lastActive: "Just now",
        telemetry: {
          cpuPct: null,
          ramUsedBytes: null,
          ramTotalBytes: null,
          diskUsedBytes: null,
          diskTotalBytes: null,
        },
      }
      setVms((prev) => [...prev, newVm])
      setExpandedId(newVm.id)
      notify(`${finalName} berhasil ditambahkan!`, "success")
      setIsAddingVm(false)
    }

    // Trigger immediate InstaBox cloud sync if API Key is configured
    if (finalApiKey && addVmTab === "instabox") {
      notify("Menyinkronkan data dengan InstaBox Cloud…", "info")
      api.syncInstaBoxVm({ apiKey: finalApiKey, vmName: cleanName, machineId: editingVm?.machineId }).then((res: any) => {
        if (res && res.success) {
          setVms((current) =>
            current.map((v) =>
              v.id === targetId
                ? {
                    ...v,
                    machineId: res.machineId || v.machineId,
                    status: res.state === "running" ? "running" : "stopped",
                    runtimeMinutes: res.runtimeMinutes ?? v.runtimeMinutes,
                    maxRuntimeMinutes: res.maxRuntimeMinutes || 480,
                    idleTimeoutMinutes: res.idleTimeoutMinutes || 30,
                    screenUrl: v.screenUrl || res.screenUrl,
                    sshHost: v.sshHost || res.sshHost,
                    sshUser: v.sshUser || res.sshUser,
                    sshPort: v.sshPort || res.sshPort,
                    telemetry: res.telemetry || v.telemetry,
                  }
                : v
            )
          )
          notify(`Terhubung ke InstaBox: ${res.machineName || 'MicroVM'}! Metrik berhasil disinkronkan.`, "success")
        } else if (res && res.error) {
          notify(`Peringatan InstaBox: ${res.error}`, "warning")
        }
      }).catch((err: any) => {
        console.warn("InstaBox sync error:", err)
      })
    }
  }

  // Open Web Service in browser
  const handleOpenWeb = (vm: VirtualMachine) => {
    if (!vm.webPort && !vm.webUrl) return
    const host = vm.sshHost || vm.ip || "localhost"
    let targetUrl = vm.webUrl || `http://${host}:${vm.webPort}`
    if (!targetUrl.startsWith("http://") && !targetUrl.startsWith("https://")) {
      targetUrl = `http://${targetUrl}`
    }
    void api.openExternalBrowser(targetUrl)
    notify(`Membuka web service ${targetUrl}…`, "info")
  }

    // Open Virtual Screen
  const handleOpenScreen = (vm: VirtualMachine) => {
    let targetUrl = (vm.screenUrl || "").trim()
    if (!targetUrl) {
      if (vm.machineId) {
        targetUrl = `https://dashboard.instabox.sh/machines/${vm.machineId}`
      } else {
        targetUrl = "https://dashboard.instabox.sh"
      }
    } else if (!targetUrl.startsWith("http://") && !targetUrl.startsWith("https://")) {
      targetUrl = `https://${targetUrl}`
    }
    void api.openExternalBrowser(targetUrl)
    notify(`Membuka Layar Virtual: ${targetUrl}`, "info")
  }

  // Copy SFTP URI
  const handleCopySftp = (vm: VirtualMachine) => {
    const user = vm.sshUser ? `${vm.sshUser}@` : ""
    const host = vm.sshHost || vm.ip || "localhost"
    const port = vm.sshPort || 22
    const sftpUri = `sftp://${user}${host}:${port}`
    copyToClipboard(sftpUri, "Tautan SFTP", vm.id)
  }

  // Open Auto-Restart Schedule modal
  const handleOpenSchedule = (vm: VirtualMachine) => {
    setSchedulingVm(vm)
    if (vm.autoRestart) {
      setSchedEnabled(vm.autoRestart.enabled)
      setSchedMode(vm.autoRestart.mode)
      setSchedIntervalVal(vm.autoRestart.intervalValue || 6)
      setSchedIntervalUnit(vm.autoRestart.intervalUnit || "hours")
      setSchedClockTime(vm.autoRestart.clockTime || "04:00")
      setSchedResetMode(vm.autoRestart.resetCycleMode || "pause_resume")
    } else {
      setSchedEnabled(false)
      setSchedMode("interval")
      setSchedIntervalVal(6)
      setSchedIntervalUnit("hours")
      setSchedClockTime("04:00")
      setSchedResetMode("pause_resume")
    }
  }

  // Save Auto-Restart schedule
  const handleSaveSchedule = (e: React.FormEvent) => {
    e.preventDefault()
    if (!schedulingVm) return
    const newSchedule: VmAutoRestartSchedule = {
      enabled: schedEnabled,
      mode: schedMode,
      intervalValue: Number(schedIntervalVal) || 6,
      intervalUnit: schedIntervalUnit,
      clockTime: schedClockTime,
      resetCycleMode: schedResetMode,
      lastExecuted: "Never",
    }
    setVms((prev) =>
      prev.map((item) =>
        item.id === schedulingVm.id ? { ...item, autoRestart: newSchedule } : item
      )
    )
    notify(`Jadwal Auto-Restart ${schedulingVm.name} disimpan!`, "success")
    setSchedulingVm(null)
  }

  // Immediate 8-hour reset cycle for InstaBox
  const handleImmediateResetCycle = async (vm: VirtualMachine) => {
    notify(`Memulai siklus reset limit 8 jam untuk ${vm.name}…`, "info")
    setVms((prev) =>
      prev.map((item) =>
        item.id === vm.id ? { ...item, status: "sleeping" } : item
      )
    )
    if (vm.apiKey) {
      try {
        await api.smartResetInstaBox({ apiKey: vm.apiKey, machineId: vm.machineId, vmId: vm.id })
      } catch {}
    }
    setTimeout(() => {
      setVms((prev) =>
        prev.map((item) =>
          item.id === vm.id ? { ...item, status: "running", runtimeMinutes: 0 } : item
        )
      )
      notify(`Siklus selesai! Limit 8 jam ${vm.name} berhasil di-reset ke 0.`, "success")
    }, 2500)
  }
  // Active Auto-Restart Scheduler Worker Loop
  useEffect(() => {
    const checkSchedules = () => {
      const now = Date.now()
      const nowDate = new Date()
      const currentHours = String(nowDate.getHours()).padStart(2, "0")
      const currentMins = String(nowDate.getMinutes()).padStart(2, "0")
      const currentTimeStr = `${currentHours}:${currentMins}`

      vmsRef.current.forEach((vm) => {
        if (!vm.autoRestart?.enabled) return

        let shouldTrigger = false

        if (vm.autoRestart.mode === "interval") {
          const val = vm.autoRestart.intervalValue || 6
          const unit = vm.autoRestart.intervalUnit || "hours"
          const multiplierMs = unit === "seconds" ? 1000 : unit === "minutes" ? 60 * 1000 : 3600 * 1000
          const intervalMs = val * multiplierMs
          const lastRun = vm.autoRestart.lastRunTimestamp || now

          if (!vm.autoRestart.lastRunTimestamp) {
            setVms((prev) =>
              prev.map((item) =>
                item.id === vm.id
                  ? {
                      ...item,
                      autoRestart: {
                        ...item.autoRestart!,
                        lastRunTimestamp: now,
                      },
                    }
                  : item
              )
            )
            return
          }

          if (now - lastRun >= intervalMs) {
            shouldTrigger = true
          }
        } else if (vm.autoRestart.mode === "clock") {
          const targetTime = vm.autoRestart.clockTime || "04:00"
          if (currentTimeStr === targetTime) {
            const lastRun = vm.autoRestart.lastRunTimestamp || 0
            if (now - lastRun > 65000) {
              shouldTrigger = true
            }
          }
        }

        if (shouldTrigger) {
          const timestampStr = nowDate.toLocaleTimeString()
          setVms((prev) =>
            prev.map((item) =>
              item.id === vm.id
                ? {
                    ...item,
                    autoRestart: {
                      ...item.autoRestart!,
                      lastRunTimestamp: now,
                      lastExecuted: timestampStr,
                    },
                  }
                : item
            )
          )
          notify(`[Auto-Restart] Menjalankan jadwal otomatis untuk ${vm.name} (${timestampStr})`, "info")
          if (vm.provider === "instabox") {
            handleImmediateResetCycle(vm)
          } else {
            handleTogglePower(vm)
          }
        }
      })
    }

    const schedTimer = setInterval(checkSchedules, 5000)
    return () => clearInterval(schedTimer)
  }, [])


  const isSingle = vms.length === 1
  const isMultiple = vms.length > 1

  // Helper renderer for Inner Card Informasi VM
  const renderVmCardContent = (vm: VirtualMachine, inAccordion: boolean) => {
    const isRunning = isOnline && vm.status === "running"
    const live = isOnline && vm.status === "running"
    const runtimeMinutes = vm.runtimeMinutes != null ? vm.runtimeMinutes : 0
    const maxRuntime = vm.maxRuntimeMinutes || 480
    const runtimePct = Math.min(100, Math.max(0, (runtimeMinutes / maxRuntime) * 100))
    const dotTone = getVmRuntimeTone(runtimePct, isRunning)

    return (
      <div className={cx("flex flex-col gap-2.5", inAccordion ? "pt-1" : "")}>
        {/* TIER 1: Header Identitas & Status Pill (Only in Single mode; Accordion has its own top row) */}
        {!inAccordion && (
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <IconBadge
                icon={Server}
                tone={
                  !isOnline
                    ? "neutral"
                    : vm.status === "running"
                      ? "success"
                      : vm.status === "sleeping"
                        ? "warning"
                        : "danger"
                }
                size="sm"
              />
              <div className="flex flex-col min-w-0">
                <span className="text-body font-bold text-ink truncate leading-tight">
                  {vm.name}
                </span>
                <span className="text-nano text-ink-subtle truncate">
                  {vm.provider === "instabox" ? "InstaBox Cloud" : "Linux VM"} · {vm.sshHost || vm.ip}:{vm.sshPort}
                </span>
              </div>
            </div>

            {/* Status Pill & Edit/Delete Icons */}
            <div className="flex items-center gap-1.5 shrink-0">
              <span
                className={cx(
                  "inline-flex items-center gap-1 text-nano font-semibold rounded-full px-2 py-0.5 border",
                  !isOnline
                    ? "bg-surface-sunken text-ink-muted border-line"
                    : vm.status === "running"
                      ? "bg-success-soft text-success-ink border-success-line/60"
                      : vm.status === "sleeping"
                        ? "bg-warning-soft text-warning-ink border-warning-line/60"
                        : "bg-danger-soft text-danger-ink border-danger-line/60"
                )}
              >
                <StatusDot
                  tone={
                    !isOnline
                      ? "neutral"
                      : vm.status === "running"
                        ? "success"
                        : vm.status === "sleeping"
                          ? "warning"
                          : "danger"
                  }
                  size="xs"
                />
                {!isOnline
                  ? "Offline"
                  : vm.status === "running"
                    ? t("vm_status_running", "Active")
                    : vm.status === "sleeping"
                      ? t("vm_status_sleep", "Sleeping")
                      : t("vm_status_cooldown", "Cooldown")}
              </span>

              <button
                type="button"
                onClick={() => handleOpenEdit(vm)}
                className="p-1 rounded-md text-ink-subtle hover:text-ink hover:bg-surface-sunken transition cursor-pointer"
                title={t("edit_vm_btn", "Edit")}
              >
                <Pencil className="size-3.5" />
              </button>

              <button
                type="button"
                onClick={() => setVmToDelete(vm)}
                className="p-1 rounded-md text-ink-subtle hover:text-danger-ink hover:bg-danger-soft/50 transition cursor-pointer"
                title={t("delete_vm_btn", "Hapus")}
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* TIER 2: Meter Titik LED Jam Penggunaan (Style File Manager) */}
        {vm.provider === "instabox" && (
          <div className="rounded-tile bg-surface-sunken/40 border border-line/60 p-2.5 flex flex-col gap-2">
            <div className="w-full px-0.5">
              <VmRuntimeDotBar usedPct={runtimePct} tone={dotTone} live={isRunning} />
            </div>

            <div className="flex items-center justify-between text-micro text-ink-subtle">
              <Mono className="truncate text-ink-subtle flex items-center gap-1">
                <Clock className="size-3 text-ink-muted" />
                <span>
                  {vm.runtimeMinutes != null
                    ? `${Math.floor(vm.runtimeMinutes / 60)}j ${vm.runtimeMinutes % 60}m / 8j runtime`
                    : "— / 8j runtime"}
                </span>
              </Mono>
              <Mono className={cx("shrink-0 font-semibold", isRunning ? "text-ink" : "text-ink-subtle")}>
                {vm.runtimeMinutes != null ? `${Math.round(runtimePct)}%` : "0%"} {t("used_label", "used")}
              </Mono>
            </div>

            <div className="flex items-center justify-between text-nano text-ink-faint border-t border-line/40 pt-1">
              <span>Auto-sleep: 30m idle</span>
              {vm.autoRestart?.enabled && (
                <span className="text-info font-medium">Auto-Restart Aktif</span>
              )}
            </div>
          </div>
        )}

        {/* TIER 2.5: Telemetri Riil 3-Kolom (Live Data / Dash saat Idle) */}
        <div className="grid grid-cols-3 gap-1.5 p-1.5 rounded-tile bg-surface-sunken/60 border border-line/60 text-center text-nano">
          <div className="flex flex-col">
            <span className="text-[9px] uppercase font-bold text-ink-faint">CPU</span>
            <Mono className="text-[11px] font-semibold text-ink">
              {vm.telemetry?.cpuPct != null ? `${vm.telemetry.cpuPct}%` : "—"}
            </Mono>
          </div>
          <div className="flex flex-col border-x border-line/40">
            <span className="text-[9px] uppercase font-bold text-ink-faint">RAM</span>
            <Mono className="text-[11px] font-semibold text-ink">
              {vm.telemetry?.ramUsedBytes != null && vm.telemetry?.ramTotalBytes
                ? `${(vm.telemetry.ramUsedBytes / (1024 ** 3)).toFixed(1)} GB`
                : "—"}
            </Mono>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] uppercase font-bold text-ink-faint">DISK</span>
            <Mono className="text-[11px] font-semibold text-ink">
              {vm.telemetry?.diskUsedBytes != null && vm.telemetry?.diskTotalBytes
                ? `${(vm.telemetry.diskUsedBytes / (1024 ** 3)).toFixed(1)} GB`
                : "—"}
            </Mono>
          </div>
        </div>

        {/* TIER 3: Rincian Koneksi SSH & Ports */}
        <div className="rounded-tile bg-surface-sunken/80 border border-line p-2.5 flex flex-col gap-1.5 text-nano">
          <div className="flex items-center justify-between text-ink-subtle">
            <span className="font-semibold text-ink">SSH Connection</span>
            {vm.tokenExpiry && (
              <span className="flex items-center gap-1 text-[10px] text-amber-500 font-medium">
                <Clock className="size-3" />
                <span>expires in {vm.tokenExpiry}</span>
              </span>
            )}
          </div>

          <div className="flex items-center justify-between gap-1 text-ink-muted">
            <span className="text-[10px]">Host:</span>
            <Mono className="text-[10.5px] text-ink truncate select-all">
              {vm.sshHost || vm.ip}:{vm.sshPort}
            </Mono>
          </div>

          {vm.sshUser && (
            <div className="flex items-center justify-between gap-1 text-ink-muted">
              <span className="text-[10px]">User:</span>
              <Mono className="text-[10.5px] text-ink-muted truncate max-w-[170px] select-all">
                {vm.sshUser.length > 20 ? `${vm.sshUser.slice(0, 16)}...` : vm.sshUser}
              </Mono>
            </div>
          )}

          {/* Published Ports (Dinamis: 0 jika kosong) */}
          {vm.publishedPorts && vm.publishedPorts.length > 0 && (
            <div className="flex items-center gap-1 flex-wrap pt-1 border-t border-line/40">
              <span className="text-[10px] text-ink-subtle">Ports:</span>
              {vm.publishedPorts.map((p) => (
                <button
                  key={p.port}
                  type="button"
                  onClick={() => p.url && void api.openExternalBrowser(p.url)}
                  className="px-1.5 py-0.5 rounded bg-info-soft text-info-ink text-[10px] font-mono hover:bg-info-soft/80 transition cursor-pointer"
                >
                  {p.port} {p.label ? `(${p.label})` : ""}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* TIER 4: Tombol Aksi Nyata */}
        <div className="flex flex-col gap-1.5 mt-0.5">
          {/* Action 1: Universal SSH Command Button */}
          <button
            type="button"
            disabled={!isOnline}
            onClick={() => copyToClipboard(getSshCommand(vm), "Perintah SSH", vm.id)}
            className={cx(
              "w-full h-9 rounded-tile flex items-center justify-center gap-2 font-bold text-caption shadow-sm transition cursor-pointer select-none",
              !isOnline
                ? "bg-surface-sunken text-ink-muted cursor-not-allowed"
                : "bg-brand text-brand-ink hover:opacity-90 active:scale-[0.99] shadow-brand/20"
            )}
          >
            {copiedId === vm.id ? (
              <>
                <Check className="size-4" />
                <span>Perintah Disalin!</span>
              </>
            ) : (
              <>
                <Terminal className="size-4" />
                <span>{t("vm_copy_ssh_cmd", "Salin Perintah SSH")}</span>
              </>
            )}
          </button>

          {/* Action Row 1: Layar Virtual, Web Service, dan SFTP */}
          <div className="flex items-center gap-1.5">
            {(vm.screenUrl || vm.provider === "instabox") ? (
              <Button
                size="sm"
                variant="info"
                icon={Monitor}
                onClick={() => handleOpenScreen(vm)}
                className="flex-1 justify-center text-nano"
              >
                Layar Virtual
              </Button>
            ) : null}

            {(vm.webPort || vm.webUrl) ? (
              <Button
                size="sm"
                variant="subtle"
                icon={Globe}
                disabled={!isOnline}
                onClick={() => handleOpenWeb(vm)}
                className="flex-1 justify-center text-nano"
              >
                Web ({vm.webPort || "App"})
              </Button>
            ) : null}

            <Button
              size="sm"
              variant="subtle"
              icon={Folder}
              onClick={() => handleCopySftp(vm)}
              className="flex-1 justify-center text-nano"
            >
              SFTP
            </Button>
          </div>

          {/* Action Row 2: Jadwal Auto-Restart & Power Toggle */}
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="subtle"
              icon={RotateCcw}
              onClick={() => handleOpenSchedule(vm)}
              className="flex-1 justify-center text-nano"
            >
              Jadwal Auto-Restart
            </Button>

            <Button
              size="sm"
              variant="subtle"
              icon={Power}
              disabled={!isOnline}
              onClick={() => handleTogglePower(vm)}
              className="flex-1 justify-center text-nano"
            >
              {vm.status === "running" ? "Tidurkan VM" : "Bangunkan VM"}
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <ViewBody>
      {/* ========================================================= */}
      {/* 1. TOP HEADER: Clean Title (Left) + Add VM Button (Right) */}
      {/* ========================================================= */}
      <div className="flex items-center justify-between pl-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-[10px] font-bold tracking-wider text-ink-muted uppercase truncate">
            {t("vm_section_title", "VIRTUAL MACHINES")}
          </span>
          {vms.length > 0 && (
            <span className="text-[10px] font-semibold text-ink-subtle">
              ({vms.length})
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => {
              setEditingVm(null)
              setAddVmTab("instabox")
              setFormName("")
              setFormSshHost("")
              setFormSshUser("")
              setFormSshPort(2222)
              setFormTokenExpiry("")
              setFormWebPort("")
              setFormScreenUrl("")
              setFormApiKey("")
              setIsAddingVm(true)
            }}
            className="h-[23px] px-2.5 flex items-center gap-1 rounded-full bg-info-ink/15 hover:bg-info-ink/25 text-info-ink text-[10.5px] font-semibold transition cursor-pointer select-none"
          >
            <Plus className="size-3" />
            <span>{t("add_vm_btn", "Tambah VM")}</span>
          </button>
        </div>
      </div>

      {/* ========================================================= */}
      {/* 2. CASE 0: EMPTY STATE (NO VMS)                           */}
      {/* ========================================================= */}
      {vms.length === 0 && (
        <Card className="flex flex-col items-center justify-center py-8 px-4 text-center gap-2">
          <div className="size-10 rounded-full bg-surface-sunken flex items-center justify-center text-ink-muted">
            <Server className="size-5" />
          </div>
          <span className="text-body font-bold text-ink">
            {t("vm_empty_title", "Belum Ada Virtual Machine")}
          </span>
          <span className="text-micro text-ink-subtle max-w-[220px]">
            {t("vm_empty_desc", "Tambahkan InstaBox atau Linux VM Anda untuk mengelola via SSH.")}
          </span>
          <Button
            size="sm"
            variant="info"
            icon={Plus}
            className="mt-2"
            onClick={() => {
              setEditingVm(null)
              setAddVmTab("instabox")
              setFormName("")
              setFormSshHost("")
              setFormSshUser("")
              setFormSshPort(2222)
              setFormTokenExpiry("")
              setFormWebPort("")
              setFormScreenUrl("")
              setFormApiKey("")
              setIsAddingVm(true)
            }}
          >
            {t("vm_add_first_btn", "Tambah VM Pertama")}
          </Button>
        </Card>
      )}

      {/* ========================================================= */}
      {/* 3. CASE 1: SINGLE VM MODE (1 RICH CARD)                   */}
      {/* ========================================================= */}
      {isSingle && (
        <Card className="flex flex-col gap-2.5 p-3 relative overflow-hidden">
          {renderVmCardContent(vms[0], false)}
        </Card>
      )}

      {/* ========================================================= */}
      {/* 4. CASE 2: MULTIPLE VMS MODE (NATURAL ACCORDION LIST)     */}
      {/* ========================================================= */}
      {isMultiple && (
        <div className="flex flex-col gap-2">
          {vms.map((vm) => {
            const isExpanded = expandedId === vm.id
            return (
              <Card
                key={vm.id}
                className={cx(
                  "flex flex-col transition-all overflow-hidden p-0 border",
                  isExpanded ? "border-brand/40 shadow-sm" : "border-line"
                )}
              >
                {/* Accordion Header Row */}
                <div
                  className="flex items-center justify-between p-2.5 cursor-pointer hover:bg-surface-sunken/40 select-none"
                  onClick={() => setExpandedId(isExpanded ? null : vm.id)}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <IconBadge
                      icon={Server}
                      tone={
                        !isOnline
                          ? "neutral"
                          : vm.status === "running"
                            ? "success"
                            : vm.status === "sleeping"
                              ? "warning"
                              : "danger"
                      }
                      size="xs"
                    />
                    <div className="flex flex-col min-w-0">
                      <span className="text-caption font-bold text-ink truncate leading-tight">
                        {vm.name}
                      </span>
                      <span className="text-nano text-ink-subtle truncate">
                        {vm.sshHost || vm.ip}:{vm.sshPort}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className={cx(
                        "inline-flex items-center gap-1 text-[10px] font-semibold rounded-full px-2 py-0.5 border",
                        !isOnline
                          ? "bg-surface-sunken text-ink-muted border-line"
                          : vm.status === "running"
                            ? "bg-success-soft text-success-ink border-success-line/60"
                            : "bg-warning-soft text-warning-ink border-warning-line/60"
                      )}
                    >
                      <StatusDot
                        tone={
                          !isOnline
                            ? "neutral"
                            : vm.status === "running"
                              ? "success"
                              : "warning"
                        }
                        size="xs"
                      />
                      {vm.status === "running" ? "Active" : "Sleep"}
                    </span>

                    {isExpanded ? (
                      <ChevronUp className="size-4 text-ink-subtle" />
                    ) : (
                      <ChevronDown className="size-4 text-ink-subtle" />
                    )}
                  </div>
                </div>

                {/* Accordion Expanded Body */}
                {isExpanded && (
                  <div className="px-3 pb-3 pt-1 border-t border-line/60 flex flex-col gap-2 bg-surface-sunken/20">
                    {renderVmCardContent(vm, true)}
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      {/* ========================================================= */}
      {/* 5. MODAL FORM: TAMBAH / EDIT VIRTUAL MACHINE (2-TAB)       */}
      {/* ========================================================= */}
      {(isAddingVm || editingVm) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <Card className="w-full max-w-[300px] p-3 flex flex-col gap-2.5 shadow-xl border border-line bg-surface max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-line pb-2">
              <span className="text-caption font-bold text-ink">
                {editingVm ? "Edit Virtual Machine" : "Tambah Virtual Machine"}
              </span>
              <button
                type="button"
                onClick={() => {
                  setIsAddingVm(false)
                  setEditingVm(null)
                }}
                className="p-1 rounded-md text-ink-subtle hover:text-ink transition cursor-pointer"
              >
                <X className="size-4" />
              </button>
            </div>

            {/* Modal 2-Tab Selector */}
            <div className="grid grid-cols-2 gap-1 p-0.5 rounded-lg bg-surface-sunken border border-line text-nano">
              <button
                type="button"
                onClick={() => setAddVmTab("instabox")}
                className={cx(
                  "py-1 rounded font-semibold transition cursor-pointer text-center",
                  addVmTab === "instabox"
                    ? "bg-surface text-ink shadow-xs"
                    : "text-ink-subtle hover:text-ink"
                )}
              >
                InstaBox Cloud
              </button>
              <button
                type="button"
                onClick={() => setAddVmTab("manual")}
                className={cx(
                  "py-1 rounded font-semibold transition cursor-pointer text-center",
                  addVmTab === "manual"
                    ? "bg-surface text-ink shadow-xs"
                    : "text-ink-subtle hover:text-ink"
                )}
              >
                Manual SSH
              </button>
            </div>

            {/* Modal Form */}
            <form onSubmit={handleSaveForm} className="flex flex-col gap-2 text-nano">
              {addVmTab === "instabox" ? (
                <>
                  <div>
                    <label className="block font-semibold text-ink-subtle mb-0.5">
                      InstaBox API Key (ibk_...)
                    </label>
                    <input
                      type="password"
                      placeholder="e.g. ibk_examplekey..."
                      value={formApiKey}
                      onChange={(e) => setFormApiKey(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand font-mono text-[10.5px]"
                    />
                    <span className="text-[10px] text-ink-faint block mt-0.5">
                      Dapatkan dari menu Settings di web InstaBox untuk auto-connect.
                    </span>
                  </div>

                  <div>
                    <label className="block font-semibold text-ink-subtle mb-0.5">
                      Nama Virtual Machine (Opsional)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Linux-Dev-Server"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-ink-subtle mb-0.5">
                      Token SSH Sementara (Opsional jika ada)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. ibssh_exampletoken..."
                      value={formSshUser}
                      onChange={(e) => setFormSshUser(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand font-mono text-[10.5px]"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-ink-subtle mb-0.5">
                      URL Layar Virtual / Web Console (Opsional)
                    </label>
                    <input
                      type="url"
                      placeholder="e.g. https://instabox.sh/app/machines/..."
                      value={formScreenUrl}
                      onChange={(e) => setFormScreenUrl(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                    />
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="block font-semibold text-ink-subtle mb-0.5">
                      Nama Virtual Machine
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Ubuntu-VPS"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-ink-subtle mb-0.5">
                      Host Gateway / IP
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. 192.168.1.100 atau vps.example.com"
                      value={formSshHost}
                      onChange={(e) => setFormSshHost(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-1.5">
                    <div>
                      <label className="block font-semibold text-ink-subtle mb-0.5">
                        Port SSH
                      </label>
                      <input
                        type="number"
                        required
                        placeholder="22"
                        value={formSshPort}
                        onChange={(e) => setFormSshPort(e.target.value)}
                        className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-ink-subtle mb-0.5">
                        Masa Berlaku
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. 30d atau Permanent"
                        value={formTokenExpiry}
                        onChange={(e) => setFormTokenExpiry(e.target.value)}
                        className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block font-semibold text-ink-subtle mb-0.5">
                      User SSH
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. root atau ubuntu"
                      value={formSshUser}
                      onChange={(e) => setFormSshUser(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand font-mono text-[10.5px]"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-ink-subtle mb-0.5">
                      Port Web Layanan (Opsional)
                    </label>
                    <input
                      type="number"
                      placeholder="e.g. 8080 (Kosongkan bila tidak ada)"
                      value={formWebPort}
                      onChange={(e) => setFormWebPort(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-ink-subtle mb-0.5">
                      URL Layar Virtual (Opsional)
                    </label>
                    <input
                      type="url"
                      placeholder="e.g. http://192.168.1.100:6080/vnc.html"
                      value={formScreenUrl}
                      onChange={(e) => setFormScreenUrl(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                    />
                  </div>
                </>
              )}

              <div className="flex items-center gap-1.5 pt-1 mt-1 border-t border-line">
                <Button
                  size="sm"
                  variant="subtle"
                  type="button"
                  onClick={() => {
                    setIsAddingVm(false)
                    setEditingVm(null)
                  }}
                  className="flex-1 justify-center"
                >
                  {t("cancel_btn", "Batal")}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  type="submit"
                  className="flex-1 justify-center"
                >
                  {t("save_btn", "Simpan")}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ========================================================= */}
      {/* 6. MODAL JADWAL AUTO-RESTART                              */}
      {/* ========================================================= */}
      {schedulingVm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <Card className="w-full max-w-[300px] p-3 flex flex-col gap-2.5 shadow-xl border border-line bg-surface max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-line pb-2">
              <div className="flex flex-col min-w-0">
                <span className="text-caption font-bold text-ink">
                  Jadwal Auto-Restart
                </span>
                <span className="text-nano text-ink-subtle truncate">
                  {schedulingVm.name}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setSchedulingVm(null)}
                className="p-1 rounded-md text-ink-subtle hover:text-ink transition cursor-pointer"
              >
                <X className="size-4" />
              </button>
            </div>

            <form onSubmit={handleSaveSchedule} className="flex flex-col gap-2 text-nano">
              {/* Toggle Aktifkan */}
              <label className="flex items-center gap-2 cursor-pointer select-none p-1 rounded bg-surface-sunken/60 border border-line/60">
                <input
                  type="checkbox"
                  checked={schedEnabled}
                  onChange={(e) => setSchedEnabled(e.target.checked)}
                  className="rounded border-line text-brand focus:ring-0"
                />
                <span className="font-semibold text-ink text-micro">
                  Aktifkan Auto-Restart Terjadwal
                </span>
              </label>

              {/* Mode Pilihan: Interval vs Jam Tertentu */}
              <div className="flex flex-col gap-1">
                <span className="text-ink-subtle font-semibold">Tipe Penjadwalan:</span>
                <div className="grid grid-cols-2 gap-1 text-nano">
                  <button
                    type="button"
                    onClick={() => setSchedMode("interval")}
                    className={cx(
                      "py-1 px-1.5 rounded border text-center transition cursor-pointer",
                      schedMode === "interval"
                        ? "bg-brand/10 border-brand/50 text-brand-ink font-semibold"
                        : "bg-surface-sunken border-line text-ink-subtle"
                    )}
                  >
                    Setiap Interval
                  </button>
                  <button
                    type="button"
                    onClick={() => setSchedMode("clock")}
                    className={cx(
                      "py-1 px-1.5 rounded border text-center transition cursor-pointer",
                      schedMode === "clock"
                        ? "bg-brand/10 border-brand/50 text-brand-ink font-semibold"
                        : "bg-surface-sunken border-line text-ink-subtle"
                    )}
                  >
                    Jam Tertentu
                  </button>
                </div>
              </div>

              {schedMode === "interval" ? (
                <div className="grid grid-cols-2 gap-1.5">
                  <div>
                    <label className="block text-ink-subtle font-semibold mb-0.5">
                      Setiap:
                    </label>
                    <input
                      type="number"
                      min={1}
                      value={schedIntervalVal}
                      onChange={(e) => setSchedIntervalVal(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                    />
                  </div>
                  <div>
                    <label className="block text-ink-subtle font-semibold mb-0.5">
                      Satuan:
                    </label>
                    <select
                      value={schedIntervalUnit}
                      onChange={(e) => setSchedIntervalUnit(e.target.value as any)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                    >
                      <option value="hours">Jam</option>
                      <option value="minutes">Menit</option>
                      <option value="seconds">Detik</option>
                    </select>
                  </div>
                </div>
              ) : (
                <div>
                  <label className="block text-ink-subtle font-semibold mb-0.5">
                    Waktu Restart (HH:MM):
                  </label>
                  <input
                    type="time"
                    value={schedClockTime}
                    onChange={(e) => setSchedClockTime(e.target.value)}
                    className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand font-mono"
                  />
                  <span className="text-[10px] text-ink-faint block mt-0.5">
                    Dijalankan otomatis setiap hari pada jam ini.
                  </span>
                </div>
              )}

              {/* Khusus InstaBox: Reset Limit 8 Jam Mode */}
              {schedulingVm.provider === "instabox" && (
                <div className="rounded-tile bg-surface-sunken/80 border border-line p-2 flex flex-col gap-1.5 mt-0.5">
                  <span className="font-semibold text-ink text-[10.5px]">
                    Metode Restart InstaBox:
                  </span>
                  <label className="flex items-start gap-1.5 cursor-pointer text-[10.5px] text-ink">
                    <input
                      type="radio"
                      name="resetMode"
                      value="pause_resume"
                      checked={schedResetMode === "pause_resume"}
                      onChange={() => setSchedResetMode("pause_resume")}
                      className="mt-0.5 text-brand focus:ring-0"
                    />
                    <span>
                      <strong>Reset Limit 8 Jam (Siklus Pause & Resume)</strong> — Menidurkan mesin 5 detik lalu bangun lagi agar timer 8 jam reset ke 0 tanpa terkena penalti cooldown 20 menit.
                    </span>
                  </label>
                  <label className="flex items-start gap-1.5 cursor-pointer text-[10.5px] text-ink-subtle">
                    <input
                      type="radio"
                      name="resetMode"
                      value="cold_restart"
                      checked={schedResetMode === "cold_restart"}
                      onChange={() => setSchedResetMode("cold_restart")}
                      className="mt-0.5 text-brand focus:ring-0"
                    />
                    <span>Reboot Penuh Sistem (Stop lalu Start)</span>
                  </label>

                  <Button
                    size="sm"
                    variant="subtle"
                    type="button"
                    onClick={() => handleImmediateResetCycle(schedulingVm)}
                    className="mt-1 justify-center text-nano text-info-ink"
                  >
                    Reset Limit 8 Jam Sekarang
                  </Button>
                </div>
              )}

              <div className="flex items-center gap-1.5 pt-1 mt-1 border-t border-line">
                <Button
                  size="sm"
                  variant="subtle"
                  type="button"
                  onClick={() => setSchedulingVm(null)}
                  className="flex-1 justify-center"
                >
                  {t("cancel_btn", "Batal")}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  type="submit"
                  className="flex-1 justify-center"
                >
                  {t("save_btn", "Simpan Jadwal")}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ========================================================= */}
      {/* 7. MODAL KONFIRMASI HAPUS VM                              */}
      {/* ========================================================= */}
      {vmToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <Card className="w-full max-w-[270px] p-3 flex flex-col gap-2.5 shadow-xl border border-danger-line/60 bg-surface">
            <div className="flex items-center gap-2 text-danger-ink">
              <div className="size-7 rounded-full bg-danger-soft flex items-center justify-center shrink-0">
                <AlertTriangle className="size-4" />
              </div>
              <span className="text-caption font-bold text-ink">
                {t("confirm_delete_vm_title", "Konfirmasi Hapus")}
              </span>
            </div>

            <p className="text-nano text-ink-muted leading-relaxed">
              Apakah Anda yakin ingin menghapus{" "}
              <strong className="text-ink">{vmToDelete.name}</strong>? Tindakan
              ini akan menghapus konfigurasi koneksi VM dari MyServer.
            </p>

            <div className="flex items-center gap-1.5 pt-1 border-t border-line">
              <Button
                size="sm"
                variant="subtle"
                onClick={() => setVmToDelete(null)}
                className="flex-1 justify-center"
              >
                {t("cancel_btn", "Batal")}
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={handleDeleteConfirm}
                className="flex-1 justify-center"
              >
                {t("delete_btn", "Hapus")}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </ViewBody>
  )
}

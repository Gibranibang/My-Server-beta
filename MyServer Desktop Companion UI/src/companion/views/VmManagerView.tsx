import { useState, useMemo, useEffect, useRef, useCallback } from "react"
import {
  AlertTriangle,
  ArrowLeftRight,
  Laptop,
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
  LoaderCircle,
  Monitor,
  Pencil,
  Plus,
  Power,
  RotateCcw,
  Server,
  Terminal,
  Trash2,
  X,
  Zap,
} from "lucide-react"
import { getTranslation } from "../i18n"
import { useCompanion, useNotice } from "../store"
import { getCompanionApi } from "../api"
import { Button, Card, Chip, IconBadge, Mono, StatusDot, cx } from "../ui"
import { ViewBody, type ViewProps } from "./shared"
import type { Tone, VirtualMachine, VmAutoOnSchedule, VmAutoRestartSchedule, VmTelemetry } from "../types"

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

const DAY_NAME_TO_IDX: Record<string, number> = {
  sun: 0, min: 0, minggu: 0, sunday: 0, "0": 0,
  mon: 1, sen: 1, senin: 1, monday: 1, "1": 1,
  tue: 2, sel: 2, selasa: 2, tuesday: 2, "2": 2,
  wed: 3, rab: 3, rabu: 3, wednesday: 3, "3": 3,
  thu: 4, kam: 4, kamis: 4, thursday: 4, "4": 4,
  fri: 5, jum: 5, jumat: 5, friday: 5, "5": 5,
  sat: 6, sab: 6, sabtu: 6, saturday: 6, "6": 6,
}

const normalizeAutoOnDays = (days?: Array<number | string>): number[] => {
  if (!Array.isArray(days) || days.length === 0) return [1, 2, 3, 4, 5, 6, 0]
  const normalized: number[] = []
  for (const d of days) {
    if (typeof d === "number" && d >= 0 && d <= 6) {
      if (!normalized.includes(d)) normalized.push(d)
    } else {
      const idx = DAY_NAME_TO_IDX[String(d).trim().toLowerCase()]
      if (idx !== undefined && !normalized.includes(idx)) normalized.push(idx)
    }
  }
  return normalized.length > 0 ? normalized : [1, 2, 3, 4, 5, 6, 0]
}

const normalizeResetCycleMode = (mode?: string): "pause_resume" | "cold_restart" => {
  const m = String(mode || "").trim().toLowerCase()
  return m === "cold_restart" || m === "full_reboot" ? "cold_restart" : "pause_resume"
}

const getClientTimezoneInfo = () => {
  let scheduleTimezone = ""
  try {
    scheduleTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || ""
  } catch {}
  return {
    scheduleTimezone,
    tzOffsetMinutes: -new Date().getTimezoneOffset(),
  }
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
  const language = settings?.language || "id"
  const t = getTranslation(language)
  const { notify } = useNotice()

  // v4.5.0 Beta: Active Server tracking for filtering & scoping
  const [activeServerId, setActiveServerId] = useState<string>("")
  const [activeServerName, setActiveServerName] = useState<string>("Server")
  const [formScope, setFormScope] = useState<"server" | "local">("server")

  // Load server details on mount & sync active server
  useEffect(() => {
    const loadServerInfo = () => {
      api.getServerDetails?.().then((d) => {
        if (d?.serverId) {
          setActiveServerId(d.serverId)
        }
        if (d?.serverName) {
          setActiveServerName(d.serverName)
        }
      }).catch(() => {})
    }
    loadServerInfo()
    window.addEventListener("myserver:refresh", loadServerInfo)
    return () => window.removeEventListener("myserver:refresh", loadServerInfo)
  }, [])

  // State: list of VMs with localStorage persistence
  const [vms, setVms] = useState<VirtualMachine[]>(() => {
    if (typeof window !== "undefined") {
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

  const vmsRef = useRef<VirtualMachine[]>(vms)
  vmsRef.current = vms

  // v4.5.0 Beta: Filter VMs by Active Server & Calculate Smart Grouping
  const visibleVms = useMemo(() => {
    return vms.filter((v) => {
      if (v.scope === "server") {
        return !activeServerId || v.serverId === activeServerId
      }
      return true
    })
  }, [vms, activeServerId])

  const serverVms = useMemo(() => visibleVms.filter((v) => v.scope === "server"), [visibleVms])
  const localVms = useMemo(() => visibleVms.filter((v) => v.scope !== "server"), [visibleVms])
  const showGroupHeaders = serverVms.length > 0 && localVms.length > 0
  const isSingle = visibleVms.length === 1 && !showGroupHeaders
  const isMultiple = visibleVms.length > 1 || showGroupHeaders

  // v4.5.5 Beta: Ref pelindung penyimpanan agar tidak menimpa sebelum sinkronisasi backend selesai
  const hasLoadedRemote = useRef<boolean>(false)
  // Tombstone Guard: Mencegah VM yang sedang dihapus muncul kembali akibat polling in-flight atau event window focus
  const pendingDeleteIdsRef = useRef<Set<string>>(new Set())
  // Optimistic Mutation Guard: Mencegah polling 4s/30s mengembalikan tombol Power/Always-On/Auto-On/Auto-Restart ke posisi lama
  const pendingMutationsRef = useRef<Map<string, { expiresAt: number; patch: Partial<VirtualMachine> }>>(new Map())
  // Newly Created VM Guard: Menjaga VM baru tetap tampil selama proses simpan ke backend sedang berlangsung
  const pendingCreatedVmsRef = useRef<Map<string, { expiresAt: number; vm: VirtualMachine }>>(new Map())
  // Smart Reset Timestamp Tracker: Membedakan reset siklus 8 jam yang sah vs angka 0 transien dari API
  const lastSmartResetRef = useRef<Map<string, number>>(new Map())

  const [isDeletingVm, setIsDeletingVm] = useState<boolean>(false)
  // Soft-Delete tracking for non-blocking Inline Card Degradation
  const [deletingVmIds, setDeletingVmIds] = useState<Set<string>>(new Set())

  const recordPendingMutation = useCallback((vmId: string, patch: Partial<VirtualMachine>, ttlMs = 15000) => {
    if (!vmId) return
    const prev = pendingMutationsRef.current.get(vmId)
    const mergedPatch: Partial<VirtualMachine> = prev && Date.now() < prev.expiresAt
      ? { ...prev.patch, ...patch }
      : { ...patch }
    pendingMutationsRef.current.set(vmId, {
      expiresAt: Date.now() + ttlMs,
      patch: mergedPatch,
    })
  }, [])

  const applyPendingMutations = useCallback((incoming: VirtualMachine, existing?: VirtualMachine): VirtualMachine => {
    let result: VirtualMachine = { ...incoming }
    const now = Date.now()

    // Lindungi runtimeMinutes pada VM yang sedang menyala agar tidak ter-reset ke 0 akibat respons transien
    const lastResetTs = lastSmartResetRef.current.get(result.id) || 0
    const recentlyReset = now - lastResetTs < 45000
    if (
      existing &&
      result.status === "running" &&
      existing.status === "running" &&
      (result.runtimeMinutes == null || result.runtimeMinutes === 0) &&
      (existing.runtimeMinutes || 0) > 0 &&
      !recentlyReset
    ) {
      result.runtimeMinutes = existing.runtimeMinutes
    }

    const pending = pendingMutationsRef.current.get(result.id)
    if (pending) {
      if (now < pending.expiresAt) {
        result = {
          ...result,
          ...pending.patch,
          autoOn: pending.patch.autoOn
            ? { ...(result.autoOn || {}), ...pending.patch.autoOn }
            : result.autoOn,
          autoRestart: pending.patch.autoRestart
            ? { ...(result.autoRestart || {}), ...pending.patch.autoRestart }
            : result.autoRestart,
        }
      } else {
        pendingMutationsRef.current.delete(result.id)
      }
    }
    if (result.autoOn) {
      result = {
        ...result,
        autoOn: {
          ...result.autoOn,
          days: normalizeAutoOnDays(result.autoOn.days),
        },
      }
    }
    if (result.autoRestart) {
      result = {
        ...result,
        autoRestart: {
          ...result.autoRestart,
          resetCycleMode: normalizeResetCycleMode(result.autoRestart.resetCycleMode || result.autoRestart.resetMode),
        },
      }
    }
    return result
  }, [])

  // Load & Sinkronisasi Pintar VM Server & Lokal (Mendukung Multi-Device & Bebas Zombie VM)
  const syncVmsFromBackend = useCallback(() => {
    if (api.loadVms) {
      const wasLoadedBefore = hasLoadedRemote.current
      api.loadVms().then((remoteVms) => {
        hasLoadedRemote.current = true
        if (Array.isArray(remoteVms)) {
          setVms((prev) => {
            const now = Date.now()
            const prevMap = new Map(prev.map((p) => [p.id, p]))

            // Saring VM yang berada dalam tombstone penghapusan & terapkan pelindung mutasi optimistik
            const filteredRemote = remoteVms
              .filter((v: any) => v && v.id && !pendingDeleteIdsRef.current.has(v.id))
              .map((v: any) => applyPendingMutations(v as VirtualMachine, prevMap.get(v.id)))

            const remoteServerVms = filteredRemote.filter((v) => v.scope === "server")
            const remoteServerIds = new Set(remoteServerVms.map((v) => v.id))

            // Pertahankan VM baru yang sedang dalam proses simpan ke server agar tidak berkedip hilang
            pendingCreatedVmsRef.current.forEach((entry, createdId) => {
              if (now >= entry.expiresAt || pendingDeleteIdsRef.current.has(createdId)) {
                pendingCreatedVmsRef.current.delete(createdId)
              } else if (entry.vm.scope === "server" && !remoteServerIds.has(createdId)) {
                const guardedCreated = applyPendingMutations(entry.vm, prevMap.get(createdId))
                remoteServerVms.push(guardedCreated)
                remoteServerIds.add(createdId)
              }
            })

            const remoteLocalVms = filteredRemote.filter((v) => v.scope !== "server")
            const remoteLocalMap = new Map(remoteLocalVms.map((v) => [v.id, v]))
            const currentLocals = prev.filter(
              (v) => v.scope !== "server" && !pendingDeleteIdsRef.current.has(v.id)
            )

            let baseLocals: VirtualMachine[]
            if (!wasLoadedBefore && currentLocals.length === 0) {
              baseLocals = remoteLocalVms
            } else {
              baseLocals = currentLocals.map((loc) => {
                const rem = remoteLocalMap.get(loc.id)
                if (!rem) return applyPendingMutations(loc, loc)
                return applyPendingMutations(
                  {
                    ...loc,
                    status: rem.status || loc.status,
                    runtimeMinutes:
                      typeof rem.runtimeMinutes === "number" && rem.runtimeMinutes > 0
                        ? rem.runtimeMinutes
                        : loc.runtimeMinutes,
                    machineId: rem.machineId || loc.machineId,
                    telemetry: rem.telemetry ?? loc.telemetry,
                  },
                  loc
                )
              })
            }

            const cleanLocals = baseLocals.filter((v) => !remoteServerIds.has(v.id) && !pendingDeleteIdsRef.current.has(v.id))

            // Server VMs adalah sumber kebenaran mutlak (authoritative) dari server ZimaOS.
            // Jangan hidupkan kembali (resurrect) VM server yang sudah dihapus dari server!
            const merged = [...cleanLocals, ...remoteServerVms]
            if (typeof window !== "undefined") {
              try {
                localStorage.setItem("myserver_vms", JSON.stringify(merged))
              } catch {}
            }
            return merged
          })
        }
      }).catch(() => {
        hasLoadedRemote.current = true
      })
    }
  }, [api, applyPendingMutations])

  // Multi-Device Real-Time Sync: Polling cepat setiap 4 detik saat menu aktif & saat window kembali fokus
  useEffect(() => {
    syncVmsFromBackend()
    const interval = setInterval(syncVmsFromBackend, 4000)
    const onRefresh = () => syncVmsFromBackend()
    const onFocus = () => syncVmsFromBackend()
    window.addEventListener("myserver:refresh", onRefresh)
    window.addEventListener("focus", onFocus)
    return () => {
      clearInterval(interval)
      window.removeEventListener("myserver:refresh", onRefresh)
      window.removeEventListener("focus", onFocus)
    }
  }, [syncVmsFromBackend, activeServerId])

  // Helper persisten untuk aksi pengguna eksplisit (Add, Edit, Migrate)
  const persistVmChanges = useCallback((updatedVms: VirtualMachine[], syncRemote = true): Promise<any> => {
    setVms(updatedVms)
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("myserver_vms", JSON.stringify(updatedVms))
      } catch {}
    }
    if (syncRemote && api.saveVms) {
      return api.saveVms(updatedVms).catch((err) => {
        console.warn("[VmManagerView] saveVms error:", err)
        return null
      })
    }
    return Promise.resolve({ status: "ok", success: true })
  }, [api])

  // Helper atomik untuk menyimpan perubahan VM tunggal ke Core Service & ZimaOS dengan rollback jika gagal
  const persistSingleVmPatch = useCallback(
    async (
      vm: VirtualMachine,
      patch: Partial<VirtualMachine>,
      uiExtra?: Partial<VirtualMachine>
    ): Promise<boolean> => {
      const includeTz = Boolean(patch.autoOn || patch.autoRestart || patch.keepAliveEnabled !== undefined)
      const serverPatch: Partial<VirtualMachine> = includeTz
        ? { ...patch, ...getClientTimezoneInfo() }
        : { ...patch }
      const optimisticPatch: Partial<VirtualMachine> = {
        ...serverPatch,
        ...(uiExtra || {}),
      }

      const prevSnapshot = vmsRef.current.find((item) => item.id === vm.id) || vm
      recordPendingMutation(vm.id, optimisticPatch, 15000)

      const applyLocalList = (list: VirtualMachine[]) => {
        setVms(list)
        if (typeof window !== "undefined") {
          try {
            localStorage.setItem("myserver_vms", JSON.stringify(list))
          } catch {}
        }
      }

      const updatedList = vmsRef.current.map((item) =>
        item.id === vm.id
          ? {
              ...item,
              ...optimisticPatch,
              autoOn: optimisticPatch.autoOn
                ? {
                    ...(item.autoOn || {}),
                    ...optimisticPatch.autoOn,
                    days: normalizeAutoOnDays(optimisticPatch.autoOn.days),
                  }
                : item.autoOn,
              autoRestart: optimisticPatch.autoRestart
                ? {
                    ...(item.autoRestart || {}),
                    ...optimisticPatch.autoRestart,
                    resetCycleMode: normalizeResetCycleMode(
                      optimisticPatch.autoRestart.resetCycleMode || optimisticPatch.autoRestart.resetMode
                    ),
                  }
                : item.autoRestart,
            }
          : item
      )
      applyLocalList(updatedList)

      if (!api.updateVm) {
        const res = await persistVmChanges(updatedList, true)
        return Boolean(!res || res.status !== "error")
      }

      const rollback = (errMsg: string) => {
        pendingMutationsRef.current.delete(vm.id)
        const restored = vmsRef.current.map((item) => (item.id === vm.id ? prevSnapshot : item))
        applyLocalList(restored)
        notify(errMsg, "danger")
      }

      try {
        const res = await api.updateVm(vm.id, serverPatch, vm.serverId)
        const failed =
          !res ||
          res.status === "error" ||
          res.success === false ||
          (vm.scope === "server" && res.backend_updated === false)
        if (failed) {
          rollback(
            res?.message ||
              (language === "id"
                ? `Gagal menyinkronkan perubahan ${vm.name} ke server ZimaOS.`
                : `Failed to sync ${vm.name} changes to ZimaOS server.`)
          )
          return false
        }
        return true
      } catch (err: any) {
        rollback(
          language === "id"
            ? `Gagal menyimpan ${vm.name}: ${err?.message || String(err)}`
            : `Failed to save ${vm.name}: ${err?.message || String(err)}`
        )
        return false
      }
    },
    [api, language, notify, persistVmChanges, recordPendingMutation]
  )

  // Save to localStorage whenever vms change
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("myserver_vms", JSON.stringify(vms))
      } catch {}
    }
  }, [vms])

  // Sinkronisasi langsung metrik InstaBox (dipakai oleh VM lokal atau setelah aksi Power)
  const syncActiveInstaboxVms = useCallback((targetVmId?: string) => {
    const knownApiKey = vmsRef.current.find((v) => v.provider === "instabox" && v.apiKey)?.apiKey
    vmsRef.current.forEach((vm) => {
      if (pendingDeleteIdsRef.current.has(vm.id)) return
      if (targetVmId && vm.id !== targetVmId) return
      // Untuk polling rutin (tanpa targetVmId), VM server sudah disinkronkan oleh daemon ZimaOS & polling 4s
      if (!targetVmId && vm.scope === "server") return

      const apiKey = vm.apiKey || knownApiKey
      if (vm.provider === "instabox" && apiKey) {
        const mid = vm.machineId || (vm.sshUser?.startsWith("m_") ? vm.sshUser : undefined)
        api.syncInstaBoxVm({ apiKey, machineId: mid, vmName: vm.name, vmId: vm.id }).then((res: any) => {
          if (res && res.success && !pendingDeleteIdsRef.current.has(vm.id)) {
            const stateStr = String(res.state || "").toLowerCase()
            const isRunning = stateStr === "running" || stateStr === "active" || stateStr === "starting" || stateStr === "resuming"
            setVms((prev) =>
              prev.map((v) => {
                if (v.id !== vm.id) return v
                const candidate: VirtualMachine = {
                  ...v,
                  machineId: res.machineId || v.machineId || mid,
                  status: isRunning ? "running" : "sleeping",
                  sleepingSince: !isRunning ? (v.sleepingSince || Date.now()) : undefined,
                  runtimeMinutes:
                    typeof res.runtimeMinutes === "number"
                      ? res.runtimeMinutes
                      : (v.runtimeMinutes ?? 0),
                  maxRuntimeMinutes: res.maxRuntimeMinutes || 480,
                  idleTimeoutMinutes: res.idleTimeoutMinutes || 30,
                  screenUrl: v.screenUrl || res.screenUrl,
                  sshHost: res.sshHost || v.sshHost || "ssh.instabox.sh",
                  sshPort: res.sshPort || v.sshPort || 2222,
                  sshUser: res.sshUser || v.sshUser || res.machineId,
                  ip: res.ip || res.sshHost || v.ip || "ssh.instabox.sh",
                  apiKey: v.apiKey || apiKey,
                  telemetry: isRunning && res.telemetry ? res.telemetry : v.telemetry ?? null,
                }
                return applyPendingMutations(candidate, v)
              })
            )
          }
        }).catch(() => {})
      }
    })
  }, [api, applyPendingMutations])

  // Periodic InstaBox Sync & Local Runtime Counter
  useEffect(() => {
    syncActiveInstaboxVms()

    // Continuous anti-sleep heartbeat & immediate wake guard for local InstaBox VMs with keepAliveEnabled
    const keepAlivePing = () => {
      vmsRef.current.forEach((vm) => {
        if (pendingDeleteIdsRef.current.has(vm.id)) return
        const pending = pendingMutationsRef.current.get(vm.id)
        if (pending && Date.now() < pending.expiresAt && "status" in pending.patch) return

        // Isolasi: VM scope server dikontrol 100% oleh daemon backend ZimaOS
        if (vm.scope !== "server" && vm.provider === "instabox" && vm.keepAliveEnabled && isOnline) {
          const mid = vm.machineId || (vm.sshUser?.startsWith("m_") ? vm.sshUser : undefined)
          if (vm.status === "sleeping") {
            api.wakeInstaBoxVm({ apiKey: vm.apiKey, machineId: mid, vmId: vm.id }).then((res: any) => {
              if (res && res.status === "ok") {
                setTimeout(() => {
                  syncActiveInstaboxVms(vm.id)
                }, 3000)
              }
            }).catch(() => {})
          }
          if (vm.status === "running" && (vm.runtimeMinutes || 0) >= 450) {
            handleImmediateResetCycle(vm)
          }
        }
      })
    }
    const keepAliveInterval = setInterval(keepAlivePing, 900000)

    const syncInterval = setInterval(() => {
      syncActiveInstaboxVms()
      keepAlivePing()
    }, 30000)

    return () => {
      clearInterval(syncInterval)
      clearInterval(keepAliveInterval)
    }
  }, [vms.length, isOnline, syncActiveInstaboxVms])

  // Accordion state (All VM cards start minimized by default)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Modal Auto-On Scheduler state
  const [autoOnVm, setAutoOnVm] = useState<VirtualMachine | null>(null)
  const [autoOnEnabled, setAutoOnEnabled] = useState<boolean>(true)
  const [autoOnMode, setAutoOnMode] = useState<"clock" | "after_off">("clock")
  const [autoOnClockTime, setAutoOnClockTime] = useState<string>("07:00")
  const [autoOnDays, setAutoOnDays] = useState<number[]>([1, 2, 3, 4, 5, 6, 0])
  const [autoOnDelayVal, setAutoOnDelayVal] = useState<number | string>(30)
  const [autoOnDelayUnit, setAutoOnDelayUnit] = useState<"seconds" | "minutes" | "hours">("minutes")

  // Modal Virtual Screen Target Selector state
  const [screenPromptVm, setScreenPromptVm] = useState<VirtualMachine | null>(null)
  const [rememberScreenTarget, setRememberScreenTarget] = useState<boolean>(false)
  const [formScreenOpenTarget, setFormScreenOpenTarget] = useState<"window" | "browser" | "ask">("ask")

  // Modals state
  const [vmToDelete, setVmToDelete] = useState<VirtualMachine | null>(null)
  const [editingVm, setEditingVm] = useState<VirtualMachine | null>(null)
  const [isAddingVm, setIsAddingVm] = useState<boolean>(false)

  // Modal Auto-Restart Scheduler state
  const [schedulingVm, setSchedulingVm] = useState<VirtualMachine | null>(null)

  // Sync form fields when editingVm changes
  useEffect(() => {
    if (editingVm) {
      setFormScope(editingVm.scope || "server")
      setFormName(editingVm.name || "")
      setAddVmTab(editingVm.provider === "instabox" ? "instabox" : "manual")
      setFormSshHost(editingVm.sshHost || editingVm.ip || "")
      setFormSshUser(editingVm.sshUser || "")
      setFormSshPort(editingVm.sshPort || 2222)
      setFormTokenExpiry(editingVm.tokenExpiry || "")
      setFormWebPort(editingVm.webPort || "")
      setFormScreenUrl(editingVm.screenUrl || "")
      setFormScreenOpenTarget(editingVm.screenOpenTarget || "ask")
      setFormApiKey(editingVm.apiKey || "")
    }
  }, [editingVm])

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
  const [powerBusyVmId, setPowerBusyVmId] = useState<string | null>(null)

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
      notify(language === "id" ? `${label} disalin ke papan klip!` : `${label} copied to clipboard!`, "success")
    } catch {
      notify(language === "id" ? `Gagal menyalin ${label}.` : `Failed to copy ${label}.`, "danger")
    }
  }

  // Generate full SSH command
  const getSshCommand = (vm: VirtualMachine) => {
    const port = vm.sshPort || (vm.provider === "instabox" ? 2222 : 22)
    const user = vm.sshUser ? `${vm.sshUser}@` : (vm.machineId ? `${vm.machineId}@` : "")
    const host = vm.sshHost || vm.ip || (vm.provider === "instabox" ? "ssh.instabox.sh" : "127.0.0.1")
    return `ssh -p ${port} ${user}${host}`
  }

  // Toggle Power (Wake / Sleep) - Real API call to InstaBox Cloud with Instant Optimistic Update
  const handleTogglePower = async (vm: VirtualMachine) => {
    if (!isOnline) {
      notify(language === "id" ? "Server sedang offline." : "Server is currently offline.", "warning")
      return
    }

    const prevStatus = vm.status
    const prevKeepAlive = vm.keepAliveEnabled
    const prevRuntime = vm.runtimeMinutes
    const isCurrentlyRunning = vm.status === "running"
    const nextStatus: VirtualMachine["status"] = isCurrentlyRunning ? "sleeping" : "running"
    // Jika pengguna mematikan/menidurkan VM secara manual saat Always-On aktif, matikan Always-On agar VM tidak langsung dibangunkan lagi
    const disableKeepAliveOnManualSleep = Boolean(isCurrentlyRunning && vm.keepAliveEnabled)
    const nextKeepAlive = disableKeepAliveOnManualSleep ? false : vm.keepAliveEnabled

    setPowerBusyVmId(vm.id)

    // 1. Optimistic update seketika agar tombol Power terasa instan & dilindungi selama transisi
    recordPendingMutation(
      vm.id,
      {
        status: nextStatus,
        keepAliveEnabled: nextKeepAlive,
        ...(nextStatus === "sleeping" ? { runtimeMinutes: 0, sleepingSince: Date.now() } : { sleepingSince: undefined }),
      },
      20000
    )

    setVms((prev) =>
      prev.map((item) =>
        item.id === vm.id
          ? {
              ...item,
              status: nextStatus,
              keepAliveEnabled: nextKeepAlive,
              runtimeMinutes: nextStatus === "sleeping" ? 0 : item.runtimeMinutes,
              sleepingSince: nextStatus === "sleeping" ? Date.now() : undefined,
              lastActive: nextStatus === "running" ? "Just now" : "Sleeping",
            }
          : item
      )
    )

    const restorePowerFailure = async (errMsg: string) => {
      pendingMutationsRef.current.delete(vm.id)
      setVms((prev) =>
        prev.map((item) =>
          item.id === vm.id
            ? { ...item, status: prevStatus, keepAliveEnabled: prevKeepAlive, runtimeMinutes: prevRuntime }
            : item
        )
      )
      if (disableKeepAliveOnManualSleep && api.updateVm) {
        await api.updateVm(vm.id, { keepAliveEnabled: prevKeepAlive }, vm.serverId).catch(() => {})
      }
      notify(errMsg, "danger")
    }

    // Pastikan Always-On dimatikan lebih dulu di backend sebelum sinyal /sleep agar scheduler tidak langsung membangunkan VM lagi
    if (disableKeepAliveOnManualSleep && api.updateVm) {
      try {
        const kaRes = await api.updateVm(
          vm.id,
          { keepAliveEnabled: false, ...getClientTimezoneInfo() },
          vm.serverId
        )
        if (!kaRes || kaRes.status === "error" || kaRes.success === false || (vm.scope === "server" && kaRes.backend_updated === false)) {
          pendingMutationsRef.current.delete(vm.id)
          setVms((prev) =>
            prev.map((item) =>
              item.id === vm.id
                ? { ...item, status: prevStatus, keepAliveEnabled: prevKeepAlive, runtimeMinutes: prevRuntime }
                : item
            )
          )
          notify(
            kaRes?.message ||
              (language === "id" ? "Gagal menonaktifkan Always-On sebelum menidurkan VM." : "Failed to disable Always-On before sleeping VM."),
            "danger"
          )
          setPowerBusyVmId(null)
          return
        }
      } catch (err: any) {
        await restorePowerFailure(
          language === "id" ? `Gagal menonaktifkan Always-On: ${err?.message || String(err)}` : `Failed to disable Always-On: ${err?.message || String(err)}`
        )
        setPowerBusyVmId(null)
        return
      }
    }

    const useBackendPower = vm.provider === "instabox" || vm.scope === "server"
    if (useBackendPower) {
      try {
        const payload = {
          apiKey: vm.apiKey,
          machineId: vm.machineId || (vm.sshUser?.startsWith("m_") ? vm.sshUser : undefined),
          vmId: vm.id,
          scope: vm.scope,
          serverId: vm.serverId,
        }
        const res = isCurrentlyRunning
          ? await api.pauseInstaBoxVm(payload)
          : await api.wakeInstaBoxVm(payload)

        if (!res || res.status === "error" || res.success === false) {
          await restorePowerFailure(
            language === "id"
              ? `Gagal mengubah daya VM: ${res?.message || "Error"}`
              : `Failed to change VM power: ${res?.message || "Error"}`
          )
          setPowerBusyVmId(null)
          return
        }

        const realStatus: VirtualMachine["status"] = res?.vmStatus || nextStatus
        recordPendingMutation(
          vm.id,
          {
            status: realStatus,
            keepAliveEnabled: nextKeepAlive,
            ...(realStatus === "sleeping" ? { runtimeMinutes: 0 } : {}),
          },
          20000
        )

        setVms((prev) =>
          prev.map((item) =>
            item.id === vm.id
              ? {
                  ...item,
                  status: realStatus,
                  keepAliveEnabled: nextKeepAlive,
                  machineId: res?.machineId || item.machineId || payload.machineId,
                  sshHost: item.sshHost || (item.provider === "instabox" ? "ssh.instabox.sh" : ""),
                  sshPort: item.sshPort || (item.provider === "instabox" ? 2222 : 22),
                  sshUser: item.sshUser || res?.machineId || payload.machineId,
                  lastActive: realStatus === "running" ? "Just now" : "Sleeping",
                }
              : item
          )
        )
        if (vm.provider === "instabox") {
          setTimeout(() => {
            syncActiveInstaboxVms(vm.id)
          }, 4000)
        }
        notify(
          nextStatus === "running"
            ? (language === "id" ? `${vm.name}: VM Berhasil Dibangunkan!` : `${vm.name}: VM Woken Up Successfully!`)
            : disableKeepAliveOnManualSleep
              ? (language === "id" ? `${vm.name}: VM Ditidurkan (Always-On dinonaktifkan)` : `${vm.name}: VM Put to Sleep (Always-On disabled)`)
              : (language === "id" ? `${vm.name}: VM Berhasil Ditidurkan!` : `${vm.name}: VM Put to Sleep Successfully!`),
          "success"
        )
      } catch (err: any) {
        await restorePowerFailure(
          language === "id" ? `Komunikasi API gagal: ${err?.message || String(err)}` : `API communication failed: ${err?.message || String(err)}`
        )
      } finally {
        setPowerBusyVmId(null)
      }
    } else {
      const ok = await persistSingleVmPatch(
        vm,
        { status: nextStatus, keepAliveEnabled: nextKeepAlive },
        nextStatus === "sleeping" ? { runtimeMinutes: 0, sleepingSince: Date.now() } : { sleepingSince: undefined }
      )
      if (ok) {
        notify(
          nextStatus === "running"
            ? `${vm.name}: ${language === "id" ? "VM Dibangunkan" : "VM Woken Up"}`
            : `${vm.name}: ${language === "id" ? "VM Masuk Mode Tidur" : "VM Entered Sleep Mode"}`,
          "neutral"
        )
      }
      setPowerBusyVmId(null)
    }
  }

  // v4.5.0 Beta: 1-Click Migration between Local & Server
  const handleMigrateVm = (vm: VirtualMachine) => {
    const isCurrentlyServer = vm.scope === "server"
    const nextScope: "server" | "local" = isCurrentlyServer ? "local" : "server"
    const nextServerId = nextScope === "server" ? activeServerId : undefined
    const nextServerName = nextScope === "server" ? activeServerName : undefined

    recordPendingMutation(
      vm.id,
      {
        scope: nextScope,
        serverId: nextServerId,
        serverName: nextServerName,
      },
      15000
    )

    const updated = vms.map((item) =>
      item.id === vm.id
        ? {
            ...item,
            scope: nextScope,
            serverId: nextServerId,
            serverName: nextServerName,
          }
        : item
    )
    persistVmChanges(updated, false)

    if (api.migrateVm) {
      void api.migrateVm(vm.id, nextScope).catch(() => {
        if (api.saveVms) void api.saveVms(updated).catch(() => {})
      })
    } else if (api.saveVms) {
      void api.saveVms(updated).catch(() => {})
    }

    const targetLabel = nextScope === "server" ? `${activeServerName}` : (language === "id" ? "Perangkat Ini (Lokal)" : "This Device (Local)")
    notify(
      language === "id"
        ? `${vm.name} ${t("vm_migrated_notice", "berhasil dipindahkan ke")} ${targetLabel}!`
        : `${vm.name} ${t("vm_migrated_notice", "migrated to")} ${targetLabel}!`,
      "success"
    )
  }

  // Delete execution dengan Immediate Removal & Anti-Zombie 60s Tombstone
  const handleDeleteConfirm = async () => {
    if (!vmToDelete || isDeletingVm) return
    const targetId = vmToDelete.id
    const targetScope = vmToDelete.scope || "server"
    const targetServerId = vmToDelete.serverId
    const targetName = vmToDelete.name

    setIsDeletingVm(true)
    // 1. Segera tutup dialog konfirmasi & aktifkan tombstone 60 detik
    setVmToDelete(null)
    pendingDeleteIdsRef.current.add(targetId)
    pendingMutationsRef.current.delete(targetId)
    pendingCreatedVmsRef.current.delete(targetId)
    setDeletingVmIds((prev) => new Set([...prev, targetId]))

    // 2. Hapus kartu dari UI & localStorage SEGERA agar tidak ada jeda atau kartu muncul kembali
    setVms((prev) => {
      const next = prev.filter((v) => v.id !== targetId)
      if (typeof window !== "undefined") {
        try {
          localStorage.setItem("myserver_vms", JSON.stringify(next))
        } catch {}
      }
      return next
    })

    // 3. Eksekusi API Delete ke Core Service & server ZimaOS secara asynchronous
    try {
      if (api.deleteVm) {
        await api.deleteVm(targetId, targetScope, targetServerId)
      }
      notify(language === "id" ? `${targetName} berhasil dihapus.` : `${targetName} deleted successfully.`, "neutral")
    } catch (err) {
      console.warn("[VmManagerView] deleteVm error:", err)
      notify(language === "id" ? `Gagal menghapus ${targetName} di server.` : `Failed to delete ${targetName} on server.`, "danger")
      pendingDeleteIdsRef.current.delete(targetId)
      syncVmsFromBackend()
    } finally {
      setIsDeletingVm(false)
      setDeletingVmIds((prev) => {
        const next = new Set(prev)
        next.delete(targetId)
        return next
      })
      // Pertahankan tombstone selama 60 detik (selaras dengan backend) untuk mencegah zombie VM
      setTimeout(() => {
        pendingDeleteIdsRef.current.delete(targetId)
      }, 60000)
    }
  }

  // Open Edit Modal
  const handleOpenEdit = (vm: VirtualMachine) => {
    setEditingVm(vm)
    setFormScope(vm.scope || 'local')
    setAddVmTab(vm.provider === "instabox" ? "instabox" : "manual")
    setFormName(vm.name)
    setFormSshHost(vm.sshHost || vm.ip || "")
    setFormSshUser(vm.sshUser || "")
    setFormSshPort(vm.sshPort || 2222)
    setFormTokenExpiry(vm.tokenExpiry || "")
    setFormWebPort(vm.webPort || "")
    setFormScreenUrl(vm.screenUrl || "")
    setFormScreenOpenTarget(vm.screenOpenTarget || "ask")
    setFormApiKey(vm.apiKey || "")
  }

  // Dedicated Always-On Toggle for InstaBox (Immediately wakes sleeping VM!)
  const handleToggleKeepAlive = async (vm: VirtualMachine) => {
    const nextVal = !vm.keepAliveEnabled
    // Smart Reset batas 8 jam ditangani otomatis oleh scheduler server & daemon lokal ketika Always-On aktif,
    // sehingga tombol Auto-Restart tetap independen dan tidak menyala/tersangkut otomatis.
    const nextAutoOn: VmAutoOnSchedule | undefined =
      nextVal && vm.autoOn?.enabled && vm.autoOn.mode === "after_off"
        ? { ...vm.autoOn, enabled: false }
        : vm.autoOn

    const patch: Partial<VirtualMachine> = {
      keepAliveEnabled: nextVal,
      ...(nextAutoOn !== undefined ? { autoOn: nextAutoOn } : {}),
    }

    const ok = await persistSingleVmPatch(vm, patch)
    if (!ok) return

    notify(
      nextVal
        ? (language === "id" ? `${vm.name}: Fitur Tetap Nyala 24/7 diaktifkan` : `${vm.name}: Always-On 24/7 enabled`)
        : (language === "id" ? `${vm.name}: Fitur Tetap Nyala dinonaktifkan` : `${vm.name}: Always-On disabled`),
      "info"
    )
    // Jika VM sedang tidur saat Always-On diaktifkan, langsung bangunkan sekarang juga!
    if (nextVal && vm.status === "sleeping") {
      await handleTogglePower({
        ...vm,
        keepAliveEnabled: true,
        autoOn: nextAutoOn,
      })
    }
  }

  // Open Auto-On Schedule Modal
  const handleOpenAutoOn = (vm: VirtualMachine) => {
    setAutoOnVm(vm)
    if (vm.autoOn) {
      setAutoOnEnabled(vm.autoOn.enabled)
      setAutoOnMode(vm.autoOn.mode || "clock")
      setAutoOnClockTime(vm.autoOn.clockTime || "07:00")
      setAutoOnDays(normalizeAutoOnDays(vm.autoOn.days))
      setAutoOnDelayVal(vm.autoOn.delayValue || 30)
      setAutoOnDelayUnit(vm.autoOn.delayUnit || "minutes")
    } else {
      setAutoOnEnabled(true)
      setAutoOnMode("clock")
      setAutoOnClockTime("07:00")
      setAutoOnDays([1, 2, 3, 4, 5, 6, 0])
      setAutoOnDelayVal(30)
      setAutoOnDelayUnit("minutes")
    }
  }

  const handleToggleAutoOnDay = (dayIndex: number) => {
    setAutoOnDays((prev) =>
      prev.includes(dayIndex)
        ? (prev.length > 1 ? prev.filter((d) => d !== dayIndex) : prev)
        : [...prev, dayIndex]
    )
  }

  const handleSaveAutoOn = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!autoOnVm) return
    const nextAutoOn: VmAutoOnSchedule = {
      enabled: autoOnEnabled,
      mode: autoOnMode,
      clockTime: autoOnClockTime || "07:00",
      days: normalizeAutoOnDays(autoOnDays),
      delayValue: Math.max(1, Number(autoOnDelayVal) || 30),
      delayUnit: autoOnDelayUnit,
    }
    const disableKeepAlive = Boolean(autoOnEnabled && autoOnMode === "after_off" && autoOnVm.keepAliveEnabled)
    const nextKeepAlive = disableKeepAlive ? false : autoOnVm.keepAliveEnabled

    const uiExtra: Partial<VirtualMachine> =
      autoOnVm.status !== "running"
        ? { sleepingSince: autoOnEnabled && autoOnMode === "after_off" ? Date.now() : (autoOnVm.sleepingSince || Date.now()) }
        : { sleepingSince: undefined }

    const ok = await persistSingleVmPatch(
      autoOnVm,
      {
        autoOn: nextAutoOn,
        keepAliveEnabled: nextKeepAlive,
      },
      uiExtra
    )
    if (!ok) return

    notify(
      language === "id"
        ? `Jadwal Auto-On ${autoOnVm.name} berhasil disimpan!`
        : `Auto-On schedule for ${autoOnVm.name} saved!`,
      "success"
    )
    setAutoOnVm(null)
  }

  // Save Add/Edit
  const handleSaveForm = (e: React.FormEvent) => {
    e.preventDefault()
    const cleanName = formName.trim()
    if (!cleanName && addVmTab === "manual") {
      notify(language === "id" ? "Nama Virtual Machine wajib diisi." : "Virtual Machine name is required.", "danger")
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
    const targetServerId = formScope === "server" ? (editingVm?.serverId || activeServerId) : undefined
    const tzInfo = getClientTimezoneInfo()
    let pendingInitialSave: Promise<any> = Promise.resolve()

    if (editingVm) {
      const editPatch: Partial<VirtualMachine> = {
        scope: formScope,
        serverId: targetServerId,
        serverName: formScope === "server" ? (editingVm.serverName || activeServerName) : undefined,
        name: cleanName || editingVm.name,
        provider: addVmTab,
        sshHost: cleanHost || (addVmTab === "instabox" ? "ssh.instabox.sh" : ""),
        sshUser: cleanUser,
        sshPort: Number(formSshPort) || (addVmTab === "instabox" ? 2222 : 22),
        tokenExpiry: formTokenExpiry.trim(),
        webPort: formWebPort ? Number(formWebPort) : undefined,
        screenUrl: formScreenUrl.trim() || undefined,
        screenOpenTarget: formScreenOpenTarget,
        apiKey: finalApiKey || undefined,
        ip: cleanHost || (addVmTab === "instabox" ? "ssh.instabox.sh" : ""),
        ...tzInfo,
      }
      const scopeChanged = editingVm.scope !== formScope
      if (scopeChanged) {
        recordPendingMutation(editingVm.id, editPatch, 15000)
        const updated = vms.map((item) =>
          item.id === editingVm.id ? { ...item, ...editPatch } : item
        )
        pendingInitialSave = persistVmChanges(updated, true)
        if (api.migrateVm) {
          void api.migrateVm(editingVm.id, formScope).catch(() => {})
        }
        notify(language === "id" ? `${cleanName || editingVm.name} berhasil diperbarui!` : `${cleanName || editingVm.name} updated successfully!`, "success")
        setEditingVm(null)
      } else {
        void persistSingleVmPatch(editingVm, editPatch).then((ok) => {
          if (ok) {
            notify(language === "id" ? `${cleanName || editingVm.name} berhasil diperbarui!` : `${cleanName || editingVm.name} updated successfully!`, "success")
            setEditingVm(null)
          }
        })
      }
    } else {
      const finalName = cleanName || (addVmTab === "instabox" ? "InstaBox-MicroVM" : "Linux-VPS")
      const newVm: VirtualMachine = {
        id: targetId,
        name: finalName,
        provider: addVmTab,
        status: "sleeping",
        scope: formScope,
        serverId: targetServerId,
        serverName: formScope === "server" ? activeServerName : undefined,
        sshHost: cleanHost || (addVmTab === "instabox" ? "ssh.instabox.sh" : "127.0.0.1"),
        sshUser: cleanUser,
        sshPort: Number(formSshPort) || (addVmTab === "instabox" ? 2222 : 22),
        tokenExpiry: formTokenExpiry.trim(),
        webPort: formWebPort ? Number(formWebPort) : undefined,
        screenUrl: formScreenUrl.trim() || undefined,
        apiKey: finalApiKey || undefined,
        ip: cleanHost || (addVmTab === "instabox" ? "ssh.instabox.sh" : "127.0.0.1"),
        runtimeMinutes: 0,
        maxRuntimeMinutes: addVmTab === "instabox" ? 480 : undefined,
        idleTimeoutMinutes: addVmTab === "instabox" ? 30 : undefined,
        lastActive: language === "id" ? "Baru ditambahkan" : "Just added",
        ...tzInfo,
        telemetry: {
          cpuPct: null,
          ramUsedBytes: null,
          ramTotalBytes: null,
          diskUsedBytes: null,
          diskTotalBytes: null,
        },
      }
      pendingCreatedVmsRef.current.set(targetId, { expiresAt: Date.now() + 15000, vm: newVm })
      recordPendingMutation(targetId, newVm, 15000)
      const nextList = [...vms, newVm]
      pendingInitialSave = persistVmChanges(nextList, true)
      notify(language === "id" ? `${finalName} berhasil ditambahkan!` : `${finalName} added successfully!`, "success")
      setIsAddingVm(false)
    }

    // Trigger immediate InstaBox cloud sync if API Key is configured (tunggu save awal selesai agar ID sudah terdaftar)
    if (finalApiKey && addVmTab === "instabox") {
      notify(language === "id" ? "Menyinkronkan data dengan InstaBox Cloud…" : "Syncing data with InstaBox Cloud…", "info")
      void pendingInitialSave.then(() =>
        api.syncInstaBoxVm({ apiKey: finalApiKey, vmName: cleanName, machineId: editingVm?.machineId, vmId: targetId, scope: formScope, serverId: targetServerId })
      ).then(async (res: any) => {
        if (res && res.success) {
          const stateStr = String(res.state || "").toLowerCase()
          const isRunning = stateStr === "running" || stateStr === "active" || stateStr === "starting" || stateStr === "resuming"
          const syncPatch: Partial<VirtualMachine> = {
            machineId: res.machineId || editingVm?.machineId,
            status: isRunning ? "running" : "sleeping",
            runtimeMinutes: typeof res.runtimeMinutes === "number" ? res.runtimeMinutes : 0,
            maxRuntimeMinutes: res.maxRuntimeMinutes || 480,
            idleTimeoutMinutes: res.idleTimeoutMinutes || 30,
            screenUrl: formScreenUrl.trim() || res.screenUrl || undefined,
            sshHost: cleanHost || res.sshHost || "ssh.instabox.sh",
            sshUser: cleanUser || res.sshUser || res.machineId,
            sshPort: Number(formSshPort) || res.sshPort || 2222,
            telemetry: isRunning && res.telemetry ? res.telemetry : null,
          }
          recordPendingMutation(targetId, syncPatch, 15000)
          setVms((current) =>
            current.map((v) =>
              v.id === targetId ? { ...v, ...syncPatch } : v
            )
          )
          if (api.updateVm) {
            await api.updateVm(targetId, syncPatch, targetServerId).catch(() => {})
          }
          notify(language === "id" ? `Terhubung ke InstaBox: ${res.machineName || 'MicroVM'}! Metrik berhasil disinkronkan.` : `Connected to InstaBox: ${res.machineName || 'MicroVM'}! Metrics synced successfully.`, "success")
        } else if (res && res.error) {
          notify(language === "id" ? `Peringatan InstaBox: ${res.error}` : `InstaBox Warning: ${res.error}`, "warning")
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
    notify(language === "id" ? `Membuka web service ${targetUrl}…` : `Opening web service ${targetUrl}…`, "info")
  }

  const resolveVmScreenUrl = (vm: VirtualMachine): string => {
    let targetUrl = (vm.screenUrl || "").trim()
    const mid = vm.machineId || (vm.sshUser?.startsWith("m_") ? vm.sshUser : "")
    if (!targetUrl) {
      if (mid) {
        targetUrl = `https://dashboard.instabox.sh/machines/${mid}`
      } else {
        targetUrl = "https://dashboard.instabox.sh"
      }
    } else if (!targetUrl.startsWith("http://") && !targetUrl.startsWith("https://")) {
      targetUrl = `https://${targetUrl}`
    }
    return targetUrl
  }

  const executeOpenScreenTarget = (vm: VirtualMachine, targetMode: "window" | "browser", remember: boolean) => {
    const targetUrl = resolveVmScreenUrl(vm)
    if (remember) {
      void persistSingleVmPatch(vm, { screenOpenTarget: targetMode })
    }
    if (targetMode === "window") {
      const winTitle = `${vm.name} - Virtual Screen`
      if (api.openVmWindow) {
        void api.openVmWindow(vm.id, winTitle, targetUrl)
      } else {
        void api.openUrl(targetUrl, winTitle)
      }
      notify(
        language === "id"
          ? `Membuka Jendela Terisolasi untuk ${vm.name} (Sesi Login Mandiri)`
          : `Opening Isolated Window for ${vm.name} (Dedicated Login Session)`,
        "info"
      )
    } else {
      void api.openExternalBrowser(targetUrl)
      notify(
        language === "id"
          ? `Membuka Layar Virtual di Browser Bawaan: ${vm.name}`
          : `Opening Virtual Screen in Default Browser: ${vm.name}`,
        "info"
      )
    }
    setScreenPromptVm(null)
  }

  // Open Virtual Screen (Checks preference or opens Target Selector Modal)
  const handleOpenScreen = (vm: VirtualMachine) => {
    if (vm.screenOpenTarget === "window" || vm.screenOpenTarget === "browser") {
      executeOpenScreenTarget(vm, vm.screenOpenTarget, false)
      return
    }
    setRememberScreenTarget(false)
    setScreenPromptVm(vm)
  }

  // Copy SFTP URI
  const handleCopySftp = (vm: VirtualMachine) => {
    const user = vm.sshUser ? `${vm.sshUser}@` : ""
    const host = vm.sshHost || vm.ip || "localhost"
    const port = vm.sshPort || 22
    const sftpUri = `sftp://${user}${host}:${port}`
    copyToClipboard(sftpUri, language === "id" ? "Tautan SFTP" : "SFTP Link", vm.id)
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
      setSchedResetMode(normalizeResetCycleMode(vm.autoRestart.resetCycleMode || vm.autoRestart.resetMode))
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
  const handleSaveSchedule = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!schedulingVm) return
    const newSchedule: VmAutoRestartSchedule = {
      enabled: schedEnabled,
      mode: schedMode,
      intervalValue: Number(schedIntervalVal) || 6,
      intervalUnit: schedIntervalUnit,
      clockTime: schedClockTime,
      resetCycleMode: normalizeResetCycleMode(schedResetMode),
      lastExecuted: schedulingVm.autoRestart?.lastExecuted || "Never",
    }

    const ok = await persistSingleVmPatch(schedulingVm, { autoRestart: newSchedule })
    if (!ok) return

    notify(language === "id" ? `Jadwal Auto-Restart ${schedulingVm.name} disimpan!` : `Auto-Restart schedule for ${schedulingVm.name} saved!`, "success")
    setSchedulingVm(null)
  }

  // Immediate 8-hour reset cycle for InstaBox
  const handleImmediateResetCycle = async (vm: VirtualMachine) => {
    const prevStatus = vm.status
    const prevRuntime = vm.runtimeMinutes
    notify(language === "id" ? `Memulai siklus reset limit 8 jam untuk ${vm.name}…` : `Starting 8-hour limit reset cycle for ${vm.name}…`, "info")
    lastSmartResetRef.current.set(vm.id, Date.now())
    recordPendingMutation(vm.id, { status: "sleeping", runtimeMinutes: 0 }, 25000)
    setVms((prev) =>
      prev.map((item) =>
        item.id === vm.id ? { ...item, status: "sleeping", runtimeMinutes: 0 } : item
      )
    )
    try {
      const res = await api.smartResetInstaBox({
        apiKey: vm.apiKey,
        machineId: vm.machineId || (vm.sshUser?.startsWith("m_") ? vm.sshUser : undefined),
        vmId: vm.id,
        scope: vm.scope,
        serverId: vm.serverId,
      })
      if (!res || res.success === false || res.status === "error") {
        pendingMutationsRef.current.delete(vm.id)
        setVms((prev) =>
          prev.map((item) =>
            item.id === vm.id ? { ...item, status: prevStatus, runtimeMinutes: prevRuntime } : item
          )
        )
        notify(
          res?.message || res?.error ||
            (language === "id" ? `Gagal melakukan smart reset pada ${vm.name}.` : `Failed to smart reset ${vm.name}.`),
          "danger"
        )
        return
      }
    } catch (err: any) {
      pendingMutationsRef.current.delete(vm.id)
      setVms((prev) =>
        prev.map((item) =>
          item.id === vm.id ? { ...item, status: prevStatus, runtimeMinutes: prevRuntime } : item
        )
      )
      notify(
        language === "id" ? `Smart reset gagal: ${err?.message || String(err)}` : `Smart reset failed: ${err?.message || String(err)}`,
        "danger"
      )
      return
    }
    lastSmartResetRef.current.set(vm.id, Date.now())
    recordPendingMutation(vm.id, { status: "running", runtimeMinutes: 0 }, 15000)
    setVms((prev) =>
      prev.map((item) =>
        item.id === vm.id ? { ...item, status: "running", runtimeMinutes: 0 } : item
      )
    )
    notify(language === "id" ? `Siklus selesai! Limit 8 jam ${vm.name} berhasil di-reset ke 0.` : `Cycle complete! 8-hour limit for ${vm.name} reset to 0.`, "success")
  }
  // Active Auto-Restart Scheduler Worker Loop
  useEffect(() => {
    const checkSchedules = () => {
      const now = Date.now()
      const nowDate = new Date()
      const currentHours = String(nowDate.getHours()).padStart(2, "0")
      const currentMins = String(nowDate.getMinutes()).padStart(2, "0")
      const currentTimeStr = `${currentHours}:${currentMins}`

      const currentDay = nowDate.getDay()
      vmsRef.current.forEach((vm) => {
        // Isolasi: jadwal VM scope server dijalankan oleh daemon backend ZimaOS, bukan dari PC ini
        if (vm.scope === "server") return
        // 1. Evaluasi Jadwal Auto-On (Ketika VM sedang sleeping / stopped)
        if (vm.autoOn?.enabled && vm.status !== "running") {
          let shouldWake = false
          if (vm.autoOn.mode === "clock") {
            const targetClock = vm.autoOn.clockTime || "07:00"
            const activeDays = normalizeAutoOnDays(vm.autoOn.days)
            const lastTrig = vm.autoOn.lastTriggeredTimestamp || 0
            if (activeDays.includes(currentDay) && currentTimeStr === targetClock && now - lastTrig > 65000) {
              shouldWake = true
            }
          } else if (vm.autoOn.mode === "after_off") {
            const val = vm.autoOn.delayValue || 30
            const unit = vm.autoOn.delayUnit || "minutes"
            const multMs = unit === "seconds" ? 1000 : unit === "minutes" ? 60000 : 3600000
            const sleepStart = vm.sleepingSince || now
            if (now - sleepStart >= val * multMs) {
              shouldWake = true
            }
          }
          if (shouldWake) {
            if (vm.provider === "instabox") {
              api.wakeInstaBoxVm({
                apiKey: vm.apiKey,
                machineId: vm.machineId || (vm.sshUser?.startsWith("m_") ? vm.sshUser : undefined),
                vmId: vm.id,
                scope: vm.scope,
                serverId: vm.serverId,
              }).then((res: any) => {
                if (res && res.status === "error") {
                  setVms((prev) =>
                    prev.map((item) =>
                      item.id === vm.id ? { ...item, status: "sleeping", sleepingSince: Date.now() } : item
                    )
                  )
                  notify(
                    language === "id"
                      ? `[Auto-On] Gagal membangunkan ${vm.name}: ${res.message || "Error"}`
                      : `[Auto-On] Failed to wake ${vm.name}: ${res.message || "Error"}`,
                    "danger"
                  )
                }
              }).catch(() => {})
            }
            setVms((prev) =>
              prev.map((item) =>
                item.id === vm.id
                  ? {
                      ...item,
                      status: "running",
                      sleepingSince: undefined,
                      autoOn: {
                        ...item.autoOn!,
                        lastTriggered: nowDate.toLocaleTimeString(),
                        lastTriggeredTimestamp: now,
                      },
                    }
                  : item
              )
            )
            notify(
              language === "id"
                ? `[Auto-On] Membangunkan ${vm.name} sesuai jadwal otomatis!`
                : `[Auto-On] Waking up ${vm.name} per automatic schedule!`,
              "success"
            )
            return
          }
        }

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
          notify(language === "id" ? `[Auto-Restart] Menjalankan jadwal otomatis untuk ${vm.name} (${timestampStr})` : `[Auto-Restart] Executing automatic schedule for ${vm.name} (${timestampStr})`, "info")
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



  // Helper renderer for Inner Card Informasi VM
  const renderVmCardContent = (vm: VirtualMachine, inAccordion: boolean) => {
    const isDeleting = deletingVmIds.has(vm.id)
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
                  isDeleting || !isOnline
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
                  {vm.provider === "instabox" ? "InstaBox Cloud" : "Linux VM"} · {vm.sshHost || vm.ip || (vm.provider === "instabox" ? "ssh.instabox.sh" : "127.0.0.1")}:{vm.sshPort || (vm.provider === "instabox" ? 2222 : 22)}
                </span>
              </div>
            </div>

            {/* Status Pill & Edit/Delete Icons */}
            <div className="flex items-center gap-1.5 shrink-0">
              <span
                className={cx(
                  "inline-flex items-center gap-1 text-nano font-semibold rounded-full px-2 py-0.5 border",
                  isDeleting
                    ? "bg-surface-sunken text-ink-muted border-line"
                    : !isOnline
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
                    isDeleting || !isOnline
                      ? "neutral"
                      : vm.status === "running"
                        ? "success"
                        : vm.status === "sleeping"
                          ? "warning"
                          : "danger"
                  }
                  size="xs"
                />
                {isDeleting
                  ? (language === "id" ? "Menghapus..." : "Deleting...")
                  : !isOnline
                    ? "Offline"
                    : vm.status === "running"
                      ? t("vm_status_running", "Active")
                      : vm.status === "sleeping"
                        ? t("vm_status_sleep", "Sleeping")
                        : t("vm_status_cooldown", "Cooldown")}
              </span>

              {/* 1-Click Migration Button */}
              <button
                type="button"
                onClick={() => handleOpenEdit(vm)}
                className="p-1 rounded-md text-ink-subtle hover:text-ink hover:bg-surface-sunken transition cursor-pointer"
                title={t("edit_vm_btn", "Edit")}
              >
                <Pencil className="size-3.5" />
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
                    ? `${Math.floor(vm.runtimeMinutes / 60)}${language === "id" ? "j" : "h"} ${vm.runtimeMinutes % 60}m / 8${language === "id" ? "j" : "h"} runtime`
                    : `— / 8${language === "id" ? "j" : "h"} runtime`}
                </span>
              </Mono>
              <Mono className={cx("shrink-0 font-semibold", isRunning ? "text-ink" : "text-ink-subtle")}>
                {vm.runtimeMinutes != null ? `${Math.round(runtimePct)}%` : "0%"} {language === "id" ? "terpakai" : "used"}
              </Mono>
            </div>

            <div className="flex items-center justify-between gap-1 text-nano text-ink-faint border-t border-line/40 pt-1">
              <span className="truncate">
                {vm.keepAliveEnabled
                  ? t("vm_always_on_disabled", "Auto-sleep: Nonaktif")
                  : vm.autoOn?.enabled
                    ? vm.autoOn.mode === "clock"
                      ? `Auto-On: ${vm.autoOn.clockTime || "07:00"}`
                      : `Auto-On: +${vm.autoOn.delayValue || 30}${vm.autoOn.delayUnit === "seconds" ? "s" : vm.autoOn.delayUnit === "hours" ? "h" : "m"}`
                    : "Auto-sleep: 30m idle"}
              </span>
              <div className="flex items-center gap-1.5 shrink-0">
                {vm.autoRestart?.enabled && (
                  <span className="text-info font-medium">{t("vm_autorestart_active")}</span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* TIER 2.5: Telemetri Riil 3-Kolom (Live Data / Dash saat Idle) */}
        <div className="grid grid-cols-3 gap-1.5 p-1.5 rounded-tile bg-surface-sunken/60 border border-line/60 text-center text-nano">
          <div className="flex flex-col">
            <span className="text-[9px] uppercase font-bold text-ink-faint">CPU</span>
            <Mono className="text-[11px] font-semibold text-ink">
              {vm.status === "running" && vm.telemetry?.cpuPct != null ? `${vm.telemetry.cpuPct}%` : "—"}
            </Mono>
          </div>
          <div className="flex flex-col border-x border-line/40">
            <span className="text-[9px] uppercase font-bold text-ink-faint">RAM</span>
            <Mono className="text-[11px] font-semibold text-ink">
              {vm.status === "running" && vm.telemetry?.ramUsedBytes != null && vm.telemetry?.ramTotalBytes
                ? `${(vm.telemetry.ramUsedBytes / (1024 ** 3)).toFixed(1)} GB`
                : "—"}
            </Mono>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] uppercase font-bold text-ink-faint">DISK</span>
            <Mono className="text-[11px] font-semibold text-ink">
              {vm.status === "running" && vm.telemetry?.diskUsedBytes != null && vm.telemetry?.diskTotalBytes
                ? `${(vm.telemetry.diskUsedBytes / (1024 ** 3)).toFixed(1)} GB`
                : "—"}
            </Mono>
          </div>
        </div>

        {/* TIER 3: Rincian Koneksi SSH & Ports */}
        <div className="rounded-tile bg-surface-sunken/80 border border-line p-2.5 flex flex-col gap-1.5 text-nano">
          <div className="flex items-center justify-between text-ink-subtle">
            <span className="font-semibold text-ink">{language === "id" ? "Koneksi SSH" : "SSH Connection"}</span>
            {vm.tokenExpiry && vm.tokenExpiry !== "7d" && vm.tokenExpiry !== "6d" && !vm.apiKey && (
              <span className="flex items-center gap-1 text-[10px] text-amber-500 font-medium shrink-0">
                <Clock className="size-3 shrink-0" />
                <span>{language === "id" ? "kedaluwarsa dlm" : "expires in"} {vm.tokenExpiry}</span>
              </span>
            )}
          </div>

          <div className="flex items-center justify-between gap-1 text-ink-muted">
            <span className="text-[10px]">Host:</span>
            <Mono className="text-[10.5px] text-ink truncate select-all">
              {vm.sshHost || vm.ip || (vm.provider === "instabox" ? "ssh.instabox.sh" : "127.0.0.1")}:{vm.sshPort || (vm.provider === "instabox" ? 2222 : 22)}
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
            onClick={() => copyToClipboard(getSshCommand(vm), language === "id" ? "Perintah SSH" : "SSH Command", vm.id)}
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
                <span>{language === "id" ? "Perintah Disalin!" : "Command Copied!"}</span>
              </>
            ) : (
              <>
                <Terminal className="size-4" />
                <span>{t("vm_copy_ssh_cmd", "Salin Perintah SSH")}</span>
              </>
            )}
          </button>

          {/* Action Grid 3x2 Simetris: Baris 1: Daya | Layar Virtual, Baris 2: Always-On | SFTP, Baris 3: Auto-On | Auto-Restart */}
          <div className="grid grid-cols-2 gap-1.5 w-full mt-1">
            {/* Baris 1, Kolom 1: Daya (Tidurkan / Bangunkan) */}
            <Button
              size="sm"
              variant="subtle"
              icon={powerBusyVmId === vm.id ? LoaderCircle : Power}
              iconClassName={cx("size-3.5 shrink-0", vm.status === "running" ? "text-warning-ink" : "text-success-ink")}
              disabled={!isOnline || powerBusyVmId === vm.id}
              onClick={() => handleTogglePower(vm)}
              className={cx(
                "h-8 justify-center gap-1.5 text-[10px] font-semibold px-1.5 transition-colors min-w-0",
                vm.status === "running"
                  ? "text-warning-ink hover:border-warning-line/80"
                  : "text-success-ink hover:border-success-line/80"
              )}
            >
              <span className="truncate">
                {powerBusyVmId === vm.id
                  ? t("vm_processing", "Memproses...")
                  : vm.status === "running"
                    ? t("vm_power_sleep", "Tidurkan")
                    : t("vm_power_wake", "Bangunkan")}
              </span>
            </Button>

            {/* Baris 1, Kolom 2: Layar Virtual */}
            <Button
              size="sm"
              variant="subtle"
              icon={Monitor}
              iconClassName="size-3.5 shrink-0 text-info-ink"
              onClick={() => handleOpenScreen(vm)}
              className="h-8 justify-center gap-1.5 text-[10px] font-semibold px-1.5 text-ink min-w-0"
            >
              <span className="truncate">{t("vm_screen_btn")}</span>
            </Button>

            {/* Baris 2, Kolom 1: Always-On (Khusus InstaBox) */}
            {vm.provider === "instabox" ? (
              <Button
                size="sm"
                variant={vm.keepAliveEnabled ? "info" : "subtle"}
                icon={Zap}
                iconClassName={cx("size-3.5 shrink-0", vm.keepAliveEnabled ? "text-warning-ink" : "text-ink")}
                disabled={!isOnline}
                onClick={() => handleToggleKeepAlive(vm)}
                className={cx(
                  "h-8 justify-center gap-1.5 text-[10px] font-semibold px-1.5 transition-colors min-w-0",
                  vm.keepAliveEnabled
                    ? "border-warning-line bg-warning-soft text-warning-ink hover:border-warning-line/90"
                    : "text-ink"
                )}
              >
                <span className="truncate">{t("vm_always_on_btn")}</span>
              </Button>
            ) : (
              <div />
            )}

            {/* Baris 2, Kolom 2: SFTP */}
            <Button
              size="sm"
              variant="subtle"
              icon={Folder}
              iconClassName="size-3.5 shrink-0 text-ink"
              onClick={() => handleCopySftp(vm)}
              className="h-8 justify-center gap-1.5 text-[10px] font-semibold px-1.5 text-ink min-w-0"
            >
              <span className="truncate">{t("vm_sftp_btn")}</span>
            </Button>

            {/* Baris 3, Kolom 1: Auto-On (Jadwal Nyala Otomatis) */}
            <Button
              size="sm"
              variant={vm.autoOn?.enabled ? "info" : "subtle"}
              icon={Clock}
              iconClassName={cx("size-3.5 shrink-0", vm.autoOn?.enabled ? "text-info-ink" : "text-ink")}
              onClick={() => handleOpenAutoOn(vm)}
              className={cx(
                "h-8 justify-center gap-1.5 text-[10px] font-semibold px-1.5 transition-colors min-w-0",
                vm.autoOn?.enabled
                  ? "border-info-line/70 bg-info-soft/50 text-info-ink"
                  : "text-ink"
              )}
            >
              <span className="truncate">{t("vm_autoon_btn", "Auto-On")}</span>
            </Button>

            {/* Baris 3, Kolom 2: Auto-Restart */}
            <Button
              size="sm"
              variant={vm.autoRestart?.enabled ? "info" : "subtle"}
              icon={RotateCcw}
              iconClassName={cx("size-3.5 shrink-0", vm.autoRestart?.enabled ? "text-info-ink" : "text-ink")}
              onClick={() => handleOpenSchedule(vm)}
              className={cx(
                "h-8 justify-center gap-1.5 text-[10px] font-semibold px-1.5 transition-colors min-w-0",
                vm.autoRestart?.enabled
                  ? "border-info-line/70 bg-info-soft/50 text-info-ink"
                  : "text-ink"
              )}
            >
              <span className="truncate">{t("vm_autorestart_btn")}</span>
            </Button>
          </div>

          {/* Web App Button (if webPort/webUrl configured) */}
          {(vm.webPort || vm.webUrl) && (
            <Button
              size="sm"
              variant="subtle"
              icon={Globe}
              iconClassName="size-4"
              disabled={!isOnline}
              onClick={() => handleOpenWeb(vm)}
              className="w-full h-8 justify-center text-[11px] font-semibold text-ink px-2.5 mt-0.5"
            >
              Web ({vm.webPort || "App"})
            </Button>
          )}
        </div>
      </div>
    )
  }

  const renderAccordionCard = (vm: VirtualMachine) => {
    const isExpanded = expandedId === vm.id
    const isDeleting = deletingVmIds.has(vm.id)
    return (
      <Card
        key={vm.id}
        className={cx(
          "flex flex-col transition-all overflow-hidden p-0 border",
          isExpanded ? "border-brand/40 shadow-sm" : "border-line",
          isDeleting && "opacity-40 pointer-events-none select-none transition-opacity duration-300"
        )}
      >
        {/* Accordion Header Row */}
        <div
          className="flex items-center justify-between p-2.5 cursor-pointer hover:bg-surface-sunken/40 select-none"
          onClick={() => setExpandedId(isExpanded ? null : vm.id)}
        >
          <div className="flex items-center gap-2 min-w-0">
            <IconBadge
              icon={vm.scope === "server" ? Server : Laptop}
              tone={
                isDeleting || !isOnline
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
                {vm.sshHost || vm.ip || (vm.provider === "instabox" ? "ssh.instabox.sh" : "127.0.0.1")}:{vm.sshPort || (vm.provider === "instabox" ? 2222 : 22)}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              title={language === "id" ? "Edit VM" : "Edit VM"}
              onClick={(e) => {
                e.stopPropagation()
                handleOpenEdit(vm)
              }}
              className="p-1 rounded text-ink-subtle hover:text-ink hover:bg-surface-sunken transition cursor-pointer"
            >
              <Pencil className="size-3.5" />
            </button>

            <span
              className={cx(
                "inline-flex items-center gap-1 text-[10px] font-semibold rounded-full px-2 py-0.5 border",
                isDeleting
                  ? "bg-surface-sunken text-ink-muted border-line animate-pulse"
                  : !isOnline
                    ? "bg-surface-sunken text-ink-muted border-line"
                    : vm.status === "running"
                      ? "bg-success-soft text-success-ink border-success-line/60"
                      : "bg-warning-soft text-warning-ink border-warning-line/60"
              )}
            >
              <StatusDot
                tone={
                  isDeleting || !isOnline
                    ? "neutral"
                    : vm.status === "running"
                      ? "success"
                      : "warning"
                }
                size="xs"
              />
              {isDeleting
                ? (language === "id" ? "Menghapus..." : "Deleting...")
                : !isOnline
                  ? "Offline"
                  : vm.status === "running"
                    ? (language === "id" ? "Aktif" : "Active")
                    : (language === "id" ? "Tidur" : "Sleep")}
            </span>

            <ChevronDown
              className={cx(
                "size-4 text-ink-subtle transition-transform duration-250 ease-out",
                isExpanded && "rotate-180"
              )}
            />
          </div>
        </div>

        {/* Smooth Animated Accordion Body using CSS Grid */}
        <div
          className={cx(
            "grid transition-all duration-250 ease-out",
            isExpanded ? "grid-rows-[1fr] opacity-100 border-t border-line/60" : "grid-rows-[0fr] opacity-0"
          )}
        >
          <div className="overflow-hidden">
            <div className="px-3 pb-3 pt-1 flex flex-col gap-2 bg-surface-sunken/20">
              {renderVmCardContent(vm, true)}
            </div>
          </div>
        </div>
      </Card>
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
        <Card
          className={cx(
            "flex flex-col gap-2.5 p-3 relative overflow-hidden transition-all duration-300",
            deletingVmIds.has(visibleVms[0].id) && "opacity-40 pointer-events-none select-none"
          )}
        >
          {renderVmCardContent(visibleVms[0], false)}
        </Card>
      )}

      {/* ========================================================= */}
      {/* 4. CASE 2: CONDITIONAL SMART GROUPING & MULTIPLE VMS      */}
      {/* ========================================================= */}
      {isMultiple && (
        <div className="flex flex-col gap-2">
          {showGroupHeaders ? (
            <>
              {/* GROUP 1: SERVER VMS (Only shown when server has VMs) */}
              {serverVms.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between px-1 pt-0.5">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Server className="size-3 text-brand shrink-0" />
                      <span className="text-[10px] font-bold tracking-wider text-ink-muted uppercase truncate">
                        {t("vm_group_server")}: {activeServerName}
                      </span>
                      <span className="text-[9.5px] font-bold text-brand">
                        ({serverVms.length})
                      </span>
                    </div>

                  </div>
                  {serverVms.map(renderAccordionCard)}
                </div>
              )}

              {/* GROUP 2: LOCAL VMS (Only shown when local has VMs) */}
              {localVms.length > 0 && (
                <div className="flex flex-col gap-1.5 mt-1 pt-1.5 border-t border-line/60">
                  <div className="flex items-center justify-between px-1 pt-0.5">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Laptop className="size-3 text-ink-muted shrink-0" />
                      <span className="text-[10px] font-bold tracking-wider text-ink-muted uppercase truncate">
                        {t("vm_group_local")}
                      </span>
                      <span className="text-[9.5px] font-bold text-ink-subtle">
                        ({localVms.length})
                      </span>
                    </div>

                  </div>
                  {localVms.map(renderAccordionCard)}
                </div>
              )}
            </>
          ) : (
            /* CLEAN UNIFIED LIST: No headers when server has 0 VMs or only 1 group exists! */
            visibleVms.map(renderAccordionCard)
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* 7. MODAL KONFIRMASI HAPUS VM                              */}
      {/* ========================================================= */}
      {(isAddingVm || editingVm) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-2.5 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150 overflow-hidden">
          <Card className="w-full max-w-[305px] p-0 flex flex-col shadow-xl border border-line bg-surface max-h-[88vh] overflow-hidden">
            {/* Pinned Modal Header */}
            <div className="flex items-center justify-between border-b border-line px-3 py-2 shrink-0 bg-surface z-10">
              <span className="text-caption font-bold text-ink">
                {editingVm
                  ? editingVm.provider === "instabox"
                    ? t("vm_edit_instabox_title")
                    : t("vm_edit_manual_title")
                  : t("add_vm_btn")}
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

            {/* Scrollable Modal Content - SINGLE SCROLLBAR */}
            <div className="p-2.5 overflow-y-auto flex flex-col gap-1.5 flex-1 min-h-0">

            {/* Modal 2-Tab Selector - Filtered: Only shown when adding new VM, hidden during edit */}
            {!editingVm && (
              <div className="grid grid-cols-2 gap-1 p-0.5 rounded-lg bg-surface-sunken border border-line text-nano">
                <button
                  type="button"
                  onClick={() => setAddVmTab("instabox")}
                  className={cx(
                    "py-0.5 rounded font-semibold transition cursor-pointer text-center text-[10px]",
                    addVmTab === "instabox"
                      ? "bg-brand text-brand-ink font-semibold shadow-xs"
                      : "text-ink-subtle hover:text-ink"
                  )}
                >
                  InstaBox Cloud
                </button>
                <button
                  type="button"
                  onClick={() => setAddVmTab("manual")}
                  className={cx(
                    "py-0.5 rounded font-semibold transition cursor-pointer text-center text-[10px]",
                    addVmTab === "manual"
                      ? "bg-brand text-brand-ink font-semibold shadow-xs"
                      : "text-ink-subtle hover:text-ink"
                  )}
                >
                  Manual SSH
                </button>
              </div>
            )}

            {/* Target Location Selector (Fitur 1 v4.5.0 Beta): Server vs Lokal */}
            <div className="flex flex-col gap-0.5">
              <label className="text-[9.5px] font-semibold text-ink-muted">
                {t("vm_scope_label", "Target Lokasi:")}
              </label>
              <div className="grid grid-cols-2 gap-1 p-0.5 rounded-lg bg-surface-sunken border border-line text-nano">
                <button
                  type="button"
                  onClick={() => setFormScope("server")}
                  className={cx(
                    "py-0.5 px-1.5 rounded font-semibold transition cursor-pointer flex items-center justify-center gap-1 truncate text-[10px]",
                    formScope === "server"
                      ? "bg-brand text-brand-ink font-semibold shadow-xs"
                      : "text-ink-subtle hover:text-ink"
                  )}
                >
                  <Server className="size-2.5 shrink-0" />
                  <span className="truncate">{activeServerName || t("vm_scope_server", "Server")}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setFormScope("local")}
                  className={cx(
                    "py-0.5 px-1.5 rounded font-semibold transition cursor-pointer flex items-center justify-center gap-1 truncate text-[10px]",
                    formScope === "local"
                      ? "bg-brand text-brand-ink font-semibold shadow-xs"
                      : "text-ink-subtle hover:text-ink"
                  )}
                >
                  <Laptop className="size-2.5 shrink-0" />
                  <span className="truncate">{t("vm_scope_local", "Lokal")}</span>
                </button>
              </div>
            </div>

            {/* Modal Form */}
            <form onSubmit={handleSaveForm} className="flex flex-col gap-1.5 text-nano">
              {addVmTab === "instabox" ? (
                <>
                  <div>
                    <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                      InstaBox API Key (ibk_...)
                    </label>
                    <input
                      type="password"
                      placeholder="e.g. ibk_examplekey..."
                      value={formApiKey}
                      onChange={(e) => setFormApiKey(e.target.value)}
                      className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand font-mono text-[10px] h-6.5"
                    />
                    <span className="text-[9px] text-ink-faint block truncate">
                      {language === "id"
                        ? "Dapatkan dari Settings di web InstaBox."
                        : "From InstaBox web Settings."}
                    </span>
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                      {language === "id" ? "Nama Virtual Machine (Opsional)" : "Virtual Machine Name (Optional)"}
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Linux-Dev-Server"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand text-[10.5px] h-6.5"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                      {language === "id" ? "Token SSH Sementara (Opsional)" : "Temporary SSH Token (Optional)"}
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. ibssh_exampletoken..."
                      value={formSshUser}
                      onChange={(e) => setFormSshUser(e.target.value)}
                      className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand font-mono text-[10px] h-6.5"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                      {language === "id" ? "URL Layar Virtual / Web Console (Opsional)" : "Virtual Screen / Web Console URL (Optional)"}
                    </label>
                    <input
                      type="url"
                      placeholder="e.g. https://instabox.sh/app/machines/..."
                      value={formScreenUrl}
                      onChange={(e) => setFormScreenUrl(e.target.value)}
                      className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand text-[10.5px] h-6.5"
                    />
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                      {language === "id" ? "Nama Virtual Machine" : "Virtual Machine Name"}
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Ubuntu-VPS"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand text-[10.5px] h-6.5"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                      Host Gateway / IP
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. 192.168.1.100 atau vps.example.com"
                      value={formSshHost}
                      onChange={(e) => setFormSshHost(e.target.value)}
                      className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand text-[10.5px] h-6.5"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-1.5">
                    <div>
                      <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                        {language === "id" ? "Port SSH" : "SSH Port"}
                      </label>
                      <input
                        type="number"
                        required
                        placeholder="22"
                        value={formSshPort}
                        onChange={(e) => setFormSshPort(e.target.value)}
                        className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand text-[10.5px] h-6.5"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                        {language === "id" ? "Masa Berlaku" : "Token Expiry"}
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. 30d atau Permanent"
                        value={formTokenExpiry}
                        onChange={(e) => setFormTokenExpiry(e.target.value)}
                        className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand text-[10.5px] h-6.5"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                      {language === "id" ? "User SSH" : "SSH User"}
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. root atau ubuntu"
                      value={formSshUser}
                      onChange={(e) => setFormSshUser(e.target.value)}
                      className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand font-mono text-[10px] h-6.5"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                      {language === "id" ? "Port Web Layanan (Opsional)" : "Web Service Port (Optional)"}
                    </label>
                    <input
                      type="number"
                      placeholder="e.g. 8080"
                      value={formWebPort}
                      onChange={(e) => setFormWebPort(e.target.value)}
                      className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand text-[10.5px] h-6.5"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                      {language === "id" ? "URL Layar Virtual (Opsional)" : "Virtual Screen URL (Optional)"}
                    </label>
                    <input
                      type="url"
                      placeholder="e.g. http://192.168.1.100:6080/vnc.html"
                      value={formScreenUrl}
                      onChange={(e) => setFormScreenUrl(e.target.value)}
                      className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand text-[10.5px] h-6.5"
                    />
                  </div>
                </>
              )}

              <div>
                <label className="block text-[10px] font-semibold text-ink-subtle mb-0.5">
                  {t("vm_screen_target_label", "Mode Buka Layar Virtual")}
                </label>
                <select
                  value={formScreenOpenTarget}
                  onChange={(e) => setFormScreenOpenTarget(e.target.value as any)}
                  className="w-full rounded border border-line bg-surface-sunken px-2 py-0.5 text-caption text-ink focus:outline-none focus:border-brand text-[10px] h-6.5"
                >
                  <option value="ask">{t("vm_screen_target_ask", "Tanyakan Setiap Membuka")}</option>
                  <option value="window">{t("vm_screen_target_window", "Jendela MyServer")}</option>
                  <option value="browser">{t("vm_screen_target_browser", "Browser Bawaan")}</option>
                </select>
              </div>

              <div className="flex items-center gap-1.5 pt-1 mt-0.5 border-t border-line">
                <Button
                  size="sm"
                  variant="subtle"
                  type="button"
                  onClick={() => {
                    setIsAddingVm(false)
                    setEditingVm(null)
                  }}
                  className="flex-1 justify-center h-7 text-[10.5px]"
                >
                  {t("cancel_btn", "Batal")}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  type="submit"
                  className="flex-1 justify-center !bg-brand !from-brand !to-brand text-brand-ink shadow-sm hover:opacity-90 h-7 text-[10.5px]"
                >
                  {editingVm ? t("vm_save_changes_btn") : t("save_btn")}
                </Button>
              </div>

              {/* Tombol Hapus VM di dalam Menu Edit (v4.5.0 Beta) */}
              {editingVm && (
                <div className="pt-1 border-t border-line">
                  <button
                    type="button"
                    onClick={() => {
                      const target = editingVm
                      setIsAddingVm(false)
                      setEditingVm(null)
                      setVmToDelete(target)
                    }}
                    className="w-full h-7 rounded-md bg-danger-soft/40 hover:bg-danger-soft text-danger-ink border border-danger-line/60 text-[10.5px] font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer"
                  >
                    <Trash2 className="size-3.5" />
                    <span>{language === "id" ? "Hapus Virtual Machine" : "Delete Virtual Machine"}</span>
                  </button>
                </div>
              )}
            </form>
            </div>
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
                  {t("vm_sched_modal_title")}
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
                  className="rounded border-line text-brand accent-[#65a30d] focus:ring-0"
                />
                <span className="font-semibold text-ink text-micro">
                  {t("vm_sched_enable")}
                </span>
              </label>

              {/* Mode Pilihan: Interval vs {t("vm_sched_clock")} */}
              <div className="flex flex-col gap-1">
                <span className="text-ink-subtle font-semibold">{t("vm_sched_mode")}:</span>
                <div className="grid grid-cols-2 gap-1 text-nano">
                  <button
                    type="button"
                    onClick={() => setSchedMode("interval")}
                    className={cx(
                      "py-1 px-1.5 rounded border text-center transition cursor-pointer truncate",
                      schedMode === "interval"
                        ? "bg-brand text-brand-ink border-brand font-semibold shadow-xs"
                        : "bg-surface-sunken border-line text-ink-subtle hover:text-ink"
                    )}
                  >
                    {t("vm_sched_interval")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setSchedMode("clock")}
                    className={cx(
                      "py-1 px-1.5 rounded border text-center transition cursor-pointer truncate",
                      schedMode === "clock"
                        ? "bg-brand text-brand-ink border-brand font-semibold shadow-xs"
                        : "bg-surface-sunken border-line text-ink-subtle hover:text-ink"
                    )}
                  >
                    {t("vm_sched_clock")}
                  </button>
                </div>
              </div>

              {schedMode === "interval" ? (
                <div className="grid grid-cols-2 gap-1.5">
                  <div>
                    <label className="block text-ink-subtle font-semibold mb-0.5">
                      {t("vm_sched_interval_val")}:
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
                      {language === "id" ? "Satuan:" : "Unit:"}
                    </label>
                    <select
                      value={schedIntervalUnit}
                      onChange={(e) => setSchedIntervalUnit(e.target.value as any)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                    >
                      <option value="hours">{t("vm_sched_hours")}</option>
                      <option value="minutes">{t("vm_sched_minutes")}</option>
                      <option value="seconds">{language === "id" ? "Detik" : "Seconds"}</option>
                    </select>
                  </div>
                </div>
              ) : (
                <div>
                  <label className="block text-ink-subtle font-semibold mb-0.5">
                    {language === "id" ? "Waktu Restart (HH:MM):" : "Restart Time (HH:MM):"}
                  </label>
                  <input
                    type="time"
                    value={schedClockTime}
                    onChange={(e) => setSchedClockTime(e.target.value)}
                    className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand font-mono"
                  />
                  <span className="text-[10px] text-ink-faint block mt-0.5">
                    {language === "id" ? "Dijalankan otomatis setiap hari pada jam ini." : "Runs automatically daily at this time."}
                  </span>
                </div>
              )}

              {/* Khusus InstaBox: Reset Limit 8 Jam Mode */}
              {schedulingVm.provider === "instabox" && (
                <div className="rounded-tile bg-surface-sunken/80 border border-line p-2 flex flex-col gap-1.5 mt-0.5">
                  <span className="font-semibold text-ink text-[10.5px]">
                    {t("vm_sched_reset_mode")}:
                  </span>
                  <label className="flex items-start gap-1.5 cursor-pointer text-[10.5px] text-ink">
                    <input
                      type="radio"
                      name="resetMode"
                      value="pause_resume"
                      checked={schedResetMode === "pause_resume"}
                      onChange={() => setSchedResetMode("pause_resume")}
                      className="mt-0.5 text-brand accent-[#65a30d] focus:ring-0"
                    />
                    <span>
                      <strong>{t("vm_sched_smart_reset")}</strong> — {language === "id" ? "Menidurkan mesin 2 detik lalu bangun lagi agar timer 8 jam reset ke 0 tanpa cooldown." : "Puts machine to sleep for 2s then wakes it to reset 8h timer without cooldown."}
                    </span>
                  </label>
                  <label className="flex items-start gap-1.5 cursor-pointer text-[10.5px] text-ink-subtle">
                    <input
                      type="radio"
                      name="resetMode"
                      value="cold_restart"
                      checked={schedResetMode === "cold_restart"}
                      onChange={() => setSchedResetMode("cold_restart")}
                      className="mt-0.5 text-brand accent-[#65a30d] focus:ring-0"
                    />
                    <span>{language === "id" ? "Reboot Penuh Sistem (Stop lalu Start)" : "Full System Reboot (Stop then Start)"}</span>
                  </label>

                  <Button
                    size="sm"
                    variant="subtle"
                    type="button"
                    onClick={() => handleImmediateResetCycle(schedulingVm)}
                    className="mt-1 justify-center text-nano text-info-ink"
                  >
                    {language === "id" ? "Reset Limit 8 Jam Sekarang" : "Reset 8h Limit Now"}
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
                  className="flex-1 justify-center !bg-brand !from-brand !to-brand text-brand-ink shadow-sm hover:opacity-90"
                >
                  {t("vm_sched_save")}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ========================================================= */}
      {/* 6.5 MODAL JADWAL NYALA OTOMATIS (AUTO-ON)                 */}
      {/* ========================================================= */}
      {autoOnVm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <Card className="w-full max-w-[305px] p-3 flex flex-col gap-2.5 shadow-xl border border-line bg-surface max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-line pb-2">
              <div className="flex flex-col min-w-0">
                <span className="text-caption font-bold text-ink">
                  {t("vm_autoon_modal_title", "Jadwal Nyala Otomatis (Auto-On)")}
                </span>
                <span className="text-nano text-ink-subtle truncate">
                  {autoOnVm.name}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setAutoOnVm(null)}
                className="p-1 rounded-md text-ink-subtle hover:text-ink transition cursor-pointer"
              >
                <X className="size-4" />
              </button>
            </div>

            <form onSubmit={handleSaveAutoOn} className="flex flex-col gap-2 text-nano">
              {/* Toggle Aktifkan Auto-On */}
              <label className="flex items-center gap-2 cursor-pointer select-none p-1.5 rounded bg-surface-sunken/60 border border-line/60">
                <input
                  type="checkbox"
                  checked={autoOnEnabled}
                  onChange={(e) => setAutoOnEnabled(e.target.checked)}
                  className="rounded border-line text-brand accent-[#65a30d] focus:ring-0"
                />
                <span className="font-semibold text-ink text-micro">
                  {t("vm_autoon_enable", "Aktifkan Jadwal Auto-On")}
                </span>
              </label>

              {/* Pilihan Mode: Jam Tertentu (HH:MM) vs Jeda Setelah Mati */}
              <div className="flex flex-col gap-1">
                <span className="text-ink-subtle font-semibold">{t("vm_sched_mode", "Mode Penjadwalan")}:</span>
                <div className="grid grid-cols-2 gap-1 text-nano">
                  <button
                    type="button"
                    onClick={() => setAutoOnMode("clock")}
                    className={cx(
                      "py-1 px-1.5 rounded border text-center transition cursor-pointer truncate",
                      autoOnMode === "clock"
                        ? "bg-brand text-brand-ink border-brand font-semibold shadow-xs"
                        : "bg-surface-sunken border-line text-ink-subtle hover:text-ink"
                    )}
                  >
                    {t("vm_autoon_mode_clock", "Jam Tertentu")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setAutoOnMode("after_off")}
                    className={cx(
                      "py-1 px-1.5 rounded border text-center transition cursor-pointer truncate",
                      autoOnMode === "after_off"
                        ? "bg-brand text-brand-ink border-brand font-semibold shadow-xs"
                        : "bg-surface-sunken border-line text-ink-subtle hover:text-ink"
                    )}
                  >
                    {t("vm_autoon_mode_delay", "Jeda Setelah Mati")}
                  </button>
                </div>
              </div>

              {autoOnMode === "clock" ? (
                <div className="flex flex-col gap-2">
                  <div>
                    <label className="block text-ink-subtle font-semibold mb-0.5">
                      {t("vm_autoon_clock_label", "Jam Nyala Otomatis (HH:MM):")}
                    </label>
                    <input
                      type="time"
                      value={autoOnClockTime}
                      onChange={(e) => setAutoOnClockTime(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-ink-subtle font-semibold mb-1">
                      {t("vm_autoon_days_label", "Hari Aktif:")}
                    </label>
                    <div className="grid grid-cols-7 gap-1">
                      {[
                        { idx: 1, id: "Sen", en: "Mon" },
                        { idx: 2, id: "Sel", en: "Tue" },
                        { idx: 3, id: "Rab", en: "Wed" },
                        { idx: 4, id: "Kam", en: "Thu" },
                        { idx: 5, id: "Jum", en: "Fri" },
                        { idx: 6, id: "Sab", en: "Sat" },
                        { idx: 0, id: "Min", en: "Sun" },
                      ].map((d) => {
                        const active = autoOnDays.includes(d.idx)
                        return (
                          <button
                            key={d.idx}
                            type="button"
                            onClick={() => handleToggleAutoOnDay(d.idx)}
                            className={cx(
                              "py-1 rounded border text-[9.5px] font-semibold transition cursor-pointer text-center",
                              active
                                ? "bg-brand text-brand-ink border-brand"
                                : "bg-surface-sunken text-ink-subtle border-line"
                            )}
                          >
                            {language === "id" ? d.id : d.en}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  <span className="text-ink-subtle font-semibold">
                    {t("vm_autoon_delay_label", "Nyalakan Setelah Mati Selama:")}
                  </span>
                  <div className="grid grid-cols-2 gap-1.5">
                    <input
                      type="number"
                      min={1}
                      value={autoOnDelayVal}
                      onChange={(e) => setAutoOnDelayVal(e.target.value)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand font-mono"
                    />
                    <select
                      value={autoOnDelayUnit}
                      onChange={(e) => setAutoOnDelayUnit(e.target.value as any)}
                      className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                    >
                      <option value="seconds">{language === "id" ? "Detik" : "Seconds"}</option>
                      <option value="minutes">{t("vm_sched_minutes", "Menit")}</option>
                      <option value="hours">{t("vm_sched_hours", "Jam")}</option>
                    </select>
                  </div>
                  <div className="rounded-md bg-surface-sunken/80 border border-line p-2 text-[10px] text-ink-subtle leading-relaxed">
                    {t("vm_autoon_conflict_note")}
                  </div>
                </div>
              )}

              <div className="flex items-center gap-1.5 pt-1 mt-1 border-t border-line">
                <Button
                  size="sm"
                  variant="subtle"
                  type="button"
                  onClick={() => setAutoOnVm(null)}
                  className="flex-1 justify-center"
                >
                  {t("cancel_btn", "Batal")}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  type="submit"
                  className="flex-1 justify-center !bg-brand !from-brand !to-brand text-brand-ink shadow-sm hover:opacity-90"
                >
                  {t("vm_sched_save", "Simpan Jadwal")}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ========================================================= */}
      {/* 6.8 MODAL PILIHAN TARGET BUKA VIRTUAL SCREEN (ISOLASI VM) */}
      {/* ========================================================= */}
      {screenPromptVm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <Card className="w-full max-w-[305px] p-3 flex flex-col gap-2.5 shadow-xl border border-line bg-surface">
            <div className="flex items-center justify-between border-b border-line pb-2">
              <div className="flex flex-col min-w-0">
                <span className="text-caption font-bold text-ink">
                  {t("vm_screen_modal_title", "Buka Layar Virtual")}
                </span>
                <span className="text-nano text-ink-subtle truncate">
                  {screenPromptVm.name}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setScreenPromptVm(null)}
                className="p-1 rounded-md text-ink-subtle hover:text-ink transition cursor-pointer"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="flex flex-col gap-2">
              {/* Opsi 1: Jendela Baru MyServer (Terisolasi Per-VM) */}
              <button
                type="button"
                onClick={() => executeOpenScreenTarget(screenPromptVm, "window", rememberScreenTarget)}
                className="w-full text-left p-2.5 rounded-tile border border-info-line/70 bg-info-soft/30 hover:bg-info-soft/50 transition cursor-pointer flex flex-col gap-1"
              >
                <div className="flex items-center justify-between gap-1.5">
                  <span className="text-micro font-bold text-ink flex items-center gap-1.5">
                    <Monitor className="size-3.5 text-info-ink shrink-0" />
                    <span>{t("vm_screen_target_window", "Jendela MyServer (Sesi Terisolasi)")}</span>
                  </span>
                </div>
                <span className="inline-flex w-fit items-center rounded-full bg-info-soft px-1.5 py-0.5 text-[9px] font-bold text-info-ink border border-info-line/50">
                  {t("vm_screen_isolated_badge", "Isolasi Multi-Akun")}
                </span>
                <span className="text-[10px] text-ink-subtle leading-snug">
                  {t("vm_screen_isolated_desc")}
                </span>
              </button>

              {/* Opsi 2: Browser Bawaan */}
              <button
                type="button"
                onClick={() => executeOpenScreenTarget(screenPromptVm, "browser", rememberScreenTarget)}
                className="w-full text-left p-2.5 rounded-tile border border-line bg-surface-sunken/70 hover:bg-surface-sunken transition cursor-pointer flex flex-col gap-1"
              >
                <span className="text-micro font-bold text-ink flex items-center gap-1.5">
                  <ExternalLink className="size-3.5 text-ink-subtle shrink-0" />
                  <span>{t("vm_screen_target_browser", "Browser Bawaan")}</span>
                </span>
                <span className="text-[10px] text-ink-subtle leading-snug">
                  {t("vm_screen_browser_desc")}
                </span>
              </button>

              <label className="flex items-center gap-2 cursor-pointer select-none pt-0.5 text-nano text-ink-subtle">
                <input
                  type="checkbox"
                  checked={rememberScreenTarget}
                  onChange={(e) => setRememberScreenTarget(e.target.checked)}
                  className="rounded border-line text-brand accent-[#65a30d] focus:ring-0"
                />
                <span>{t("vm_screen_remember_choice", "Ingat pilihan ini untuk VM ini")}</span>
              </label>
            </div>
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
              {language === "id" ? (
                <>
                  Apakah Anda yakin ingin menghapus{" "}
                  <strong className="text-ink">{vmToDelete.name}</strong>? Tindakan
                  ini akan menghapus konfigurasi koneksi VM dari MyServer.
                </>
              ) : (
                <>
                  Are you sure you want to delete{" "}
                  <strong className="text-ink">{vmToDelete.name}</strong>? This action
                  will remove the VM connection configuration from MyServer.
                </>
              )}
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
                disabled={isDeletingVm}
                className="flex-1 justify-center"
              >
                {isDeletingVm ? (language === "id" ? "Menghapus..." : "Deleting...") : t("delete_btn", "Hapus")}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </ViewBody>
  )
}

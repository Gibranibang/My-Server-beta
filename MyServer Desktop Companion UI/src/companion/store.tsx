import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import {
  DEFAULT_MAC,
  DEFAULT_SETTINGS,
  SERVER_IP,
  SERVER_URL,
  getCompanionApi,
} from "./api"
import { APP_VERSION } from "./version"
import type {
  ChecklistKey,
  NoticeHistoryItem,
  Drive,
  Metrics,
  TransitionState,
  PowerState,
  Settings,
  Tone,
  WebApp,
} from "./types"

export { DEFAULT_MAC, DEFAULT_SETTINGS, SERVER_IP, SERVER_URL }

export const errorText = (error: unknown, lang?: string) => {
  if (error instanceof Error && error.message) return error.message
  return lang === "en" ? "An error occurred. Please try again." : "Terjadi kesalahan. Coba lagi."
}

const EMPTY_METRICS: Metrics = {
  cpu: 0,
  ram: 0,
  hdd: 0,
  lanDown: 0,
  lanHistory: Array(12).fill(0),
  syncUp: 0,
  syncDown: 0,
  isLoading: true,
}

interface CompanionStore {
  metrics: Metrics
  power: PowerState
  isOnline: boolean
  isAdmin: boolean
  reboot: () => Promise<void>
  shutdown: () => Promise<void>
  wake: () => Promise<void>
  drives: Drive[]
  setAllMounted: (mounted: boolean) => Promise<void>
  settings: Settings
  setSetting: (key: keyof Settings, value: any) => Promise<void>
  resetSettings: () => Promise<void>
  syncRequests: number
  acceptSyncRequest: () => Promise<void>
  mac: string
  setMac: (mac: string) => void
  checklist: Record<ChecklistKey, boolean>
  toggleCheck: (key: ChecklistKey, value?: boolean) => void
  webApps: WebApp[]
  serverUrl: string
  refreshWebApps: () => Promise<void>
  refreshDrives: () => Promise<void>
  addWebApp: (name: string, url: string) => Promise<void>
  deleteWebApp: (appId: string) => Promise<void>
  openUrl: (url: string, title?: string) => Promise<void>
  openExternalBrowser: (url: string) => Promise<void>
  transitionState: TransitionState
  startTransition: (title: string, message?: string) => void
  endTransition: () => void
  runWithTransition: <T = any>(
    title: string,
    message: string,
    task: () => Promise<T>,
    options?: { resetMetrics?: boolean },
  ) => Promise<T>
  isInitialLoading: boolean
  homeLoading: boolean
  monitoringLoading: boolean
  setMonitoringLoading: (loading: boolean) => void
  wizardOpen: boolean
  wizardInitializing: boolean
  openedFromSettings: boolean
  openWizard: () => Promise<void>
  closeWizard: (completed?: boolean) => void
}

const StoreContext = createContext<CompanionStore | null>(null)

/** Single source of truth shared by every companion instance, so all frames stay synchronized. */
export function CompanionStoreProvider({ children }: { children: ReactNode }) {
  const api = getCompanionApi()
  const [metrics, setMetrics] = useState<Metrics>(EMPTY_METRICS)
  const [power, setPower] = useState<PowerState>("online")
  const [drives, setDrives] = useState<Drive[]>([])
  const [settings, setSettings] = useState<Settings>(() => {
    try {
      const urlParams = new URLSearchParams(window.location.search)
      const qTheme = urlParams.get("theme")
      if (qTheme === "dark" || qTheme === "light") {
        return { ...DEFAULT_SETTINGS, theme: qTheme }
      }
      const cached = localStorage.getItem("myserver_theme")
      if (cached === "dark" || cached === "light") {
        return { ...DEFAULT_SETTINGS, theme: cached }
      }
    } catch {}
    return DEFAULT_SETTINGS
  })
  const settingsRef = useRef<Settings>(settings)
  useEffect(() => {
    settingsRef.current = settings
  }, [settings])
  const transitionEpochRef = useRef(0)
  const [syncRequests, setSyncRequests] = useState(0)
  const [transitionState, setTransitionState] = useState<TransitionState>({ active: false, title: "" })
  const [isInitialLoading, setIsInitialLoading] = useState(true)
  const [homeLoading, setHomeLoading] = useState(true)
  const [monitoringLoading, setMonitoringLoading] = useState(true)
  // First-run wizard gating (D-05): telemetry stays suspended until loadSettings() resolves
  // and, when firstRunSetup is true, until the wizard completes (03-RESEARCH Pitfall 2).
  const [wizardInitializing, setWizardInitializing] = useState(true)
  const [firstRunLocked, setFirstRunLocked] = useState(false)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [openedFromSettings, setOpenedFromSettings] = useState(false)
  const telemetrySuspended = wizardInitializing || firstRunLocked

  useEffect(() => {
    let cancelled = false
    const finish = (first: boolean, loaded?: Settings | null) => {
      if (cancelled) return
      if (first && loaded) {
        setSettings((prev) => ({ ...prev, ...loaded }))
        try {
          if (loaded.theme) document.documentElement.setAttribute("data-theme", loaded.theme)
        } catch {}
        setFirstRunLocked(true)
        setWizardOpen(true)
        setOpenedFromSettings(false)
      }
      setWizardInitializing(false)
    }
    Promise.resolve()
      .then(() => api.loadSettings())
      .then((loaded) => finish(Boolean(loaded?.firstRunSetup), loaded))
      .catch(() => finish(false))
    return () => {
      cancelled = true
    }
  }, [api])

  const openWizard = useCallback(async () => {
    try {
      await api.setWizardMode(true, 460, 560)
    } catch {}
    setOpenedFromSettings(true)
    setWizardOpen(true)
  }, [api])

  const closeWizard = useCallback((completed?: boolean) => {
    setWizardOpen(false)
    setOpenedFromSettings(false)
    if (completed) {
      setSettings((prev) => ({ ...prev, firstRunSetup: false }))
      setFirstRunLocked(false)
    }
  }, [])

  const startTransition = useCallback((title: string, message?: string) => {
    setTransitionState({ active: true, title, message })
  }, [])

  const endTransition = useCallback(() => {
    setTransitionState({ active: false, title: "" })
  }, [])

  const runWithTransition = useCallback(
    async <T = any,>(
      title: string,
      message: string,
      task: () => Promise<T>,
      options?: { resetMetrics?: boolean },
    ): Promise<T> => {
      const myEpoch = ++transitionEpochRef.current
      startTransition(title, message)
      const shouldReset = options?.resetMetrics ?? false
      if (shouldReset) {
        setMonitoringLoading(true)
        setDrives([])
        setMetrics({
          ...EMPTY_METRICS,
          smbSyncing: true,
          isLoading: true,
        })
      }
      try {
        const result = await task()
        if (transitionEpochRef.current !== myEpoch) {
          return result
        }

        // Progressive auto-refresh for newly mounted SMB drives & fresh metrics
        void (async () => {
          let metricsSettled = false
          let smbSettled = false
          for (let i = 0; i < 24; i++) {
            if (transitionEpochRef.current !== myEpoch) return
            try {
              const [drivesRes, freshMetrics] = await Promise.allSettled([
                api.listDrives(),
                api.refreshMetrics ? api.refreshMetrics() : Promise.resolve(null),
              ])
              if (transitionEpochRef.current !== myEpoch) return
              if (drivesRes.status === "fulfilled" && Array.isArray(drivesRes.value)) {
                setDrives(drivesRes.value)
              }
              if (freshMetrics.status === "fulfilled" && freshMetrics.value) {
                const fresh = freshMetrics.value
                setMetrics(fresh)
                if (!fresh.isLoading || fresh.cpu > 0 || fresh.ram > 0) {
                  setMonitoringLoading(false)
                  metricsSettled = true
                }
                if (!fresh.smbSyncing) {
                  smbSettled = true
                }
              }
            } catch {
              // ignore
            }
            if (transitionEpochRef.current !== myEpoch) return
            if (metricsSettled && smbSettled && i >= 6) {
              break
            }
            await new Promise((r) => setTimeout(r, i < 8 ? 350 : 600))
          }
          if (transitionEpochRef.current !== myEpoch) return
          setMonitoringLoading(false)
          setMetrics((m) => (m.isLoading ? { ...m, isLoading: false } : m))
        })()

        await new Promise((r) => setTimeout(r, 200))
        return result
      } finally {
        if (transitionEpochRef.current === myEpoch) {
          endTransition()
        }
      }
    },
    [api, startTransition, endTransition],
  )
  const [mac, setMac] = useState(DEFAULT_MAC)
  const [checklist, setChecklist] = useState<Record<ChecklistKey, boolean>>({
    lan: false,
    bios: false,
    standby: false,
  })
  const [webApps, setWebApps] = useState<WebApp[]>([])
  const [serverUrl, setServerUrlState] = useState<string>("")

  const refreshWebApps = useCallback(async () => {
    try {
      const list = await api.listWebApps()
      setWebApps(list)
    } catch (err) {
      console.warn("[Store] refreshWebApps error:", err)
    }
  }, [api])

  const addWebApp = useCallback(
    async (name: string, url: string) => {
      const updated = await api.addWebApp(name, url)
      setWebApps(updated)
    },
    [api],
  )

  const deleteWebApp = useCallback(
    async (appId: string) => {
      const updated = await api.deleteWebApp(appId)
      setWebApps(updated)
    },
    [api],
  )

  const openUrl = useCallback(
    async (targetUrl: string, title?: string) => {
      await api.openUrl(targetUrl, title)
    },
    [api],
  )

  const openExternalBrowser = useCallback(
    async (targetUrl: string) => {
      await api.openExternalBrowser(targetUrl)
    },
    [api],
  )

  const refreshDrives = useCallback(async () => {
    try {
      const d = await api.listDrives()
      if (Array.isArray(d)) {
        setDrives(d)
      }
    } catch {
      // ignore
    }
  }, [api])

  useEffect(() => {
    if (telemetrySuspended) return
    const coldStartBegin = Date.now()
    const offMetrics = api.subscribeMetrics((newM) => {
      setMetrics(newM)
      if (newM && (!newM.isLoading || newM.cpu > 0 || newM.ram > 0)) {
        setMonitoringLoading(false)
      }
    })
    let isInitialBoot = true
    let prevPowerState: string | null = null
    const bootMountTs = Date.now()
    const offPower = api.subscribePower((p) => {
      setPower(p)
      if (p === "offline" || p === "online") {
        setMonitoringLoading(false)
      }
      // Jangan kirim spam notifikasi disconnect/reconnect selama 15 detik awal boot/startup aplikasi
      const pastStartupGrace = (Date.now() - bootMountTs) >= 15_000
      if (pastStartupGrace && !isInitialBoot && prevPowerState !== null && p !== prevPowerState) {
        if (p === "connecting" && prevPowerState === "offline") {
          window.dispatchEvent(new CustomEvent("myserver:notify", {
            detail: { text: "Menghubungkan ke server...", tone: "warning" }
          }))
        } else if (p === "online" && prevPowerState === "offline") {
          window.dispatchEvent(new CustomEvent("myserver:notify", {
            detail: { text: "Terhubung kembali ke server", tone: "success" }
          }))
        } else if (p === "offline" && prevPowerState === "online") {
          window.dispatchEvent(new CustomEvent("myserver:notify", {
            detail: { text: "Koneksi Terputus", tone: "danger" }
          }))
        }
      }
      if (p === "online" || p === "offline") {
        isInitialBoot = false
      }
      prevPowerState = p
    })

    // Monitoring notifikasi berkala: Syncthing milestones (25%, 50%, 90%, 100%) & perubahan rute
    // Persisten di localStorage agar tidak spam ulang 100% setiap kali aplikasi dibuka atau laptop baru menyala.
    const SERVER_DETAILS_POLL_MIN_MS = 12_000
    const SYNCTHING_STORE_KEY = "myserver_syncthing_milestones_v2"
    type StoredMilestoneState = { triggered: number[]; lastComp: number; lastNotifiedAt?: Record<string, number> }
    const loadStoredMilestones = (): Record<string, StoredMilestoneState> => {
      try {
        const raw = localStorage.getItem(SYNCTHING_STORE_KEY)
        if (raw) {
          const parsed = JSON.parse(raw)
          if (parsed && typeof parsed === "object") return parsed
        }
      } catch {}
      return {}
    }
    const saveStoredMilestones = (state: Record<string, StoredMilestoneState>) => {
      try {
        localStorage.setItem(SYNCTHING_STORE_KEY, JSON.stringify(state))
      } catch {}
    }
    const milestoneStore = loadStoredMilestones()
    const initializedTasksInSession = new Set<string>()
    let prevActiveRouteId: string | null = null
    let lastServerDetailsPollTs = Date.now()

    const checkMilestonesAndRoutes = async () => {
      try {
        if (api.getSyncthingTasks) {
          const tasks = await api.getSyncthingTasks()
          if (Array.isArray(tasks) && tasks.length > 0) {
            let storeDirty = false
            const nowTs = Date.now()
            for (const task of tasks) {
              const comp = Math.round(Number(task.completion || 0))
              const saved = milestoneStore[task.id] || { triggered: [], lastComp: comp, lastNotifiedAt: {} }
              const triggered = new Set<number>(Array.isArray(saved.triggered) ? saved.triggered : [])
              const lastNotifiedAt: Record<string, number> = { ...(saved.lastNotifiedAt || {}) }

              // Observasi pertama kali task di sesi ini (startup / cold boot): seed diam-diam tanpa notifikasi!
              if (!initializedTasksInSession.has(task.id)) {
                initializedTasksInSession.add(task.id)
                for (const m of [25, 50, 90, 100]) {
                  if (comp >= m) triggered.add(m)
                }
                milestoneStore[task.id] = { triggered: Array.from(triggered), lastComp: comp, lastNotifiedAt }
                storeDirty = true
                continue
              }

              if (task.paused) continue

              // Reset hanya jika task benar-benar kembali melakukan sinkronisasi baru (< 20% dan bukan nol transien saat reconnect)
              const isActivelySyncingNewBatch = comp > 0 && comp < 20 && saved.lastComp >= 20
              if (isActivelySyncingNewBatch) {
                triggered.clear()
                storeDirty = true
              }

              // Kumpulkan milestone baru yang terlewati, kirim maksimal 1 milestone tertinggi per polling
              let highestNewMilestone: number | null = null
              for (const m of [25, 50, 90, 100]) {
                if (comp >= m && !triggered.has(m)) {
                  triggered.add(m)
                  highestNewMilestone = m
                  storeDirty = true
                }
              }
              if (highestNewMilestone !== null) {
                const prevNotifTs = Number(lastNotifiedAt[String(highestNewMilestone)] || 0)
                if ((nowTs - prevNotifTs) >= 600_000) {
                  lastNotifiedAt[String(highestNewMilestone)] = nowTs
                  const text = highestNewMilestone === 100
                    ? `Syncthing '${task.label || task.id}': 100% Selesai`
                    : `Syncthing '${task.label || task.id}': ${highestNewMilestone}%`
                  window.dispatchEvent(new CustomEvent("myserver:notify", {
                    detail: { text, tone: highestNewMilestone === 100 ? "success" : "info" }
                  }))
                }
              }

              if (saved.lastComp !== comp) {
                storeDirty = true
              }
              milestoneStore[task.id] = { triggered: Array.from(triggered), lastComp: comp, lastNotifiedAt }
            }
            if (storeDirty) {
              saveStoredMilestones(milestoneStore)
            }
          }
        }
      } catch {}

      try {
        const isDocHidden = typeof document !== "undefined" && document.hidden === true
        const nowTs = Date.now()
        if (!isDocHidden && (nowTs - lastServerDetailsPollTs) >= SERVER_DETAILS_POLL_MIN_MS) {
          lastServerDetailsPollTs = nowTs
          const details = await api.getServerDetails()
          const activeRoute = details?.routes?.find((r: any) => r.active)
          const currentId = activeRoute?.id || (activeRoute?.url ?? null)
          if (prevActiveRouteId !== null && currentId && currentId !== prevActiveRouteId) {
            const routeName = activeRoute?.name || activeRoute?.url || "Rute Baru"
            window.dispatchEvent(new CustomEvent("myserver:notify", {
              detail: { text: `Status Rute: Terhubung (${routeName})`, tone: "success" }
            }))
          }
          if (currentId) prevActiveRouteId = currentId
        }
      } catch {}
    }

    const milestoneInterval = setInterval(checkMilestonesAndRoutes, 4000)
    void api.getPendingSyncRequests().then(setSyncRequests)
    const appsInterval = setInterval(() => {
      void refreshWebApps()
    }, 10000)
    const drivesInterval = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) return
      void api.listDrives().then(setDrives).catch(() => undefined)
    }, 15000)
    let effectDisposed = false
    let coldStartTimer: ReturnType<typeof setTimeout> | null = null
    const syncDetailsAndMac = (details: any) => {
      if (effectDisposed) return
      const active = details?.routes?.find((r: any) => r.active)
      if (active && active.url) {
        setServerUrlState(active.url)
      }
      if (details?.macAddress && String(details.macAddress).trim()) {
        setMac(String(details.macAddress).trim().toUpperCase())
      } else {
        void api
          .detectMac()
          .then((found) => {
            if (effectDisposed) return
            const clean = (found || "").trim().toUpperCase()
            if (clean) {
              setMac(clean)
              void api.saveMac(clean)
            }
          })
          .catch(() => undefined)
      }
    }

    // Graceful initial home card loading threshold (min 650ms to allow smooth visual render)
    Promise.allSettled([
      api.getServerDetails().then(syncDetailsAndMac),
      api.listDrives().then((d) => {
        if (!effectDisposed) setDrives(d)
      }),
      api.loadSettings().then((loaded) => {
        if (effectDisposed) return
        let effective = loaded
        try {
          const urlParams = new URLSearchParams(window.location.search)
          const qTheme = urlParams.get("theme")
          const qLang = urlParams.get("lang")
          if (qTheme === "dark" || qTheme === "light") {
            effective = { ...loaded, theme: qTheme as any }
          } else {
            const cached = localStorage.getItem("myserver_theme")
            if (cached === "light" || cached === "dark") {
              effective = { ...loaded, theme: cached }
              if (loaded?.theme !== cached) {
                void api.saveSettings({ ...effective, theme: cached })
              }
            } else if (loaded?.theme === "light" || loaded?.theme === "dark") {
              localStorage.setItem("myserver_theme", loaded.theme)
            }
          }
          if (effective?.theme && typeof document !== "undefined") {
            document.documentElement.setAttribute("data-theme", effective.theme)
          }
          if (qLang === "id" || qLang === "en") {
            effective = { ...effective, language: qLang as any }
          }
        } catch {}
        if (!effectDisposed) setSettings(effective)
      }),
      refreshWebApps(),
    ]).finally(() => {
      if (effectDisposed) return
      const elapsed = Date.now() - coldStartBegin
      const remaining = Math.max(0, 650 - elapsed)
      coldStartTimer = setTimeout(() => {
        if (effectDisposed) return
        const isForcedSkeleton = typeof window !== "undefined" && window.location.search.includes("skeleton=1")
        if (isForcedSkeleton) return
        setHomeLoading(false)
        setIsInitialLoading(false)
      }, remaining)
    })

    // v4.1.0: Silent background check for updates on startup if enabled
    const autoUpdateCheckTimer = setTimeout(() => {
      try {
        const checkPromise = typeof api.loadSettings === "function" ? api.loadSettings() : Promise.resolve(null)
        Promise.resolve(checkPromise).then((loadedSettings: any) => {
          const autoCheck = loadedSettings?.autoCheckUpdate ?? true
          if (autoCheck && typeof api.checkForUpdate === "function") {
            api.checkForUpdate().then((info) => {
              if (info && !info.upToDate) {
                const parseVer = (v: string) => {
                  const parts = (v || "").match(/\d+/g)
                  return parts ? parts.map(Number) : [0, 0, 0]
                }
                const remote = parseVer(info.version)
                const current = parseVer(APP_VERSION)
                const isActuallyNewer =
                  remote[0] > current[0] ||
                  (remote[0] === current[0] && remote[1] > current[1]) ||
                  (remote[0] === current[0] && remote[1] === current[1] && remote[2] > current[2])

                if (!isActuallyNewer) return
                const isId = (loadedSettings?.language || "id") === "id"
                window.dispatchEvent(
                  new CustomEvent("myserver:notify", {
                    detail: {
                      text: isId
                        ? `Pembaruan Tersedia: MyServer v${info.version}!`
                        : `Update Available: MyServer v${info.version}!`,
                      tone: "info",
                    },
                  }),
                )
              }
            }).catch(() => {})
          }
        }).catch(() => {})
      } catch {}
    }, 3500)

    // Safety fallback: ensure monitoring skeleton doesn't spin forever if core service or server is unreachable
    const monitoringFallbackTimer = setTimeout(() => {
      setMonitoringLoading(false)
    }, 5000)

    const onStoreRefresh = () => {
      void api.listDrives().then(setDrives)
      void refreshWebApps()
      if (api.refreshMetrics) {
        void api.refreshMetrics().then((fresh) => {
          setMetrics(fresh)
          if (fresh && (!fresh.isLoading || fresh.cpu > 0 || fresh.ram > 0)) {
            setMonitoringLoading(false)
          }
        })
      }
      void api.getServerDetails().then(syncDetailsAndMac)
    }
    window.addEventListener("myserver:refresh", onStoreRefresh)

    return () => {
      effectDisposed = true
      if (coldStartTimer !== null) clearTimeout(coldStartTimer)
      offMetrics()
      offPower()
      clearInterval(appsInterval)
      clearInterval(drivesInterval)
      clearInterval(milestoneInterval)
      clearTimeout(monitoringFallbackTimer)
      clearTimeout(autoUpdateCheckTimer)
      window.removeEventListener("myserver:refresh", onStoreRefresh)
    }
  }, [api, refreshWebApps, telemetrySuspended])

  const hasStoragePartitions = Boolean(metrics.storagePartitions && metrics.storagePartitions.length > 0)
  const isSmbSyncing = Boolean(metrics.smbSyncing)
  const prevSmbSyncingRef = useRef(false)
  useEffect(() => {
    if (telemetrySuspended || !hasStoragePartitions) return
    void api.listDrives().then(setDrives).catch(() => undefined)
  }, [api, hasStoragePartitions, telemetrySuspended])

  useEffect(() => {
    if (telemetrySuspended) {
      prevSmbSyncingRef.current = isSmbSyncing
      return
    }
    if (isSmbSyncing) {
      prevSmbSyncingRef.current = true
      void api.listDrives().then(setDrives).catch(() => undefined)
      const syncPoll = setInterval(() => {
        void api.listDrives().then(setDrives).catch(() => undefined)
      }, 2000)
      return () => clearInterval(syncPoll)
    }
    if (prevSmbSyncingRef.current) {
      prevSmbSyncingRef.current = false
      void api.listDrives().then(setDrives).catch(() => undefined)
    }
  }, [api, isSmbSyncing, telemetrySuspended])

  const value = useMemo<CompanionStore>(
    () => ({
      metrics,
      power,
      isOnline: power === "online",
      isAdmin: Boolean(metrics.isAdmin),
      reboot: () => api.reboot(),
      shutdown: () => api.shutdown(),
      wake: () => api.wakeOnLan(mac),
      drives,
      setAllMounted: async (mounted) =>
        setDrives(await api.setAllMounted(mounted)),
      settings,
      setSetting: async (key, v) => {
        const previousValue = settingsRef.current[key]
        const nextSnapshot = { ...settingsRef.current, [key]: v }
        settingsRef.current = nextSnapshot
        if (key === "theme") {
          try {
            localStorage.setItem("myserver_theme", String(v))
            document.documentElement.setAttribute("data-theme", String(v))
          } catch {}
        }
        setSettings((prev) => {
          const next = { ...prev, [key]: v }
          settingsRef.current = next
          return next
        })
        try {
          await api.saveSettings(nextSnapshot)
        } catch (error) {
          setSettings((prev) => {
            const rolledBack = { ...prev, [key]: previousValue }
            settingsRef.current = rolledBack
            return rolledBack
          })
          throw error
        }
      },
      resetSettings: async () => {
        settingsRef.current = DEFAULT_SETTINGS
        setSettings(DEFAULT_SETTINGS)
        await api.saveSettings(DEFAULT_SETTINGS)
      },
      syncRequests,
      acceptSyncRequest: async () => {
        await api.acceptSyncRequest()
        setSyncRequests((n) => Math.max(0, n - 1))
      },
      mac,
      setMac,
      checklist,
      toggleCheck: (key, value) => setChecklist((c) => ({ ...c, [key]: value !== undefined ? value : !c[key] })),
      webApps,
      serverUrl,
      refreshWebApps,
      addWebApp,
      deleteWebApp,
      openUrl,
      openExternalBrowser,
      refreshDrives,
      transitionState,
      startTransition,
      endTransition,
      runWithTransition,
      isInitialLoading,
      homeLoading,
      monitoringLoading,
      setMonitoringLoading,
      wizardOpen,
      wizardInitializing,
      openedFromSettings,
      openWizard,
      closeWizard,
    }),
    [
      api,
      metrics,
      power,
      drives,
      settings,
      syncRequests,
      mac,
      checklist,
      webApps,
      serverUrl,
      refreshWebApps,
      addWebApp,
      deleteWebApp,
      openUrl,
      openExternalBrowser,
      refreshDrives,
      transitionState,
      startTransition,
      endTransition,
      runWithTransition,
      isInitialLoading,
      homeLoading,
      monitoringLoading,
      setMonitoringLoading,
      wizardOpen,
      wizardInitializing,
      openedFromSettings,
      openWizard,
      closeWizard,
    ],
  )

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useCompanion() {
  const store = useContext(StoreContext)
  if (!store)
    throw new Error("useCompanion must be used inside CompanionStoreProvider")
  return store
}

interface PowerStatus {
  tone: Tone
  label: string
}

const POWER_STATUS: Record<PowerState, PowerStatus> = {
  online: { tone: "success", label: "Online" },
  rebooting: { tone: "warning", label: "Restart" },
  waking: { tone: "warning", label: "Waking" },
  offline: { tone: "neutral", label: "Offline" },
}

export function usePowerStatus(): PowerStatus {
  const { power, isOnline } = useCompanion()
  return POWER_STATUS[power] || (isOnline ? { tone: "success", label: "Online" } : { tone: "neutral", label: "Offline" })
}

/** Runs an API task: idle → busy → done → idle. Failures surface as a danger toast. */
export function useAsyncAction<T = void>(task: () => Promise<T>) {
  const [state, setState] = useState<"idle" | "busy" | "done">("idle")
  const timer = useRef<number | undefined>(undefined)
  const busy = useRef(false)
  const alive = useRef(true)
  const { notify } = useNotice()

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      window.clearTimeout(timer.current)
    }
  }, [])

  const run = useCallback(
    async (onComplete?: (result: T) => void) => {
      if (busy.current) return
      busy.current = true
      setState("busy")
      try {
        const result = await task()
        onComplete?.(result)
        if (!alive.current) return
        setState("done")
        timer.current = window.setTimeout(() => setState("idle"), 1600)
      } catch (error) {
        if (alive.current) setState("idle")
        notify(errorText(error), "danger")
      } finally {
        busy.current = false
      }
    },
    [task, notify],
  )

  return [state, run] as const
}

interface Notice {
  id: number
  text: string
  tone: Tone
}

const NoticeContext = createContext<{
  notice: Notice | null
  notify: (text: string, tone?: Tone) => void
  noticeHistory: NoticeHistoryItem[]
  clearNoticeHistory: () => void
} | null>(null)

/** Per-companion transient notices, so a toast appears only in the flyout that triggered it. */
export function NoticeProvider({ children }: { children: ReactNode }) {
  const [notice, setNotice] = useState<Notice | null>(null)
  const [noticeHistory, setNoticeHistory] = useState<NoticeHistoryItem[]>(() => {
    try {
      const raw = localStorage.getItem("myserver_notice_history")
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) return parsed
      }
    } catch {}
    return []
  })
  const timer = useRef<number | undefined>(undefined)
  const nextNoticeIdRef = useRef(0)
  const recentNoticeTsRef = useRef<Map<string, number>>(new Map())

  const clearNoticeHistory = useCallback(() => {
    setNoticeHistory([])
    recentNoticeTsRef.current.clear()
    try {
      localStorage.removeItem("myserver_notice_history")
      localStorage.setItem(
        "myserver_last_seen_notice_id",
        String(Math.max(nextNoticeIdRef.current, Date.now() * 1000)),
      )
    } catch {}
  }, [])

  const notify = useCallback((text: string, tone: Tone = "success") => {
    const nowTs = Date.now()
    const dedupKey = `${tone}::${text}`
    const lastTs = recentNoticeTsRef.current.get(dedupKey)
    const isDuplicateBurst = lastTs !== undefined && (nowTs - lastTs) < 60_000
    recentNoticeTsRef.current.set(dedupKey, nowTs)

    window.clearTimeout(timer.current)
    nextNoticeIdRef.current = Math.max(nextNoticeIdRef.current + 1, nowTs * 1000)
    const id = nextNoticeIdRef.current
    const d = new Date()
    const timeStr = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`
    setNotice({ id, text, tone })
    if (!isDuplicateBurst) {
      setNoticeHistory((prev) => {
        const filtered = prev.filter((item) => !(item.text === text && item.tone === tone))
        const next = [{ id, text, tone, timeStr }, ...filtered.slice(0, 49)]
        try {
          localStorage.setItem("myserver_notice_history", JSON.stringify(next))
        } catch {}
        return next
      })
    }
    timer.current = window.setTimeout(() => setNotice(null), 3200)
  }, [])

  useEffect(() => {
    const handleCustomNotify = (e: Event) => {
      const ce = e as CustomEvent<{ text: string; tone?: Tone }>
      if (ce.detail?.text) {
        notify(ce.detail.text, ce.detail.tone)
      }
    }
    window.addEventListener("myserver:notify", handleCustomNotify)
    return () => {
      window.removeEventListener("myserver:notify", handleCustomNotify)
      window.clearTimeout(timer.current)
    }
  }, [notify])

  const value = useMemo(() => ({ notice, notify, noticeHistory, clearNoticeHistory }), [notice, notify, noticeHistory, clearNoticeHistory])
  return (
    <NoticeContext.Provider value={value}>{children}</NoticeContext.Provider>
  )
}

export function useNotice() {
  const ctx = useContext(NoticeContext)
  if (!ctx) throw new Error("useNotice must be used inside NoticeProvider")
  return ctx
}

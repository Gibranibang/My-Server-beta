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
  const [syncRequests, setSyncRequests] = useState(0)
  const [transitionState, setTransitionState] = useState<TransitionState>({ active: false, title: "" })
  const [isInitialLoading, setIsInitialLoading] = useState(true)
  const [homeLoading, setHomeLoading] = useState(true)
  const [monitoringLoading, setMonitoringLoading] = useState(true)

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
      startTransition(title, message)
      const shouldReset = options?.resetMetrics ?? false
      if (shouldReset) {
        setMonitoringLoading(true)
        setMetrics({
          ...EMPTY_METRICS,
          isLoading: true,
        })
      }
      try {
        const result = await task()

        // Progressive auto-refresh for newly mounted SMB drives & fresh metrics
        void (async () => {
          let metricsSettled = false
          for (let i = 0; i < 16; i++) {
            try {
              const [drivesRes, freshMetrics] = await Promise.allSettled([
                api.listDrives(),
                api.refreshMetrics ? api.refreshMetrics() : Promise.resolve(null),
              ])
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
              }
            } catch {
              // ignore
            }
            if (metricsSettled && i >= 6) {
              break
            }
            await new Promise((r) => setTimeout(r, 350))
          }
          setMonitoringLoading(false)
          setMetrics((m) => (m.isLoading ? { ...m, isLoading: false } : m))
        })()

        await new Promise((r) => setTimeout(r, 200))
        return result
      } finally {
        endTransition()
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
    const coldStartBegin = Date.now()
    const offMetrics = api.subscribeMetrics((newM) => {
      setMetrics(newM)
      if (newM && (!newM.isLoading || newM.cpu > 0 || newM.ram > 0)) {
        setMonitoringLoading(false)
      }
    })
    let prevPowerState: string | null = null
    const offPower = api.subscribePower((p) => {
      setPower(p)
      if (p === "offline" || p === "online") {
        setMonitoringLoading(false)
      }
      if (prevPowerState !== null && p !== prevPowerState) {
        if (p === "connecting") {
          window.dispatchEvent(new CustomEvent("myserver:notify", {
            detail: { text: "Menghubungkan ke server...", tone: "warning" }
          }))
        } else if (p === "online") {
          window.dispatchEvent(new CustomEvent("myserver:notify", {
            detail: { text: "Terhubung ke server", tone: "success" }
          }))
        } else if (p === "offline") {
          window.dispatchEvent(new CustomEvent("myserver:notify", {
            detail: { text: "Koneksi Terputus", tone: "danger" }
          }))
        }
      }
      prevPowerState = p
    })

    // Monitoring notifikasi berkala: Syncthing milestones (25%, 50%, 90%, 100%) & perubahan rute
    const lastMilestones = new Map<string, Set<number>>()
    let prevActiveRouteId: string | null = null

    const checkMilestonesAndRoutes = async () => {
      try {
        if (api.getSyncthingTasks) {
          const tasks = await api.getSyncthingTasks()
          if (Array.isArray(tasks)) {
            for (const task of tasks) {
              if (task.paused) continue
              const comp = Math.round(task.completion || 0)
              let triggered = lastMilestones.get(task.id)
              if (!triggered) {
                triggered = new Set<number>()
                lastMilestones.set(task.id, triggered)
              }
              if (comp < 20) {
                triggered.clear()
              }
              for (const m of [25, 50, 90, 100]) {
                if (comp >= m && !triggered.has(m)) {
                  triggered.add(m)
                  const text = m === 100
                    ? `Syncthing '${task.label || task.id}': 100% Selesai`
                    : `Syncthing '${task.label || task.id}': ${m}%`
                  window.dispatchEvent(new CustomEvent("myserver:notify", {
                    detail: { text, tone: m === 100 ? "success" : "info" }
                  }))
                }
              }
            }
          }
        }
      } catch {}

      try {
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
      } catch {}
    }

    const milestoneInterval = setInterval(checkMilestonesAndRoutes, 4000)
    void api.getPendingSyncRequests().then(setSyncRequests)
    const appsInterval = setInterval(() => {
      void refreshWebApps()
    }, 10000)
    const syncDetailsAndMac = (details: any) => {
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
      api.listDrives().then(setDrives),
      api.loadSettings().then((loaded) => {
        let effective = loaded
        try {
          const urlParams = new URLSearchParams(window.location.search)
          const qTheme = urlParams.get("theme")
          if (qTheme === "dark" || qTheme === "light") {
            effective = { ...loaded, theme: qTheme as any }
          } else {
            const cached = localStorage.getItem("myserver_theme")
            if (cached && (!loaded || !loaded.theme)) {
              effective = { ...loaded, theme: cached as any }
            } else if (loaded?.theme) {
              localStorage.setItem("myserver_theme", loaded.theme)
            }
          }
        } catch {}
        setSettings(effective)
      }),
      refreshWebApps(),
    ]).finally(() => {
      const elapsed = Date.now() - coldStartBegin
      const remaining = Math.max(0, 650 - elapsed)
      setTimeout(() => {
        setHomeLoading(false)
        setIsInitialLoading(false)
      }, remaining)
    })

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
      offMetrics()
      offPower()
      clearInterval(appsInterval)
      clearInterval(milestoneInterval)
      clearTimeout(monitoringFallbackTimer)
      window.removeEventListener("myserver:refresh", onStoreRefresh)
    }
  }, [api, refreshWebApps])

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
        const previous = settings
        const next = { ...settings, [key]: v }
        if (key === "theme") {
          try {
            localStorage.setItem("myserver_theme", String(v))
            document.documentElement.setAttribute("data-theme", String(v))
          } catch {}
        }
        setSettings(next)
        try {
          await api.saveSettings(next)
        } catch (error) {
          setSettings(previous)
          throw error
        }
      },
      resetSettings: async () => {
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
  const [noticeHistory, setNoticeHistory] = useState<NoticeHistoryItem[]>([])
  const timer = useRef<number | undefined>(undefined)

  const clearNoticeHistory = useCallback(() => {
    setNoticeHistory([])
  }, [])

  const notify = useCallback((text: string, tone: Tone = "success") => {
    window.clearTimeout(timer.current)
    const id = Date.now()
    const d = new Date()
    const timeStr = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`
    setNotice({ id, text, tone })
    setNoticeHistory((prev) => [{ id, text, tone, timeStr }, ...prev.slice(0, 49)])
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

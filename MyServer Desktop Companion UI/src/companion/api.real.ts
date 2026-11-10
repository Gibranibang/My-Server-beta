import type { CompanionApi, UpdateInfo } from "./api"
import { APP_VERSION, APP_CHANNEL } from "./version"

import { setServerIp, setServerUrl, setDefaultMac, DEFAULT_SETTINGS } from "./api"

import type { Drive, Metrics, PowerState, Settings, WebApp, SyncthingFullStatus, SyncthingFolderTask, ServerDetails, SyncthingConfigData } from "./types"



const round1 = (v: number) => Math.round(v * 10) / 10



/** Helper to interact with Python backend safely (supports Tauri Native IPC invoke and pywebview) */

async function getPyApi(): Promise<any> {

  const w = window as any



  // Detect Tauri runtime immediately (Zero latency / Zero pywebview timeout)

  const hasTauri = Boolean(w.__TAURI_INTERNALS__ || w.__TAURI__)

  if (hasTauri) {

    const invoke = (cmd: string, args?: any) => {

      if (w.__TAURI_INTERNALS__?.invoke) {

        return w.__TAURI_INTERNALS__.invoke(cmd, args)

      }

      if (w.__TAURI__?.core?.invoke) {

        return w.__TAURI__.core.invoke(cmd, args)

      }

      throw new Error('Tauri invoke function not found')

    }



    const tauriProxy: any = new Proxy({}, {

      get(_target, prop: string | symbol) {

        if (typeof prop === "symbol" || prop === "then" || prop === "toJSON" || prop === "constructor") {

          return undefined

        }

        const propStr = String(prop)

        if (propStr === 'minimize') {

          return async () => invoke('minimize_window')

        }

        if (propStr === 'hide_flyout' || prop === 'hide') {

          return async () => invoke('hide_window')

        }

        if (propStr === 'quit_app' || prop === 'exit') {

          return async () => {

            try {

              await invoke('call_core_api', { endpoint: 'quit_app', payload: {} })

            } catch {}

            return invoke('exit_app')

          }

        }



        // Native Tauri Command RPC forwarding directly to Core Service (Zero CORS / Zero Browser Sandbox blocks)

        return async (...args: any[]) => {

          let payload: any = {}

          if (args.length === 1 && typeof args[0] === 'object' && !Array.isArray(args[0])) {

            payload = args[0]

          } else if (args.length > 0) {

            payload = {

              arg: args[0],

              args: args,

              name: args[0],

              url: args.length > 1 ? args[1] : args[0],

              serverId: args[0],

              routeId: args[0],

              profileName: args[0],

            }

          }

          return invoke('call_core_api', {

            endpoint: propStr,

            payload: payload,

          })

        }

      }

    })



    return tauriProxy

  }



  // PyWebView fallback

  if (w.pywebview && w.pywebview.api) {

    return w.pywebview.api

  }



  return null

}



export function createRealApi(): CompanionApi {

  let power: PowerState = "online"

  const powerListeners = new Set<(p: PowerState) => void>()
  const metricsListeners = new Set<(m: Metrics) => void>()

  let currentMetrics: Metrics = {
    cpu: 0,
    ram: 0,
    hdd: 0,
    lanDown: 0,
    lanHistory: Array(12).fill(0),
    syncUp: 0,
    syncDown: 0,
  }

  let currentDrives: Drive[] = []
  let currentSettings: Settings = DEFAULT_SETTINGS
  let syncRequests = 0

  const notifyMetrics = (m: Metrics) => {
    metricsListeners.forEach((fn) => fn(m))
  }

  const setPower = (next: PowerState) => {
    if (power !== next) {
      power = next
      powerListeners.forEach((fn) => fn(next))
    }
  }

  let rebootTimestamp = 0
  let rebootSawOffline = false
  let wakeTimestamp = 0
  let isPollingRunning = false
  let pollTimeoutId: number | undefined
  let isPollInProgress = false

  const parseStateToMetrics = (state: any): Metrics => {
    if (state.ip) {
      setServerIp(state.ip)
    }
    if (state.server_url) {
      setServerUrl(state.server_url)
    }

    const speedDownKb = Number(state.speed_down || 0)
    const speedUpKb = Number(state.speed_up || 0)
    const lanDownMb = round1(speedDownKb / 1024)
    const syncDownMb = round1(Number(state.sync_down || speedDownKb) / 1024)
    const syncUpMb = round1(Number(state.sync_up || speedUpKb) / 1024)
    const newHistory = [...currentMetrics.lanHistory.slice(1), lanDownMb]

    currentMetrics = {
      cpu: Math.round(Number(state.cpu_percent || 0)),
      ram: Math.round(Number(state.ram_percent || 0)),
      hdd: Math.round(Number(state.disk_percent || 0)),
      lanDown: lanDownMb,
      lanHistory: newHistory,
      syncUp: syncUpMb,
      syncDown: syncDownMb,
      speedDownStr: state.speed_down_str || `${lanDownMb} MB/s`,
      speedUpStr: state.speed_up_str || `${syncUpMb} MB/s`,
      speedDownBps: Number(state.speed_down_bps || 0),
      speedUpBps: Number(state.speed_up_bps || 0),
      isAdmin: Boolean(state.is_admin),
      cpuWattage: state.cpu_wattage !== undefined ? Number(state.cpu_wattage) : undefined,
      cpuTemp: state.cpu_temperature !== undefined && state.cpu_temperature !== null ? Number(state.cpu_temperature) : null,
      ramUsedBytes: state.ram_used_bytes !== undefined ? Number(state.ram_used_bytes) : undefined,
      ramTotalBytes: state.ram_total_bytes !== undefined ? Number(state.ram_total_bytes) : undefined,
      storageUsedBytes: state.storage_used_bytes !== undefined ? Number(state.storage_used_bytes) : undefined,
      storageTotalBytes: state.storage_total_bytes !== undefined ? Number(state.storage_total_bytes) : undefined,
      storagePartitions: Array.isArray(state.storage_partitions) ? state.storage_partitions : undefined,
      isLoading: Boolean(state.telemetry_loading),
    }
    return currentMetrics
  }

  const pollCycle = async () => {
    if (isPollInProgress) return
    isPollInProgress = true
    try {
      const api = await getPyApi()
      if (!api) return
      const state = await api.get_state()
      if (!state) return

      const isOnline = Boolean(state.is_online)
      const now = Date.now()
      let powerChangedToOnline = false

      if (power === "rebooting") {
        if (!isOnline) {
          rebootSawOffline = true
        }
        if ((rebootSawOffline || now > rebootTimestamp + 10000) && isOnline) {
          rebootSawOffline = false
          setPower("online")
          powerChangedToOnline = true
        } else if (now > rebootTimestamp + 180000) {
          rebootSawOffline = false
          setPower(isOnline ? "online" : "offline")
        }
      } else if (power === "waking") {
        if (isOnline) {
          setPower("online")
          powerChangedToOnline = true
        } else if (now > wakeTimestamp + 90000) {
          setPower("offline")
        }
      } else {
        const prevPower = power
        const nextPower = isOnline ? "online" : "offline"
        setPower(nextPower)
        if (prevPower !== "online" && nextPower === "online") {
          powerChangedToOnline = true
        }
      }

      // Selalu perbarui metrik dan sebarkan SETELAH status daya (online/offline) terselesaikan
      const updatedMetrics = parseStateToMetrics(state)
      notifyMetrics(updatedMetrics)

      if (powerChangedToOnline) {
        window.dispatchEvent(new CustomEvent("myserver:refresh"))
      }
    } catch (err) {
      console.warn("[RealApi] Metrics poll error:", err)
    } finally {
      isPollInProgress = false
      if (isPollingRunning) {
        // Akselerasi interval saat waking/rebooting/offline (1000ms) agar respons online & metrik instan
        const interval = (power === "waking" || power === "rebooting" || power === "offline") ? 1000 : 2000
        pollTimeoutId = window.setTimeout(pollCycle, interval)
      }
    }
  }

  const startPolling = () => {
    if (!isPollingRunning) {
      isPollingRunning = true
      void pollCycle()
    }
  }

  const triggerPollNow = () => {
    if (pollTimeoutId !== undefined) {
      window.clearTimeout(pollTimeoutId)
      pollTimeoutId = undefined
    }
    void pollCycle()
  }

  return {

    subscribeMetrics(onMetrics) {
      metricsListeners.add(onMetrics)
      onMetrics(currentMetrics)
      startPolling()

      const onVisChange = () => {
        if (!document.hidden) triggerPollNow()
      }
      window.addEventListener("focus", triggerPollNow)
      window.addEventListener("online", triggerPollNow)
      document.addEventListener("visibilitychange", onVisChange)
      window.addEventListener("myserver:refresh", triggerPollNow)

      return () => {
        metricsListeners.delete(onMetrics)
        window.removeEventListener("focus", triggerPollNow)
        window.removeEventListener("online", triggerPollNow)
        document.removeEventListener("visibilitychange", onVisChange)
        window.removeEventListener("myserver:refresh", triggerPollNow)
      }
    },

    async refreshMetrics(): Promise<Metrics> {
      try {
        const api = await getPyApi()
        if (api && api.get_state) {
          const state = await api.get_state()
          if (state) {
            const isOnline = Boolean(state.is_online)
            if (isOnline && (power === "waking" || power === "rebooting" || power === "offline")) {
              setPower("online")
            } else if (!isOnline && power === "online") {
              setPower("offline")
            }
            const updated = parseStateToMetrics(state)
            notifyMetrics(updated)
            return updated
          }
        }
      } catch (err) {
        console.warn("[RealApi] refreshMetrics error:", err)
      }
      return currentMetrics
    },

    subscribePower(onPower) {

      powerListeners.add(onPower)

      onPower(power)

      return () => {

        powerListeners.delete(onPower)

      }

    },



    async reboot() {

      rebootTimestamp = Date.now()
      rebootSawOffline = false
      setPower("rebooting")
      triggerPollNow()

      try {

        const api = await getPyApi()

        if (api && api.reboot) {

          await api.reboot()

        }

      } catch (err) {

        console.error("[RealApi] Reboot error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal memulai ulang server.")

      }

    },



    async shutdown() {

      try {

        const api = await getPyApi()

        if (api && api.shutdown) {

          await api.shutdown()

        }

        setPower("offline")

      } catch (err) {

        console.error("[RealApi] Shutdown error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal mematikan server.")

      }

    },



    async wakeOnLan(mac: string) {

      wakeTimestamp = Date.now()
      setPower("waking")
      triggerPollNow()

      try {

        const api = await getPyApi()

        if (api && api.wake_on_lan) {

          await api.wake_on_lan(mac)

        }

      } catch (err) {

        console.error("[RealApi] Wake-on-LAN error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal mengirim paket Wake-on-LAN.")

      }

    },



    async detectMac() {

      try {

        const api = await getPyApi()

        if (api && api.detect_mac) {

          const detected = await api.detect_mac()

          if (detected) {

            setDefaultMac(detected)

            return detected

          }

        }

      } catch (err) {

        console.warn("[RealApi] Detect MAC error:", err)

      }

      return ""

    },



    async listDrives() {

      try {

        const api = await getPyApi()

        if (api && api.list_drives) {

          const drives = await api.list_drives()

          if (Array.isArray(drives)) {

            currentDrives = drives

            return currentDrives

          }

        }

      } catch (err) {

        console.warn("[RealApi] List drives error:", err)

      }

      return currentDrives

    },



    async setAllMounted(mounted: boolean) {

      try {

        const api = await getPyApi()

        if (api && api.set_all_mounted) {

          const drives = await api.set_all_mounted(mounted)

          if (Array.isArray(drives)) {

            currentDrives = drives

            return currentDrives

          }

        }

      } catch (err) {

        console.error("[RealApi] Set all mounted error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal mengubah status partisi SMB.")

      }

      currentDrives = currentDrives.map((d) => ({ ...d, mounted }))

      return currentDrives

    },



    async loadSettings() {

      try {

        const api = await getPyApi()

        if (api && api.load_settings) {

          const s = await api.load_settings()

          if (s) {
            const cachedTheme = typeof window !== "undefined" ? localStorage.getItem("myserver_theme") : null
            const resolvedTheme = (s.theme === "light" || s.theme === "dark")
              ? s.theme
              : (cachedTheme === "light" || cachedTheme === "dark" ? cachedTheme : DEFAULT_SETTINGS.theme)
            currentSettings = { ...DEFAULT_SETTINGS, ...s, theme: resolvedTheme }

            return currentSettings

          }

        }

      } catch (err) {

        console.warn("[RealApi] Load settings error:", err)

      }

      return currentSettings

    },



    async saveSettings(settings: Settings) {

      currentSettings = settings

      try {

        const api = await getPyApi()

        if (api && api.save_settings) {

          await api.save_settings(settings)

        }

      } catch (err) {

        console.error("[RealApi] Save settings error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal menyimpan pengaturan.")

      }

    },



    async createBackup() {

      try {

        const api = await getPyApi()

        if (api && api.create_backup) {

          const res = await api.create_backup()

          if (res && res.file) return res

        }

      } catch (err) {

        console.error("[RealApi] Create backup error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal membuat cadangan data.")

      }

      return { file: `myserver-backup-${new Date().toISOString().slice(0, 10)}.zip` }

    },



    async restoreBackup() {

      try {

        const api = await getPyApi()

        if (api && api.restore_backup) {

          const res = await api.restore_backup()

          if (res && res.rollbackFile) return res

        }

      } catch (err) {

        console.error("[RealApi] Restore backup error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal memulihkan cadangan data.")

      }

      return { rollbackFile: "myserver-config.bak" }

    },



    async clearCache() {

      try {

        const api = await getPyApi()

        if (api && api.clear_cache) {

          const res = await api.clear_cache()

          if (res && typeof res.freedMb === "number") return res

        }

      } catch (err) {

        console.error("[RealApi] Clear cache error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal membersihkan cache browser.")

      }

      return { freedMb: 0 }

    },



    async checkForUpdate(): Promise<UpdateInfo> {

      try {

        const api = await getPyApi()

        if (api && api.check_for_update) {

          const res = await api.check_for_update()

          if (res) return res

        }

      } catch (err) {

        console.warn("[RealApi] Check for update error:", err)

      }

      return { upToDate: true, version: APP_VERSION }

    },



    async getPendingSyncRequests() {

      try {

        const api = await getPyApi()

        if (api && api.get_pending_sync_requests) {

          const count = await api.get_pending_sync_requests()

          syncRequests = Number(count || 0)

          return syncRequests

        }

      } catch (err) {

        console.warn("[RealApi] Get pending sync error:", err)

      }

      return syncRequests

    },



    async acceptSyncRequest() {

      try {

        const api = await getPyApi()

        if (api && api.accept_sync_request) {

          await api.accept_sync_request()

        }

        syncRequests = Math.max(0, syncRequests - 1)

      } catch (err) {

        console.error("[RealApi] Accept sync request error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal menerima permintaan sinkronisasi.")

      }

    },



    async saveMac(mac: string) {

      try {

        const api = await getPyApi()

        if (api && api.save_mac) {

          await api.save_mac(mac)

        }

      } catch (err) {

        console.error("[RealApi] Save MAC error:", err)

      }

    },



    async hideFlyout() {

      try {

        const api = await getPyApi()

        if (api && api.hide_flyout) {

          await api.hide_flyout()

        }

      } catch (err) {

        console.warn("[RealApi] Hide flyout error:", err)

      }

    },



    async minimizeWindow() {

      try {

        const api = await getPyApi()

        if (api && api.minimize) {

          await api.minimize()

        }

      } catch (err) {

        console.warn("[RealApi] Minimize window error:", err)

      }

    },



    async probeUrl(url: string) {
      try {
        const api = await getPyApi()
        if (api && api.probe_url) {
          return await api.probe_url({ url })
        }
      } catch (err) {
        console.warn('[RealApi] probeUrl error:', err)
      }
      return { reachable: true, latency_ms: 0, url }
    },

    async getActivityLog() {
      try {
        const api = await getPyApi()
        if (api && api.get_activity_log) {
          const res = await api.get_activity_log({})
          return res || { lines: [] }
        }
      } catch (err) {
        console.warn('[RealApi] getActivityLog error:', err)
      }
      return { lines: [] }
    },

    async openUrl(url: string, title?: string) {
      // Zima Client v2.3.5 probeDashboard check: Verifikasi target tanpa memblokir pembukaan
      try {
        const probe = await this.probeUrl(url)
        if (probe && probe.reachable === false) {
          console.warn(`[RealApi] Probe check: target port offline/closed (${probe.error || 'Offline'}), melanjutkan peluncuran jendela...`)
        }
      } catch (err: any) {
        console.warn('[RealApi] Probe check warning:', err)
      }

      let launched = false
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          await invoke('open_app_window', { url, title: title || '' })
          launched = true
          return
        } catch (err) {
          console.warn('[RealApi] Tauri open_app_window error, mencoba fallback core API:', err)
        }
      }

      try {
        const api = await getPyApi()
        if (api && api.open_app_window) {
          await api.open_app_window({ url, title: title || '' })
          launched = true
        } else if (api && api.open_url) {
          await api.open_url({ url, title: title || '' })
          launched = true
        }
      } catch (err) {
        console.warn('[RealApi] Python API open_app_window error:', err)
      }

      if (!launched) {
        try {
          await this.openExternalBrowser(url)
        } catch (browserErr) {
          console.warn('[RealApi] Fallback browser error:', browserErr)
        }
      }
    },



    async openExternalBrowser(url: string) {

      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {

        try {

          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke

          await invoke('open_in_browser', { url })

          return

        } catch (err) {

          console.warn('[RealApi] Tauri open_in_browser error:', err)

        }

      }

      try {

        const api = await getPyApi()

        if (api && api.open_external_browser) {

          await api.open_external_browser({ url })

        }

      } catch (err) {

        console.warn('[RealApi] openExternalBrowser error:', err)

      }

    },



    async syncInstaBoxVm(params: { apiKey: string; machineId?: string; vmName?: string; vmId?: string }) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'instabox/sync', payload: params })
        } catch (err) {
          console.warn('[RealApi] syncInstaBoxVm invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['instabox/sync']) {
          return await api['instabox/sync'](params)
        }
      } catch (err) {
        console.warn('[RealApi] syncInstaBoxVm error:', err)
      }
      return { success: false, error: 'Core service unreachable' }
    },

    async smartResetInstaBox(params: { apiKey?: string; machineId?: string; vmId?: string }) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'instabox/smart_reset', payload: params })
        } catch (err) {
          console.warn('[RealApi] smartResetInstaBox invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['instabox/smart_reset']) {
          return await api['instabox/smart_reset'](params)
        }
      } catch (err) {
        console.warn('[RealApi] smartResetInstaBox error:', err)
      }
      return { success: false, error: 'Core service unreachable' }
    },

    async wakeInstaBoxVm(params: { apiKey?: string; machineId?: string; vmId?: string }) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'instabox/wake', payload: params })
        } catch (err) {
          console.warn('[RealApi] wakeInstaBoxVm invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['instabox/wake']) {
          return await api['instabox/wake'](params)
        }
      } catch (err) {
        console.warn('[RealApi] wakeInstaBoxVm error:', err)
      }
      return { success: false, error: 'Core service unreachable' }
    },

    async pauseInstaBoxVm(params: { apiKey?: string; machineId?: string; vmId?: string }) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'instabox/pause', payload: params })
        } catch (err) {
          console.warn('[RealApi] pauseInstaBoxVm invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['instabox/pause']) {
          return await api['instabox/pause'](params)
        }
      } catch (err) {
        console.warn('[RealApi] pauseInstaBoxVm error:', err)
      }
      return { success: false, error: 'Core service unreachable' }
    },

    async loadVms() {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          const res = await invoke('call_core_api', { endpoint: 'vms/load', payload: {} })
          if (res && Array.isArray(res.vms)) return res.vms
        } catch (err) {
          console.warn('[RealApi] loadVms invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['vms/load']) {
          const res = await api['vms/load']({})
          if (res && Array.isArray(res.vms)) return res.vms
        }
      } catch (err) {
        console.warn('[RealApi] loadVms error:', err)
      }
      return []
    },

    async saveVms(vms: any[]) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'vms/save', payload: { vms } })
        } catch (err) {
          console.warn('[RealApi] saveVms invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['vms/save']) {
          return await api['vms/save']({ vms })
        }
      } catch (err) {
        console.warn('[RealApi] saveVms error:', err)
      }
      return { status: 'error' }
    },

    async updateVm(vmId: string, updates: any, serverId?: string) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'vms/update', payload: { vmId, vm: updates, serverId } })
        } catch (err) {
          console.warn('[RealApi] updateVm invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['vms/update']) {
          return await api['vms/update']({ vmId, vm: updates, serverId })
        }
      } catch (err) {
        console.warn('[RealApi] updateVm error:', err)
      }
      return { status: 'error' }
    },

    async deleteVm(vmId: string, scope?: string, serverId?: string) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'vms/delete', payload: { vmId, scope, serverId } })
        } catch (err) {
          console.warn('[RealApi] deleteVm invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['vms/delete']) {
          return await api['vms/delete']({ vmId, scope, serverId })
        }
      } catch (err) {
        console.warn('[RealApi] deleteVm error:', err)
      }
      return { status: 'error' }
    },

    async migrateVm(vmId: string, targetScope: "server" | "local") {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'vms/migrate', payload: { vm_id: vmId, target_scope: targetScope } })
        } catch (err) {
          console.warn('[RealApi] migrateVm invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['vms/migrate']) {
          return await api['vms/migrate']({ vm_id: vmId, target_scope: targetScope })
        }
      } catch (err) {
        console.warn('[RealApi] migrateVm error:', err)
      }
      return { status: 'error' }
    },

    async openSshTerminal(params?: { host?: string; user?: string; port?: number }) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'server/ssh_terminal', payload: params || {} })
        } catch (err) {
          console.warn('[RealApi] openSshTerminal invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['server/ssh_terminal']) {
          return await api['server/ssh_terminal'](params || {})
        }
      } catch (err) {
        console.warn('[RealApi] openSshTerminal error:', err)
      }
      return { status: 'error' }
    },

    async triggerBackendAction(action: "install" | "update", serverId?: string) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'server/backend_action', payload: { action, serverId } })
        } catch (err) {
          console.warn('[RealApi] triggerBackendAction invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['server/backend_action']) {
          return await api['server/backend_action']({ action, serverId })
        }
      } catch (err) {
        console.warn('[RealApi] triggerBackendAction error:', err)
      }
      return { success: false, status: 'error', message: 'API tidak tersedia' }
    },

    async getBackendStatus(serverId?: string) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          return await invoke('call_core_api', { endpoint: 'server/backend_status', payload: { serverId } })
        } catch (err) {
          console.warn('[RealApi] getBackendStatus invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['server/backend_status']) {
          return await api['server/backend_status']({ serverId })
        }
      } catch (err) {
        console.warn('[RealApi] getBackendStatus error:', err)
      }
      return { online: false, version: '', latestVersion: '1.2.2' }
    },

    async openVmWindow(vmId: string, title: string, url: string) {
      if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
        try {
          const invoke = (window as any).__TAURI_INTERNALS__?.invoke || (window as any).__TAURI__?.core?.invoke
          await invoke('call_core_api', { endpoint: 'vm/open_window', payload: { vmId, title, url } })
          return
        } catch (err) {
          console.warn('[RealApi] openVmWindow invoke error:', err)
        }
      }
      try {
        const api = await getPyApi()
        if (api && api['vm/open_window']) {
          await api['vm/open_window']({ vmId, title, url })
          return
        }
      } catch (err) {
        console.warn('[RealApi] openVmWindow error:', err)
      }
      await this.openUrl(url, title)
    },

    async openFileExplorer() {
      try {
        const api = await getPyApi()
        if (api && api.open_file_explorer) {
          await api.open_file_explorer()
        }
      } catch (err) {
        console.error("[RealApi] Open File Explorer error:", err)
      }
    },

    async openZimaFileManager() {
      try {
        const api = await getPyApi()
        if (api && api.open_zima_file_manager) {
          await api.open_zima_file_manager()
        }
      } catch (err) {
        console.error("[RealApi] Open Zima File Manager error:", err)
      }
    },

    async openFileManager() {

      try {

        const api = await getPyApi()

        if (api && api.open_file_manager) {

          await api.open_file_manager()

        }

      } catch (err) {

        console.error("[RealApi] Open File Manager error:", err)

      }

    },



    async openPeerDrop() {

      try {

        const api = await getPyApi()

        if (api && api.open_peerdrop) {

          await api.open_peerdrop()

        }

      } catch (err) {

        console.error("[RealApi] Open PeerDrop error:", err)

      }

    },



    async openUnc() {

      try {

        const api = await getPyApi()

        if (api && api.open_unc) {

          await api.open_unc()

        }

      } catch (err) {

        console.error("[RealApi] Open UNC error:", err)

      }

    },



    async openDrive(letter: string) {

      try {

        const api = await getPyApi()

        if (api && api.open_drive) {

          await api.open_drive(letter)

        }

      } catch (err) {

        console.error("[RealApi] Open drive error:", err)

      }

    },



    async openLogFile() {

      try {

        const api = await getPyApi()

        if (api && api.open_log_file) {

          await api.open_log_file()

        }

      } catch (err) {

        console.error("[RealApi] Open log file error:", err)

      }

    },



    async openLogFolder() {

      try {

        const api = await getPyApi()

        if (api && api.open_log_folder) {

          await api.open_log_folder()

        }

      } catch (err) {

        console.error("[RealApi] Open log folder error:", err)

      }

    },

    async copyLogToClipboard() {
      try {
        const api = await getPyApi()
        if (api && api.copy_log) {
          const res = await api.copy_log()
          if (res?.log && typeof navigator !== "undefined" && navigator.clipboard) {
            try {
              await navigator.clipboard.writeText(res.log)
            } catch {}
          }
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] Copy log error:", err)
      }
      return { success: false }
    },

    async saveLogToFile() {
      try {
        const api = await getPyApi()
        if (api && api.save_log_as) {
          const res = await api.save_log_as()
          return res || { success: false }
        }
      } catch (err) {
        console.error("[RealApi] Save log error:", err)
      }
      return { success: false }
    },

    async getLogDirectory() {
      try {
        const api = await getPyApi()
        if (api && api.get_log_directory) {
          const res = await api.get_log_directory()
          if (res) return res
        }
      } catch (err) {
        console.error("[RealApi] Get log directory error:", err)
      }
      return { logDirectory: "", defaultDirectory: "", isCustom: false }
    },

    async chooseLogFolder() {
      try {
        const api = await getPyApi()
        if (api && api.choose_log_folder) {
          const res = await api.choose_log_folder()
          return res || { success: false }
        }
      } catch (err) {
        console.error("[RealApi] Choose log folder error:", err)
      }
      return { success: false, error: "Gagal memilih folder log" }
    },

    async resetLogDirectory() {
      try {
        const api = await getPyApi()
        if (api && api.reset_log_directory) {
          const res = await api.reset_log_directory()
          return res || { success: false }
        }
      } catch (err) {
        console.error("[RealApi] Reset log directory error:", err)
      }
      return { success: false, error: "Gagal me-reset folder log" }
    },



    async getServerDetails() {

      try {

        const api = await getPyApi()

        if (api && api.get_server_details) {

          const details = await api.get_server_details()

          if (details) {
            return {
              ...details,
              isAdmin: Boolean(details.isAdmin || currentMetrics.isAdmin),
              appVersion: details.appVersion || APP_VERSION,
              appChannel: details.appChannel || APP_CHANNEL,
            }
          }

        }

      } catch (err) {

        console.warn("[RealApi] Get server details error:", err)

      }

      return {

        serverName: "Menghubungkan...",

        activeRoute: "auto",

        routes: [],

        activeProfile: "–",

        profiles: [],

        uptimeStr: "–",

        isAdmin: false,
        appVersion: APP_VERSION,
        appChannel: APP_CHANNEL,

      }

    },



    async switchRoute(routeId: string) {
      currentMetrics = {
        ...currentMetrics,
        speedDownBps: 0,
        speedUpBps: 0,
        speedDownStr: "0 B/s",
        speedUpStr: "0 B/s",
      }
      notifyMetrics(currentMetrics)
      try {
        const api = await getPyApi()
        if (api && api.switch_route) {
          const res = await api.switch_route(routeId)
          triggerPollNow()
          if (res) return res
        }
      } catch (err) {
        console.error("[RealApi] Switch route error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal mengalihkan rute koneksi.")
      }
      triggerPollNow()
      return this.getServerDetails()
    },

    async switchProfile(profileName: string) {
      try {
        const api = await getPyApi()
        if (api && api.switch_profile) {
          const res = await api.switch_profile(profileName)
          triggerPollNow()
          if (res) return res
        }
      } catch (err) {
        console.error("[RealApi] Switch profile error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal mengganti profil akun.")
      }
      triggerPollNow()
      return this.getServerDetails()
    },



    async listWebApps(): Promise<WebApp[]> {

      try {

        const api = await getPyApi()

        if (api && api.list_web_apps) {

          const list = await api.list_web_apps()

          if (Array.isArray(list)) return list

        }

      } catch (err) {

        console.warn("[RealApi] List web apps error:", err)

      }

      return []

    },



    async addWebApp(name: string, url: string): Promise<WebApp[]> {

      try {

        const api = await getPyApi()

        if (api && api.add_web_app) {

          const list = await api.add_web_app({ name, url, args: [name, url] })

          if (Array.isArray(list)) return list

        }

      } catch (err) {

        console.error("[RealApi] Add web app error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal menambahkan Web App.")

      }

      return this.listWebApps()

    },



    async deleteWebApp(appId: string): Promise<WebApp[]> {

      try {

        const api = await getPyApi()

        if (api && api.delete_web_app) {

          const list = await api.delete_web_app(appId)

          if (Array.isArray(list)) return list

        }

      } catch (err) {

        console.error("[RealApi] Delete web app error:", err)

        throw new Error(err instanceof Error ? err.message : "Gagal menghapus Web App.")

      }

      return this.listWebApps()

    },



    async switchServer(serverId: string): Promise<ServerDetails> {
      try {
        const api = await getPyApi()
        if (api && api.switch_server) {
          const res = await api.switch_server(serverId)
          triggerPollNow()
          if (res) return res
        }
      } catch (err) {
        console.error("[RealApi] Switch server error:", err)
      }
      triggerPollNow()
      return this.getServerDetails()
    },



    async saveRoute(data: { serverId?: string; id?: string; name: string; url: string }): Promise<any> {
      try {
        const api = await getPyApi()
        if (api && api.save_route) return await api.save_route(data)
        return { success: false, message: "API tidak tersedia" }
      } catch (err: any) {
        return { success: false, message: err?.message || String(err) }
      }
    },

    async removeRoute(data: { serverId?: string; id?: string; routeId?: string }): Promise<any> {
      try {
        const api = await getPyApi()
        if (api && api.remove_route) return await api.remove_route(data)
        return { success: false, message: "API tidak tersedia" }
      } catch (err: any) {
        return { success: false, message: err?.message || String(err) }
      }
    },

    async saveProfile(data: { serverId?: string; profileName: string; username?: string; password?: string; oldProfileName?: string }): Promise<any> {
      try {
        const api = await getPyApi()
        if (api && api.save_profile) return await api.save_profile(data)
        return { success: false, message: "API tidak tersedia" }
      } catch (err: any) {
        return { success: false, message: err?.message || String(err) }
      }
    },

    async removeProfile(data: { serverId?: string; profileName: string }): Promise<any> {
      try {
        const api = await getPyApi()
        if (api && api.remove_profile) return await api.remove_profile(data)
        return { success: false, message: "API tidak tersedia" }
      } catch (err: any) {
        return { success: false, message: err?.message || String(err) }
      }
    },

    async saveServer(data: { id?: string; name: string; url: string; username?: string; password?: string; zerotierNetworkId?: string; zerotierVirtualIp?: string }): Promise<any> {
      try {
        const api = await getPyApi()
        if (api && api.save_server) return await api.save_server(data)
        return { success: false, message: "API tidak tersedia" }
      } catch (err: any) {
        return { success: false, message: err?.message || String(err) }
      }
    },

    async removeServer(data: { id?: string; serverId?: string }): Promise<any> {
      try {
        const api = await getPyApi()
        if (api && api.remove_server) return await api.remove_server(data)
        return { success: false, message: "API tidak tersedia" }
      } catch (err: any) {
        return { success: false, message: err?.message || String(err) }
      }
    },

    async joinZeroTierNetwork(networkId: string): Promise<any> {
      try {
        const api = await getPyApi()
        if (api && api.join_zerotier_network) return await api.join_zerotier_network({ networkId })
        return { success: false, message: "API tidak tersedia" }
      } catch (err: any) {
        return { success: false, message: err?.message || String(err) }
      }
    },

    async leaveZeroTierNetwork(networkId: string): Promise<any> {
      try {
        const api = await getPyApi()
        if (api && api.leave_zerotier_network) return await api.leave_zerotier_network({ networkId })
        return { success: false, message: "API tidak tersedia" }
      } catch (err: any) {
        return { success: false, message: err?.message || String(err) }
      }
    },

        async addServer(): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.add_server) await api.add_server()

      } catch (err) {

        console.error("[RealApi] Add server error:", err)

      }

    },



    async editServer(serverId: string): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.edit_server) await api.edit_server(serverId)

      } catch (err) {

        console.error("[RealApi] Edit server error:", err)

      }

    },



    async deleteServer(serverId: string): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.delete_server) await api.delete_server(serverId)

      } catch (err) {

        console.error("[RealApi] Delete server error:", err)

      }

    },



    async addRoute(): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.add_route) await api.add_route()

      } catch (err) {

        console.error("[RealApi] Add route error:", err)

      }

    },



    async editRoute(routeId: string): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.edit_route) await api.edit_route(routeId)

      } catch (err) {

        console.error("[RealApi] Edit route error:", err)

      }

    },



    async deleteRoute(routeId: string): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.delete_route) await api.delete_route(routeId)

      } catch (err) {

        console.error("[RealApi] Delete route error:", err)

      }

    },



    async addProfile(): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.add_profile) await api.add_profile()

      } catch (err) {

        console.error("[RealApi] Add profile error:", err)

      }

    },



    async editProfile(profileName: string): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.edit_profile) await api.edit_profile(profileName)

      } catch (err) {

        console.error("[RealApi] Edit profile error:", err)

      }

    },



    async deleteProfile(profileName: string): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.delete_profile) await api.delete_profile(profileName)

      } catch (err) {

        console.error("[RealApi] Delete profile error:", err)

      }

    },



    async configCredentials(): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.config_credentials) await api.config_credentials()

      } catch (err) {

        console.error("[RealApi] Config credentials error:", err)

      }

    },




    // =========================================================================
    // SYNTCHING & BACKUP FULL IMPLEMENTATION
    // =========================================================================

    async getSyncthingConfig(): Promise<SyncthingConfigData> {
      try {
        const api = await getPyApi()
        if (api && api.get_syncthing_config) {
          const res = await api.get_syncthing_config()
          if (res && res.server) return res
        }
      } catch (err) {
        console.warn("[RealApi] getSyncthingConfig error:", err)
      }
      return this.getSyncthingApiKeys()
    },

    async saveSyncthingServerRoute(payload: any) {
      try {
        const api = await getPyApi()
        if (api && api.save_syncthing_server_route) {
          const res = await api.save_syncthing_server_route(payload)
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] saveSyncthingServerRoute error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal menyimpan rute server.")
      }
      return { success: true }
    },

    async saveSyncthingLocalConfig(payload: any) {
      try {
        const api = await getPyApi()
        if (api && api.save_syncthing_local_config) {
          const res = await api.save_syncthing_local_config(payload)
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] saveSyncthingLocalConfig error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal menyimpan konfigurasi lokal.")
      }
      return { success: true }
    },

    async testSyncthingTarget(url: string, use_https?: boolean) {
      try {
        const api = await getPyApi()
        if (api && api.test_syncthing_target) {
          const res = await api.test_syncthing_target({ url, use_https })
          if (res) return res
        }
      } catch (err) {
        console.warn("[RealApi] testSyncthingTarget error:", err)
      }
      return { success: false, online: false, latency_ms: 0, message: "Koneksi gagal" }
    },

    async getSyncthingApiKeys(): Promise<SyncthingConfigData> {
      try {
        const api = await getPyApi()
        if (api && api.get_syncthing_api_keys) {
          const res = await api.get_syncthing_api_keys()
          if (res && res.local) return res
        }
      } catch (err) {
        console.warn("[RealApi] getSyncthingApiKeys error:", err)
      }
      return {
        local: { port: "8384", api_key: "" },
        server: { server_name: "Server", port: "8384", api_key: "" }
      }
    },

    async saveSyncthingApiKeys(payload: {
      target?: "local" | "server" | "both"
      local_port?: string
      local_api_key?: string
      server_port?: string
      server_api_key?: string
    }) {
      try {
        const api = await getPyApi()
        if (api && api.save_syncthing_api_keys) {
          const res = await api.save_syncthing_api_keys(payload)
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] saveSyncthingApiKeys error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal menyimpan konfigurasi API Key.")
      }
      return { success: true }
    },

    async dialogConfigureLocalSyncthing() {
      try {
        const api = await getPyApi()
        if (api && api.dialog_configure_local_syncthing) {
          const res = await api.dialog_configure_local_syncthing()
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] dialogConfigureLocalSyncthing error:", err)
      }
      return { success: true }
    },

    async dialogConfigureServerSyncthing() {
      try {
        const api = await getPyApi()
        if (api && api.dialog_configure_server_syncthing) {
          const res = await api.dialog_configure_server_syncthing()
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] dialogConfigureServerSyncthing error:", err)
      }
      return { success: true }
    },

    async getSyncthingFullStatus(): Promise<SyncthingFullStatus> {
      try {
        const api = await getPyApi()
        if (api && api.get_syncthing_full_status) {
          const res = await api.get_syncthing_full_status()
          if (res && res.local) return res
        }
      } catch (err) {
        console.warn("[RealApi] getSyncthingFullStatus error:", err)
      }
      return {
        local: {
          online: false,
          device_id: "",
          devices: [],
          folders: [],
          pending_devices: {},
          metrics: { active: false, direction: "none", percentage: 100, completed_files: 0, total_files: 0, errors: 0, in_speed: "0 B/s", out_speed: "0 B/s", state: "Idle" }
        },
        server: {
          online: false,
          device_id: "",
          devices: [],
          folders: [],
          pending_devices: {},
          metrics: { active: false, direction: "none", percentage: 100, completed_files: 0, total_files: 0, errors: 0, in_speed: "0 B/s", out_speed: "0 B/s", state: "Idle" }
        },
        daemon: { running: false, port: "8384", has_binary: false, binary_path: "" },
        paired: false,
        last_update: 0
      }
    },

    async pairLaptopAndServer(): Promise<{ success: boolean; local_id?: string; server_id?: string; error?: string }> {
      try {
        const api = await getPyApi()
        if (api && api.pair_laptop_and_server) {
          const res = await api.pair_laptop_and_server()
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] pairLaptopAndServer error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal menghubungkan laptop dan server.")
      }
      return { success: false, error: "Backend API tidak tersedia" }
    },

    async getSyncthingTasks(): Promise<SyncthingFolderTask[]> {
      try {
        const api = await getPyApi()
        if (api && api.get_syncthing_tasks) {
          const res = await api.get_syncthing_tasks()
          if (Array.isArray(res)) return res
        }
      } catch (err) {
        console.warn("[RealApi] getSyncthingTasks error:", err)
      }
      return []
    },

    async chooseFolder(title?: string) {
      try {
        const api = await getPyApi()
        if (api && api.choose_folder) {
          const res = await api.choose_folder({ title: title || "" })
          return res || { success: true, path: "" }
        }
      } catch (err) {
        console.warn("[RealApi] chooseFolder error:", err)
      }
      return { success: false, path: "" }
    },

    async createSyncTask(payload?: { folder_path?: string; task_label?: string; server_path?: string; sync_mode?: string; target_server_id?: string }) {
      try {
        const api = await getPyApi()
        if (api && api.create_sync_task) {
          const res = await api.create_sync_task(payload || {})
          return res || { success: true }
        }
      } catch (err: any) {
        console.error("[RealApi] createSyncTask error:", err)
        const msg = typeof err === "string" ? err : (err?.message || "Gagal membuat jalur backup.")
        return { success: false, error: msg }
      }
      return { success: false, error: "Backend API tidak tersedia" }
    },

    async deleteSyncTask(folderId: string) {
      try {
        const api = await getPyApi()
        if (api && api.delete_sync_task) {
          const res = await api.delete_sync_task({ folder_id: folderId })
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] deleteSyncTask error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal menghapus jalur backup.")
      }
      return { success: true }
    },

    async setTaskPaused(folderId: string, paused: boolean) {
      try {
        const api = await getPyApi()
        if (api && api.set_task_paused) {
          const res = await api.set_task_paused({ folder_id: folderId, paused })
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] setTaskPaused error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal mengubah status pause.")
      }
      return { success: true }
    },

    async rescanTask(folderId?: string) {
      try {
        const api = await getPyApi()
        if (api && api.rescan_task) {
          const res = await api.rescan_task({ folder_id: folderId || "" })
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] rescanTask error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal memindai folder.")
      }
      return { success: true }
    },

    async openTaskFolder(pathOrId: string) {
      try {
        const api = await getPyApi()
        if (api && api.open_task_folder) {
          const res = await api.open_task_folder({ path: pathOrId, folder_id: pathOrId })
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] openTaskFolder error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal membuka folder di File Explorer.")
      }
      return { success: true }
    },

    async getMyDeviceIds() {
      try {
        const api = await getPyApi()
        if (api && api.get_my_device_ids) {
          const res = await api.get_my_device_ids()
          if (res) return res
        }
      } catch (err) {
        console.warn("[RealApi] getMyDeviceIds error:", err)
      }
      return { local_id: "", server_id: "" }
    },

    async addSyncthingDevice(deviceId: string, name: string, target?: "local" | "server" | "both") {
      try {
        const api = await getPyApi()
        if (api && api.add_syncthing_device) {
          const res = await api.add_syncthing_device({ device_id: deviceId, name, target: target || "local" })
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] addSyncthingDevice error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal menambahkan perangkat.")
      }
      return { success: true }
    },

    async removeSyncthingDevice(deviceId: string, target?: "local" | "server" | "both") {
      try {
        const api = await getPyApi()
        if (api && api.remove_syncthing_device) {
          const res = await api.remove_syncthing_device({ device_id: deviceId, target: target || "local" })
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] removeSyncthingDevice error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal menghapus perangkat.")
      }
      return { success: true }
    },

    async setDevicePaused(deviceId: string, paused: boolean, target?: "local" | "server" | "both") {
      try {
        const api = await getPyApi()
        if (api && api.set_device_paused) {
          const res = await api.set_device_paused({ device_id: deviceId, paused, target: target || "local" })
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] setDevicePaused error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal mengubah status jeda perangkat.")
      }
      return { success: true }
    },

    async resolvePendingDevice(deviceId: string, action: "accept" | "reject", target?: "local" | "server", name?: string) {
      try {
        const api = await getPyApi()
        if (api && api.resolve_pending_device) {
          const res = await api.resolve_pending_device({ device_id: deviceId, action, target: target || "local", name: name || "" })
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] resolvePendingDevice error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal memproses permintaan koneksi.")
      }
      return { success: true }
    },

    async toggleLocalSyncthingDaemon(action?: "start" | "stop" | "toggle") {
      try {
        const api = await getPyApi()
        if (api && api.toggle_local_syncthing_daemon) {
          const res = await api.toggle_local_syncthing_daemon({ action: action || "toggle" })
          return res || { success: true, running: true }
        }
      } catch (err) {
        console.error("[RealApi] toggleLocalSyncthingDaemon error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal mengontrol daemon Syncthing.")
      }
      return { success: true, running: true }
    },

    async openSyncthingWebGui(target?: "local" | "server") {
      try {
        const api = await getPyApi()
        if (api && api.open_syncthing_web_gui) {
          const res = await api.open_syncthing_web_gui({ target: target || "server" })
          return res || { success: true, url: "" }
        }
      } catch (err) {
        console.error("[RealApi] openSyncthingWebGui error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal membuka Web GUI Syncthing.")
      }
      return { success: true, url: "" }
    },

    async executeBackupDialog(targetFile?: string) {
      try {
        const api = await getPyApi()
        if (api && api.execute_backup_dialog) {
          const res = await api.execute_backup_dialog({ target_file: targetFile || "" })
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] executeBackupDialog error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal menjalankan backup data.")
      }
      return { success: true }
    },

    async executeRestoreDialog(targetFile?: string) {
      try {
        const api = await getPyApi()
        if (api && api.execute_restore_dialog) {
          const res = await api.execute_restore_dialog({ target_file: targetFile || "" })
          return res || { success: true }
        }
      } catch (err) {
        console.error("[RealApi] executeRestoreDialog error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal memulihkan cadangan data.")
      }
      return { success: true }
    },

    async installUpdateFromZip(filePath?: string): Promise<{ success: boolean; cancelled?: boolean; restarting?: boolean; error?: string }> {
      try {
        const api = await getPyApi()
        if (api && api.install_update_from_zip) {
          const res = await api.install_update_from_zip({ filePath: filePath || "" })
          if (res) return res
        }
      } catch (err) {
        console.error("[RealApi] installUpdateFromZip error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal memasang pembaruan dari ZIP.")
      }
      return { success: false, error: "Layanan Core Service tidak merespons." }
    },

    async downloadAndInstallUpdate(downloadUrl?: string): Promise<{ success: boolean; installerLaunched?: boolean; message?: string; error?: string }> {
      try {
        const api = await getPyApi()
        if (api && api.download_and_install_update) {
          const res = await api.download_and_install_update({ downloadUrl: downloadUrl || "" })
          if (res) return res
        }
      } catch (err) {
        console.error("[RealApi] downloadAndInstallUpdate error:", err)
        throw new Error(err instanceof Error ? err.message : "Gagal mengunduh dan memasang pembaruan.")
      }
      return { success: false, error: "Metode pembaruan otomatis tidak tersedia." }
    },

    async joinZeroTier(): Promise<void> {

      try {

        const api = await getPyApi()

        if (api && api.join_zerotier) await api.join_zerotier()

      } catch (err) {

        console.error("[RealApi] Join ZeroTier error:", err)

      }

    },


    async getEasyTierStatus() {
      try {
        const api = await getPyApi()
        if (api) {
          if (typeof api['easytier/status'] === 'function') {
            return await api['easytier/status']({})
          }
          if (typeof api.easytier_status === 'function') {
            return await api.easytier_status({})
          }
        }
      } catch (err) {
        console.warn('[RealApi] getEasyTierStatus error:', err)
      }
      return { running: false, error: 'Unavailable' }
    },

    async startEasyTier(payload: any) {
      try {
        const api = await getPyApi()
        if (api) {
          if (typeof api['easytier/start'] === 'function') {
            return await api['easytier/start'](payload || {})
          }
          if (typeof api.easytier_start === 'function') {
            return await api.easytier_start(payload || {})
          }
        }
      } catch (err) {
        console.error('[RealApi] startEasyTier error:', err)
        throw err
      }
      return { success: false, message: 'Core API unavailable' }
    },

    async stopEasyTier() {
      try {
        const api = await getPyApi()
        if (api) {
          if (typeof api['easytier/stop'] === 'function') {
            return await api['easytier/stop']({})
          }
          if (typeof api.easytier_stop === 'function') {
            return await api.easytier_stop({})
          }
        }
      } catch (err) {
        console.error('[RealApi] stopEasyTier error:', err)
        throw err
      }
      return { success: false, message: 'Core API unavailable' }
    },

    async getRemoteStatus() {
      try {
        const api = await getPyApi()
        if (api) {
          if (typeof api['remote/status'] === 'function') {
            return await api['remote/status']({})
          }
          if (typeof api.remote_status === 'function') {
            return await api.remote_status({})
          }
        }
      } catch (err) {
        console.warn('[RealApi] getRemoteStatus error:', err)
      }
      return { activeEngine: 'none', easytier: { running: false }, zerotier: { running: false } }
    },

    async setRemoteMode(mode: string) {
      try {
        const api = await getPyApi()
        if (api) {
          if (typeof api.set_remote_mode === 'function') {
            return await api.set_remote_mode({ mode })
          }
        }
      } catch (err) {
        console.error('[RealApi] setRemoteMode error:', err)
        throw err
      }
      return { success: false, message: 'Core API unavailable' }
    },
  }

}


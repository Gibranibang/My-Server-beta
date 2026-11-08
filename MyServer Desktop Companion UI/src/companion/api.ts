import type { Drive, Metrics, PowerState, Settings, ServerDetails, WebApp, SyncthingFullStatus, SyncthingFolderTask, SyncthingConfigData } from "./types"

import { APP_VERSION, APP_CHANNEL } from "./version"



/**

 * The only boundary between the UI and the real server/OS.

 * Implement this interface (Tauri invoke, Electron IPC, ZimaOS REST/WebSocket)

 * and register it with `setCompanionApi()` before the app renders.

 * Every method may reject; the UI shows the error message as a danger toast.

 */

export interface CompanionApi {

  /** Push live metrics (about every 1-2 s). Return an unsubscribe function. */

  subscribeMetrics(onMetrics: (metrics: Metrics) => void): () => void

  refreshMetrics?(): Promise<Metrics>

  probeUrl?: (url: string) => Promise<any>

  /** Push every server power-state change (including ones not started by the UI). */

  subscribePower(onPower: (power: PowerState) => void): () => void



  /** Resolves when the command is accepted; progress is reported via subscribePower. */

  reboot(): Promise<void>

  shutdown(): Promise<void>

  /** Send a Wake-on-LAN magic packet (UDP broadcast, port 9) to the MAC address. */

  wakeOnLan(mac: string): Promise<void>

  /** Resolve the MAC address of the server (ARP lookup). */

  detectMac(): Promise<string>

  saveMac(mac: string): Promise<void>



  saveRoute(data: { serverId?: string; id?: string; name: string; url: string }): Promise<{ success: boolean; message?: string }>

  removeRoute(data: { serverId?: string; id?: string; routeId?: string }): Promise<{ success: boolean; message?: string }>

  saveProfile(data: { serverId?: string; profileName: string; username?: string; password?: string; oldProfileName?: string }): Promise<{ success: boolean; message?: string }>

  removeProfile(data: { serverId?: string; profileName: string }): Promise<{ success: boolean; message?: string }>

  saveServer(data: { id?: string; name: string; url: string; username?: string; password?: string; zerotierNetworkId?: string; zerotierVirtualIp?: string }): Promise<{ success: boolean; message?: string }>

  removeServer(data: { id?: string; serverId?: string }): Promise<{ success: boolean; message?: string }>

  joinZeroTierNetwork(networkId: string): Promise<{ success: boolean; message?: string }>

  leaveZeroTierNetwork(networkId: string): Promise<{ success: boolean; message?: string }>



  listDrives(): Promise<Drive[]>

  /** Mount (SMB) or unmount every server share; resolves with the new drive list. */

  setAllMounted(mounted: boolean): Promise<Drive[]>



  loadSettings(): Promise<Settings>

  saveSettings(settings: Settings): Promise<void>



  /** Zip the configuration; resolves with the saved file name. */

  createBackup(): Promise<{ file: string }>

  restoreBackup(): Promise<{ rollbackFile: string }>

  /** Clear the WebView cache; resolves with the freed size in MB. */

  clearCache(): Promise<{ freedMb: number }>

  cleanBrowserCache?(): Promise<{ freedMb: number }>

  getLogDirectory(): Promise<{ logDirectory: string; defaultDirectory: string; isCustom: boolean }>

  chooseLogFolder(): Promise<{ success: boolean; logDirectory?: string; defaultDirectory?: string; isCustom?: boolean; cancelled?: boolean; error?: string }>

  resetLogDirectory(): Promise<{ success: boolean; logDirectory?: string; defaultDirectory?: string; isCustom?: boolean; error?: string }>

  checkForUpdate(): Promise<UpdateInfo>

  installUpdateFromZip(filePath?: string): Promise<{ success: boolean; cancelled?: boolean; restarting?: boolean; error?: string }>

  downloadAndInstallUpdate?(downloadUrl?: string): Promise<{ success: boolean; installerLaunched?: boolean; message?: string; error?: string }>



  /** Number of pending Syncthing device requests. */

  getPendingSyncRequests(): Promise<number>

  acceptSyncRequest(): Promise<void>



  /** Real OS / Native Desktop Actions */

  hideFlyout(): Promise<void>

  minimizeWindow(): Promise<void>

  openUrl(url: string, title?: string): Promise<void>

  openExternalBrowser(url: string): Promise<void>

  openFileManager(): Promise<void>

  openFileExplorer(): Promise<void>

  openZimaFileManager(): Promise<void>

  openPeerDrop(): Promise<void>

  openUnc(): Promise<void>

  openDrive(letter: string): Promise<void>

  openLogFile(): Promise<void>

  openLogFolder(): Promise<void>

  copyLogToClipboard(): Promise<{ success: boolean; log?: string }>

  saveLogToFile(): Promise<{ success: boolean; path?: string; cancelled?: boolean; error?: string }>



  /** Server & Connection Route Management */

  getServerDetails(): Promise<ServerDetails>

  switchRoute(routeId: string): Promise<ServerDetails>

  switchProfile(profileName: string): Promise<ServerDetails>



  /** Web Apps & Docker Services */

  listWebApps(): Promise<WebApp[]>

  addWebApp(name: string, url: string): Promise<WebApp[]>

  deleteWebApp(appId: string): Promise<WebApp[]>



  switchServer(serverId: string): Promise<ServerDetails>

  addServer(): Promise<void>

  editServer(serverId: string): Promise<void>

  deleteServer(serverId: string): Promise<void>



  addRoute(): Promise<void>

  editRoute(routeId: string): Promise<void>

  deleteRoute(routeId: string): Promise<void>



  addProfile(): Promise<void>

  editProfile(profileName: string): Promise<void>

  deleteProfile(profileName: string): Promise<void>



  configCredentials(): Promise<void>

  joinZeroTier(): Promise<void>

  getEasyTierStatus?(): Promise<any>
  startEasyTier?(payload: { remote_id?: string; network_name?: string; network_secret?: string; ipv4?: string; peers?: string[]; use_no_tun?: boolean; external_node?: string }): Promise<any>
  stopEasyTier?(): Promise<any>
  getRemoteStatus?(): Promise<any>
  setRemoteMode?(mode: string): Promise<any>



  /** Full Syncthing & Atomic Backup Operations */

  getSyncthingConfig(): Promise<SyncthingConfigData>

  saveSyncthingServerRoute(payload: {

    route_mode?: string

    lan_mode?: string

    lan_ip?: string

    lan_port?: string

    lan_https?: boolean

    wan_url?: string

    wan_port?: string

    wan_https?: boolean

    api_key?: string

  }): Promise<{ success: boolean }>

  saveSyncthingLocalConfig(payload: {

    port?: string

    api_key?: string

    auto_start?: boolean

    binary_path?: string

  }): Promise<{ success: boolean }>

  testSyncthingTarget(url: string, use_https?: boolean): Promise<{ success: boolean; online: boolean; latency_ms: number; message?: string }>

  getSyncthingApiKeys(): Promise<SyncthingConfigData>

  saveSyncthingApiKeys(payload: {

    target?: "local" | "server" | "both"

    local_port?: string

    local_api_key?: string

    server_port?: string

    server_api_key?: string

  }): Promise<{ success: boolean }>

  dialogConfigureLocalSyncthing(): Promise<{ success: boolean }>

  dialogConfigureServerSyncthing(): Promise<{ success: boolean }>

  getSyncthingFullStatus(): Promise<SyncthingFullStatus>

  pairLaptopAndServer(): Promise<{ success: boolean; local_id?: string; server_id?: string; error?: string }>

  getSyncthingTasks(): Promise<SyncthingFolderTask[]>

  chooseFolder(title?: string): Promise<{ success: boolean; path: string }>

  createSyncTask(payload?: { folder_path?: string; task_label?: string; server_path?: string; sync_mode?: string; target_server_id?: string }): Promise<{ success: boolean; task_id?: string; label?: string; mode?: string; error?: string; cancelled?: boolean }>

  deleteSyncTask(folderId: string): Promise<{ success: boolean }>

  setTaskPaused(folderId: string, paused: boolean): Promise<{ success: boolean }>

  rescanTask(folderId?: string): Promise<{ success: boolean }>

  openTaskFolder(pathOrId: string): Promise<{ success: boolean }>

  getMyDeviceIds(): Promise<{ local_id: string; server_id: string }>

  addSyncthingDevice(deviceId: string, name: string, target?: "local" | "server" | "both"): Promise<{ success: boolean; error?: string }>

  removeSyncthingDevice(deviceId: string, target?: "local" | "server" | "both"): Promise<{ success: boolean }>

  setDevicePaused(deviceId: string, paused: boolean, target?: "local" | "server" | "both"): Promise<{ success: boolean }>

  resolvePendingDevice(deviceId: string, action: "accept" | "reject", target?: "local" | "server", name?: string): Promise<{ success: boolean }>

  toggleLocalSyncthingDaemon(action?: "start" | "stop" | "toggle"): Promise<{ success: boolean; running: boolean }>

  openSyncthingWebGui(target?: "local" | "server"): Promise<{ success: boolean; url: string }>

  executeBackupDialog(targetFile?: string): Promise<{ success: boolean; file?: string; path?: string; cancelled?: boolean; error?: string }>

  executeRestoreDialog(targetFile?: string): Promise<{ success: boolean; rollbackFile?: string; restarting?: boolean; cancelled?: boolean; error?: string }>

}



export interface UpdateInfo {

  upToDate: boolean

  version: string

  currentVersion?: string

  downloadUrl?: string

  htmlUrl?: string

  name?: string

  body?: string

  message?: string

}



const wait = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms))

const clamp = (v: number, min: number, max: number) =>

  Math.min(max, Math.max(min, v))

const drift = (v: number, spread: number, min: number, max: number) =>

  clamp(v + (Math.random() - 0.5) * spread, min, max)

const round1 = (v: number) => Math.round(v * 10) / 10



export let SERVER_IP = "127.0.0.1"

export const setServerIp = (ip: string) => {

  if (ip && ip.trim()) SERVER_IP = ip.trim()

}

export let SERVER_URL = ""

export const setServerUrl = (url: string) => {

  if (url && url.trim()) SERVER_URL = url.trim()

}

export let DEFAULT_MAC = ""

export const setDefaultMac = (mac: string) => {

  if (mac && mac.trim()) DEFAULT_MAC = mac.trim().toUpperCase()

}



export const DEFAULT_SETTINGS: Settings = {

  autostart: true,

  openDashboard: false,

  autoMountSmb: true,

  autoZeroTier: true,

  autoCleanOnExit: true,

  showTraffic: true,

  autoOpenMiniTray: true,

  fileManagerClickTarget: "explorer",

  language: "id",

  theme: "dark",

  autoCheckUpdate: true,

}



const MOCK_DRIVES: Drive[] = [

  {

    letter: "Z",

    name: "DATA",

    free: "1.2 TB",

    total: "2.0 TB",

    usedPct: 40,

    mounted: true,

  },

  {

    letter: "Y",

    name: "Toshiba 1TB",

    free: "450 GB",

    total: "1.0 TB",

    usedPct: 55,

    mounted: true,

  },

]



const isUpMock = typeof window !== "undefined" && window.location.search.includes("net=upload")

const MOCK_METRICS: Metrics = {
  cpu: 34,
  ram: 61,
  hdd: 64,
  lanDown: 4.5,
  lanHistory: [2.1, 3.4, 2.8, 4.9, 3.6, 5.2, 4.1, 6.3, 4.4, 3.9, 5.6, 4.5],
  syncUp: 1.2,
  syncDown: 4.5,
  speedDownBps: isUpMock ? 500000 : 4500000,
  speedUpBps: isUpMock ? 28000000 : 1200000,
  speedDownStr: isUpMock ? "500 KB/s" : "4.5 MB/s",
  speedUpStr: isUpMock ? "28 MB/s" : "1.2 MB/s",
  isLoading: false,
}

/** Simulated backend used for the design preview and as a reference for real implementations. */

export function createMockApi(): CompanionApi {

  const isOfflineMock = typeof window !== "undefined" && (window.location.search.includes("power=offline") || window.location.search.includes("offline=1"))
  let power: PowerState = isOfflineMock ? "offline" : "online"

  let drives = MOCK_DRIVES

  let settings = { ...DEFAULT_SETTINGS }
  if (typeof window !== "undefined") {
    const p = new URLSearchParams(window.location.search)
    if (p.get("theme") === "light" || p.get("theme") === "dark") {
      settings.theme = p.get("theme") as "light" | "dark"
    }
    if (p.get("lang") === "id" || p.get("lang") === "en") {
      settings.language = p.get("lang") as "id" | "en"
    }
  }

  let syncRequests = 1

  let metrics = MOCK_METRICS

  let powerTimer: number | undefined

  const powerListeners = new Set<(p: PowerState) => void>()



  const setPower = (next: PowerState) => {

    power = next

    powerListeners.forEach((fn) => fn(next))

  }

  const transition = (interim: PowerState, ms: number) => {

    window.clearTimeout(powerTimer)

    setPower(interim)

    powerTimer = window.setTimeout(() => setPower("online"), ms)

  }



  return {

    subscribeMetrics(onMetrics) {

      onMetrics(metrics)

      const id = window.setInterval(() => {

        const lanDown = round1(drift(metrics.lanDown, 2.4, 0.6, 9.4))

        metrics = {

          cpu: Math.round(drift(metrics.cpu, 14, 12, 78)),

          ram: Math.round(drift(metrics.ram, 4, 52, 72)),

          hdd: metrics.hdd,

          lanDown,

          lanHistory: [...metrics.lanHistory.slice(1), lanDown],

          syncUp: round1(drift(metrics.syncUp, 0.5, 0.6, 2.2)),

          syncDown: round1(drift(metrics.syncDown, 1.2, 2.8, 6.4)),

        }

        onMetrics(metrics)

      }, 1600)

      return () => window.clearInterval(id)

    },

    subscribePower(onPower) {

      powerListeners.add(onPower)

      onPower(power)

      return () => void powerListeners.delete(onPower)

    },

    async reboot() {

      transition("rebooting", 4200)

    },

    async shutdown() {

      window.clearTimeout(powerTimer)

      setPower("offline")

    },

    async wakeOnLan() {

      if (power === "offline") transition("waking", 4200)

      await wait(1000)

    },

    async detectMac() {

      await wait(1200)

      return "B8:27:EB:3A:91:7C"

    },

    async saveRoute() { return { success: true } },

    async removeRoute() { return { success: true } },

    async saveProfile() { return { success: true } },

    async removeProfile() { return { success: true } },

    async saveServer() { return { success: true } },

    async removeServer() { return { success: true } },

    async joinZeroTierNetwork() { return { success: true } },

    async leaveZeroTierNetwork() { return { success: true } },



    async listDrives() {

      return drives

    },

    async setAllMounted(mounted) {

      await wait(mounted ? 1200 : 900)

      drives = drives.map((d) => ({ ...d, mounted }))

      return drives

    },

    async loadSettings() {

      return settings

    },

    async saveSettings(next) {

      settings = next

    },

    async createBackup() {

      await wait(1400)

      return { file: "myserver-backup.zip" }

    },

    async restoreBackup() {

      await wait(1600)

      return { rollbackFile: "myserver-config.bak" }

    },

    async clearCache() {

      await wait(900)

      return { freedMb: 184 }

    },

    async cleanBrowserCache() {

      return this.clearCache()

    },

    async getLogDirectory() {

      return { logDirectory: "C:\\Users\\gibra\\.myserver\\logs", defaultDirectory: "C:\\Users\\gibra\\.myserver\\logs", isCustom: false }

    },

    async chooseLogFolder() {

      return { success: true, logDirectory: "D:\\Logs", defaultDirectory: "C:\\Users\\gibra\\.myserver\\logs", isCustom: true }

    },

    async resetLogDirectory() {

      return { success: true, logDirectory: "C:\\Users\\gibra\\.myserver\\logs", defaultDirectory: "C:\\Users\\gibra\\.myserver\\logs", isCustom: false }

    },

    async checkForUpdate() {

      await wait(1500)

      return { upToDate: true, version: APP_VERSION }

    },

    async installUpdateFromZip(filePath?: string) {

      await wait(1500)

      return { success: true, restarting: true }

    },

    async downloadAndInstallUpdate(downloadUrl?: string) {

      await wait(1500)

      return { success: true, installerLaunched: true, message: "Installer pembaruan berhasil diluncurkan." }

    },

    async getPendingSyncRequests() {

      return syncRequests

    },

    async acceptSyncRequest() {

      syncRequests = Math.max(0, syncRequests - 1)

    },

    async saveMac(mac) {

      DEFAULT_MAC = mac

    },

    async hideFlyout() {},

    async minimizeWindow() {},

    async openUrl() {},

    async openExternalBrowser() {},

    async openFileManager() {},

    async openFileExplorer() {},

    async openZimaFileManager() {},

    async openPeerDrop() {},

    async openUnc() {},

    async openDrive() {},

    async openLogFile() {},

    async openLogFolder() {},

    async copyLogToClipboard() {

      return { success: true, log: "[Mock] MyServer diagnostic log" }

    },

    async saveLogToFile() {

      return { success: true, path: "C:\\Users\\Desktop\\MyServer_Log.txt" }

    },

    async getServerDetails(): Promise<ServerDetails> {

      return {

        serverId: "stimi",

        serverName: "STIMI-Server",

        servers: [

          { id: "algitha", name: "Algitha-Server" },

          { id: "stimi", name: "STIMI-Server" },

        ],

        activeRoute: "conn_auto",

        routes: [

          { id: "conn_lan", name: "Local / Primary", url: "http://stimiserver.algitha.my.id", active: true, pingMs: 287 },

          { id: "conn_ip", name: "IP Local", url: "http://192.168.1.6", active: false, pingMs: 2 },

          { id: "conn_zt", name: "ZeroTier Remote (P2P)", url: "http://172.24.0.1", active: false, isZeroTier: true, pingMs: 18 },

        ],

        zeroTier: {
          running: true,
          networkStatus: "OK",
          networkName: "IceWhale-RemoteAccess",
          configuredNwid: "2be7ac7a591b7bc8",
          nodeId: "e642c82437",
          virtualIp: "172.24.236.144",
          serverVirtualIp: "172.24.0.1",
          joined: true,
        },
        easyTier: {
          running: true,
          available: true,
          remote_id: "2be7ac7a591b7bc8",
          network_name: "zima-2be7ac7a591b7bc8",
          virtual_ipv4: null,
          virtual_ip: null,
          uptime: 120,
          peers_count: 3,
        },

        activeProfile: "Marcom",

        profiles: ["Admin", "Marcom", "Keuangan"],

        uptimeStr: "2d 4h",

        isAdmin: false,

        accountStatus: {

          accessDescription: "Standard User (Samba Access Only)",

        },

        appVersion: APP_VERSION,

        appChannel: APP_CHANNEL,

      }

    },

    async switchRoute(routeId) {

      return this.getServerDetails()

    },

    async switchProfile(profileName) {

      return this.getServerDetails()

    },

    async listWebApps(): Promise<WebApp[]> {

      return [

        { id: "app_1", name: "Jellyfin", url: "http://192.168.1.50:8096", port: "8096" },

        { id: "app_2", name: "Nextcloud", url: "http://192.168.1.50:8081", port: "8081" },

      ]

    },

    async addWebApp(name: string, url: string): Promise<WebApp[]> {

      return this.listWebApps()

    },

    async deleteWebApp(appId: string): Promise<WebApp[]> {

      return this.listWebApps()

    },

    async switchServer(serverId: string): Promise<ServerDetails> {

      return this.getServerDetails()

    },

    async addServer(): Promise<void> {},

    async editServer(serverId: string): Promise<void> {},

    async deleteServer(serverId: string): Promise<void> {},

    async addRoute(): Promise<void> {},

    async editRoute(routeId: string): Promise<void> {},

    async deleteRoute(routeId: string): Promise<void> {},

    async addProfile(): Promise<void> {},

    async editProfile(profileName: string): Promise<void> {},

    async deleteProfile(profileName: string): Promise<void> {},

    async configCredentials(): Promise<void> {},

    async joinZeroTier(): Promise<void> {},

    async getEasyTierStatus() {
      return {
        running: true,
        version: "2.6.4-8428a89d",
        network_name: "myserver-mesh",
        virtual_ip: "10.144.144.12",
        peer_id: 12345678,
        peers_count: 2,
        direct_peers: 1,
        relay_peers: 1,
        peers: [
          { id: "1001", hostname: "Ubuntu-Server", ipv4: "10.144.144.1", cost: "Direct", lat_ms: "8ms", rx_bytes: "1.2 MB", tx_bytes: "450 KB", tunnel_proto: "udp", nat_type: "Cone" }
        ],
        routes: [],
        error: null,
      }
    },
    async startEasyTier(payload: any) {
      return { success: true, message: "EasyTier mesh connected", status: { running: true, network_name: payload?.network_name || "myserver-mesh" } }
    },
    async stopEasyTier() {
      return { success: true, message: "EasyTier disconnected", status: { running: false } }
    },
    async getRemoteStatus() {
      return {
        activeEngine: "easytier",
        easytier: { running: true, network_name: "myserver-mesh", virtual_ip: "10.144.144.12" },
        zerotier: { running: false, nodeId: "", version: "", networks: [] }
      }
    },



    async getSyncthingConfig(): Promise<SyncthingConfigData> {

      return {

        local: { port: "8384", api_key: "MOCK_LOCAL_KEY", auto_start: true },

        server: { server_name: "MockServer", port: "8384", api_key: "MOCK_SERVER_KEY", route_mode: "auto" }

      }

    },

    async saveSyncthingServerRoute() { return { success: true } },

    async saveSyncthingLocalConfig() { return { success: true } },

    async testSyncthingTarget() { return { success: true, online: true, latency_ms: 45, message: "Online (45ms)" } },

    async getSyncthingApiKeys(): Promise<SyncthingConfigData> {

      return {

        local: { port: "8384", api_key: "MOCK_LOCAL_KEY" },

        server: { server_name: "MockServer", port: "8384", api_key: "MOCK_SERVER_KEY" }

      }

    },

    async saveSyncthingApiKeys() { return { success: true } },

    async dialogConfigureLocalSyncthing() { return { success: true } },

    async dialogConfigureServerSyncthing() { return { success: true } },

    async getSyncthingFullStatus(): Promise<SyncthingFullStatus> {

      return {

        local: {

          online: true,

          device_id: "D7FJ5II-44QVMU3-TAZK4UB-FOE5HFK-UX4LKO2-ON7AOWR-RXQQKJY-7VTQQAP",

          devices: [],

          folders: [],

          pending_devices: {},

          metrics: { active: false, direction: "none", percentage: 100, completed_files: 10, total_files: 10, errors: 0, in_speed: "0 B/s", out_speed: "0 B/s", state: "Idle" }

        },

        server: {

          online: true,

          device_id: "SRV7Q2K-Z4NDA5L-J3PXHQ8-RTE2B6V-UC9MYF1-GKS4N3D-7XWAQZ5-PLR8XYZ",

          devices: [],

          folders: [],

          pending_devices: {},

          metrics: { active: false, direction: "none", percentage: 100, completed_files: 10, total_files: 10, errors: 0, in_speed: "0 B/s", out_speed: "0 B/s", state: "Idle" }

        },

        daemon: { running: true, port: "8384", has_binary: true, binary_path: "syncthing.exe" },

        paired: true,

        last_update: Date.now()

      }

    },

    async pairLaptopAndServer() { return { success: true } },

    async getSyncthingTasks(): Promise<SyncthingFolderTask[]> {

      return [

        {

          id: "task-dokumen-kerja-101",

          label: "Dokumen Kerja",

          localPath: "D:/Data Kerja/Dokumen",

          serverPath: "/DATA/Backups/Dokumen",

          type: "sendonly",

          paused: false,

          completion: 100,

          needFiles: 0,

          needBytes: 0,

          owner: "Admin",

          existsOnServer: true,

          isActiveServer: true,

          targetServerName: "Server Utama"
        },
        {
          id: "task-capcut-project-102",
          label: "CapCut Project",
          localPath: "D:/Capcut Project",
          serverPath: "/disk_gibran1/Disk D/CapCut Project",
          type: "sendreceive",
          paused: false,
          completion: 100,
          needFiles: 0,
          needBytes: 0,
          owner: "Admin",
          existsOnServer: true,
          isActiveServer: true,
          targetServerName: "Server Utama"
        }

      ]

    },

    async chooseFolder() { return { success: true, path: "D:/Documents/Work" } },

    async createSyncTask() { return { success: true, task_id: "task-mock-1" } },

    async deleteSyncTask() { return { success: true } },

    async setTaskPaused() { return { success: true } },

    async rescanTask() { return { success: true } },

    async openTaskFolder() { return { success: true } },

    async getMyDeviceIds() { return { local_id: "LOCAL-ID", server_id: "SERVER-ID" } },

    async addSyncthingDevice() { return { success: true } },

    async removeSyncthingDevice() { return { success: true } },

    async setDevicePaused() { return { success: true } },

    async resolvePendingDevice() { return { success: true } },

    async toggleLocalSyncthingDaemon() { return { success: true, running: true } },

    async openSyncthingWebGui() { return { success: true, url: "http://127.0.0.1:8384" } },

    async executeBackupDialog() { return { success: true, file: "myserver-backup.zip" } },

    async executeRestoreDialog() { return { success: true, rollbackFile: "config.json.bak" } }

  }

}



let current: CompanionApi = createMockApi()



export const getCompanionApi = () => current

/** Call once at startup (before render) to replace the mock with a real backend. */

export const setCompanionApi = (api: CompanionApi) => {

  current = api

}


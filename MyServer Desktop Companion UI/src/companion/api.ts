import type {
  Drive,
  Metrics,
  PowerState,
  Settings,
  ServerDetails,
  WebApp,
  SyncthingFullStatus,
  SyncthingFolderTask,
  SyncthingConfigData,
  VirtualMachine,
  WizardVerifyZimaResponse,
  WizardCommitServerPayload,
  WizardCommitServerResult,
  BackendDeploySource,
  BackendActionResult,
  SyncthingAutoDetectResult,
  FileManagerSourceStatus,
  FileManagerSourcePayload,
  ExplorerOpenResult,
  ShareTargetInfo,
  ShareResolveResult,
  PublicShareItem,
  ShareListResponse,
  ShareCreatePayload,
  ShareCreateResult,
  QuickShareResult,
  ShareSettingsResult,
  ShareRevokeResult,
  ExplorerContextMenuResult,
  PublicShareRole,
  InternalShareRole,
  ShareAccountCandidate,
  ShareAccountCandidatesResponse,
  AccountShareItem,
  AccountShareListResponse,
  AccountShareMutateResult,
  ExplorerClipboardItem,
  ExplorerClipboardState,
  TransferWindowMode,
  TransferConflictAction,
  TransferStatusResponse,
  QuickPickerBrowseResponse,
  TransferPastePayload,
  QuickPickerEntry,
  TransferQueueItem,
} from "./types"

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

  probeUrl?: (url: string) => Promise<{ reachable: boolean; latency_ms?: number; status?: number; url?: string; error?: string }>

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

  hideWindow(): Promise<void>

  startDrag(): Promise<void>

  setWizardMode(active: boolean, width?: number, height?: number): Promise<void>

  minimizeWindow(): Promise<void>

  openUrl(url: string, title?: string): Promise<void>

  openExternalBrowser(url: string): Promise<void>

  syncInstaBoxVm(params: { apiKey: string; machineId?: string; vmName?: string; vmId?: string; scope?: "server" | "local"; serverId?: string }): Promise<any>

  smartResetInstaBox(params: { apiKey?: string; machineId?: string; vmId?: string; scope?: "server" | "local"; serverId?: string }): Promise<any>

  wakeInstaBoxVm(params: { apiKey?: string; machineId?: string; vmId?: string; scope?: "server" | "local"; serverId?: string }): Promise<any>

  pauseInstaBoxVm(params: { apiKey?: string; machineId?: string; vmId?: string; scope?: "server" | "local"; serverId?: string }): Promise<any>

  loadVms?(): Promise<VirtualMachine[]>

  saveVms?(vms: VirtualMachine[]): Promise<any>

  updateVm?(vmId: string, updates: Partial<VirtualMachine>, serverId?: string): Promise<any>

  deleteVm?(vmId: string, scope?: string, serverId?: string): Promise<any>

  migrateVm?(vmId: string, targetScope: "server" | "local", vm?: Partial<VirtualMachine>): Promise<any>

  openSshTerminal?(params?: { host?: string; user?: string; port?: number; serverId?: string; saveSshUser?: boolean }): Promise<any>

  openVmWindow?(vmId: string, title: string, url: string): Promise<void>

  openFileManager(): Promise<ExplorerOpenResult | void>

  openFileExplorer(): Promise<ExplorerOpenResult | void>

  openZimaFileManager(): Promise<void>

  openBackendFileManager?(): Promise<{ success: boolean; url?: string; error?: string } | void>

  getFileManagerSource?(): Promise<FileManagerSourceStatus>

  configureFileManagerSource?(payload: FileManagerSourcePayload): Promise<FileManagerSourceStatus>

  openPeerDrop(): Promise<void>

  openUnc(): Promise<ExplorerOpenResult | void>

  openDrive(letter: string): Promise<ExplorerOpenResult | void>

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

    remote_ip?: string

    remote_port?: string

    remote_https?: boolean

    wan_url?: string

    wan_port?: string

    wan_https?: boolean

    api_key?: string

  }): Promise<{ success: boolean }>

  detectLocalSyncthing(): Promise<SyncthingAutoDetectResult>

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

  triggerBackendAction?(
    action: "install" | "update",
    serverId?: string,
    options?: {
      source?: BackendDeploySource
      sshHost?: string
      sshPort?: number
      sshUser?: string
      sshPassword?: string
    },
  ): Promise<BackendActionResult>

  getBackendStatus?(serverId?: string): Promise<{ online: boolean; version?: string; latestVersion?: string; url?: string }>

  verifyZimaLogin(payload: {
    url?: string
    remoteId?: string
    wanUrl?: string
    username: string
    password: string
  }): Promise<WizardVerifyZimaResponse>

  commitWizardServer(payload: WizardCommitServerPayload): Promise<WizardCommitServerResult>

  completeWizard(): Promise<{ success: boolean; firstRunSetup?: boolean; message?: string; error?: string }>

  /** Phase 11: Windows File Explorer Native Share & Quick Share */
  resolveSharePath(path: string): Promise<ShareResolveResult>

  listShares(opts?: { serverId?: string; targetPath?: string }): Promise<ShareListResponse>

  createShare(payload: ShareCreatePayload): Promise<ShareCreateResult>

  quickSharePath(path: string): Promise<QuickShareResult>

  revokeShare(token: string, serverId?: string): Promise<ShareRevokeResult>

  updateShareSettings(publicBaseUrl: string, serverId?: string): Promise<ShareSettingsResult>

  copyShareClipboard(text: string): Promise<boolean>

  setExplorerContextMenuEnabled(enabled: boolean): Promise<ExplorerContextMenuResult>

  openShareWindow(target: ShareTargetInfo): Promise<void>

  closeShareWindow(): Promise<void>

  getShareWindowTarget(): Promise<ShareTargetInfo | null>

  /** Phase 12: Internal Backend Account Sharing */
  listShareAccountCandidates(serverId?: string): Promise<ShareAccountCandidatesResponse>

  listAccountShares(targetPath: string, serverId?: string): Promise<AccountShareListResponse>

  grantAccountShare(payload: {
    targetPath: string
    granteeUsername: string
    role: InternalShareRole
    serverId?: string
  }): Promise<AccountShareMutateResult>

  updateAccountShareRole(
    grantId: number,
    role: InternalShareRole,
    serverId?: string
  ): Promise<AccountShareMutateResult>

  revokeAccountShare(grantId: number, serverId?: string): Promise<AccountShareMutateResult>

  /** Phase 13: Windows Explorer HTTP Copy-Paste & Floating Transfer Window */
  getExplorerClipboard(): Promise<ExplorerClipboardState>

  copyServerItemsToClipboard(payload: {
    serverId?: string
    items: ExplorerClipboardItem[]
  }): Promise<{ success: boolean; clipboard?: ExplorerClipboardState; error?: string }>

  clearExplorerClipboard(): Promise<{ success: boolean }>

  browseTransferDirectory(opts?: {
    serverId?: string
    server_id?: string
    path?: string
    source?: "disks" | "shared"
  }): Promise<QuickPickerBrowseResponse>

  startTransferPaste(payload: TransferPastePayload): Promise<TransferStatusResponse>

  getTransferStatus(): Promise<TransferStatusResponse>

  resolveTransferConflict(payload: {
    jobId: string
    action: TransferConflictAction
    applyToAll?: boolean
  }): Promise<TransferStatusResponse>

  pauseTransferJob(jobId?: string): Promise<TransferStatusResponse>

  resumeTransferJob(jobId?: string): Promise<TransferStatusResponse>

  cancelTransferJob(jobId?: string): Promise<TransferStatusResponse>

  clearTransferHistory(): Promise<{ success: boolean }>

  setExplorerHotkeyEnabled(enabled: boolean): Promise<{ success: boolean; enabled: boolean; error?: string }>

  openTransferWindow(initialState?: { mode?: TransferWindowMode; [key: string]: unknown }): Promise<void>

  closeTransferWindow(): Promise<void>

  getTransferWindowState(): Promise<Record<string, unknown> | null>

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

  explorerContextMenuEnabled: false,

  explorerHotkeyEnabled: true,

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

  let mockSmbSource: FileManagerSourceStatus = {
    success: true,
    source: "zimaos",
    hasCredentials: false,
    backendOnline: true,
    smbMode: "zimaos",
    needsAuth: false,
  }

  let mockPublicBaseUrl = "https://nas.example.com"
  const mockIsAdmin = true
  let mockShareCounter = 1
  let mockShareTarget: ShareTargetInfo | null =
    typeof window !== "undefined" && window.location.search.includes("window=share")
      ? {
          server_id: "srv_mock_1",
          server_name: "Server Utama",
          disk_name: "DATA",
          share_name: "DATA",
          canonical_rel: "DATA/Documents/Report.pdf",
          basename: "Report.pdf",
          is_dir: false,
          is_admin: true,
          backend_url: "http://192.0.2.10:8085",
          smb_source: "zimaos",
        }
      : null
  let mockShares: PublicShareItem[] = [
    {
      token: "demo1234",
      target_path: "DATA/Documents/Report.pdf",
      is_dir: false,
      label: "Report.pdf",
      share_url: "https://nas.example.com/s/demo1234",
      resolved_url: "https://nas.example.com/s/demo1234",
      is_lan_fallback: false,
      expires_at: null,
      password_protected: false,
      revoked: false,
      download_count: 3,
      created_at: "2026-11-24T10:00:00Z",
      owner_username: "admin",
    },
  ]
  const mockShareAccounts: ShareAccountCandidate[] = [
    { id: 2, username: "bob" },
    { id: 3, username: "charlie" },
  ]
  let mockAccountShares: AccountShareItem[] = []
  let mockAccountShareSeq = 1

  let powerTimer: number | undefined

  const powerListeners = new Set<(p: PowerState) => void>()

  let mockClipboard: ExplorerClipboardState = {
    kind: "empty",
    items: [],
  }

  let mockTransferWindowState: Record<string, unknown> | null =
    typeof window !== "undefined" && window.location.search.includes("window=transfer")
      ? { mode: "progress" }
      : null

  let mockTransferSeq = 1
  let mockTransferStatus: TransferStatusResponse = {
    success: true,
    mode: "progress",
    status: "idle",
    total_files: 0,
    completed_files: 0,
    failed_files: 0,
    skipped_files: 0,
    bytes_done: 0,
    bytes_total: 0,
    speed_bps: 0,
    eta_seconds: null,
    active_workers: 0,
    max_workers: 3,
    items: [],
    clipboard: mockClipboard,
  }

  const cloneTransferStatus = (): TransferStatusResponse => ({
    ...mockTransferStatus,
    items: mockTransferStatus.items.map((item) => ({ ...item })),
    conflict: mockTransferStatus.conflict ? { ...mockTransferStatus.conflict } : null,
    clipboard: {
      ...mockClipboard,
      items: mockClipboard.items.map((item) => ({ ...item })),
    },
  })



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

      return { logDirectory: "C:\\MyServer\\logs", defaultDirectory: "C:\\MyServer\\logs", isCustom: false }

    },

    async chooseLogFolder() {

      return { success: true, logDirectory: "C:\\MyServer\\logs", defaultDirectory: "C:\\MyServer\\logs", isCustom: false }

    },

    async resetLogDirectory() {

      return { success: true, logDirectory: "C:\\MyServer\\logs", defaultDirectory: "C:\\MyServer\\logs", isCustom: false }

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

    async probeUrl(url: string) {
      return { reachable: true, latency_ms: 12, status: 200, url }
    },

    async hideFlyout() {},

    async hideWindow() {},

    async startDrag() {},

    async setWizardMode() {},

    async minimizeWindow() {},

    async openUrl() {},

    async openExternalBrowser(url?: string) {
      if (typeof window !== "undefined" && url) window.open(url, "_blank")
    },

    async syncInstaBoxVm(params: any) {
      return {
        success: true,
        machineId: params?.machineId || "m_demo123",
        machineName: params?.vmName || "InstaBox Cloud VM",
        state: "running",
        runtimeMinutes: 184,
        maxRuntimeMinutes: 480,
        idleTimeoutMinutes: 30,
        screenUrl: "https://instabox.sh/app/machines/m_demo",
        telemetry: {
          cpuPct: 14,
          ramUsedBytes: 2576980377,
          ramTotalBytes: 8589934592,
          diskUsedBytes: 5583457484,
          diskTotalBytes: 21474836480,
        }
      }
    },

    async smartResetInstaBox() {
      return { success: true, message: "Limit 8 jam berhasil direset." }
    },

    async wakeInstaBoxVm() {
      return { status: "ok", message: "VM berhasil dibangunkan (mock)." }
    },

    async pauseInstaBoxVm() {
      return { status: "ok", message: "VM berhasil di-pause (mock)." }
    },

    async loadVms() {
      return []
    },

    async saveVms() {
      return { status: "ok", success: true }
    },

    async updateVm(_vmId: string, _updates: any, _serverId?: string) {
      return { status: "ok", success: true }
    },

    async deleteVm(_vmId: string, _scope?: string, _serverId?: string) {
      return { status: "ok", success: true }
    },

    async migrateVm(_vmId: string, _targetScope: "server" | "local", _vm?: Partial<VirtualMachine>) {
      return { status: "ok", success: true }
    },

    async openSshTerminal(params?: { host?: string; user?: string; port?: number; serverId?: string; saveSshUser?: boolean }) {
      const user = (params?.user || "casaos").trim()
      const host = (params?.host || "zimaos.local").trim()
      const port = Number(params?.port || 22)
      const command = port !== 22 ? `ssh -p ${port} ${user}@${host}` : `ssh ${user}@${host}`
      return { status: "ok", success: true, command, user, host, port, launched: true }
    },

    async openVmWindow(_vmId: string, title: string, url: string) {
      await this.openUrl(url, title)
    },

    async openFileManager() { return { success: true } },

    async openFileExplorer() { return { success: true } },

    async openZimaFileManager() {},

    async openBackendFileManager() {
      return { success: true, url: "http://127.0.0.1:8080/" }
    },

    async getFileManagerSource() {
      return {
        ...mockSmbSource,
        drives: drives.map((d) => ({ ...d })),
      }
    },

    async configureFileManagerSource(payload: FileManagerSourcePayload) {
      const nextSource = payload?.source || mockSmbSource.source || "zimaos"
      if (nextSource === "backend") {
        const uname = (payload?.username ?? mockSmbSource.username ?? "").trim()
        const hasPwd =
          Boolean(payload?.password) ||
          Boolean(mockSmbSource.hasCredentials && !mockSmbSource.needsAuth)
        if (!uname || !hasPwd) {
          return {
            ...mockSmbSource,
            success: false,
            needsAuth: true,
            error: "Username dan password akun Backend wajib diisi.",
            drives: drives.map((d) => ({ ...d })),
          }
        }
        const role = uname.toLowerCase() === "admin" ? "admin" : "user"
        const allowedDisks = role === "admin" ? ["DATA", "Media"] : ["DATA"]
        mockSmbSource = {
          ...mockSmbSource,
          success: true,
          source: "backend",
          username: uname,
          role,
          allowedDisks,
          hasCredentials: true,
          backendOnline: true,
          smbMode: "backend",
          needsAuth: false,
          error: undefined,
        }
        return {
          ...mockSmbSource,
          drives: drives.map((d) => ({ ...d })),
        }
      }
      mockSmbSource = {
        ...mockSmbSource,
        success: true,
        source: "zimaos",
        smbMode: "zimaos",
        needsAuth: false,
        error: undefined,
      }
      return {
        ...mockSmbSource,
        drives: drives.map((d) => ({ ...d })),
      }
    },

    async openPeerDrop() {},

    async openUnc() { return { success: true } },

    async openDrive() { return { success: true } },

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

        serverId: "srv_primary",

        serverName: "Primary-Server",

        servers: [

          { id: "srv_primary", name: "Primary-Server" },

          { id: "srv_secondary", name: "Secondary-Server" },

        ],

        activeRoute: "conn_auto",

        routes: [

          { id: "conn_lan", name: "Local / Primary", url: "http://zimaos.local", active: true, pingMs: 287 },

          { id: "conn_ip", name: "IP Local", url: "http://192.0.2.10", active: false, pingMs: 2 },

          { id: "conn_zt", name: "ZeroTier Remote (P2P)", url: "http://192.0.2.20", active: false, isZeroTier: true, pingMs: 18 },

        ],

        zeroTier: {
          running: true,
          networkStatus: "OK",
          networkName: "IceWhale-RemoteAccess",
          configuredNwid: "0000000000000000",
          nodeId: "0000000000",
          virtualIp: "192.0.2.21",
          serverVirtualIp: "192.0.2.20",
          joined: true,
        },
        easyTier: {
          running: true,
          available: true,
          remote_id: "0000000000000000",
          network_name: "zima-0000000000000000",
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

        { id: "app_1", name: "Jellyfin", url: "http://zimaos.local:8096", port: "8096" },

        { id: "app_2", name: "Nextcloud", url: "http://zimaos.local:8081", port: "8081" },

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

    async triggerBackendAction(_action: "install" | "update", _serverId?: string, _options?: { source?: BackendDeploySource; sshHost?: string; sshPort?: number; sshUser?: string; sshPassword?: string }) {
      return { success: true, status: "ok", stage: "done", version: "1.0.0", latestVersion: "1.0.0", message: "Mock backend updated", backend: { online: true, version: "1.0.0", latestVersion: "1.0.0" } }
    },

    async getBackendStatus(_serverId?: string) {
      return { online: true, version: "1.0.0", latestVersion: "1.0.0", url: "http://zimaos.local:8788" }
    },

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

    async detectLocalSyncthing() {
      return {
        detected: true,
        localPort: "8384",
        localApiKey: "MOCK_LOCAL_KEY",
        serverApiKey: "MOCK_SERVER_KEY",
      }
    },

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
          serverPath: "/DATA/Projects/Media",
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

    async executeRestoreDialog() { return { success: true, rollbackFile: "config.json.bak" } },

    async verifyZimaLogin(payload) {
      return {
        success: true,
        username: payload.username,
        resolvedUrl: payload.url || "http://zimaos.local",
        isAdmin: true,
      }
    },

    async commitWizardServer(payload) {
      return {
        success: true,
        serverId: payload.serverId || "srv_mock_1",
        name: payload.name || "Server Utama",
      }
    },

    async completeWizard() {
      settings = { ...settings, firstRunSetup: false }
      return { success: true, firstRunSetup: false }
    },

    async resolveSharePath(path: string) {
      const clean = typeof path === "string" ? path.trim().replace(/^["']|["']$/g, "") : ""
      if (!clean || clean.includes("\0") || /(^|[\\/])\.\.($|[\\/])/.test(clean)) {
        return { ok: false, code: "INVALID_PATH", message: "Invalid or unsupported file path." }
      }
      if (power === "offline") {
        return {
          ok: false,
          code: "SERVER_OFFLINE",
          message: "Cannot create share link while server or Backend is offline.",
        }
      }
      if (/^[a-dA-D]:/.test(clean)) {
        return {
          ok: false,
          code: "LOCAL_DRIVE",
          message: "Only files or folders on a MyServer SMB drive can be shared.",
        }
      }
      const norm = clean
        .replace(/\\/g, "/")
        .replace(/^[A-Za-z]:\/?/, "")
        .replace(/^\/+/, "")
      const canonical = norm.startsWith("DATA/") ? norm : norm ? `DATA/${norm}` : "DATA"
      const segs = canonical.split("/").filter(Boolean)
      const basename = segs[segs.length - 1] || "DATA"
      return {
        ok: true,
        target: {
          server_id: "srv_mock_1",
          server_name: "Server Utama",
          disk_name: "DATA",
          share_name: "DATA",
          canonical_rel: canonical,
          basename,
          is_dir: !basename.includes("."),
          is_admin: mockIsAdmin,
          backend_url: "http://192.0.2.10:8085",
          smb_source: "zimaos",
          raw_path: path,
        },
      }
    },

    async listShares(opts) {
      const base = (mockPublicBaseUrl || "http://192.0.2.10:8085").replace(/\/+$/, "")
      const isLanFallback = !mockPublicBaseUrl
      const targetNorm = opts?.targetPath
        ? opts.targetPath.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "")
        : null
      const filtered = mockShares
        .filter((s) => !s.revoked)
        .filter((s) => (targetNorm ? s.target_path === targetNorm : true))
        .map((s) => {
          const url = `${base}/s/${s.token}`
          return {
            ...s,
            share_url: url,
            resolved_url: url,
            is_lan_fallback: isLanFallback,
          }
        })
      return {
        success: true,
        shares: filtered,
        public_base_url: mockPublicBaseUrl,
        is_admin: mockIsAdmin,
        username: "admin",
        backend_url: "http://192.0.2.10:8085",
      }
    },

    async createShare(payload) {
      const cleanPath = typeof payload.path === "string" ? payload.path.trim() : ""
      if (!cleanPath) {
        return { success: false, code: "INVALID_PATH", error: "Invalid or empty path." }
      }
      const token = `mock${++mockShareCounter}${Math.random().toString(36).slice(2, 6)}`
      const base = (mockPublicBaseUrl || "http://192.0.2.10:8085").replace(/\/+$/, "")
      const isLanFallback = !mockPublicBaseUrl
      const shareUrl = `${base}/s/${token}`
      const expiresAt =
        typeof payload.expires_in_hours === "number" && payload.expires_in_hours > 0
          ? new Date(Date.now() + payload.expires_in_hours * 3600 * 1000).toISOString()
          : null
      const segs = cleanPath.replace(/\\/g, "/").split("/").filter(Boolean)
      const label = payload.label || segs[segs.length - 1] || cleanPath
      const isDir = !label.includes(".")
      const cleanRole: PublicShareRole = isDir && payload.role === "editor" ? "editor" : "viewer"
      const maxUploadMb =
        cleanRole === "editor" && typeof payload.max_upload_mb === "number" && payload.max_upload_mb > 0
          ? Math.floor(payload.max_upload_mb)
          : null
      const item: PublicShareItem = {
        token,
        target_path: segs.join("/"),
        is_dir: isDir,
        label,
        role: cleanRole,
        max_upload_mb: maxUploadMb,
        max_upload_bytes: maxUploadMb ? maxUploadMb * 1024 * 1024 : null,
        share_url: shareUrl,
        resolved_url: shareUrl,
        is_lan_fallback: isLanFallback,
        expires_at: expiresAt,
        password_protected: Boolean(payload.password && payload.password.trim()),
        revoked: false,
        download_count: 0,
        created_at: new Date().toISOString(),
        owner_username: "admin",
      }
      mockShares = [item, ...mockShares]
      return {
        success: true,
        share: item,
        share_url: shareUrl,
        is_lan_fallback: isLanFallback,
        clipboard_copied: payload.copy_to_clipboard !== false,
      }
    },

    async quickSharePath(path: string) {
      const resolved = await this.resolveSharePath(path)
      if (!resolved.ok || !resolved.target) {
        return {
          success: false,
          ok: false,
          code: resolved.code || "INVALID_PATH",
          error: resolved.message || "Unable to resolve path.",
        }
      }
      const created = await this.createShare({
        path: resolved.target.canonical_rel,
        server_id: resolved.target.server_id,
        password: null,
        expires_in_hours: null,
        role: "viewer",
        copy_to_clipboard: true,
      })
      if (!created.success || !created.share_url) {
        return {
          success: false,
          ok: false,
          code: created.code || "UNKNOWN_ERROR",
          error: created.error || "Failed to create quick share link.",
        }
      }
      return {
        success: true,
        ok: true,
        code: created.is_lan_fallback ? "OK_LAN_FALLBACK" : "OK_PUBLIC",
        share: created.share,
        share_url: created.share_url,
        is_lan_fallback: created.is_lan_fallback,
        clipboard_copied: true,
        toast_title:
          settings.language === "en"
            ? "Share link copied to clipboard"
            : "Tautan berbagi disalin ke clipboard",
        toast_body: resolved.target.basename,
      }
    },

    async revokeShare(token: string) {
      const idx = mockShares.findIndex((s) => s.token === token && !s.revoked)
      if (idx === -1) {
        return { success: false, already_revoked: true, error: "Share link not found." }
      }
      mockShares = mockShares.filter((s) => s.token !== token)
      return { success: true }
    },

    async updateShareSettings(publicBaseUrl: string) {
      if (!mockIsAdmin) {
        return { success: false, status: 403, error: "Only administrators may update Public Base URL." }
      }
      mockPublicBaseUrl = (publicBaseUrl || "").trim().replace(/\/+$/, "")
      return { success: true, public_base_url: mockPublicBaseUrl }
    },

    async copyShareClipboard(text: string) {
      if (!text) return false
      try {
        if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(text)
        }
      } catch {
        // ignore in mock/jsdom
      }
      return true
    },

    async setExplorerContextMenuEnabled(enabled: boolean) {
      const next = Boolean(enabled)
      settings = { ...settings, explorerContextMenuEnabled: next }
      return { success: true, enabled: next }
    },

    async openShareWindow(target: ShareTargetInfo) {
      mockShareTarget = target
    },

    async closeShareWindow() {
      mockShareTarget = null
    },

    async getShareWindowTarget() {
      return mockShareTarget
    },

    async listShareAccountCandidates() {
      return { success: true, accounts: [...mockShareAccounts] }
    },

    async listAccountShares(targetPath: string) {
      const norm = targetPath.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "")
      return {
        success: true,
        shares: mockAccountShares.filter((s) => s.target_path === norm),
        caller_role: "owner",
      }
    },

    async grantAccountShare(payload) {
      const norm = payload.targetPath.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "")
      const candidate = mockShareAccounts.find((a) => a.username === payload.granteeUsername)
      if (!candidate) {
        return { success: false, error: "Account not found." }
      }
      const isDir = !norm.split("/").pop()?.includes(".")
      const effectiveRole: InternalShareRole = isDir ? payload.role : "viewer"
      const now = new Date().toISOString()
      const existingIdx = mockAccountShares.findIndex(
        (s) => s.target_path === norm && s.grantee_username === payload.granteeUsername
      )
      if (existingIdx !== -1) {
        const updated: AccountShareItem = {
          ...mockAccountShares[existingIdx],
          role: effectiveRole,
          updated_at: now,
        }
        mockAccountShares = mockAccountShares.map((s, i) => (i === existingIdx ? updated : s))
        return { success: true, share: updated }
      }
      const created: AccountShareItem = {
        id: mockAccountShareSeq++,
        owner_user_id: 1,
        owner_username: "admin",
        target_path: norm,
        is_dir: isDir,
        grantee_user_id: candidate.id,
        grantee_username: candidate.username,
        role: effectiveRole,
        created_at: now,
        updated_at: now,
      }
      mockAccountShares = [created, ...mockAccountShares]
      return { success: true, share: created }
    },

    async updateAccountShareRole(grantId: number, role: InternalShareRole) {
      const existing = mockAccountShares.find((s) => s.id === grantId)
      if (!existing) {
        return { success: false, error: "Grant not found." }
      }
      const effectiveRole: InternalShareRole = existing.is_dir ? role : "viewer"
      const updated: AccountShareItem = {
        ...existing,
        role: effectiveRole,
        updated_at: new Date().toISOString(),
      }
      mockAccountShares = mockAccountShares.map((s) => (s.id === grantId ? updated : s))
      return { success: true, share: updated }
    },

    async revokeAccountShare(grantId: number) {
      const exists = mockAccountShares.some((s) => s.id === grantId)
      if (!exists) {
        return { success: false, error: "Grant not found." }
      }
      mockAccountShares = mockAccountShares.filter((s) => s.id !== grantId)
      return { success: true, grant_id: grantId }
    },

    async getExplorerClipboard(): Promise<ExplorerClipboardState> {
      return {
        ...mockClipboard,
        items: mockClipboard.items.map((item) => ({ ...item })),
      }
    },

    async copyServerItemsToClipboard(payload) {
      const items = Array.isArray(payload.items)
        ? payload.items.map((item) => ({
            path: item.path,
            relative_path: item.relative_path,
            name: item.name,
            is_dir: Boolean(item.is_dir),
            size: item.size,
          }))
        : []
      mockClipboard = {
        kind: items.length > 0 ? "server" : "empty",
        items,
        server_id: payload.serverId || "srv_mock_1",
        server_name: "Server Utama",
        copied_at: Date.now(),
        source_origin: "companion",
      }
      mockTransferStatus = {
        ...mockTransferStatus,
        clipboard: mockClipboard,
      }
      return {
        success: true,
        clipboard: {
          ...mockClipboard,
          items: mockClipboard.items.map((item) => ({ ...item })),
        },
      }
    },

    async clearExplorerClipboard() {
      mockClipboard = { kind: "empty", items: [] }
      mockTransferStatus = {
        ...mockTransferStatus,
        clipboard: mockClipboard,
      }
      return { success: true }
    },

    async browseTransferDirectory(opts) {
      const serverId = opts?.serverId ?? opts?.server_id ?? "srv_mock_1"
      const source = opts?.source ?? "disks"
      const rawPath = (opts?.path ?? "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "")

      if (source === "shared" && !rawPath) {
        const items: QuickPickerEntry[] = [
          {
            name: "SharedDocs",
            relative_path: "SharedDocs",
            is_dir: true,
            effective_role: "viewer",
            writable: false,
            owner_username: "budi",
            is_remote: true,
          },
          {
            name: "TeamProject",
            relative_path: "TeamProject",
            is_dir: true,
            effective_role: "editor",
            writable: true,
            owner_username: "andi",
            is_remote: true,
          },
        ]
        return {
          success: true,
          server_id: serverId,
          server_name: "Server Utama",
          current_path: "",
          parent_path: "",
          effective_role: "viewer",
          writable: false,
          view_mode: "shared",
          items,
        }
      }

      if (!rawPath) {
        const items: QuickPickerEntry[] = [
          {
            name: "DATA",
            relative_path: "DATA",
            is_dir: true,
            effective_role: "owner",
            writable: true,
          },
          {
            name: "Media",
            relative_path: "Media",
            is_dir: true,
            effective_role: "owner",
            writable: true,
          },
        ]
        return {
          success: true,
          server_id: serverId,
          server_name: "Server Utama",
          current_path: "",
          parent_path: "",
          effective_role: "owner",
          writable: true,
          view_mode: "disks",
          items,
        }
      }

      const segs = rawPath.split("/").filter(Boolean)
      const parentPath = segs.length > 1 ? segs.slice(0, -1).join("/") : ""

      if (rawPath === "SharedDocs" || rawPath.startsWith("SharedDocs/") || rawPath === "DATA/ReadOnlyViewer" || rawPath.startsWith("DATA/ReadOnlyViewer/")) {
        return {
          success: true,
          server_id: serverId,
          server_name: "Server Utama",
          current_path: rawPath,
          parent_path: parentPath,
          effective_role: "viewer",
          writable: false,
          view_mode: "folder",
          items: [
            {
              name: "Handbook.pdf",
              relative_path: `${rawPath}/Handbook.pdf`,
              is_dir: false,
              size: 1024 * 512,
              effective_role: "viewer",
              writable: false,
            },
          ],
        }
      }

      if (rawPath === "DATA") {
        return {
          success: true,
          server_id: serverId,
          server_name: "Server Utama",
          current_path: "DATA",
          parent_path: "",
          effective_role: "owner",
          writable: true,
          view_mode: "folder",
          items: [
            {
              name: "Documents",
              relative_path: "DATA/Documents",
              is_dir: true,
              effective_role: "owner",
              writable: true,
            },
            {
              name: "ReadOnlyViewer",
              relative_path: "DATA/ReadOnlyViewer",
              is_dir: true,
              effective_role: "viewer",
              writable: false,
            },
            {
              name: "ConflictFolder",
              relative_path: "DATA/ConflictFolder",
              is_dir: true,
              effective_role: "editor",
              writable: true,
            },
            {
              name: "Report.pdf",
              relative_path: "DATA/Report.pdf",
              is_dir: false,
              size: 245760,
              effective_role: "owner",
              writable: true,
            },
          ],
        }
      }

      return {
        success: true,
        server_id: serverId,
        server_name: "Server Utama",
        current_path: rawPath,
        parent_path: parentPath,
        effective_role: "editor",
        writable: true,
        view_mode: "folder",
        items: [
          {
            name: "Notes.txt",
            relative_path: `${rawPath}/Notes.txt`,
            is_dir: false,
            size: 4096,
            effective_role: "editor",
            writable: true,
          },
        ],
      }
    },

    async startTransferPaste(payload: TransferPastePayload): Promise<TransferStatusResponse> {
      const destRel = (payload.destRel ?? payload.dest_rel ?? "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "")
      const sourceItems =
        mockClipboard.items.length > 0
          ? mockClipboard.items
          : [{ name: "Archive.zip", is_dir: false, size: 1024 * 1024 * 12 }]
      const jobId = `job_mock_${mockTransferSeq++}`
      const isConflict = destRel.toLowerCase().includes("conflict")
      const totalBytes = sourceItems.reduce((acc, item) => acc + (item.size ?? 1024 * 512), 0)
      const queueItems: TransferQueueItem[] = sourceItems.map((item, idx) => ({
        id: `${jobId}_item_${idx}`,
        name: item.name,
        relative_path: destRel ? `${destRel}/${item.name}` : item.name,
        is_dir: item.is_dir,
        bytes_done: isConflict ? 0 : item.size ?? 1024 * 512,
        bytes_total: item.size ?? 1024 * 512,
        status: isConflict ? (idx === 0 ? "active" : "pending") : "done",
      }))

      mockTransferStatus = {
        success: true,
        mode: "progress",
        job_id: jobId,
        direction: mockClipboard.kind === "server" ? "server_copy" : "upload",
        status: isConflict ? "awaiting_conflict" : "completed",
        dest_label: destRel || "DATA",
        total_files: queueItems.length,
        completed_files: isConflict ? 0 : queueItems.length,
        failed_files: 0,
        skipped_files: 0,
        bytes_done: isConflict ? 0 : totalBytes,
        bytes_total: totalBytes,
        speed_bps: isConflict ? 0 : 42 * 1024 * 1024,
        eta_seconds: isConflict ? null : 0,
        active_workers: isConflict ? 1 : 0,
        max_workers: 3,
        current_item_name: queueItems[0]?.name,
        conflict: isConflict
          ? {
              job_id: jobId,
              item_name: queueItems[0]?.name || "Archive.zip",
              dest_path: destRel ? `${destRel}/${queueItems[0]?.name || "Archive.zip"}` : "Archive.zip",
              is_dir: Boolean(queueItems[0]?.is_dir),
              remaining_conflicts_hint: Math.max(0, queueItems.length - 1),
            }
          : null,
        items: queueItems,
        clipboard: mockClipboard,
      }
      return cloneTransferStatus()
    },

    async getTransferStatus(): Promise<TransferStatusResponse> {
      return cloneTransferStatus()
    },

    async resolveTransferConflict(payload): Promise<TransferStatusResponse> {
      const isSkip = payload.action === "skip"
      const totalBytes = mockTransferStatus.bytes_total
      const updatedItems: TransferQueueItem[] = mockTransferStatus.items.map((item) => ({
        ...item,
        bytes_done: isSkip ? 0 : item.bytes_total,
        status: isSkip ? "skipped" : "done",
      }))
      mockTransferStatus = {
        ...mockTransferStatus,
        job_id: payload.jobId || mockTransferStatus.job_id,
        status: "completed",
        completed_files: isSkip ? 0 : updatedItems.length,
        skipped_files: isSkip ? updatedItems.length : 0,
        bytes_done: isSkip ? 0 : totalBytes,
        speed_bps: isSkip ? 0 : 38 * 1024 * 1024,
        eta_seconds: 0,
        active_workers: 0,
        conflict: null,
        items: updatedItems,
      }
      return cloneTransferStatus()
    },

    async pauseTransferJob(): Promise<TransferStatusResponse> {
      mockTransferStatus = {
        ...mockTransferStatus,
        status: "paused",
        speed_bps: 0,
        active_workers: 0,
      }
      return cloneTransferStatus()
    },

    async resumeTransferJob(): Promise<TransferStatusResponse> {
      mockTransferStatus = {
        ...mockTransferStatus,
        status: "running",
        speed_bps: 28 * 1024 * 1024,
        active_workers: 2,
      }
      return cloneTransferStatus()
    },

    async cancelTransferJob(): Promise<TransferStatusResponse> {
      mockTransferStatus = {
        ...mockTransferStatus,
        status: "cancelled",
        speed_bps: 0,
        active_workers: 0,
        conflict: null,
        items: mockTransferStatus.items.map((item) =>
          item.status === "done" || item.status === "skipped"
            ? item
            : { ...item, status: "cancelled" }
        ),
      }
      return cloneTransferStatus()
    },

    async clearTransferHistory() {
      mockTransferStatus = {
        success: true,
        mode: "progress",
        status: "idle",
        total_files: 0,
        completed_files: 0,
        failed_files: 0,
        skipped_files: 0,
        bytes_done: 0,
        bytes_total: 0,
        speed_bps: 0,
        eta_seconds: null,
        active_workers: 0,
        max_workers: 3,
        conflict: null,
        items: [],
        clipboard: mockClipboard,
      }
      return { success: true }
    },

    async setExplorerHotkeyEnabled(enabled: boolean) {
      const next = Boolean(enabled)
      settings = { ...settings, explorerHotkeyEnabled: next }
      return { success: true, enabled: next }
    },

    async openTransferWindow(initialState) {
      mockTransferWindowState = initialState ? { ...initialState } : { mode: "progress" }
    },

    async closeTransferWindow() {
      mockTransferWindowState = null
    },

    async getTransferWindowState() {
      return mockTransferWindowState ? { ...mockTransferWindowState } : null
    },

  }

}



let current: CompanionApi = createMockApi()



export const getCompanionApi = () => current

/** Call once at startup (before render) to replace the mock with a real backend. */

export const setCompanionApi = (api: CompanionApi) => {

  current = api

}


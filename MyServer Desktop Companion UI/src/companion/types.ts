export type ViewId = "home" | "files" | "backup" | "apps" | "settings" | "power" | "server" | "vm"

export interface VmAutoRestartSchedule {
  enabled: boolean
  mode: "interval" | "clock"
  intervalValue?: number
  intervalUnit?: "seconds" | "minutes" | "hours"
  clockTime?: string // "HH:MM" e.g. "04:00"
  resetCycleMode?: "pause_resume" | "cold_restart" | "sleep_2s" | "full_reboot"
  resetMode?: "pause_resume" | "cold_restart" | "sleep_2s" | "full_reboot"
  lastExecuted?: string
  lastRunTimestamp?: number
}

export interface VmAutoOnSchedule {
  enabled: boolean
  mode: "clock" | "after_off"
  clockTime?: string // "HH:MM" e.g. "07:00"
  days?: Array<number | string> // 0=Sun..6=Sat or "Mon".."Sun"
  delayValue?: number // e.g. 30
  delayUnit?: "seconds" | "minutes" | "hours"
  lastTriggered?: string
  lastTriggeredTimestamp?: number
}

export interface VmTelemetry {
  cpuPct?: number | null
  ramUsedBytes?: number | null
  ramTotalBytes?: number | null
  diskUsedBytes?: number | null
  diskTotalBytes?: number | null
  netUpKbs?: number | null
  netDownKbs?: number | null
  updatedAt?: string
}

export interface VmPublishedPort {
  port: number
  label?: string
  url?: string
}

export interface VirtualMachine {
  id: string
  name: string
  provider: "instabox" | "custom" | "manual"
  status: "running" | "sleeping" | "cooldown" | "stopped"
  scope?: "server" | "local"
  serverId?: string
  serverName?: string
  machineId?: string
  sshHost?: string
  sshUser?: string
  sshPort: number
  ip?: string
  tokenExpiry?: string
  webPort?: number
  webUrl?: string
  screenUrl?: string
  screenOpenTarget?: "window" | "browser" | "ask"
  apiKey?: string
  publishedPorts?: VmPublishedPort[]
  telemetry?: VmTelemetry
  autoRestart?: VmAutoRestartSchedule
  autoOn?: VmAutoOnSchedule
  sleepingSince?: number
  keepAliveEnabled?: boolean
  scheduleTimezone?: string
  tzOffsetMinutes?: number
  meshIp?: string
  specs?: {
    cpu?: string
    ram?: string
    storage?: string
  }
  runtimeMinutes?: number // minutes running today
  maxRuntimeMinutes?: number // batas sesi runtime dalam menit (-1 = unlimited)
  idleTimeoutMinutes?: number // 30 min
  cooldownRemainingMinutes?: number
  lastActive?: string
  notes?: string
}

export type PowerState = "online" | "rebooting" | "offline" | "waking"

export type Tone = "success" | "neutral" | "info" | "warning" | "danger"

export interface StoragePartitionItem {
  name: string
  used_bytes?: number
  total_bytes?: number
  usedBytes?: number
  totalBytes?: number
  mount_point?: string
  mountPoint?: string
}

export interface Metrics {
  cpu: number
  ram: number
  hdd: number
  lanDown: number
  lanHistory: number[]
  syncUp: number
  syncDown: number
  speedDownStr?: string
  speedUpStr?: string
  speedDownBps?: number
  speedUpBps?: number
  isAdmin?: boolean
  cpuWattage?: number
  cpuTemp?: number | null
  ramUsedBytes?: number
  ramTotalBytes?: number
  storageUsedBytes?: number
  storageTotalBytes?: number
  storagePartitions?: StoragePartitionItem[]
  smbSource?: SmbSourceMode
  smbSyncing?: boolean
  smbSyncReason?: string
  smbSyncMessage?: string
  activeServerId?: string
  isLoading?: boolean
}

export interface Drive {
  letter: string
  name: string
  free: string
  total: string
  usedPct: number
  mounted: boolean
  totalBytes?: number
  usedBytes?: number
  isRemote?: boolean
}

export type SmbSourceMode = "zimaos" | "backend"

export interface ExplorerOpenResult {
  success?: boolean
  error?: string
  message?: string
  drive?: string
  host?: string
  unc?: string
  target?: string
}

export interface FileManagerSourceStatus {
  success?: boolean
  source: SmbSourceMode
  username?: string
  role?: string
  allowedDisks?: string[]
  hasCredentials?: boolean
  backendOnline?: boolean
  backendUrl?: string
  smbMode?: SmbSourceMode
  error?: string
  needsAuth?: boolean
  warning?: string
  drives?: Drive[]
  easytierNoTun?: boolean
  tunActive?: boolean
  smbWarning?: string
}

export interface FileManagerSourcePayload {
  action?: "get" | "set"
  source?: SmbSourceMode
  username?: string
  password?: string
  autoMount?: boolean
}

export interface TransitionState {
  active: boolean
  title: string
  message?: string
}

export interface Settings {
  autostart: boolean
  openDashboard: boolean
  autoMountSmb: boolean
  autoZeroTier: boolean
  autoCleanOnExit: boolean
  appEntryOpen?: "window" | "browser"
  showTraffic?: boolean
  autoOpenMiniTray?: boolean
  fileManagerClickTarget?: "explorer" | "zimaos"
  language?: "en" | "id"
  dpapiActive?: boolean
  theme?: "dark" | "light"
  autoCheckUpdate?: boolean
  firstRunSetup?: boolean
  explorerContextMenuEnabled?: boolean
}

export type ChecklistKey = "lan" | "bios" | "standby"

export interface AccountStatusInfo {
  username: string
  isAdmin: boolean
  roleName: string
  accessDescription: string
  verified: boolean
}

export interface ServerRoute {
  id: string
  name: string
  url: string
  active: boolean
  isZeroTier?: boolean
  pingMs?: number | null
}

export interface ServerItem {
  id: string
  name: string
  active: boolean
  sshUser?: string
}

export interface ZeroTierInfo {
  running: boolean
  nodeId: string
  networkName: string
  networkStatus: string
  virtualIp: string
  configuredNwid: string
  joined?: boolean
  serverVirtualIp?: string
}

export interface EasyTierInfo {
  running?: boolean
  available?: boolean
  remote_id?: string | null
  network_name?: string | null
  virtual_ipv4?: string | null
  virtual_ip?: string | null
  server_peer_ip?: string
  peers_count?: number
  peers?: any[]
  uptime?: number
  tun_active?: boolean
  no_tun_fallback?: boolean
  smb_warning?: string
}

export interface ServerDetails {
  serverId?: string
  serverName: string
  activeId: string
  activeName: string
  activeHost?: string
  sshUser?: string
  servers?: ServerItem[]
  zeroTier?: ZeroTierInfo
  easyTier?: EasyTierInfo
  remoteMode?: string
  activeRemoteEngine?: string
  activeRemoteIp?: string
  activeRoute: string
  routes: ServerRoute[]
  activeProfile: string
  profiles: string[]
  uptimeStr: string
  syncthingDeviceId?: string
  isAdmin?: boolean
  macAddress?: string
  accountStatus?: AccountStatusInfo
  appVersion?: string
  appChannel?: string
  fullVersion?: string
  dpapiActive?: boolean
  theme?: "dark" | "light"
  backend?: {
    online: boolean
    version?: string
    latestVersion?: string
    url?: string
  }
}

export interface WebApp {
  id: string
  name: string
  url: string
  port?: string
  status?: "running" | "exited" | "custom" | string
  icon?: string
  is_zima_container?: boolean
}

export interface SyncthingSyncMetrics {
  active: boolean
  direction: "upload" | "download" | "both" | "none" | string
  percentage: number
  completed_files: number
  total_files: number
  errors: number
  in_speed: string
  out_speed: string
  state: string
}

export interface SyncthingDeviceItem {
  deviceID: string
  name: string
  addresses?: string[]
  compression?: string
  certName?: string
  introducedBy?: string
  paused?: boolean
  connected?: boolean
  address?: string
  client_version?: string
  is_self?: boolean
}

export interface SyncthingPendingDeviceItem {
  name?: string
  address?: string
}

export interface SyncthingNodeStatus {
  online: boolean
  device_id: string
  devices: SyncthingDeviceItem[]
  folders: any[]
  pending_devices: Record<string, SyncthingPendingDeviceItem>
  metrics: SyncthingSyncMetrics
}

export interface SyncthingDaemonStatus {
  running: boolean
  port: string
  has_binary: boolean
  binary_path: string
}

export interface SyncthingFullStatus {
  local: SyncthingNodeStatus
  server: SyncthingNodeStatus
  daemon: SyncthingDaemonStatus
  paired: boolean
  last_update: number
}

export interface SyncthingFolderTask {
  id: string
  label: string
  localPath: string
  serverPath: string
  type: "sendonly" | "sendreceive" | "receiveonly" | string
  paused: boolean
  completion: number
  needFiles: number
  needBytes: number
  owner: string
  existsOnServer: boolean
  isActiveServer?: boolean
  targetServerName?: string
  targetServerId?: string
}

export interface SyncthingConfigData {
  success?: boolean
  server_id?: string
  server_name?: string
  local: {
    port: string
    api_key: string
    auto_start?: boolean
    binary_path?: string
  }
  server: {
    server_name: string
    port: string
    api_key: string
    route_mode?: string
    lan_mode?: string
    lan_ip?: string
    lan_port?: string
    lan_https?: boolean
    wan_url?: string
    wan_port?: string
    wan_https?: boolean
    remote_ip?: string
    remote_port?: string
    remote_https?: boolean
  }
}

export interface NoticeHistoryItem {
  id: number
  text: string
  tone: Tone
  timeStr: string
}

export type WizardStepId = 1 | 2 | 3 | 4 | 5 | "5a" | "5b"

export type BackendDeploySource = "github" | "bundle"

export interface WizardVerifyZimaResponse {
  success: boolean
  username?: string
  resolvedUrl?: string
  isAdmin?: boolean
  zerotierNetworkId?: string
  zerotierIp?: string
  ztStatus?: string
  message?: string
  error?: string
}

export interface WizardCommitServerPayload {
  serverId?: string
  name?: string
  url?: string
  localUrl?: string
  remoteId?: string
  wanUrl?: string
  username: string
  password: string
  sshUser?: string
  setActive?: boolean
  zerotierNetworkId?: string
  zerotierVirtualIp?: string
  easytierVirtualIp?: string
}

export interface WizardCommitServerResult {
  success: boolean
  serverId?: string
  name?: string
  zerotierNetworkId?: string
  zerotierVirtualIp?: string
  message?: string
  error?: string
}

export interface BackendActionPayload {
  action: "install" | "update"
  serverId: string
  source?: BackendDeploySource
  sshHost?: string
  sshPort?: number
  sshUser?: string
  sshPassword?: string
}

export interface BackendActionResult {
  success: boolean
  status?: string
  authFailed?: boolean
  busy?: boolean
  validationError?: boolean
  stage?: string
  version?: string
  latestVersion?: string
  updateAvailable?: boolean
  rebuildRecommended?: boolean
  message?: string
  backend?: Record<string, unknown>
}

export interface SyncthingAutoDetectResult {
  detected: boolean
  localPort?: string
  localApiKey?: string
  serverApiKey?: string
  deviceId?: string
  message?: string
}

export interface WizardDraft {
  connectionMode: "lan" | "remote"
  lanUrl: string
  remoteId: string
  connectionVerified: boolean
  wanUrl: string
  username: string
  /** Transient UI memory only — cleared immediately after Step 3 commit. */
  password: string
  serverId: string
  serverName: string
  zerotierNetworkId: string
  zerotierIp: string
  easytierVirtualIp: string
  step1And3Done: boolean
  backendSource: BackendDeploySource
  backendInstalled: boolean
  backendVersion: string
  syncthingDone: boolean
  vmDone: boolean
}

export type ShareErrorCode =
  | "INVALID_PATH"
  | "LOCAL_DRIVE"
  | "FOREIGN_NAS"
  | "SHARE_NOT_MOUNTED_IN_BACKEND"
  | "MULTI_ITEM_DROP"
  | "SERVER_OFFLINE"
  | "BACKEND_OFFLINE"
  | "UNAUTHENTICATED_SESSION"
  | "FORBIDDEN_PATH"
  | "UNKNOWN_ERROR"

export interface ShareTargetInfo {
  server_id: string
  server_name: string
  disk_name: string
  share_name: string
  canonical_rel: string
  basename: string
  is_dir: boolean
  is_admin?: boolean
  backend_url?: string
  smb_source?: "backend" | "zimaos"
  raw_path?: string
}

export interface ShareResolveResult {
  ok: boolean
  code?: ShareErrorCode
  message?: string
  target?: ShareTargetInfo
}

export type PublicShareRole = "viewer" | "editor"

export type InternalShareRole = "viewer" | "editor" | "administrator"

export type MaxUploadMbPreset = "unlimited" | "25" | "100" | "500" | "1024" | "custom"

export interface PublicShareItem {
  token: string
  target_path: string
  is_dir?: boolean
  label?: string | null
  role?: PublicShareRole
  max_upload_bytes?: number | null
  max_upload_mb?: number | null
  share_url: string
  resolved_url?: string
  is_lan_fallback?: boolean
  expires_at?: string | null
  password_protected?: boolean
  revoked?: boolean
  download_count?: number
  created_at?: string
  owner_username?: string
}

export interface ShareListResponse {
  success: boolean
  shares: PublicShareItem[]
  public_base_url: string
  is_admin: boolean
  username?: string
  backend_url?: string
  error?: string
}

export interface ShareCreatePayload {
  path: string
  server_id?: string
  password?: string | null
  expires_in_hours?: number | null
  role?: PublicShareRole
  max_upload_mb?: number | null
  label?: string | null
  copy_to_clipboard?: boolean
}

export interface ShareAccountCandidate {
  id: number
  username: string
}

export interface ShareAccountCandidatesResponse {
  success: boolean
  accounts: ShareAccountCandidate[]
  error?: string
}

export interface AccountShareItem {
  id: number
  owner_user_id?: number
  owner_username: string
  target_path: string
  is_dir: boolean
  grantee_user_id: number
  grantee_username: string
  role: InternalShareRole
  created_at?: string
  updated_at?: string
}

export interface AccountShareListResponse {
  success: boolean
  shares: AccountShareItem[]
  caller_role?: string
  error?: string
}

export interface AccountShareMutateResult {
  success: boolean
  share?: AccountShareItem
  grant_id?: number
  error?: string
}

export interface ShareCreateResult {
  success: boolean
  share?: PublicShareItem
  share_url?: string
  is_lan_fallback?: boolean
  clipboard_copied?: boolean
  error?: string
  code?: ShareErrorCode
}

export interface QuickShareResult {
  success: boolean
  ok?: boolean
  code?: ShareErrorCode | "OK_PUBLIC" | "OK_LAN_FALLBACK"
  share?: PublicShareItem
  share_url?: string
  is_lan_fallback?: boolean
  clipboard_copied?: boolean
  toast_title?: string
  toast_body?: string
  error?: string
}

export interface ShareSettingsResult {
  success: boolean
  public_base_url?: string
  status?: number
  error?: string
}

export interface ShareRevokeResult {
  success: boolean
  already_revoked?: boolean
  error?: string
}

export interface ExplorerContextMenuResult {
  success: boolean
  enabled: boolean
  error?: string
}

export type MiniTrayDragDropDetail =
  | { type: "enter"; count: number }
  | { type: "drop"; paths: string[] }
  | { type: "leave" }

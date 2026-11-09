export type ViewId = "home" | "files" | "backup" | "apps" | "settings" | "power" | "server" | "vm"

export interface VmAutoRestartSchedule {
  enabled: boolean
  mode: "interval" | "clock"
  intervalValue?: number
  intervalUnit?: "seconds" | "minutes" | "hours"
  clockTime?: string // "HH:MM" e.g. "04:00"
  resetCycleMode?: "pause_resume" | "cold_restart"
  resetMode?: "pause_resume" | "cold_restart"
  lastExecuted?: string
  lastRunTimestamp?: number
}

export interface VmAutoOnSchedule {
  enabled: boolean
  mode: "clock" | "after_off"
  clockTime?: string // "HH:MM" e.g. "07:00"
  days?: number[] // 0=Sun..6=Sat
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
  provider: "instabox" | "custom"
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
  meshIp?: string
  specs?: {
    cpu?: string
    ram?: string
    storage?: string
  }
  runtimeMinutes?: number // minutes running today
  maxRuntimeMinutes?: number // 480 min (8 hours)
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

export interface ServerDetails {
  serverId?: string
  serverName: string
  activeHost?: string
  servers?: ServerItem[]
  zeroTier?: ZeroTierInfo
  easyTier?: any
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
  }
}

export interface NoticeHistoryItem {
  id: number
  text: string
  tone: Tone
  timeStr: string
}

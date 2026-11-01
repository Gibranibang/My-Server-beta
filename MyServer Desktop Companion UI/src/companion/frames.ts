import type { ViewId } from "./types"

export interface FrameMeta {
  view: ViewId
  index: string
  name: string
  short: string
  hint: string
}

export const FRAMES: FrameMeta[] = [
  {
    view: "home",
    index: "01",
    name: "Default Companion Hub",
    short: "Hub",
    hint: "Open a feature card, or press the red dock button for power controls.",
  },
  {
    view: "files",
    index: "02",
    name: "File Manager & SMB Storage",
    short: "Files",
    hint: "Mount or disconnect both SMB drives. The state syncs to every frame.",
  },
  {
    view: "backup",
    index: "03",
    name: "Backup & Data Synchronization",
    short: "Backup",
    hint: "Run an atomic backup, flip Auto-Clean and accept the pending Syncthing device.",
  },
  {
    view: "apps",
    index: "04",
    name: "Web Apps & Container Services",
    short: "Apps",
    hint: "Launch a container service. Status dots follow the server power state.",
  },
  {
    view: "settings",
    index: "05",
    name: "Preferences & System Configuration",
    short: "Options",
    hint: "Toggle client preferences, then restore them with the Reset to Default chip.",
  },
  {
    view: "power",
    index: "06",
    name: "Power Control & Wake-on-LAN",
    short: "Power",
    hint: "Shutdown asks for a second click. The magic packet wakes an offline server.",
  },
]

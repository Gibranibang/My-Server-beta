import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import TrayDock from "../TrayDock"
import FilesView from "../views/FilesView"
import type { Drive, Metrics } from "../types"

const mockCompanionState: {
  metrics: Metrics
  drives: Drive[]
  isOnline: boolean
  power: "online" | "offline" | "rebooting" | "waking"
  settings: any
  transitionState: { active: boolean; title: string; message: string }
  monitoringLoading: boolean
  serverUrl: string
  setAllMounted: ReturnType<typeof vi.fn>
  refreshDrives: ReturnType<typeof vi.fn>
} = {
  metrics: {
    cpu: 18,
    ram: 42,
    hdd: 55,
    lanDown: 0,
    lanHistory: [0],
    syncUp: 0,
    syncDown: 0,
    smbSource: "backend",
    smbSyncing: false,
    isLoading: false,
  },
  drives: [],
  isOnline: true,
  power: "online",
  settings: { language: "id" },
  transitionState: { active: false, title: "", message: "" },
  monitoringLoading: false,
  serverUrl: "http://172.24.0.1",
  setAllMounted: vi.fn(async () => []),
  refreshDrives: vi.fn(async () => {}),
}

vi.mock("../store", () => ({
  useCompanion: () => mockCompanionState,
  useNotice: () => ({ notify: vi.fn() }),
  useAsyncAction: (fn: () => Promise<unknown>) => ["idle", vi.fn(fn)],
  usePowerStatus: () => ({ tone: "success", label: "Online" }),
}))

vi.mock("../api", () => ({
  getCompanionApi: () => ({
    getFileManagerSource: vi.fn(async () => ({
      success: true,
      source: "backend",
      username: "Marcom",
      role: "user",
      allowedDisks: ["Marcom", "STIMI"],
      hasCredentials: true,
      backendOnline: true,
      smbMode: "backend",
      needsAuth: false,
      drives: [],
    })),
    openDrive: vi.fn(async () => ({ success: true })),
    openFileExplorer: vi.fn(async () => ({ success: true })),
    openBackendFileManager: vi.fn(async () => ({ success: true })),
    openZimaFileManager: vi.fn(),
    openPeerDrop: vi.fn(),
  }),
}))

describe("SMB syncing indicator & stale DISK protection", () => {
  beforeEach(() => {
    mockCompanionState.metrics = {
      cpu: 18,
      ram: 42,
      hdd: 55,
      lanDown: 0,
      lanHistory: [0],
      syncUp: 0,
      syncDown: 0,
      smbSource: "backend",
      smbSyncing: false,
      isLoading: false,
    }
    mockCompanionState.drives = []
  })

  it("FilesView displays smb-syncing-indicator and suppresses false empty state during SMB switch", () => {
    mockCompanionState.metrics = {
      ...mockCompanionState.metrics,
      smbSyncing: true,
      smbSyncMessage: "Menyegarkan partisi STIMI-Server...",
    }

    render(<FilesView />)

    const indicator = screen.getByTestId("smb-syncing-indicator")
    expect(indicator).toHaveTextContent("Menyegarkan Partisi SMB...")
    expect(indicator).toHaveTextContent("Menyegarkan partisi STIMI-Server...")
    expect(screen.queryByText("Belum Ada Partisi Penyimpanan Terdeteksi")).not.toBeInTheDocument()
  })

  it("TrayDock DISK tile shows syncing state while smbSyncing is true", () => {
    mockCompanionState.metrics = {
      ...mockCompanionState.metrics,
      smbSyncing: true,
      smbSyncMessage: "Menyinkronkan partisi STIMI-Server...",
    }

    render(<TrayDock powerActive={true} onNavigate={vi.fn()} />)

    const syncingDiskBtn = screen.getByRole("button", { name: /DISK: Menyinkronkan partisi STIMI-Server/i })
    expect(syncingDiskBtn).toBeInTheDocument()
  })
})

import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { CompanionStoreProvider, NoticeProvider, useNotice } from "../store"
import SettingsView from "../views/SettingsView"
import Companion from "../Companion"

function NoticeHistorySpy() {
  const { noticeHistory } = useNotice()
  return (
    <div data-testid="notice-history-count">{noticeHistory.length}</div>
  )
}

function makeMockApi(overrides: Partial<CompanionApi> = {}): CompanionApi {
  const base = createMockApi()
  const baseLoad = base.loadSettings.bind(base)
  return {
    ...base,
    loadSettings: vi.fn(async () => ({
      ...(await baseLoad()),
      firstRunSetup: false,
      language: "id" as const,
      theme: "dark" as const,
      autoCheckUpdate: true,
      dashboardClickTarget: "zimaos" as const,
      fileManagerClickTarget: "explorer" as const,
    })),
    subscribeMetrics: vi.fn(() => () => {}) as unknown as CompanionApi["subscribeMetrics"],
    subscribePower: vi.fn((cb) => {
      cb("online")
      return () => {}
    }) as unknown as CompanionApi["subscribePower"],
    listDrives: vi.fn(async () => []),
    getLogDirectory: vi.fn(async () => ({
      logDirectory: "C:\\Logs",
      defaultDirectory: "C:\\Logs",
      isCustom: false,
    })),
    getServerDetails: vi.fn(async () => ({
      serverId: "srv_1",
      serverName: "Algitha-Server",
      activeId: "srv_1",
      activeName: "Algitha-Server",
      activeHost: "http://192.168.1.50:80",
      activeRoute: "lan",
      routes: [{ id: "lan", name: "LAN", url: "http://192.168.1.50:80", active: true }],
      activeProfile: "admin",
      profiles: ["admin"],
      uptimeStr: "1d",
    })) as unknown as CompanionApi["getServerDetails"],
    saveSettings: vi.fn(async () => {}),
    ...overrides,
  }
}

describe("SettingsView v4.9.5 Options UX, Dashboard/FM targets, and Notification Deduplication", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
    cleanup()
    vi.restoreAllMocks()
    localStorage.clear()
    setCompanionApi(createMockApi())
  })

  it("renders a single auto-check-update control, unified update banner, 3 file manager targets, and dashboard target selector", async () => {
    const savedPayloads: any[] = []
    const api = makeMockApi({
      saveSettings: vi.fn(async (s) => {
        savedPayloads.push(s)
      }),
      checkForUpdate: vi.fn(async () => ({
        upToDate: false,
        version: "9.9.9",
        htmlUrl: "https://github.com/Gibranibang/My-Server-beta/releases/latest",
        downloadUrl: "https://github.com/Gibranibang/My-Server-beta/releases/latest",
      })),
    })
    setCompanionApi(api)

    render(
      <NoticeProvider>
        <CompanionStoreProvider>
          <SettingsView />
        </CompanionStoreProvider>
      </NoticeProvider>,
    )

    await waitFor(() => expect(api.loadSettings).toHaveBeenCalled())

    // 1. Only a single "Check for Updates Automatically" / autoCheckUpdate control exists
    const autoCheckControls = screen.getAllByRole("switch", {
      name: /Periksa Pembaruan Otomatis|Check for Updates Automatically/i,
    })
    expect(autoCheckControls).toHaveLength(1)

    // 2. Check update reveals unified card containing Download + Re-check together (no separate duplicate card)
    const checkBtn = screen.getByRole("button", { name: /Periksa Pembaruan|Check for Updates/i })
    fireEvent.click(checkBtn)
    await waitFor(() => expect(screen.getByTestId("unified-update-available")).toBeInTheDocument())
    expect(screen.getByRole("button", { name: /Unduh & Pasang v9\.9\.9|Download & Install v9\.9\.9/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Periksa Ulang|Re-check/i })).toBeInTheDocument()

    // 3. Dashboard target toggle (ZimaOS vs Backend)
    fireEvent.click(screen.getByTestId("dashboard-target-backend"))
    await waitFor(() => {
      expect(savedPayloads.some((s) => s.dashboardClickTarget === "backend")).toBe(true)
    })

    // 4. All 3 File Manager targets exist (explorer, zimaos, backend)
    expect(screen.getByTestId("fm-target-explorer")).toBeInTheDocument()
    expect(screen.getByTestId("fm-target-zimaos")).toBeInTheDocument()
    fireEvent.click(screen.getByTestId("fm-target-backend"))
    await waitFor(() => {
      expect(savedPayloads.some((s) => s.fileManagerClickTarget === "backend")).toBe(true)
    })
  })

  it("opens Backend File Manager from home top-left dashboard button when dashboardClickTarget is 'backend'", async () => {
    const openBackendFileManager = vi.fn(async () => ({ success: true, url: "http://192.168.1.50:8080/" }))
    const openUrl = vi.fn(async () => {})
    const api = makeMockApi({
      loadSettings: vi.fn(async () => ({
        ...(await createMockApi().loadSettings()),
        firstRunSetup: false,
        language: "en" as const,
        theme: "dark" as const,
        dashboardClickTarget: "backend" as const,
      })),
      openBackendFileManager,
      openUrl,
    })
    setCompanionApi(api)

    render(
      <NoticeProvider>
        <CompanionStoreProvider>
          <Companion view="home" onViewChange={() => {}} />
        </CompanionStoreProvider>
      </NoticeProvider>,
    )

    await waitFor(() => expect(api.loadSettings).toHaveBeenCalled())
    const dashBtn = await screen.findByRole("button", { name: /Open Backend Dashboard/i })
    fireEvent.click(dashBtn)
    await waitFor(() => expect(openBackendFileManager).toHaveBeenCalledTimes(1))
    expect(openUrl).not.toHaveBeenCalled()
  })

  it("does not emit Syncthing 100% spam notifications on startup even when initial polls return empty before tasks appear", async () => {
    let pollCount = 0
    const api = makeMockApi({
      getSyncthingTasks: vi.fn(async () => {
        pollCount += 1
        // Simulate boot race: first poll returns empty [], second poll returns existing 100% synced folder
        if (pollCount === 1) return []
        return [{ id: "folder-1", label: "Work", completion: 100, paused: false, state: "idle" }]
      }),
    })
    setCompanionApi(api)

    render(
      <NoticeProvider>
        <CompanionStoreProvider>
          <NoticeHistorySpy />
        </CompanionStoreProvider>
      </NoticeProvider>,
    )

    await waitFor(() => expect(api.loadSettings).toHaveBeenCalled())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(13_000)
    })

    expect(pollCount).toBeGreaterThanOrEqual(2)
    expect(screen.getByTestId("notice-history-count")).toHaveTextContent("0")
  })
})

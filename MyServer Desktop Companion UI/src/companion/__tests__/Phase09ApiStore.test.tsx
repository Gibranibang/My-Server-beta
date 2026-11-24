import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { createRealApi } from "../api.real"
import { CompanionStoreProvider, NoticeProvider, useCompanion, useNotice } from "../store"
import { ViewBody } from "../views/shared"
import { createInitialDraft } from "../wizard/SetupWizard"

describe("Phase 09 api.real.ts single-invocation, error propagation, isAdmin isolation, retry & polling", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    cleanup()
    vi.restoreAllMocks()
    localStorage.clear()
    delete (window as any).__TAURI_INTERNALS__
    delete (window as any).pywebview
    setCompanionApi(createMockApi())
  })

  it("invokes call_core_api at most once for all 10 VM/InstaBox/SSH/window RPCs even on error and when pywebview exists", async () => {
    const pyFallbackSpy = vi.fn(async () => ({ success: true, vms: [] }))
    ;(window as any).pywebview = {
      api: new Proxy(
        {},
        {
          get: () => pyFallbackSpy,
        },
      ),
    }

    const invoke = vi.fn(async () => {
      throw "Tauri core IPC error"
    })
    ;(window as any).__TAURI_INTERNALS__ = { invoke }
    const realApi = createRealApi()

    // 1-4: InstaBox RPCs return { success: false, error } after 1 invoke
    const syncRes = await realApi.syncInstaBoxVm({ apiKey: "k", machineId: "m1" })
    expect(syncRes).toEqual({ success: false, error: "Tauri core IPC error" })

    const resetRes = await realApi.smartResetInstaBox({ apiKey: "k", machineId: "m1" })
    expect(resetRes).toEqual({ success: false, error: "Tauri core IPC error" })

    const wakeRes = await realApi.wakeInstaBoxVm({ apiKey: "k", machineId: "m1" })
    expect(wakeRes).toEqual({ success: false, error: "Tauri core IPC error" })

    const pauseRes = await realApi.pauseInstaBoxVm({ apiKey: "k", machineId: "m1" })
    expect(pauseRes).toEqual({ success: false, error: "Tauri core IPC error" })

    // 5-8: VM CRUD RPCs throw after 1 invoke
    await expect(realApi.loadVms!()).rejects.toThrow("Tauri core IPC error")
    await expect(realApi.saveVms!([])).rejects.toThrow("Tauri core IPC error")
    await expect(realApi.updateVm!("vm_1", { name: "x" })).rejects.toThrow("Tauri core IPC error")
    await expect(realApi.deleteVm!("vm_1", "server")).rejects.toThrow("Tauri core IPC error")

    // 9-10: SSH terminal & VM window
    const sshRes = await realApi.openSshTerminal!({ host: "192.168.1.10", user: "root" })
    expect(sshRes).toMatchObject({ status: "error", success: false, message: "Tauri core IPC error" })

    await realApi.openVmWindow!("vm_1", "VM 1", "http://127.0.0.1:8000")

    // Exact invoke counts: 9 call_core_api calls + openVmWindow fallback (probe_url + open_app_window + open_in_browser)
    const coreCalls = invoke.mock.calls.filter((c: any[]) => c[0] === "call_core_api")
    const endpoints = coreCalls.map((c: any[]) => c[1]?.endpoint)
    expect(endpoints.filter((e: string) => e === "instabox/sync")).toHaveLength(1)
    expect(endpoints.filter((e: string) => e === "instabox/smart_reset")).toHaveLength(1)
    expect(endpoints.filter((e: string) => e === "instabox/wake")).toHaveLength(1)
    expect(endpoints.filter((e: string) => e === "instabox/pause")).toHaveLength(1)
    expect(endpoints.filter((e: string) => e === "vms/load")).toHaveLength(1)
    expect(endpoints.filter((e: string) => e === "vms/save")).toHaveLength(1)
    expect(endpoints.filter((e: string) => e === "vms/update")).toHaveLength(1)
    expect(endpoints.filter((e: string) => e === "vms/delete")).toHaveLength(1)
    expect(endpoints.filter((e: string) => e === "server/ssh_terminal")).toHaveLength(1)
    expect(endpoints.filter((e: string) => e === "vm/open_window")).toHaveLength(1)
    expect(endpoints.filter((e: string) => e === "open_app_window" || e === "open_url")).toHaveLength(0)
    expect(pyFallbackSpy).not.toHaveBeenCalled()
  })

  it("openUrl invokes Tauri open_app_window once without falling back to call_core_api", async () => {
    const invoke = vi.fn(async (cmd: string) => {
      if (cmd === "call_core_api") return { reachable: true }
      if (cmd === "open_app_window") throw "window spawn blocked"
      return undefined
    })
    ;(window as any).__TAURI_INTERNALS__ = { invoke }
    const realApi = createRealApi()

    await realApi.openUrl("http://192.168.1.50:80", "ZimaOS")

    const appWinCalls = invoke.mock.calls.filter((c: any[]) => c[0] === "open_app_window")
    const browserCalls = invoke.mock.calls.filter((c: any[]) => c[0] === "open_in_browser")
    const coreOpenUrlCalls = invoke.mock.calls.filter(
      (c: any[]) => c[0] === "call_core_api" && (c[1]?.endpoint === "open_app_window" || c[1]?.endpoint === "open_url"),
    )
    expect(appWinCalls).toHaveLength(1)
    expect(browserCalls).toHaveLength(1)
    expect(coreOpenUrlCalls).toHaveLength(0)
  })

  it("throws from loadVms, saveVms, updateVm, deleteVm, and switchServer when backend returns error payloads", async () => {
    const invoke = vi.fn(async (_cmd: string, args: any) => {
      if (args?.endpoint === "vms/load") {
        return { status: "error", message: "Backend VM registry unreachable" }
      }
      if (args?.endpoint === "vms/save") {
        return { status: "error", success: false, message: "Disk full" }
      }
      if (args?.endpoint === "vms/update") {
        return { success: false, error: "VM not found" }
      }
      if (args?.endpoint === "vms/delete") {
        return { status: "error", success: false, message: "Delete forbidden" }
      }
      if (args?.endpoint === "switch_server") {
        return { status: "error", success: false, message: "Server offline" }
      }
      return { success: true }
    })
    ;(window as any).__TAURI_INTERNALS__ = { invoke }
    const realApi = createRealApi()

    await expect(realApi.loadVms!()).rejects.toThrow("Backend VM registry unreachable")
    await expect(realApi.saveVms!([])).rejects.toThrow("Disk full")
    await expect(realApi.updateVm!("vm_1", { name: "Renamed" })).rejects.toThrow("VM not found")
    await expect(realApi.deleteVm!("vm_1", "server")).rejects.toThrow("Delete forbidden")
    await expect(realApi.switchServer("srv_2")).rejects.toThrow("Server offline")
  })

  it("isolates isAdmin across profile/server switches and never OR-leaks stale currentMetrics.isAdmin", async () => {
    let profile = "Admin"
    const invoke = vi.fn(async (_cmd: string, args: any) => {
      if (args?.endpoint === "get_state") {
        return { is_online: true, is_admin: profile === "Admin", storage_partitions: [{ name: "DATA" }] }
      }
      if (args?.endpoint === "switch_profile") {
        profile = args?.payload?.profileName || "Guest"
        return {
          serverName: "NAS",
          activeRoute: "lan",
          routes: [],
          activeProfile: profile,
          profiles: ["Admin", "Guest"],
          uptimeStr: "1h",
          isAdmin: false,
        }
      }
      if (args?.endpoint === "get_server_details") {
        return {
          serverName: "NAS",
          activeRoute: "lan",
          routes: [],
          activeProfile: profile,
          profiles: ["Admin", "Guest"],
          uptimeStr: "1h",
          isAdmin: false,
        }
      }
      return { success: true }
    })
    ;(window as any).__TAURI_INTERNALS__ = { invoke }
    const realApi = createRealApi()

    const latestMetrics: any[] = []
    const unsub = realApi.subscribeMetrics((m) => latestMetrics.push(m))
    await waitFor(() => {
      expect(latestMetrics[latestMetrics.length - 1]?.isAdmin).toBe(true)
    })

    // Switch profile -> immediately resets currentMetrics.isAdmin to false and getServerDetails respects details.isAdmin === false
    await realApi.switchProfile("Guest")
    expect(latestMetrics[latestMetrics.length - 1]?.isAdmin).toBe(false)
    expect(latestMetrics[latestMetrics.length - 1]?.storagePartitions).toBeUndefined()

    const details = await realApi.getServerDetails()
    expect(details.isAdmin).toBe(false)

    unsub()
  })

  it("retries loadSettings() during cold startup and resolves once Core Service responds", async () => {
    vi.useFakeTimers()
    let calls = 0
    const invoke = vi.fn(async (_cmd: string, args: any) => {
      if (args?.endpoint === "load_settings") {
        calls++
        if (calls < 3) {
          throw new Error("Connection refused 127.0.0.1:48123")
        }
        return { firstRunSetup: false, language: "en", theme: "light", autoCheckUpdate: false }
      }
      return {}
    })
    ;(window as any).__TAURI_INTERNALS__ = { invoke }
    const realApi = createRealApi()

    const pending = realApi.loadSettings()
    await vi.advanceTimersByTimeAsync(1000)
    const settings = await pending

    expect(calls).toBe(3)
    expect(settings.language).toBe("en")
    expect(settings.theme).toBe("light")
    expect(settings.autoCheckUpdate).toBe(false)
  })

  it("queues pendingImmediatePoll when triggerPollNow runs mid-poll and stops polling on unsubscribe", async () => {
    let resolveFirstPoll!: (v: any) => void
    let getStateCalls = 0
    const invoke = vi.fn((_cmd: string, args: any) => {
      if (args?.endpoint === "get_state") {
        getStateCalls++
        if (getStateCalls === 1) {
          return new Promise((r) => {
            resolveFirstPoll = r
          })
        }
        return Promise.resolve({ is_online: true, cpu_percent: 25, is_admin: false })
      }
      if (args?.endpoint === "switch_route") {
        return Promise.resolve({ serverName: "NAS", activeRoute: "wan", routes: [], activeProfile: "User", profiles: [], uptimeStr: "1h", isAdmin: false })
      }
      return Promise.resolve({})
    })
    ;(window as any).__TAURI_INTERNALS__ = { invoke }
    const realApi = createRealApi()

    const unsub = realApi.subscribeMetrics(() => {})
    await waitFor(() => expect(getStateCalls).toBe(1))

    // Trigger poll while first poll is still in flight
    await realApi.switchRoute("wan")
    expect(getStateCalls).toBe(1)

    // Completing the first poll must immediately trigger the queued follow-up poll
    resolveFirstPoll({ is_online: true, cpu_percent: 10, is_admin: true })
    await waitFor(() => expect(getStateCalls).toBe(2))

    unsub()
    const countAtUnsub = getStateCalls
    await new Promise((r) => setTimeout(r, 50))
    expect(getStateCalls).toBe(countAtUnsub)
  })
})

describe("Phase 09 store.tsx, shared.tsx, and SetupWizard.tsx fixes", () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    localStorage.clear()
    setCompanionApi(createMockApi())
  })

  it("serializes sequential setSetting calls without clobbering prior updates and generates unique monotonic notice IDs", async () => {
    const savedSnapshots: any[] = []
    const api: CompanionApi = createMockApi()
    const baseLoad = api.loadSettings.bind(api)
    api.loadSettings = vi.fn(async () => ({ ...(await baseLoad()), firstRunSetup: false, language: "id" as const, theme: "dark" as const }))
    api.saveSettings = vi.fn(async (s) => {
      savedSnapshots.push(s)
    })
    api.subscribeMetrics = vi.fn(() => () => {}) as unknown as CompanionApi["subscribeMetrics"]
    api.subscribePower = vi.fn(() => () => {}) as unknown as CompanionApi["subscribePower"]
    api.listDrives = vi.fn(async () => []) as unknown as CompanionApi["listDrives"]
    setCompanionApi(api)

    vi.spyOn(Date, "now").mockReturnValue(1700000000000)

    function Harness() {
      const { settings, setSetting } = useCompanion()
      const { notify, noticeHistory } = useNotice()
      return (
        <div>
          <div data-testid="settings-state">{`${settings.theme}:${settings.language}`}</div>
          <div data-testid="notice-ids">{noticeHistory.map((n) => n.id).join(",")}</div>
          <button
            onClick={() => {
              void setSetting("theme", "light")
              void setSetting("language", "en")
            }}
          >
            toggle-both
          </button>
          <button
            onClick={() => {
              notify("First", "info")
              notify("Second", "success")
            }}
          >
            notify-twice
          </button>
        </div>
      )
    }

    render(
      <NoticeProvider>
        <CompanionStoreProvider>
          <Harness />
        </CompanionStoreProvider>
      </NoticeProvider>,
    )

    await waitFor(() => expect(api.loadSettings).toHaveBeenCalled())

    fireEvent.click(screen.getByText("toggle-both"))
    await waitFor(() => {
      expect(screen.getByTestId("settings-state")).toHaveTextContent("light:en")
    })
    expect(savedSnapshots[savedSnapshots.length - 1]).toMatchObject({ theme: "light", language: "en" })

    fireEvent.click(screen.getByText("notify-twice"))
    await waitFor(() => {
      const ids = screen.getByTestId("notice-ids").textContent?.split(",").filter(Boolean) || []
      expect(ids).toHaveLength(2)
      expect(new Set(ids).size).toBe(2)
    })
  })

  it("cancels stale runWithTransition refresh loops using transitionEpochRef", async () => {
    const api: CompanionApi = createMockApi()
    const baseLoad = api.loadSettings.bind(api)
    api.loadSettings = vi.fn(async () => ({ ...(await baseLoad()), firstRunSetup: false, language: "id" as const }))
    api.subscribeMetrics = vi.fn(() => () => {}) as unknown as CompanionApi["subscribeMetrics"]
    api.subscribePower = vi.fn(() => () => {}) as unknown as CompanionApi["subscribePower"]
    let releaseStaleDrives!: (v: any) => void
    let mode: "initial" | "stale" | "fresh" = "initial"
    api.listDrives = vi.fn(() => {
      if (mode === "stale") {
        return new Promise((resolve) => {
          releaseStaleDrives = resolve
        })
      }
      if (mode === "fresh") {
        return Promise.resolve([{ letter: "Y", name: "NewServer", free: "50 GB", total: "100 GB", usedPct: 50, mounted: true }])
      }
      return Promise.resolve([])
    }) as unknown as CompanionApi["listDrives"]
    setCompanionApi(api)

    function TransitionHarness() {
      const { drives, runWithTransition } = useCompanion()
      return (
        <div>
          <div data-testid="drives-names">{drives.map((d) => d.name).join(",")}</div>
          <button
            onClick={() => {
              void runWithTransition("T1", "msg1", async () => {})
            }}
          >
            start-1
          </button>
          <button
            onClick={() => {
              void runWithTransition("T2", "msg2", async () => {})
            }}
          >
            start-2
          </button>
        </div>
      )
    }

    render(
      <NoticeProvider>
        <CompanionStoreProvider>
          <TransitionHarness />
        </CompanionStoreProvider>
      </NoticeProvider>,
    )

    await waitFor(() => expect(api.loadSettings).toHaveBeenCalled())

    mode = "stale"
    fireEvent.click(screen.getByText("start-1"))
    await waitFor(() => expect(releaseStaleDrives).toBeTypeOf("function"))

    mode = "fresh"
    fireEvent.click(screen.getByText("start-2"))
    await waitFor(() => {
      expect(screen.getByTestId("drives-names")).toHaveTextContent("NewServer")
    })

    // Resolving the superseded transition's in-flight listDrives must NOT overwrite NewServer with OldServer
    await act(async () => {
      releaseStaleDrives([{ letter: "Z", name: "OldServer", free: "10 GB", total: "100 GB", usedPct: 90, mounted: true }])
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(screen.getByTestId("drives-names")).toHaveTextContent("NewServer")
  })

  it("merges ViewBody className via cx and seeds easytierVirtualIp in createInitialDraft", () => {
    const { container } = render(
      <ViewBody className="space-y-3 custom-test-class">
        <span>body-content</span>
      </ViewBody>,
    )
    const rootDiv = container.firstElementChild as HTMLElement
    expect(rootDiv).toHaveClass("min-h-0", "flex-1", "space-y-3", "custom-test-class")
    expect(createInitialDraft().easytierVirtualIp).toBe("")
  })
})

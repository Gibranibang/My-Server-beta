import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { createRealApi } from "../api.real"
import { CompanionStoreProvider, NoticeProvider, useNotice } from "../store"
import VmManagerView from "../views/VmManagerView"
import type { VirtualMachine } from "../types"

function NoticeSpy() {
  const { notice } = useNotice()
  return (
    <div data-testid="notice-spy">
      {notice ? `${notice.tone}:${notice.text}` : ""}
    </div>
  )
}

function makeTestVm(overrides: Partial<VirtualMachine> = {}): VirtualMachine {
  return {
    id: "vm_mig_ui_1",
    name: "Dev-Node-1",
    provider: "manual",
    status: "sleeping",
    scope: "local",
    sshHost: "10.0.0.5",
    sshUser: "ubuntu",
    sshPort: 22,
    ip: "10.0.0.5",
    runtimeMinutes: 0,
    lastActive: "Sleeping",
    ...overrides,
  }
}

function setupVmView(initialVms: VirtualMachine[], migrateImpl: (...args: any[]) => Promise<any>) {
  localStorage.setItem("myserver_vms", JSON.stringify(initialVms))
  let currentRemote = initialVms.filter((v) => v.scope === "server")

  const api: CompanionApi = createMockApi()
  const baseLoadSettings = api.loadSettings.bind(api)
  api.loadSettings = vi.fn(async () => ({ ...(await baseLoadSettings()), firstRunSetup: false, language: "id" as const }))
  api.getServerDetails = vi.fn(async () => ({
    serverId: "srv_1",
    serverName: "ZimaOS-NAS",
    activeHost: "192.168.1.50",
    activeRoute: "lan",
    routes: [],
    activeProfile: "",
    profiles: [],
    uptimeStr: "",
  })) as unknown as CompanionApi["getServerDetails"]
  api.subscribeMetrics = vi.fn(() => () => {}) as unknown as CompanionApi["subscribeMetrics"]
  api.subscribePower = vi.fn(() => () => {}) as unknown as CompanionApi["subscribePower"]
  api.listDrives = vi.fn(async () => []) as unknown as CompanionApi["listDrives"]
  api.loadVms = vi.fn(async () => currentRemote)
  api.saveVms = vi.fn(async () => ({ status: "ok", success: true }))
  api.migrateVm = vi.fn(async (vmId: string, targetScope: "server" | "local", vm?: Partial<VirtualMachine>) => {
    const res = await migrateImpl(vmId, targetScope, vm)
    if (res && res.status !== "error" && res.success !== false) {
      if (targetScope === "server" && vm) {
        currentRemote = [{ ...(vm as VirtualMachine), id: vmId, scope: "server", serverId: "srv_1", serverName: "ZimaOS-NAS" }]
      } else if (targetScope === "local") {
        currentRemote = currentRemote.filter((item) => item.id !== vmId)
      }
    }
    return res
  }) as unknown as CompanionApi["migrateVm"]

  setCompanionApi(api)
  render(
    <NoticeProvider>
      <CompanionStoreProvider>
        <NoticeSpy />
        <VmManagerView go={() => {}} />
      </CompanionStoreProvider>
    </NoticeProvider>
  )
  return { api }
}

describe("VM Migration payload forwarding & rollback (MIG-03, D-03)", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    localStorage.clear()
    delete (window as any).__TAURI_INTERNALS__
    setCompanionApi(createMockApi())
  })

  it("realApi.migrateVm forwards full vm object inside call_core_api payload", async () => {
    const invoke = vi.fn(async () => ({ status: "ok", success: true }))
    ;(window as any).__TAURI_INTERNALS__ = { invoke }

    const realApi = createRealApi()
    const vmObj = makeTestVm({ id: "vm_1", scope: "server", serverId: "srv_1", serverName: "ZimaOS-NAS" })
    const res = await realApi.migrateVm!("vm_1", "server", vmObj)

    expect(res).toEqual({ status: "ok", success: true })
    expect(invoke).toHaveBeenCalledWith("call_core_api", {
      endpoint: "vms/migrate",
      payload: {
        vmId: "vm_1",
        targetScope: "server",
        vm_id: "vm_1",
        target_scope: "server",
        vm: vmObj,
      },
    })
  })

  it("rolls back localStorage and notifies danger without calling saveVms when migrateVm returns error", async () => {
    const localVm = makeTestVm({ id: "vm_err_1", name: "Local-Box", scope: "local" })
    const { api } = setupVmView([localVm], async () => ({
      status: "error",
      success: false,
      message: "Server offline",
    }))

    await screen.findByText("Local-Box")
    await waitFor(() => expect(api.getServerDetails).toHaveBeenCalled())

    fireEvent.click(screen.getByTitle("Edit"))
    const serverBtn = await screen.findByRole("button", { name: "ZimaOS-NAS" })
    fireEvent.click(serverBtn)
    fireEvent.click(screen.getByRole("button", { name: "Perbarui" }))

    await waitFor(() => {
      expect(api.migrateVm).toHaveBeenCalledWith(
        "vm_err_1",
        "server",
        expect.objectContaining({
          id: "vm_err_1",
          scope: "server",
          serverId: "srv_1",
          serverName: "ZimaOS-NAS",
        })
      )
    })

    expect(api.saveVms).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("danger:Server offline")
    })

    const storedAfterError = JSON.parse(localStorage.getItem("myserver_vms") || "[]")
    expect(storedAfterError).toHaveLength(1)
    expect(storedAfterError[0].scope).toBe("local")
    expect(storedAfterError[0].serverId).toBeUndefined()

    // Concurrent/subsequent 4s refresh returning [] from server must keep the rolled-back local VM intact
    fireEvent(window, new Event("myserver:refresh"))
    await waitFor(() => {
      const storedAfterSync = JSON.parse(localStorage.getItem("myserver_vms") || "[]")
      expect(storedAfterSync).toHaveLength(1)
      expect(storedAfterSync[0].id).toBe("vm_err_1")
      expect(storedAfterSync[0].scope).toBe("local")
    })
  })

  it("rolls back localStorage and notifies danger when migrateVm rejects", async () => {
    const localVm = makeTestVm({ id: "vm_rej_1", name: "Local-Reject-Box", scope: "local" })
    const { api } = setupVmView([localVm], async () => {
      throw new Error("IPC timeout")
    })

    await screen.findByText("Local-Reject-Box")
    await waitFor(() => expect(api.getServerDetails).toHaveBeenCalled())

    fireEvent.click(screen.getByTitle("Edit"))
    fireEvent.click(await screen.findByRole("button", { name: "ZimaOS-NAS" }))
    fireEvent.click(screen.getByRole("button", { name: "Perbarui" }))

    await waitFor(() => {
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("danger:IPC timeout")
    })
    expect(api.saveVms).not.toHaveBeenCalled()
    const stored = JSON.parse(localStorage.getItem("myserver_vms") || "[]")
    expect(stored).toHaveLength(1)
    expect(stored[0].scope).toBe("local")
  })

  it("completes Server -> Local -> Server round-trip migration with full VM payload", async () => {
    const serverVm = makeTestVm({
      id: "vm_rt_1",
      name: "RoundTrip-Box",
      scope: "server",
      serverId: "srv_1",
      serverName: "ZimaOS-NAS",
    })
    const { api } = setupVmView([serverVm], async (_vmId, targetScope, vm) => ({
      status: "ok",
      success: true,
      vm: { ...vm, scope: targetScope },
    }))

    await screen.findByText("RoundTrip-Box")
    await waitFor(() => expect(api.getServerDetails).toHaveBeenCalled())

    // Step 1: Server -> Local
    fireEvent.click(screen.getByTitle("Edit"))
    fireEvent.click(await screen.findByRole("button", { name: "Lokal" }))
    fireEvent.click(screen.getByRole("button", { name: "Perbarui" }))

    await waitFor(() => {
      expect(api.migrateVm).toHaveBeenNthCalledWith(
        1,
        "vm_rt_1",
        "local",
        expect.objectContaining({ id: "vm_rt_1", scope: "local" })
      )
    })
    await waitFor(() => {
      const storedLocal = JSON.parse(localStorage.getItem("myserver_vms") || "[]")
      expect(storedLocal[0].scope).toBe("local")
    })

    // Step 2: Local -> Server
    fireEvent.click(screen.getByTitle("Edit"))
    fireEvent.click(await screen.findByRole("button", { name: "ZimaOS-NAS" }))
    fireEvent.click(screen.getByRole("button", { name: "Perbarui" }))

    await waitFor(() => {
      expect(api.migrateVm).toHaveBeenNthCalledWith(
        2,
        "vm_rt_1",
        "server",
        expect.objectContaining({
          id: "vm_rt_1",
          scope: "server",
          serverId: "srv_1",
          serverName: "ZimaOS-NAS",
        })
      )
    })
    await waitFor(() => {
      const storedServer = JSON.parse(localStorage.getItem("myserver_vms") || "[]")
      expect(storedServer[0].scope).toBe("server")
      expect(storedServer[0].serverId).toBe("srv_1")
    })
    expect(api.saveVms).not.toHaveBeenCalled()
  })

  it("keeps legacy undefined-scope VM as local on Edit without unintended migration (CR-03)", async () => {
    const legacyLocal = makeTestVm({ id: "vm_legacy_1", name: "Legacy-Local" })
    delete (legacyLocal as any).scope
    const { api } = setupVmView([legacyLocal], async () => ({ status: "ok", success: true }))
    api.updateVm = vi.fn(async () => ({ status: "ok", success: true }))

    await screen.findByText("Legacy-Local")
    await waitFor(() => expect(api.getServerDetails).toHaveBeenCalled())

    fireEvent.click(screen.getByTitle("Edit"))
    const nameInput = await screen.findByDisplayValue("Legacy-Local")
    fireEvent.change(nameInput, { target: { value: "Legacy-Renamed" } })
    fireEvent.click(screen.getByRole("button", { name: "Perbarui" }))

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem("myserver_vms") || "[]")
      expect(stored[0].name).toBe("Legacy-Renamed")
      expect(stored[0].scope).toBe("local")
    })
    expect(api.migrateVm).not.toHaveBeenCalled()
  })

  it("locks submit button against double-click during async migration and applies res.vm (WR-01, WR-05)", async () => {
    const localVm = makeTestVm({ id: "vm_lock_1", name: "Lock-Box", scope: "local" })
    let resolveMig!: (val: any) => void
    const { api } = setupVmView([localVm], () => new Promise((r) => { resolveMig = r }))

    await screen.findByText("Lock-Box")
    await waitFor(() => expect(api.getServerDetails).toHaveBeenCalled())

    fireEvent.click(screen.getByTitle("Edit"))
    fireEvent.click(await screen.findByRole("button", { name: "ZimaOS-NAS" }))
    const submitBtn = screen.getByRole("button", { name: "Perbarui" })
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Perbarui" })).toBeDisabled()
    })
    fireEvent.click(screen.getByRole("button", { name: "Perbarui" }))
    expect(api.migrateVm).toHaveBeenCalledTimes(1)

    resolveMig({
      status: "ok",
      success: true,
      vm: { id: "vm_lock_1", name: "Lock-Box", scope: "server", serverId: "srv_auth_99", serverName: "Authoritative-NAS" },
    })

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem("myserver_vms") || "[]")
      expect(stored[0].serverId).toBe("srv_auth_99")
      expect(stored[0].serverName).toBe("Authoritative-NAS")
    })
  })

  it("invokes Tauri call_core_api only once on realApi.migrateVm rejection (WR-05)", async () => {
    const invoke = vi.fn(async () => {
      throw new Error("Core socket down")
    })
    ;(window as any).__TAURI_INTERNALS__ = { invoke }

    const realApi = createRealApi()
    const res = await realApi.migrateVm!("vm_fail_once", "server", makeTestVm({ id: "vm_fail_once" }))

    expect(invoke).toHaveBeenCalledTimes(1)
    expect(res).toEqual({ status: "error", success: false, message: "Core socket down" })
  })
})

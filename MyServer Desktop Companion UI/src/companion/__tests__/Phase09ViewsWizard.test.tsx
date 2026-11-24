import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { CompanionStoreProvider, NoticeProvider, useNotice } from "../store"
import { I18N } from "../i18n"
import type { VirtualMachine, WizardDraft } from "../types"
import { SubStepVm } from "../wizard/SubStepVm"
import { StepConnection } from "../wizard/StepConnection"
import { StepZimaLogin } from "../wizard/StepZimaLogin"
import VmManagerView from "../views/VmManagerView"
import SettingsView from "../views/SettingsView"
import FilesView from "../views/FilesView"
import BackupView from "../views/BackupView"
import { isLanRouteUrl } from "../views/PowerView"

function NoticeSpy() {
  const { notice } = useNotice()
  return (
    <div data-testid="notice-spy">
      {notice ? `${notice.tone}:${notice.text}` : ""}
    </div>
  )
}

function makeDraft(overrides: Partial<WizardDraft> = {}): WizardDraft {
  return {
    connectionMode: "lan",
    lanUrl: "http://192.168.1.50:8080",
    remoteId: "",
    connectionVerified: true,
    wanUrl: "https://nas.example.com",
    username: "admin",
    password: "secret-password",
    serverId: "srv-zima-1",
    serverName: "ZimaNAS",
    zerotierNetworkId: "",
    zerotierIp: "",
    easytierVirtualIp: "",
    step1And3Done: true,
    backendSource: "github",
    backendInstalled: true,
    backendVersion: "v1.2.3",
    syncthingDone: false,
    vmDone: false,
    ...overrides,
  }
}

function makeVm(overrides: Partial<VirtualMachine> = {}): VirtualMachine {
  return {
    id: "vm_p9_1",
    name: "Phase9-Node",
    provider: "manual",
    status: "sleeping",
    scope: "server",
    serverId: "srv_1",
    serverName: "ZimaOS-NAS",
    sshHost: "192.168.1.50",
    sshUser: "ubuntu",
    sshPort: 22,
    ip: "192.168.1.50",
    runtimeMinutes: 0,
    lastActive: "Sleeping",
    ...overrides,
  }
}

function makeBaseViewApi(overrides: Partial<CompanionApi> = {}): CompanionApi {
  const base = createMockApi()
  const baseLoadSettings = base.loadSettings.bind(base)
  return {
    ...base,
    loadSettings: vi.fn(async () => ({
      ...(await baseLoadSettings()),
      firstRunSetup: false,
      language: "id" as const,
    })),
    subscribeMetrics: vi.fn(() => () => {}) as unknown as CompanionApi["subscribeMetrics"],
    subscribePower: vi.fn((cb) => {
      cb("online")
      return () => {}
    }) as unknown as CompanionApi["subscribePower"],
    listDrives: vi.fn(async () => []) as unknown as CompanionApi["listDrives"],
    getServerDetails: vi.fn(async () => ({
      serverId: "srv_1",
      serverName: "ZimaOS-NAS",
      activeId: "srv_1",
      activeName: "ZimaOS-NAS",
      activeHost: "http://192.168.1.50:80",
      activeRoute: "lan",
      routes: [{ id: "lan", name: "LAN", url: "http://192.168.1.50:80", active: true }],
      activeProfile: "admin",
      profiles: ["admin"],
      uptimeStr: "1d",
    })) as unknown as CompanionApi["getServerDetails"],
    ...overrides,
  }
}

describe("Phase 09 Views & Wizard Regressions (FIXV-01, FIXV-04, FIXV-05)", () => {
  beforeEach(() => {
    localStorage.clear()
    setCompanionApi(createMockApi())
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    localStorage.clear()
    setCompanionApi(createMockApi())
  })

  it("SubStepVm aborts without marking vmDone when loadVms rejects", async () => {
    const loadVms = vi.fn().mockRejectedValue(new Error("Core service unreachable"))
    const saveVms = vi.fn()
    setCompanionApi({
      ...createMockApi(),
      loadVms,
      saveVms,
    })

    const onPatchDraft = vi.fn()
    const onDoneSubStep = vi.fn()

    render(
      <SubStepVm
        draft={makeDraft()}
        onPatchDraft={onPatchDraft}
        onDoneSubStep={onDoneSubStep}
        onBack={vi.fn()}
        language="id"
      />
    )

    fireEvent.click(screen.getByTestId("vm-provider-manual"))
    fireEvent.change(screen.getByLabelText(/Nama VM/i), { target: { value: "Safe-VM" } })
    fireEvent.change(screen.getByLabelText(/Host Gateway \/ IP/i), { target: { value: "192.168.1.90" } })
    fireEvent.click(screen.getByRole("button", { name: /Simpan VM/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Core service unreachable")
    expect(saveVms).not.toHaveBeenCalled()
    expect(onPatchDraft).not.toHaveBeenCalledWith({ vmDone: true })
    expect(onDoneSubStep).not.toHaveBeenCalled()
  })

  it("SubStepVm surfaces Disk error and blocks vmDone when saveVms returns error envelope", async () => {
    const loadVms = vi.fn().mockResolvedValue([])
    const saveVms = vi.fn().mockResolvedValue({
      status: "error",
      success: false,
      message: "Disk error",
    })
    setCompanionApi({
      ...createMockApi(),
      loadVms,
      saveVms,
    })

    const onPatchDraft = vi.fn()
    const onDoneSubStep = vi.fn()

    render(
      <SubStepVm
        draft={makeDraft()}
        onPatchDraft={onPatchDraft}
        onDoneSubStep={onDoneSubStep}
        onBack={vi.fn()}
        language="id"
      />
    )

    fireEvent.click(screen.getByTestId("vm-provider-manual"))
    fireEvent.change(screen.getByLabelText(/Nama VM/i), { target: { value: "Disk-Fail-VM" } })
    fireEvent.change(screen.getByLabelText(/Host Gateway \/ IP/i), { target: { value: "192.168.1.91" } })
    fireEvent.click(screen.getByRole("button", { name: /Simpan VM/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Disk error")
    expect(saveVms).toHaveBeenCalledTimes(1)
    expect(onPatchDraft).not.toHaveBeenCalledWith({ vmDone: true })
    expect(onDoneSubStep).not.toHaveBeenCalled()
  })

  it("StepConnection persists easytierVirtualIp from server_peer_ip and StepZimaLogin forwards ZeroTier + EasyTier fields into commitWizardServer", async () => {
    const startEasyTier = vi.fn().mockResolvedValue({ success: true, status: { running: true } })
    const getRemoteStatus = vi.fn().mockResolvedValue({
      activeEngine: "easytier",
      easytier: {
        running: true,
        network_name: "mesh-01",
        virtual_ip: "10.126.126.12",
        server_peer_ip: "10.126.126.1",
      },
    })
    setCompanionApi({
      ...createMockApi(),
      startEasyTier,
      getRemoteStatus,
    })

    const onPatchConn = vi.fn()
    render(
      <StepConnection
        draft={makeDraft({ connectionMode: "remote", remoteId: "a1b2c3d4e5f60708", connectionVerified: false })}
        onPatchDraft={onPatchConn}
        onNext={vi.fn()}
        onBack={vi.fn()}
        language="id"
      />
    )

    fireEvent.click(screen.getByRole("button", { name: I18N.id.wiz_test_conn }))

    await waitFor(() => {
      expect(onPatchConn).toHaveBeenCalledWith({
        remoteId: "a1b2c3d4e5f60708",
        connectionVerified: true,
        easytierVirtualIp: "10.126.126.1",
      })
    })

    cleanup()

    const verifyZimaLogin = vi.fn().mockResolvedValue({
      success: true,
      username: "admin",
      resolvedUrl: "http://192.168.1.50",
      zerotierNetworkId: "8056c2e21c000001",
      zerotierIp: "10.147.20.42",
    })
    const commitWizardServer = vi.fn().mockResolvedValue({
      success: true,
      serverId: "srv-abc123",
      name: "Homelab Utama",
    })
    setCompanionApi({
      ...createMockApi(),
      verifyZimaLogin,
      commitWizardServer,
    })

    const onNext = vi.fn()
    render(
      <StepZimaLogin
        draft={makeDraft({
          connectionMode: "remote",
          lanUrl: "",
          remoteId: "a1b2c3d4e5f60708",
          easytierVirtualIp: "10.126.126.1",
          username: "admin",
          password: "",
        })}
        onPatchDraft={vi.fn()}
        onNext={onNext}
        onBack={vi.fn()}
        language="id"
      />
    )

    fireEvent.change(screen.getByLabelText(I18N.id.wiz_password_label), {
      target: { value: "s3cr3t!" },
    })
    fireEvent.click(screen.getByRole("button", { name: I18N.id.wiz_login_btn }))

    await waitFor(() => {
      expect(commitWizardServer).toHaveBeenCalledWith(
        expect.objectContaining({
          remoteId: "a1b2c3d4e5f60708",
          zerotierNetworkId: "8056c2e21c000001",
          zerotierVirtualIp: "10.147.20.42",
          easytierVirtualIp: "10.126.126.1",
          setActive: true,
        })
      )
    })
    expect(onNext).toHaveBeenCalledTimes(1)
  })

  it("VmManagerView restores VM and emits danger notice when deleteVm returns error envelope", async () => {
    const vm = makeVm({ id: "vm_del_err", name: "Keep-Me-VM", scope: "server" })
    localStorage.setItem("myserver_vms", JSON.stringify([vm]))

    const deleteVm = vi.fn().mockResolvedValue({
      status: "error",
      success: false,
      message: "Backend error",
    })
    const loadVms = vi.fn().mockResolvedValue([vm])
    const api = makeBaseViewApi({ loadVms, deleteVm })
    setCompanionApi(api)

    render(
      <NoticeProvider>
        <CompanionStoreProvider>
          <NoticeSpy />
          <VmManagerView go={() => {}} />
        </CompanionStoreProvider>
      </NoticeProvider>
    )

    await screen.findByText("Keep-Me-VM")
    fireEvent.click(screen.getByTitle("Edit"))
    fireEvent.click(await screen.findByRole("button", { name: /Hapus Virtual Machine/i }))
    fireEvent.click(await screen.findByRole("button", { name: /^Hapus$/i }))

    await waitFor(() => {
      expect(deleteVm).toHaveBeenCalledWith("vm_del_err", "server", "srv_1")
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("danger:Backend error")
    })
    expect(await screen.findByText("Keep-Me-VM")).toBeInTheDocument()
  })

  it("SettingsView hydrates logDirInfo via api.getLogDirectory on mount and renders path", async () => {
    const getLogDirectory = vi.fn().mockResolvedValue({
      logDirectory: "D:\\CustomLogs\\MyServer",
      defaultDirectory: "C:\\Users\\Default\\Logs",
      isCustom: true,
    })
    setCompanionApi(makeBaseViewApi({ getLogDirectory }))

    render(
      <NoticeProvider>
        <CompanionStoreProvider>
          <SettingsView />
        </CompanionStoreProvider>
      </NoticeProvider>
    )

    await waitFor(() => {
      expect(getLogDirectory).toHaveBeenCalledTimes(1)
    })
    fireEvent.click(screen.getByRole("button", { name: new RegExp(I18N.id.sec_diag_logs_title, "i") }))
    expect(await screen.findByText("D:\\CustomLogs\\MyServer")).toBeInTheDocument()
  })

  it("FilesView renders double-backslash UNC prefix, BackupView strips https:// in testSyncthingTarget and resolves Inherit-LAN host, and PowerView isLanRouteUrl filters VPN subnets", async () => {
    const testSyncthingTarget = vi.fn().mockResolvedValue({ online: true, latency_ms: 12 })
    const getSyncthingConfig = vi.fn().mockResolvedValue({
      local: { port: "8384", api_key: "loc-key", auto_start: true, binary_path: "" },
      server: {
        server_name: "ZimaOS-NAS",
        route_mode: "wan",
        lan_mode: "inherit",
        lan_ip: "",
        lan_port: "8384",
        lan_https: false,
        wan_url: "https://nas.example.com/syncthing",
        wan_port: "8443",
        wan_https: true,
        api_key: "srv-key",
      },
    })
    setCompanionApi(
      makeBaseViewApi({
        getSyncthingFullStatus: vi.fn().mockResolvedValue({
          paired: false,
          local: { online: true, device_id: "DEV-LOC", pending_devices: {} },
          server: { online: true, device_id: "DEV-SRV", pending_devices: {} },
          daemon: { running: true, pid: 100 },
        }) as unknown as CompanionApi["getSyncthingFullStatus"],
        getSyncthingTasks: vi.fn().mockResolvedValue([]) as unknown as CompanionApi["getSyncthingTasks"],
        getSyncthingConfig: getSyncthingConfig as unknown as CompanionApi["getSyncthingConfig"],
        testSyncthingTarget: testSyncthingTarget as unknown as CompanionApi["testSyncthingTarget"],
      })
    )

    render(
      <NoticeProvider>
        <CompanionStoreProvider>
          <FilesView />
        </CompanionStoreProvider>
      </NoticeProvider>
    )

    expect(await screen.findByText("\\\\192.168.1.50")).toBeInTheDocument()
    cleanup()

    render(
      <NoticeProvider>
        <CompanionStoreProvider>
          <BackupView />
        </CompanionStoreProvider>
      </NoticeProvider>
    )

    fireEvent.click(await screen.findByRole("button", { name: /API Server/i }))
    await waitFor(() => {
      expect(getSyncthingConfig).toHaveBeenCalledTimes(1)
    })

    fireEvent.click(screen.getByRole("button", { name: /Uji Koneksi Target/i }))
    await waitFor(() => {
      expect(testSyncthingTarget).toHaveBeenCalledWith("https://nas.example.com:8443", true)
    })

    // Switch to LAN Inherit mode and verify it resolves serverDetails.activeHost (192.168.1.50)
    fireEvent.click(screen.getByRole("button", { name: /Hanya LAN/i }))
    fireEvent.click(screen.getByRole("button", { name: /Uji Koneksi Target/i }))
    await waitFor(() => {
      expect(testSyncthingTarget).toHaveBeenLastCalledWith("http://192.168.1.50:8384", false)
    })

    // PowerView strict LAN IP parser assertions
    expect(isLanRouteUrl("http://192.168.1.50:80")).toBe(true)
    expect(isLanRouteUrl("http://10.0.0.5:8080")).toBe(true)
    expect(isLanRouteUrl("http://172.16.10.2")).toBe(true)
    expect(isLanRouteUrl("http://zima.local")).toBe(true)
    expect(isLanRouteUrl("http://10.126.126.1:80")).toBe(false)
    expect(isLanRouteUrl("http://10.144.144.12:80")).toBe(false)
    expect(isLanRouteUrl("http://172.24.0.1")).toBe(false)
    expect(isLanRouteUrl("http://100.64.0.1")).toBe(false)
    expect(isLanRouteUrl("https://110.example.com")).toBe(false)
    expect(isLanRouteUrl("http://192.168.1.50:80", "zerotier")).toBe(false)
  })
})

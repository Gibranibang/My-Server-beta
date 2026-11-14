import React from "react"
import "@testing-library/jest-dom/vitest"
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../../api"
import type { VirtualMachine, WizardDraft } from "../../types"
import { StepFinishHub } from "../StepFinishHub"
import { SubStepSyncthing } from "../SubStepSyncthing"
import { SubStepVm } from "../SubStepVm"

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
    zerotierNetworkId: "8056c2e21c000001",
    zerotierIp: "10.147.20.42",
    step1And3Done: true,
    backendSource: "github",
    backendInstalled: true,
    backendVersion: "v1.2.3",
    syncthingDone: false,
    vmDone: false,
    ...overrides,
  }
}

describe("Wizard Step 5 Hub and Sub-steps 5a / 5b", () => {
  beforeEach(() => {
    setCompanionApi(createMockApi())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    setCompanionApi(createMockApi())
  })

  it("StepFinishHub routes to 5a/5b sub-steps and guards Buka MyServer against double-click", async () => {
    const onOpenSubStep = vi.fn()
    const onBack = vi.fn()
    let resolveComplete!: () => void
    const onComplete = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveComplete = resolve
        })
    )

    render(
      <StepFinishHub
        draft={makeDraft()}
        language="id"
        onOpenSubStep={onOpenSubStep}
        onComplete={onComplete}
        onBack={onBack}
      />
    )

    expect(screen.getByText("ZimaNAS")).toBeInTheDocument()
    expect(screen.getByText("admin")).toBeInTheDocument()
    expect(screen.getByText("Sudah Terpasang")).toBeInTheDocument()

    fireEvent.click(screen.getByTestId("hub-card-5a"))
    expect(onOpenSubStep).toHaveBeenCalledWith("5a")

    fireEvent.click(screen.getByTestId("hub-card-5b"))
    expect(onOpenSubStep).toHaveBeenCalledWith("5b")

    const completeBtn = screen.getByTestId("wizard-complete-btn")
    fireEvent.click(completeBtn)
    fireEvent.click(completeBtn)

    expect(onComplete).toHaveBeenCalledTimes(1)
    expect(completeBtn).toBeDisabled()

    resolveComplete()
    await waitFor(() => {
      expect(completeBtn).not.toBeDisabled()
    })
  })

  it("SubStepSyncthing hydrates config, redacts config.xml paths, switches routes, tests WAN, and saves with daemon start & auto-pair", async () => {
    const baseApi = createMockApi()
    const getSyncthingConfig = vi.fn().mockResolvedValue({
      success: true,
      server_id: "srv-zima-1",
      server_name: "ZimaNAS",
      local: {
        port: "8384",
        api_key: "",
        auto_start: false,
        binary_path: "C:\\Users\\Alice\\AppData\\Local\\Syncthing\\syncthing.exe",
      },
      server: {
        server_name: "ZimaNAS",
        port: "8384",
        api_key: "srv-st-key-111",
        route_mode: "auto",
        lan_ip: "192.168.1.50",
        lan_port: "8384",
        lan_https: false,
        wan_url: "nas.example.com",
        wan_port: "443",
        wan_https: true,
        remote_ip: "10.147.20.42",
        remote_port: "8384",
        remote_https: false,
      },
    })
    const detectLocalSyncthing = vi.fn().mockResolvedValue({
      detected: true,
      localPort: "8385",
      localApiKey: "local-secret-999",
      serverApiKey: "srv-st-key-222",
      message: "Loaded from C:\\Users\\Alice\\AppData\\Local\\Syncthing\\config.xml",
    })
    const testSyncthingTarget = vi.fn().mockResolvedValue({
      success: true,
      online: true,
      latency_ms: 21,
    })
    const saveSyncthingLocalConfig = vi.fn().mockResolvedValue({ success: true })
    const saveSyncthingServerRoute = vi.fn().mockResolvedValue({ success: true })
    const toggleLocalSyncthingDaemon = vi.fn().mockResolvedValue({ success: true, running: true })
    const pairLaptopAndServer = vi.fn().mockResolvedValue({ success: true, local_id: "L1", server_id: "S1" })

    const customApi: CompanionApi = {
      ...baseApi,
      getSyncthingConfig,
      detectLocalSyncthing,
      testSyncthingTarget,
      saveSyncthingLocalConfig,
      saveSyncthingServerRoute,
      toggleLocalSyncthingDaemon,
      pairLaptopAndServer,
    }
    setCompanionApi(customApi)

    const onPatchDraft = vi.fn()
    const onDoneSubStep = vi.fn()
    const onBack = vi.fn()

    const { container } = render(
      <SubStepSyncthing
        draft={makeDraft()}
        onPatchDraft={onPatchDraft}
        onDoneSubStep={onDoneSubStep}
        onBack={onBack}
        language="id"
      />
    )

    await waitFor(() => {
      expect(getSyncthingConfig).toHaveBeenCalledTimes(1)
      expect(getSyncthingConfig).toHaveBeenCalledWith()
    })

    const remoteInput = screen.getByLabelText(/IP Remote/i) as HTMLInputElement
    expect(remoteInput.value).toBe("10.147.20.42")
    expect(container.textContent).not.toContain("syncthing.exe")

    fireEvent.click(screen.getByRole("button", { name: /Cek Otomatis/i }))
    await waitFor(() => {
      expect(detectLocalSyncthing).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect((screen.getByLabelText(/Port Lokal/i) as HTMLInputElement).value).toBe("8385")
    })
    expect(container.textContent).not.toMatch(/config\.xml/i)
    expect(container.textContent).not.toContain("C:\\Users\\Alice")

    // Turn Auto-Switch Rute OFF to reveal Selalu Gunakan LAN & Selalu Gunakan Domain / WAN
    const autoSwitch = screen.getByRole("switch", { name: /Auto-Switch Rute/i })
    expect(autoSwitch).toHaveAttribute("aria-checked", "true")
    fireEvent.click(autoSwitch)

    const wanRadio = screen.getByRole("radio", { name: /Selalu Gunakan Domain \/ WAN/i })
    expect(screen.getByRole("radio", { name: /Selalu Gunakan LAN/i })).toBeInTheDocument()
    fireEvent.click(wanRadio)

    fireEvent.click(screen.getByRole("button", { name: /Test Koneksi/i }))
    await waitFor(() => {
      expect(testSyncthingTarget).toHaveBeenCalledWith("https://nas.example.com:443", true)
    })

    // Edit Remote IP and enable Auto-Start Startup (Pair Otomatis is ON by default)
    fireEvent.change(remoteInput, { target: { value: "10.147.20.99" } })
    const autoStartSwitch = screen.getByRole("switch", { name: /Jalankan Syncthing lokal otomatis/i })
    expect(autoStartSwitch).toHaveAttribute("aria-checked", "false")
    fireEvent.click(autoStartSwitch)
    expect(screen.getByRole("switch", { name: /Pair Otomatis/i })).toHaveAttribute("aria-checked", "true")

    fireEvent.click(screen.getByRole("button", { name: /Simpan & Aktifkan/i }))

    await waitFor(() => {
      expect(saveSyncthingLocalConfig).toHaveBeenCalledWith({
        port: "8385",
        api_key: "local-secret-999",
        auto_start: true,
      })
      expect(saveSyncthingServerRoute).toHaveBeenCalledWith(
        expect.objectContaining({
          route_mode: "wan",
          lan_ip: "192.168.1.50",
          remote_ip: "10.147.20.99",
          wan_url: "nas.example.com",
          wan_port: "443",
          wan_https: true,
          api_key: "srv-st-key-222",
        })
      )
      expect(toggleLocalSyncthingDaemon).toHaveBeenCalledWith("start")
      expect(pairLaptopAndServer).toHaveBeenCalledTimes(1)
      expect(onPatchDraft).toHaveBeenCalledWith({ syncthingDone: true })
      expect(onDoneSubStep).toHaveBeenCalledTimes(1)
    })
  })

  it("SubStepVm switches provider, scope, and screenOpenTarget without emitting invalid provider", async () => {
    const baseApi = createMockApi()
    const existingVm: VirtualMachine = {
      id: "vm-existing-1",
      name: "Existing-VM",
      provider: "custom",
      status: "stopped",
      scope: "server",
      sshPort: 22,
    }
    const loadVms = vi.fn().mockResolvedValue([existingVm])
    const saveVms = vi.fn().mockResolvedValue({ success: true })
    const syncInstaBoxVm = vi.fn().mockResolvedValue({ success: true })

    setCompanionApi({
      ...baseApi,
      loadVms,
      saveVms,
      syncInstaBoxVm,
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
    fireEvent.click(screen.getByTestId("vm-scope-local"))

    fireEvent.change(screen.getByLabelText(/Nama VM/i), { target: { value: "Dev-Node" } })
    fireEvent.change(screen.getByLabelText(/SSH Host/i), { target: { value: "192.168.1.90" } })
    fireEvent.change(screen.getByLabelText(/SSH Port/i), { target: { value: "22" } })
    fireEvent.change(screen.getByLabelText(/Username SSH/i), { target: { value: "ubuntu" } })
    fireEvent.change(screen.getByLabelText(/URL VM Web/i), { target: { value: "https://vnc.local:6080" } })
    fireEvent.change(screen.getByLabelText(/Mode Buka Layar Virtual/i), { target: { value: "window" } })

    fireEvent.click(screen.getByRole("button", { name: /Simpan VM/i }))

    await waitFor(() => {
      expect(saveVms).toHaveBeenCalledTimes(1)
    })

    const savedPayload = saveVms.mock.calls[0][0] as VirtualMachine[]
    expect(savedPayload).toHaveLength(2)
    expect(savedPayload[1]).toEqual(
      expect.objectContaining({
        name: "Dev-Node",
        provider: "manual",
        scope: "local",
        sshHost: "192.168.1.90",
        sshPort: 22,
        sshUser: "ubuntu",
        screenUrl: "https://vnc.local:6080",
        screenOpenTarget: "window",
      })
    )
    expect(syncInstaBoxVm).not.toHaveBeenCalled()
    expect(onPatchDraft).toHaveBeenCalledWith({ vmDone: true })
    expect(onDoneSubStep).toHaveBeenCalledTimes(1)
  })

  it("SubStepVm prevents duplicate VMs on rapid double-click and invokes syncInstaBoxVm for instabox", async () => {
    const baseApi = createMockApi()
    const loadVms = vi.fn().mockResolvedValue([])
    let resolveSave!: () => void
    const saveVms = vi.fn(
      () =>
        new Promise<{ success: boolean }>((resolve) => {
          resolveSave = () => resolve({ success: true })
        })
    )
    const syncInstaBoxVm = vi.fn().mockResolvedValue({ success: true })

    setCompanionApi({
      ...baseApi,
      loadVms,
      saveVms,
      syncInstaBoxVm,
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

    fireEvent.click(screen.getByTestId("vm-scope-server"))
    fireEvent.change(screen.getByLabelText(/Nama VM/i), { target: { value: "AI-Runner" } })
    fireEvent.change(screen.getByLabelText(/API Key InstaBox/i), { target: { value: "ibx_live_key_123" } })
    fireEvent.change(screen.getByLabelText(/Mode Buka Layar Virtual/i), { target: { value: "browser" } })

    const saveBtn = screen.getByRole("button", { name: /Simpan VM/i })
    fireEvent.click(saveBtn)
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(saveVms).toHaveBeenCalledTimes(1)
    })

    resolveSave()

    await waitFor(() => {
      expect(syncInstaBoxVm).toHaveBeenCalledTimes(1)
      expect(syncInstaBoxVm).toHaveBeenCalledWith(
        expect.objectContaining({
          apiKey: "ibx_live_key_123",
          vmName: "AI-Runner",
          vmId: expect.any(String),
          scope: "server",
          serverId: "srv-zima-1",
        })
      )
      expect(onPatchDraft).toHaveBeenCalledWith({ vmDone: true })
      expect(onDoneSubStep).toHaveBeenCalledTimes(1)
    })
  })
})

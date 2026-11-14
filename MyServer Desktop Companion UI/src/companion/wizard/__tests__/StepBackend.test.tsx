import { useState } from "react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { StepBackend } from "../StepBackend"
import { createMockApi, setCompanionApi, type CompanionApi } from "../../api"
import { I18N, type Language } from "../../i18n"
import type { WizardDraft } from "../../types"

function makeDraft(overrides: Partial<WizardDraft> = {}): WizardDraft {
  return {
    connectionMode: "lan",
    lanUrl: "http://192.168.1.50",
    remoteId: "",
    connectionVerified: true,
    wanUrl: "",
    username: "admin",
    password: "",
    serverId: "srv-1",
    serverName: "Homelab",
    zerotierNetworkId: "",
    zerotierIp: "",
    step1And3Done: true,
    backendSource: "github",
    backendInstalled: false,
    backendVersion: "",
    syncthingDone: false,
    vmDone: false,
    ...overrides,
  }
}

function BackendHarness({
  initialDraft,
  language = "id",
  onNext = vi.fn(),
  onBack = vi.fn(),
  onPatchSpy,
  onErrorChange = vi.fn(),
}: {
  initialDraft?: Partial<WizardDraft>
  language?: Language
  onNext?: () => void
  onBack?: () => void
  onPatchSpy?: (patch: Partial<WizardDraft>) => void
  onErrorChange?: (hasError: boolean) => void
}) {
  const [draft, setDraft] = useState<WizardDraft>(() => makeDraft(initialDraft))
  const handlePatch = (patch: Partial<WizardDraft>) => {
    onPatchSpy?.(patch)
    setDraft(prev => ({ ...prev, ...patch }))
  }

  return (
    <StepBackend
      draft={draft}
      onPatchDraft={handlePatch}
      onNext={onNext}
      onBack={onBack}
      language={language}
      onErrorChange={onErrorChange}
    />
  )
}

describe("StepBackend (Step 4)", () => {
  let mockApi: CompanionApi

  beforeEach(() => {
    mockApi = createMockApi()
    setCompanionApi(mockApi)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    setCompanionApi(createMockApi())
  })

  it("renders 2-row kv-list summary and hides inline SSH inputs until Ubah is clicked", async () => {
    mockApi.getBackendStatus = vi.fn().mockResolvedValue({ online: false })

    render(<BackendHarness />)

    expect(await screen.findByText(I18N.id.wiz_backend_not_installed)).toBeInTheDocument()
    expect(screen.getByText(I18N.id.wiz_kv_server)).toBeInTheDocument()
    expect(screen.getByText(I18N.id.wiz_kv_ssh)).toBeInTheDocument()
    expect(screen.getByText(/Homelab/)).toBeInTheDocument()
    expect(screen.getByText(/admin@192\.168\.1\.50/)).toBeInTheDocument()

    expect(screen.queryByLabelText(I18N.id.wiz_ssh_host_label)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(I18N.id.wiz_ssh_port_label)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(I18N.id.wiz_ssh_user_label)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(I18N.id.wiz_ssh_pass_label)).not.toBeInTheDocument()
  })

  it("expands inline SSH fields on Ubah click, forwards SSH overrides, and wipes transient sshPassword", async () => {
    mockApi.getBackendStatus = vi.fn().mockResolvedValue({ online: false })
    const actionSpy = vi.fn().mockResolvedValue({
      success: true,
      version: "4.2.0",
    })
    mockApi.triggerBackendAction = actionSpy

    render(<BackendHarness />)
    expect(await screen.findByText(I18N.id.wiz_backend_not_installed)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: I18N.id.wiz_edit_ssh }))

    const hostInput = screen.getByLabelText(I18N.id.wiz_ssh_host_label) as HTMLInputElement
    const portInput = screen.getByLabelText(I18N.id.wiz_ssh_port_label) as HTMLInputElement
    const userInput = screen.getByLabelText(I18N.id.wiz_ssh_user_label) as HTMLInputElement
    const passInput = screen.getByLabelText(I18N.id.wiz_ssh_pass_label) as HTMLInputElement

    fireEvent.change(hostInput, { target: { value: "10.147.20.9" } })
    fireEvent.change(portInput, { target: { value: "2222" } })
    fireEvent.change(userInput, { target: { value: "root" } })
    fireEvent.change(passInput, { target: { value: "ssh-secret-pw" } })

    fireEvent.click(screen.getByRole("button", { name: I18N.id.wiz_install_backend }))

    await waitFor(() => {
      expect(actionSpy).toHaveBeenCalledWith("install", "srv-1", {
        source: "github",
        sshHost: "10.147.20.9",
        sshPort: 2222,
        sshUser: "root",
        sshPassword: "ssh-secret-pw",
      })
    })

    expect(await screen.findByText(new RegExp(I18N.id.wiz_backend_ok))).toBeInTheDocument()
    expect(passInput.value).toBe("")
  })

  it("toggles deploy source between GitHub Release and Paket Lokal and passes bundle to triggerBackendAction", async () => {
    mockApi.getBackendStatus = vi.fn().mockResolvedValue({ online: false })
    const actionSpy = vi.fn().mockResolvedValue({ success: true, version: "4.2.0" })
    mockApi.triggerBackendAction = actionSpy
    const onPatchSpy = vi.fn()

    render(<BackendHarness onPatchSpy={onPatchSpy} />)
    expect(await screen.findByText(I18N.id.wiz_backend_not_installed)).toBeInTheDocument()

    const bundleBtn = screen.getByRole("button", { name: I18N.id.wiz_source_bundle })
    fireEvent.click(bundleBtn)
    expect(onPatchSpy).toHaveBeenCalledWith({ backendSource: "bundle" })

    fireEvent.click(screen.getByRole("button", { name: I18N.id.wiz_install_backend }))

    await waitFor(() => {
      expect(actionSpy).toHaveBeenCalledWith("install", "srv-1", {
        source: "bundle",
      })
    })
  })

  it("detects current backend via compareSemver (Sudah Terpasang + Lanjut) and outdated backend (Update Tersedia -> update)", async () => {
    mockApi.getBackendStatus = vi.fn().mockResolvedValue({
      online: true,
      version: "4.0.0",
      latestVersion: "4.0.0",
    })
    const onNext = vi.fn()

    const { unmount } = render(<BackendHarness onNext={onNext} />)
    expect(await screen.findByText(new RegExp(I18N.id.wiz_backend_installed))).toBeInTheDocument()

    const nextBtn = screen.getByRole("button", { name: I18N.id.wiz_next })
    expect(nextBtn).toBeEnabled()
    fireEvent.click(nextBtn)
    expect(onNext).toHaveBeenCalledTimes(1)

    unmount()

    mockApi.getBackendStatus = vi.fn().mockResolvedValue({
      online: true,
      version: "3.9.0",
      latestVersion: "4.0.0",
    })
    const actionSpy = vi.fn().mockResolvedValue({ success: true, version: "4.0.0" })
    mockApi.triggerBackendAction = actionSpy

    render(<BackendHarness />)
    expect(await screen.findByText(new RegExp(I18N.id.wiz_backend_update_avail))).toBeInTheDocument()

    const updateBtn = screen.getByRole("button", { name: I18N.id.wiz_update_backend })
    fireEvent.click(updateBtn)

    await waitFor(() => {
      expect(actionSpy).toHaveBeenCalledWith("update", "srv-1", {
        source: "github",
      })
    })
  })

  it("shows human-friendly stages without raw stdout, prevents double-submit, auto-opens Ubah on authFailed, and skips cleanly", async () => {
    mockApi.getBackendStatus = vi.fn().mockResolvedValue({ online: false })

    let resolveAction!: (v: any) => void
    const actionSpy = vi.fn().mockImplementation(
      () =>
        new Promise(resolve => {
          resolveAction = resolve
        })
    )
    mockApi.triggerBackendAction = actionSpy

    const onNext = vi.fn()
    render(<BackendHarness onNext={onNext} />)
    expect(await screen.findByText(I18N.id.wiz_backend_not_installed)).toBeInTheDocument()

    const installBtn = screen.getByRole("button", { name: I18N.id.wiz_install_backend })
    fireEvent.click(installBtn)
    fireEvent.click(installBtn)

    await waitFor(() => {
      expect(actionSpy).toHaveBeenCalledTimes(1)
    })

    expect(screen.getByText(I18N.id.wiz_backend_stage_connect)).toBeInTheDocument()
    expect(screen.queryByText(/chmod|systemctl|tar -xzf/i)).not.toBeInTheDocument()

    resolveAction({
      success: false,
      authFailed: true,
      message: "SSH permission denied",
    })

    expect(await screen.findByRole("alert")).toHaveTextContent(I18N.id.wiz_backend_auth_err)
    expect(screen.getByLabelText(I18N.id.wiz_ssh_host_label)).toBeInTheDocument()
    expect(screen.getByLabelText(I18N.id.wiz_ssh_pass_label)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: I18N.id.wiz_skip }))
    expect(onNext).toHaveBeenCalledTimes(1)
    expect(actionSpy).toHaveBeenCalledTimes(1)
  })
})

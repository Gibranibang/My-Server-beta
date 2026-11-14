import { useState } from "react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { StepConnection } from "../StepConnection"
import { StepWanDomain } from "../StepWanDomain"
import { StepZimaLogin } from "../StepZimaLogin"
import { createMockApi, setCompanionApi } from "../../api"
import { I18N, type Language } from "../../i18n"
import type { CompanionApi, WizardDraft } from "../../types"

function makeDraft(overrides: Partial<WizardDraft> = {}): WizardDraft {
  return {
    connectionMode: "lan",
    lanUrl: "",
    remoteId: "",
    connectionVerified: false,
    wanUrl: "",
    username: "",
    password: "",
    serverId: "",
    serverName: "My Server",
    zerotierNetworkId: "",
    zerotierIp: "",
    step1And3Done: false,
    backendSource: "github",
    backendInstalled: false,
    backendVersion: "",
    syncthingDone: false,
    vmDone: false,
    ...overrides,
  }
}

function Harness({
  step,
  initialDraft,
  language = "id",
  onNext = vi.fn(),
  onBack = vi.fn(),
  onPatchSpy,
  onErrorChange = vi.fn(),
}: {
  step: 1 | 2 | 3
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

  if (step === 1) {
    return (
      <StepConnection
        draft={draft}
        onPatchDraft={handlePatch}
        onNext={onNext}
        onBack={onBack}
        language={language}
        onErrorChange={onErrorChange}
      />
    )
  }
  if (step === 2) {
    return (
      <StepWanDomain
        draft={draft}
        onPatchDraft={handlePatch}
        onNext={onNext}
        onBack={onBack}
        language={language}
        onErrorChange={onErrorChange}
      />
    )
  }
  return (
    <StepZimaLogin
      draft={draft}
      onPatchDraft={handlePatch}
      onNext={onNext}
      onBack={onBack}
      language={language}
      onErrorChange={onErrorChange}
    />
  )
}

describe("Wizard Steps 1-3", () => {
  let mockApi: CompanionApi

  beforeEach(() => {
    mockApi = createMockApi()
    setCompanionApi(mockApi)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    setCompanionApi(null)
  })

  describe("StepConnection (Step 1)", () => {
    it("normalizes raw LAN IP to http://, calls probeUrl, unlocks Next, and advances", async () => {
      const probeSpy = vi.fn().mockResolvedValue({
        reachable: true,
        latency_ms: 14,
        url: "http://192.168.1.50",
      })
      mockApi.probeUrl = probeSpy
      const onNext = vi.fn()
      const onPatchSpy = vi.fn()

      render(<Harness step={1} onNext={onNext} onPatchSpy={onPatchSpy} />)

      const nextBtn = screen.getByRole("button", { name: I18N.id.wiz_next })
      expect(nextBtn).toBeDisabled()

      const lanInput = screen.getByLabelText(I18N.id.wiz_lan_label)
      fireEvent.change(lanInput, { target: { value: "192.168.1.50" } })

      const testBtn = screen.getByRole("button", { name: I18N.id.wiz_test_conn })
      expect(testBtn).toBeEnabled()
      fireEvent.click(testBtn)

      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith("http://192.168.1.50")
      })

      expect(await screen.findByText(new RegExp(I18N.id.wiz_conn_ok))).toBeInTheDocument()
      expect(onPatchSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          lanUrl: "http://192.168.1.50",
          connectionVerified: true,
        })
      )
      expect(nextBtn).toBeEnabled()

      fireEvent.click(nextBtn)
      expect(onNext).toHaveBeenCalledTimes(1)
    })

    it("keeps Next disabled and surfaces inline error when LAN reachability fails", async () => {
      mockApi.probeUrl = vi.fn().mockResolvedValue({
        reachable: false,
        error: "Connection refused",
      })

      render(<Harness step={1} initialDraft={{ lanUrl: "http://192.168.1.99" }} />)

      const testBtn = screen.getByRole("button", { name: I18N.id.wiz_test_conn })
      fireEvent.click(testBtn)

      expect(await screen.findByRole("alert")).toHaveTextContent(/Connection refused|Server tidak/)
      expect(screen.getByRole("button", { name: I18N.id.wiz_next })).toBeDisabled()
    })

    it("switches to Remote ID, validates 16-hex format, shows UAC note, and runs EasyTier test", async () => {
      const startEtSpy = vi.fn().mockResolvedValue({ success: true, status: { running: true } })
      const remoteStatusSpy = vi.fn().mockResolvedValue({
        activeEngine: "easytier",
        easytier: { running: true, network_name: "mesh-01", virtual_ip: "10.144.144.12" },
      })
      mockApi.startEasyTier = startEtSpy
      mockApi.getRemoteStatus = remoteStatusSpy
      const onErrorChange = vi.fn()
      const onPatchSpy = vi.fn()

      render(<Harness step={1} onErrorChange={onErrorChange} onPatchSpy={onPatchSpy} />)

      const remoteTab = screen.getByRole("button", { name: I18N.id.wiz_conn_remote })
      fireEvent.click(remoteTab)

      expect(screen.getByText(I18N.id.wiz_uac_notice)).toBeInTheDocument()

      const remoteInput = screen.getByLabelText(I18N.id.wiz_remote_label)
      const testBtn = screen.getByRole("button", { name: I18N.id.wiz_test_conn })
      const nextBtn = screen.getByRole("button", { name: I18N.id.wiz_next })

      fireEvent.change(remoteInput, { target: { value: "zzzz12345" } })
      expect(screen.getByRole("alert")).toHaveTextContent(I18N.id.wiz_remote_invalid)
      expect(onErrorChange).toHaveBeenCalledWith(true)
      expect(testBtn).toBeDisabled()
      expect(nextBtn).toBeDisabled()

      fireEvent.change(remoteInput, { target: { value: "A1B2C3D4E5F60708" } })
      expect(testBtn).toBeEnabled()
      fireEvent.click(testBtn)

      await waitFor(() => {
        expect(startEtSpy).toHaveBeenCalledWith({ remote_id: "a1b2c3d4e5f60708" })
        expect(remoteStatusSpy).toHaveBeenCalledTimes(1)
      })

      expect(onPatchSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          remoteId: "a1b2c3d4e5f60708",
          connectionVerified: true,
        })
      )
      expect(nextBtn).toBeEnabled()
    })
  })

  describe("StepWanDomain (Step 2)", () => {
    it("rejects malformed scheme or unparseable URL and disables Next", () => {
      const onErrorChange = vi.fn()
      render(<Harness step={2} onErrorChange={onErrorChange} />)

      const wanInput = screen.getByLabelText(I18N.id.wiz_wan_label)
      const nextBtn = screen.getByRole("button", { name: I18N.id.wiz_next })
      const testBtn = screen.getByRole("button", { name: I18N.id.wiz_test_domain })

      fireEvent.change(wanInput, { target: { value: "ftp://bad.example.com" } })
      expect(screen.getByRole("alert")).toHaveTextContent(I18N.id.wiz_wan_invalid)
      expect(onErrorChange).toHaveBeenCalledWith(true)
      expect(nextBtn).toBeDisabled()
      expect(testBtn).toBeDisabled()

      fireEvent.change(wanInput, { target: { value: "not a domain" } })
      expect(screen.getByRole("alert")).toHaveTextContent(I18N.id.wiz_wan_invalid)
      expect(nextBtn).toBeDisabled()
    })

    it("allows skipping WAN step via Lewati even after typing text and clears wanUrl", () => {
      const onNext = vi.fn()
      const onPatchSpy = vi.fn()
      render(
        <Harness
          step={2}
          initialDraft={{ wanUrl: "ftp://invalid" }}
          onNext={onNext}
          onPatchSpy={onPatchSpy}
        />
      )

      const skipBtn = screen.getByRole("button", { name: I18N.id.wiz_skip })
      fireEvent.click(skipBtn)

      expect(onPatchSpy).toHaveBeenCalledWith({ wanUrl: "" })
      expect(onNext).toHaveBeenCalledTimes(1)
    })

    it("tests valid HTTPS domain with probeUrl and advances with trimmed wanUrl", async () => {
      const probeSpy = vi.fn().mockResolvedValue({ reachable: true, status: 200 })
      mockApi.probeUrl = probeSpy
      const onNext = vi.fn()
      const onPatchSpy = vi.fn()

      render(<Harness step={2} onNext={onNext} onPatchSpy={onPatchSpy} />)

      const wanInput = screen.getByLabelText(I18N.id.wiz_wan_label)
      fireEvent.change(wanInput, { target: { value: "  https://nas.example.com  " } })

      const testBtn = screen.getByRole("button", { name: I18N.id.wiz_test_domain })
      fireEvent.click(testBtn)

      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith("https://nas.example.com")
      })
      expect(await screen.findByText(I18N.id.wiz_wan_ok)).toBeInTheDocument()

      const nextBtn = screen.getByRole("button", { name: I18N.id.wiz_next })
      fireEvent.click(nextBtn)

      expect(onPatchSpy).toHaveBeenCalledWith({ wanUrl: "https://nas.example.com" })
      expect(onNext).toHaveBeenCalledTimes(1)
    })
  })

  describe("StepZimaLogin (Step 3)", () => {
    it("has no skip button, shows DPAPI+SSH note, and toggles password visibility", () => {
      render(<Harness step={3} initialDraft={{ lanUrl: "http://192.168.1.50" }} />)

      expect(screen.queryByRole("button", { name: I18N.id.wiz_skip })).not.toBeInTheDocument()
      expect(screen.getByText(I18N.id.wiz_dpapi_note)).toBeInTheDocument()

      const passInput = screen.getByLabelText(I18N.id.wiz_password_label) as HTMLInputElement
      expect(passInput.type).toBe("password")

      const toggleBtn = screen.getByRole("button", { name: I18N.id.wiz_show_password })
      fireEvent.click(toggleBtn)
      expect(passInput.type).toBe("text")

      const hideBtn = screen.getByRole("button", { name: I18N.id.wiz_hide_password })
      fireEvent.click(hideBtn)
      expect(passInput.type).toBe("password")
    })

    it("surfaces verification failure without calling commitWizardServer or onNext", async () => {
      const verifySpy = vi.fn().mockResolvedValue({
        success: false,
        error: "Invalid ZimaOS credentials",
      })
      const commitSpy = vi.fn()
      mockApi.verifyZimaLogin = verifySpy
      mockApi.commitWizardServer = commitSpy
      const onNext = vi.fn()

      render(
        <Harness
          step={3}
          initialDraft={{ lanUrl: "http://192.168.1.50" }}
          onNext={onNext}
        />
      )

      fireEvent.change(screen.getByLabelText(I18N.id.wiz_username_label), {
        target: { value: "admin" },
      })
      fireEvent.change(screen.getByLabelText(I18N.id.wiz_password_label), {
        target: { value: "wrong-pass" },
      })

      fireEvent.click(screen.getByRole("button", { name: I18N.id.wiz_login_btn }))

      expect(await screen.findByRole("alert")).toHaveTextContent("Invalid ZimaOS credentials")
      expect(commitSpy).not.toHaveBeenCalled()
      expect(onNext).not.toHaveBeenCalled()
    })

    it("disables submit while in-flight, calls verify then commit, propagates ZeroTier fields, clears password, and writes zero browser storage", async () => {
      let resolveVerify!: (val: any) => void
      const verifySpy = vi.fn().mockImplementation(
        () =>
          new Promise(resolve => {
            resolveVerify = resolve
          })
      )
      const commitSpy = vi.fn().mockResolvedValue({
        success: true,
        serverId: "srv-abc123",
        name: "Homelab Utama",
        zerotierNetworkId: "8056c2e21c000001",
        zerotierVirtualIp: "10.147.20.42",
      })
      mockApi.verifyZimaLogin = verifySpy
      mockApi.commitWizardServer = commitSpy

      const localSetSpy = vi.spyOn(Storage.prototype, "setItem")
      const onNext = vi.fn()
      const onPatchSpy = vi.fn()

      render(
        <Harness
          step={3}
          initialDraft={{
            connectionMode: "lan",
            lanUrl: "http://192.168.1.50",
            wanUrl: "https://nas.example.com",
            serverName: "Homelab Utama",
          }}
          onNext={onNext}
          onPatchSpy={onPatchSpy}
        />
      )

      fireEvent.change(screen.getByLabelText(I18N.id.wiz_username_label), {
        target: { value: "admin" },
      })
      const passInput = screen.getByLabelText(I18N.id.wiz_password_label) as HTMLInputElement
      fireEvent.change(passInput, { target: { value: "s3cr3t!" } })

      const submitBtn = screen.getByRole("button", { name: I18N.id.wiz_login_btn })
      fireEvent.click(submitBtn)

      await waitFor(() => {
        expect(verifySpy).toHaveBeenCalledTimes(1)
      })
      expect(
        screen.getByRole("button", { name: I18N.id.wiz_verifying_login })
      ).toBeDisabled()

      resolveVerify({
        success: true,
        username: "admin",
        resolvedUrl: "http://192.168.1.50",
        zerotierNetworkId: "8056c2e21c000001",
        zerotierIp: "10.147.20.42",
      })

      await waitFor(() => {
        expect(commitSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            name: "Homelab Utama",
            localUrl: "http://192.168.1.50",
            wanUrl: "https://nas.example.com",
            username: "admin",
            password: "s3cr3t!",
            sshUser: "admin",
            setActive: true,
          })
        )
      })

      expect(onPatchSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          serverId: "srv-abc123",
          serverName: "Homelab Utama",
          username: "admin",
          password: "",
          zerotierNetworkId: "8056c2e21c000001",
          zerotierIp: "10.147.20.42",
          step1And3Done: true,
        })
      )
      expect(passInput.value).toBe("")
      expect(onNext).toHaveBeenCalledTimes(1)
      expect(localSetSpy).not.toHaveBeenCalled()
    })
  })
})

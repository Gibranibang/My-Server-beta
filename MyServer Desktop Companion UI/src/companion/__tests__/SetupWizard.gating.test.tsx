import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import CompanionApp from "../../CompanionApp"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import type { WizardStepProps } from "../wizard/StepConnection"

// Step bodies are covered by their own suites (WizardSteps123 / StepBackend / SubSteps5ab);
// here they are reduced to navigation stubs so the gating/orchestration is tested in isolation.
vi.mock("../wizard/StepConnection", () => ({
  StepConnection: ({ draft, onNext }: WizardStepProps) => (
    <div data-testid="stub-step-1">
      <span data-testid="draft-server-id">{draft.serverId}</span>
      <button onClick={onNext}>next-1</button>
    </div>
  ),
  normalizeLanUrl: (v: string) => v,
}))
vi.mock("../wizard/StepWanDomain", () => ({
  StepWanDomain: ({ onNext }: WizardStepProps) => (
    <div data-testid="stub-step-2">
      <button onClick={onNext}>next-2</button>
    </div>
  ),
  validateWanUrl: (v: string) => ({ valid: true, normalized: v }),
}))
vi.mock("../wizard/StepZimaLogin", () => ({
  StepZimaLogin: ({ onPatchDraft, onNext }: WizardStepProps) => (
    <div data-testid="stub-step-3">
      <button
        onClick={() => {
          onPatchDraft({ step1And3Done: true, serverId: "srv_committed" })
          onNext()
        }}
      >
        next-3
      </button>
    </div>
  ),
}))
vi.mock("../wizard/StepBackend", () => ({
  StepBackend: ({ draft, onNext }: WizardStepProps) => (
    <div data-testid="stub-step-4">
      <span data-testid="draft-server-id-4">{draft.serverId}</span>
      <button onClick={onNext}>next-4</button>
    </div>
  ),
  compareSemver: () => 0,
}))
vi.mock("../wizard/SubStepSyncthing", () => ({
  SubStepSyncthing: ({ onBack }: { onBack: () => void }) => (
    <div data-testid="stub-sub-5a">
      <button onClick={onBack}>back-5a</button>
    </div>
  ),
}))
vi.mock("../wizard/SubStepVm", () => ({
  SubStepVm: ({ onBack }: { onBack: () => void }) => (
    <div data-testid="stub-sub-5b">
      <button onClick={onBack}>back-5b</button>
    </div>
  ),
}))

function setup(firstRunSetup: boolean) {
  const api: CompanionApi = createMockApi()
  const base = api.loadSettings.bind(api)
  api.loadSettings = vi.fn(async () => ({ ...(await base()), firstRunSetup, language: "id" as const }))
  api.getServerDetails = vi.fn(async () => ({
    serverId: "srv_active",
    serverName: "Active NAS",
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
  api.setWizardMode = vi.fn(async () => {})
  api.hideWindow = vi.fn(async () => {})
  api.completeWizard = vi.fn(async () => ({ success: true })) as unknown as CompanionApi["completeWizard"]
  setCompanionApi(api)
  return api
}

async function waitForWizard() {
  await screen.findByTestId("setup-wizard")
}

describe("SetupWizard first-run gating (WIZ-01, WIZ-02, WIZ-06, D-04..D-06, T-03-09)", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/")
  })
  afterEach(() => {
    vi.restoreAllMocks()
    window.history.replaceState({}, "", "/")
    setCompanionApi(createMockApi())
  })

  it("firstRunSetup=true mounts the wizard inside both providers and suspends telemetry", async () => {
    const api = setup(true)
    render(<CompanionApp />)
    await waitForWizard()
    expect(screen.getByTestId("stub-step-1")).toBeInTheDocument()
    // Wizard children call useCompanion() + useNotice(); reaching here means neither threw.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(api.subscribeMetrics).not.toHaveBeenCalled()
    expect(api.subscribePower).not.toHaveBeenCalled()
    expect(api.listDrives).not.toHaveBeenCalled()
  })

  it("firstRunSetup=false skips the wizard and boots the dashboard", async () => {
    const api = setup(false)
    render(<CompanionApp />)
    await waitFor(() => expect(api.subscribeMetrics).toHaveBeenCalled())
    expect(screen.queryByTestId("setup-wizard")).not.toBeInTheDocument()
    expect(screen.queryByTestId("wizard-boot-loading")).not.toBeInTheDocument()
  })

  it("close × before Step 1+3 shows the guard toast, stays mounted and never hides the window", async () => {
    const api = setup(true)
    render(<CompanionApp />)
    await waitForWizard()
    fireEvent.click(screen.getByRole("button", { name: /Setup Wizard/ }))
    expect(await screen.findByText("Selesaikan koneksi & login dulu")).toBeInTheDocument()
    expect(screen.getByTestId("setup-wizard")).toBeInTheDocument()
    expect(api.hideWindow).not.toHaveBeenCalled()
  })

  it("Settings re-entry seeds the active serverId and × resets wizard mode before hiding", async () => {
    window.history.replaceState({}, "", "/?view=settings")
    const api = setup(false)
    render(<CompanionApp />)
    await waitFor(() => expect(api.subscribeMetrics).toHaveBeenCalled())

    let openBtn = screen.queryByTestId("settings-open-wizard")
    if (!openBtn) {
      const header = await screen.findByText("Bahasa & Keamanan Vault")
      fireEvent.click(header)
      openBtn = await screen.findByTestId("settings-open-wizard")
    }
    fireEvent.click(openBtn)
    await waitForWizard()
    expect(api.setWizardMode).toHaveBeenCalledWith(true, 460, 560)
    await waitFor(() => expect(screen.getByTestId("draft-server-id")).toHaveTextContent("srv_active"))

    fireEvent.click(screen.getByRole("button", { name: /Setup Wizard/ }))
    await waitFor(() => expect(api.hideWindow).toHaveBeenCalled())
    expect(api.setWizardMode).toHaveBeenCalledWith(false)
    const calls = (api.setWizardMode as ReturnType<typeof vi.fn>).mock.calls
    expect(calls[calls.length - 1]).toEqual([false])
    await waitFor(() => expect(screen.queryByTestId("setup-wizard")).not.toBeInTheDocument())
  })

  it("switches window size for 5a/5b and Buka MyServer completes then resumes telemetry", async () => {
    const api = setup(true)
    render(<CompanionApp />)
    await waitForWizard()
    fireEvent.click(screen.getByText("next-1"))
    fireEvent.click(screen.getByText("next-2"))
    fireEvent.click(screen.getByText("next-3"))
    expect(await screen.findByTestId("stub-step-4")).toBeInTheDocument()
    expect(screen.getByTestId("draft-server-id-4")).toHaveTextContent("srv_committed")
    fireEvent.click(screen.getByText("next-4"))
    fireEvent.click(await screen.findByTestId("hub-card-5a"))
    await screen.findByTestId("stub-sub-5a")
    expect(api.setWizardMode).toHaveBeenCalledWith(true, 540, 620)
    fireEvent.click(screen.getByText("back-5a"))
    await screen.findByTestId("wizard-step-5")
    await waitFor(() => {
      const calls = (api.setWizardMode as ReturnType<typeof vi.fn>).mock.calls
      expect(calls[calls.length - 1]).toEqual([true, 460, 560])
    })
    expect(api.subscribeMetrics).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId("wizard-complete-btn"))
    await waitFor(() => expect(screen.queryByTestId("setup-wizard")).not.toBeInTheDocument())
    expect(api.completeWizard).toHaveBeenCalledTimes(1)
    const completeOrder = (api.completeWizard as ReturnType<typeof vi.fn>).mock.invocationCallOrder[0]
    const modeCalls = (api.setWizardMode as ReturnType<typeof vi.fn>).mock
    const offIdx = modeCalls.calls.findIndex((c) => c[0] === false)
    expect(offIdx).toBeGreaterThanOrEqual(0)
    expect(modeCalls.invocationCallOrder[offIdx]).toBeGreaterThan(completeOrder)
    await waitFor(() => expect(api.subscribeMetrics).toHaveBeenCalled())
    await waitFor(() => expect(api.listDrives).toHaveBeenCalled())
  })

  it("myserver:reset-home does not interrupt an active wizard", async () => {
    setup(true)
    render(<CompanionApp />)
    await waitForWizard()
    fireEvent.click(screen.getByText("next-1"))
    await screen.findByTestId("stub-step-2")
    act(() => {
      window.dispatchEvent(new CustomEvent("myserver:reset-home"))
    })
    expect(screen.getByTestId("setup-wizard")).toBeInTheDocument()
    expect(screen.getByTestId("stub-step-2")).toBeInTheDocument()
  })
})

import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import CompanionApp from "../../CompanionApp"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { I18N } from "../i18n"

describe("SetupWizard Settings re-entry clean slate", () => {
  let mockApi: CompanionApi

  beforeEach(async () => {
    window.history.replaceState({}, "", "/?view=settings")
    mockApi = createMockApi()
    const baseSettings = await mockApi.loadSettings()
    vi.spyOn(mockApi, "loadSettings").mockResolvedValue({
      ...baseSettings,
      language: "id",
      firstRunSetup: false,
      setupWizardCompleted: true,
    })
    vi.spyOn(mockApi, "subscribeMetrics")
    const baseDetails = await mockApi.getServerDetails()
    vi.spyOn(mockApi, "getServerDetails").mockResolvedValue({
      ...baseDetails,
      serverId: "srv_active",
      serverName: "Personal-Custom-NAS",
      activeHost: "192.168.1.11",
      routes: [
        { id: "conn_1", name: "LAN", url: "http://192.168.1.11", active: true },
      ],
    })
    setCompanionApi(mockApi)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    setCompanionApi(createMockApi())
    window.history.replaceState({}, "", "/")
  })

  it("does not prefill existing config serverName or lanUrl when opened from Settings", async () => {
    render(<CompanionApp />)
    await waitFor(() => expect(mockApi.subscribeMetrics).toHaveBeenCalled())

    let openBtn = screen.queryByTestId("settings-open-wizard")
    if (!openBtn) {
      const header = await screen.findByText("Bahasa & Keamanan Vault")
      fireEvent.click(header)
      openBtn = await screen.findByTestId("settings-open-wizard")
    }
    fireEvent.click(openBtn)

    const lanInput = (await screen.findByLabelText(
      I18N.id.wiz_lan_label
    )) as HTMLInputElement
    await waitFor(() => expect(mockApi.getServerDetails).toHaveBeenCalled())
    expect(lanInput.value).toBe("")
    expect(screen.queryByDisplayValue(/192\.168\.1\.11/)).not.toBeInTheDocument()

    mockApi.probeUrl = vi.fn().mockResolvedValue({
      reachable: true,
      latencyMs: 3,
      normalizedUrl: "http://192.0.2.55",
    })

    fireEvent.change(lanInput, { target: { value: "http://192.0.2.55" } })
    fireEvent.click(screen.getByRole("button", { name: I18N.id.wiz_test_conn }))
    await waitFor(() => expect(mockApi.probeUrl).toHaveBeenCalledWith("http://192.0.2.55"))

    const nextBtn1 = screen.getByRole("button", { name: I18N.id.wiz_next })
    await waitFor(() => expect(nextBtn1).toBeEnabled())
    fireEvent.click(nextBtn1)

    const skipWanBtn = await screen.findByRole("button", { name: I18N.id.wiz_skip })
    fireEvent.click(skipWanBtn)

    const serverNameInput = (await screen.findByLabelText(
      I18N.id.wiz_server_name_label
    )) as HTMLInputElement
    expect(serverNameInput.value).toBe("")
    expect(
      screen.queryByDisplayValue(/Personal-Custom-NAS/)
    ).not.toBeInTheDocument()

    mockApi.verifyZimaLogin = vi.fn().mockResolvedValue({
      success: true,
      username: "admin",
      resolvedUrl: "http://192.0.2.55",
    })
    const commitSpy = vi.fn().mockResolvedValue({
      success: true,
      serverId: "srv_active",
      name: "CleanServer",
    })
    mockApi.commitWizardServer = commitSpy

    fireEvent.change(serverNameInput, { target: { value: "CleanServer" } })
    fireEvent.change(screen.getByLabelText(I18N.id.wiz_username_label), {
      target: { value: "admin" },
    })
    fireEvent.change(screen.getByLabelText(I18N.id.wiz_password_label), {
      target: { value: "pw-secret" },
    })
    fireEvent.click(screen.getByRole("button", { name: I18N.id.wiz_login_btn }))

    await waitFor(() => {
      expect(commitSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          serverId: "srv_active",
          name: "CleanServer",
          localUrl: "http://192.0.2.55",
        })
      )
    })
  })
})

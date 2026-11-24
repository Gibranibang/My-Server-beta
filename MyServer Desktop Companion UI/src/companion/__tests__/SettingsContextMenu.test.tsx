import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { I18N } from "../i18n"
import { CompanionStoreProvider, NoticeProvider, useNotice } from "../store"
import type { ExplorerContextMenuResult } from "../types"
import SettingsView from "../views/SettingsView"

function NoticeSpy() {
  const { notice } = useNotice()
  return (
    <div data-testid="notice-spy">
      {notice ? `${notice.tone}:${notice.text}` : ""}
    </div>
  )
}

function setupApi(opts: {
  language?: "en" | "id"
  explorerContextMenuEnabled?: boolean
  overrides?: Partial<CompanionApi>
} = {}) {
  const base = createMockApi()
  const baseLoadSettings = base.loadSettings.bind(base)
  const language = opts.language ?? "en"
  const explorerContextMenuEnabled = opts.explorerContextMenuEnabled ?? false

  const api: CompanionApi = {
    ...base,
    loadSettings: vi.fn(async () => ({
      ...(await baseLoadSettings()),
      firstRunSetup: false,
      language,
      theme: "dark" as const,
      explorerContextMenuEnabled,
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
      serverName: "Server Utama",
      activeId: "srv_1",
      activeName: "Server Utama",
      activeHost: "http://192.168.1.50:80",
      activeRoute: "lan",
      routes: [{ id: "lan", name: "LAN", url: "http://192.168.1.50:80", active: true }],
      activeProfile: "admin",
      profiles: ["admin"],
      uptimeStr: "1d",
    })) as unknown as CompanionApi["getServerDetails"],
    saveSettings: vi.fn(async () => {}),
    ...opts.overrides,
  }
  setCompanionApi(api)
  return api
}

function renderSettings() {
  return render(
    <NoticeProvider>
      <NoticeSpy />
      <CompanionStoreProvider>
        <SettingsView />
      </CompanionStoreProvider>
    </NoticeProvider>,
  )
}

async function expandStorageAccordion(language: "en" | "id") {
  const title = I18N[language].sec_storage_net_title
  const btn = await screen.findByRole("button", { name: new RegExp(title, "i") })
  fireEvent.click(btn)
}

describe("SettingsView Windows File Explorer Context Menu Toggle (SHAR-02 / Surface 4 E6)", () => {
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

  it("renders Explorer Context Menu toggle row with Share2 icon, dynamic captions, and Win11 hint strip in EN and ID", async () => {
    const enApi = setupApi({ language: "en", explorerContextMenuEnabled: false })
    renderSettings()
    await waitFor(() => expect(enApi.loadSettings).toHaveBeenCalled())
    await expandStorageAccordion("en")

    const toggle = await screen.findByRole("switch", { name: I18N.en.explorer_ctx_label })
    expect(toggle).toHaveAttribute("aria-checked", "false")
    expect(screen.getByText(I18N.en.explorer_ctx_off)).toBeInTheDocument()
    const row = toggle.closest("div")!
    expect(row.querySelector("svg")).not.toBeNull()

    const hint = screen.getByTestId("explorer-ctx-win11-hint")
    expect(hint).toHaveTextContent(I18N.en.explorer_ctx_win11_hint)
    expect(hint.querySelector("svg")).not.toBeNull()

    cleanup()

    const idApi = setupApi({ language: "id", explorerContextMenuEnabled: true })
    renderSettings()
    await waitFor(() => expect(idApi.loadSettings).toHaveBeenCalled())
    await expandStorageAccordion("id")

    const idToggle = await screen.findByRole("switch", { name: I18N.id.explorer_ctx_label })
    expect(idToggle).toHaveAttribute("aria-checked", "true")
    expect(screen.getByText(I18N.id.explorer_ctx_on)).toBeInTheDocument()
    expect(screen.getByTestId("explorer-ctx-win11-hint")).toHaveTextContent(I18N.id.explorer_ctx_win11_hint)
  })

  it("disables toggle while in flight (E6/loading), updates to ON/OFF, and emits localized success toasts", async () => {
    let resolveEnable!: (val: ExplorerContextMenuResult) => void
    const enablePromise = new Promise<ExplorerContextMenuResult>((resolve) => {
      resolveEnable = resolve
    })
    const setExplorerContextMenuEnabled = vi
      .fn()
      .mockImplementationOnce(() => enablePromise)
      .mockImplementationOnce(async () => ({ success: true, enabled: false }))

    const api = setupApi({
      language: "en",
      explorerContextMenuEnabled: false,
      overrides: { setExplorerContextMenuEnabled },
    })
    renderSettings()
    await waitFor(() => expect(api.loadSettings).toHaveBeenCalled())
    await expandStorageAccordion("en")

    const toggle = await screen.findByRole("switch", { name: I18N.en.explorer_ctx_label })
    expect(toggle).toHaveAttribute("aria-checked", "false")

    fireEvent.click(toggle)
    expect(toggle).toBeDisabled()
    expect(setExplorerContextMenuEnabled).toHaveBeenCalledWith(true)

    await act(async () => {
      resolveEnable({ success: true, enabled: true })
    })

    await waitFor(() => {
      expect(toggle).not.toBeDisabled()
      expect(toggle).toHaveAttribute("aria-checked", "true")
      expect(screen.getByText(I18N.en.explorer_ctx_on)).toBeInTheDocument()
      expect(screen.getByTestId("notice-spy")).toHaveTextContent(`success:${I18N.en.explorer_ctx_enabled_toast}`)
    })

    fireEvent.click(toggle)
    await waitFor(() => {
      expect(setExplorerContextMenuEnabled).toHaveBeenCalledWith(false)
      expect(toggle).toHaveAttribute("aria-checked", "false")
      expect(screen.getByText(I18N.en.explorer_ctx_off)).toBeInTheDocument()
      expect(screen.getByTestId("notice-spy")).toHaveTextContent(`success:${I18N.en.explorer_ctx_disabled_toast}`)
    })
  })

  it("rolls back visual toggle state and emits localized danger toast when Registry write rejects or returns success: false", async () => {
    const setExplorerContextMenuEnabled = vi
      .fn()
      .mockRejectedValueOnce(new Error("Access denied"))
      .mockResolvedValueOnce({ success: false, enabled: true, error: "Access denied" })

    const api = setupApi({
      language: "en",
      explorerContextMenuEnabled: false,
      overrides: { setExplorerContextMenuEnabled },
    })
    renderSettings()
    await waitFor(() => expect(api.loadSettings).toHaveBeenCalled())
    await expandStorageAccordion("en")

    const toggle = await screen.findByRole("switch", { name: I18N.en.explorer_ctx_label })
    expect(toggle).toHaveAttribute("aria-checked", "false")

    fireEvent.click(toggle)

    await waitFor(() => {
      expect(toggle).not.toBeDisabled()
      expect(toggle).toHaveAttribute("aria-checked", "false")
      expect(screen.getByText(I18N.en.explorer_ctx_off)).toBeInTheDocument()
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("danger:")
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("Access denied")
    })

    cleanup()

    const idApi = setupApi({
      language: "id",
      explorerContextMenuEnabled: true,
      overrides: {
        setExplorerContextMenuEnabled: vi.fn(async () => ({
          success: false,
          enabled: true,
          error: "Access denied",
        })),
      },
    })
    renderSettings()
    await waitFor(() => expect(idApi.loadSettings).toHaveBeenCalled())
    await expandStorageAccordion("id")

    const idToggle = await screen.findByRole("switch", { name: I18N.id.explorer_ctx_label })
    expect(idToggle).toHaveAttribute("aria-checked", "true")
    fireEvent.click(idToggle)

    await waitFor(() => {
      expect(idToggle).toHaveAttribute("aria-checked", "true")
      expect(screen.getByText(I18N.id.explorer_ctx_on)).toBeInTheDocument()
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("danger:")
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("Access denied")
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("Gagal memperbarui menu Windows Explorer")
    })
  })
})

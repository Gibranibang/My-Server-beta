import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import CompanionApp from "../../CompanionApp"
import { CompanionFrame } from "../Companion"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { I18N } from "../i18n"
import { CompanionStoreProvider, NoticeProvider, useNotice } from "../store"
import type { MiniTrayDragDropDetail, ShareErrorCode, ShareTargetInfo } from "../types"

function NoticeSpy() {
  const { notice } = useNotice()
  return (
    <div data-testid="notice-spy">
      {notice ? `${notice.tone}:${notice.text}` : ""}
    </div>
  )
}

function makeTarget(overrides: Partial<ShareTargetInfo> = {}): ShareTargetInfo {
  return {
    server_id: "srv_1",
    server_name: "Server Utama",
    disk_name: "DATA",
    share_name: "DATA",
    canonical_rel: "DATA/Projects/report.pdf",
    basename: "report.pdf",
    is_dir: false,
    is_admin: true,
    backend_url: "http://192.168.1.50:8085",
    smb_source: "zimaos",
    raw_path: "Z:\\Projects\\report.pdf",
    ...overrides,
  }
}

function setupApi(opts: {
  language?: "en" | "id"
  online?: boolean
  firstRunSetup?: boolean
  overrides?: Partial<CompanionApi>
} = {}) {
  const base = createMockApi()
  const baseLoadSettings = base.loadSettings.bind(base)
  const language = opts.language ?? "en"
  const online = opts.online ?? true
  const firstRunSetup = opts.firstRunSetup ?? false

  const api: CompanionApi = {
    ...base,
    loadSettings: vi.fn(async () => ({
      ...(await baseLoadSettings()),
      firstRunSetup,
      language,
      theme: "dark" as const,
    })),
    subscribeMetrics: vi.fn((cb) => {
      cb({
        cpu: 18,
        ram: 42,
        hdd: 30,
        lanDown: 0.4,
        lanHistory: Array(12).fill(0),
        syncUp: 0,
        syncDown: 0,
        isLoading: false,
      })
      return () => {}
    }) as unknown as CompanionApi["subscribeMetrics"],
    subscribePower: vi.fn((cb) => {
      cb(online ? "online" : "offline")
      return () => {}
    }) as unknown as CompanionApi["subscribePower"],
    listDrives: vi.fn(async () => []),
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
    resolveSharePath: vi.fn(async (path: string) => ({
      ok: true,
      target: makeTarget({ raw_path: path }),
    })),
    openShareWindow: vi.fn(async () => {}),
    ...opts.overrides,
  }
  setCompanionApi(api)
  return api
}

function renderMiniTray() {
  return render(
    <NoticeProvider>
      <NoticeSpy />
      <CompanionStoreProvider>
        <CompanionFrame view="home" onViewChange={vi.fn()} />
      </CompanionStoreProvider>
    </NoticeProvider>,
  )
}

async function waitForMiniTrayReady(language: "en" | "id" = "en") {
  await screen.findByRole("button", { name: I18N[language].open_in_browser })
}

function dispatchDragDrop(detail: MiniTrayDragDropDetail) {
  act(() => {
    window.dispatchEvent(new CustomEvent("myserver:drag-drop", { detail }))
  })
}

describe("Mini Tray Drag-and-Drop Unified Overlay (SHAR-05 / Surface 2 E5)", () => {
  beforeEach(() => {
    localStorage.clear()
    window.history.replaceState({}, "", "/")
    ;(window as any).__TAURI_INTERNALS__ = { invoke: vi.fn() }
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    localStorage.clear()
    delete (window as any).__TAURI_INTERNALS__
    delete (window as any).__TAURI__
    window.history.replaceState({}, "", "/")
    setCompanionApi(createMockApi())
  })

  it("renders unified lime drop overlay on enter and dismisses on leave and blur (EN & ID)", async () => {
    setupApi({ language: "en", online: true })
    renderMiniTray()
    await waitForMiniTrayReady("en")

    dispatchDragDrop({ type: "enter", count: 1 })
    const overlay = await screen.findByTestId("mini-tray-drop-overlay")
    expect(overlay).toHaveClass("absolute", "inset-0", "z-50", "rounded-[16px]")
    expect(overlay.firstElementChild).toHaveClass("border-brand")
    expect(screen.getByText(I18N.en.drop_title_online)).toBeInTheDocument()
    expect(screen.getByText(I18N.en.drop_sub_online)).toBeInTheDocument()

    dispatchDragDrop({ type: "leave" })
    expect(screen.queryByTestId("mini-tray-drop-overlay")).not.toBeInTheDocument()

    dispatchDragDrop({ type: "enter", count: 1 })
    expect(screen.getByTestId("mini-tray-drop-overlay")).toBeInTheDocument()
    act(() => {
      window.dispatchEvent(new Event("blur"))
    })
    expect(screen.queryByTestId("mini-tray-drop-overlay")).not.toBeInTheDocument()

    cleanup()
    setupApi({ language: "id", online: true })
    renderMiniTray()
    await waitForMiniTrayReady("id")
    dispatchDragDrop({ type: "enter", count: 1 })
    expect(await screen.findByText(I18N.id.drop_title_online)).toBeInTheDocument()
    expect(screen.getByText(I18N.id.drop_sub_online)).toBeInTheDocument()
  })

  it("renders offline danger overlay and emits offline toast without calling resolveSharePath", async () => {
    const api = setupApi({ language: "en", online: false })
    renderMiniTray()
    await waitForMiniTrayReady("en")

    dispatchDragDrop({ type: "enter", count: 1 })
    const overlay = await screen.findByTestId("mini-tray-drop-overlay")
    expect(overlay.firstElementChild).toHaveClass("border-danger")
    expect(screen.getByText(I18N.en.drop_title_offline)).toBeInTheDocument()
    expect(screen.getByText(I18N.en.drop_sub_offline)).toBeInTheDocument()

    dispatchDragDrop({ type: "drop", paths: ["Z:\\docs\\report.pdf"] })
    expect(screen.queryByTestId("mini-tray-drop-overlay")).not.toBeInTheDocument()
    expect(screen.getByTestId("notice-spy")).toHaveTextContent(`danger:${I18N.en.share_err_offline}`)
    expect(api.resolveSharePath).not.toHaveBeenCalled()
    expect(api.openShareWindow).not.toHaveBeenCalled()
  })

  it("ignores myserver:drag-drop when Setup Wizard is open or outside native Tauri main", async () => {
    const wizardApi = setupApi({ language: "id", firstRunSetup: true })
    render(<CompanionApp />)
    await screen.findByTestId("setup-wizard")

    dispatchDragDrop({ type: "enter", count: 1 })
    dispatchDragDrop({ type: "drop", paths: ["Z:\\docs\\report.pdf"] })
    expect(screen.queryByTestId("mini-tray-drop-overlay")).not.toBeInTheDocument()
    expect(wizardApi.resolveSharePath).not.toHaveBeenCalled()

    cleanup()
    delete (window as any).__TAURI_INTERNALS__
    const nonTauriApi = setupApi({ language: "en" })
    renderMiniTray()
    await waitForMiniTrayReady("en")
    dispatchDragDrop({ type: "enter", count: 1 })
    dispatchDragDrop({ type: "drop", paths: ["Z:\\docs\\report.pdf"] })
    expect(screen.queryByTestId("mini-tray-drop-overlay")).not.toBeInTheDocument()
    expect(nonTauriApi.resolveSharePath).not.toHaveBeenCalled()

    cleanup()
    ;(window as any).__TAURI_INTERNALS__ = { invoke: vi.fn() }
    window.history.replaceState({}, "", "/?window=share")
    const shareWinApi = setupApi({ language: "en" })
    renderMiniTray()
    await waitForMiniTrayReady("en")
    dispatchDragDrop({ type: "enter", count: 1 })
    dispatchDragDrop({ type: "drop", paths: ["Z:\\docs\\report.pdf"] })
    expect(screen.queryByTestId("mini-tray-drop-overlay")).not.toBeInTheDocument()
    expect(shareWinApi.resolveSharePath).not.toHaveBeenCalled()
  })

  it("dismisses overlay cleanly on empty paths: [] drop without calling resolveSharePath or emitting a toast", async () => {
    const api = setupApi({ language: "en", online: true })
    renderMiniTray()
    await waitForMiniTrayReady("en")

    dispatchDragDrop({ type: "enter", count: 1 })
    expect(screen.getByTestId("mini-tray-drop-overlay")).toBeInTheDocument()

    dispatchDragDrop({ type: "drop", paths: [] })
    expect(screen.queryByTestId("mini-tray-drop-overlay")).not.toBeInTheDocument()
    expect(screen.getByTestId("notice-spy")).toHaveTextContent("")
    expect(api.resolveSharePath).not.toHaveBeenCalled()
    expect(api.openShareWindow).not.toHaveBeenCalled()
  })

  it("rejects multi-item drops immediately with MULTI_ITEM_DROP danger toast before calling resolveSharePath", async () => {
    const api = setupApi({ language: "en", online: true })
    renderMiniTray()
    await waitForMiniTrayReady("en")

    dispatchDragDrop({ type: "enter", count: 2 })
    dispatchDragDrop({ type: "drop", paths: ["Z:\\a.txt", "Z:\\b.txt"] })

    expect(screen.queryByTestId("mini-tray-drop-overlay")).not.toBeInTheDocument()
    expect(screen.getByTestId("notice-spy")).toHaveTextContent(`danger:${I18N.en.share_err_multi_item}`)
    expect(api.resolveSharePath).not.toHaveBeenCalled()
    expect(api.openShareWindow).not.toHaveBeenCalled()
  })

  it.each<[ShareErrorCode, keyof typeof I18N.en]>([
    ["LOCAL_DRIVE", "share_err_local_drive"],
    ["FOREIGN_NAS", "share_err_foreign_nas"],
    ["SHARE_NOT_MOUNTED_IN_BACKEND", "share_err_unmounted"],
    ["SERVER_OFFLINE", "share_err_offline"],
    ["BACKEND_OFFLINE", "share_err_offline"],
    ["UNAUTHENTICATED_SESSION", "share_err_unauthenticated"],
    ["FORBIDDEN_PATH", "share_err_forbidden"],
  ])("maps %s resolver rejection to danger toast and does not call openShareWindow", async (code, i18nKey) => {
    const api = setupApi({
      language: "en",
      online: true,
      overrides: {
        resolveSharePath: vi.fn(async () => ({ ok: false, code })),
      },
    })
    renderMiniTray()
    await waitForMiniTrayReady("en")

    dispatchDragDrop({ type: "drop", paths: ["C:\\Users\\test\\secret.txt"] })

    await waitFor(() => {
      expect(screen.getByTestId("notice-spy")).toHaveTextContent(`danger:${I18N.en[i18nKey]}`)
    })
    expect(api.resolveSharePath).toHaveBeenCalledWith("C:\\Users\\test\\secret.txt")
    expect(api.openShareWindow).not.toHaveBeenCalled()
  })

  it("opens share-window via openShareWindow(res.target) on valid single SMB drop and guards overlapping drops", async () => {
    const target = makeTarget({ canonical_rel: "DATA/Photos/vacation.jpg", basename: "vacation.jpg" })
    let resolveDeferred!: (val: { ok: boolean; target: ShareTargetInfo }) => void
    const resolvePromise = new Promise<{ ok: boolean; target: ShareTargetInfo }>((resolve) => {
      resolveDeferred = resolve
    })
    const api = setupApi({
      language: "en",
      online: true,
      overrides: {
        resolveSharePath: vi.fn(() => resolvePromise),
      },
    })
    renderMiniTray()
    await waitForMiniTrayReady("en")

    dispatchDragDrop({ type: "enter", count: 1 })
    dispatchDragDrop({ type: "drop", paths: ["Z:\\Photos\\vacation.jpg"] })
    // Rapid second drop while first resolveSharePath is still in flight should be ignored
    dispatchDragDrop({ type: "drop", paths: ["Z:\\Photos\\other.jpg"] })

    expect(screen.queryByTestId("mini-tray-drop-overlay")).not.toBeInTheDocument()
    expect(api.resolveSharePath).toHaveBeenCalledTimes(1)
    expect(api.resolveSharePath).toHaveBeenCalledWith("Z:\\Photos\\vacation.jpg")

    await act(async () => {
      resolveDeferred({ ok: true, target })
    })

    await waitFor(() => {
      expect(api.openShareWindow).toHaveBeenCalledTimes(1)
      expect(api.openShareWindow).toHaveBeenCalledWith(target)
    })
  })
})

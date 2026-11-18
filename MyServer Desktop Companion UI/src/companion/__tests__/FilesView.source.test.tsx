import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { createRealApi } from "../api.real"
import { CompanionStoreProvider, NoticeProvider, useNotice } from "../store"
import FilesView from "../views/FilesView"
import type { Drive, FileManagerSourcePayload, FileManagerSourceStatus } from "../types"

function NoticeSpy() {
  const { notice } = useNotice()
  return (
    <div data-testid="notice-spy">
      {notice ? `${notice.tone}:${notice.text}` : ""}
    </div>
  )
}

interface SetupOptions {
  language?: "en" | "id"
  fileManagerClickTarget?: "explorer" | "zimaos"
  initialDrives?: Drive[]
  initialSource?: FileManagerSourceStatus
  configureImpl?: (payload: FileManagerSourcePayload) => Promise<FileManagerSourceStatus>
}

function setupFilesView(opts: SetupOptions = {}) {
  const api: CompanionApi = createMockApi()
  const baseLoadSettings = api.loadSettings.bind(api)
  api.loadSettings = vi.fn(async () => ({
    ...(await baseLoadSettings()),
    firstRunSetup: false,
    language: opts.language ?? "id",
    fileManagerClickTarget: opts.fileManagerClickTarget ?? "explorer",
  }))

  api.subscribeMetrics = vi.fn(() => () => {}) as unknown as CompanionApi["subscribeMetrics"]
  api.subscribePower = vi.fn((cb) => {
    cb("online")
    return () => {}
  }) as unknown as CompanionApi["subscribePower"]
  api.getServerDetails = vi.fn(async () => ({
    serverId: "srv_1",
    serverName: "Server Utama",
    activeHost: "127.0.0.1",
    activeRoute: "lan",
    routes: [{ id: "lan", name: "LAN", url: "http://127.0.0.1:80", active: true }],
    activeProfile: "Admin",
    profiles: ["Admin"],
    uptimeStr: "1d",
  })) as unknown as CompanionApi["getServerDetails"]

  const baseListDrives = api.listDrives.bind(api)
  api.listDrives = vi.fn(async () =>
    opts.initialDrives !== undefined ? opts.initialDrives : await baseListDrives(),
  )
  api.openZimaFileManager = vi.fn(async () => {})
  api.openBackendFileManager = vi.fn(async () => ({ success: true, url: "http://127.0.0.1:8080/" }))
  api.openFileExplorer = vi.fn(async () => {})

  const initialSource: FileManagerSourceStatus = opts.initialSource ?? {
    success: true,
    source: "zimaos",
    hasCredentials: false,
    backendOnline: true,
    smbMode: "zimaos",
    needsAuth: false,
  }
  api.getFileManagerSource = vi.fn(async () => ({ ...initialSource }))

  const baseConfigure = api.configureFileManagerSource!.bind(api)
  api.configureFileManagerSource = vi.fn(async (payload: FileManagerSourcePayload) => {
    if (opts.configureImpl) {
      return await opts.configureImpl(payload)
    }
    return await baseConfigure(payload)
  })

  setCompanionApi(api)
  const rendered = render(
    <NoticeProvider>
      <CompanionStoreProvider>
        <NoticeSpy />
        <FilesView />
      </CompanionStoreProvider>
    </NoticeProvider>,
  )
  return { api, ...rendered }
}

describe("FilesView SMB source toggle & Backend login (D-06, SMB-05)", () => {
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

  it("preserves 100% of existing FilesView elements (D-06 Zero Overhaul)", async () => {
    const { container } = setupFilesView({ language: "en" })

    expect(await screen.findByRole("button", { name: "Mount All Server Drives" })).toBeInTheDocument()
    expect(screen.getByText("ZimaOS Files")).toBeInTheDocument()
    expect(screen.getByText("PeerDrop")).toBeInTheDocument()
    expect(screen.getByText("Network Drive (SMB)")).toBeInTheDocument()
    expect(await screen.findByText("Drive Z:")).toBeInTheDocument()
    expect(screen.getByText("[DATA]")).toBeInTheDocument()
    expect(screen.getByText("Drive Y:")).toBeInTheDocument()
    expect(screen.getByText("[Toshiba 1TB]")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Disconnect All Drives" })).toBeInTheDocument()
    expect(screen.getByText("SMBv3 Active")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open UNC" })).toBeInTheDocument()

    // StorageDotBar SVGs remain rendered inside DriveCards
    const dotBarSvgs = container.querySelectorAll('svg[viewBox="0 0 252 18"]')
    expect(dotBarSvgs.length).toBe(2)

    cleanup()

    setupFilesView({ language: "en", fileManagerClickTarget: "zimaos" })
    expect(await screen.findByText("File Explorer")).toBeInTheDocument()
  })

  it("toggles to Backend, submits login, clears password, refreshes drives, shows Chip/Mono/TextAction, and routes tile to openBackendFileManager", async () => {
    const { api } = setupFilesView({ language: "id" })

    const tablist = await screen.findByRole("tablist", { name: "Sumber Penyimpanan SMB" })
    expect(tablist).toBeInTheDocument()
    const zimaTab = screen.getByRole("tab", { name: "ZimaOS" })
    const backendTab = screen.getByRole("tab", { name: "Backend" })
    expect(zimaTab).toHaveAttribute("aria-selected", "true")
    expect(backendTab).toHaveAttribute("aria-selected", "false")

    fireEvent.click(backendTab)

    expect(backendTab).toHaveAttribute("aria-selected", "true")
    const userInput = await screen.findByLabelText("Username Akun Backend")
    const passInput = screen.getByLabelText("Kata Sandi Akun Backend")
    const submitBtn = screen.getByRole("button", { name: "Hubungkan Akun Backend" })
    expect(submitBtn).toBeDisabled()

    fireEvent.change(userInput, { target: { value: "staff_budi" } })
    expect(submitBtn).toBeDisabled()
    fireEvent.change(passInput, { target: { value: "rahasia123" } })
    expect(submitBtn).toBeEnabled()

    const listCallsBeforeSubmit = (api.listDrives as any).mock.calls.length
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(api.configureFileManagerSource).toHaveBeenCalledWith({
        source: "backend",
        username: "staff_budi",
        password: "rahasia123",
        autoMount: true,
      })
    })

    await waitFor(() => {
      expect((api.listDrives as any).mock.calls.length).toBeGreaterThan(listCallsBeforeSubmit)
    })

    const monoUser = await screen.findByText("staff_budi")
    expect(monoUser).toHaveAttribute("title", "staff_budi")
    expect(screen.getByText("Staff · 1 Disk")).toBeInTheDocument()
    const switchBtn = screen.getByRole("button", { name: "Ganti Akun Backend" })
    expect(switchBtn).toBeInTheDocument()

    // Ensure Web Files LaunchTile now routes to Backend File Manager
    const backendFilesTile = screen.getByText("Backend Files").closest("button")
    expect(backendFilesTile).not.toBeNull()
    fireEvent.click(backendFilesTile!)
    expect(api.openBackendFileManager).toHaveBeenCalledTimes(1)
    expect(api.openZimaFileManager).not.toHaveBeenCalled()

    // Clicking Ganti Akun Backend reveals empty password field (never retained in UI memory) and Batal Ganti Akun
    fireEvent.click(switchBtn)
    const reopenedPass = await screen.findByLabelText("Kata Sandi Akun Backend")
    expect((reopenedPass as HTMLInputElement).value).toBe("")
    const cancelSwitchBtn = screen.getByRole("button", { name: "Batal Ganti Akun" })
    expect(cancelSwitchBtn).toBeInTheDocument()

    fireEvent.click(cancelSwitchBtn)
    await waitFor(() => {
      expect(screen.queryByLabelText("Kata Sandi Akun Backend")).not.toBeInTheDocument()
    })

    // Also verifies Admin role Chip when connected as admin
    cleanup()
    setupFilesView({
      language: "id",
      initialSource: {
        success: true,
        source: "backend",
        username: "admin",
        role: "admin",
        allowedDisks: ["DATA", "Media"],
        hasCredentials: true,
        needsAuth: false,
        backendOnline: true,
      },
    })
    const adminMono = await screen.findByText("admin")
    expect(adminMono).toHaveAttribute("title", "admin")
    expect(screen.getByText("Admin")).toBeInTheDocument()
  })

  it("shows inline Backend login Card when needsAuth is true even if hasCredentials is true", async () => {
    setupFilesView({
      language: "id",
      initialSource: {
        success: false,
        source: "backend",
        hasCredentials: true,
        needsAuth: true,
        username: "staff_budi",
        backendOnline: true,
      },
    })

    const userInput = (await screen.findByLabelText("Username Akun Backend")) as HTMLInputElement
    expect(userInput.value).toBe("staff_budi")
    expect(screen.getByLabelText("Kata Sandi Akun Backend")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Hubungkan Akun Backend" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Ganti Akun Backend" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Batal Ganti Akun" })).not.toBeInTheDocument()
  })

  it("displays danger toast, keeps inline login Card focused on failed Backend login, and switches cleanly back to ZimaOS", async () => {
    const { api } = setupFilesView({
      language: "id",
      initialDrives: [],
      configureImpl: async (payload) => {
        if (payload.source === "backend") {
          return {
            success: false,
            source: "zimaos",
            hasCredentials: false,
            needsAuth: true,
            error: "Password salah",
          }
        }
        return {
          success: true,
          source: "zimaos",
          hasCredentials: false,
          smbMode: "zimaos",
          needsAuth: false,
        }
      },
    })

    const backendTab = await screen.findByRole("tab", { name: "Backend" })
    fireEvent.click(backendTab)

    expect(await screen.findByText("Belum Ada Partisi Penyimpanan Terdeteksi")).toBeInTheDocument()

    const userInput = screen.getByLabelText("Username Akun Backend")
    const passInput = screen.getByLabelText("Kata Sandi Akun Backend") as HTMLInputElement
    fireEvent.change(userInput, { target: { value: "admin" } })
    fireEvent.change(passInput, { target: { value: "salah" } })
    fireEvent.click(screen.getByRole("button", { name: "Hubungkan Akun Backend" }))

    await waitFor(() => {
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("danger:")
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("Password salah")
    })

    // Remains on Backend mode with inline login Card open and password cleared & focused
    expect(backendTab).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("button", { name: "Hubungkan Akun Backend" })).toBeInTheDocument()
    expect(passInput.value).toBe("")
    expect(document.activeElement).toBe(passInput)

    // Switching back to ZimaOS calls configureFileManagerSource({ source: "zimaos", autoMount: true })
    const zimaTab = screen.getByRole("tab", { name: "ZimaOS" })
    fireEvent.click(zimaTab)

    await waitFor(() => {
      expect(api.configureFileManagerSource).toHaveBeenCalledWith({
        source: "zimaos",
        autoMount: true,
      })
    })
    expect(zimaTab).toHaveAttribute("aria-selected", "true")
  })

  it("forwards realApi getFileManagerSource, configureFileManagerSource, and openBackendFileManager via Tauri call_core_api", async () => {
    const invoke = vi.fn(async (cmd: string, args?: Record<string, unknown>) => {
      if (cmd === "call_core_api" && args?.endpoint === "smb/source") {
        return { success: true, source: "backend", username: "admin", role: "admin", allowedDisks: ["DATA"] }
      }
      return { success: true }
    })
    ;(window as any).__TAURI_INTERNALS__ = { invoke }

    const realApi = createRealApi()
    const status = await realApi.getFileManagerSource!()
    expect(status.source).toBe("backend")
    expect(invoke).toHaveBeenCalledWith("call_core_api", {
      endpoint: "smb/source",
      payload: { action: "get" },
    })

    await realApi.configureFileManagerSource!({
      source: "backend",
      username: "admin",
      password: "secret",
      autoMount: true,
    })
    expect(invoke).toHaveBeenCalledWith("call_core_api", {
      endpoint: "smb/source",
      payload: {
        action: "set",
        source: "backend",
        username: "admin",
        password: "secret",
        autoMount: true,
      },
    })

    const openRes = await realApi.openBackendFileManager!()
    expect(invoke).toHaveBeenCalledWith("call_core_api", {
      endpoint: "open_backend_file_manager",
      payload: {},
    })
    expect(openRes).toMatchObject({ success: true })
  })

  it("displays Admin Chip when Backend role is root (WR-04)", async () => {
    setupFilesView({
      language: "id",
      initialSource: {
        success: true,
        source: "backend",
        username: "root",
        role: "root",
        allowedDisks: [],
        hasCredentials: true,
        needsAuth: false,
        backendOnline: true,
      },
    })

    const rootMono = await screen.findByText("root")
    expect(rootMono).toHaveAttribute("title", "root")
    expect(screen.getByText("Admin")).toBeInTheDocument()
    expect(screen.queryByText(/Staff ·/i)).not.toBeInTheDocument()
  })

  it("keeps Batal Ganti Akun visible when Ganti Akun Backend submission fails (WR-05)", async () => {
    setupFilesView({
      language: "id",
      initialSource: {
        success: true,
        source: "backend",
        username: "staff_budi",
        role: "staff",
        allowedDisks: ["DATA"],
        hasCredentials: true,
        needsAuth: false,
        backendOnline: true,
      },
      configureImpl: async () => ({
        success: false,
        source: "zimaos",
        hasCredentials: false,
        needsAuth: true,
        error: "Password salah",
      }),
    })

    const switchBtn = await screen.findByRole("button", { name: "Ganti Akun Backend" })
    fireEvent.click(switchBtn)

    const userInput = await screen.findByLabelText("Username Akun Backend")
    const passInput = screen.getByLabelText("Kata Sandi Akun Backend")
    fireEvent.change(userInput, { target: { value: "other_user" } })
    fireEvent.change(passInput, { target: { value: "wrong_pw" } })
    fireEvent.click(screen.getByRole("button", { name: "Hubungkan Akun Backend" }))

    await waitFor(() => {
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("danger:")
      expect(screen.getByTestId("notice-spy")).toHaveTextContent("Password salah")
    })

    const cancelBtn = screen.getByRole("button", { name: "Batal Ganti Akun" })
    expect(cancelBtn).toBeInTheDocument()

    fireEvent.click(cancelBtn)
    await waitFor(() => {
      expect(screen.queryByLabelText("Kata Sandi Akun Backend")).not.toBeInTheDocument()
    })
    expect(screen.getByText("staff_budi")).toBeInTheDocument()
    expect(screen.getByText("Staff · 1 Disk")).toBeInTheDocument()
  })

  it("shows danger toast on openBackendFileManager failure and removes redundant pywebview catch fallback (WR-05, WR-09)", async () => {
    const { api } = setupFilesView({
      language: "id",
      initialSource: {
        success: true,
        source: "backend",
        username: "admin",
        role: "admin",
        allowedDisks: ["DATA"],
        hasCredentials: true,
        needsAuth: false,
        backendOnline: true,
      },
    })

    api.openBackendFileManager = vi.fn(async () => ({
      success: false,
      error: "Backend tidak dapat dijangkau atau belum aktif.",
    }))

    const backendFilesTile = (await screen.findByText("Backend Files")).closest("button")
    expect(backendFilesTile).not.toBeNull()
    fireEvent.click(backendFilesTile!)

    await waitFor(() => {
      expect(screen.getByTestId("notice-spy")).toHaveTextContent(
        "danger:Backend tidak dapat dijangkau atau belum aktif.",
      )
    })
    expect(screen.getByTestId("notice-spy")).not.toHaveTextContent("Membuka Storage Explorer Backend")

    // Also verify realApi propagates Core HTTP 503 error & rejects without falling back to pywebview.api.open_backend_file_manager
    const pyOpenSpy = vi.fn(async () => {})
    ;(window as any).pywebview = { api: { open_backend_file_manager: pyOpenSpy } }
    try {
      const invokeErr = vi.fn(async () => {
        throw new Error("Core service offline")
      })
      ;(window as any).__TAURI_INTERNALS__ = { invoke: invokeErr }
      const realApi = createRealApi()
      const errRes = await realApi.openBackendFileManager!()
      expect(errRes).toEqual({ success: false, error: "Core service offline" })
      expect(pyOpenSpy).not.toHaveBeenCalled()

      const invoke503 = vi.fn(async () => ({
        success: false,
        error: "Backend tidak dapat dijangkau atau belum aktif.",
      }))
      ;(window as any).__TAURI_INTERNALS__ = { invoke: invoke503 }
      const res503 = await realApi.openBackendFileManager!()
      expect(res503).toEqual({
        success: false,
        url: undefined,
        error: "Backend tidak dapat dijangkau atau belum aktif.",
      })
      expect(pyOpenSpy).not.toHaveBeenCalled()
    } finally {
      delete (window as any).pywebview
    }
  })
})

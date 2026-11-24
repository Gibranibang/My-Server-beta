import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"

const mockEncodeState = vi.hoisted(() => ({ shouldThrow: false }))

vi.mock("uqr", async (importOriginal) => {
  const actual = await importOriginal<typeof import("uqr")>()
  return {
    ...actual,
    encode: (...args: Parameters<typeof actual.encode>) => {
      if (mockEncodeState.shouldThrow) {
        throw new Error("Simulated QR encode error")
      }
      return actual.encode(...args)
    },
  }
})

import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { I18N } from "../i18n"
import type { PublicShareItem, ShareListResponse, ShareTargetInfo } from "../types"
import { ShareWindow } from "../share/ShareWindow"

function makeTarget(overrides: Partial<ShareTargetInfo> = {}): ShareTargetInfo {
  return {
    server_id: "srv_1",
    server_name: "MyServer-Main",
    disk_name: "DATA",
    share_name: "DATA",
    canonical_rel: "DATA/Projects/Finance/report.pdf",
    basename: "report.pdf",
    is_dir: false,
    is_admin: true,
    backend_url: "http://192.168.1.10:8085",
    smb_source: "zimaos",
    ...overrides,
  }
}

function makeShare(overrides: Partial<PublicShareItem> = {}): PublicShareItem {
  const token = overrides.token ?? "tok_default"
  return {
    token,
    target_path: "DATA/Projects/Finance/report.pdf",
    is_dir: false,
    label: "report.pdf",
    share_url: `http://192.168.1.10:8085/s/${token}`,
    resolved_url: `http://192.168.1.10:8085/s/${token}`,
    is_lan_fallback: true,
    expires_at: null,
    password_protected: false,
    revoked: false,
    download_count: 0,
    created_at: "2026-11-24T10:00:00Z",
    owner_username: "admin",
    ...overrides,
  }
}

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (err: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function makeTestApi(overrides: Partial<CompanionApi> = {}): CompanionApi {
  const base = createMockApi()
  return {
    ...base,
    loadSettings: vi.fn(async () => ({
      autostart: true,
      openDashboard: false,
      autoMountSmb: true,
      autoZeroTier: true,
      autoCleanOnExit: true,
      language: "en" as const,
      theme: "dark" as const,
      explorerContextMenuEnabled: false,
    })),
    subscribeMetrics: vi.fn(() => () => {}),
    setWizardMode: vi.fn(async () => undefined),
    startDrag: vi.fn(async () => undefined),
    closeShareWindow: vi.fn(async () => undefined),
    getShareWindowTarget: vi.fn(async () => makeTarget()),
    openExternalBrowser: vi.fn(async () => undefined),
    copyShareClipboard: vi.fn(async () => true),
    listShares: vi.fn(async () => ({
      success: true,
      shares: [],
      public_base_url: "",
      is_admin: true,
    })),
    ...overrides,
  }
}

describe("ShareWindow (Surface 1: E1-E4, SHAR-03, SECH-02, SECH-03)", () => {
  beforeEach(() => {
    mockEncodeState.shouldThrow = false
    window.history.replaceState({}, "", "/")
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    mockEncodeState.shouldThrow = false
  })

  it("enforces anti-lock (never calls setWizardMode/subscribeMetrics) and supports drag + close + Escape", async () => {
    const api = makeTestApi()
    setCompanionApi(api)

    render(<ShareWindow initialTarget={makeTarget()} />)
    await waitFor(() => {
      expect(screen.getByText(I18N.en.share_active_empty_title)).toBeInTheDocument()
    })

    expect(api.setWizardMode).not.toHaveBeenCalled()
    expect(api.subscribeMetrics).not.toHaveBeenCalled()

    const dragBar = screen.getByTestId("share-drag-bar")
    fireEvent.mouseDown(dragBar, { button: 0 })
    expect(api.startDrag).toHaveBeenCalledTimes(1)

    const closeBtn = screen.getByRole("button", { name: I18N.en.share_win_close_aria })
    fireEvent.mouseDown(closeBtn, { button: 0 })
    expect(api.startDrag).toHaveBeenCalledTimes(1)

    fireEvent.click(closeBtn)
    expect(api.closeShareWindow).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(window, { key: "Escape" })
    expect(api.closeShareWindow).toHaveBeenCalledTimes(2)
  })

  it("E1: truncates long basename/path/chip with exact title attributes, switches folder/file icons, and supports ?path= fallback", async () => {
    const longTarget = makeTarget({
      basename: "quarterly-financial-report-final-v2026-backup-extremely-long-filename.xlsx",
      canonical_rel:
        "DATA/Projects/Finance/2026/Q4/Reports/quarterly-financial-report-final-v2026-backup-extremely-long-filename.xlsx",
      server_name: "VeryLongMyServerName",
      disk_name: "DiskArchive01",
      is_dir: true,
    })

    const api = makeTestApi({
      getShareWindowTarget: vi.fn(async () => null),
      resolveSharePath: vi.fn(async () => ({ ok: true, target: longTarget })),
    })
    setCompanionApi(api)
    window.history.replaceState({}, "", "/?window=share&path=Z%3A%5CProjects%5CFinance")

    render(<ShareWindow />)

    await waitFor(() => {
      expect(screen.getByTitle(longTarget.basename)).toBeInTheDocument()
    })
    expect(api.resolveSharePath).toHaveBeenCalledWith("Z:\\Projects\\Finance")

    const basenameEl = screen.getByTitle(longTarget.basename)
    const relEl = screen.getByTitle(longTarget.canonical_rel)
    const chipTextEl = screen.getByTitle("VeryLongMyServerName · DiskArchive01")
    expect(basenameEl).toHaveClass("truncate")
    expect(relEl).toHaveClass("truncate")
    expect(chipTextEl).toHaveClass("truncate")
    expect(chipTextEl.closest("span.max-w-\\[120px\\]")).not.toBeNull()

    // Folder icon uses warning tint class on wrapper
    expect(screen.getByTestId("share-window").querySelector("[class*='text-warning']")).not.toBeNull()

    // Re-render with file target (is_dir: false) -> no warning folder tint
    cleanup()
    const fileTarget = makeTarget({ is_dir: false, basename: "notes.txt", canonical_rel: "DATA/notes.txt" })
    render(<ShareWindow initialTarget={fileTarget} />)
    await waitFor(() => {
      expect(screen.getByTitle("notes.txt")).toBeInTheDocument()
    })
    expect(screen.getByTestId("share-window").querySelector("[class*='text-warning']")).toBeNull()
  })

  it("SECH-03 (E2): omits public_base_url from DOM while loading and for non-admin, and validates/saves for admin", async () => {
    const deferred = createDeferred<ShareListResponse>()
    const apiLoading = makeTestApi({
      listShares: vi.fn(() => deferred.promise),
    })
    setCompanionApi(apiLoading)

    const { unmount } = render(<ShareWindow initialTarget={makeTarget()} />)

    // While pending: MUST be omitted from DOM + skeleton shown
    expect(screen.queryByLabelText(/Public Base URL/i)).toBeNull()
    expect(screen.getByTestId("active-links-skeleton")).toBeInTheDocument()

    // Resolve as non-admin: MUST remain completely omitted from DOM
    await act(async () => {
      deferred.resolve({
        success: true,
        shares: [],
        public_base_url: "https://secret-admin-domain.example.com",
        is_admin: false,
      })
    })
    await waitFor(() => {
      expect(screen.getByText(I18N.en.share_active_empty_title)).toBeInTheDocument()
    })
    expect(screen.queryByLabelText(/Public Base URL/i)).toBeNull()
    expect(document.querySelector("input[type='url']")).toBeNull()
    unmount()

    // Resolve as admin: present, pre-populated, validates URL, and calls updateShareSettings
    const updateShareSettings = vi.fn(async (url: string) => ({
      success: true,
      public_base_url: url,
    }))
    const apiAdmin = makeTestApi({
      listShares: vi.fn(async () => ({
        success: true,
        shares: [],
        public_base_url: "https://initial.example.com",
        is_admin: true,
      })),
      updateShareSettings,
    })
    setCompanionApi(apiAdmin)

    render(<ShareWindow initialTarget={makeTarget()} />)
    const urlInput = (await screen.findByLabelText(/Public Base URL/i)) as HTMLInputElement
    expect(urlInput.value).toBe("https://initial.example.com")

    // Invalid scheme rejected without API call
    fireEvent.change(urlInput, { target: { value: "ftp://bad.example.com" } })
    fireEvent.click(screen.getByRole("button", { name: I18N.en.share_public_base_save }))
    expect(screen.getByText(I18N.en.share_public_base_invalid)).toBeInTheDocument()
    expect(updateShareSettings).not.toHaveBeenCalled()

    // Valid https:// saved
    fireEvent.change(urlInput, { target: { value: "https://nas.example.com" } })
    fireEvent.click(screen.getByRole("button", { name: I18N.en.share_public_base_save }))
    await waitFor(() => {
      expect(updateShareSettings).toHaveBeenCalledWith("https://nas.example.com", "srv_1")
    })
    expect(screen.getByRole("status")).toHaveTextContent(I18N.en.share_public_base_saved)

    // Blank "" clears base URL cleanly
    fireEvent.change(urlInput, { target: { value: "" } })
    fireEvent.click(screen.getByRole("button", { name: I18N.en.share_public_base_save }))
    await waitFor(() => {
      expect(updateShareSettings).toHaveBeenCalledWith("", "srv_1")
    })
  })

  it("E2: toggles password visibility, validates custom expiry 1..8760 boundaries, guards double-submit, and preserves inputs on create failure", async () => {
    const pendingCreate = createDeferred<any>()
    const createShare = vi.fn(() => pendingCreate.promise)
    const api = makeTestApi({ createShare })
    setCompanionApi(api)

    render(<ShareWindow initialTarget={makeTarget()} />)
    await waitFor(() => {
      expect(screen.getByText(I18N.en.share_active_empty_title)).toBeInTheDocument()
    })

    // Password eye toggle
    const pwdInput = screen.getByPlaceholderText(I18N.en.share_password_placeholder) as HTMLInputElement
    expect(pwdInput.type).toBe("password")
    const toggleBtn = screen.getByRole("button", { name: I18N.en.share_password_show_aria })
    fireEvent.click(toggleBtn)
    expect(pwdInput.type).toBe("text")
    fireEvent.click(screen.getByRole("button", { name: I18N.en.share_password_hide_aria }))
    expect(pwdInput.type).toBe("password")

    // Custom expiry validation
    fireEvent.click(screen.getByRole("radio", { name: I18N.en.share_expiry_custom }))
    const customInput = screen.getByLabelText(I18N.en.share_expiry_custom) as HTMLInputElement
    expect(customInput.value).toBe("48")

    const submitBtn = screen.getByRole("button", { name: I18N.en.share_cta_create })
    for (const bad of ["0", "8761", "-5", "1.5", ""]) {
      fireEvent.change(customInput, { target: { value: bad } })
      expect(screen.getByText(I18N.en.share_expiry_invalid)).toBeInTheDocument()
      expect(submitBtn).toBeDisabled()
    }

    // Valid boundaries 1 and 8760 enable submit
    fireEvent.change(customInput, { target: { value: "1" } })
    expect(screen.queryByText(I18N.en.share_expiry_invalid)).toBeNull()
    expect(submitBtn).toBeEnabled()

    fireEvent.change(customInput, { target: { value: "8760" } })
    expect(screen.queryByText(I18N.en.share_expiry_invalid)).toBeNull()
    expect(submitBtn).toBeEnabled()

    // Enter password, click submit twice rapidly -> only 1 createShare call, button disabled & aria-busy
    fireEvent.change(pwdInput, { target: { value: "my-secret" } })
    fireEvent.click(submitBtn)
    expect(submitBtn).toBeDisabled()
    expect(submitBtn).toHaveAttribute("aria-busy", "true")
    fireEvent.click(submitBtn)
    expect(createShare).toHaveBeenCalledTimes(1)
    expect(createShare).toHaveBeenCalledWith({
      path: "DATA/Projects/Finance/report.pdf",
      server_id: "srv_1",
      password: "my-secret",
      expires_in_hours: 8760,
      label: "report.pdf",
      copy_to_clipboard: true,
    })

    // Resolve with error -> toast shown, inputs preserved, E3 card NOT shown
    await act(async () => {
      pendingCreate.resolve({
        success: false,
        code: "BACKEND_OFFLINE",
        error: "Backend offline",
      })
    })
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(I18N.en.share_err_offline)
    })
    expect(pwdInput.value).toBe("my-secret")
    expect(customInput.value).toBe("8760")
    expect(screen.queryByTestId("generated-share-card")).toBeNull()

    // Blank password submits password: null with Unlimited expiry
    fireEvent.change(pwdInput, { target: { value: "   " } })
    fireEvent.click(screen.getByRole("radio", { name: I18N.en.share_expiry_unlimited }))
    const createShare2 = vi.fn(async () => ({
      success: true,
      share: makeShare({ token: "tok_new1" }),
      share_url: "https://nas.example.com/s/tok_new1",
      is_lan_fallback: false,
      clipboard_copied: true,
    }))
    api.createShare = createShare2
    fireEvent.click(screen.getByRole("button", { name: I18N.en.share_cta_create }))
    await waitFor(() => {
      expect(createShare2).toHaveBeenCalledWith({
        path: "DATA/Projects/Finance/report.pdf",
        server_id: "srv_1",
        password: null,
        expires_in_hours: null,
        label: "report.pdf",
        copy_to_clipboard: true,
      })
    })
  })

  it("E3 & SECH-02: renders Generated Link Card with local QR SVG, LAN warnings (Admin vs Non-Admin), openExternalBrowser, and QR fallback", async () => {
    const winOpenSpy = vi.spyOn(window, "open").mockImplementation(() => null)

    const apiAdmin = makeTestApi({
      listShares: vi.fn(async () => ({
        success: true,
        shares: [],
        public_base_url: "",
        is_admin: true,
      })),
      createShare: vi.fn(async () => ({
        success: true,
        share: makeShare({ token: "tok_lan", is_lan_fallback: true }),
        share_url: "http://192.168.1.10:8085/s/tok_lan",
        is_lan_fallback: true,
        clipboard_copied: true,
      })),
    })
    setCompanionApi(apiAdmin)

    const { unmount } = render(<ShareWindow initialTarget={makeTarget()} />)
    await waitFor(() => {
      expect(screen.getByText(I18N.en.share_active_empty_title)).toBeInTheDocument()
    })

    // Hidden before creation
    expect(screen.queryByTestId("generated-share-card")).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: I18N.en.share_cta_create }))

    const card = await screen.findByTestId("generated-share-card")
    expect(within(card).getByText(I18N.en.share_copied_badge)).toBeInTheDocument()
    expect(within(card).getByTitle("http://192.168.1.10:8085/s/tok_lan")).toHaveClass("select-all")
    expect(within(card).getByText(I18N.en.share_lan_warn_admin)).toBeInTheDocument()
    expect(apiAdmin.copyShareClipboard).toHaveBeenCalledWith("http://192.168.1.10:8085/s/tok_lan")

    // Local SVG QR inside #FFFFFF quiet-zone container
    const qrSvg = within(card).getByRole("img", { name: I18N.en.share_qr_aria })
    expect(qrSvg.tagName.toLowerCase()).toBe("svg")
    expect(qrSvg.parentElement).toHaveClass("bg-[#FFFFFF]")

    // SECH-02: Open in Browser calls openExternalBrowser, never window.open
    fireEvent.click(within(card).getByRole("button", { name: I18N.en.share_btn_open_browser }))
    expect(apiAdmin.openExternalBrowser).toHaveBeenCalledWith("http://192.168.1.10:8085/s/tok_lan")
    expect(winOpenSpy).not.toHaveBeenCalled()

    // Copy Link button is idempotent
    fireEvent.click(within(card).getByRole("button", { name: I18N.en.share_btn_copy_link }))
    expect(apiAdmin.copyShareClipboard).toHaveBeenCalledTimes(2)

    unmount()

    // Non-admin LAN warning + QR encode failure graceful fallback
    mockEncodeState.shouldThrow = true
    const apiNonAdmin = makeTestApi({
      listShares: vi.fn(async () => ({
        success: true,
        shares: [],
        public_base_url: "",
        is_admin: false,
      })),
      createShare: vi.fn(async () => ({
        success: true,
        share: makeShare({ token: "tok_qr_err", is_lan_fallback: true }),
        share_url: "http://192.168.1.10:8085/s/tok_qr_err",
        is_lan_fallback: true,
        clipboard_copied: true,
      })),
    })
    setCompanionApi(apiNonAdmin)

    render(<ShareWindow initialTarget={makeTarget()} />)
    await waitFor(() => {
      expect(screen.getByText(I18N.en.share_active_empty_title)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole("button", { name: I18N.en.share_cta_create }))
    const card2 = await screen.findByTestId("generated-share-card")
    expect(within(card2).getByText(I18N.en.share_lan_warn_non_admin)).toBeInTheDocument()
    expect(within(card2).getByTestId("qr-fallback")).toHaveTextContent(I18N.en.share_qr_fallback)
    expect(within(card2).getByRole("button", { name: I18N.en.share_btn_copy_link })).toBeEnabled()
    expect(within(card2).getByRole("button", { name: I18N.en.share_btn_open_browser })).toBeEnabled()
  })

  it("E4: filters revoked/expired/other-path shares, handles 0/1/many singular/plural downloads, list error retry, and inline 2-step revoke", async () => {
    const winOpenSpy = vi.spyOn(window, "open").mockImplementation(() => null)
    const futureIso = new Date(Date.now() + 24 * 3600 * 1000).toISOString()
    const pastIso = new Date(Date.now() - 3600 * 1000).toISOString()

    // 1. Error state allows Refresh Links retry without blocking E2 creation
    const listMock = vi
      .fn()
      .mockResolvedValueOnce({
        success: false,
        shares: [],
        public_base_url: "",
        is_admin: false,
        error: "Network timeout",
      })
      .mockResolvedValueOnce({
        success: true,
        shares: [
          makeShare({ token: "tok_valid1", download_count: 1, password_protected: false, expires_at: null }),
          makeShare({ token: "tok_revoked", revoked: true, download_count: 5 }),
          makeShare({ token: "tok_expired", expires_at: pastIso, download_count: 2 }),
          makeShare({ token: "tok_other", target_path: "DATA/other.pdf", download_count: 4 }),
        ],
        public_base_url: "",
        is_admin: false,
      })

    const revokeDeferred = createDeferred<any>()
    const revokeShare = vi
      .fn()
      .mockResolvedValueOnce({ success: false, error: "Server busy" })
      .mockImplementationOnce(() => revokeDeferred.promise)

    const api = makeTestApi({
      listShares: listMock,
      revokeShare,
      createShare: vi.fn(async () => ({
        success: true,
        share: makeShare({
          token: "tok_created_top",
          download_count: 3,
          password_protected: true,
          expires_at: futureIso,
        }),
        share_url: "https://nas.example.com/s/tok_created_top",
        is_lan_fallback: false,
        clipboard_copied: true,
      })),
    })
    setCompanionApi(api)

    render(<ShareWindow initialTarget={makeTarget()} />)

    // Error rendered + E2 form still enabled
    await waitFor(() => {
      expect(screen.getByText("Network timeout")).toBeInTheDocument()
    })
    expect(screen.getByRole("button", { name: I18N.en.share_cta_create })).toBeEnabled()

    // Retry loads filtered 1 active link (excludes revoked, expired, other target_path)
    fireEvent.click(screen.getByRole("button", { name: I18N.en.share_btn_refresh_links }))
    await waitFor(() => {
      expect(screen.getByTestId("active-share-row-tok_valid1")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("active-share-row-tok_revoked")).toBeNull()
    expect(screen.queryByTestId("active-share-row-tok_expired")).toBeNull()
    expect(screen.queryByTestId("active-share-row-tok_other")).toBeNull()

    const row1 = screen.getByTestId("active-share-row-tok_valid1")
    expect(within(row1).getByText("1 download")).toBeInTheDocument()
    expect(within(row1).getByText(I18N.en.share_expiry_unlimited)).toBeInTheDocument()
    expect(within(row1).queryByText(I18N.en.share_chip_password)).toBeNull()

    // Row Open button uses openExternalBrowser
    fireEvent.click(within(row1).getByRole("button", { name: I18N.en.share_btn_open_aria }))
    expect(api.openExternalBrowser).toHaveBeenCalledWith("http://192.168.1.10:8085/s/tok_valid1")
    expect(winOpenSpy).not.toHaveBeenCalled()

    // Create another link -> placed at top, plural "3 downloads" + Password chip shown
    fireEvent.click(screen.getByRole("button", { name: I18N.en.share_cta_create }))
    const createdRow = await screen.findByTestId("active-share-row-tok_created_top")
    expect(within(createdRow).getByText("3 downloads")).toBeInTheDocument()
    expect(within(createdRow).getByText(I18N.en.share_chip_password)).toBeInTheDocument()
    expect(screen.getByTestId("generated-share-card")).toBeInTheDocument()

    // Inline 2-step Revoke: Keep Link cancels without API call
    fireEvent.click(within(createdRow).getByRole("button", { name: I18N.en.share_btn_revoke_aria }))
    expect(within(createdRow).getByText(I18N.en.share_revoke_confirm_prompt)).toBeInTheDocument()
    fireEvent.click(within(createdRow).getByRole("button", { name: I18N.en.share_btn_keep_link }))
    expect(revokeShare).not.toHaveBeenCalled()
    expect(within(createdRow).queryByText(I18N.en.share_revoke_confirm_prompt)).toBeNull()

    // Confirm Revoke failure keeps row intact + shows toast
    fireEvent.click(within(createdRow).getByRole("button", { name: I18N.en.share_btn_revoke_aria }))
    fireEvent.click(within(createdRow).getByRole("button", { name: I18N.en.share_btn_revoke_link }))
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("Server busy")
    })
    expect(screen.getByTestId("active-share-row-tok_created_top")).toBeInTheDocument()
    expect(screen.getByTestId("generated-share-card")).toBeInTheDocument()

    // Second confirm enters busy state then removes row AND hides E3 card
    const confirmBtn = within(createdRow).getByRole("button", { name: I18N.en.share_btn_revoke_link })
    fireEvent.click(confirmBtn)
    expect(confirmBtn).toBeDisabled()
    expect(confirmBtn).toHaveAttribute("aria-busy", "true")

    await act(async () => {
      revokeDeferred.resolve({ success: true })
    })
    await waitFor(() => {
      expect(screen.queryByTestId("active-share-row-tok_created_top")).toBeNull()
    })
    expect(screen.queryByTestId("generated-share-card")).toBeNull()
    expect(screen.getByRole("status")).toHaveTextContent(I18N.en.share_revoked_toast)
  })

  it("handles myserver:share-target re-target updates in-place and renders Indonesian (id) + light theme copy", async () => {
    const firstTarget = makeTarget({ basename: "first.pdf", canonical_rel: "DATA/first.pdf" })
    const secondTarget = makeTarget({ basename: "second-folder", canonical_rel: "DATA/second-folder", is_dir: true })

    const listShares = vi.fn(async (opts?: { targetPath?: string }) => ({
      success: true,
      shares:
        opts?.targetPath === "DATA/second-folder"
          ? [makeShare({ token: "tok_second", target_path: "DATA/second-folder", download_count: 2 })]
          : [],
      public_base_url: "",
      is_admin: false,
    }))

    const api = makeTestApi({
      loadSettings: vi.fn(async () => ({
        autostart: true,
        openDashboard: false,
        autoMountSmb: true,
        autoZeroTier: true,
        autoCleanOnExit: true,
        language: "id" as const,
        theme: "light" as const,
        explorerContextMenuEnabled: false,
      })),
      listShares,
    })
    setCompanionApi(api)

    render(<ShareWindow initialTarget={firstTarget} />)

    await waitFor(() => {
      expect(screen.getByTestId("share-window")).toHaveAttribute("data-theme", "light")
    })
    expect(screen.getByRole("button", { name: I18N.id.share_cta_create })).toBeInTheDocument()
    expect(screen.getByText(I18N.id.share_active_empty_title)).toBeInTheDocument()

    // Dispatch myserver:share-target event to switch target in-place
    act(() => {
      window.dispatchEvent(new CustomEvent("myserver:share-target", { detail: secondTarget }))
    })

    await waitFor(() => {
      expect(screen.getByTitle("second-folder")).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByTestId("active-share-row-tok_second")).toBeInTheDocument()
    })

    const secondRow = screen.getByTestId("active-share-row-tok_second")
    expect(within(secondRow).getByText("2 unduhan")).toBeInTheDocument()
    fireEvent.click(within(secondRow).getByRole("button", { name: I18N.id.share_btn_revoke_aria }))
    expect(within(secondRow).getByText(I18N.id.share_revoke_confirm_prompt)).toBeInTheDocument()
    expect(within(secondRow).getByRole("button", { name: I18N.id.share_btn_keep_link })).toBeInTheDocument()
    expect(within(secondRow).getByRole("button", { name: I18N.id.share_btn_revoke_link })).toBeInTheDocument()
  })

  it("WR-02: does not re-run hydrateTarget/fetchShares when loadSettings changes language to id, and ignores stale listShares responses", async () => {
    const firstTarget = makeTarget({ basename: "first.pdf", canonical_rel: "DATA/first.pdf" })
    const secondTarget = makeTarget({ basename: "second.pdf", canonical_rel: "DATA/second.pdf" })

    const settingsDeferred = createDeferred<any>()
    const firstListDeferred = createDeferred<ShareListResponse>()
    const secondListDeferred = createDeferred<ShareListResponse>()

    const getShareWindowTarget = vi.fn(async () => firstTarget)
    const listShares = vi
      .fn()
      .mockImplementationOnce(() => firstListDeferred.promise)
      .mockImplementationOnce(() => secondListDeferred.promise)

    const api = makeTestApi({
      loadSettings: vi.fn(() => settingsDeferred.promise),
      getShareWindowTarget,
      listShares,
    })
    setCompanionApi(api)

    render(<ShareWindow />)

    await waitFor(() => {
      expect(listShares).toHaveBeenCalledTimes(1)
    })
    expect(getShareWindowTarget).toHaveBeenCalledTimes(1)

    // Switch language asynchronously from "en" -> "id": must NOT re-trigger hydrateTarget or listShares
    await act(async () => {
      settingsDeferred.resolve({
        autostart: true,
        openDashboard: false,
        autoMountSmb: true,
        autoZeroTier: true,
        autoCleanOnExit: true,
        language: "id" as const,
        theme: "dark" as const,
        explorerContextMenuEnabled: false,
      })
    })
    await waitFor(() => {
      expect(screen.getByRole("button", { name: I18N.id.share_cta_create })).toBeInTheDocument()
    })
    expect(getShareWindowTarget).toHaveBeenCalledTimes(1)
    expect(listShares).toHaveBeenCalledTimes(1)

    // Re-target while first listShares is still pending, then resolve second BEFORE first
    act(() => {
      window.dispatchEvent(new CustomEvent("myserver:share-target", { detail: secondTarget }))
    })
    await waitFor(() => {
      expect(listShares).toHaveBeenCalledTimes(2)
    })

    await act(async () => {
      secondListDeferred.resolve({
        success: true,
        shares: [makeShare({ token: "tok_fresh", target_path: "DATA/second.pdf" })],
        public_base_url: "https://fresh.example.com",
        is_admin: true,
      })
    })
    await waitFor(() => {
      expect(screen.getByTestId("active-share-row-tok_fresh")).toBeInTheDocument()
    })

    // Now resolve the stale first request with is_admin: false and different shares — must be ignored
    await act(async () => {
      firstListDeferred.resolve({
        success: true,
        shares: [makeShare({ token: "tok_stale", target_path: "DATA/first.pdf" })],
        public_base_url: "",
        is_admin: false,
      })
    })
    expect(screen.getByTestId("active-share-row-tok_fresh")).toBeInTheDocument()
    expect(screen.queryByTestId("active-share-row-tok_stale")).toBeNull()
    expect(screen.getByLabelText(/Public Base URL/i)).toHaveValue("https://fresh.example.com")
  })
})

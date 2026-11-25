import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { I18N } from "../i18n"
import type {
  ExplorerClipboardState,
  QuickPickerBrowseResponse,
  TransferStatusResponse,
} from "../types"
import { TransferWindow } from "../transfer/TransferWindow"

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (err: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function makeStatus(overrides: Partial<TransferStatusResponse> = {}): TransferStatusResponse {
  return {
    success: true,
    mode: "progress",
    job_id: "job_1",
    direction: "upload",
    status: "idle",
    dest_label: "DATA/Projects",
    total_files: 0,
    completed_files: 0,
    bytes_done: 0,
    bytes_total: 0,
    speed_bps: 0,
    eta_seconds: null,
    active_workers: 0,
    max_workers: 3,
    conflict: null,
    items: [],
    ...overrides,
  }
}

function makeClipboard(overrides: Partial<ExplorerClipboardState> = {}): ExplorerClipboardState {
  return {
    kind: "local",
    items: [{ path: "C:\\Users\\Demo\\report.pdf", name: "report.pdf", is_dir: false, size: 1024 }],
    ...overrides,
  }
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
      explorerHotkeyEnabled: true,
    })),
    subscribeMetrics: vi.fn(() => () => {}),
    setWizardMode: vi.fn(async () => undefined),
    startDrag: vi.fn(async () => undefined),
    closeTransferWindow: vi.fn(async () => undefined),
    getTransferWindowState: vi.fn(async () => null),
    getTransferStatus: vi.fn(async () => makeStatus()),
    getExplorerClipboard: vi.fn(async () => makeClipboard()),
    browseTransferDirectory: vi.fn(async () => ({
      success: true,
      server_id: "srv_1",
      server_name: "MyServer-Main",
      current_path: "",
      parent_path: "",
      effective_role: "owner",
      writable: true,
      view_mode: "disks",
      items: [
        {
          name: "DATA",
          relative_path: "DATA",
          is_dir: true,
          effective_role: "owner",
          writable: true,
        },
      ],
    })),
    startTransferPaste: vi.fn(async () =>
      makeStatus({
        status: "running",
        total_files: 2,
        completed_files: 1,
        bytes_done: 512,
        bytes_total: 1024,
        speed_bps: 2048,
        eta_seconds: 10,
        active_workers: 2,
        max_workers: 3,
      }),
    ),
    resolveTransferConflict: vi.fn(async () => makeStatus({ status: "running", active_workers: 2 })),
    pauseTransferJob: vi.fn(async () => makeStatus({ status: "paused", active_workers: 0 })),
    resumeTransferJob: vi.fn(async () => makeStatus({ status: "running", active_workers: 2 })),
    cancelTransferJob: vi.fn(async () => makeStatus({ status: "cancelled", active_workers: 0 })),
    clearTransferHistory: vi.fn(async () => ({ success: true })),
    copyServerItemsToClipboard: vi.fn(async ({ items }) => ({
      success: true,
      clipboard: { kind: "server" as const, items },
    })),
    ...overrides,
  }
}

describe("TransferWindow", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/?window=transfer")
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it("enforces anti-lock isolation (never calls setWizardMode or subscribeMetrics) and supports drag + close + Escape", async () => {
    const api = makeTestApi()
    setCompanionApi(api)

    render(<TransferWindow />)

    const win = await screen.findByTestId("transfer-window")
    expect(win).toHaveAttribute("data-theme", "dark")

    expect(api.setWizardMode).not.toHaveBeenCalled()
    expect(api.subscribeMetrics).not.toHaveBeenCalled()

    const dragBar = screen.getByTestId("transfer-drag-bar")
    fireEvent.mouseDown(dragBar, { button: 0 })
    expect(api.startDrag).toHaveBeenCalledTimes(1)

    const closeBtn = screen.getByRole("button", { name: I18N.en.xfer_close_aria })
    fireEvent.click(closeBtn)
    expect(api.closeTransferWindow).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(window, { key: "Escape" })
    expect(api.closeTransferWindow).toHaveBeenCalledTimes(2)
  })

  it("supports Light theme and Indonesian (id) localization", async () => {
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
        explorerHotkeyEnabled: true,
      })),
    })
    setCompanionApi(api)

    render(<TransferWindow />)

    const win = await screen.findByTestId("transfer-window")
    await waitFor(() => expect(win).toHaveAttribute("data-theme", "light"))
    expect(screen.getByText(I18N.id.xfer_empty_title)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: I18N.id.xfer_close_aria })).toBeInTheDocument()
  })

  it("Quick Picker: navigates Disks & Shared with Me, locks Paste Here for Viewer role, and enables Paste for Editor/Owner", async () => {
    const browseMock = vi.fn(async (opts?: { source?: string; path?: string }) => {
      if (opts?.source === "shared" && !opts?.path) {
        return {
          success: true,
          server_id: "srv_1",
          current_path: "",
          parent_path: "",
          effective_role: "viewer",
          writable: false,
          view_mode: "shared" as const,
          items: [
            {
              name: "ReadOnlyShare",
              relative_path: "DATA/ReadOnlyShare",
              is_dir: true,
              effective_role: "viewer",
              writable: false,
              owner_username: "alice",
            },
            {
              name: "TeamDocs",
              relative_path: "DATA/TeamDocs",
              is_dir: true,
              effective_role: "editor",
              writable: true,
              owner_username: "bob",
            },
          ],
        } satisfies QuickPickerBrowseResponse
      }
      if (opts?.path === "DATA/ReadOnlyShare") {
        return {
          success: true,
          server_id: "srv_1",
          current_path: "DATA/ReadOnlyShare",
          parent_path: "",
          effective_role: "viewer",
          writable: false,
          view_mode: "folder" as const,
          items: [],
        } satisfies QuickPickerBrowseResponse
      }
      if (opts?.path === "DATA/TeamDocs") {
        return {
          success: true,
          server_id: "srv_1",
          current_path: "DATA/TeamDocs",
          parent_path: "",
          effective_role: "editor",
          writable: true,
          view_mode: "folder" as const,
          items: [],
        } satisfies QuickPickerBrowseResponse
      }
      return {
        success: true,
        server_id: "srv_1",
        current_path: "",
        parent_path: "",
        effective_role: "owner",
        writable: true,
        view_mode: "disks" as const,
        items: [
          {
            name: "DATA",
            relative_path: "DATA",
            is_dir: true,
            effective_role: "owner",
            writable: true,
          },
        ],
      } satisfies QuickPickerBrowseResponse
    })

    const api = makeTestApi({ browseTransferDirectory: browseMock })
    setCompanionApi(api)

    render(<TransferWindow initialMode="quick_picker" />)

    expect(await screen.findByText("DATA")).toBeInTheDocument()

    // Switch to Shared with Me
    fireEvent.click(screen.getByRole("button", { name: I18N.en.xfer_qp_shared_with_me }))
    expect(await screen.findByText("ReadOnlyShare")).toBeInTheDocument()

    // Viewer folder locks Paste Here + shows warning banner
    fireEvent.click(screen.getByText("ReadOnlyShare"))
    expect(await screen.findByTestId("quick-picker-viewer-banner")).toHaveTextContent(
      I18N.en.xfer_qp_viewer_locked,
    )
    const pasteBtn = screen.getByRole("button", { name: I18N.en.xfer_qp_btn_paste_here })
    expect(pasteBtn).toBeDisabled()

    // Go back and open Editor folder
    fireEvent.click(screen.getByRole("button", { name: "Back" }))
    expect(await screen.findByText("TeamDocs")).toBeInTheDocument()
    fireEvent.click(screen.getByText("TeamDocs"))

    await waitFor(() =>
      expect(screen.queryByTestId("quick-picker-viewer-banner")).not.toBeInTheDocument(),
    )
    expect(pasteBtn).toBeEnabled()
    fireEvent.click(pasteBtn)

    await waitFor(() =>
      expect(api.startTransferPaste).toHaveBeenCalledWith({
        serverId: "srv_1",
        destRel: "DATA/TeamDocs",
      }),
    )
  })

  it("drops stale browseTransferDirectory responses when switching folders rapidly", async () => {
    const slowDeferred = createDeferred<QuickPickerBrowseResponse>()
    const browseMock = vi
      .fn()
      .mockResolvedValueOnce({
        success: true,
        server_id: "srv_1",
        current_path: "",
        parent_path: "",
        effective_role: "owner",
        writable: true,
        items: [
          { name: "SlowDir", relative_path: "DATA/SlowDir", is_dir: true, writable: true },
          { name: "FastDir", relative_path: "DATA/FastDir", is_dir: true, writable: true },
        ],
      })
      .mockImplementationOnce(() => slowDeferred.promise)
      .mockResolvedValueOnce({
        success: true,
        server_id: "srv_1",
        current_path: "DATA/FastDir",
        parent_path: "",
        effective_role: "owner",
        writable: true,
        items: [{ name: "fast-file.txt", relative_path: "DATA/FastDir/fast-file.txt", is_dir: false, writable: true }],
      })

    const api = makeTestApi({ browseTransferDirectory: browseMock })
    setCompanionApi(api)

    render(<TransferWindow initialMode="quick_picker" />)
    expect(await screen.findByText("SlowDir")).toBeInTheDocument()

    fireEvent.click(screen.getByText("SlowDir"))
    fireEvent.click(screen.getByText("FastDir"))

    expect(await screen.findByText("fast-file.txt")).toBeInTheDocument()

    // Resolve stale SlowDir request — should NOT overwrite FastDir
    await act(async () => {
      slowDeferred.resolve({
        success: true,
        server_id: "srv_1",
        current_path: "DATA/SlowDir",
        parent_path: "",
        effective_role: "owner",
        writable: true,
        items: [{ name: "stale-file.txt", relative_path: "DATA/SlowDir/stale-file.txt", is_dir: false, writable: true }],
      })
    })

    expect(screen.getByText("fast-file.txt")).toBeInTheDocument()
    expect(screen.queryByText("stale-file.txt")).not.toBeInTheDocument()
  })

  it("renders Windows-Style Conflict Modal on awaiting_conflict and resolves overwrite/rename/skip with applyToAll", async () => {
    const conflictStatus = makeStatus({
      status: "awaiting_conflict",
      job_id: "job_conflict",
      conflict: {
        job_id: "job_conflict",
        item_name: "budget.xlsx",
        dest_path: "DATA/Finance/budget.xlsx",
        is_dir: false,
        remaining_conflicts_hint: 2,
      },
    })

    const api = makeTestApi({
      getTransferStatus: vi.fn(async () => conflictStatus),
    })
    setCompanionApi(api)

    render(<TransferWindow />)

    const modal = await screen.findByTestId("transfer-conflict-modal")
    expect(modal).toBeInTheDocument()
    expect(screen.getAllByText(/budget\.xlsx/).length).toBeGreaterThanOrEqual(1)

    const applyAllCheckbox = screen.getByRole("checkbox", { name: I18N.en.xfer_conflict_apply_all })
    fireEvent.click(applyAllCheckbox)
    expect(applyAllCheckbox).toBeChecked()

    fireEvent.click(screen.getByRole("button", { name: I18N.en.xfer_conflict_overwrite }))
    await waitFor(() =>
      expect(api.resolveTransferConflict).toHaveBeenCalledWith({
        jobId: "job_conflict",
        action: "overwrite",
        applyToAll: true,
      }),
    )
  })

  it("Floating Progress Queue: displays N/3 workers, speed, progress, and calls Pause/Resume/Cancel", async () => {
    const runningStatus = makeStatus({
      status: "running",
      job_id: "job_prog",
      total_files: 4,
      completed_files: 2,
      bytes_done: 1024 * 1024,
      bytes_total: 2 * 1024 * 1024,
      speed_bps: 512 * 1024,
      eta_seconds: 12,
      active_workers: 2,
      max_workers: 3,
      items: [
        {
          id: "it_1",
          name: "video.mp4",
          bytes_done: 1024 * 1024,
          bytes_total: 2 * 1024 * 1024,
          status: "active",
        },
      ],
    })

    const api = makeTestApi({
      getTransferStatus: vi.fn(async () => runningStatus),
      pauseTransferJob: vi.fn(async () =>
        makeStatus({ job_id: "job_prog", status: "paused", active_workers: 0 }),
      ),
      resumeTransferJob: vi.fn(async () =>
        makeStatus({ job_id: "job_prog", status: "running", active_workers: 2 }),
      ),
      cancelTransferJob: vi.fn(async () =>
        makeStatus({ job_id: "job_prog", status: "cancelled", active_workers: 0 }),
      ),
    })
    setCompanionApi(api)

    render(<TransferWindow />)

    expect(await screen.findByTestId("transfer-workers-pill")).toHaveTextContent("2/3")
    expect(screen.getByText("512.0 KB/s")).toBeInTheDocument()
    expect(screen.getAllByText("50%").length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText("video.mp4")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: I18N.en.xfer_btn_pause }))
    await waitFor(() => expect(api.pauseTransferJob).toHaveBeenCalledWith("job_prog"))

    // Now paused -> Resume button appears
    fireEvent.click(await screen.findByRole("button", { name: I18N.en.xfer_btn_resume }))
    await waitFor(() => expect(api.resumeTransferJob).toHaveBeenCalledWith("job_prog"))

    // Cancel button
    fireEvent.click(await screen.findByRole("button", { name: I18N.en.xfer_btn_cancel }))
    await waitFor(() => expect(api.cancelTransferJob).toHaveBeenCalledWith("job_prog"))
  })

  it("HTTP Browse mode: Copy to Desktop calls copyServerItemsToClipboard with full item metadata", async () => {
    const api = makeTestApi({
      browseTransferDirectory: vi.fn(async () => ({
        success: true,
        server_id: "srv_1",
        current_path: "DATA/Projects",
        parent_path: "DATA",
        effective_role: "owner",
        writable: true,
        items: [
          {
            name: "Archive",
            relative_path: "DATA/Projects/Archive",
            is_dir: true,
            writable: true,
          },
          {
            name: "notes.txt",
            relative_path: "DATA/Projects/notes.txt",
            is_dir: false,
            size: 4096,
            writable: true,
          },
        ],
      })),
    })
    setCompanionApi(api)

    render(<TransferWindow initialMode="browse" />)

    expect(await screen.findByText("Archive")).toBeInTheDocument()
    const copyButtons = screen.getAllByRole("button", { name: I18N.en.xfer_qp_btn_copy_desktop })
    expect(copyButtons).toHaveLength(2)

    fireEvent.click(copyButtons[0])
    await waitFor(() =>
      expect(api.copyServerItemsToClipboard).toHaveBeenCalledWith({
        serverId: "srv_1",
        items: [
          {
            relative_path: "DATA/Projects/Archive",
            name: "Archive",
            is_dir: true,
            size: undefined,
          },
        ],
      }),
    )
  })
})

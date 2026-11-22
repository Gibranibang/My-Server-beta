import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { CompanionStoreProvider, NoticeProvider } from "../store"
import TrayDock from "../TrayDock"
import type { Drive, Metrics } from "../types"

function renderTrayDock(metricsPatch: Partial<Metrics>, drivesList: Drive[]) {
  const api: CompanionApi = createMockApi()
  const baseLoadSettings = api.loadSettings.bind(api)
  api.loadSettings = vi.fn(async () => ({
    ...(await baseLoadSettings()),
    firstRunSetup: false,
    language: "id" as const,
  }))
  api.listDrives = vi.fn(async () => drivesList)
  api.subscribeMetrics = vi.fn((cb) => {
    cb({
      cpu: 55,
      ram: 31,
      hdd: 35,
      lanDown: 0.1,
      lanHistory: Array(12).fill(0),
      syncUp: 0,
      syncDown: 0,
      storageUsedBytes: 165 * 1024 ** 3,
      storageTotalBytes: 476 * 1024 ** 3,
      storagePartitions: [{ name: "System Storage (/DATA)", used_bytes: 165 * 1024 ** 3, total_bytes: 476 * 1024 ** 3 }],
      isLoading: false,
      ...metricsPatch,
    })
    return () => {}
  }) as unknown as CompanionApi["subscribeMetrics"]
  api.subscribePower = vi.fn((cb) => {
    cb("online")
    return () => {}
  }) as unknown as CompanionApi["subscribePower"]

  setCompanionApi(api)
  return render(
    <NoticeProvider>
      <CompanionStoreProvider>
        <TrayDock powerActive={false} onNavigate={() => {}} />
      </CompanionStoreProvider>
    </NoticeProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("TrayDock DISK telemetry isolation & remote FUSE filtering", () => {
  it("uses metrics.hdd directly in backend SMB mode instead of 100 TB cloud drives", async () => {
    renderTrayDock(
      { smbSource: "backend", hdd: 35 },
      [
        {
          letter: "Y",
          name: "CloudDrive_A",
          free: "99.9 TB",
          total: "100 TB",
          usedPct: 0,
          mounted: true,
          totalBytes: 100 * 1024 ** 4,
          usedBytes: 100 * 1024 ** 3,
          isRemote: true,
        },
        {
          letter: "X",
          name: "CloudDrive_B",
          free: "4.99 TB",
          total: "5.00 TB",
          usedPct: 0,
          mounted: true,
          totalBytes: 5 * 1024 ** 4,
          usedBytes: 10 * 1024 ** 3,
          isRemote: true,
        },
      ],
    )

    const diskBtn = await screen.findByRole("button", { name: /^DISK: 35% terpakai/i })
    expect(diskBtn).toHaveAttribute("aria-label", expect.stringContaining("35% terpakai"))
    expect(diskBtn).toHaveAttribute("aria-label", expect.stringContaining("1 partisi"))
  })

  it("excludes isRemote cloud drives from physical drive capacity averaging in zimaos mode", async () => {
    renderTrayDock(
      { smbSource: "zimaos", hdd: 35 },
      [
        {
          letter: "Z",
          name: "LocalPool",
          free: "311 GB",
          total: "476 GB",
          usedPct: 35,
          mounted: true,
          totalBytes: 476 * 1024 ** 3,
          usedBytes: 165 * 1024 ** 3,
          isRemote: false,
        },
        {
          letter: "Y",
          name: "CloudDrive_A",
          free: "99.9 TB",
          total: "100 TB",
          usedPct: 0,
          mounted: true,
          totalBytes: 100 * 1024 ** 4,
          usedBytes: 100 * 1024 ** 3,
          isRemote: true,
        },
      ],
    )

    const diskBtn = await screen.findByRole("button", { name: /^DISK: 35% terpakai/i })
    expect(diskBtn).toHaveAttribute("aria-label", expect.stringContaining("1 disk"))
  })

  it("falls back to metrics.hdd when drives only contain remote or zero-byte subfolder shares", async () => {
    renderTrayDock(
      { smbSource: "zimaos", hdd: 35 },
      [
        {
          letter: "U",
          name: "SubShare",
          free: "0 B",
          total: "0 B",
          usedPct: 0,
          mounted: true,
          totalBytes: 0,
          usedBytes: 0,
          isRemote: false,
        },
        {
          letter: "Y",
          name: "CloudDrive_A",
          free: "99.9 TB",
          total: "100 TB",
          usedPct: 0,
          mounted: true,
          totalBytes: 100 * 1024 ** 4,
          usedBytes: 100 * 1024 ** 3,
          isRemote: true,
        },
      ],
    )

    const diskBtn = await screen.findByRole("button", { name: /^DISK: 35% terpakai/i })
    expect(diskBtn).toHaveAttribute("aria-label", expect.stringContaining("35% terpakai"))
  })
})

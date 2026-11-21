import React from "react"
import fs from "node:fs"
import path from "node:path"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { CompanionStoreProvider, NoticeProvider } from "../store"
import HomeView from "../views/HomeView"
import type { RouteEntry } from "../types"

function setupHomeView(routes: RouteEntry[], activeHost: string, activeRoute = "auto") {
  const api: CompanionApi = createMockApi()
  const baseLoadSettings = api.loadSettings.bind(api)
  api.loadSettings = vi.fn(async () => ({
    ...(await baseLoadSettings()),
    firstRunSetup: false,
    language: "id",
  }))

  api.subscribeMetrics = vi.fn(() => () => {}) as unknown as CompanionApi["subscribeMetrics"]
  api.subscribePower = vi.fn((cb) => {
    cb("online")
    return () => {}
  }) as unknown as CompanionApi["subscribePower"]

  api.getServerDetails = vi.fn(async () => ({
    serverId: "srv_1",
    serverName: "ZimaServer",
    activeHost,
    activeRoute,
    routes,
    activeProfile: "admin",
    profiles: ["admin"],
    uptimeStr: "2d",
  })) as unknown as CompanionApi["getServerDetails"]

  setCompanionApi(api)
  const go = vi.fn()
  const rendered = render(
    <NoticeProvider>
      <CompanionStoreProvider>
        <HomeView go={go} />
      </CompanionStoreProvider>
    </NoticeProvider>,
  )
  return { api, go, ...rendered }
}

async function renderAndCaptureRouteIcons(routes: RouteEntry[], activeHost: string) {
  const { container } = setupHomeView(routes, activeHost)
  const pillBtn = await screen.findByTitle("Ganti Rute Akses", {}, { timeout: 2500 })
  const pillSvg = pillBtn.querySelector("svg")
  expect(pillSvg).not.toBeNull()
  const pillIconHtml = pillSvg!.innerHTML

  fireEvent.click(pillBtn)

  const activeBadge = await screen.findByText("Aktif")
  const summaryCard = activeBadge.closest(".rounded-tile")
  expect(summaryCard).not.toBeNull()
  const modalSvg = summaryCard!.querySelector("svg")
  expect(modalSvg).not.toBeNull()
  const modalIconHtml = modalSvg!.innerHTML

  return { pillBtn, pillIconHtml, modalIconHtml, container }
}

describe("HomeView dynamic footer route pill icon (RPI-01, D-04, 06-UI-SPEC Surface 1)", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    localStorage.clear()
    setCompanionApi(createMockApi())
  })

  it("Test 1 (LAN) & Test 2 (WAN) & Test 3 (Remote): renders dynamic Network, Globe, and Remote icons in footer pill matching Switch Access Route modal 1:1", async () => {
    // Test 1: LAN route
    const lanRes = await renderAndCaptureRouteIcons(
      [{ id: "lan", name: "LAN", url: "http://192.168.1.100:80", active: true }],
      "http://192.168.1.100:80",
    )
    expect(lanRes.pillBtn).toHaveTextContent("LAN")
    expect(lanRes.pillIconHtml).toBe(lanRes.modalIconHtml)
    const lanSvgHtml = lanRes.pillIconHtml
    cleanup()

    // Test 2: WAN route
    const wanRes = await renderAndCaptureRouteIcons(
      [{ id: "wan", name: "WAN", url: "https://nas.algitha.com", active: true }],
      "https://nas.algitha.com",
    )
    expect(wanRes.pillBtn).toHaveTextContent("WAN")
    expect(wanRes.pillIconHtml).toBe(wanRes.modalIconHtml)
    const wanSvgHtml = wanRes.pillIconHtml
    cleanup()

    // Test 3: Remote route (EasyTier / ZeroTier)
    const remoteRes = await renderAndCaptureRouteIcons(
      [
        {
          id: "remote",
          name: "Remote EasyTier",
          url: "http://10.126.126.1:80",
          active: true,
          isEasyTier: true,
        },
      ],
      "http://10.126.126.1:80",
    )
    expect(remoteRes.pillBtn).toHaveTextContent("Remote")
    expect(remoteRes.pillIconHtml).toBe(remoteRes.modalIconHtml)
    const remoteSvgHtml = remoteRes.pillIconHtml

    // Verify all three route icons are distinct Lucide SVGs
    expect(lanSvgHtml).not.toBe(wanSvgHtml)
    expect(remoteSvgHtml).not.toBe(wanSvgHtml)
    expect(lanSvgHtml).not.toBe(remoteSvgHtml)
  })

  it("Test 4 (Strict 1-line isolation, D-04, T-06-07): verifies HomeView.tsx line 327 uses <currentRouteMeta.icon with 639 total lines and lines 296-299 untouched", () => {
    const homeViewPath = path.resolve(__dirname, "../views/HomeView.tsx")
    const raw = fs.readFileSync(homeViewPath, "utf-8")
    const lines = raw.split(/\r?\n/)
    // File ends with trailing newline -> 640 lines before final empty split element (or 640 lines)
    const nonTrailingLines = lines[lines.length - 1] === "" ? lines.slice(0, -1) : lines
    expect(nonTrailingLines.length).toBe(639)

    // 1-indexed line 327 -> 0-indexed lines[326]
    expect(lines[326].trim()).toBe(
      '<currentRouteMeta.icon className={cx("size-[10.07px] shrink-0", isOnline ? "text-[#047857]" : "text-[#2D2D2D]")} strokeWidth={1.8} />',
    )

    // Verify lines 296-299 (onOpenExplorer) remain 100% untouched for Phase 7 orthogonality
    expect(lines[295].trim()).toBe("onOpenExplorer={() => {")
    expect(lines[296].trim()).toBe("api.openFileManager()")
    expect(lines[297].trim()).toBe('notify("Membuka Windows File Explorer...", "info")')
    expect(lines[298].trim()).toBe("}}")
  })
})

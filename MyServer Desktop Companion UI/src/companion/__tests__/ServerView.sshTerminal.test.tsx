import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { createMockApi, setCompanionApi, type CompanionApi } from "../api"
import { CompanionStoreProvider, NoticeProvider } from "../store"
import ServerView from "../views/ServerView"

function setupServerView(overrides: Partial<ReturnType<any>> = {}) {
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
    serverId: "srv_stimi",
    serverName: "STIMI-Server",
    activeId: "srv_stimi",
    activeName: "STIMI-Server",
    activeHost: "192.168.10.50",
    sshUser: "",
    servers: [{ id: "srv_stimi", name: "STIMI-Server", active: true, sshUser: "" }],
    activeRoute: "r1",
    routes: [{ id: "r1", name: "LAN", url: "http://192.168.10.50:80", active: true, status: "online" }],
    activeProfile: "Admin",
    profiles: ["Admin"],
    credentials: { Admin: { username: "DesktopAdminName", hasPassword: true } },
    uptimeStr: "2d",
    isAdmin: true,
    ...overrides,
  })) as unknown as CompanionApi["getServerDetails"]

  api.openSshTerminal = vi.fn(async (params) => ({
    status: "ok",
    success: true,
    command: params?.port && params.port !== 22
      ? `ssh -p ${params.port} ${params.user}@${params.host}`
      : `ssh ${params?.user}@${params?.host}`,
    user: params?.user,
    host: params?.host,
    port: params?.port ?? 22,
    launched: true,
  }))

  setCompanionApi(api)
  const go = vi.fn()
  const rendered = render(
    <NoticeProvider>
      <CompanionStoreProvider>
        <ServerView go={go} />
      </CompanionStoreProvider>
    </NoticeProvider>,
  )
  return { api, go, ...rendered }
}

describe("ServerView SSH Terminal username prompt modal", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it("opens SSH modal instead of immediately running SSH, lets user override username & port, and remembers ssh user per server", async () => {
    const { api } = setupServerView()

    const sshBtn = await screen.findByText("Terminal SSH", {}, { timeout: 2500 })
    fireEvent.click(sshBtn)

    // Clicking button must NOT bypass the username modal
    expect(api.openSshTerminal).not.toHaveBeenCalled()

    const userInput = await screen.findByLabelText("Username SSH") as HTMLInputElement
    const hostInput = screen.getByLabelText("Host / IP SSH") as HTMLInputElement
    const portInput = screen.getByLabelText("Port SSH") as HTMLInputElement

    expect(userInput.value).toBe("DesktopAdminName")
    expect(hostInput.value).toBe("192.168.10.50")
    expect(portInput.value).toBe("22")

    // User changes SSH username to actual ZimaOS Linux username (not MyServer profile name) + custom port
    fireEvent.change(userInput, { target: { value: "algitha" } })
    fireEvent.change(portInput, { target: { value: "2222" } })

    expect(screen.getByTestId("ssh-command-preview")).toHaveTextContent("ssh -p 2222 algitha@192.168.10.50")

    const submitBtn = screen.getByRole("button", { name: "Buka Terminal SSH" })
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(api.openSshTerminal).toHaveBeenCalledWith({
        host: "192.168.10.50",
        user: "algitha",
        port: 2222,
        serverId: "srv_stimi",
        saveSshUser: true,
      })
    })

    expect(localStorage.getItem("myserver_ssh_user_srv_stimi")).toBe("algitha")
  })
})

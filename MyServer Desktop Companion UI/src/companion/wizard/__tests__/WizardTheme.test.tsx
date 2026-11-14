import React from "react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { createMockApi, setCompanionApi } from "../../api"
import { assets } from "../../assets"
import { WizardErrorBoundary, WizardShell } from "../WizardShell"

function renderShell(props: Partial<React.ComponentProps<typeof WizardShell>> = {}) {
  return render(
    <WizardShell
      theme="dark"
      stepNumber={1}
      onClose={() => {}}
      onToggleTheme={() => {}}
      {...props}
    >
      <div>body</div>
    </WizardShell>
  )
}

function bgOf(container: HTMLElement): string {
  const win = container.querySelector(".wizard-win") as HTMLElement
  return win.style.backgroundImage
}

describe("WizardShell theme + assets (D-06, WIZ-01)", () => {
  beforeEach(() => setCompanionApi(createMockApi()))
  afterEach(() => vi.restoreAllMocks())

  it("renders dark/light logo marks and flyout backgrounds, offline variants on error", () => {
    const dark = renderShell({ theme: "dark" })
    expect(dark.container.querySelector(`img[src="${assets.logoDarkMark}"]`)).toBeTruthy()
    expect(bgOf(dark.container)).toContain(assets.flyoutBgDark)
    dark.unmount()

    const darkErr = renderShell({ theme: "dark", isError: true })
    expect(bgOf(darkErr.container)).toContain(assets.flyoutBgDarkOffline)
    darkErr.unmount()

    const light = renderShell({ theme: "light" })
    expect(light.container.querySelector(`img[src="${assets.logoLightMark}"]`)).toBeTruthy()
    expect(bgOf(light.container)).toContain(assets.flyoutBgLight)
    light.unmount()

    const lightErr = renderShell({ theme: "light", isError: true })
    expect(bgOf(lightErr.container)).toContain(assets.flyoutBgLightOffline)
  })

  it("toggles .is-expanded for 540px sub-steps", () => {
    const a = renderShell({ isExpanded: true })
    expect(a.container.querySelector(".wizard-win")).toHaveClass("is-expanded")
    a.unmount()
    const b = renderShell({ isExpanded: false })
    expect(b.container.querySelector(".wizard-win")).not.toHaveClass("is-expanded")
  })

  it("invokes onClose from the × button and renders 5 stepper segments with active state", () => {
    const onClose = vi.fn()
    const { container } = renderShell({ stepNumber: 3, onClose, subStepLabel: "5a Syncthing" })
    fireEvent.click(screen.getByLabelText("Close Setup Wizard"))
    expect(onClose).toHaveBeenCalledTimes(1)
    const segs = container.querySelectorAll(".wiz-rail-seg")
    expect(segs).toHaveLength(5)
    expect(segs[2]).toHaveClass("is-active")
    expect(segs[0]).toHaveClass("is-done")
    expect(screen.getByText("5a Syncthing")).toBeInTheDocument()
  })

  it("WizardErrorBoundary catches child throws and offers a reset button", () => {
    vi.spyOn(console, "error").mockImplementation(() => {})
    let shouldThrow = true
    function Bomb() {
      if (shouldThrow) throw new Error("boom")
      return <div>recovered</div>
    }
    render(
      <WizardErrorBoundary>
        <Bomb />
      </WizardErrorBoundary>
    )
    expect(screen.getByRole("alert")).toBeInTheDocument()
    shouldThrow = false
    fireEvent.click(screen.getByRole("button"))
    expect(screen.getByText("recovered")).toBeInTheDocument()
  })
})

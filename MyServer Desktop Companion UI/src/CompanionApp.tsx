import { useEffect, useRef, useState } from "react"
import Companion from "./companion/Companion"
import { CompanionStoreProvider, NoticeProvider, useCompanion } from "./companion/store"
import type { ViewId } from "./companion/types"
import { SetupWizard } from "./companion/wizard/SetupWizard"

const VALID_VIEWS: ViewId[] = ["home", "files", "backup", "apps", "settings", "server", "power", "vm"]

function initialView(): ViewId {
  if (typeof window !== "undefined") {
    const p = new URLSearchParams(window.location.search).get("view") as ViewId
    if (p && VALID_VIEWS.includes(p)) return p
  }
  return "home"
}

/** Lives inside <CompanionStoreProvider> so useCompanion() is always legal here. */
function CompanionShellGate() {
  const { wizardOpen, wizardInitializing } = useCompanion()
  const [view, setView] = useState<ViewId>(initialView)
  const wizardOpenRef = useRef(wizardOpen)
  wizardOpenRef.current = wizardOpen

  useEffect(() => {
    // D-04 / T-03-09: tray reset and hide events must never unmount or bypass an active wizard.
    const handleResetHome = () => {
      if (wizardOpenRef.current) return
      setView("home")
    }
    const handleVisibility = () => {
      if (document.visibilityState === "hidden" && !wizardOpenRef.current) {
        setView("home")
      }
    }
    window.addEventListener("myserver:reset-home", handleResetHome)
    document.addEventListener("visibilitychange", handleVisibility)
    return () => {
      window.removeEventListener("myserver:reset-home", handleResetHome)
      document.removeEventListener("visibilitychange", handleVisibility)
    }
  }, [])

  if (wizardInitializing) {
    return <div className="wizard-boot-loading" data-testid="wizard-boot-loading" />
  }

  if (wizardOpen) {
    return (
      <NoticeProvider>
        <SetupWizard />
      </NoticeProvider>
    )
  }

  return (
    <div className="flex h-full w-full items-start justify-start p-0 select-none overflow-hidden bg-transparent">
      <Companion view={view} onViewChange={setView} />
    </div>
  )
}

export default function CompanionApp() {
  return (
    <CompanionStoreProvider>
      <CompanionShellGate />
    </CompanionStoreProvider>
  )
}

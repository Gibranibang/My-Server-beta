import { useEffect, useState } from "react"
import Companion from "./companion/Companion"
import { CompanionStoreProvider } from "./companion/store"
import type { ViewId } from "./companion/types"

export default function CompanionApp() {
  const [view, setView] = useState<ViewId>(() => {
    if (typeof window !== "undefined") {
      const p = new URLSearchParams(window.location.search).get("view") as ViewId
      if (p && ["home", "files", "backup", "apps", "settings", "server", "power"].includes(p)) {
        return p
      }
    }
    return "home"
  })

  useEffect(() => {
    const handleResetHome = () => setView("home")
    const handleVisibility = () => {
      if (document.visibilityState === "hidden") {
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

  return (
    <CompanionStoreProvider>
      <div className="flex h-full w-full items-start justify-start p-0 select-none overflow-hidden bg-transparent">
        <Companion view={view} onViewChange={setView} />
      </div>
    </CompanionStoreProvider>
  )
}

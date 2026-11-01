import { useEffect, useState } from "react"
import Companion from "./companion/Companion"
import { CompanionStoreProvider } from "./companion/store"
import type { ViewId } from "./companion/types"

export default function CompanionApp() {
  const [view, setView] = useState<ViewId>("home")

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
      <div className="flex h-full w-full items-center justify-center p-0 select-none overflow-hidden bg-transparent">
        <Companion view={view} onViewChange={setView} />
      </div>
    </CompanionStoreProvider>
  )
}

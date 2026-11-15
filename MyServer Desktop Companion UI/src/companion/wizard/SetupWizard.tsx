import { useCallback, useEffect, useRef, useState } from "react"
import { getCompanionApi } from "../api"
import { getTranslation } from "../i18n"
import { useCompanion, useNotice } from "../store"
import type { WizardDraft } from "../types"
import { StepBackend } from "./StepBackend"
import { StepConnection } from "./StepConnection"
import { StepFinishHub } from "./StepFinishHub"
import { StepWanDomain } from "./StepWanDomain"
import { StepZimaLogin } from "./StepZimaLogin"
import { SubStepSyncthing } from "./SubStepSyncthing"
import { SubStepVm } from "./SubStepVm"
import { WizardErrorBoundary, WizardShell, type WizardToast } from "./WizardShell"

export type WizardStep = 1 | 2 | 3 | 4 | 5 | "5a" | "5b"

export const WIZARD_WIDTH_BASE = 460
export const WIZARD_HEIGHT_BASE = 560
export const WIZARD_WIDTH_EXPANDED = 540
export const WIZARD_HEIGHT_EXPANDED = 620

/** Volatile draft — credentials live in memory only and are never written to browser storage (T-03-07). */
export function createInitialDraft(): WizardDraft {
  return {
    connectionMode: "lan",
    lanUrl: "",
    remoteId: "",
    connectionVerified: false,
    wanUrl: "",
    username: "",
    password: "",
    serverId: "srv_default",
    serverName: "",
    zerotierNetworkId: "",
    zerotierIp: "",
    step1And3Done: false,
    backendSource: "github",
    backendInstalled: false,
    backendVersion: "",
    syncthingDone: false,
    vmDone: false,
  }
}

function numericStep(step: WizardStep): 1 | 2 | 3 | 4 | 5 {
  return step === "5a" || step === "5b" ? 5 : step
}

export function SetupWizard({ onCompleted }: { onCompleted?: () => void }) {
  const { settings, setSetting, closeWizard, openedFromSettings } = useCompanion()
  const { notify } = useNotice()
  const api = getCompanionApi()
  const language = settings?.language === "id" ? "id" : "en"
  const theme = settings?.theme === "light" ? "light" : "dark"
  const t = getTranslation(language)

  const [step, setStep] = useState<WizardStep>(1)
  const [draft, setDraft] = useState<WizardDraft>(createInitialDraft)
  const [hasError, setHasError] = useState(false)
  const [toast, setToast] = useState<WizardToast>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const closingRef = useRef(false)
  const [boundaryKey, setBoundaryKey] = useState(0)

  const showToast = useCallback((text: string, tone: "info" | "success" | "error" | "warning" = "info") => {
    setToast({ text, tone })
    if (toastTimer.current) clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(null), 4000)
  }, [])

  useEffect(
    () => () => {
      if (toastTimer.current) clearTimeout(toastTimer.current)
    },
    []
  )

  const patchDraft = useCallback((patch: Partial<WizardDraft>) => {
    setDraft((prev) => ({ ...prev, ...patch }))
  }, [])

  // Settings re-entry: target the active configured server ID without prefilling existing config values.
  useEffect(() => {
    if (!openedFromSettings) return
    let cancelled = false
    void Promise.resolve()
      .then(() => api.getServerDetails())
      .then((details) => {
        if (cancelled || !details) return
        const patch: Partial<WizardDraft> = { step1And3Done: true }
        if (details.serverId) patch.serverId = details.serverId
        setDraft((prev) => ({ ...prev, ...patch }))
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [api, openedFromSettings])

  // D-06: 460x560 for steps 1..5, 540x620 for sub-steps 5a/5b.
  useEffect(() => {
    const expanded = step === "5a" || step === "5b"
    void Promise.resolve(
      api.setWizardMode(
        true,
        expanded ? WIZARD_WIDTH_EXPANDED : WIZARD_WIDTH_BASE,
        expanded ? WIZARD_HEIGHT_EXPANDED : WIZARD_HEIGHT_BASE
      )
    ).catch(() => undefined)
    setHasError(false)
  }, [api, step])

  const handleClose = useCallback(async () => {
    if (closingRef.current) return
    if (openedFromSettings) {
      closingRef.current = true
      try {
        await api.setWizardMode(false)
        closeWizard()
        await api.hideWindow()
      } finally {
        closingRef.current = false
      }
      return
    }
    if (!draft.step1And3Done) {
      showToast(t("wiz_close_guard", "Selesaikan koneksi & login dulu"), "warning")
      return
    }
    await api.hideWindow()
  }, [api, closeWizard, draft.step1And3Done, openedFromSettings, showToast, t])

  const completingRef = useRef(false)
  const handleComplete = useCallback(async () => {
    if (completingRef.current) return
    completingRef.current = true
    try {
      const result = await api.completeWizard()
      if (result && result.success === false) {
        throw new Error(result.error || result.message || "Setup belum selesai")
      }
      await api.setWizardMode(false)
      closeWizard(true)
      onCompleted?.()
    } finally {
      completingRef.current = false
    }
  }, [api, closeWizard, onCompleted])

  const onNotify = useCallback(
    (msg: string, type: "info" | "success" | "error" | "warning" = "info") => {
      showToast(msg, type)
      if (type === "error") notify(msg, "danger")
    },
    [notify, showToast]
  )

  const toggleTheme = useCallback(() => {
    void setSetting("theme", theme === "light" ? "dark" : "light").catch(() => undefined)
  }, [setSetting, theme])

  const common = { draft, onPatchDraft: patchDraft, language, onNotify, onErrorChange: setHasError } as const
  const subLabel = step === "5a" ? "5a Syncthing" : step === "5b" ? "5b Virtual Machine" : undefined

  let body: React.ReactNode
  switch (step) {
    case 1:
      body = <StepConnection {...common} onNext={() => setStep(2)} onBack={() => undefined} />
      break
    case 2:
      body = <StepWanDomain {...common} onNext={() => setStep(3)} onBack={() => setStep(1)} />
      break
    case 3:
      body = <StepZimaLogin {...common} onNext={() => setStep(4)} onBack={() => setStep(2)} />
      break
    case 4:
      body = <StepBackend {...common} onNext={() => setStep(5)} onBack={() => setStep(3)} />
      break
    case 5:
      body = (
        <StepFinishHub
          draft={draft}
          language={language}
          onOpenSubStep={(sub) => setStep(sub)}
          onComplete={handleComplete}
          onBack={() => setStep(4)}
          onNotify={onNotify}
          onErrorChange={setHasError}
        />
      )
      break
    case "5a":
      body = (
        <SubStepSyncthing
          {...common}
          onDoneSubStep={() => {
            patchDraft({ syncthingDone: true })
            setStep(5)
          }}
          onSkip={() => setStep(5)}
          onBack={() => setStep(5)}
        />
      )
      break
    default:
      body = (
        <SubStepVm
          {...common}
          onDoneSubStep={() => {
            patchDraft({ vmDone: true })
            setStep(5)
          }}
          onSkip={() => setStep(5)}
          onBack={() => setStep(5)}
        />
      )
  }

  return (
    <div className="wizard-root" data-testid="setup-wizard">
      <WizardShell
        theme={theme}
        language={language}
        stepNumber={numericStep(step)}
        isExpanded={step === "5a" || step === "5b"}
        isError={hasError}
        subStepLabel={subLabel}
        toast={toast}
        onClose={() => void handleClose()}
        onToggleTheme={toggleTheme}
      >
        <WizardErrorBoundary
          key={`${String(step)}-${boundaryKey}`}
          language={language}
          onReset={() => setBoundaryKey((k) => k + 1)}
        >
          {body}
        </WizardErrorBoundary>
      </WizardShell>
    </div>
  )
}

export default SetupWizard

import React, { Component, type ErrorInfo, type ReactNode } from "react"
import { Moon, Sun, X } from "lucide-react"
import { getCompanionApi } from "../api"
import { assets } from "../assets"
import { getTranslation, type Language } from "../i18n"

export type WizardToast = { text: string; tone?: "info" | "success" | "error" | "warning" } | null

export interface WizardShellProps {
  theme: "dark" | "light"
  stepNumber: 1 | 2 | 3 | 4 | 5
  isExpanded?: boolean
  isError?: boolean
  subStepLabel?: string
  toast?: WizardToast
  language?: Language
  onClose: () => void
  onToggleTheme: () => void
  children?: ReactNode
}

function backdropFor(theme: "dark" | "light", isError: boolean): string {
  if (theme === "light") return isError ? assets.flyoutBgLightOffline : assets.flyoutBgLight
  return isError ? assets.flyoutBgDarkOffline : assets.flyoutBgDark
}

export function WizardShell({
  theme,
  stepNumber,
  isExpanded = false,
  isError = false,
  subStepLabel,
  toast,
  language = "en",
  onClose,
  onToggleTheme,
  children,
}: WizardShellProps) {
  const t = getTranslation(language)

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    const target = e.target as HTMLElement
    if (target.closest("button, input, select, textarea, a")) return
    void getCompanionApi().startDrag().catch(() => undefined)
  }

  const classes = ["wizard-win", isExpanded ? "is-expanded" : "", isError ? "is-error" : ""]
    .filter(Boolean)
    .join(" ")

  return (
    <div
      className={classes}
      data-theme={theme}
      data-testid="wizard-window"
      style={{ backgroundImage: `url("${backdropFor(theme, isError)}")` }}
    >
      <div className="wiz-header" onMouseDown={handleMouseDown} data-testid="wizard-drag-bar">
        <img
          className="wiz-logo"
          alt="MyServer"
          src={theme === "light" ? assets.logoLightMark : assets.logoDarkMark}
          draggable={false}
        />
        <div className="wiz-header-right">
          <span className="wiz-step-count">
            {t("wiz_step_pill", "Step")} {stepNumber}/5
          </span>
          <button
            type="button"
            className="wiz-icon-btn"
            aria-label={t("wiz_theme_toggle", "Toggle theme")}
            onClick={onToggleTheme}
          >
            {theme === "light" ? <Moon size={14} /> : <Sun size={14} />}
          </button>
          <button
            type="button"
            className="wiz-icon-btn wiz-close"
            aria-label={t("wiz_close_label", "Close Setup Wizard")}
            onClick={onClose}
          >
            <X size={14} />
          </button>
        </div>
      </div>

      <div className="wiz-step-rail" role="progressbar" aria-valuemin={1} aria-valuemax={5} aria-valuenow={stepNumber}>
        {[1, 2, 3, 4, 5].map((n) => (
          <span
            key={n}
            className={`wiz-rail-seg${n < stepNumber ? " is-done" : ""}${n === stepNumber ? " is-active" : ""}`}
          />
        ))}
      </div>

      {subStepLabel ? <span className="wiz-sub-badge">{subStepLabel}</span> : null}

      {toast ? (
        <div
          className={`wiz-toast${toast.tone === "error" ? " is-error" : toast.tone === "success" ? " is-success" : ""}`}
          role="status"
        >
          {toast.text}
        </div>
      ) : null}

      <div className="wiz-body">{children}</div>
    </div>
  )
}

interface BoundaryProps {
  children: ReactNode
  language?: Language
  onReset?: () => void
}

export class WizardErrorBoundary extends Component<BoundaryProps, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[wizard] step render failed", error, info.componentStack)
  }

  private reset = () => {
    this.props.onReset?.()
    this.setState({ failed: false })
  }

  render() {
    if (!this.state.failed) return this.props.children
    const id = this.props.language === "id"
    return (
      <div className="wiz-banner wiz-banner-error" role="alert">
        <p style={{ margin: "0 0 8px" }}>
          {id ? "Langkah ini gagal ditampilkan." : "This step failed to render."}
        </p>
        <button type="button" className="wiz-btn wiz-btn-secondary wiz-btn-sm" onClick={this.reset}>
          {id ? "Coba lagi" : "Try again"}
        </button>
      </div>
    )
  }
}

export default WizardShell

import { Component, type ErrorInfo, type ReactNode } from "react"
import { AlertTriangle, CircleCheck, Info, RefreshCw, TriangleAlert } from "lucide-react"
import { assets } from "./assets"
import { useCompanion, useNotice, usePowerStatus } from "./store"
import { StatusDot, cx } from "./ui"
import type { Tone } from "./types"

/** Engineering graph-paper texture from the Figma reference, fading in toward the footer module. */
function GridTexture() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
      <div className="absolute inset-x-0 bottom-0 h-3/5 bg-linear-to-b from-surface to-surface-sunken" />
      <div className="absolute top-[calc(100%-265px)] left-1/2 size-[642px] -translate-x-1/2 overflow-hidden opacity-45">
        <div className="absolute inset-[-3.9%_0]">
          <img
            alt=""
            src={assets.gridHorizontal}
            className="absolute inset-0 block size-full max-w-none"
          />
        </div>
        <div className="absolute top-[-64.5px] left-[-2.2px] h-[768.73px] w-[642.227px] rotate-[-89.9deg]">
          <img
            alt=""
            src={assets.gridVertical}
            className="absolute inset-0 block size-full max-w-none"
          />
        </div>
        <div className="absolute top-0 right-[-0.31%] bottom-1/2 left-[-2.34%]">
          <img
            alt=""
            src={assets.gridFade}
            className="absolute inset-0 size-full max-w-none object-cover"
          />
        </div>
      </div>
    </div>
  )
}

function TopGlow() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute top-[-41px] left-[53px] -z-10 size-[82px]"
    >
      <div className="absolute inset-[-256%]">
        <img
          alt=""
          src={assets.topGlow}
          className="block size-full max-w-none"
        />
      </div>
    </div>
  )
}

const TOAST_ICON_TONES: Record<Tone, string> = {
  success: "text-success-bright",
  info: "text-info-line",
  neutral: "text-info-line",
  warning: "text-warning",
  danger: "text-danger-bright",
}

function Toast() {
  const { notice } = useNotice()
  const Icon = !notice
    ? Info
    : notice.tone === "success"
      ? CircleCheck
      : notice.tone === "warning" || notice.tone === "danger"
        ? TriangleAlert
        : Info
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none absolute bottom-28 left-1/2 z-20 w-max max-w-[calc(100%-32px)] -translate-x-1/2"
    >
      {notice && (
        <div
          key={notice.id}
          className="flex items-center gap-2 rounded-full bg-ink/95 py-1.5 pr-3.5 pl-2.5 text-caption font-medium text-white shadow-toast backdrop-blur motion-safe:animate-toast-in"
        >
          <Icon
            className={cx("size-3.5 shrink-0", TOAST_ICON_TONES[notice.tone])}
            strokeWidth={2.4}
            aria-hidden
          />
          <span className="truncate">{notice.text}</span>
        </div>
      )}
    </div>
  )
}

function TransitionOverlay() {
  const { transitionState } = useCompanion()
  if (!transitionState?.active) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-surface/85 backdrop-blur-xs motion-safe:animate-fade-in"
    >
      <div className="flex flex-col items-center gap-3 p-6 text-center">
        <div className="relative flex items-center justify-center">
          <span className="absolute size-12 rounded-full bg-brand/20 animate-ping" />
          <span className="inline-flex size-10 items-center justify-center rounded-full bg-brand/10 text-brand shadow-inner">
            <RefreshCw className="size-5 animate-spin" />
          </span>
        </div>
        <div>
          <h4 className="text-body font-bold text-ink">{transitionState.title}</h4>
          {transitionState.message && (
            <p className="mt-1 text-micro text-ink-subtle">{transitionState.message}</p>
          )}
        </div>
      </div>
    </div>
  )
}

export function FlyoutHeader({
  leading,
  trailing,
}: {
  leading: ReactNode
  trailing: ReactNode
}) {
  return (
    <header className="flex h-13 shrink-0 items-center justify-between gap-2 px-3 pt-3">
      <div className="flex min-w-0 flex-1 items-center gap-2">{leading}</div>
      <div className="flex shrink-0 items-center gap-0.5">{trailing}</div>
    </header>
  )
}

export function HeaderTitle({
  title,
  subtitle,
}: {
  title: string
  subtitle: string
}) {
  return (
    <div className="min-w-0">
      <h2 className="truncate text-heading font-bold tracking-[-0.01em] text-ink">
        {title}
      </h2>
      <p className="truncate text-micro font-medium text-ink-subtle">
        {subtitle}
      </p>
    </div>
  )
}

/** Small green glow that sits behind the first footer chip, as in the Figma status card. */
export function ChipGlow() {
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute top-3 -left-1 -z-10 size-[25px]"
    >
      <span className="absolute inset-[-256%]">
        <img
          alt=""
          src={assets.chipGlow}
          className="block size-full max-w-none"
        />
      </span>
    </span>
  )
}

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ViewErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  public state: ErrorBoundaryState = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ViewErrorBoundary] Uncaught UI render error:", error, errorInfo)
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
          <div className="mb-3 flex size-12 items-center justify-center rounded-full bg-danger/10 text-danger-bright">
            <AlertTriangle className="size-6" />
          </div>
          <h3 className="text-body font-bold text-ink">Tampilan Gagal Dimuat</h3>
          <p className="mt-1 text-micro text-ink-subtle max-w-xs">
            {this.state.error?.message || "Terjadi kesalahan saat merender halaman."}
          </p>
          <button
            type="button"
            onClick={() => {
              this.setState({ hasError: false, error: null })
              window.dispatchEvent(new CustomEvent("myserver:reset-home"))
            }}
            className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface-sunken px-3 py-1.5 text-caption font-semibold text-ink hover:border-line-strong transition-colors cursor-pointer"
          >
            <RefreshCw className="size-3.5" />
            Muat Ulang Halaman
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

/** Technical status card sitting over the graph-paper texture at the base of every flyout view. */
export function FooterStatus({
  title,
  chips,
  onClick,
}: {
  title: ReactNode
  chips: ReactNode
  onClick?: () => void
}) {
  const status = usePowerStatus()
  const { transitionState } = useCompanion()
  const isTransitioning = Boolean(transitionState?.active)

  return (
    <footer className="relative shrink-0 px-3 pt-1 pb-3">
      <div
        role={onClick && !isTransitioning ? "button" : undefined}
        tabIndex={onClick && !isTransitioning ? 0 : undefined}
        onClick={isTransitioning ? undefined : onClick}
        onKeyDown={onClick && !isTransitioning ? (e) => (e.key === "Enter" || e.key === " " ? onClick() : undefined) : undefined}
        className={cx(
          "relative overflow-hidden rounded-card border border-line bg-surface p-3.5 shadow-footer outline-none",
          onClick && !isTransitioning && "cursor-pointer transition-[border-color,box-shadow,transform] duration-150 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-card-hover focus-visible:ring-2 focus-visible:ring-info/45 active:translate-y-0",
        )}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute top-2 right-10 size-[50px]"
        >
          <div className="absolute inset-[-256%]">
            <img
              alt=""
              src={assets.statusGlow}
              className="block size-full max-w-none"
            />
          </div>
        </div>
        <div className="relative flex items-center justify-between gap-3">
          {isTransitioning ? (
            <div className="h-5 w-32 rounded bg-surface-sunken animate-pulse" />
          ) : (
            <h3 className="min-w-0 truncate text-heading font-bold text-ink">
              {title}
            </h3>
          )}
          {isTransitioning ? (
            <span className="inline-flex h-4 w-16 rounded-full bg-surface-sunken animate-pulse" />
          ) : (
            <span className="inline-flex shrink-0 items-center gap-1.5 text-micro font-semibold text-ink-subtle">
              <StatusDot tone={status.tone} />
              {status.label}
            </span>
          )}
        </div>
        <div className="relative mt-2.5 flex flex-wrap items-center gap-1.5">
          {isTransitioning ? (
            <>
              <span className="inline-block h-6 w-16 rounded-full bg-surface-sunken animate-pulse" />
              <span className="inline-block h-6 w-20 rounded-full bg-surface-sunken animate-pulse" />
            </>
          ) : (
            chips
          )}
        </div>
      </div>
    </footer>
  )
}

export default function FlyoutShell({
  header,
  children,
}: {
  header: ReactNode
  children: ReactNode
}) {
  return (
    <section
      aria-label="MyServer flyout"
      className="relative isolate flex h-companion w-flyout shrink-0 flex-col overflow-hidden rounded-2xl border border-line bg-surface motion-safe:animate-flyout-in"
    >
      <GridTexture />
      <TopGlow />
      {header}
      <ViewErrorBoundary>{children}</ViewErrorBoundary>
      <Toast />
      <TransitionOverlay />
    </section>
  )
}

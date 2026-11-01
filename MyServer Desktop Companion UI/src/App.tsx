import { APP_VERSION } from "./companion/version"
import { useState, type ReactNode } from "react"
import {
  LayoutGrid,
  Maximize2,
  MousePointerClick,
  RotateCcw,
  Server,
  type LucideIcon,
} from "lucide-react"
import Companion from "./companion/Companion"
import { FRAMES } from "./companion/frames"
import {
  CompanionStoreProvider,
  SERVER_IP,
  useCompanion,
  usePowerStatus,
} from "./companion/store"
import { Mono, StatusDot, cx } from "./companion/ui"
import type { ViewId } from "./companion/types"

type Mode = "board" | "prototype"

const canvasFocus =
  "outline-none focus-visible:ring-2 focus-visible:ring-info-line/60 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"

function CanvasButton({
  icon: Icon,
  children,
  onClick,
}: {
  icon: LucideIcon
  children: ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "inline-flex h-7 items-center gap-1.5 rounded-full border border-canvas-line bg-canvas-raised/60 px-2.5 text-caption font-semibold text-canvas-muted transition-colors duration-150 hover:border-canvas-muted/40 hover:text-canvas-ink",
        canvasFocus,
      )}
    >
      <Icon className="size-3.5" strokeWidth={2.2} aria-hidden />
      {children}
    </button>
  )
}

interface ModeOption {
  id: Mode
  label: string
  icon: LucideIcon
}

function ModeSwitch({
  mode,
  onChange,
}: {
  mode: Mode
  onChange: (mode: Mode) => void
}) {
  const options: ModeOption[] = [
    { id: "board", label: "All Frames", icon: LayoutGrid },
    { id: "prototype", label: "Prototype", icon: MousePointerClick },
  ]
  return (
    <div
      role="group"
      aria-label="Presentation mode"
      className="inline-flex rounded-full border border-canvas-line bg-canvas-raised/60 p-1 shadow-canvas-pill"
    >
      {options.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          type="button"
          aria-pressed={mode === id}
          onClick={() => onChange(id)}
          className={cx(
            "inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 text-label font-semibold transition-[background-color,color,box-shadow] duration-200",
            canvasFocus,
            mode === id
              ? "bg-surface text-ink shadow-control"
              : "text-canvas-muted hover:text-canvas-ink",
          )}
        >
          <Icon className="size-3.5" strokeWidth={2.2} aria-hidden />
          {label}
        </button>
      ))}
    </div>
  )
}

function LiveStatus() {
  const { metrics, isOnline } = useCompanion()
  const status = usePowerStatus()
  return (
    <div className="inline-flex h-10 items-center gap-2.5 rounded-full border border-canvas-line bg-canvas-raised/60 px-3.5 text-caption font-medium text-canvas-muted">
      <StatusDot tone={status.tone} />
      <span className="font-semibold text-canvas-ink">
        Server {status.label}
      </span>
      <span className="h-3 w-px bg-canvas-line" aria-hidden />
      <Mono>{SERVER_IP}</Mono>
      <span className="hidden sm:inline">
        CPU{" "}
        <Mono className="text-canvas-ink">
          {isOnline ? `${metrics.cpu}%` : "–"}
        </Mono>
      </span>
    </div>
  )
}

function TopBar({
  mode,
  onModeChange,
}: {
  mode: Mode
  onModeChange: (mode: Mode) => void
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-4">
      <div className="flex items-center gap-3.5">
        <span className="inline-flex size-11 items-center justify-center rounded-tile border border-canvas-line bg-canvas-raised text-brand shadow-canvas-pill">
          <Server className="size-5" strokeWidth={2.2} aria-hidden />
        </span>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-heading font-bold text-canvas-ink">
              MyServer Tray Companion
            </h1>
            <span className="inline-flex h-5 items-center rounded-full border border-info/40 bg-info/15 px-2 text-nano font-bold tracking-wide text-info-line uppercase">
              Beta Channel
            </span>
            <Mono className="text-caption text-canvas-faint">v{APP_VERSION}</Mono>
          </div>
          <p className="mt-0.5 text-label text-canvas-muted">
            Desktop flyout system for ZimaOS &amp; private homelab servers. Six
            frames share one live server state.
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <LiveStatus />
        <ModeSwitch mode={mode} onChange={onModeChange} />
      </div>
    </header>
  )
}

function Board({ onOpen }: { onOpen: (view: ViewId) => void }) {
  const [views, setViews] = useState<ViewId[]>(() =>
    FRAMES.map((frame) => frame.view),
  )
  const [resets, setResets] = useState<number[]>(() => FRAMES.map(() => 0))

  const setView = (index: number, view: ViewId) =>
    setViews((list) => list.map((v, i) => (i === index ? view : v)))
  const reset = (index: number) => {
    setView(index, FRAMES[index].view)
    setResets((list) => list.map((n, i) => (i === index ? n + 1 : n)))
  }

  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(min(var(--spacing-companion-w),100%),1fr))] justify-items-center gap-x-10 gap-y-14">
      {FRAMES.map((frame, index) => {
        const drifted = views[index] !== frame.view
        return (
          <figure
            key={frame.view}
            className="flex w-full max-w-companion-w flex-col gap-4"
          >
            <figcaption className="flex items-end justify-between gap-3">
              <div className="min-w-0">
                <div className="font-mono text-micro font-semibold tracking-[0.16em] text-canvas-faint uppercase">
                  Frame {frame.index}
                </div>
                <div className="truncate text-body font-semibold text-canvas-ink">
                  {frame.name}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                {drifted && (
                  <CanvasButton icon={RotateCcw} onClick={() => reset(index)}>
                    Reset
                  </CanvasButton>
                )}
                <CanvasButton
                  icon={Maximize2}
                  onClick={() => onOpen(frame.view)}
                >
                  Focus
                </CanvasButton>
              </div>
            </figcaption>
            <Companion
              key={resets[index]}
              view={views[index]}
              onViewChange={(view) => setView(index, view)}
            />
          </figure>
        )
      })}
    </div>
  )
}

function Prototype({
  view,
  onViewChange,
}: {
  view: ViewId
  onViewChange: (view: ViewId) => void
}) {
  const frame = FRAMES.find((f) => f.view === view) ?? FRAMES[0]
  return (
    <div className="flex flex-col items-center gap-7">
      <nav
        aria-label="Frames"
        className="flex max-w-full gap-1 overflow-x-auto scrollbar-none rounded-full border border-canvas-line bg-canvas-raised/60 p-1"
      >
        {FRAMES.map((f) => (
          <button
            key={f.view}
            type="button"
            aria-current={f.view === view ? "page" : undefined}
            onClick={() => onViewChange(f.view)}
            className={cx(
              "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3 text-label font-semibold transition-colors duration-200",
              canvasFocus,
              f.view === view
                ? "bg-surface text-ink shadow-control"
                : "text-canvas-muted hover:text-canvas-ink",
            )}
          >
            <Mono
              className={
                f.view === view ? "text-ink-faint" : "text-canvas-faint"
              }
            >
              {f.index}
            </Mono>
            {f.short}
          </button>
        ))}
      </nav>
      <Companion view={view} onViewChange={onViewChange} />
      <p className="max-w-md text-center text-label text-canvas-muted">
        <span className="font-semibold text-canvas-ink">
          Frame {frame.index} · {frame.name}.
        </span>{" "}
        {frame.hint}
      </p>
    </div>
  )
}

export default function App() {
  const [mode, setMode] = useState<Mode>("board")
  const [prototypeView, setPrototypeView] = useState<ViewId>("home")

  const openPrototype = (view: ViewId) => {
    setPrototypeView(view)
    setMode("prototype")
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  return (
    <CompanionStoreProvider>
      <div className="relative isolate min-h-dvh overflow-x-hidden canvas-backdrop">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-10 canvas-grid"
        />
        <main className="mx-auto flex max-w-board flex-col gap-10 px-4 py-6 sm:px-8 sm:py-8">
          <TopBar mode={mode} onModeChange={setMode} />
          {mode === "board" ? (
            <Board onOpen={openPrototype} />
          ) : (
            <Prototype view={prototypeView} onViewChange={setPrototypeView} />
          )}
        </main>
      </div>
    </CompanionStoreProvider>
  )
}

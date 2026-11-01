import { useState, type ButtonHTMLAttributes, type ReactNode } from "react"
import { Check, ChevronDown, LoaderCircle, type LucideIcon } from "lucide-react"
import type { Tone } from "./types"

export const cx = (...classes: Array<string | false | null | undefined>) =>
  classes.filter(Boolean).join(" ")

const focusRing =
  "outline-none focus-visible:ring-2 focus-visible:ring-info/45 focus-visible:ring-offset-2 focus-visible:ring-offset-surface"

/* ------------------------------------------------------------------ */
/* Icon button (window controls, back navigation)                      */
/* ------------------------------------------------------------------ */

export function IconButton({
  icon: Icon,
  label,
  onClick,
  className,
}: {
  icon: LucideIcon
  label: string
  onClick?: () => void
  className?: string
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cx(
        "inline-flex size-7 items-center justify-center rounded-full text-ink-muted transition-colors duration-150 hover:bg-surface-muted hover:text-ink active:bg-line",
        focusRing,
        className,
      )}
    >
      <Icon className="size-4" strokeWidth={2} aria-hidden />
    </button>
  )
}

/* ------------------------------------------------------------------ */
/* Button                                                              */
/* ------------------------------------------------------------------ */

type ButtonVariant = "primary" | "danger" | "secondary" | "soft" | "info"

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-linear-to-b from-success-bright to-success text-white shadow-success hover:from-success hover:to-success-strong",
  danger:
    "bg-linear-to-b from-danger-bright to-danger text-white shadow-danger hover:from-danger hover:to-danger-strong",
  secondary:
    "border border-line bg-surface text-ink shadow-control hover:border-line-strong hover:bg-surface-sunken",
  soft: "bg-surface-muted text-ink-soft hover:bg-line",
  info: "border border-info-line/70 bg-info-soft text-info-ink hover:border-info-line hover:bg-info-line/40",
}

const BUTTON_SIZES = {
  md: "h-9.5 gap-2 rounded-control px-4 text-label",
  sm: "h-7 gap-1.5 rounded-full px-3 text-caption",
} as const

export function Button({
  variant = "secondary",
  size = "md",
  icon: Icon,
  state = "idle",
  busyLabel,
  doneLabel,
  block,
  className,
  children,
  ...rest
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  variant?: ButtonVariant
  size?: keyof typeof BUTTON_SIZES
  icon?: LucideIcon
  state?: "idle" | "busy" | "done"
  busyLabel?: string
  doneLabel?: string
  block?: boolean
  children: ReactNode
}) {
  const iconClass = size === "md" ? "size-4" : "size-3.5"
  const StateIcon =
    state === "busy" ? LoaderCircle : state === "done" ? Check : Icon
  return (
    <button
      type="button"
      aria-busy={state === "busy" || undefined}
      className={cx(
        "relative inline-flex shrink-0 select-none items-center justify-center font-semibold whitespace-nowrap transition-[background-color,border-color,box-shadow,color,transform] duration-150 active:translate-y-px disabled:pointer-events-none disabled:opacity-45",
        focusRing,
        BUTTON_SIZES[size],
        BUTTON_VARIANTS[variant],
        block && "w-full",
        className,
      )}
      {...rest}
    >
      {StateIcon && (
        <StateIcon
          className={cx(iconClass, state === "busy" && "animate-spin")}
          strokeWidth={2.2}
          aria-hidden
        />
      )}
      <span>
        {state === "busy" && busyLabel
          ? busyLabel
          : state === "done" && doneLabel
            ? doneLabel
            : children}
      </span>
    </button>
  )
}

/* ------------------------------------------------------------------ */
/* Chip / badge                                                        */
/* ------------------------------------------------------------------ */

const CHIP_TONES: Record<Tone, string> = {
  success: "border-success-line/70 bg-success-soft text-success-ink",
  neutral: "border-transparent bg-surface-muted text-ink-muted",
  info: "border-info-line/70 bg-info-soft text-info-ink",
  warning: "border-warning-line/80 bg-warning-soft text-warning-ink",
  danger: "border-danger-line/80 bg-danger-soft text-danger-ink",
}

const CHIP_HOVER: Record<Tone, string> = {
  success: "hover:border-success-line",
  neutral: "hover:bg-line",
  info: "hover:border-info-line",
  warning: "hover:border-warning-line",
  danger: "hover:border-danger-line",
}

export function Chip({
  tone = "neutral",
  icon: Icon,
  children,
  onClick,
  label,
  size = "md",
  className,
  leading,
}: {
  tone?: Tone
  icon?: LucideIcon
  children: ReactNode
  onClick?: () => void
  label?: string
  size?: "md" | "sm"
  className?: string
  leading?: ReactNode
}) {
  const classes = cx(
    "relative isolate inline-flex shrink-0 items-center overflow-hidden rounded-full border font-semibold whitespace-nowrap",
    size === "md"
      ? "h-6 gap-1 px-2 text-micro"
      : "h-5 gap-1 px-1.5 text-nano tracking-wide",
    CHIP_TONES[tone],
    className,
  )
  const content = (
    <>
      {leading}
      {Icon && (
        <Icon
          className={size === "md" ? "size-3" : "size-2.5"}
          strokeWidth={2.4}
          aria-hidden
        />
      )}
      {children}
    </>
  )
  if (onClick) {
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          onClick()
        }}
        aria-label={label}
        className={cx(
          classes,
          CHIP_HOVER[tone],
          "transition-colors duration-150 active:translate-y-px",
          focusRing,
        )}
      >
        {content}
      </button>
    )
  }
  return <span className={classes}>{content}</span>
}

/* ------------------------------------------------------------------ */
/* Status dot                                                          */
/* ------------------------------------------------------------------ */

const DOT_TONES: Record<Tone, string> = {
  success: "bg-success",
  neutral: "bg-ink-faint",
  info: "bg-info",
  warning: "bg-warning",
  danger: "bg-danger",
}

export function StatusDot({
  tone = "success",
  pulse = true,
  className,
}: {
  tone?: Tone
  pulse?: boolean
  className?: string
}) {
  return (
    <span
      className={cx("relative inline-flex size-2 shrink-0", className)}
      aria-hidden
    >
      {pulse && tone !== "neutral" && (
        <span
          className={cx(
            "absolute inset-0 rounded-full motion-safe:animate-halo",
            DOT_TONES[tone],
          )}
        />
      )}
      <span className={cx("relative size-2 rounded-full", DOT_TONES[tone])} />
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* Toggle switch (iOS style)                                           */
/* ------------------------------------------------------------------ */

export function Toggle({
  checked,
  onChange,
  label,
  id,
  disabled,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  label: string
  id?: string
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        "inline-flex h-5.5 w-9 shrink-0 items-center rounded-full p-0.5 shadow-track transition-colors duration-200 disabled:opacity-45",
        focusRing,
        checked ? "bg-success" : "bg-line-strong",
      )}
    >
      <span
        className={cx(
          "size-4.5 rounded-full bg-white shadow-knob transition-transform duration-200 ease-glide",
          checked && "translate-x-3.5",
        )}
      />
    </button>
  )
}

/* ------------------------------------------------------------------ */
/* Progress bar                                                        */
/* ------------------------------------------------------------------ */

const BAR_TONES: Record<Tone, string> = {
  success: "from-success-bright to-success",
  neutral: "from-line-strong to-ink-faint",
  info: "from-info/70 to-info",
  warning: "from-warning/70 to-warning",
  danger: "from-danger-bright to-danger",
}

export function ProgressBar({
  value,
  tone = "success",
  label,
}: {
  value: number
  tone?: Tone
  label: string
}) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
      className="h-1.5 w-full overflow-hidden rounded-full bg-surface-muted shadow-track"
    >
      <div
        className={cx(
          "h-full rounded-full bg-linear-to-r transition-[width] duration-500 ease-glide",
          BAR_TONES[tone],
        )}
        style={{ width: `${value}%` }}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Surfaces + text helpers                                             */
/* ------------------------------------------------------------------ */

export function Card({
  className,
  children,
  onClick,
  role,
}: {
  className?: string
  children: ReactNode
  onClick?: () => void
  role?: string
}) {
  return (
    <div
      onClick={onClick}
      role={role}
      className={cx(
        "rounded-card border border-line bg-surface shadow-card",
        className,
      )}
    >
      {children}
    </div>
  )
}

/** Stroke-only icon in a dark slate tone; the optional tone prop is accepted for call-site compatibility but no longer colors the icon. */
export function IconBadge({
  icon: Icon,
  size = "md",
}: {
  icon: LucideIcon
  tone?: string
  size?: "md" | "sm"
}) {
  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center justify-center text-ink-soft",
        size === "md" ? "size-8" : "size-6.5",
      )}
      aria-hidden
    >
      <Icon
        className={size === "md" ? "size-5" : "size-4.5"}
        strokeWidth={1.75}
        fill="none"
      />
    </span>
  )
}

export function SectionLabel({
  children,
  trailing,
}: {
  children: ReactNode
  trailing?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between px-1">
      <span className="text-nano font-bold tracking-[0.12em] text-ink-subtle uppercase">
        {children}
      </span>
      {trailing && (
        <span className="text-micro font-medium text-ink-faint">
          {trailing}
        </span>
      )}
    </div>
  )
}

/** Monospace run for network identifiers (IPs, ports, MAC addresses, sizes). */
export function Mono({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <span className={cx("font-mono font-medium tracking-[-0.03em]", className)}>
      {children}
    </span>
  )
}

export function TextAction({
  icon: Icon,
  children,
  onClick,
  tone = "info",
  trailing,
  disabled,
}: {
  icon?: LucideIcon
  children: ReactNode
  onClick?: () => void
  tone?: "info" | "success" | "neutral"
  trailing?: ReactNode
  disabled?: boolean
}) {
  const toneClass = {
    info: "text-info hover:text-info-ink",
    success: "text-success-strong hover:text-success-ink",
    neutral: "text-ink-muted hover:text-ink",
  }[tone]
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "inline-flex items-center gap-1 rounded-full text-caption font-semibold transition-colors duration-150 disabled:opacity-45",
        focusRing,
        toneClass,
      )}
    >
      {Icon && <Icon className="size-3.5" strokeWidth={2.3} aria-hidden />}
      <span>{children}</span>
      {trailing}
    </button>
  )
}


/* ------------------------------------------------------------------ */
/* Accordion Section (Collapsible Server-Rack Panel)                 */
/* ------------------------------------------------------------------ */

export function AccordionSection({
  title,
  subtitle,
  icon: Icon,
  badge,
  defaultOpen = false,
  isOpen: controlledIsOpen,
  onToggle,
  children,
  className,
}: {
  title: string
  subtitle?: string
  icon?: LucideIcon
  badge?: ReactNode
  defaultOpen?: boolean
  isOpen?: boolean
  onToggle?: () => void
  children: ReactNode
  className?: string
}) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen)
  const isExpanded = controlledIsOpen !== undefined ? controlledIsOpen : uncontrolledOpen
  const handleToggle = () => {
    if (onToggle) onToggle()
    else setUncontrolledOpen(!uncontrolledOpen)
  }

  return (
    <div
      className={cx(
        "overflow-hidden rounded-card border border-line bg-surface shadow-card transition-all duration-200",
        className,
      )}
    >
      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={isExpanded}
        className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left transition-colors duration-150 hover:bg-surface-sunken cursor-pointer"
      >
        <div className="flex min-w-0 items-center gap-2.5">
          {Icon && (
            <span className="flex size-7 shrink-0 items-center justify-center rounded-tile border border-line bg-surface-muted text-ink-subtle">
              <Icon className="size-4" strokeWidth={2} />
            </span>
          )}
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-label font-semibold text-ink">
              {title}
            </span>
            {subtitle && (
              <span className="truncate text-micro text-ink-muted">
                {subtitle}
              </span>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {badge}
          <ChevronDown
            className={cx(
              "size-4 text-ink-subtle transition-transform duration-200",
              isExpanded && "rotate-180 text-brand",
            )}
            strokeWidth={2.2}
          />
        </div>
      </button>

      {isExpanded && (
        <div className="border-t border-line/60 bg-surface/50 p-3">
          {children}
        </div>
      )}
    </div>
  )
}

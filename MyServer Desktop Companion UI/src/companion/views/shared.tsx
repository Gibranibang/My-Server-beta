import type { ReactNode } from "react"
import { Check, LoaderCircle, type LucideIcon } from "lucide-react"
import { IconBadge, cx } from "../ui"
import type { ViewId } from "../types"

export interface ViewProps {
  go: (view: ViewId) => void
}

/** Scrollable content region between the flyout header and the pinned footer status card. */
export function ViewBody({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto scroll-fade scrollbar-slim px-4 pt-1.5 pb-3">
      <div className="flex flex-col gap-2.5">{children}</div>
    </div>
  )
}

type BadgeTone = NonNullable<Parameters<typeof IconBadge>[0]["tone"]>

export const tileSurface =
  "rounded-tile border border-line bg-linear-to-b from-surface to-surface-sunken shadow-tile"

export const tileInteraction =
  "transition-[border-color,box-shadow,translate] duration-150 outline-none hover:-translate-y-px hover:border-line-strong hover:shadow-card-hover focus-visible:ring-2 focus-visible:ring-info/45 focus-visible:ring-offset-2 active:translate-y-0 disabled:pointer-events-none disabled:opacity-50"

/** Compact launch tile: icon badge, title and an optional action caption. */
export function LaunchTile({
  icon,
  tone,
  title,
  caption,
  state = "idle",
  onClick,
  disabled,
}: {
  icon: LucideIcon
  tone: BadgeTone
  title: string
  caption?: string
  state?: "idle" | "busy" | "done"
  onClick: () => void
  disabled?: boolean
}) {
  const Icon = state === "busy" ? LoaderCircle : state === "done" ? Check : icon
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-busy={state === "busy" || undefined}
      className={cx(
        "flex min-w-0 items-center gap-2 p-2.5 text-left",
        tileSurface,
        tileInteraction,
      )}
    >
      <span
        className={cx("contents", state === "busy" && "[&_svg]:animate-spin")}
      >
        <IconBadge
          icon={Icon}
          tone={state === "done" ? "success" : tone}
          size="sm"
        />
      </span>
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 text-label font-semibold text-ink">
          {title}
        </span>
        {caption && (
          <span className="block truncate text-micro font-semibold text-info">
            {caption}
          </span>
        )}
      </span>
    </button>
  )
}

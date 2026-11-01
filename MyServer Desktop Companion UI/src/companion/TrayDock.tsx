import { getTranslation } from "./i18n"
import type { ReactNode } from "react"
import { Power } from "lucide-react"
import { useCompanion } from "./store"
import { cx } from "./ui"
import type { Tone, ViewId } from "./types"

const meterTone = (value: number): Tone =>
  value < 65 ? "success" : value < 85 ? "warning" : "danger"

const SVG_FILL_TONES: Record<Tone, string> = {
  success: "fill-success",
  warning: "fill-warning",
  danger: "fill-danger",
  info: "fill-info",
  neutral: "fill-line-strong",
}

function MetricTile({
  label,
  summary,
  onClick,
  children,
}: {
  label: string
  summary: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`${label}: ${summary}`}
      title={`${label} · ${summary}`}
      className="flex h-22 w-full shrink-0 flex-col items-center justify-between rounded-lg border border-line bg-linear-to-b from-surface to-surface-sunken px-1 py-3 shadow-tile transition-[border-color,box-shadow,translate] duration-150 outline-none hover:-translate-y-px hover:border-line-strong hover:shadow-card-hover focus-visible:ring-2 focus-visible:ring-info/45 focus-visible:ring-offset-2 active:translate-y-0 cursor-pointer"
    >
      {children}
      <span className="text-caption leading-none font-bold tracking-[0.06em] text-ink-soft uppercase whitespace-nowrap">
        {label}
      </span>
    </button>
  )
}

function Readout({ children }: { children: ReactNode }) {
  return (
    <span className="font-mono text-caption leading-none font-bold tracking-[-0.03em] text-ink">
      {children}
    </span>
  )
}

const DOT_COLS = 6
const DOT_ROWS = 3

/** Server-rack style LED bank: square dots, filled bottom-up per column. */
interface DotMatrixProps {
  levels: number[]
  tone: Tone
}

function DotMatrix({ levels, tone }: DotMatrixProps) {
  const colStep = 6
  const rowStep = 6
  const r = 2.1
  return (
    <svg
      viewBox="0 0 36 18"
      className="w-[36px] h-[18px] shrink-0 block overflow-visible"
      aria-hidden="true"
    >
      {Array.from({ length: DOT_COLS }, (_, col) => {
        const litCount = levels[col] || 0
        return Array.from({ length: DOT_ROWS }, (_, row) => {
          const heightFromBottom = DOT_ROWS - row
          const lit = heightFromBottom <= litCount
          const dotX = 3 + col * colStep
          const dotY = 3 + row * rowStep
          return (
            <circle
              key={`${col}-${row}`}
              cx={dotX}
              cy={dotY}
              r={r}
              className={cx(
                "transition-colors duration-300",
                lit ? SVG_FILL_TONES[tone] : "fill-line",
              )}
            />
          )
        })
      })}
    </svg>
  )
}

/** Spread a 0-100 value across the matrix so it fills column by column, like a level meter. */
function percentLevels(value: number, live: boolean) {
  const total = Math.round(((live ? value : 0) / 100) * DOT_COLS * DOT_ROWS)
  return Array.from({ length: DOT_COLS }, (_, col) =>
    Math.min(DOT_ROWS, Math.max(0, total - col * DOT_ROWS)),
  )
}

function PercentMeter({
  value,
  live,
  tone,
}: {
  value: number
  live: boolean
  tone: Tone
}) {
  return (
    <>
      <Readout>{live ? `${value}%` : "–"}</Readout>
      <DotMatrix
        levels={percentLevels(value, live)}
        tone={live ? tone : "neutral"}
      />
    </>
  )
}

/** Konversi kecepatan bytes/detik menjadi format minimal ringkas tanpa /s (contoh: 0B, 14K, 1.5M) */
function formatMinimalSpeed(bytesPerSec: number): string {
  if (!bytesPerSec || bytesPerSec <= 0) return "0B"
  if (bytesPerSec < 1024) {
    return `${Math.round(bytesPerSec)}B`
  }
  const kb = bytesPerSec / 1024
  if (kb < 1000) {
    return kb >= 10 ? `${Math.round(kb)}K` : `${kb.toFixed(1)}K`
  }
  const mb = kb / 1024
  if (mb < 1000) {
    return mb >= 10 ? `${Math.round(mb)}M` : `${mb.toFixed(1)}M`
  }
  const gb = mb / 1024
  return `${gb.toFixed(1)}G`
}

/** Konversi kecepatan bytes/detik menjadi persentase 0-100% untuk mengisi dot matrix */
function speedToPercent(bps: number): number {
  if (!bps || bps <= 0) return 0
  const kbps = bps / 1024
  if (kbps < 10) return Math.min(15, Math.max(5, Math.round(kbps * 1.5))) // 1 dot
  if (kbps < 100) return Math.round(15 + ((kbps - 10) / 90) * 20) // 15% - 35% (3-6 dots)
  if (kbps < 1000) return Math.round(35 + ((kbps - 100) / 900) * 25) // 35% - 60% (6-11 dots)
  const mbps = kbps / 1024
  if (mbps < 10) return Math.round(60 + ((mbps - 1) / 9) * 25) // 60% - 85% (11-15 dots)
  return Math.min(100, Math.round(85 + ((mbps - 10) / 40) * 15)) // 85% - 100% (15-18 dots)
}

function NetMeter({
  speedDownBps = 0,
  speedUpBps = 0,
  live,
}: {
  speedDownBps?: number
  speedUpBps?: number
  live: boolean
}) {
  const isUpHigher = live && speedUpBps > speedDownBps
  const activeBps = isUpHigher ? speedUpBps : speedDownBps

  const levels = percentLevels(speedToPercent(activeBps), live)
  const dotTone: Tone = isUpHigher ? "info" : "success"

  return (
    <>
      <Readout>{live ? formatMinimalSpeed(activeBps) : "–"}</Readout>
      <DotMatrix levels={levels} tone={live ? dotTone : "neutral"} />
    </>
  )
}

function SkeletonMeter() {
  const colStep = 6
  const rowStep = 6
  const r = 2.1
  return (
    <>
      <span className="inline-block h-3.5 w-7 rounded bg-line-strong animate-pulse" />
      <svg
        viewBox="0 0 36 18"
        className="w-[36px] h-[18px] shrink-0 block overflow-visible"
        aria-hidden="true"
      >
        {Array.from({ length: DOT_COLS }, (_, col) =>
          Array.from({ length: DOT_ROWS }, (_, row) => {
            const dotX = 3 + col * colStep
            const dotY = 3 + row * rowStep
            return (
              <circle
                key={`${col}-${row}`}
                cx={dotX}
                cy={dotY}
                r={r}
                className="fill-line-strong animate-pulse"
                style={{ animationDelay: `${col * 120}ms` }}
              />
            )
          })
        )}
      </svg>
    </>
  )
}

/** Floating vertical capsule with live server telemetry and the emergency power control. */
export default function TrayDock({
  powerActive,
  onNavigate,
}: {
  powerActive: boolean
  onNavigate: (view: ViewId) => void
}) {
  const { metrics, isOnline, power, settings, drives, transitionState, monitoringLoading } = useCompanion()
  const accountDrives = drives || []
  const accDriveCount = accountDrives.length
  const accTotalBytes = accountDrives.reduce((sum, d) => sum + (d.totalBytes || 0), 0)
  const accUsedBytes = accountDrives.reduce((sum, d) => sum + (d.usedBytes || 0), 0)
  const accUsedPct = accTotalBytes > 0 ? Math.round((accUsedBytes / accTotalBytes) * 100) : metrics.hdd
  const isId = settings?.language === "id"
  const offline = isId ? "server tidak terjangkau" : "server unreachable"
  const t = getTranslation(settings?.language)
  const isTelemetryLoading = power === "waking" || Boolean(monitoringLoading) || Boolean(transitionState?.active) || Boolean(metrics.isLoading)
  const connectingStr = t("connecting_telemetry", isId ? "Menghubungkan telemetri server…" : "Connecting server telemetry…")

  return (
    <aside
      aria-label="MyServer mini tray"
      className="flex h-companion w-dock shrink-0 flex-col items-center gap-2 rounded-2xl border border-line bg-surface p-3"
    >
      <MetricTile
        label="CPU"
        summary={
          isTelemetryLoading
            ? connectingStr
            : isOnline
              ? `${metrics.cpu}% ${isId ? "beban" : "load"}${metrics.cpuTemp !== undefined && metrics.cpuTemp !== null ? ` · ${metrics.cpuTemp.toFixed(1)}°C` : ""}${metrics.cpuWattage !== undefined ? ` · ${metrics.cpuWattage.toFixed(1)}W` : ""}`
              : offline
        }
        onClick={() => onNavigate("home")}
      >
        {isTelemetryLoading ? (
          <SkeletonMeter />
        ) : (
          <PercentMeter
            value={metrics.cpu}
            live={isOnline}
            tone={meterTone(metrics.cpu)}
          />
        )}
      </MetricTile>

      <MetricTile
        label="RAM"
        summary={
          isTelemetryLoading
            ? connectingStr
            : isOnline
              ? `${metrics.ram}% ${isId ? "terpakai" : "used"}${metrics.ramUsedBytes && metrics.ramTotalBytes ? ` (${(metrics.ramUsedBytes / (1024 ** 3)).toFixed(2)} GB / ${(metrics.ramTotalBytes / (1024 ** 3)).toFixed(2)} GB)` : ""}`
              : offline
        }
        onClick={() => onNavigate("home")}
      >
        {isTelemetryLoading ? (
          <SkeletonMeter />
        ) : (
          <PercentMeter
            value={metrics.ram}
            live={isOnline}
            tone={meterTone(metrics.ram)}
          />
        )}
      </MetricTile>

      <MetricTile
        label="DISK"
        summary={
          isTelemetryLoading
            ? connectingStr
            : isOnline
              ? `${accDriveCount > 0 ? accUsedPct : metrics.hdd}% ${isId ? "terpakai" : "used"}${accDriveCount > 0 && accTotalBytes > 0 ? ` (${(accUsedBytes / (1024 ** 3)).toFixed(1)} GB / ${(accTotalBytes / (1024 ** 3)).toFixed(1)} GB)` : metrics.storageUsedBytes && metrics.storageTotalBytes ? ` (${(metrics.storageUsedBytes / (1024 ** 3)).toFixed(1)} GB / ${(metrics.storageTotalBytes / (1024 ** 3)).toFixed(1)} GB)` : ""}${accDriveCount > 0 ? ` · ${accDriveCount} ${isId ? "disk" : "drives"}` : metrics.storagePartitions && metrics.storagePartitions.length > 0 ? ` · ${metrics.storagePartitions.length} ${isId ? "partisi" : "partitions"}` : ""}`
              : offline
        }
        onClick={() => onNavigate("files")}
      >
        {isTelemetryLoading ? (
          <SkeletonMeter />
        ) : (
          <PercentMeter
            value={accDriveCount > 0 && accTotalBytes > 0 ? accUsedPct : metrics.hdd}
            live={isOnline}
            tone={meterTone(accDriveCount > 0 && accTotalBytes > 0 ? accUsedPct : metrics.hdd)}
          />
        )}
      </MetricTile>

      <MetricTile
        label="NET"
        summary={
          isTelemetryLoading
            ? connectingStr
            : isOnline
              ? `↓ ${metrics.speedDownStr || "0 B/s"} · ↑ ${metrics.speedUpStr || "0 B/s"}`
              : offline
        }
        onClick={() => onNavigate("home")}
      >
        {isTelemetryLoading ? (
          <SkeletonMeter />
        ) : (
          <NetMeter
            speedDownBps={metrics.speedDownBps}
            speedUpBps={metrics.speedUpBps}
            live={isOnline}
          />
        )}
      </MetricTile>

      <div className="flex-1" aria-hidden />

      <button
        type="button"
        onClick={() => onNavigate(powerActive ? "home" : "power")}
        aria-label={t("power_title")}
        aria-pressed={powerActive}
        title={t("power_title")}
        className={cx(
          "inline-flex size-12 shrink-0 items-center justify-center rounded-full bg-linear-to-b from-danger-bright to-danger text-white shadow-power transition-[translate,box-shadow] duration-150 outline-none hover:from-danger hover:to-danger-strong focus-visible:ring-2 focus-visible:ring-danger/45 focus-visible:ring-offset-2 active:translate-y-px cursor-pointer",
          powerActive && "ring-4 ring-danger/20",
        )}
      >
        <Power className="size-5" strokeWidth={2.6} aria-hidden />
      </button>
    </aside>
  )
}

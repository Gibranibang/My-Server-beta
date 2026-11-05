import { getTranslation } from "./i18n"
import { useId, type ReactNode } from "react"
import { Power } from "lucide-react"
import { useCompanion } from "./store"
import { cx } from "./ui"
import type { Tone, ViewId } from "./types"

const meterTone = (value: number): Tone =>
  value < 65 ? "success" : value < 85 ? "warning" : "danger"

/**
 * Telemetry tile — 1:1 dari "Telementry Unit.svg" (Figma 136:27062), satu tile 50 × 74px.
 * Casing metalik rx=7.5, LCD #1B1B1B (46 × 50, radius atas 6px) dengan inner shadow
 * dx=4 dy=4 blur=3 rgba(255,255,255,.25), label bawah Plus Jakarta Sans Bold 9.6px #334155.
 * Isi LCD (angka "Doto" + dot-matrix 6×3) dikirim lewat children sebagai elemen SVG.
 */
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
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "")
  const fillId = `tile-fill-${uid}`
  const strokeId = `tile-stroke-${uid}`
  const innerId = `tile-inner-${uid}`
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`${label}: ${summary}`}
      title={`${label} · ${summary}`}
      className="relative block h-[74px] w-[50px] shrink-0 cursor-pointer select-none rounded-[8px] border-0 bg-transparent p-0 outline-none transition-[translate,filter] duration-150 hover:-translate-y-px hover:brightness-105 focus-visible:ring-2 focus-visible:ring-info/45 active:translate-y-0"
    >
      <svg
        width="50"
        height="74"
        viewBox="0 0 50 74"
        fill="none"
        className="block overflow-visible"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="telemetry-readout-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#7BC504" />
            <stop offset="100%" stopColor="#FBEE75" />
          </linearGradient>
          <radialGradient
            id={fillId}
            cx="0"
            cy="0"
            r="1"
            gradientUnits="userSpaceOnUse"
            gradientTransform="translate(25.0176 37) rotate(-90) scale(76.5517 51.7605)"
          >
            <stop stopColor="#E2E2E2" />
            <stop offset="1" stopColor="#ABABAB" />
          </radialGradient>
          <radialGradient
            id={strokeId}
            cx="0"
            cy="0"
            r="1"
            gradientUnits="userSpaceOnUse"
            gradientTransform="translate(25.0176 37) rotate(90) scale(37 25.0176)"
          >
            <stop stopColor="#DDDDDD" />
            <stop offset="1" stopColor="#D9D9D9" />
          </radialGradient>
          <filter
            id={innerId}
            x="2"
            y="2"
            width="50"
            height="54"
            filterUnits="userSpaceOnUse"
            colorInterpolationFilters="sRGB"
          >
            <feFlood floodOpacity="0" result="BackgroundImageFix" />
            <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape" />
            <feColorMatrix
              in="SourceAlpha"
              type="matrix"
              values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0"
              result="hardAlpha"
            />
            <feOffset dx="4" dy="4" />
            <feGaussianBlur stdDeviation="3" />
            <feComposite in2="hardAlpha" operator="arithmetic" k2="-1" k3="1" />
            <feColorMatrix
              type="matrix"
              values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.25 0"
            />
            <feBlend mode="normal" in2="shape" result="effect1_innerShadow" />
          </filter>
        </defs>
        {/* Casing metalik */}
        <rect x="0.5" y="0.5" width="49.0352" height="73" rx="7.5" fill={`url(#${fillId})`} />
        <rect x="0.5" y="0.5" width="49.0352" height="73" rx="7.5" stroke={`url(#${strokeId})`} />
        {/* Layar LCD hitam + inner shadow */}
        <g filter={`url(#${innerId})`}>
          <path d="M2 8C2 4.68629 4.68629 2 8 2H42C45.3137 2 48 4.68629 48 8V52H2V8Z" fill="#1B1B1B" />
        </g>
        <path
          d="M8 2.5H42C45.0376 2.5 47.5 4.96243 47.5 8V51.5H2.5V8C2.5 4.96243 4.96243 2.5 8 2.5Z"
          stroke="black"
        />
        {children}
        {/* Label pada strip metal bawah (y = 52..74) */}
        <text
          x="25"
          y="64"
          textAnchor="middle"
          fontFamily="'Plus Jakarta Sans', sans-serif"
          fontWeight={700}
          fontSize="9.6"
          fill="#334155"
        >
          {label}
        </text>
      </svg>
    </button>
  )
}

const LCD_GREEN = "#669E0C"
const LED_ON = "#7BC504"
const LED_OFF = "#263016"
const LED_ALERT = "#EF4444"

/** Angka persentase / kecepatan — font "Doto" (Figma: y = 10.67..16.88). */
function Readout({ children, tone }: { children: ReactNode; tone?: Tone }) {
  return (
    <text
      x="25"
      y="16"
      textAnchor="middle"
      fontFamily="'Doto', 'Doto:Black', monospace"
      style={{ fontVariationSettings: '"ROND" 100' }}
      fontWeight={900}
      fontSize="9.5"
      letterSpacing="-0.2px"
      fill={tone === "danger" ? LED_ALERT : "url(#telemetry-readout-grad)"}
    >
      {children}
    </text>
  )
}

const DOT_COLS = 6
const DOT_ROWS = 3
// Koordinat pusat lingkaran persis dari Telementry Unit.svg
const DOT_X0 = 11.9392
const DOT_Y0 = 30.6991
const DOT_COL_STEP = 5.0381
const DOT_ROW_STEP = 5.0383
const DOT_R = 1.7634

/** Server-rack style LED bank (6 × 3): terisi dari bawah per kolom. */
interface DotMatrixProps {
  levels: number[]
  tone: Tone
}

function DotMatrix({ levels, tone }: DotMatrixProps) {
  const on = tone === "danger" ? LED_ALERT : LED_ON
  return (
    <>
      {Array.from({ length: DOT_COLS }, (_, col) => {
        const litCount = levels[col] || 0
        return Array.from({ length: DOT_ROWS }, (_, row) => {
          const heightFromBottom = DOT_ROWS - row
          const lit = heightFromBottom <= litCount
          return (
            <circle
              key={`${col}-${row}`}
              cx={DOT_X0 + col * DOT_COL_STEP}
              cy={DOT_Y0 + row * DOT_ROW_STEP}
              r={DOT_R}
              fill={lit ? on : LED_OFF}
              style={{ transition: "fill 200ms" }}
            />
          )
        })
      })}
    </>
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
      <Readout tone={live ? tone : undefined}>{live ? `${value}%` : "–"}</Readout>
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
  if (kbps < 10) return Math.min(15, Math.max(5, Math.round(kbps * 1.5)))
  if (kbps < 100) return Math.round(15 + ((kbps - 10) / 90) * 20)
  if (kbps < 1000) return Math.round(35 + ((kbps - 100) / 900) * 25)
  const mbps = kbps / 1024
  if (mbps < 10) return Math.round(60 + ((mbps - 1) / 9) * 25)
  return Math.min(100, Math.round(85 + ((mbps - 10) / 40) * 15))
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
  return (
    <>
      <rect x="17" y="10.5" width="16" height="6" rx="2" fill="#333" className="animate-pulse" />
      {Array.from({ length: DOT_COLS }, (_, col) =>
        Array.from({ length: DOT_ROWS }, (_, row) => (
          <circle
            key={`${col}-${row}`}
            cx={DOT_X0 + col * DOT_COL_STEP}
            cy={DOT_Y0 + row * DOT_ROW_STEP}
            r={DOT_R}
            fill="#333"
            className="animate-pulse"
            style={{ animationDelay: `${col * 120}ms` }}
          />
        )),
      )}
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
      className="flex h-[410px] w-[70px] shrink-0 flex-col items-center rounded-[16px] border border-line bg-surface pt-[9px] pb-[9px] px-[9px] shadow-panel select-none"
    >
      {/* 4 Telemetry Tiles dengan jarak vertikal 10px (Telementry Unit.svg: y = 0, 84, 168, 252) */}
      <div className="flex flex-col gap-[10px]">
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
          onClick={() => onNavigate("server")}
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
      </div>

      {/* Emergency Power Button jarak otomatis (25.54px) di bawah tile NET */}
      <button
        type="button"
        onClick={() => onNavigate(powerActive ? "home" : "power")}
        aria-label={t("power_title")}
        aria-pressed={powerActive}
        title={t("power_title")}
        style={{ marginTop: "25px" }}
        className={cx(
          "inline-flex size-[40px] shrink-0 items-center justify-center rounded-full bg-gradient-to-b from-[#f87171] via-[#f45c5b] to-[#ef4444] text-white drop-shadow-[0px_8px_10px_rgba(239,68,68,0.35),0px_2px_2px_rgba(239,68,68,0.25)] shadow-[inset_0px_1px_0px_0px_rgba(255,255,255,0.35)] transition hover:scale-105 active:scale-95 outline-none focus-visible:ring-2 focus-visible:ring-danger/45 cursor-pointer",
          powerActive && "ring-4 ring-danger/30",
        )}
      >
        <Power className="size-[16.79px]" strokeWidth={2.4} aria-hidden />
      </button>
    </aside>
  )
}

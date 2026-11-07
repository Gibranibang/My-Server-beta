import { useState, useEffect, Component, type ErrorInfo, type ReactNode } from "react"
import { AlertTriangle, ChevronRight, CircleCheck, Info, RefreshCw, TriangleAlert, X, type LucideIcon } from "lucide-react"
import { assets } from "./assets"
import { useCompanion, useNotice, usePowerStatus } from "./store"
import { StatusDot, cx } from "./ui"
import type { Tone } from "./types"

/** Engineering graph-paper texture from the Figma reference, fading in toward the footer module. */
function GridTexture() {
  const { settings } = useCompanion()
  const isLight = settings?.theme === "light"

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-0 overflow-hidden rounded-[16px]">
      <img
        alt=""
        src={isLight ? assets.flyoutBgLight : assets.flyoutBgDark}
        className="block size-full object-cover select-none"
      />
    </div>
  )
}

function TopGlow() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute top-[-33.44px] left-[45.52px] -z-10 size-[68.88px]"
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
          className="flex items-center gap-2 rounded-full bg-slate-900/95 dark:bg-[#181D12]/95 border border-slate-700/50 dark:border-[#3A452D] py-1.5 pr-3.5 pl-2.5 text-caption font-medium text-white shadow-toast backdrop-blur motion-safe:animate-toast-in"
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
    <header className="flex h-[48px] shrink-0 items-center justify-between gap-[6.71px] px-[10.08px] pt-1.5 pb-1">
      <div className="flex min-w-0 flex-1 items-center">{leading}</div>
      <div className="flex shrink-0 items-center gap-[1.68px]">{trailing}</div>
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
    <div className="min-w-0 flex flex-col justify-center pl-1.5 py-0.5">
      <h2 className="truncate text-[12.5px] leading-tight font-bold tracking-tight text-ink" title={title}>
        {title}
      </h2>
      <p className="truncate text-[9.5px] leading-tight font-medium text-ink-subtle mt-[1px]">
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

/**
 * Notifikasi terakhir yang sudah "dibaca" (pill dibuka). Disimpan di level modul agar status
 * unread tetap konsisten ketika FooterStatus di-mount ulang saat berpindah menu.
 */
let lastSeenNoticeId = 0
try {
  const savedSeen = localStorage.getItem("myserver_last_seen_notice_id")
  if (savedSeen) lastSeenNoticeId = Number(savedSeen) || 0
} catch {}
const completedNoticeIds = new Set<number>()

/** Teks pill notifikasi: statis saat idle/count, berjalan (marquee) ketika ada notifikasi baru. */
function NoticeMarquee({
  text,
  noticeId,
  count,
}: {
  text: string
  noticeId?: number
  count: number
}) {
  const [activeCycleId, setActiveCycleId] = useState<number | undefined>(noticeId)
  const isAlreadySeen = noticeId ? completedNoticeIds.has(noticeId) : false
  const [isMarqueeDone, setIsMarqueeDone] = useState(isAlreadySeen)

  useEffect(() => {
    if (noticeId && noticeId !== activeCycleId) {
      setActiveCycleId(noticeId)
      const seen = completedNoticeIds.has(noticeId)
      setIsMarqueeDone(seen)
    }
  }, [noticeId, activeCycleId])

  const textCls =
    "font-['Doto'] font-black text-[8px] leading-none whitespace-nowrap bg-gradient-to-b from-[#7BC504] to-[#FBEE75] bg-clip-text text-transparent"

  const handleAnimationEnd = () => {
    if (noticeId) {
      completedNoticeIds.add(noticeId)
    }
    // Langsung selesaikan marquee agar berpindah ke angka badge tanpa snap-back ke tengah
    setIsMarqueeDone(true)
  }

  // Setelah 2 putaran teks berjalan (atau jika tidak ada teks baru), tampilkan jumlah notifikasi yang tersedia (atau '-' jika 0)
  if (isMarqueeDone || !text) {
    return (
      <span
        className={cx(
          "font-['Doto'] font-black text-[8px] leading-none text-center w-full block transition-opacity duration-200 select-none",
          textCls
        )}
        title={count > 0 ? `${count} notifikasi aktif` : "Tidak ada notifikasi baru"}
      >
        {count > 0 ? count : "-"}
      </span>
    )
  }

  // Kecepatan stabil ~30-32 px/detik berdasarkan total jarak tempuh riil (25px aperture + lebar teks)
  const approxWidth = Math.max(30, text.length * 6)
  const duration = Math.max(2.6, (25 + approxWidth) / 32)
  return (
    <span
      key={`${activeCycleId}-${text}`}
      className={cx(
        "inline-block notif-pill-marquee select-none",
        textCls
      )}
      style={{ animationDuration: `${duration}s`, animationIterationCount: 2 }}
      onAnimationEnd={handleAnimationEnd}
    >
      {text}
    </span>
  )
}

/**
 * Kartu status footer â€” 1:1 dari "footer.relative.svg" (Figma 142:4530 & 83:4623), kartu 252 Ã— 70px.
 */
/**
 * Pill status skeuomorfik untuk footer tray (1:1 styling pill HomeView dari Figma)
 */
export function TrayChip({
  tone = "neutral",
  icon: Icon,
  children,
  onClick,
  title,
  className,
}: {
  tone?: "success" | "info" | "warning" | "danger" | "neutral"
  icon?: LucideIcon
  children: ReactNode
  onClick?: () => void
  title?: string
  className?: string
}) {
  const toneClasses = {
    success: "border-[#A7F3D0] text-[#047857] shadow-[0px_2px_4px_rgba(80,130,0,0.18),inset_0px_1px_1px_rgba(255,255,255,0.9)]",
    info: "border-[#BFDBFE] text-[#1D4ED8] shadow-[0px_2px_4px_rgba(0,52,101,0.15),inset_0px_1px_1px_rgba(255,255,255,0.9)]",
    warning: "border-[#FDE68A] text-[#B45309] shadow-[0px_2px_4px_rgba(180,83,9,0.15),inset_0px_1px_1px_rgba(255,255,255,0.9)]",
    danger: "border-[#FECACA] text-[#DC2626] shadow-[0px_2px_4px_rgba(220,38,38,0.15),inset_0px_1px_1px_rgba(255,255,255,0.9)]",
    neutral: "border-[#DDD] text-[#334155] shadow-[0px_2px_4px_rgba(0,0,0,0.06),inset_0px_1px_1px_rgba(255,255,255,0.9)]",
  }

  const baseClasses = cx(
    "h-[20px] shrink-0 rounded-full bg-white border px-[7px] py-0 flex items-center gap-[3.5px] text-[8.5px] font-semibold leading-tight whitespace-nowrap select-none transition-all outline-none",
    toneClasses[tone],
    onClick && "cursor-pointer hover:bg-slate-50 hover:brightness-95 active:scale-95",
    className
  )

  if (onClick) {
    return (
      <button type="button" onClick={onClick} title={title} className={baseClasses}>
        {Icon && <Icon className="size-[10px] shrink-0" strokeWidth={2.2} aria-hidden />}
        {children}
      </button>
    )
  }

  return (
    <div title={title} className={baseClasses}>
      {Icon && <Icon className="size-[10px] shrink-0" strokeWidth={2.2} aria-hidden />}
      {children}
    </div>
  )
}

export function FooterStatus({
  title,
  chips,
  onClick,
  className,
  showNoticePill = true,
}: {
  title: ReactNode
  chips: ReactNode
  onClick?: () => void
  className?: string
  showNoticePill?: boolean
}) {
  const { noticeHistory, clearNoticeHistory } = useNotice()
  const { isOnline, settings } = useCompanion()
  const historyList = Array.isArray(noticeHistory) ? noticeHistory : []
  const status = usePowerStatus()
  const currentTone = status?.tone ?? (isOnline ? "success" : "neutral")
  const currentLabel = status?.label ?? (isOnline ? "Online" : "Offline")
  const isTransitioning = currentTone === "warning" && (currentLabel?.includes("...") ?? false)
  const [showNotifModal, setShowNotifModal] = useState(false)
  const [seenId, setSeenId] = useState(lastSeenNoticeId)
  const latest = historyList[0]
  const hasUnread = Boolean(latest) && latest!.id !== seenId
  
  const openNotifications = () => {
    lastSeenNoticeId = latest?.id ?? 0
    try {
      localStorage.setItem("myserver_last_seen_notice_id", String(lastSeenNoticeId))
    } catch {}
    setSeenId(lastSeenNoticeId)
    setShowNotifModal(true)
  }

  return (
    <footer className={cx("relative shrink-0 w-full z-10 px-0 pt-0", showNoticePill ? "pb-0" : "pb-[10px] mt-[9.19px]", className)}>
      <div
        className="relative w-[252px] h-[70px] mx-auto rounded-[10px] border-2 border-[#DDD] shadow-[4px_4px_4px_0px_rgba(0,0,0,0.15)] bg-[#F6F6F6] px-[7px] pt-[6.5px] pb-[6px] flex flex-col justify-between items-start overflow-hidden select-none"
      >
        {/* Glow hijau (#9DFF00, blur 53.76) di pojok kanan bawah persis sesuai SVG & Figma 142:4533 */}
        <div
          aria-hidden
          className="pointer-events-none absolute right-[4.78px] top-[31.91px] size-[42px] rounded-full bg-[#9DFF00] blur-[53.76px]"
        />

        {/* ROW 1: 1:1 Figma 142:4538 & footer.relative.svg — w-[234px], h-[21px], gap-[8px] */}
        <div className="flex items-center justify-between w-[234px] h-[21px] shrink-0 relative z-1">
          {/* LCD kiri — nama server (171 × 20px, rounded-[4px], border black, shadow inset 4px) */}
          <div
            onClick={isTransitioning ? undefined : onClick}
            role={onClick && !isTransitioning ? "button" : undefined}
            tabIndex={onClick && !isTransitioning ? 0 : undefined}
            onKeyDown={onClick && !isTransitioning ? (e) => (e.key === "Enter" || e.key === " " ? onClick() : undefined) : undefined}
            className={cx(
              "h-[20px] w-[171px] shrink-0 rounded-[4px] border border-black bg-[#1B1B1B] shadow-[inset_4px_4px_4px_0px_rgba(255,255,255,0.25)] px-[8px] flex items-center overflow-hidden outline-none",
              onClick && !isTransitioning && "cursor-pointer hover:border-[#444] transition",
            )}
            title="Buka status & rute server"
          >
            {isTransitioning ? (
              <div className="h-3.5 w-24 rounded bg-surface-sunken animate-pulse" />
            ) : (
              <div className="min-w-0 w-full truncate text-[11.5px] leading-none font-black bg-gradient-to-b from-[#7BC504] to-[#FBEE75] bg-clip-text text-transparent flex items-center justify-between font-['Doto']">
                {title}
              </div>
            )}
          </div>

          {/* LCD kanan — status koneksi (55 × 21px, rounded-[4px], border black, shadow inset 4px) */}
          <div className="h-[21px] w-[55px] shrink-0 rounded-[4px] border border-black bg-[#1B1B1B] shadow-[inset_4px_4px_4px_0px_rgba(255,255,255,0.25)] flex items-center justify-center overflow-hidden">
            {isTransitioning ? (
              <span className="inline-block h-2.5 w-8 rounded bg-surface-sunken animate-pulse" />
            ) : (
              <span
                className={cx(
                  "font-['Doto'] text-[9px] leading-normal font-black tracking-tight text-center whitespace-nowrap",
                  currentTone === "success" && "bg-gradient-to-b from-[#7BC504] to-[#FBEE75] bg-clip-text text-transparent",
                  currentTone === "warning" && "bg-gradient-to-b from-[#F59E0B] to-[#FDE047] bg-clip-text text-transparent animate-pulse",
                  currentTone === "danger" && "bg-gradient-to-b from-[#EF4444] to-[#FCA5A5] bg-clip-text text-transparent",
                  currentTone === "neutral" && "text-slate-400",
                )}
              >
                {currentLabel}
              </span>
            )}
          </div>
        </div>

        {/* ROW 2: 1:1 Figma 142:4544 & footer.relative.svg — w-[234px], h-[24px], justify-between */}
        <div className={cx("flex items-center h-[24px] shrink-0 relative z-1", showNoticePill ? "w-[234px] justify-between" : "w-full justify-start gap-1.5 px-0.5")}>
          {/* Baris chip */}
          <div className={cx("flex items-center overflow-visible", showNoticePill ? "gap-[6px] pl-[1px] shrink-0" : "gap-1.5 w-full")}>
            {chips}
          </div>

          {/* Pill notifikasi — hanya ditampilkan di HomeView (showNoticePill=true) */}
          {showNoticePill && (
            <div
              onClick={openNotifications}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " " ? openNotifications() : undefined)}
              className="group relative h-[24px] w-[56px] rounded-[128px] bg-[#1B1B1B] shadow-[inset_4px_4px_4px_0px_rgba(255,255,255,0.25)] cursor-pointer outline-none hover:brightness-110 transition shrink-0 select-none overflow-hidden"
              title={latest ? "Klik untuk membuka riwayat notifikasi" : "Belum ada notifikasi"}
            >
              {/* Lingkaran #EDEDED 16 × 16 (left 4px, centered vertically) dengan ikon lonceng hijau #5F9901 */}
              <span
                className={cx(
                  "absolute left-[4px] top-1/2 -translate-y-1/2 size-[16px] rounded-full bg-[#EDEDED] flex items-center justify-center shrink-0",
                  hasUnread && "notif-bell-ring",
                )}
              >
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path transform="translate(-210 -52)" d="M220.519 60.9157H220.234V56.8681C220.234 55.1883 218.992 53.8002 217.377 53.5693V53.1062C217.377 52.8431 216.163 52.63 216.9 52.63C216.637 52.63 216.424 52.8431 216.424 53.1062V53.5693C214.809 53.8002 213.567 55.1883 213.567 56.8681V60.9157H213.281C213.071 60.9157 212.9 61.086 212.9 61.2967V61.6776C212.9 61.73 212.943 61.7729 212.996 61.7729H215.567C215.567 62.5086 216.165 63.1062 216.9 63.1062C217.636 63.1062 218.234 62.5086 218.234 61.7729H220.805C220.858 61.7729 220.9 61.73 220.9 61.6776V61.2967C220.9 61.086 220.73 60.9157 220.519 60.9157ZM216.9 62.3443C216.585 62.3443 216.329 62.0883 216.329 61.7729H217.472C217.472 62.0883 217.216 62.3443 216.9 62.3443ZM214.424 60.9157V56.8681C214.424 56.2062 214.681 55.5848 215.149 55.1169C215.617 54.6491 216.238 54.3919 216.9 54.3919C217.562 54.3919 218.184 54.6491 218.652 55.1169C219.119 55.5848 219.377 56.2062 219.377 56.8681V60.9157H214.424Z" fill="#5F9901" />
                </svg>
              </span>
              {/* Layar teks aperture 25 × 13px: 1:1 Figma 142:4571 (left 35.5px, top 12.5px / center) */}
              <span className="absolute left-[35.5px] -translate-x-1/2 top-1/2 -translate-y-1/2 h-[13px] w-[25px] overflow-hidden flex items-center justify-start">
                <NoticeMarquee
                  text={hasUnread ? (latest?.text ?? "") : ""}
                  noticeId={hasUnread ? latest?.id : undefined}
                  count={historyList.length}
                  />
              </span>
            </div>
          )}
        </div>
      </div>


      {/* History modal */}
      {showNotifModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3 backdrop-blur-xs"
          onClick={() => setShowNotifModal(false)}
        >
          <div
            className="flex w-full max-w-[270px] flex-col gap-2 rounded-[10px] border border-[#262626] bg-[#11140C] p-3 text-white shadow-2xl motion-safe:animate-flyout-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#262626] pb-2">
              <span className="text-[11px] font-bold text-white flex items-center gap-1.5">
                <Info className="size-3.5 text-[#7BC504]" />
                Riwayat Notifikasi
              </span>
              <div className="flex items-center gap-2">
                {historyList.length > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      clearNoticeHistory?.(); window.dispatchEvent(new CustomEvent("myserver:clear-notices"))
                    }}
                    className="text-[9px] text-slate-400 hover:text-white transition cursor-pointer underline"
                  >
                    Bersihkan
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowNotifModal(false)}
                  aria-label="Tutup Riwayat Notifikasi"
                  className="rounded p-0.5 text-slate-400 hover:text-white transition cursor-pointer"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            </div>

            <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1 scrollbar-slim">
              {historyList.length === 0 ? (
                <div className="py-6 text-center text-[11px] text-slate-400">
                  Belum ada notifikasi pada sesi ini
                </div>
              ) : (
                historyList.map((item) => (
                  <div
                    key={item.id}
                    className="flex flex-col gap-0.5 rounded-[6px] border border-[#262626] bg-[#181D12] p-2 text-[10px]"
                  >
                    <div className="flex items-center justify-between text-slate-400 text-[9px] font-mono">
                      <span className={cx(
                        "font-semibold",
                        item.tone === "success" && "text-[#7BC504]",
                        item.tone === "danger" && "text-red-400",
                        item.tone === "warning" && "text-amber-400",
                        item.tone === "info" && "text-blue-400",
                      )}>
                        [{item.tone.toUpperCase()}]
                      </span>
                      <span>{item.timeStr}</span>
                    </div>
                    <span className="text-slate-200 break-words leading-tight">
                      {item.text}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
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
      className="relative isolate flex h-[410px] w-[286.26px] shrink-0 flex-col overflow-hidden rounded-[16px] border border-line bg-surface select-none shadow-panel motion-safe:animate-flyout-in"
    >
      <GridTexture />
      <TopGlow />
      <div className="relative z-10 flex flex-col flex-1 min-h-0">
        {header}
        <ViewErrorBoundary>{children}</ViewErrorBoundary>
      </div>
      <Toast />
      <TransitionOverlay />
    </section>
  )
}

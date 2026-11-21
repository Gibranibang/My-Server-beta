import { getTranslation } from "../i18n"
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react"
import { AlertTriangle, Folder, FolderOpen, HardDrive, Send, Server, ShieldCheck, Unplug } from "lucide-react"
import { FooterStatus, TrayChip } from "../FlyoutShell"
import { useAsyncAction, useCompanion, useNotice } from "../store"
import { getCompanionApi } from "../api"
import {
  Button,
  Card,
  Chip,
  IconBadge,
  Mono,
  SectionLabel,
  TextAction,
  cx,
} from "../ui"
import type { Drive, FileManagerSourceStatus, SmbSourceMode, Tone } from "../types"
import { LaunchTile, ViewBody } from "./shared"

export const BACKEND_SOURCE_POLL_MS = 25_000
export const DRIVES_REFRESH_POLL_MS = 10_000
const VISIBILITY_REFRESH_MIN_GAP_MS = 5_000

const STORAGE_DOT_COLS = 42
const STORAGE_DOT_ROWS = 3

const SVG_FILL_TONES: Record<Tone, string> = {
  success: "fill-success",
  warning: "fill-warning",
  danger: "fill-danger",
  info: "fill-info",
  neutral: "fill-line-strong",
}

const getStorageTone = (usedPct: number, live: boolean): Tone => {
  if (!live) return "neutral"
  return usedPct < 70 ? "success" : usedPct < 85 ? "warning" : "danger"
}

function StorageDotBar({ usedPct, tone }: { usedPct: number; tone: Tone }) {
  const colStep = 6
  const rowStep = 6
  const r = 2.1
  const totalDots = STORAGE_DOT_COLS * STORAGE_DOT_ROWS
  const totalLit = Math.round((Math.max(0, Math.min(100, usedPct)) / 100) * totalDots)

  return (
    <svg
      viewBox={`0 0 ${STORAGE_DOT_COLS * colStep} ${STORAGE_DOT_ROWS * rowStep}`}
      className="w-full h-[18px] block overflow-visible"
      aria-hidden="true"
    >
      {Array.from({ length: STORAGE_DOT_COLS }, (_, col) => {
        const colLitCount = Math.min(
          STORAGE_DOT_ROWS,
          Math.max(0, totalLit - col * STORAGE_DOT_ROWS),
        )
        return Array.from({ length: STORAGE_DOT_ROWS }, (_, row) => {
          const heightFromBottom = STORAGE_DOT_ROWS - row
          const lit = heightFromBottom <= colLitCount
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

interface DriveCardProps {
  drive: Drive
  online: boolean
}

function DriveCard({ drive, online, onOpen }: DriveCardProps & { onOpen: (letter: string) => void }) {
  const { settings } = useCompanion()
  const t = getTranslation(settings?.language)
  const live = drive.mounted && online
  const tone = getStorageTone(drive.usedPct, live)

  return (
    <Card
      onClick={() => live && onOpen(drive.letter)}
      className={cx(
        "flex flex-col gap-2.5 p-3 transition-colors",
        live && "cursor-pointer hover:border-line-strong hover:bg-surface-sunken",
      )}
    >
      {/* TIER 1: Header (Identitas Drive & Tombol Aksi) */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <IconBadge
            icon={HardDrive}
            tone={live ? tone : "neutral"}
            size="sm"
          />
          <div className="flex min-w-0 flex-1 items-baseline gap-1.5">
            <span className="shrink-0 text-caption font-semibold text-ink">
              Drive {drive.letter}:
            </span>
            <span
              className="truncate text-caption font-semibold text-ink-subtle"
              title={`Drive ${drive.letter}: [${drive.name}]`}
            >
              [{drive.name}]
            </span>
          </div>
        </div>
        <Chip
          size="sm"
          tone={live ? "success" : "neutral"}
          className="shrink-0"
          onClick={live ? () => onOpen(drive.letter) : undefined}
        >
          {live ? t("open_explorer_chip", "Open Explorer") : online ? t("unmounted_chip", "Unmounted") : t("offline_chip", "Offline")}
        </Chip>
      </div>

      {/* TIER 2: Meter Titik LED (StorageDotBar) */}
      <div className="w-full px-0.5">
        <StorageDotBar usedPct={drive.usedPct} tone={tone} />
      </div>

      {/* TIER 3: Footer Rincian Kapasitas & Persentase */}
      <div className="flex items-center justify-between gap-2 text-micro">
        <Mono className="truncate text-ink-subtle">
          {drive.free} free / {drive.total}
        </Mono>
        <Mono className={cx("shrink-0 font-semibold", live ? "text-ink" : "text-ink-subtle")}>
          {drive.usedPct}% {t("used_label", "used")}
        </Mono>
      </div>
    </Card>
  )
}

export default function FilesView() {
  const api = getCompanionApi()
  const { drives, setAllMounted, isOnline, refreshDrives, serverUrl, settings } = useCompanion()
  const t = getTranslation(settings?.language)
  const isDefaultExplorer = (settings?.fileManagerClickTarget || "explorer") === "explorer"
  const { notify } = useNotice()

  const [smbSource, setSmbSource] = useState<SmbSourceMode>("zimaos")
  const [sourceStatus, setSourceStatus] = useState<FileManagerSourceStatus | null>(null)
  const [isSwitchingSource, setIsSwitchingSource] = useState(false)
  const [editingBackendAuth, setEditingBackendAuth] = useState(false)
  const [backendUser, setBackendUser] = useState("")
  const [backendPass, setBackendPass] = useState("")
  const [isSubmittingAuth, setIsSubmittingAuth] = useState(false)
  const userTouchedSourceRef = useRef(false)
  const backendPassInputRef = useRef<HTMLInputElement | null>(null)
  const lastPollRef = useRef<number>(Date.now())
  const lastSourcePollRef = useRef<number>(Date.now())

  useEffect(() => {
    lastPollRef.current = Date.now()
    lastSourcePollRef.current = Date.now()
    void refreshDrives?.()

    const pollBackendSource = () => {
      if (
        smbSource !== "backend" ||
        isSwitchingSource ||
        isSubmittingAuth ||
        editingBackendAuth ||
        typeof api.getFileManagerSource !== "function"
      ) {
        return
      }
      lastSourcePollRef.current = Date.now()
      void api
        .getFileManagerSource()
        .then((res) => {
          if (res && res.source === "backend") {
            setSourceStatus((prev) => ({ ...(prev ?? { source: "backend" }), ...res }))
          }
        })
        .catch(() => {})
    }

    const drivesTimer = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) return
      lastPollRef.current = Date.now()
      void refreshDrives?.()
    }, DRIVES_REFRESH_POLL_MS)

    const sourceTimer =
      smbSource === "backend"
        ? setInterval(() => {
            if (typeof document !== "undefined" && document.hidden) return
            pollBackendSource()
          }, BACKEND_SOURCE_POLL_MS)
        : null

    const onVisibilityChange = () => {
      if (typeof document === "undefined" || document.hidden) return
      const nowTs = Date.now()
      if (nowTs - lastPollRef.current < VISIBILITY_REFRESH_MIN_GAP_MS) return
      lastPollRef.current = nowTs
      void refreshDrives?.()
      if (smbSource === "backend") {
        pollBackendSource()
      }
    }

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibilityChange)
    }

    return () => {
      clearInterval(drivesTimer)
      if (sourceTimer) clearInterval(sourceTimer)
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibilityChange)
      }
    }
  }, [api, editingBackendAuth, isSubmittingAuth, isSwitchingSource, refreshDrives, smbSource])

  useEffect(() => {
    let active = true
    if (typeof api.getFileManagerSource !== "function") return
    void api
      .getFileManagerSource()
      .then((res) => {
        if (!active || !res || userTouchedSourceRef.current) return
        setSourceStatus(res)
        const nextSource: SmbSourceMode = res.source === "backend" ? "backend" : "zimaos"
        setSmbSource(nextSource)
        if (res.needsAuth && res.username) {
          setBackendUser((prev) => prev || res.username || "")
        }
      })
      .catch(() => {
        // Fallback aman ke mode zimaos saat Core API belum siap
      })
    return () => {
      active = false
    }
  }, [api])

  const formatBackendError = useCallback(
    (rawError?: string) => {
      const detail = (rawError || "Server tidak merespons").trim()
      return `${t("backend_smb_error_prefix", "Gagal terhubung ke SMB Backend")}: ${detail}. ${t(
        "backend_smb_error_hint",
        "Periksa kembali username/kata sandi akun Backend atau pastikan container MyServer Backend sedang berjalan di port 8080.",
      )}`
    },
    [t],
  )

  const handleSelectSource = useCallback(
    async (target: SmbSourceMode) => {
      if (isSwitchingSource || isSubmittingAuth) return
      userTouchedSourceRef.current = true

      if (target === "zimaos") {
        if (smbSource === "zimaos") return
        setIsSwitchingSource(true)
        try {
          const res = await api.configureFileManagerSource?.({
            source: "zimaos",
            autoMount: true,
          })
          if (res && res.success === false) {
            notify(formatBackendError(res.error), "danger")
            return
          }
          setSmbSource("zimaos")
          if (res) setSourceStatus(res)
          setEditingBackendAuth(false)
          setBackendPass("")
          await refreshDrives?.()
          notify(t("zimaos_smb_connected_notice", "Sumber SMB ZimaOS aktif"), "success")
        } catch (err) {
          notify(formatBackendError(err instanceof Error ? err.message : String(err)), "danger")
        } finally {
          setIsSwitchingSource(false)
        }
        return
      }

      if (smbSource === "backend") return
      if (sourceStatus?.hasCredentials && !sourceStatus?.needsAuth) {
        setIsSwitchingSource(true)
        try {
          const res = await api.configureFileManagerSource?.({
            source: "backend",
            autoMount: true,
          })
          if (res?.needsAuth) {
            setSmbSource("backend")
            setSourceStatus({ ...res, source: "backend" })
            setBackendUser((prev) => prev || res.username || sourceStatus.username || "")
            setEditingBackendAuth(true)
            if (res.error) notify(formatBackendError(res.error), "danger")
            return
          }
          if (res && res.success === false) {
            notify(formatBackendError(res.error), "danger")
            return
          }
          setSmbSource("backend")
          if (res) setSourceStatus({ ...res, source: "backend" })
          setEditingBackendAuth(false)
          await refreshDrives?.()
          notify(t("backend_smb_connected_notice", "Sumber SMB Backend aktif"), "success")
        } catch (err) {
          notify(formatBackendError(err instanceof Error ? err.message : String(err)), "danger")
        } finally {
          setIsSwitchingSource(false)
        }
        return
      }

      setSmbSource("backend")
      if (sourceStatus?.username) {
        setBackendUser((prev) => prev || sourceStatus.username || "")
      }
      setEditingBackendAuth(true)
    },
    [
      api,
      formatBackendError,
      isSubmittingAuth,
      isSwitchingSource,
      notify,
      refreshDrives,
      smbSource,
      sourceStatus,
      t,
    ],
  )

  const handleBackendLoginSubmit = useCallback(
    async (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault()
      const uname = backendUser.trim()
      const pwd = backendPass
      if (!uname || !pwd || isSubmittingAuth || isSwitchingSource) return

      userTouchedSourceRef.current = true
      setIsSubmittingAuth(true)
      try {
        const res = await api.configureFileManagerSource?.({
          source: "backend",
          username: uname,
          password: pwd,
          autoMount: true,
        })
        setBackendPass("")
        if (res && res.success !== false && !res.needsAuth) {
          setSmbSource("backend")
          setSourceStatus({
            ...res,
            source: "backend",
            username: res.username || uname,
            hasCredentials: true,
            needsAuth: false,
          })
          setEditingBackendAuth(false)
          await refreshDrives?.()
          notify(t("backend_smb_connected_notice", "Sumber SMB Backend aktif"), "success")
        } else {
          if (res) {
            setSourceStatus((prev) =>
              editingBackendAuth
                ? {
                    ...(prev ?? { source: "backend" }),
                    source: "backend",
                    error: res.error,
                  }
                : {
                    ...(prev ?? { source: "backend" }),
                    ...res,
                    source: "backend",
                  },
            )
          }
          notify(formatBackendError(res?.error), "danger")
          backendPassInputRef.current?.focus()
        }
      } catch (err) {
        setBackendPass("")
        notify(formatBackendError(err instanceof Error ? err.message : String(err)), "danger")
        backendPassInputRef.current?.focus()
      } finally {
        setIsSubmittingAuth(false)
      }
    },
    [
      api,
      backendPass,
      backendUser,
      editingBackendAuth,
      formatBackendError,
      isSubmittingAuth,
      isSwitchingSource,
      notify,
      refreshDrives,
      t,
    ],
  )

  const showBackendLoginCard =
    !sourceStatus?.hasCredentials || Boolean(sourceStatus?.needsAuth) || editingBackendAuth

  const activeHost = useMemo(() => {
    if (serverUrl) {
      try {
        const u = new URL(serverUrl.startsWith("http") ? serverUrl : `http://${serverUrl}`)
        if (u.hostname) return u.hostname
      } catch {
        // ignore
      }
    }
    return "127.0.0.1"
  }, [serverUrl])
  const uncHost = `\\${activeHost}`

  const mountAll = useCallback(() => setAllMounted(true), [setAllMounted])
  const unmountAll = useCallback(() => setAllMounted(false), [setAllMounted])
  const [mountState, runMount] = useAsyncAction(mountAll)
  const [unmountState, runUnmount] = useAsyncAction(unmountAll)
  const mounted = drives.filter((d) => d.mounted).length
  const online = isOnline ? mounted : 0

  return (
    <>
      <ViewBody>
        {/* Storage Source Segmented Control (SettingsView.tsx pattern, D-06) */}
        <div className="flex flex-col gap-1.5 rounded-tile border border-line bg-surface p-2.5">
          <span className="text-micro font-semibold text-ink">
            {t("smb_source_title", "Sumber Penyimpanan (SMB)")}
          </span>
          <div
            role="tablist"
            aria-label="Sumber Penyimpanan SMB"
            className="grid grid-cols-2 gap-2 pt-1"
          >
            <button
              type="button"
              role="tab"
              aria-selected={smbSource === "zimaos"}
              disabled={isSwitchingSource || isSubmittingAuth}
              onClick={() => void handleSelectSource("zimaos")}
              className={cx(
                "flex items-center justify-center gap-1.5 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border disabled:opacity-60",
                smbSource === "zimaos"
                  ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                  : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
              )}
            >
              <Folder className="size-3.5" aria-hidden />
              <span>{t("smb_source_zimaos", "ZimaOS")}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={smbSource === "backend"}
              disabled={isSwitchingSource || isSubmittingAuth}
              onClick={() => void handleSelectSource("backend")}
              className={cx(
                "flex items-center justify-center gap-1.5 rounded-control px-2.5 py-1.5 text-micro font-medium transition cursor-pointer border disabled:opacity-60",
                smbSource === "backend"
                  ? "bg-brand text-brand-ink border-transparent font-semibold shadow-xs"
                  : "bg-surface-sunken text-ink-subtle border-line hover:text-ink",
              )}
            >
              <Server className="size-3.5" aria-hidden />
              <span>{t("smb_source_backend", "Backend")}</span>
            </button>
          </div>
        </div>

        {/* Backend Login / Authenticated Status Card (ui.tsx primitives, D-06) */}
        {smbSource === "backend" &&
          (showBackendLoginCard ? (
            <Card className="flex flex-col gap-2.5 p-3">
              <div className="flex items-start gap-2.5">
                <IconBadge icon={ShieldCheck} tone="info" size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="text-caption font-semibold text-ink">
                    {sourceStatus?.hasCredentials && !sourceStatus?.needsAuth
                      ? t("backend_smb_login_title", "Masuk Akun Backend")
                      : t("backend_smb_not_connected_title", "Akun Backend Belum Terhubung")}
                  </div>
                  <p className="mt-0.5 text-micro text-ink-subtle leading-snug">
                    {t(
                      "backend_smb_not_connected_body",
                      "Masukkan username dan kata sandi akun MyServer Backend Anda di atas untuk memuat daftar partisi SMB yang diizinkan.",
                    )}
                  </p>
                </div>
              </div>

              <form onSubmit={handleBackendLoginSubmit} className="flex flex-col gap-2">
                <div className="flex flex-col gap-1">
                  <label
                    htmlFor="backend-smb-user"
                    className="text-micro font-semibold text-ink-subtle"
                  >
                    {t("backend_user_label", "Username Akun Backend")}
                  </label>
                  <input
                    id="backend-smb-user"
                    type="text"
                    value={backendUser}
                    onChange={(e) => setBackendUser(e.target.value)}
                    placeholder={t("backend_user_placeholder", "Masukkan username Backend...")}
                    aria-label={t("backend_user_label", "Username Akun Backend")}
                    autoComplete="username"
                    className="w-full rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-medium text-ink focus:border-brand focus:outline-none"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label
                    htmlFor="backend-smb-pass"
                    className="text-micro font-semibold text-ink-subtle"
                  >
                    {t("backend_pass_label", "Kata Sandi Akun Backend")}
                  </label>
                  <input
                    id="backend-smb-pass"
                    ref={backendPassInputRef}
                    type="password"
                    value={backendPass}
                    onChange={(e) => setBackendPass(e.target.value)}
                    placeholder={t("backend_pass_placeholder", "Masukkan kata sandi...")}
                    aria-label={t("backend_pass_label", "Kata Sandi Akun Backend")}
                    autoComplete="current-password"
                    className="w-full rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-medium text-ink focus:border-brand focus:outline-none"
                  />
                </div>

                <div className="flex flex-col gap-1.5 pt-0.5">
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    block
                    disabled={!isOnline || !backendUser.trim() || !backendPass || isSubmittingAuth}
                    state={isSubmittingAuth ? "busy" : "idle"}
                    busyLabel={t("backend_smb_busy", "Memverifikasi & mengaktifkan SMB…")}
                  >
                    {t("backend_smb_login_btn", "Hubungkan Akun Backend")}
                  </Button>

                  {sourceStatus?.hasCredentials && !sourceStatus?.needsAuth && (
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      block
                      disabled={isSubmittingAuth}
                      onClick={() => {
                        setEditingBackendAuth(false)
                        setBackendPass("")
                      }}
                    >
                      {t("backend_smb_cancel_btn", "Batal Ganti Akun")}
                    </Button>
                  )}
                </div>
              </form>
            </Card>
          ) : (
            <Card
              onClick={() => {
                setBackendUser(sourceStatus?.username || "")
                setBackendPass("")
                setEditingBackendAuth(true)
              }}
              className="flex items-center justify-between gap-2 p-2.5 transition-colors cursor-pointer hover:border-line-strong hover:bg-surface-sunken"
            >
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <IconBadge icon={ShieldCheck} tone="info" size="sm" />
                <Mono
                  className="truncate text-caption font-semibold text-ink"
                  title={sourceStatus?.username}
                >
                  {sourceStatus?.username}
                </Mono>
              </div>
              <TextAction
                aria-label={t("backend_smb_switch_btn", "Ganti Akun Backend")}
                onClick={() => {
                  setBackendUser(sourceStatus?.username || "")
                  setBackendPass("")
                  setEditingBackendAuth(true)
                }}
              >
                {t("backend_smb_switch_btn", "Ganti Akun Backend")}
              </TextAction>
            </Card>
          ))}

        <div className="grid grid-cols-2 gap-2.5">
          {isDefaultExplorer ? (
            <LaunchTile
              icon={Folder}
              tone="warning"
              title={
                smbSource === "backend"
                  ? t("backend_files_tile_title", "Backend Files")
                  : "ZimaOS Files"
              }
              caption={t("open_web_files_caption", "Open Web File Manager")}
              disabled={!isOnline}
              onClick={async () => {
                if (smbSource === "backend") {
                  try {
                    const res = await api.openBackendFileManager?.()
                    if (res && res.success === true) {
                      notify(
                        t("opening_backend_fm_notice", "Membuka Storage Explorer Backend..."),
                        "info",
                      )
                    } else {
                      notify(
                        res?.error ||
                          t("backend_explorer_unreachable", "Backend tidak dapat dijangkau."),
                        "danger",
                      )
                    }
                  } catch (err) {
                    notify(
                      err instanceof Error && err.message
                        ? err.message
                        : t("backend_explorer_unreachable", "Backend tidak dapat dijangkau."),
                      "danger",
                    )
                  }
                } else {
                  api.openZimaFileManager()
                  notify(t("opening_zima_fm_notice", "Opening ZimaOS File Manager..."), "info")
                }
              }}
            />
          ) : (
            <LaunchTile
              icon={HardDrive}
              tone="info"
              title="File Explorer"
              caption={t("open_smb_explorer_caption", "Open SMB in File Explorer")}
              disabled={!isOnline}
              onClick={async () => {
                const res = await api.openFileExplorer()
                if (res && res.success === false) {
                  notify(
                    res.error || t("smb_preflight_unreachable", "Port 445 SMB server tidak merespons. Pembukaan File Explorer dibatalkan agar tidak hang."),
                    "danger",
                  )
                } else {
                  notify(t("opening_explorer_notice", "Opening Windows File Explorer to SMB disk..."), "info")
                }
              }}
            />
          )}
          <LaunchTile
            icon={Send}
            tone="info"
            title="PeerDrop"
            caption={t("peerdrop_caption", "P2P Direct File Sharing")}
            disabled={!isOnline}
            onClick={() => {
              api.openPeerDrop()
              notify(t("opening_peerdrop_notice", "Launching PeerDrop window..."), "info")
            }}
          />
        </div>

        {sourceStatus?.easytierNoTun && (
          <div data-testid="easytier-no-tun-warning" role="status">
            <Card className="flex items-start gap-2.5 p-2.5 border-warning/40 bg-warning/5">
              <IconBadge icon={AlertTriangle} tone="warning" size="sm" />
              <div className="min-w-0 flex-1">
                <div className="text-micro font-semibold text-ink">
                  {t("easytier_no_tun_warning_title", "Adapter Wintun EasyTier Tidak Aktif (--no-tun)")}
                </div>
                <p className="text-nano text-ink-muted leading-snug mt-0.5">
                  {sourceStatus.smbWarning ||
                    t(
                      "easytier_no_tun_warning_desc",
                      "Akses drive SMB via EasyTier memerlukan izin Administrator/UAC untuk adapter Wintun. Jalankan ulang sebagai Admin atau gunakan rute LAN / ZeroTier.",
                    )}
                </p>
              </div>
            </Card>
          </div>
        )}

        <section
          aria-label="Network Drive (SMB)"
          className="flex flex-col gap-2"
        >
          <SectionLabel trailing={`${mounted}/${drives.length} ${t("mounted_trailing", "mounted")}`}>
            Network Drive (SMB)
          </SectionLabel>
          {drives.map((drive) => (
            <DriveCard
              key={drive.letter}
              drive={drive}
              online={isOnline}
              onOpen={async (letter) => {
                const res = await api.openDrive(letter)
                if (res && res.success === false) {
                  notify(
                    res.error || t("smb_preflight_unreachable", "Port 445 SMB server tidak merespons. Pembukaan File Explorer dibatalkan agar tidak hang."),
                    "danger",
                  )
                } else {
                  notify(t("opening_explorer_notice", "Opening Windows File Explorer to SMB disk..."), "info")
                }
              }}
            />
          ))}
          {smbSource === "backend" && drives.length === 0 && (
            <Card className="p-2.5 text-micro text-ink-subtle">
              {t("backend_smb_empty_drives", "Belum Ada Partisi Penyimpanan Terdeteksi")}
            </Card>
          )}
        </section>

        <div className="flex flex-col gap-2">
          <Button
            variant="primary"
            icon={HardDrive}
            block
            disabled={!isOnline}
            state={mountState}
            busyLabel={t("mount_all_busy", "Mounting drives…")}
            doneLabel={t("mount_all_done", "All drives mounted")}
            onClick={() =>
              runMount(() => notify(t("all_mounted_notice", "All server storage partitions mounted via SMB")))
            }
          >{t("mount_all_btn", "Mount All Server Drives")}</Button>
          <Button
            variant="secondary"
            icon={Unplug}
            block
            disabled={mounted === 0 && unmountState === "idle"}
            state={unmountState}
            busyLabel={t("unmount_all_busy", "Disconnecting drives…")}
            doneLabel={t("unmount_all_done", "All drives disconnected")}
            onClick={() =>
              runUnmount(() =>
                notify(t("all_unmounted_notice", "All network drives disconnected"), "neutral"),
              )
            }
          >{t("unmount_all_btn", "Disconnect All Drives")}</Button>
        </div>
      </ViewBody>

      <FooterStatus
        showNoticePill={false}
        title={
          <>
            Host: <Mono className="font-semibold">{uncHost}</Mono>
          </>
        }
        chips={
          <>
            <TrayChip tone={isOnline ? "success" : "neutral"}>
              SMBv3 {isOnline ? "Active" : "Idle"}
            </TrayChip>
            <TrayChip tone={online > 0 ? "info" : "neutral"}>
              {online} {online === 1 ? "Drive" : "Drives"}
            </TrayChip>
            <TrayChip
              icon={FolderOpen}
              onClick={async () => {
                const res = await api.openUnc()
                if (res && res.success === false) {
                  notify(
                    res.error || t("smb_preflight_unreachable", "Port 445 SMB server tidak merespons. Pembukaan File Explorer dibatalkan agar tidak hang."),
                    "danger",
                  )
                } else {
                  notify(`Membuka root ${uncHost} di Explorer`, "info")
                }
              }}
              title={`Open Root UNC ${uncHost}`}
            >{t("open_unc_chip", "Open UNC")}</TrayChip>
          </>
        }
      />
    </>
  )
}

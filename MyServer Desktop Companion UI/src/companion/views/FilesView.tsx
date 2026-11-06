import { getTranslation } from "../i18n"
import { useCallback, useEffect, useMemo } from "react"
import { Folder, FolderOpen, HardDrive, Send, Unplug } from "lucide-react"
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
  cx,
} from "../ui"
import type { Drive, Tone } from "../types"
import { LaunchTile, ViewBody } from "./shared"

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

  useEffect(() => {
    void refreshDrives?.()
    const timer = setInterval(() => {
      void refreshDrives?.()
    }, 3000)
    return () => clearInterval(timer)
  }, [refreshDrives])

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
        <div className="grid grid-cols-2 gap-2.5">
          {isDefaultExplorer ? (
            <LaunchTile
              icon={Folder}
              tone="warning"
              title="ZimaOS Files"
              caption={t("open_web_files_caption", "Open Web File Manager")}
              disabled={!isOnline}
              onClick={() => {
                api.openZimaFileManager()
                notify(t("opening_zima_fm_notice", "Opening ZimaOS File Manager..."), "info")
              }}
            />
          ) : (
            <LaunchTile
              icon={HardDrive}
              tone="info"
              title="File Explorer"
              caption={t("open_smb_explorer_caption", "Open SMB in File Explorer")}
              disabled={!isOnline}
              onClick={() => {
                api.openFileExplorer()
                notify(t("opening_explorer_notice", "Opening Windows File Explorer to SMB disk..."), "info")
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
              onOpen={(letter) => {
                api.openDrive(letter)
                notify(t("opening_explorer_notice", "Opening Windows File Explorer to SMB disk..."), "info")
              }}
            />
          ))}
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
              onClick={() => {
                api.openUnc()
                notify(`Membuka root ${uncHost} di Explorer`, "info")
              }}
              title={`Open Root UNC ${uncHost}`}
            >{t("open_unc_chip", "Open UNC")}</TrayChip>
          </>
        }
      />
    </>
  )
}

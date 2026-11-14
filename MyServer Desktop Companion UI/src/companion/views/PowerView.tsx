import { getTranslation } from "../i18n"
import { useEffect, useState } from "react"
import { Circle, CircleCheck, Power, Radar, RotateCw, ShieldAlert, Zap, AlertTriangle } from "lucide-react"
import { FooterStatus, TrayChip } from "../FlyoutShell"
import { getCompanionApi } from "../api"
import {
  SERVER_IP,
  errorText,
  useAsyncAction,
  useCompanion,
  useNotice,
} from "../store"
import { Button, Card, Chip, IconBadge, Mono, cx } from "../ui"
import type { ChecklistKey, ServerDetails } from "../types"
import { ViewBody } from "./shared"

const MAC_PATTERN = /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/

const formatMac = (raw: string) =>
  raw
    .toUpperCase()
    .replace(/[^0-9A-F]/g, "")
    .slice(0, 12)
    .replace(/(.{2})(?=.)/g, "$1:")

export default function PowerView() {
  const api = getCompanionApi()
  const {
    power,
    isOnline,
    isAdmin,
    reboot,
    shutdown,
    wake,
    mac,
    setMac,
    checklist,
    toggleCheck,
    settings,
  } = useCompanion()
  const t = getTranslation(settings?.language)
  const { notify } = useNotice()

  const [serverDetails, setServerDetails] = useState<ServerDetails | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [arpState, runArp] = useAsyncAction(api.detectMac)
  const [wolState, runWol] = useAsyncAction(wake)

  useEffect(() => {
    void api
      .getServerDetails()
      .then((details) => {
        setServerDetails(details)
        if (details?.macAddress && details.macAddress.trim()) {
          setMac(details.macAddress.trim().toUpperCase())
        }
      })
      .catch(() => undefined)
  }, [api, setMac])

  // 1. Dinamis: Deteksi apakah rute aktif saat ini adalah jaringan fisik LAN lokal
  const activeRouteObj = serverDetails?.routes?.find((r) => r.active)
  const activeUrl = (activeRouteObj?.url || serverDetails?.activeHost || "").toLowerCase()
  const isLanRoute = Boolean(
    activeUrl &&
    (
      activeUrl.includes("192.168.") ||
      activeUrl.includes("10.") ||
      activeUrl.includes(".local") ||
      activeUrl.includes("127.0.0.1") ||
      activeUrl.includes("localhost") ||
      /172\.(1[6-9]|2[0-9]|3[0-1])\./.test(activeUrl)
    ) &&
    !activeUrl.includes("172.24.") &&
    !activeUrl.includes("172.25.")
  )

  // 2. Persistensi konfirmasi hardware BIOS & Standby per server di localStorage
  const serverId = serverDetails?.serverId || "default"
  useEffect(() => {
    if (!serverId || serverId === "default") return
    try {
      const savedBios = localStorage.getItem(`myserver_wol_bios_${serverId}`) === "true"
      const savedStandby = localStorage.getItem(`myserver_wol_standby_${serverId}`) === "true"
      toggleCheck("bios", savedBios)
      toggleCheck("standby", savedStandby)
    } catch {
      // ignore
    }
  }, [serverId])

  // Sinkronkan status checklist LAN otomatis mengikuti rute jaringan aktif
  useEffect(() => {
    toggleCheck("lan", isLanRoute)
  }, [isLanRoute])

  const handleToggleCheck = (key: ChecklistKey) => {
    if (key === "lan") {
      if (!isLanRoute) {
        notify(t("wol_lan_not_active_notice", "Koneksi saat ini bukan LAN lokal (WAN/Domain). WoL membutuhkan jaringan LAN fisik."), "warning")
      }
      return
    }
    const nextVal = !checklist[key]
    toggleCheck(key, nextVal)
    try {
      localStorage.setItem(`myserver_wol_${key}_${serverId}`, String(nextVal))
    } catch {
      // ignore
    }
  }

  const userIsAdmin = Boolean(isAdmin || serverDetails?.isAdmin)
  const activeUser = serverDetails?.activeProfile || "User"

  const macValid = MAC_PATTERN.test(mac) && mac !== "00:00:00:00:00:00"
  const isLanReady = isLanRoute
  const isBiosReady = Boolean(checklist.bios)
  const isStandbyReady = Boolean(checklist.standby)

  // STATUS READY MURNI DINAMIS: Hanya aktif bila MAC valid, koneksi LAN lokal aktif, dan hardware telah dikonfirmasi!
  const ready = macValid && isLanReady && isBiosReady && isStandbyReady

  const checklistItems = [
    {
      key: "lan" as const,
      label: t("wol_lan_check", "Kabel LAN Fisik Terhubung"),
      checked: isLanReady,
      desc: isLanReady
        ? t("wol_lan_detected", "Terhubung ke jaringan LAN fisik lokal")
        : t("wol_wan_detected", "Rute aktif: WAN / Domain (WoL butuh LAN)"),
      isAuto: true,
    },
    {
      key: "bios" as const,
      label: t("wol_bios_check", "WoL Aktif di BIOS / UEFI"),
      checked: isBiosReady,
      desc: isBiosReady
        ? t("wol_bios_confirmed", "Telah dikonfirmasi aktif di BIOS / UEFI")
        : t("wol_bios_unconfirmed", "Klik untuk konfirmasi aktif di BIOS"),
      isAuto: false,
    },
    {
      key: "standby" as const,
      label: t("wol_standby_check", "Daya Siaga Aktif (+5VSB)"),
      checked: isStandbyReady,
      desc: isStandbyReady
        ? t("wol_standby_confirmed", "Telah dikonfirmasi daya siaga aktif")
        : t("wol_standby_unconfirmed", "Klik untuk konfirmasi kabel power standby"),
      isAuto: false,
    },
  ]

  useEffect(() => {
    if (!confirming) return
    const timer = window.setTimeout(() => setConfirming(false), 3200)
    return () => window.clearTimeout(timer)
  }, [confirming])

  const onShutdown = () => {
    if (!confirming) return setConfirming(true)
    setConfirming(false)
    shutdown()
      .then(() => notify(t("notify_server_shutdown_wol", "Server dimatikan · nyalakan lagi via WoL"), "warning"))
      .catch((e) => notify(errorText(e), "danger"))
  }

  const onWake = () => {
    if (!isLanReady) {
      notify(t("wol_wan_sent_warning", "Magic packet terkirim, namun rute aktif bukan LAN lokal. Server mungkin tidak menyala melalui WAN."), "warning")
    }
    runWol(() =>
      notify(
        power === "offline" || power === "waking"
          ? t("notify_wol_magic_packet_waking", `Magic packet → ${mac} · server menyala`)
          : t("notify_wol_magic_packet_online", "Magic packet terkirim · server sudah online"),
        "info",
      ),
    )
  }

  return (
    <>
      <ViewBody>
        {!userIsAdmin ? (
          <Card className="flex flex-col gap-2 rounded-tile border border-warning-line/60 bg-warning-soft/20 p-3 text-caption">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 font-semibold text-warning-ink">
                <ShieldAlert className="size-4 text-warning shrink-0" />
                {t("power_control_title", "Kontrol Daya Server")}
              </span>
              <span className="rounded bg-warning/15 px-2 py-0.5 text-nano font-bold tracking-wider uppercase text-warning-ink border border-warning/30">
                {t("admin_only_badge", "Admin Only")}
              </span>
            </div>
            <p className="text-[10px] text-ink-subtle leading-normal">
              {t("admin_power_locked_desc", `Tombol Reboot & Shutdown hanya dapat dikendalikan oleh Administrator. Profil saat ini (${activeUser}) adalah akun pengguna standar.`)}
            </p>
            <div className="grid grid-cols-2 gap-1.5 pt-1 opacity-75 cursor-not-allowed">
              <button
                type="button"
                disabled
                className="h-[26px] px-1.5 flex items-center justify-center gap-1 rounded-full bg-surface-muted border border-line text-ink-soft text-[9px] font-medium tracking-tight transition cursor-not-allowed select-none"
              >
                <RotateCw className="size-3 shrink-0 stroke-[2]" aria-hidden />
                <span className="whitespace-nowrap">{t("reboot_locked", "Reboot (Terkunci)")}</span>
              </button>
              <button
                type="button"
                disabled
                className="h-[26px] px-1.5 flex items-center justify-center gap-1 rounded-full bg-danger-soft/40 border border-danger/30 text-danger-ink text-[9px] font-medium tracking-tight transition cursor-not-allowed select-none"
              >
                <Power className="size-3 shrink-0 stroke-[2]" aria-hidden />
                <span className="whitespace-nowrap">{t("shutdown_locked", "Shutdown (Terkunci)")}</span>
              </button>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={power === "offline" || power === "waking"}
              onClick={() => {
                if (!isOnline) return
                reboot()
                  .then(() =>
                    notify(t("reboot_sent_notice", "Perintah reboot dikirim ke server"), "warning"),
                  )
                  .catch((e) => notify(errorText(e), "danger"))
              }}
              className="h-[28px] px-2 flex items-center justify-center gap-1.5 rounded-full bg-surface-muted hover:bg-line text-ink-soft text-[11px] font-medium transition cursor-pointer select-none disabled:opacity-45 disabled:pointer-events-none"
            >
              <RotateCw className="size-3.5 shrink-0 stroke-[2]" aria-hidden />
              <span className="truncate">{t("reboot_server_btn", "Muat Ulang Server")}</span>
            </button>
            <button
              type="button"
              disabled={!isOnline}
              onClick={onShutdown}
              className={cx(
                "h-[28px] px-2 flex items-center justify-center gap-1.5 rounded-full bg-danger/15 hover:bg-danger/25 text-danger-ink border border-danger/30 text-[11px] font-semibold transition cursor-pointer select-none disabled:opacity-45 disabled:pointer-events-none",
                confirming && "ring-4 ring-danger/25"
              )}
            >
              <Power className="size-3.5 shrink-0 stroke-[2]" aria-hidden />
              <span className="truncate">
                {confirming
                  ? t("confirm_click_again", "Konfirmasi")
                  : power === "offline"
                    ? t("server_offline_status", "Server Mati")
                    : t("shutdown_server_btn", "Matikan Server")}
              </span>
            </button>
          </div>
        )}

        <Card className="flex flex-col gap-2.5 p-3.5">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2 text-label font-semibold text-ink">
              <IconBadge icon={Zap} tone="warning" size="sm" />
              Wake-on-LAN (WoL)
            </span>
            <Chip
              size="sm"
              tone={ready ? "success" : (!isLanReady || !macValid ? "warning" : "warning")}
            >
              {ready
                ? t("status_ready", "Siap")
                : !isLanReady
                  ? t("wol_status_need_lan", "Perlu LAN")
                  : !macValid
                    ? t("wol_status_need_mac", "Perlu MAC")
                    : t("status_check", "Periksa")}
            </Chip>
          </div>

          <div
            className={cx(
              "flex h-[30px] items-center gap-1.5 rounded-lg border bg-surface-sunken pr-1 pl-2.5 shadow-track transition-[border-color,box-shadow] focus-within:ring-2 focus-within:ring-info/15",
              macValid
                ? "border-line focus-within:border-info/50"
                : "border-warning",
            )}
          >
            <input
              aria-label="MAC Address"
              aria-invalid={!macValid || undefined}
              value={mac}
              onChange={(event) => {
                const next = formatMac(event.target.value)
                setMac(next)
                if (MAC_PATTERN.test(next)) {
                  void api.saveMac(next)
                }
              }}
              onBlur={() => {
                if (macValid) {
                  void api.saveMac(mac)
                  notify(t("notify_mac_saved_permanent", `MAC ${mac} disimpan permanen`), "info")
                }
              }}
              spellCheck={false}
              autoComplete="off"
              placeholder={t("mac_placeholder", "Masukkan MAC atau klik Deteksi ARP")}
              className="min-w-0 flex-1 bg-transparent font-mono text-[10.5px] font-semibold tracking-[0.02em] text-ink outline-none placeholder:text-ink-faint"
            />
            <button
              type="button"
              disabled={arpState === "busy"}
              onClick={() =>
                runArp((found) => {
                  const clean = formatMac(found || "")
                  if (clean && MAC_PATTERN.test(clean)) {
                    setMac(clean)
                    void api.saveMac(clean)
                    const hostLabel = serverDetails?.activeHost || SERVER_IP
                    notify(t("notify_arp_mac_saved", `ARP ${hostLabel} → ${clean} (Tersimpan)`), "info")
                  } else {
                    notify(t("notify_arp_mac_not_found", "MAC belum ditemukan di tabel ARP lokal"), "warning")
                  }
                })
              }
              className="h-[22px] px-2 flex items-center gap-1 rounded-full bg-info/10 hover:bg-info/20 text-info text-[9.5px] font-semibold transition cursor-pointer select-none"
            >
              <Radar className="size-3 shrink-0" />
              <span>{arpState === "busy" ? t("scanning_busy", "Memindai…") : t("detect_arp_btn", "Deteksi via ARP")}</span>
            </button>
          </div>

          <button
            type="button"
            disabled={!macValid || power === "rebooting" || wolState === "busy"}
            onClick={onWake}
            className={cx("h-[30px] w-full flex items-center justify-center gap-2 rounded-lg text-white text-[11px] font-semibold transition shadow-xs cursor-pointer select-none disabled:opacity-50 disabled:pointer-events-none", isOnline ? "bg-emerald-600 hover:bg-emerald-500" : "bg-[#E60004] hover:bg-[#C40003]")}
          >
            <Zap className="size-3.5 shrink-0" />
            <span>
              {power === "waking"
                ? t("waking_busy", "Menunggu server bangun…")
                : wolState === "busy"
                  ? t("sending_packet_busy", "Mengirim paket…")
                  : wolState === "done"
                    ? t("packet_sent_done", "Paket terkirim")
                    : t("send_wol_btn", "Kirim Magic Packet (WoL)")}
            </span>
          </button>

          <ul
            aria-label={t("hw_requirements_label", "Persyaratan perangkat keras")}
            className="flex flex-col gap-1.5 border-t border-line/60 pt-2"
          >
            {checklistItems.map((item) => {
              const checked = item.checked
              const Icon = checked ? CircleCheck : Circle
              return (
                <li key={item.key}>
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={checked}
                    onClick={() => handleToggleCheck(item.key)}
                    className="flex w-full items-start gap-2 rounded-md p-1 text-left transition hover:bg-surface-sunken/40 outline-none focus-visible:ring-2 focus-visible:ring-info/45 cursor-pointer"
                  >
                    <Icon
                      className={cx(
                        "size-3.5 mt-0.5 shrink-0",
                        checked ? "text-success" : (item.isAuto ? "text-warning" : "text-ink-faint")
                      )}
                      strokeWidth={2.2}
                      aria-hidden
                    />
                    <div className="flex flex-col min-w-0">
                      <span className={cx("text-[11px] font-medium leading-tight", !checked && "text-ink-subtle")}>
                        {item.label}
                      </span>
                      <span className={cx("text-[9.5px] leading-tight", checked ? "text-ink-muted" : (item.isAuto ? "text-warning-ink font-semibold" : "text-ink-faint"))}>
                        {item.desc}
                      </span>
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>

          {!isLanReady && (
            <div className="flex items-start gap-1.5 rounded-lg border border-warning-line/60 bg-warning-soft/20 p-1.5 text-[9.5px] text-warning-ink leading-tight">
              <AlertTriangle className="size-3 text-warning shrink-0 mt-0.5" />
              <span>{t("wol_wan_warning", "Rute saat ini adalah WAN/Domain. Paket Wake-on-LAN hanya dapat menjangkau server saat laptop berada di jaringan LAN lokal yang sama.")}</span>
            </div>
          )}
        </Card>
      </ViewBody>

      <FooterStatus
        showNoticePill={false}
        title={t("power_subsystem_title", "Subsistem Daya")}
        chips={
          <>
            <TrayChip>
              9 / UDP
            </TrayChip>
            <TrayChip>
              Broadcast
            </TrayChip>
            <TrayChip tone={ready ? "success" : "warning"}>
              {ready ? t("status_ready", "Siap") : (!isLanReady ? t("wol_status_need_lan", "Perlu LAN") : t("status_check", "Periksa"))}
            </TrayChip>
          </>
        }
      />
    </>
  )
}

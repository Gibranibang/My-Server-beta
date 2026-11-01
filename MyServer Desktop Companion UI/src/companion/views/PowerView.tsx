import { getTranslation } from "../i18n"
import { useEffect, useState } from "react"
import { Circle, CircleCheck, Power, Radar, RotateCw, ShieldAlert, Zap, AlertTriangle } from "lucide-react"
import { FooterStatus } from "../FlyoutShell"
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
            <p className="text-micro text-ink-subtle leading-relaxed">
              {t("admin_power_locked_desc", `Tombol Reboot & Shutdown hanya dapat dikendalikan oleh Administrator. Profil saat ini (${activeUser}) adalah akun pengguna standar.`)}
            </p>
            <div className="grid grid-cols-2 gap-2 pt-1 opacity-50 cursor-not-allowed">
              <Button variant="secondary" icon={RotateCw} block disabled size="sm">
                {t("reboot_locked", "Reboot (Terkunci)")}
              </Button>
              <Button variant="danger" icon={Power} block disabled size="sm">
                {t("shutdown_locked", "Shutdown (Terkunci)")}
              </Button>
            </div>
          </Card>
        ) : (
          <div className="flex flex-col gap-2">
            <Button
              variant="secondary"
              icon={RotateCw}
              block
              disabled={power === "offline" || power === "waking"}
              state={power === "rebooting" ? "busy" : "idle"}
              busyLabel={t("rebooting_busy", "Memulai ulang server…")}
              onClick={() => {
                if (!isOnline) return
                reboot()
                  .then(() =>
                    notify(t("reboot_sent_notice", "Perintah reboot dikirim ke server"), "warning"),
                  )
                  .catch((e) => notify(errorText(e), "danger"))
              }}
            >
              {t("reboot_server_btn", "Muat Ulang Server (Reboot)")}
            </Button>
            <Button
              variant="danger"
              icon={Power}
              block
              disabled={!isOnline}
              onClick={onShutdown}
              className={cx(confirming && "ring-4 ring-danger/25")}
            >
              {confirming
                ? t("confirm_click_again", "Klik lagi untuk konfirmasi")
                : power === "offline"
                  ? t("server_offline_status", "Server Mati")
                  : t("shutdown_server_btn", "Matikan Server (Shutdown)")}
            </Button>
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
              "flex h-9.5 items-center gap-2 rounded-control border bg-surface-sunken pr-1 pl-3 shadow-track transition-[border-color,box-shadow] focus-within:ring-2 focus-within:ring-info/15",
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
              className="min-w-0 flex-1 bg-transparent font-mono text-caption font-semibold tracking-[0.02em] text-ink outline-none placeholder:text-ink-faint"
            />
            <Button
              size="sm"
              variant="info"
              icon={Radar}
              className="px-2.5"
              state={arpState}
              busyLabel={t("scanning_busy", "Memindai…")}
              doneLabel={t("detected_done", "Terdeteksi")}
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
            >
              {t("detect_arp_btn", "Deteksi via ARP")}
            </Button>
          </div>

          <Button
            variant="primary"
            icon={Zap}
            block
            disabled={!macValid || power === "rebooting"}
            state={power === "waking" ? "busy" : wolState}
            busyLabel={
              power === "waking" ? t("waking_busy", "Menunggu server bangun…") : t("sending_packet_busy", "Mengirim paket…")
            }
            doneLabel={t("packet_sent_done", "Paket terkirim")}
            onClick={onWake}
          >
            {t("send_wol_btn", "Kirim Magic Packet (WoL)")}
          </Button>

          <ul
            aria-label={t("hw_requirements_label", "Persyaratan perangkat keras")}
            className="flex flex-col gap-2"
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
                    className="flex w-full items-start gap-2.5 rounded-control p-1 text-left transition hover:bg-surface-sunken/40 outline-none focus-visible:ring-2 focus-visible:ring-info/45 cursor-pointer"
                  >
                    <Icon
                      className={cx(
                        "size-4 mt-0.5 shrink-0",
                        checked ? "text-success" : (item.isAuto ? "text-warning" : "text-ink-faint")
                      )}
                      strokeWidth={2.2}
                      aria-hidden
                    />
                    <div className="flex flex-col min-w-0">
                      <span className={cx("text-caption font-medium", !checked && "text-ink-subtle")}>
                        {item.label}
                      </span>
                      <span className={cx("text-micro", checked ? "text-ink-muted" : (item.isAuto ? "text-warning-ink font-semibold" : "text-ink-faint"))}>
                        {item.desc}
                      </span>
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>

          {!isLanReady && (
            <div className="flex items-start gap-2 rounded-control border border-warning-line/60 bg-warning-soft/20 p-2 text-micro text-warning-ink leading-relaxed">
              <AlertTriangle className="size-3.5 text-warning shrink-0 mt-0.5" />
              <span>{t("wol_wan_warning", "Rute saat ini adalah WAN/Domain. Paket Wake-on-LAN hanya dapat menjangkau server saat laptop berada di jaringan LAN lokal yang sama.")}</span>
            </div>
          )}
        </Card>
      </ViewBody>

      <FooterStatus
        title={t("power_subsystem_title", "Power Subsystem")}
        chips={
          <>
            <Chip>
              <span>
                {t("port_label", "Port")}: <Mono>9</Mono> UDP
              </span>
            </Chip>
            <Chip>{t("target_broadcast", "Target: Broadcast")}</Chip>
            <Chip tone={ready ? "success" : "warning"}>
              {t("status_label", "Status")}: {ready ? t("status_ready", "Ready") : (!isLanReady ? t("wol_status_need_lan", "Need LAN") : t("status_check", "Check"))}
            </Chip>
          </>
        }
      />
    </>
  )
}

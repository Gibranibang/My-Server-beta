import { getTranslation } from "../i18n"
import { useEffect, useRef, useState } from "react"
import {
  Check,
  ChevronRight,
  Copy,
  Edit2,
  ExternalLink,
  Globe,
  KeyRound,
  Eye,
  EyeOff,
  MoreVertical,
  Network,
  Plus,
  Radio,
  RefreshCw,
  Server,
  Trash2,
  User,
  Wifi,
  X,
  Zap,
} from "lucide-react"
import { FooterStatus, TrayChip } from "../FlyoutShell"
import { getCompanionApi } from "../api"
import { errorText, useCompanion, useNotice } from "../store"
import { Button, Card, Chip, IconBadge, Mono, SectionLabel, StatusDot, cx } from "../ui"
import type { ServerDetails, ServerRoute } from "../types"
import type { ViewProps } from "./shared"
import { ViewBody } from "./shared"

export default function ServerView({ go }: ViewProps) {
  const api = getCompanionApi()
  const { isOnline, settings, startTransition, endTransition, runWithTransition } = useCompanion()
  const t = getTranslation(settings?.language)
  const { notify } = useNotice()
  const [details, setDetails] = useState<ServerDetails | null>(null)
  const [switching, setSwitching] = useState<string | null>(null)
  const [routeMenuOpenId, setRouteMenuOpenId] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)

  const loadDetails = () => {
    api
      .getServerDetails()
      .then((data) => {
        setDetails(data)
      })
      .catch((e) => {
        notify(errorText(e), "danger")
      })
  }

  useEffect(() => {
    loadDetails()
    window.addEventListener("myserver:refresh", loadDetails)
    return () => window.removeEventListener("myserver:refresh", loadDetails)
  }, [])

  // Auto-close inline route menu when clicking outside
  useEffect(() => {
    if (!routeMenuOpenId) return
    const onMouseDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setRouteMenuOpenId(null)
      }
    }
    document.addEventListener("mousedown", onMouseDown)
    return () => document.removeEventListener("mousedown", onMouseDown)
  }, [routeMenuOpenId])

  const copyText = async (text: string, label: string) => {
    if (!text) return
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const textArea = document.createElement("textarea")
        textArea.value = text
        document.body.appendChild(textArea)
        textArea.select()
        document.execCommand("copy")
        document.body.removeChild(textArea)
      }
      notify(`${label} ${t("copied_notice", "copied to clipboard!")}`, "success")
    } catch {
      notify(`${t("copy_failed_notice", "Failed to copy")} ${label}.`, "danger")
    }
  }

  const onSwitchRoute = (route: { id: string; name: string; url: string; active?: boolean }) => {
    if (route.active) return
    setSwitching(route.id)
    runWithTransition(
      t("switching_route_title", "Beralih Rute..."),
      t("switching_route_desc", "Menghubungkan ke jalur akses server..."),
      async () => {
        const updated = await api.switchRoute(route.id)
        setDetails(updated)
        setSwitching(null)
        window.dispatchEvent(new CustomEvent("myserver:refresh"))
        notify(`${t("route_switched_notice", "Access route switched to: ")}${route.name}`, "success")
        return updated
      },
      { resetMetrics: false }
    ).catch((e) => {
      setSwitching(null)
      notify(errorText(e), "danger")
    })
  }

  const onSwitchProfile = (profile: string) => {
    if (details?.activeProfile === profile) return
    runWithTransition(
      t("switching_profile_title", "Beralih Profil Akun..."),
      t("switching_profile_desc", "Memasang penyimpanan share akun..."),
      async () => {
        const updated = await api.switchProfile(profile)
        setDetails(updated)
        window.dispatchEvent(new CustomEvent("myserver:refresh"))
        notify(t("switched_profile_notice", "Beralih ke profil: ") + profile, "success")
        return updated
      },
      { resetMetrics: false }
    ).catch((e) => notify(errorText(e), "danger"))
  }

  const onSwitchServer = (serverId: string) => {
    if (details?.serverId === serverId) return
    runWithTransition(
      t("switching_server_title", "Beralih Server..."),
      t("switching_server_desc", "Menghubungkan dan menyinkronkan status server..."),
      async () => {
        const updated = await api.switchServer(serverId)
        setDetails(updated)
        window.dispatchEvent(new CustomEvent("myserver:refresh"))
        notify(t("switched_server_notice", "Beralih ke server: ") + updated.serverName, "success")
        return updated
      },
      { resetMetrics: true }
    ).catch((e) => notify(errorText(e), "danger"))
  }

  // ============================================================================
  // REACT MODALS STATE & HANDLERS (Pengganti Native WinForms)
  // ============================================================================
  const [modalMode, setModalMode] = useState<null | "addServer" | "editServer" | "deleteServer" | "addRoute" | "editRoute" | "deleteRoute" | "addProfile" | "editProfile" | "deleteProfile" | "credentials" | "joinZeroTier">(null)
  const [activeItem, setActiveItem] = useState<any>(null)
  const [formName, setFormName] = useState("")
  const [formUrl, setFormUrl] = useState("")
  const [formUser, setFormUser] = useState("")
  const [formPass, setFormPass] = useState("")
  const [formNwid, setFormNwid] = useState("")
  const [formVip, setFormVip] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  const closeModal = () => {
    setModalMode(null)
    setActiveItem(null)
    setFormName("")
    setFormUrl("")
    setFormUser("")
    setFormPass("")
    setFormNwid("")
    setFormVip("")
    setIsSubmitting(false)
    setShowPassword(false)
  }

  const onAddServer = () => {
    setFormName("")
    setFormUrl("http://")
    setFormUser("Admin")
    setFormPass("")
    setFormNwid("")
    setFormVip("")
    setModalMode("addServer")
  }

  const onEditServer = () => {
    const cur = details?.servers?.find(s => s.id === details?.serverId) || { name: details?.serverName || "" }
    setActiveItem(cur)
    setFormName(cur.name || "")
    setFormUrl(activeRouteObj?.url || "")
    setFormNwid(details?.zeroTier?.configuredNwid || "")
    setFormVip(details?.zeroTier?.serverVirtualIp || "")
    setModalMode("editServer")
  }

  const onDeleteServer = () => {
    const cur = details?.servers?.find(s => s.id === details?.serverId) || { id: details?.serverId, name: details?.serverName || "Server" }
    setActiveItem(cur)
    setModalMode("deleteServer")
  }

  const onAddRoute = () => {
    setFormName("")
    setFormUrl("http://")
    setModalMode("addRoute")
  }

  const onEditRoute = (routeId: string) => {
    const target = routes.find(r => r.id === routeId)
    if (target) {
      setActiveItem(target)
      setFormName(target.name)
      setFormUrl(target.url)
      setModalMode("editRoute")
    }
  }

  const onDeleteRoute = (routeId: string) => {
    const target = routes.find(r => r.id === routeId)
    if (target) {
      setActiveItem(target)
      setModalMode("deleteRoute")
    }
  }

  const onAddProfile = () => {
    const nextNum = (details?.profiles?.length || 0) + 1
    setFormName(`User-${nextNum}`)
    setFormUser("")
    setFormPass("")
    setModalMode("addProfile")
  }

  const onEditProfile = () => {
    const act = details?.activeProfile || "Admin"
    setActiveItem({ name: act })
    setFormName(act)
    setModalMode("editProfile")
  }

  const onDeleteProfile = () => {
    const act = details?.activeProfile || "Admin"
    setActiveItem({ name: act })
    setModalMode("deleteProfile")
  }

  const onConfigCredentials = () => {
    const act = details?.activeProfile || "Admin"
    setActiveItem({ name: act })
    setFormName(act)
    setFormUser(details?.accountStatus?.username || (act !== "Admin" ? act : ""))
    setFormPass("")
    setModalMode("credentials")
  }

  const onConnectEasyTier = async () => {
    setIsSubmitting(true)
    try {
      const rid = details?.easyTier?.remote_id || details?.zeroTier?.configuredNwid || ""
      if (!rid) {
        onJoinZeroTier()
        return
      }
      const res = await api.startEasyTier?.({ remote_id: rid })
      if (res?.success) {
        notify(t("easytier_connected_notice", "EasyTier berhasil terhubung"), "success")
        loadDetails()
      } else {
        notify(res?.message || "Gagal menghubungkan EasyTier", "danger")
      }
    } catch (err: any) {
      notify(err?.message || "Terjadi kesalahan EasyTier", "danger")
    } finally {
      setIsSubmitting(false)
    }
  }

  const onDisconnectEasyTier = async () => {
    setIsSubmitting(true)
    try {
      const res = await api.stopEasyTier?.()
      if (res?.success) {
        notify(t("easytier_disconnected_notice", "EasyTier diputuskan"), "neutral")
        loadDetails()
      } else {
        notify(res?.message || "Gagal memutuskan EasyTier", "danger")
      }
    } catch (err: any) {
      notify(err?.message || "Terjadi kesalahan EasyTier", "danger")
    } finally {
      setIsSubmitting(false)
    }
  }

  const onConnectZeroTier = async () => {
    const nwid = details?.zeroTier?.configuredNwid || details?.easyTier?.remote_id || ""
    if (!nwid) {
      onJoinZeroTier()
      return
    }
    setIsSubmitting(true)
    try {
      const res = await api.joinZeroTierNetwork(nwid)
      if (res?.success !== false) {
        notify(t("zt_connected_notice", "ZeroTier berhasil terhubung"), "success")
        loadDetails()
      } else {
        notify(res?.message || "Gagal menghubungkan ZeroTier", "danger")
      }
    } catch (err: any) {
      notify(err?.message || "Terjadi kesalahan ZeroTier", "danger")
    } finally {
      setIsSubmitting(false)
    }
  }

  const onDisconnectZeroTier = async () => {
    const nwid = details?.zeroTier?.configuredNwid || ""
    setIsSubmitting(true)
    try {
      const res = await api.leaveZeroTierNetwork(nwid)
      if (res?.success !== false) {
        notify(t("zt_disconnected_notice", "ZeroTier diputuskan"), "neutral")
        loadDetails()
      } else {
        notify(res?.message || "Gagal memutuskan ZeroTier", "danger")
      }
    } catch (err: any) {
      notify(err?.message || "Terjadi kesalahan ZeroTier", "danger")
    } finally {
      setIsSubmitting(false)
    }
  }

  const onSetRemoteMode = async (mode: "auto" | "easytier" | "zerotier") => {
    try {
      const res = await api.setRemoteMode?.(mode)
      if (res?.success !== false) {
        notify(t("remote_mode_updated", `Mode failover remote: ${mode}`), "info")
        loadDetails()
      }
    } catch (err: any) {
      notify(err?.message || "Gagal mengubah mode remote", "danger")
    }
  }

  const onJoinZeroTier = () => {
    setFormNwid(details?.zeroTier?.configuredNwid || "")
    setModalMode("joinZeroTier")
  }

  const handleSaveModal = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    try {
      if (modalMode === "addServer") {
        const res = await api.saveServer({ name: formName, url: formUrl, username: formUser, password: formPass, zerotierNetworkId: formNwid, zerotierVirtualIp: formVip })
        if (res?.success === false) throw new Error(res.message || "Gagal menyimpan server")
        notify(t("server_added_notice", "Server baru berhasil ditambahkan"), "success")
      } else if (modalMode === "editServer") {
        const res = await api.saveServer({ id: activeItem?.id || details?.serverId, name: formName, url: formUrl, zerotierNetworkId: formNwid, zerotierVirtualIp: formVip })
        if (res?.success === false) throw new Error(res.message || "Gagal memperbarui server")
        notify(t("server_updated_notice", "Server berhasil diperbarui"), "success")
      } else if (modalMode === "deleteServer") {
        const res = await api.removeServer({ id: activeItem?.id || details?.serverId })
        if (res?.success === false) throw new Error(res.message || "Gagal menghapus server")
        notify(t("server_deleted_notice", "Server berhasil dihapus"), "info")
      } else if (modalMode === "addRoute") {
        const res = await api.saveRoute({ name: formName, url: formUrl })
        if (res?.success === false) throw new Error(res.message || "Gagal menambah rute")
        notify(t("route_added_notice", "Rute berhasil ditambahkan"), "success")
      } else if (modalMode === "editRoute") {
        const res = await api.saveRoute({ id: activeItem?.id, name: formName, url: formUrl })
        if (res?.success === false) throw new Error(res.message || "Gagal memperbarui rute")
        notify(t("route_updated_notice", "Rute berhasil diperbarui"), "success")
      } else if (modalMode === "deleteRoute") {
        const res = await api.removeRoute({ id: activeItem?.id })
        if (res?.success === false) throw new Error(res.message || "Gagal menghapus rute")
        notify(t("route_deleted_notice", "Rute berhasil dihapus"), "info")
      } else if (modalMode === "addProfile") {
        const res = await api.saveProfile({ profileName: formName, username: formUser, password: formPass })
        if (res?.success === false) throw new Error(res.message || "Gagal menambah akun")
        notify(t("profile_added_notice", "Akun berhasil ditambahkan"), "success")
      } else if (modalMode === "editProfile") {
        const res = await api.saveProfile({ oldProfileName: activeItem?.name, profileName: formName })
        if (res?.success === false) throw new Error(res.message || "Gagal mengubah nama akun")
        notify(t("profile_updated_notice", "Nama akun berhasil diubah"), "success")
      } else if (modalMode === "deleteProfile") {
        const res = await api.removeProfile({ profileName: activeItem?.name })
        if (res?.success === false) throw new Error(res.message || "Gagal menghapus akun")
        notify(t("profile_deleted_notice", "Akun berhasil dihapus"), "info")
      } else if (modalMode === "credentials") {
        const res = await api.saveProfile({ oldProfileName: activeItem?.name, profileName: activeItem?.name, username: formUser, password: formPass })
        if (res?.success === false) throw new Error(res.message || "Gagal memperbarui kredensial")
        notify(t("creds_updated_notice", "Kredensial berhasil diperbarui"), "success")
      } else if (modalMode === "joinZeroTier") {
        const cleanNwid = formNwid.trim().toLowerCase()
        const res = await api.joinZeroTierNetwork(cleanNwid)
        if (res?.success === false) throw new Error(res.message || "Gagal menyambung ZeroTier")
        if (api.startEasyTier && cleanNwid) {
          try {
            await api.startEasyTier({ remote_id: cleanNwid })
          } catch (_) {}
        }
        notify(t("zt_join_sent_notice", "Perintah sambung Remote ID berhasil dikirim"), "success")
      }
      closeModal()
      loadDetails()
      window.dispatchEvent(new CustomEvent("myserver:refresh"))
    } catch (err: any) {
      notify(err?.message || "Terjadi kesalahan", "danger")
    } finally {
      setIsSubmitting(false)
    }
  }

  const routes = details?.routes || []
  const activeRouteObj = routes.find((r) => r.active)
  const isAutoActive = details?.activeRoute === "auto"

  return (
    <>
      <ViewBody>
        {/* 1. KARTU UTAMA SERVER & MULTI-SERVER */}
        <Card className="flex flex-col gap-2.5 p-3.5 shadow-card">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <span className="inline-flex size-9 items-center justify-center rounded-tile border border-line bg-surface-sunken text-brand shadow-tile">
                <Server className="size-5" strokeWidth={2.2} aria-hidden />
              </span>
              <div>
                <h3 className="text-[13px] font-semibold text-ink">
                  {details?.serverName || "Memuat..."}
                </h3>
                <p className="text-micro text-ink-subtle">
                  {t("route_prefix", "Jalur:")}{" "}
                  <span className="font-semibold text-ink-muted">
                    {isAutoActive ? t("route_auto_resolve", "Otomatis") : activeRouteObj?.name || t("route_auto_resolve", "Otomatis")}
                  </span>
                </p>
              </div>
            </div>
            <Chip tone={isOnline ? "success" : "neutral"} size="sm">
              <StatusDot tone={isOnline ? "success" : "neutral"} />
              {isOnline ? t("status_online", "Online") : t("status_offline", "Offline")}
            </Chip>
          </div>

          {/* Multi-Server Switcher Pills */}
          {details?.servers && details.servers.length > 1 && (
            <div className="flex items-center gap-1 overflow-x-auto scrollbar-none border-t border-line pt-2">
              <span className="text-[10px] font-medium text-ink-muted shrink-0 mr-0.5">{t("select_prefix", "Pilih:")}</span>
              {details.servers.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => onSwitchServer(s.id)}
                  className={cx(
                    "rounded-full px-2 py-0.5 text-[9.5px] font-semibold transition-colors cursor-pointer shrink-0 whitespace-nowrap",
                    s.active
                      ? "bg-brand text-brand-ink font-bold shadow-xs border border-brand/40"
                      : "bg-surface-sunken text-ink-muted hover:bg-line hover:text-ink border border-line"
                  )}
                >
                  {s.name}
                </button>
              ))}
            </div>
          )}

          {/* Baris Aksi Server: Tambah, Ubah, Hapus (Grid 3-Kolom Simetris v3.12.1) */}
          <div className="grid grid-cols-3 gap-1.5 border-t border-line pt-2">
            <button
              type="button"
              onClick={onAddServer}
              className="h-[25px] px-1 flex items-center justify-center gap-1 rounded-full bg-surface-muted hover:bg-line text-ink-soft text-[10px] font-medium transition cursor-pointer select-none"
            >
              <Plus className="size-3.5 shrink-0 stroke-[2.4]" aria-hidden />
              <span className="truncate">{t("srv_add_btn", "Add")}</span>
            </button>
            <button
              type="button"
              onClick={onEditServer}
              className="h-[25px] px-1 flex items-center justify-center gap-1 rounded-full bg-surface-muted hover:bg-line text-ink-soft text-[10px] font-medium transition cursor-pointer select-none"
            >
              <Edit2 className="size-3.5 shrink-0 stroke-[2]" aria-hidden />
              <span className="truncate">{t("srv_edit_btn", "Edit")}</span>
            </button>
            <button
              type="button"
              disabled={!details?.servers || details.servers.length <= 1}
              onClick={onDeleteServer}
              className="h-[25px] px-1 flex items-center justify-center gap-1 rounded-full bg-surface-muted hover:bg-line text-ink-soft text-[10px] font-medium transition cursor-pointer select-none disabled:opacity-45 disabled:pointer-events-none"
            >
              <Trash2 className="size-3.5 shrink-0 stroke-[2]" aria-hidden />
              <span className="truncate">{t("srv_del_btn", "Delete")}</span>
            </button>
          </div>
        </Card>

        {/* 2. KARTU REMOTE ACCESS DINAMIS TUNGGAL (EASYTIER / ZEROTIER) */}
        {(() => {
          const activeRemoteEngine = 
            details?.remoteMode === "easytier" 
              ? "easytier" 
              : details?.remoteMode === "zerotier" 
                ? "zerotier" 
                : (details?.activeRemoteEngine === "easytier" || (details?.easyTier?.running && !details?.zeroTier?.running) ? "easytier" : "zerotier");

          return (
            <section aria-label="Remote Access" className="flex flex-col gap-2">
              <div className="flex items-center justify-between px-1">
                <span className="text-[10px] font-bold tracking-wider text-ink-muted uppercase truncate">
                  {activeRemoteEngine === "easytier" 
                    ? t("easytier_p2p_title", "EasyTier Remote Access (P2P)")
                    : t("zerotier_p2p_title", "ZeroTier Remote Access (P2P)")}
                </span>
                <div className="flex items-center gap-1 bg-surface-sunken p-0.5 rounded-full border border-line text-nano">
                  <button
                    type="button"
                    onClick={() => onSetRemoteMode("auto")}
                    className={cx(
                      "px-2 py-0.5 rounded-full font-semibold transition cursor-pointer select-none",
                      (details?.remoteMode || "auto") === "auto" ? "bg-brand text-surface shadow-xs" : "text-ink-subtle hover:text-ink"
                    )}
                  >
                    Auto
                  </button>
                  <button
                    type="button"
                    onClick={() => onSetRemoteMode("easytier")}
                    className={cx(
                      "px-2 py-0.5 rounded-full font-semibold transition cursor-pointer select-none",
                      details?.remoteMode === "easytier" ? "bg-brand text-surface shadow-xs" : "text-ink-subtle hover:text-ink"
                    )}
                  >
                    EasyTier
                  </button>
                  <button
                    type="button"
                    onClick={() => onSetRemoteMode("zerotier")}
                    className={cx(
                      "px-2 py-0.5 rounded-full font-semibold transition cursor-pointer select-none",
                      details?.remoteMode === "zerotier" ? "bg-brand text-surface shadow-xs" : "text-ink-subtle hover:text-ink"
                    )}
                  >
                    ZeroTier
                  </button>
                </div>
              </div>

              {activeRemoteEngine === "easytier" ? (
                /* KARTU EASYTIER TUNGGAL */
                <Card className="flex flex-col gap-2.5 p-3 overflow-hidden">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <IconBadge
                        icon={Network}
                        tone={
                          details?.easyTier?.running
                            ? (details?.easyTier?.peers_count > 0 ? "success" : "warning")
                            : "neutral"
                        }
                        size="sm"
                      />
                      <div className="min-w-0">
                        <div className="text-label font-semibold text-ink truncate">
                          {details?.easyTier?.network_name || "EasyTier P2P Mesh"}
                        </div>
                        <div className="text-micro text-ink-subtle truncate">
                          {t("status_label", "Status:")}{" "}
                          <span className="font-semibold text-ink-muted">
                            {details?.easyTier?.running
                              ? (details?.easyTier?.peers_count > 0
                                  ? `${details.easyTier.peers_count} Node Peer Aktif`
                                  : "Menghubungkan Relay...")
                              : t("easytier_status_disconnected", "Terputus")}
                          </span>
                        </div>
                      </div>
                    </div>
                    <Chip
                      size="sm"
                      tone={
                        details?.easyTier?.running
                          ? (details?.easyTier?.peers_count > 0 ? "success" : "warning")
                          : "neutral"
                      }
                    >
                      <StatusDot
                        tone={
                          details?.easyTier?.running
                            ? (details?.easyTier?.peers_count > 0 ? "success" : "warning")
                            : "neutral"
                        }
                      />
                      {details?.easyTier?.running
                        ? (details?.easyTier?.peers_count > 0 ? "Direct P2P" : "Relay")
                        : t("status_disabled_zt", "Nonaktif")}
                    </Chip>
                  </div>

                  <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-nano border-t border-line pt-2 text-ink-subtle">
                    <div className="flex items-center gap-1 min-w-0">
                      <span className="shrink-0 text-ink-subtle">Remote ID:</span>
                      <Mono className="font-semibold text-ink truncate text-[9.5px]">
                        {details?.easyTier?.remote_id || details?.zeroTier?.configuredNwid || "–"}
                      </Mono>
                      {(details?.easyTier?.remote_id || details?.zeroTier?.configuredNwid) && (
                        <button
                          type="button"
                          onClick={() => copyText(details?.easyTier?.remote_id || details?.zeroTier?.configuredNwid || "", "Remote ID")}
                          className="shrink-0 rounded p-0.5 text-ink-subtle hover:text-ink transition cursor-pointer"
                          title={t("copy_node_id", "Salin Remote ID")}
                          aria-label={t("copy_node_id", "Salin Remote ID")}
                        >
                          <Copy className="size-2.5 text-ink-muted hover:text-ink" />
                        </button>
                      )}
                    </div>
                    <div className="flex items-center justify-end gap-1 min-w-0 text-right">
                      <span className="shrink-0 text-ink-subtle">Laptop IP:</span>
                      <Mono className="text-ink text-[9.5px] truncate">
                        {details?.easyTier?.virtual_ipv4 || details?.easyTier?.virtual_ip || (details?.easyTier?.running ? "10.126.126.2" : "–")}
                      </Mono>
                    </div>
                    {(details?.easyTier?.server_peer_ip || details?.easyTier?.running) && (
                      <div className="col-span-2 flex items-center justify-between text-nano border-t border-line/40 pt-1">
                        <span className="text-ink-subtle">Server IP:</span>
                        <Mono className="text-ink font-semibold text-[9.5px]">
                          {details?.easyTier?.server_peer_ip || "10.126.126.1"}
                        </Mono>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2 pt-1 w-full min-w-0">
                    {details?.easyTier?.running ? (
                      <Button
                        size="sm"
                        variant="soft"
                        icon={Network}
                        className="flex-1 min-w-0 truncate"
                        disabled={isSubmitting}
                        onClick={onDisconnectEasyTier}
                      >
                        {t("easytier_btn_disconnect", "Putuskan EasyTier")}
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="primary"
                        icon={Network}
                        className="flex-1 min-w-0 truncate"
                        disabled={isSubmitting}
                        onClick={onConnectEasyTier}
                      >
                        {t("easytier_btn_connect", "Hubungkan EasyTier")}
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="soft"
                      icon={Edit2}
                      className="shrink-0 w-8 px-0 flex items-center justify-center"
                      onClick={onJoinZeroTier}
                      title={t("edit_remote_id", "Ubah Remote ID")}
                      aria-label={t("edit_remote_id", "Ubah Remote ID")}
                    />
                  </div>
                </Card>
              ) : (
                /* KARTU ZEROTIER TUNGGAL */
                <Card className="flex flex-col gap-2.5 p-3 overflow-hidden">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <IconBadge
                        icon={Network}
                        tone={
                          details?.zeroTier?.running && (details?.zeroTier?.networkStatus === "OK" || (!details?.zeroTier?.configuredNwid && details?.zeroTier?.running))
                            ? "success"
                            : details?.zeroTier?.running
                            ? "warning"
                            : "neutral"
                        }
                        size="sm"
                      />
                      <div className="min-w-0">
                        <div className="text-label font-semibold text-ink truncate">
                          {details?.zeroTier?.networkName || (details?.zeroTier?.configuredNwid ? `Network ${details.zeroTier.configuredNwid}` : t("zt_one_net", "ZeroTier One Network"))}
                        </div>
                        <div className="text-micro text-ink-subtle truncate">
                          {t("status_label", "Status:")}{" "}
                          <span className="font-semibold text-ink-muted">
                            {details?.zeroTier?.configuredNwid && details?.zeroTier?.joined === false
                              ? t("zt_not_connected", "Belum Terhubung")
                              : details?.zeroTier?.networkStatus || (details?.zeroTier?.running ? "OK" : t("status_offline", "Offline"))}
                          </span>
                        </div>
                      </div>
                    </div>
                    <Chip
                      size="sm"
                      tone={
                        details?.zeroTier?.running && (details?.zeroTier?.networkStatus === "OK" || (!details?.zeroTier?.configuredNwid && details?.zeroTier?.running))
                          ? "success"
                          : details?.zeroTier?.running
                          ? "warning"
                          : "neutral"
                      }
                    >
                      <StatusDot
                        tone={
                          details?.zeroTier?.running && (details?.zeroTier?.networkStatus === "OK" || (!details?.zeroTier?.configuredNwid && details?.zeroTier?.running))
                            ? "success"
                            : details?.zeroTier?.running
                            ? "warning"
                            : "neutral"
                        }
                      />
                      {details?.zeroTier?.running
                        ? details?.zeroTier?.networkStatus === "OK" || (!details?.zeroTier?.configuredNwid && details?.zeroTier?.running)
                          ? t("status_active_zt", "Aktif")
                          : t("status_connecting_zt", "Menghubungkan")
                        : t("status_disabled_zt", "Nonaktif")}
                    </Chip>
                  </div>

                  <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-nano border-t border-line pt-2 text-ink-subtle">
                    <div className="flex items-center gap-1 min-w-0">
                      <span className="shrink-0 text-ink-subtle">Node ID:</span>
                      <Mono className="font-semibold text-ink truncate text-[9.5px]">{details?.zeroTier?.nodeId || "–"}</Mono>
                      {details?.zeroTier?.nodeId && (
                        <button
                          type="button"
                          onClick={() => copyText(details.zeroTier!.nodeId, "Node ID ZeroTier")}
                          className="shrink-0 rounded p-0.5 text-ink-subtle hover:text-ink transition cursor-pointer"
                          title={t("copy_node_id", "Salin Node ID")}
                          aria-label={t("copy_node_id", "Salin Node ID")}
                        >
                          <Copy className="size-2.5 text-ink-muted hover:text-ink" />
                        </button>
                      )}
                    </div>
                    <div className="flex items-center justify-end gap-1 min-w-0 text-right">
                      <span className="shrink-0 text-ink-subtle">Laptop IP:</span>
                      <Mono className="text-ink text-[9.5px] truncate">{details?.zeroTier?.virtualIp || "–"}</Mono>
                    </div>
                    {details?.zeroTier?.serverVirtualIp && (
                      <div className="col-span-2 flex items-center justify-between text-nano border-t border-line/40 pt-1">
                        <span className="text-ink-subtle">Server IP:</span>
                        <Mono className="text-ink font-semibold text-[9.5px]">{details.zeroTier.serverVirtualIp}</Mono>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2 pt-1 w-full min-w-0">
                    {details?.zeroTier?.running && details?.zeroTier?.joined !== false ? (
                      <Button
                        size="sm"
                        variant="soft"
                        icon={Network}
                        className="flex-1 min-w-0 truncate"
                        disabled={isSubmitting}
                        onClick={onDisconnectZeroTier}
                      >
                        {t("zt_btn_disconnect", "Putuskan ZeroTier")}
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="primary"
                        icon={Network}
                        className="flex-1 min-w-0 truncate"
                        disabled={isSubmitting}
                        onClick={onConnectZeroTier}
                      >
                        {t("zt_btn_connect", "Hubungkan ZeroTier")}
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="soft"
                      icon={Edit2}
                      className="shrink-0 w-8 px-0 flex items-center justify-center"
                      onClick={onJoinZeroTier}
                      title={t("edit_network_id", "Ubah Network ID")}
                      aria-label={t("edit_network_id", "Ubah Network ID")}
                    />
                  </div>
                </Card>
              )}
            </section>
          );
        })()}

        {/* 3. PILIHAN RUTE JARINGAN (AUTO FAILOVER) */}
        <section aria-label="Rute Jaringan" className="flex flex-col gap-2">
          <div className="flex items-center justify-between pl-1">
            <SectionLabel trailing={`${routes.length} ${t("routes_available_trailing", "jalur tersedia")}`}>
              {t("network_routes_title", "Pilihan Rute Jaringan")}
            </SectionLabel>
            <Button
              size="sm"
              variant="soft"
              icon={Plus}
              onClick={onAddRoute}
            >{t("add_route_btn", "Add Route")}</Button>
          </div>

          <div className="flex flex-col gap-1.5">
            {/* Opsi Khusus: {t("auto_failover_label", "Auto Failover (Jalur Otomatis)")} */}
            <button
              type="button"
              disabled={isAutoActive}
              onClick={() => onSwitchRoute({ id: "auto", name: "Auto Failover", url: "", active: isAutoActive })}
              className={cx(
                "group flex w-full items-center justify-between rounded-tile border p-2.5 text-left transition-[border-color,background-color] duration-150 outline-none cursor-pointer",
                isAutoActive
                  ? "border-2 border-brand bg-surface shadow-tile"
                  : "border border-line bg-surface hover:border-line-strong hover:bg-surface-sunken"
              )}
            >
              <div className="flex items-center gap-3">
                <IconBadge
                  icon={Zap}
                  tone={isAutoActive ? "success" : "info"}
                  size="sm"
                />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-label font-semibold text-ink">
                      {t("auto_failover_label", "Auto Failover (Jalur Otomatis)")}
                    </span>
                    {isAutoActive && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-brand/15 px-2 py-0.5 text-nano font-bold text-brand uppercase">
                        <Check className="size-2.5" strokeWidth={3} /> {t("status_active", "Active")}
                      </span>
                    )}
                  </div>
                  <span className="text-micro text-ink-subtle">
                    {t("auto_failover_desc", "Pilih jalur tercepat otomatis (LAN / Remote / WAN)")}
                  </span>
                </div>
              </div>
              {!isAutoActive && (
                <ChevronRight
                  className="size-4 text-ink-faint transition-transform group-hover:translate-x-0.5"
                  aria-hidden
                />
              )}
            </button>

            {/* Daftar Rute Spesifik */}
            {routes.map((route) => {
              const Icon = route.isZeroTier ? Network : route.url.includes("https") ? Globe : Wifi
              const isSwitchingThis = switching === route.id
              const isMenuOpen = routeMenuOpenId === route.id

              return (
                <div
                  key={route.id}
                  className={cx(
                    "rounded-tile border transition-[border-color,background-color] duration-150",
                    route.active && !isAutoActive
                      ? "border-2 border-brand bg-surface shadow-tile"
                      : "border border-line bg-surface hover:border-line-strong hover:bg-surface-sunken"
                  )}
                >
                  <div
                    onClick={() => onSwitchRoute(route)}
                    className="flex w-full items-center justify-between p-2.5 cursor-pointer outline-none"
                  >
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <IconBadge
                        icon={Icon}
                        tone={route.active && !isAutoActive ? "success" : route.isZeroTier ? "info" : "neutral"}
                        size="sm"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-label font-semibold text-ink truncate">
                            {route.name}
                          </span>
                          {route.isZeroTier && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-info-ink/15 px-1.5 py-0.2 text-nano font-bold text-info-ink uppercase shrink-0">
                              P2P
                            </span>
                          )}
                          {route.active && !isAutoActive && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-brand/15 px-2 py-0.5 text-nano font-bold text-brand uppercase shrink-0">
                              <Check className="size-2.5" strokeWidth={3} /> {t("status_active", "Active")}
                            </span>
                          )}
                        </div>
                        <Mono className="text-micro text-ink-subtle truncate block">{route.url}</Mono>
                      </div>
                    </div>

                    <div className="flex items-center gap-1 shrink-0 ml-1">
                      {typeof route.pingMs === "number" && (
                        <span className="font-mono text-micro text-ink-subtle mr-0.5 shrink-0 whitespace-nowrap">
                          {route.pingMs} ms
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          setRouteMenuOpenId(isMenuOpen ? null : route.id)
                        }}
                        className="rounded-md p-1 text-ink-subtle hover:bg-surface-sunken hover:text-ink transition cursor-pointer"
                        title={t("options_route_title", `Opsi ${route.name}`)}
                        aria-label={t("options_route_title", `Opsi ${route.name}`)}
                      >
                        <MoreVertical className="size-4" />
                      </button>
                    </div>
                  </div>

                  {/* Auto-Layout Inline Action Panel (Zero Clipping) */}
                  {isMenuOpen && (
                    <div
                      ref={menuRef}
                      className="mx-2 mb-2 flex flex-col gap-1 rounded-xl border border-line bg-surface-sunken/90 p-2 shadow-sm animate-in fade-in duration-150"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center justify-between px-1.5 py-0.5 border-b border-line mb-0.5">
                        <span className="text-nano font-bold uppercase tracking-wider text-ink-subtle truncate">
                          {t("options_route_panel", `Opsi Rute ${route.name}`)}
                        </span>
                        <button
                          type="button"
                          onClick={() => setRouteMenuOpenId(null)}
                          className="rounded p-0.5 text-ink-subtle hover:text-ink transition cursor-pointer"
                          aria-label={t("close_options_menu", "Tutup menu opsi")}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          setRouteMenuOpenId(null)
                          onEditRoute(route.id)
                        }}
                        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-micro font-medium text-ink hover:bg-surface transition cursor-pointer text-left"
                      >
                        <Edit2 className="h-3 w-3 text-info-ink shrink-0" />
                        <span className="truncate">{t("edit_route_btn", "Ubah Rute")}</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setRouteMenuOpenId(null)
                          copyText(route.url, `URL ${route.name}`)
                        }}
                        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-micro font-medium text-ink hover:bg-surface transition cursor-pointer text-left"
                      >
                        <Copy className="h-3 w-3 text-ink-muted shrink-0" />
                        <span className="truncate">{t("copy_url_btn", "Salin URL")}</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setRouteMenuOpenId(null)
                          onDeleteRoute(route.id)
                        }}
                        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-micro font-medium text-danger-ink hover:bg-danger-ink/10 transition cursor-pointer text-left border-t border-line pt-1"
                      >
                        <Trash2 className="h-3 w-3 shrink-0" />
                        <span className="truncate">{t("delete_route_btn", "Hapus Rute")}</span>
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </section>

        {/* 4. PROFIL AKUN & KREDENSIAL */}
        <section aria-label="Profil Akun" className="flex flex-col gap-2">
          <SectionLabel trailing={details?.activeProfile ? `Login: ${details.activeProfile}` : undefined}>
            {t("account_profiles_sec", "Account Profiles & Credentials")}
          </SectionLabel>

          <Card className="flex flex-col gap-2.5 p-3">
            <div className="flex items-center gap-2.5">
              <IconBadge icon={User} tone="info" size="sm" />
              <div className="min-w-0 flex-1">
                <div className="text-label font-semibold text-ink">
                  {t("account_prefix", "Akun:")} {details?.activeProfile || details?.profiles?.[0] || (settings?.language === "id" ? "Profil Pengguna" : "User Profile")}
                </div>
                <div className="text-micro text-ink-subtle">
                  {t("access_rights_prefix", "Hak Akses:")} {details?.accountStatus?.accessDescription || (details?.isAdmin ? t("admin_full_rights", "Administrator (Samba & Kontrol Penuh)") : t("user_standard_rights", "Pengguna Standar (Hanya Akses Samba)"))}
                </div>
              </div>
            </div>

            {/* Profile Switcher Pills */}
            {details && details.profiles && details.profiles.length > 1 && (
              <div className="flex flex-wrap items-center gap-1.5 border-t border-line pt-2">
                <span className="text-micro font-medium text-ink-faint">{t("switch_prefix", "Ganti:")}</span>
                {details.profiles.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => onSwitchProfile(p)}
                    className={cx(
                      "rounded-full px-2.5 py-0.5 text-micro font-semibold transition-colors cursor-pointer",
                      details.activeProfile === p
                        ? "bg-brand text-brand-ink font-bold shadow-xs border border-brand/40"
                        : "bg-surface-sunken text-ink-muted hover:bg-line hover:text-ink border border-line"
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            )}

            {/* Baris Aksi Akun: Grid 2x2 Auto-Layout (Icon Plus Proporsional & Font v3.12.1) */}
            <div className="grid grid-cols-2 gap-2 border-t border-line pt-2">
              <button
                type="button"
                onClick={onAddProfile}
                className="h-[26px] px-2 flex items-center justify-center gap-1.5 rounded-full bg-surface-muted hover:bg-line text-ink-soft text-[10.5px] font-medium transition cursor-pointer select-none"
              >
                <Plus className="size-4 shrink-0 stroke-[2.6]" aria-hidden />
                <span className="truncate">{t("add_profile_btn", "Tambah Akun")}</span>
              </button>
              <button
                type="button"
                onClick={onConfigCredentials}
                className="h-[26px] px-2 flex items-center justify-center gap-1.5 rounded-full bg-surface-muted hover:bg-line text-ink-soft text-[10.5px] font-medium transition cursor-pointer select-none"
              >
                <KeyRound className="size-3.5 shrink-0 stroke-[2]" aria-hidden />
                <span className="truncate">{t("credentials_btn", "Kredensial")}</span>
              </button>
              <button
                type="button"
                onClick={onEditProfile}
                className="h-[26px] px-2 flex items-center justify-center gap-1.5 rounded-full bg-surface-muted hover:bg-line text-ink-soft text-[10.5px] font-medium transition cursor-pointer select-none"
              >
                <Edit2 className="size-3.5 shrink-0 stroke-[2]" aria-hidden />
                <span className="truncate">{t("rename_profile_btn", "Ubah Nama")}</span>
              </button>
              <button
                type="button"
                disabled={!details?.profiles || details.profiles.length <= 1}
                onClick={onDeleteProfile}
                className="h-[26px] px-2 flex items-center justify-center gap-1.5 rounded-full bg-surface-muted hover:bg-line text-ink-soft text-[10.5px] font-medium transition cursor-pointer select-none disabled:opacity-45 disabled:pointer-events-none"
              >
                <Trash2 className="size-3.5 shrink-0 stroke-[2]" aria-hidden />
                <span className="truncate">{t("delete_profile_btn", "Hapus Akun")}</span>
              </button>
            </div>
          </Card>
        </section>

        {/* 5. ACTION BUTTON: BUKA DASHBOARD CONSOLE (100% DINAMIS - ZERO HARDCODED - v3.12.1 SIZING) */}
        <Button
          size="sm"
          variant="secondary"
          icon={ExternalLink}
          block
          onClick={() => {
            const targetUrl = activeRouteObj?.url || (details?.serverName ? `http://${details.serverName}.local` : "")
            if (targetUrl) {
              api.openUrl(targetUrl).catch((err: any) => notify(err?.message || "Gagal membuka server", "danger"))
            } else {
              notify("URL server belum tersedia.", "warning")
            }
          }}
        >
          {t("open_web_console_btn", "Buka Console Server di Browser")}
        </Button>
      </ViewBody>

      <FooterStatus
        showNoticePill={false}
        title={t("comm_routes_status", "Jalur Komunikasi")}
        chips={
          <>
            <TrayChip tone={isOnline ? "success" : "neutral"} icon={Radio}>
              {isAutoActive ? "Auto Failover" : activeRouteObj?.name || "LAN"}
            </TrayChip>
            <TrayChip
              icon={RefreshCw}
              onClick={loadDetails}
              title={t("refresh_net_status", "Perbarui Status Jaringan")}
            >{t("refresh_ping_btn", "Refresh Ping")}</TrayChip>
          </>
        }
      />
    
      {/* ====================================================================== */}
      {/* FLOATING REACT MODAL (Tambah/Ubah Server, Rute, Akun & ZeroTier)       */}
      {/* ====================================================================== */}
      {modalMode && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-3 backdrop-blur-xs"
          onClick={closeModal}
        >
          <div
            className="flex w-full max-w-[340px] flex-col gap-3 rounded-card border border-line bg-surface p-4 shadow-panel motion-safe:animate-flyout-in"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-line pb-2.5">
              <span className="flex items-center gap-2 text-label font-bold text-ink">
                {modalMode.includes("Server") && <Server className="size-4 text-brand" />}
                {modalMode.includes("Route") && <Network className="size-4 text-brand" />}
                {(modalMode.includes("Profile") || modalMode === "credentials") && <User className="size-4 text-info" />}
                {modalMode === "joinZeroTier" && <Network className="size-4 text-brand" />}
                {modalMode === "addServer" && t("add_server_modal_title", "Tambah Server Baru")}
                {modalMode === "editServer" && t("edit_server_modal_title", "Ubah Server")}
                {modalMode === "deleteServer" && t("confirm_delete_title", "Konfirmasi Hapus")}
                {modalMode === "addRoute" && t("add_route_modal_title", "Tambah Rute Akses")}
                {modalMode === "editRoute" && t("edit_route_modal_title", "Ubah Rute Akses")}
                {modalMode === "deleteRoute" && t("confirm_delete_title", "Konfirmasi Hapus")}
                {modalMode === "addProfile" && t("add_profile_modal_title", "Tambah Akun Server")}
                {modalMode === "editProfile" && t("edit_profile_modal_title", "Ubah Nama Akun")}
                {modalMode === "deleteProfile" && t("confirm_delete_title", "Konfirmasi Hapus")}
                {modalMode === "credentials" && t("profile_creds_modal_title", "Kelola Kredensial Akun")}
                {modalMode === "joinZeroTier" && t("join_zt_modal_title", "Sambung Jaringan ZeroTier")}
              </span>
              <button
                type="button"
                onClick={closeModal}
                className="rounded p-1 text-ink-subtle hover:bg-surface-sunken hover:text-ink transition cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Modal Form or Confirm Body */}
            {modalMode.startsWith("delete") ? (
              <div className="flex flex-col gap-3 py-1">
                <p className="text-caption text-ink-soft">
                  {t("confirm_delete_msg", "Apakah Anda yakin ingin menghapus item ini secara permanen?")}
                </p>
                <div className="rounded-tile border border-danger/30 bg-danger/10 p-2.5 font-bold text-danger text-body">
                  {activeItem?.name || activeItem?.id || "Item"}
                </div>
                <div className="flex items-center justify-end gap-2 pt-2 border-t border-line">
                  <Button size="sm" variant="soft" onClick={closeModal}>
                    {t("cancel_btn", "Batal")}
                  </Button>
                  <Button size="sm" variant="danger" onClick={handleSaveModal} disabled={isSubmitting}>
                    {isSubmitting ? t("saving_btn", "Menyimpan...") : t("delete_btn", "Hapus")}
                  </Button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSaveModal} className="flex flex-col gap-2.5">
                {/* Server Fields */}
                {(modalMode === "addServer" || modalMode === "editServer") && (
                  <>
                    <div className="flex flex-col gap-1">
                      <label className="text-micro font-semibold text-ink-subtle">{t("server_name_label", "Nama Server")}</label>
                      <input
                        type="text"
                        required
                        value={formName}
                        onChange={(e) => setFormName(e.target.value)}
                        placeholder="e.g. Server Rumah"
                        className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-medium text-ink focus:border-brand focus:outline-none"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-micro font-semibold text-ink-subtle">{t("server_url_label", "URL Utama")}</label>
                      <input
                        type="text"
                        required
                        value={formUrl}
                        onChange={(e) => setFormUrl(e.target.value)}
                        placeholder="http://192.168.1.6:80"
                        className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-mono text-ink focus:border-brand focus:outline-none"
                      />
                    </div>
                    {modalMode === "addServer" && (
                      <>
                        <div className="flex flex-col gap-1">
                          <label className="text-micro font-semibold text-ink-subtle">{t("username_label", "Nama Pengguna")}</label>
                          <input
                            type="text"
                            value={formUser}
                            onChange={(e) => setFormUser(e.target.value)}
                            placeholder="Admin"
                            className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-medium text-ink focus:border-brand focus:outline-none"
                          />
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-micro font-semibold text-ink-subtle">{t("password_label", "Kata Sandi")}</label>
                          <input
                            type={showPassword ? "text" : "password"}
                            value={formPass}
                            onChange={(e) => setFormPass(e.target.value)}
                            className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-medium text-ink focus:border-brand focus:outline-none"
                          />
                        </div>
                      </>
                    )}
                    <div className="flex flex-col gap-1">
                      <label className="text-micro font-semibold text-ink-subtle">{t("zt_nwid_label", "ZeroTier Network ID (Opsional)")}</label>
                      <input
                        type="text"
                        value={formNwid}
                        onChange={(e) => setFormNwid(e.target.value)}
                        placeholder="16-hex Network ID"
                        className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-mono text-ink focus:border-brand focus:outline-none"
                      />
                    </div>
                  </>
                )}

                {/* Route Fields */}
                {(modalMode === "addRoute" || modalMode === "editRoute") && (
                  <>
                    <div className="flex flex-col gap-1">
                      <label className="text-micro font-semibold text-ink-subtle">{t("route_name_label", "Nama Rute")}</label>
                      <input
                        type="text"
                        required
                        value={formName}
                        onChange={(e) => setFormName(e.target.value)}
                        placeholder="e.g. LAN Kantor / Domain WAN"
                        className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-medium text-ink focus:border-brand focus:outline-none"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-micro font-semibold text-ink-subtle">{t("route_url_label", "URL Jalur Akses")}</label>
                      <input
                        type="text"
                        required
                        value={formUrl}
                        onChange={(e) => setFormUrl(e.target.value)}
                        placeholder="http://192.168.1.6:80"
                        className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-mono text-ink focus:border-brand focus:outline-none"
                      />
                    </div>
                  </>
                )}

                {/* Profile & Credentials Fields */}
                {(modalMode === "addProfile" || modalMode === "editProfile" || modalMode === "credentials") && (
                  <>
                    <div className="flex flex-col gap-1">
                      <label className="text-micro font-semibold text-ink-subtle">{t("profile_name_label", "Nama Akun / Profil")}</label>
                      <input
                        type="text"
                        required
                        disabled={modalMode === "credentials"}
                        value={formName}
                        onChange={(e) => setFormName(e.target.value)}
                        className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-medium text-ink focus:border-brand focus:outline-none disabled:opacity-60"
                      />
                    </div>
                    {(modalMode === "addProfile" || modalMode === "credentials") && (
                      <>
                        <div className="flex flex-col gap-1">
                          <label className="text-micro font-semibold text-ink-subtle">{t("username_label", "Nama Pengguna")}</label>
                          <input
                            type="text"
                            required
                            value={formUser}
                            onChange={(e) => setFormUser(e.target.value)}
                            placeholder="Username ZimaOS / Samba"
                            className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-medium text-ink focus:border-brand focus:outline-none"
                          />
                        </div>
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center justify-between">
                            <label className="text-micro font-semibold text-ink-subtle">{t("password_label", "Kata Sandi")}</label>
                            <button
                              type="button"
                              onClick={() => setShowPassword((p) => !p)}
                              className="text-[10px] text-ink-muted hover:text-ink cursor-pointer"
                            >
                              {showPassword ? "Sembunyikan" : "Perlihatkan"}
                            </button>
                          </div>
                          <input
                            type={showPassword ? "text" : "password"}
                            value={formPass}
                            onChange={(e) => setFormPass(e.target.value)}
                            placeholder={modalMode === "credentials" ? t("password_optional_hint", "Kosongkan jika tetap") : ""}
                            className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-medium text-ink focus:border-brand focus:outline-none"
                          />
                        </div>
                      </>
                    )}
                  </>
                )}

                {/* ZeroTier Field */}
                {modalMode === "joinZeroTier" && (
                  <div className="flex flex-col gap-1.5">
                    <p className="text-micro text-ink-subtle">
                      {t("join_zt_desc", "Masukkan 16 karakter heksadesimal Network ID:")}
                    </p>
                    <input
                      type="text"
                      required
                      maxLength={16}
                      value={formNwid}
                      onChange={(e) => setFormNwid(e.target.value.toLowerCase().replace(/[^0-9a-f]/g, ""))}
                      placeholder="e.g. 8056c2e21c000001"
                      className="rounded-control border border-line bg-surface-sunken px-2.5 py-1.5 text-caption font-mono text-ink tracking-wider focus:border-brand focus:outline-none"
                    />
                  </div>
                )}

                {/* Form Action Buttons */}
                <div className="flex items-center justify-end gap-2 pt-2 border-t border-line">
                  <Button size="sm" variant="soft" onClick={closeModal} type="button">
                    {t("cancel_btn", "Batal")}
                  </Button>
                  <Button size="sm" variant="primary" type="submit" disabled={isSubmitting}>
                    {isSubmitting ? t("saving_btn", "Menyimpan...") : t("save_btn", "Simpan")}
                  </Button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

    </>
  )
}

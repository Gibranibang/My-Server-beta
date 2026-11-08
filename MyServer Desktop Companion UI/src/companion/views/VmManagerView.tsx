import { useState, useMemo, useEffect } from "react"
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  ExternalLink,
  Globe,
  HardDrive,
  Key,
  Pencil,
  Plus,
  Power,
  Server,
  Terminal,
  Trash2,
  X,
} from "lucide-react"
import { getTranslation } from "../i18n"
import { useCompanion, useNotice } from "../store"
import { Button, Card, Chip, IconBadge, Mono, StatusDot, cx } from "../ui"
import { ViewBody, type ViewProps } from "./shared"
import type { VirtualMachine } from "../types"

const INITIAL_VMS: VirtualMachine[] = [
  {
    id: "vm-algitha-instabox",
    name: "Algitha-VM",
    provider: "instabox",
    status: "running",
    sshHost: "ssh.instabox.sh",
    sshUser: "ibssh_s3hsj4qxhbpc43a5xishpolliq",
    sshPort: 2222,
    tokenExpiry: "6d",
    ip: "ssh.instabox.sh",
    lastActive: "Just now",
    runtimeMinutes: 184, // 3h 04m elapsed out of 480m (8h limit)
    maxRuntimeMinutes: 480,
    idleTimeoutMinutes: 30,
  },
]

export default function VmManagerView({ go }: ViewProps) {
  const { isOnline, settings } = useCompanion()
  const t = getTranslation(settings?.language)
  const { notify } = useNotice()

  // State: list of VMs with localStorage persistence
  const [vms, setVms] = useState<VirtualMachine[]>(() => {
    if (typeof window !== "undefined") {
      // Allow URL parameter for testing/sandbox
      const params = new URLSearchParams(window.location.search)
      if (params.get("vm_mode") === "multi") {
        return [
          INITIAL_VMS[0],
          {
            id: "vm-worker-instabox",
            name: "Worker-VM",
            provider: "instabox",
            status: "sleeping",
            sshHost: "ssh.instabox.sh",
            sshUser: "ibssh_k99asdf0092348a0",
            sshPort: 2222,
            tokenExpiry: "4d",
            ip: "ssh.instabox.sh",
            lastActive: "45m ago",
            runtimeMinutes: 310,
            maxRuntimeMinutes: 480,
            idleTimeoutMinutes: 30,
          },
        ]
      }
      if (params.get("vm_mode") === "empty") {
        return []
      }
      try {
        const saved = localStorage.getItem("myserver_vms")
        if (saved) {
          const parsed = JSON.parse(saved)
          if (Array.isArray(parsed)) return parsed
        }
      } catch {}
    }
    return INITIAL_VMS
  })

  // Save to localStorage whenever vms change
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("myserver_vms", JSON.stringify(vms))
      } catch {}
    }
  }, [vms])

  // Accordion state (expanded VM id in multi-mode)
  const [expandedId, setExpandedId] = useState<string | null>(vms[0]?.id || null)

  // Modals state
  const [vmToDelete, setVmToDelete] = useState<VirtualMachine | null>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      if (params.get("vm_modal") === "delete") {
        return vms[0] || null
      }
    }
    return null
  })

  const [editingVm, setEditingVm] = useState<VirtualMachine | null>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      if (params.get("vm_modal") === "edit") {
        return vms[0] || null
      }
    }
    return null
  })

  const [isAddingVm, setIsAddingVm] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      return params.get("vm_modal") === "add"
    }
    return false
  })

  // Form fields
  const [formName, setFormName] = useState("")
  const [formSshHost, setFormSshHost] = useState("ssh.instabox.sh")
  const [formSshUser, setFormSshUser] = useState("")
  const [formSshPort, setFormSshPort] = useState<number | string>(2222)
  const [formTokenExpiry, setFormTokenExpiry] = useState("6d")
  const [formWebPort, setFormWebPort] = useState<number | string>("")
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // Copy helper
  const copyToClipboard = async (text: string, label: string, vmId?: string) => {
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
      if (vmId) {
        setCopiedId(vmId)
        setTimeout(() => setCopiedId(null), 1800)
      }
      notify(`${label} disalin ke papan klip!`, "success")
    } catch {
      notify(`Gagal menyalin ${label}.`, "danger")
    }
  }

  // Generate full SSH command
  const getSshCommand = (vm: VirtualMachine) => {
    const port = vm.sshPort || 2222
    const user = vm.sshUser ? `${vm.sshUser}@` : ""
    const host = vm.sshHost || vm.ip || "ssh.instabox.sh"
    return `ssh -p ${port} ${user}${host}`
  }

  // Toggle Power (Wake / Sleep)
  const handleTogglePower = (vm: VirtualMachine) => {
    if (!isOnline) {
      notify(t("server_offline_warning", "Server sedang offline."), "warning")
      return
    }
    const nextStatus = vm.status === "running" ? "sleeping" : "running"
    setVms((prev) =>
      prev.map((item) =>
        item.id === vm.id ? { ...item, status: nextStatus } : item
      )
    )
    notify(
      nextStatus === "running"
        ? `${vm.name}: ${t("wake_vm_btn", "VM Dibangunkan")}`
        : `${vm.name}: ${t("sleep_vm_btn", "VM Masuk Mode Tidur")}`,
      "neutral"
    )
  }

  // Delete execution
  const handleDeleteConfirm = () => {
    if (!vmToDelete) return
    const targetId = vmToDelete.id
    setVms((prev) => prev.filter((v) => v.id !== targetId))
    notify(`${vmToDelete.name} berhasil dihapus.`, "neutral")
    setVmToDelete(null)
  }

  // Open Edit Modal
  const handleOpenEdit = (vm: VirtualMachine) => {
    setEditingVm(vm)
    setFormName(vm.name)
    setFormSshHost(vm.sshHost || vm.ip || "ssh.instabox.sh")
    setFormSshUser(vm.sshUser || "")
    setFormSshPort(vm.sshPort || 2222)
    setFormTokenExpiry(vm.tokenExpiry || "6d")
    setFormWebPort(vm.webPort || "")
  }

  // Save Add/Edit
  const handleSaveForm = (e: React.FormEvent) => {
    e.preventDefault()
    const cleanName = formName.trim()
    if (!cleanName) {
      notify("Nama Virtual Machine wajib diisi.", "danger")
      return
    }

    if (editingVm) {
      setVms((prev) =>
        prev.map((item) =>
          item.id === editingVm.id
            ? {
                ...item,
                name: cleanName,
                sshHost: formSshHost.trim() || "ssh.instabox.sh",
                sshUser: formSshUser.trim(),
                sshPort: Number(formSshPort) || 2222,
                tokenExpiry: formTokenExpiry.trim(),
                webPort: formWebPort ? Number(formWebPort) : undefined,
                ip: formSshHost.trim() || "ssh.instabox.sh",
              }
            : item
        )
      )
      notify(`${cleanName} berhasil diperbarui!`, "success")
      setEditingVm(null)
    } else {
      const newVm: VirtualMachine = {
        id: `vm-${Date.now()}`,
        name: cleanName,
        provider: "instabox",
        status: "running",
        sshHost: formSshHost.trim() || "ssh.instabox.sh",
        sshUser: formSshUser.trim(),
        sshPort: Number(formSshPort) || 2222,
        tokenExpiry: formTokenExpiry.trim() || "7d",
        webPort: formWebPort ? Number(formWebPort) : undefined,
        ip: formSshHost.trim() || "ssh.instabox.sh",
        runtimeMinutes: 0,
        maxRuntimeMinutes: 480,
        idleTimeoutMinutes: 30,
        lastActive: "Just now",
      }
      setVms((prev) => [...prev, newVm])
      setExpandedId(newVm.id)
      notify(`${cleanName} berhasil ditambahkan!`, "success")
      setIsAddingVm(false)
    }
  }

  // Open Web Service in browser
  const handleOpenWeb = (vm: VirtualMachine) => {
    if (!vm.webPort && !vm.webUrl) return
    const host = vm.sshHost || vm.ip || "localhost"
    const targetUrl = vm.webUrl || `http://${host}:${vm.webPort}`
    window.open(targetUrl, "_blank")
    notify(`Membuka web service ${targetUrl} di browser…`, "info")
  }

  const isSingle = vms.length === 1
  const isMultiple = vms.length > 1

  return (
    <ViewBody>
      {/* ========================================================= */}
      {/* 1. TOP HEADER: Clean Title (Left) + Add VM Button (Right) */}
      {/* ========================================================= */}
      <div className="flex items-center justify-between pl-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-[10px] font-bold tracking-wider text-ink-muted uppercase truncate">
            {t("vm_section_title", "VIRTUAL MACHINES")}
          </span>
          {vms.length > 0 && (
            <span className="text-[10px] font-semibold text-ink-subtle">
              ({vms.length})
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => {
              setEditingVm(null)
              setFormName("")
              setFormSshHost("ssh.instabox.sh")
              setFormSshUser("")
              setFormSshPort(2222)
              setFormTokenExpiry("7d")
              setFormWebPort("")
              setIsAddingVm(true)
            }}
            className="h-[23px] px-2.5 flex items-center gap-1 rounded-full bg-info-ink/15 hover:bg-info-ink/25 text-info-ink text-[10.5px] font-semibold transition cursor-pointer select-none"
          >
            <Plus className="size-3" />
            <span>{t("add_vm_btn", "Tambah VM")}</span>
          </button>
        </div>
      </div>

      {/* ========================================================= */}
      {/* 2. CASE 0: EMPTY STATE (NO VMS)                           */}
      {/* ========================================================= */}
      {vms.length === 0 && (
        <Card className="flex flex-col items-center justify-center py-8 px-4 text-center gap-2">
          <div className="size-10 rounded-full bg-surface-sunken flex items-center justify-center text-ink-muted">
            <Server className="size-5" />
          </div>
          <span className="text-body font-bold text-ink">
            {t("vm_empty_title", "Belum Ada Virtual Machine")}
          </span>
          <span className="text-micro text-ink-subtle max-w-[220px]">
            {t("vm_empty_desc", "Tambahkan InstaBox atau Linux VM Anda untuk mengelola via SSH.")}
          </span>
          <Button
            size="sm"
            variant="info"
            icon={Plus}
            className="mt-2"
            onClick={() => {
              setEditingVm(null)
              setFormName("Algitha-VM")
              setFormSshHost("ssh.instabox.sh")
              setFormSshUser("ibssh_s3hsj4qxhbpc43a5xishpolliq")
              setFormSshPort(2222)
              setFormTokenExpiry("6d")
              setFormWebPort("")
              setIsAddingVm(true)
            }}
          >
            {t("vm_add_first_btn", "Tambah VM Pertama")}
          </Button>
        </Card>
      )}

      {/* ========================================================= */}
      {/* 3. CASE 1: SINGLE VM MODE (1 RICH CARD)                   */}
      {/* ========================================================= */}
      {isSingle && (
        <Card className="flex flex-col gap-2.5 p-3 relative overflow-hidden">
          {/* Card Header: Icon, Name, Provider, Status & Action Icons */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <IconBadge
                icon={Server}
                tone={
                  !isOnline
                    ? "neutral"
                    : vms[0].status === "running"
                      ? "success"
                      : vms[0].status === "sleeping"
                        ? "warning"
                        : "danger"
                }
                size="sm"
              />
              <div className="flex flex-col min-w-0">
                <span className="text-body font-bold text-ink truncate leading-tight">
                  {vms[0].name}
                </span>
                <span className="text-nano text-ink-subtle truncate">
                  InstaBox Cloud · {vms[0].sshHost || vms[0].ip}:{vms[0].sshPort}
                </span>
              </div>
            </div>

            {/* Status Pill & Edit/Delete Icons */}
            <div className="flex items-center gap-1.5 shrink-0">
              <span
                className={cx(
                  "inline-flex items-center gap-1 text-nano font-semibold rounded-full px-2 py-0.5 border",
                  !isOnline
                    ? "bg-surface-sunken text-ink-muted border-line"
                    : vms[0].status === "running"
                      ? "bg-success-soft text-success-ink border-success-line/60"
                      : vms[0].status === "sleeping"
                        ? "bg-warning-soft text-warning-ink border-warning-line/60"
                        : "bg-danger-soft text-danger-ink border-danger-line/60"
                )}
              >
                <StatusDot
                  tone={
                    !isOnline
                      ? "neutral"
                      : vms[0].status === "running"
                        ? "success"
                        : vms[0].status === "sleeping"
                          ? "warning"
                          : "danger"
                  }
                  size="xs"
                />
                {!isOnline
                  ? "Offline"
                  : vms[0].status === "running"
                    ? t("vm_status_running", "Active")
                    : vms[0].status === "sleeping"
                      ? t("vm_status_sleep", "Sleeping")
                      : t("vm_status_cooldown", "Cooldown")}
              </span>

              <button
                type="button"
                onClick={() => handleOpenEdit(vms[0])}
                className="p-1 rounded-md text-ink-subtle hover:text-ink hover:bg-surface-sunken transition cursor-pointer"
                title={t("edit_vm_btn", "Edit")}
              >
                <Pencil className="size-3.5" />
              </button>

              <button
                type="button"
                onClick={() => setVmToDelete(vms[0])}
                className="p-1 rounded-md text-ink-subtle hover:text-danger-ink hover:bg-danger-soft/50 transition cursor-pointer"
                title={t("delete_vm_btn", "Hapus")}
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          </div>

          {/* Connection Details Box (1:1 Sesuai Dashboard SSH InstaBox) */}
          <div className="rounded-tile bg-surface-sunken/80 border border-line p-2.5 flex flex-col gap-1.5 text-nano">
            <div className="flex items-center justify-between text-ink-subtle">
              <span className="font-semibold text-ink">SSH Connection</span>
              {vms[0].tokenExpiry && (
                <span className="flex items-center gap-1 text-[10px] text-amber-500 font-medium">
                  <Clock className="size-3" />
                  <span>expires in {vms[0].tokenExpiry}</span>
                </span>
              )}
            </div>

            <div className="flex items-center justify-between gap-1 text-ink-muted">
              <span className="text-[10px]">Host:</span>
              <Mono className="text-[10.5px] text-ink truncate select-all">
                {vms[0].sshHost || vms[0].ip}:{vms[0].sshPort}
              </Mono>
            </div>

            {vms[0].sshUser && (
              <div className="flex items-center justify-between gap-1 text-ink-muted">
                <span className="text-[10px]">Token:</span>
                <Mono className="text-[10.5px] text-ink-muted truncate max-w-[170px] select-all">
                  {vms[0].sshUser.slice(0, 16)}...
                </Mono>
              </div>
            )}
          </div>

          {/* Runtime & Limits Bar */}
          <div className="rounded-tile bg-surface-sunken/40 border border-line/60 p-2 flex flex-col gap-1 text-nano">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1 text-ink-subtle">
                <Clock className="size-3 text-info" />
                <span>{t("vm_runtime_remaining", "Runtime:")}</span>
              </span>
              <span className="font-mono text-ink font-semibold">
                {Math.floor((vms[0].runtimeMinutes || 0) / 60)}j{" "}
                {(vms[0].runtimeMinutes || 0) % 60}m / 8j
              </span>
            </div>
            <div className="w-full bg-surface-sunken rounded-full h-1 overflow-hidden">
              <div
                className="bg-brand h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(100, (((vms[0].runtimeMinutes || 0) / 480) * 100))}%`,
                }}
              />
            </div>
            <div className="flex items-center justify-between text-[10px] text-ink-faint">
              <span>Auto-sleep: 30m idle</span>
              <span>Port: {vms[0].sshPort}</span>
            </div>
          </div>

          {/* Action Buttons: Primary Universal SSH Connection */}
          <div className="flex flex-col gap-1.5 mt-0.5">
            <button
              type="button"
              disabled={!isOnline}
              onClick={() => copyToClipboard(getSshCommand(vms[0]), "Perintah SSH", vms[0].id)}
              className={cx(
                "w-full h-9 rounded-tile flex items-center justify-center gap-2 font-bold text-caption shadow-sm transition cursor-pointer select-none",
                !isOnline
                  ? "bg-surface-sunken text-ink-muted cursor-not-allowed"
                  : "bg-brand text-brand-ink hover:opacity-90 active:scale-[0.99] shadow-brand/20"
              )}
            >
              {copiedId === vms[0].id ? (
                <>
                  <Check className="size-4" />
                  <span>Perintah Disalin!</span>
                </>
              ) : (
                <>
                  <Terminal className="size-4" />
                  <span>{t("vm_copy_ssh_cmd", "Salin Perintah SSH")}</span>
                </>
              )}
            </button>

            {/* Optional Web Service Button (Only when webPort is configured) */}
            {vms[0].webPort && (
              <button
                type="button"
                disabled={!isOnline}
                onClick={() => handleOpenWeb(vms[0])}
                className="w-full h-8 rounded-tile flex items-center justify-center gap-1.5 font-semibold text-micro bg-info-soft text-info-ink hover:bg-info-soft/80 border border-info-line/60 transition cursor-pointer select-none"
              >
                <Globe className="size-3.5" />
                <span>Buka Layanan Web (Port {vms[0].webPort})</span>
                <ExternalLink className="size-3" />
              </button>
            )}

            {/* Secondary Row: Power Toggle */}
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="subtle"
                icon={Power}
                disabled={!isOnline}
                onClick={() => handleTogglePower(vms[0])}
                className="flex-1 justify-center"
              >
                {vms[0].status === "running"
                  ? t("sleep_vm_btn", "Tidurkan VM")
                  : t("wake_vm_btn", "Bangunkan VM")}
              </Button>

              <Button
                size="sm"
                variant="subtle"
                icon={Copy}
                disabled={!isOnline}
                onClick={() => copyToClipboard(`ssh://${vms[0].sshUser ? `${vms[0].sshUser}@` : ""}${vms[0].sshHost || vms[0].ip}:${vms[0].sshPort}`, "URI SSH")}
                className="flex-1 justify-center text-nano"
              >
                Salin URI
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* ========================================================= */}
      {/* 4. CASE 2: MULTIPLE VMS MODE (NATURAL ACCORDION LIST)     */}
      {/* ========================================================= */}
      {isMultiple && (
        <div className="flex flex-col gap-2">
          {vms.map((vm) => {
            const isExpanded = expandedId === vm.id
            return (
              <Card
                key={vm.id}
                className={cx(
                  "flex flex-col transition-all overflow-hidden p-0 border",
                  isExpanded ? "border-brand/40 shadow-sm" : "border-line"
                )}
              >
                {/* Accordion Header Row */}
                <div
                  className="flex items-center justify-between p-2.5 cursor-pointer hover:bg-surface-sunken/40 select-none"
                  onClick={() => setExpandedId(isExpanded ? null : vm.id)}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <IconBadge
                      icon={Server}
                      tone={
                        !isOnline
                          ? "neutral"
                          : vm.status === "running"
                            ? "success"
                            : vm.status === "sleeping"
                              ? "warning"
                              : "danger"
                      }
                      size="xs"
                    />
                    <div className="flex flex-col min-w-0">
                      <span className="text-caption font-bold text-ink truncate leading-tight">
                        {vm.name}
                      </span>
                      <span className="text-nano text-ink-subtle truncate">
                        {vm.sshHost || vm.ip}:{vm.sshPort}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className={cx(
                        "inline-flex items-center gap-1 text-[10px] font-semibold rounded-full px-2 py-0.5 border",
                        !isOnline
                          ? "bg-surface-sunken text-ink-muted border-line"
                          : vm.status === "running"
                            ? "bg-success-soft text-success-ink border-success-line/60"
                            : "bg-warning-soft text-warning-ink border-warning-line/60"
                      )}
                    >
                      <StatusDot
                        tone={
                          !isOnline
                            ? "neutral"
                            : vm.status === "running"
                              ? "success"
                              : "warning"
                        }
                        size="xs"
                      />
                      {vm.status === "running" ? "Active" : "Sleep"}
                    </span>

                    {isExpanded ? (
                      <ChevronUp className="size-4 text-ink-subtle" />
                    ) : (
                      <ChevronDown className="size-4 text-ink-subtle" />
                    )}
                  </div>
                </div>

                {/* Accordion Expanded Body */}
                {isExpanded && (
                  <div className="px-2.5 pb-2.5 pt-1 border-t border-line/60 flex flex-col gap-2 bg-surface-sunken/20">
                    {/* Connection details */}
                    <div className="rounded-tile bg-surface-sunken/80 border border-line p-2 flex flex-col gap-1 text-nano">
                      <div className="flex items-center justify-between text-ink-subtle">
                        <span className="font-semibold text-ink text-[10.5px]">Connection</span>
                        {vm.tokenExpiry && (
                          <span className="flex items-center gap-1 text-[10px] text-amber-500 font-medium">
                            <Clock className="size-3" />
                            <span>expires in {vm.tokenExpiry}</span>
                          </span>
                        )}
                      </div>
                      <Mono className="text-[10.5px] text-ink select-all truncate">
                        {getSshCommand(vm)}
                      </Mono>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-1.5 pt-0.5">
                      <Button
                        size="sm"
                        variant="info"
                        icon={copiedId === vm.id ? Check : Terminal}
                        disabled={!isOnline}
                        onClick={(e) => {
                          e.stopPropagation()
                          copyToClipboard(getSshCommand(vm), "Perintah SSH", vm.id)
                        }}
                        className="flex-1 justify-center text-nano"
                      >
                        {copiedId === vm.id ? "Disalin!" : "Salin SSH"}
                      </Button>

                      {vm.webPort && (
                        <Button
                          size="sm"
                          variant="subtle"
                          icon={Globe}
                          disabled={!isOnline}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleOpenWeb(vm)
                          }}
                          className="flex-1 justify-center text-nano"
                        >
                          Web ({vm.webPort})
                        </Button>
                      )}

                      <Button
                        size="sm"
                        variant="subtle"
                        icon={Power}
                        disabled={!isOnline}
                        onClick={(e) => {
                          e.stopPropagation()
                          handleTogglePower(vm)
                        }}
                        className="flex-1 justify-center text-nano"
                      >
                        {vm.status === "running" ? "Tidur" : "Bangun"}
                      </Button>

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleOpenEdit(vm)
                        }}
                        className="p-1.5 rounded-md text-ink-subtle hover:text-ink hover:bg-surface-sunken transition cursor-pointer"
                        title={t("edit_vm_btn", "Edit")}
                      >
                        <Pencil className="size-3.5" />
                      </button>

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          setVmToDelete(vm)
                        }}
                        className="p-1.5 rounded-md text-ink-subtle hover:text-danger-ink hover:bg-danger-soft/50 transition cursor-pointer"
                        title={t("delete_vm_btn", "Hapus")}
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      {/* ========================================================= */}
      {/* 5. MODAL FORM: TAMBAH / EDIT VIRTUAL MACHINE              */}
      {/* ========================================================= */}
      {(isAddingVm || editingVm) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <Card className="w-full max-w-[280px] p-3 flex flex-col gap-2.5 shadow-xl border border-line bg-surface">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-line pb-2">
              <span className="text-caption font-bold text-ink">
                {editingVm ? "Edit Virtual Machine" : "Tambah Virtual Machine"}
              </span>
              <button
                type="button"
                onClick={() => {
                  setIsAddingVm(false)
                  setEditingVm(null)
                }}
                className="p-1 rounded-md text-ink-subtle hover:text-ink transition cursor-pointer"
              >
                <X className="size-4" />
              </button>
            </div>

            {/* Modal Form */}
            <form onSubmit={handleSaveForm} className="flex flex-col gap-2 text-nano">
              <div>
                <label className="block font-semibold text-ink-subtle mb-0.5">
                  Nama Virtual Machine
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Algitha-VM"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                />
              </div>

              <div>
                <label className="block font-semibold text-ink-subtle mb-0.5">
                  Host Gateway SSH
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. ssh.instabox.sh"
                  value={formSshHost}
                  onChange={(e) => setFormSshHost(e.target.value)}
                  className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                />
              </div>

              <div className="grid grid-cols-2 gap-1.5">
                <div>
                  <label className="block font-semibold text-ink-subtle mb-0.5">
                    Port SSH
                  </label>
                  <input
                    type="number"
                    required
                    placeholder="2222"
                    value={formSshPort}
                    onChange={(e) => setFormSshPort(e.target.value)}
                    className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-ink-subtle mb-0.5">
                    Masa Berlaku
                  </label>
                  <input
                    type="text"
                    placeholder="6d / 7d"
                    value={formTokenExpiry}
                    onChange={(e) => setFormTokenExpiry(e.target.value)}
                    className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                  />
                </div>
              </div>

              <div>
                <label className="block font-semibold text-ink-subtle mb-0.5">
                  User / Token SSH
                </label>
                <input
                  type="text"
                  placeholder="ibssh_s3hsj... (Token sebelum @)"
                  value={formSshUser}
                  onChange={(e) => setFormSshUser(e.target.value)}
                  className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand font-mono text-[10.5px]"
                />
              </div>

              <div>
                <label className="block font-semibold text-ink-subtle mb-0.5">
                  Port Web Layanan (Opsional)
                </label>
                <input
                  type="number"
                  placeholder="e.g. 8080 (Kosongkan bila tidak ada)"
                  value={formWebPort}
                  onChange={(e) => setFormWebPort(e.target.value)}
                  className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-caption text-ink focus:outline-none focus:border-brand"
                />
              </div>

              <div className="flex items-center gap-1.5 pt-1 mt-1 border-t border-line">
                <Button
                  size="sm"
                  variant="subtle"
                  type="button"
                  onClick={() => {
                    setIsAddingVm(false)
                    setEditingVm(null)
                  }}
                  className="flex-1 justify-center"
                >
                  {t("cancel_btn", "Batal")}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  type="submit"
                  className="flex-1 justify-center"
                >
                  {t("save_btn", "Simpan")}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ========================================================= */}
      {/* 6. MODAL KONFIRMASI HAPUS VM                              */}
      {/* ========================================================= */}
      {vmToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <Card className="w-full max-w-[270px] p-3 flex flex-col gap-2.5 shadow-xl border border-danger-line/60 bg-surface">
            <div className="flex items-center gap-2 text-danger-ink">
              <div className="size-7 rounded-full bg-danger-soft flex items-center justify-center shrink-0">
                <AlertTriangle className="size-4" />
              </div>
              <span className="text-caption font-bold text-ink">
                {t("confirm_delete_vm_title", "Konfirmasi Hapus")}
              </span>
            </div>

            <p className="text-nano text-ink-muted leading-relaxed">
              Apakah Anda yakin ingin menghapus{" "}
              <strong className="text-ink">{vmToDelete.name}</strong>? Tindakan
              ini akan menghapus konfigurasi koneksi VM dari MyServer.
            </p>

            <div className="flex items-center gap-1.5 pt-1 border-t border-line">
              <Button
                size="sm"
                variant="subtle"
                onClick={() => setVmToDelete(null)}
                className="flex-1 justify-center"
              >
                {t("cancel_btn", "Batal")}
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={handleDeleteConfirm}
                className="flex-1 justify-center"
              >
                {t("delete_btn", "Hapus")}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </ViewBody>
  )
}

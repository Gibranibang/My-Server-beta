import { useState, useMemo } from "react"
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Cpu,
  ExternalLink,
  HardDrive,
  LoaderCircle,
  MemoryStick,
  Pencil,
  Plus,
  Power,
  Server,
  Terminal,
  Trash2,
  X,
  Zap,
} from "lucide-react"
import { getTranslation } from "../i18n"
import { useCompanion, useNotice } from "../store"
import { Button, Card, Chip, IconBadge, Mono, StatusDot, cx } from "../ui"
import { ViewBody, type ViewProps } from "./shared"
import type { VirtualMachine } from "../types"

const DEFAULT_VMS: VirtualMachine[] = [
  {
    id: "vm-instabox-primary",
    name: "InstaBox Dev Server",
    provider: "instabox",
    status: "running",
    ip: "159.223.45.110",
    sshPort: 2222,
    specs: {
      cpu: "4 vCPU AMD EPYC",
      ram: "8 GB DDR5",
      storage: "20 GB NVMe",
    },
    runtimeMinutes: 184, // 3h 04m elapsed out of 480m (8h limit)
    maxRuntimeMinutes: 480,
    idleTimeoutMinutes: 30,
    antigravityPort: 8080,
    lastActive: "Just now",
  },
]

const SECOND_VM: VirtualMachine = {
  id: "vm-instabox-worker",
  name: "InstaBox Build Worker",
  provider: "instabox",
  status: "sleeping",
  ip: "159.223.45.112",
  sshPort: 2223,
  specs: {
    cpu: "4 vCPU AMD EPYC",
    ram: "8 GB DDR5",
    storage: "20 GB NVMe",
  },
  runtimeMinutes: 310,
  maxRuntimeMinutes: 480,
  idleTimeoutMinutes: 30,
  antigravityPort: 8082,
  lastActive: "45m ago",
}

export default function VmManagerView({ go }: ViewProps) {
  const { isOnline, settings } = useCompanion()
  const t = getTranslation(settings?.language)
  const { notify } = useNotice()

  // State: list of VMs
  const [vms, setVms] = useState<VirtualMachine[]>(() => {
    // Check if URL query asks for multi mode
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      if (params.get("vm_mode") === "multi") {
        return [DEFAULT_VMS[0], SECOND_VM]
      }
    }
    return [DEFAULT_VMS[0]]
  })

  // Accordion state (expanded VM id in multi-mode)
  const [expandedId, setExpandedId] = useState<string | null>(DEFAULT_VMS[0].id)

  // Modals state
  const [vmToDelete, setVmToDelete] = useState<VirtualMachine | null>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      if (params.get("vm_modal") === "delete") {
        return DEFAULT_VMS[0]
      }
    }
    return null
  })

  const [editingVm, setEditingVm] = useState<VirtualMachine | null>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      if (params.get("vm_modal") === "edit") {
        return DEFAULT_VMS[0]
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
  const [formName, setFormName] = useState(editingVm?.name || "InstaBox Cloud VM")
  const [formIp, setFormIp] = useState(editingVm?.ip || "159.223.45.110")
  const [formSshPort, setFormSshPort] = useState(editingVm?.sshPort || 2222)
  const [formAgPort, setFormAgPort] = useState(editingVm?.antigravityPort || 8080)
  const [formCpu, setFormCpu] = useState(editingVm?.specs.cpu || "4 vCPU AMD EPYC")
  const [formRam, setFormRam] = useState(editingVm?.specs.ram || "8 GB DDR5")
  const [formStorage, setFormStorage] = useState(editingVm?.specs.storage || "20 GB NVMe")

  // Pre-flight action state
  const [preflightVmId, setPreflightVmId] = useState<string | null>(null)

  // Toggle demo mode between 1 VM and 2 VMs
  const toggleDemoMode = () => {
    if (vms.length === 1) {
      setVms([vms[0], SECOND_VM])
      setExpandedId(vms[0].id)
      notify(t("vm_accordion_mode_label", "Multiple VMs (Accordion Mode)"), "info")
    } else {
      setVms([vms[0]])
      notify(t("vm_card_mode_label", "1 VM Connected (Card Mode)"), "info")
    }
  }

  // Pre-flight wake and launch Antigravity WebApp
  const handleLaunchAntigravity = (vm: VirtualMachine) => {
    if (!isOnline) {
      notify(t("server_offline_warning", "Server is offline. Cannot reach VM."), "danger")
      return
    }

    if (vm.status === "cooldown") {
      notify(t("vm_preflight_cooldown_err", "VM is in cooldown. Please wait before waking."), "warning")
      return
    }

    if (vm.status === "sleeping") {
      setPreflightVmId(vm.id)
      notify(t("vm_preflight_waking", "Waking VM from sleep..."), "info")

      setTimeout(() => {
        setVms((prev) =>
          prev.map((item) =>
            item.id === vm.id ? { ...item, status: "running" as const } : item
          )
        )
        setPreflightVmId(null)
        notify(t("vm_preflight_success", "VM is active! Opening Antigravity Remote..."), "success")
        window.open(`http://${vm.ip}:${vm.antigravityPort || 8080}`, "_blank")
      }, 1200)
    } else {
      notify(t("vm_preflight_success", "Opening Antigravity Remote..."), "success")
      window.open(`http://${vm.ip}:${vm.antigravityPort || 8080}`, "_blank")
    }
  }

  // Toggle Power (Wake / Sleep)
  const handleTogglePower = (vm: VirtualMachine) => {
    if (!isOnline) return
    const nextStatus = vm.status === "running" ? "sleeping" : "running"
    setVms((prev) =>
      prev.map((item) =>
        item.id === vm.id ? { ...item, status: nextStatus } : item
      )
    )
    notify(
      nextStatus === "running"
        ? t("wake_vm_btn", "VM Woken Up")
        : t("sleep_vm_btn", "VM Entered Sleep"),
      "neutral"
    )
  }

  // Copy SSH terminal command
  const handleCopySsh = (vm: VirtualMachine) => {
    const cmd = `ssh -p ${vm.sshPort} root@${vm.ip}`
    if (navigator?.clipboard) {
      navigator.clipboard.writeText(cmd)
    }
    notify(`SSH Command copied: ${cmd}`, "info")
  }

  // Delete execution
  const handleDeleteConfirm = () => {
    if (!vmToDelete) return
    const targetId = vmToDelete.id
    setVms((prev) => prev.filter((v) => v.id !== targetId))
    notify(`${vmToDelete.name} deleted`, "neutral")
    setVmToDelete(null)
  }

  // Open Edit Modal
  const handleOpenEdit = (vm: VirtualMachine) => {
    setEditingVm(vm)
    setFormName(vm.name)
    setFormIp(vm.ip)
    setFormSshPort(vm.sshPort)
    setFormAgPort(vm.antigravityPort || 8080)
    setFormCpu(vm.specs.cpu)
    setFormRam(vm.specs.ram)
    setFormStorage(vm.specs.storage)
  }

  // Save Add/Edit
  const handleSaveForm = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingVm) {
      setVms((prev) =>
        prev.map((item) =>
          item.id === editingVm.id
            ? {
                ...item,
                name: formName,
                ip: formIp,
                sshPort: Number(formSshPort),
                antigravityPort: Number(formAgPort),
                specs: {
                  cpu: formCpu,
                  ram: formRam,
                  storage: formStorage,
                },
              }
            : item
        )
      )
      notify(t("save_btn", "VM Updated"), "success")
      setEditingVm(null)
    } else {
      const newVm: VirtualMachine = {
        id: `vm-${Date.now()}`,
        name: formName || "New InstaBox VM",
        provider: "instabox",
        status: "sleeping",
        ip: formIp || "159.223.45.115",
        sshPort: Number(formSshPort) || 2222,
        antigravityPort: Number(formAgPort) || 8080,
        specs: {
          cpu: formCpu || "4 vCPU AMD EPYC",
          ram: formRam || "8 GB DDR5",
          storage: formStorage || "20 GB NVMe",
        },
        runtimeMinutes: 0,
        maxRuntimeMinutes: 480,
        idleTimeoutMinutes: 30,
        lastActive: "Just now",
      }
      setVms((prev) => [...prev, newVm])
      notify(t("add_vm_btn", "VM Added"), "success")
      setIsAddingVm(false)
    }
  }

  const isSingle = vms.length === 1

  return (
    <ViewBody>
      {/* Top Bar: Section Title + Active Count + Add VM Button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-body font-bold text-ink truncate">
            {t("vm_section_title", "InstaBox Virtual Machines")}
          </span>
          <Chip tone={isOnline ? "success" : "neutral"} size="sm">
            {vms.filter((v) => v.status === "running").length}/{vms.length}{" "}
            {t("vm_status_running", "Active")}
          </Chip>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            size="sm"
            variant="info"
            icon={Plus}
            disabled={!isOnline}
            onClick={() => {
              setEditingVm(null)
              setFormName("InstaBox Dev Server 2")
              setFormIp("159.223.45.114")
              setFormSshPort(2224)
              setFormAgPort(8084)
              setIsAddingVm(true)
            }}
          >
            {t("add_vm_btn", "Tambah VM")}
          </Button>
        </div>
      </div>

      {/* Mode Switcher pill helper for Demo / Testing */}
      <div className="flex items-center justify-between rounded-tile bg-surface-sunken/60 px-2.5 py-1 text-nano text-ink-subtle border border-line/60">
        <span className="font-medium">
          {isSingle
            ? t("vm_card_mode_label", "1 VM Connected (Card Mode)")
            : t("vm_accordion_mode_label", "Multiple VMs (Accordion Mode)")}
        </span>
        <button
          type="button"
          onClick={toggleDemoMode}
          className="text-info font-semibold hover:underline cursor-pointer"
        >
          {isSingle ? "+ Tampilkan 2 VM (Accordion)" : "Kembali ke 1 VM (Card)"}
        </button>
      </div>

      {/* ========================================================= */}
      {/* CASE 1: SINGLE VM MODE (RENDERED AS DIRECT RICH CARD)     */}
      {/* ========================================================= */}
      {isSingle && (
        <Card className="flex flex-col gap-2.5 p-3 relative overflow-hidden">
          {/* Card Header: Icon, Name, Status, Action Icons */}
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
                  InstaBox Cloud · {vms[0].ip}
                </span>
              </div>
            </div>

            {/* Status & Item Actions */}
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
                  pulse={isOnline && vms[0].status === "running"}
                />
                {!isOnline
                  ? "Offline"
                  : vms[0].status === "running"
                    ? t("vm_status_running", "Active")
                    : vms[0].status === "sleeping"
                      ? t("vm_status_sleep", "Sleeping")
                      : t("vm_status_cooldown", "Cooldown")}
              </span>

              {/* Edit button */}
              <button
                type="button"
                onClick={() => handleOpenEdit(vms[0])}
                title={t("edit_vm_btn", "Edit VM")}
                aria-label={t("edit_vm_btn", "Edit VM")}
                className="rounded-control p-1 text-ink-subtle hover:bg-surface-sunken hover:text-ink transition cursor-pointer"
              >
                <Pencil className="size-3.5" />
              </button>

              {/* Delete button */}
              <button
                type="button"
                onClick={() => setVmToDelete(vms[0])}
                title={t("delete_vm_btn", "Hapus VM")}
                aria-label={t("delete_vm_btn", "Hapus VM")}
                className="rounded-control p-1 text-ink-subtle hover:bg-danger-soft hover:text-danger-bright transition cursor-pointer"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          </div>

          {/* Specs & Hardware Grid */}
          <div className="grid grid-cols-3 gap-1.5 rounded-tile border border-line bg-surface-sunken/60 p-2 text-caption">
            <div className="flex items-center gap-1.5 min-w-0">
              <Cpu className="size-3 text-info shrink-0" />
              <div className="flex flex-col min-w-0">
                <span className="text-nano text-ink-subtle uppercase font-semibold">CPU</span>
                <span className="text-micro font-bold text-ink truncate leading-tight">
                  {vms[0].specs.cpu.split(" ")[0]} {vms[0].specs.cpu.split(" ")[1]}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-1.5 min-w-0">
              <MemoryStick className="size-3 text-info shrink-0" />
              <div className="flex flex-col min-w-0">
                <span className="text-nano text-ink-subtle uppercase font-semibold">RAM</span>
                <span className="text-micro font-bold text-ink truncate leading-tight">
                  {vms[0].specs.ram.split(" ")[0]} {vms[0].specs.ram.split(" ")[1]}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-1.5 min-w-0">
              <HardDrive className="size-3 text-info shrink-0" />
              <div className="flex flex-col min-w-0">
                <span className="text-nano text-ink-subtle uppercase font-semibold">NVMe</span>
                <span className="text-micro font-bold text-ink truncate leading-tight">
                  {vms[0].specs.storage.split(" ")[0]} {vms[0].specs.storage.split(" ")[1]}
                </span>
              </div>
            </div>
          </div>

          {/* Free Tier Runtime & Idle Rules Information */}
          <div className="flex flex-col gap-1.5 rounded-tile border border-line bg-surface-sunken/40 p-2">
            <div className="flex items-center justify-between text-nano font-medium">
              <span className="text-ink-subtle flex items-center gap-1">
                <Clock className="size-3 text-info shrink-0" />
                {t("vm_runtime_remaining", "Sisa Waktu Nyala")}:
              </span>
              <span className="text-ink font-mono font-semibold">
                {Math.floor((vms[0].maxRuntimeMinutes - vms[0].runtimeMinutes) / 60)}j{" "}
                {(vms[0].maxRuntimeMinutes - vms[0].runtimeMinutes) % 60}m / 8j
              </span>
            </div>

            {/* Progress bar */}
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
              <div
                className={cx(
                  "h-full rounded-full transition-all duration-300",
                  vms[0].runtimeMinutes > 420
                    ? "bg-danger"
                    : vms[0].runtimeMinutes > 300
                      ? "bg-warning"
                      : "bg-success"
                )}
                style={{
                  width: `${Math.min(100, (vms[0].runtimeMinutes / vms[0].maxRuntimeMinutes) * 100)}%`,
                }}
              />
            </div>

            <div className="flex items-center justify-between text-[9px] text-ink-muted">
              <span>{t("vm_idle_note", "Auto-sleep setelah 30m idle")}</span>
              <span className="font-mono text-ink-subtle">Port SSH: {vms[0].sshPort}</span>
            </div>
          </div>

          {/* Primary Action Button: Launch Antigravity Remote */}
          <Button
            block
            variant="primary"
            size="md"
            icon={preflightVmId === vms[0].id ? LoaderCircle : ExternalLink}
            disabled={!isOnline}
            onClick={() => handleLaunchAntigravity(vms[0])}
          >
            {preflightVmId === vms[0].id
              ? t("vm_preflight_waking", "Membangunkan VM...")
              : t("launch_antigravity_btn", "Buka Antigravity Remote")}
          </Button>

          {/* Secondary Actions: Wake/Sleep Toggle & SSH Terminal */}
          <div className="grid grid-cols-2 gap-2">
            <Button
              size="sm"
              variant={vms[0].status === "running" ? "soft" : "info"}
              icon={Power}
              disabled={!isOnline}
              onClick={() => handleTogglePower(vms[0])}
            >
              {vms[0].status === "running"
                ? t("sleep_vm_btn", "Tidurkan VM")
                : t("wake_vm_btn", "Bangunkan VM")}
            </Button>

            <Button
              size="sm"
              variant="secondary"
              icon={Terminal}
              disabled={!isOnline}
              onClick={() => handleCopySsh(vms[0])}
            >
              {t("open_ssh_btn", "Terminal SSH")}
            </Button>
          </div>
        </Card>
      )}

      {/* ========================================================= */}
      {/* CASE 2: MULTIPLE VMS (RENDERED AS ACCORDION CARDS)        */}
      {/* ========================================================= */}
      {!isSingle && (
        <div className="flex flex-col gap-2">
          {vms.map((vm) => {
            const isExpanded = expandedId === vm.id
            const isPreflight = preflightVmId === vm.id

            return (
              <Card
                key={vm.id}
                className="flex flex-col overflow-hidden transition-all duration-200"
              >
                {/* Accordion Item Header (Click to Expand / Collapse) */}
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
                      size="sm"
                    />
                    <div className="flex flex-col min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-label font-bold text-ink truncate">
                          {vm.name}
                        </span>
                        <span
                          className={cx(
                            "inline-flex items-center gap-1 text-[9px] font-semibold rounded-full px-1.5 py-0.2 border",
                            !isOnline
                              ? "bg-surface-sunken text-ink-muted border-line"
                              : vm.status === "running"
                                ? "bg-success-soft text-success-ink border-success-line/60"
                                : vm.status === "sleeping"
                                  ? "bg-warning-soft text-warning-ink border-warning-line/60"
                                  : "bg-danger-soft text-danger-ink border-danger-line/60"
                          )}
                        >
                          <StatusDot
                            tone={
                              !isOnline
                                ? "neutral"
                                : vm.status === "running"
                                  ? "success"
                                  : vm.status === "sleeping"
                                    ? "warning"
                                    : "danger"
                            }
                            pulse={isOnline && vm.status === "running"}
                          />
                          {!isOnline
                            ? "Off"
                            : vm.status === "running"
                              ? "Active"
                              : vm.status === "sleeping"
                                ? "Sleep"
                                : "Cooldown"}
                        </span>
                      </div>
                      <span className="text-nano text-ink-subtle truncate">
                        {vm.specs.cpu.split(" ")[0]} {vm.specs.cpu.split(" ")[1]} · {vm.specs.ram}
                      </span>
                    </div>
                  </div>

                  {/* Header Trailing: Edit, Delete, Chevron */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleOpenEdit(vm)
                      }}
                      title={t("edit_vm_btn", "Edit")}
                      className="rounded p-1 text-ink-subtle hover:bg-surface-sunken hover:text-ink transition cursor-pointer"
                    >
                      <Pencil className="size-3" />
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setVmToDelete(vm)
                      }}
                      title={t("delete_vm_btn", "Hapus")}
                      className="rounded p-1 text-ink-subtle hover:bg-danger-soft hover:text-danger-bright transition cursor-pointer"
                    >
                      <Trash2 className="size-3" />
                    </button>
                    <span className="text-ink-subtle p-0.5">
                      {isExpanded ? (
                        <ChevronUp className="size-3.5" />
                      ) : (
                        <ChevronDown className="size-3.5" />
                      )}
                    </span>
                  </div>
                </div>

                {/* Accordion Expanded Body */}
                {isExpanded && (
                  <div className="flex flex-col gap-2 border-t border-line p-2.5 bg-surface-sunken/30 motion-safe:animate-fade-in">
                    {/* Specs & Hardware Detail */}
                    <div className="grid grid-cols-3 gap-1 rounded-tile border border-line bg-surface p-1.5 text-center text-nano">
                      <div className="flex flex-col">
                        <span className="text-ink-subtle uppercase text-[8px] font-semibold">CPU</span>
                        <span className="text-micro font-bold text-ink truncate">
                          {vm.specs.cpu.split(" ")[0]} {vm.specs.cpu.split(" ")[1]}
                        </span>
                      </div>
                      <div className="flex flex-col border-x border-line">
                        <span className="text-ink-subtle uppercase text-[8px] font-semibold">RAM</span>
                        <span className="text-micro font-bold text-ink truncate">
                          {vm.specs.ram}
                        </span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-ink-subtle uppercase text-[8px] font-semibold">NVMe</span>
                        <span className="text-micro font-bold text-ink truncate">
                          {vm.specs.storage}
                        </span>
                      </div>
                    </div>

                    {/* Runtime & Idle info */}
                    <div className="flex items-center justify-between text-nano text-ink-subtle px-1">
                      <span className="flex items-center gap-1 font-medium">
                        <Clock className="size-3 text-info" />
                        Sisa: {Math.floor((vm.maxRuntimeMinutes - vm.runtimeMinutes) / 60)}j{" "}
                        {(vm.maxRuntimeMinutes - vm.runtimeMinutes) % 60}m
                      </span>
                      <span className="font-mono text-ink">Port: {vm.sshPort}</span>
                    </div>

                    {/* Action buttons */}
                    <Button
                      block
                      variant="primary"
                      size="sm"
                      icon={isPreflight ? LoaderCircle : ExternalLink}
                      disabled={!isOnline}
                      onClick={() => handleLaunchAntigravity(vm)}
                    >
                      {isPreflight
                        ? t("vm_preflight_waking", "Membangunkan VM...")
                        : t("launch_antigravity_btn", "Buka Antigravity Remote")}
                    </Button>

                    <div className="grid grid-cols-2 gap-1.5">
                      <Button
                        size="sm"
                        variant={vm.status === "running" ? "soft" : "info"}
                        icon={Power}
                        disabled={!isOnline}
                        onClick={() => handleTogglePower(vm)}
                      >
                        {vm.status === "running"
                          ? t("sleep_vm_btn", "Tidurkan")
                          : t("wake_vm_btn", "Bangunkan")}
                      </Button>

                      <Button
                        size="sm"
                        variant="secondary"
                        icon={Terminal}
                        disabled={!isOnline}
                        onClick={() => handleCopySsh(vm)}
                      >
                        {t("open_ssh_btn", "SSH")}
                      </Button>
                    </div>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      {/* ========================================================= */}
      {/* POPUP MODAL 1: CONFIRM DELETE VM                          */}
      {/* ========================================================= */}
      {vmToDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3 backdrop-blur-xs"
          onClick={() => setVmToDelete(null)}
        >
          <div
            className="flex w-full max-w-[270px] flex-col gap-3 rounded-card border border-line bg-surface p-3.5 shadow-2xl motion-safe:animate-flyout-in select-none"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header with Danger Icon */}
            <div className="flex items-start justify-between border-b border-line pb-2">
              <div className="flex items-center gap-2">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-danger-soft text-danger-bright">
                  <AlertTriangle className="size-4" />
                </div>
                <div className="flex flex-col">
                  <span className="text-label font-bold text-ink">
                    {t("confirm_delete_vm_title", "Konfirmasi Hapus VM")}
                  </span>
                  <span className="text-nano text-ink-subtle">
                    {t("vm_section_title", "InstaBox Cloud")}
                  </span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setVmToDelete(null)}
                className="rounded p-1 text-ink-subtle hover:bg-surface-sunken hover:text-ink transition cursor-pointer"
              >
                <X className="size-3.5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex flex-col gap-2 text-caption">
              <p className="text-micro text-ink leading-relaxed">
                {t(
                  "confirm_delete_vm_desc",
                  "Apakah Anda yakin ingin menghapus virtual machine ini secara permanen?"
                )}
              </p>

              {/* Target Highlight */}
              <div className="rounded-tile border border-danger-line/60 bg-danger-soft/30 p-2 text-micro">
                <div className="font-bold text-ink truncate">{vmToDelete.name}</div>
                <div className="font-mono text-nano text-ink-subtle">
                  IP: {vmToDelete.ip} · SSH: {vmToDelete.sshPort}
                </div>
              </div>

              <span className="text-nano text-ink-muted leading-tight">
                {t("delete_vm_confirm_warning", "Kode atau task yang belum tersinkronisasi di VM ini akan hilang.")}
              </span>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 border-t border-line pt-2">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setVmToDelete(null)}
              >
                {t("cancel_btn", "Batal")}
              </Button>
              <Button
                size="sm"
                variant="danger"
                icon={Trash2}
                onClick={handleDeleteConfirm}
              >
                {t("delete_btn", "Hapus")}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* POPUP MODAL 2: ADD / EDIT VM FORM                         */}
      {/* ========================================================= */}
      {(isAddingVm || editingVm) && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3 backdrop-blur-xs"
          onClick={() => {
            setIsAddingVm(false)
            setEditingVm(null)
          }}
        >
          <div
            className="flex w-full max-w-[276px] flex-col gap-2.5 rounded-card border border-line bg-surface p-3.5 shadow-2xl motion-safe:animate-flyout-in select-none"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-line pb-2">
              <span className="text-label font-bold text-ink flex items-center gap-1.5">
                <Server className="size-3.5 text-info" />
                {editingVm
                  ? t("edit_vm_modal_title", "Edit Virtual Machine")
                  : t("add_vm_modal_title", "Tambah Virtual Machine")}
              </span>
              <button
                type="button"
                onClick={() => {
                  setIsAddingVm(false)
                  setEditingVm(null)
                }}
                className="rounded p-1 text-ink-subtle hover:bg-surface-sunken hover:text-ink transition cursor-pointer"
              >
                <X className="size-3.5" />
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSaveForm} className="flex flex-col gap-2">
              <div>
                <label className="block text-nano font-semibold text-ink-subtle mb-0.5">
                  {t("vm_name_label", "Nama VM")}
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-micro text-ink placeholder:text-ink-muted focus:border-info focus:outline-none"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-nano font-semibold text-ink-subtle mb-0.5">
                    {t("vm_ip_label", "Host / IP")}
                  </label>
                  <input
                    type="text"
                    value={formIp}
                    onChange={(e) => setFormIp(e.target.value)}
                    className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-micro text-ink font-mono focus:border-info focus:outline-none"
                    required
                  />
                </div>
                <div>
                  <label className="block text-nano font-semibold text-ink-subtle mb-0.5">
                    {t("vm_port_label", "Port SSH")}
                  </label>
                  <input
                    type="number"
                    value={formSshPort}
                    onChange={(e) => setFormSshPort(Number(e.target.value))}
                    className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-micro text-ink font-mono focus:border-info focus:outline-none"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-nano font-semibold text-ink-subtle mb-0.5">
                  {t("vm_antigravity_port_label", "Port Antigravity Remote")}
                </label>
                <input
                  type="number"
                  value={formAgPort}
                  onChange={(e) => setFormAgPort(Number(e.target.value))}
                  className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-micro text-ink font-mono focus:border-info focus:outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-nano font-semibold text-ink-subtle mb-0.5">
                  {t("vm_template_label", "Spesifikasi VM")}
                </label>
                <input
                  type="text"
                  value={formCpu}
                  onChange={(e) => setFormCpu(e.target.value)}
                  className="w-full rounded-md border border-line bg-surface-sunken px-2 py-1 text-micro text-ink focus:border-info focus:outline-none"
                />
              </div>

              {/* Actions */}
              <div className="mt-1 flex items-center justify-end gap-2 border-t border-line pt-2">
                <Button
                  size="sm"
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    setIsAddingVm(false)
                    setEditingVm(null)
                  }}
                >
                  {t("cancel_btn", "Batal")}
                </Button>
                <Button size="sm" variant="info" type="submit">
                  {t("save_btn", "Simpan")}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </ViewBody>
  )
}

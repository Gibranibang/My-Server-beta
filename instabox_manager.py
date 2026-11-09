"""
InstaBox & Antigravity Remote Manager for MyServer Desktop (v4.4.0 Beta)
Modul pengontrol siklus hidup microVM InstaBox (REST API v1), pre-flight wake,
pelacak batas runtime continuous 8 jam, dan pencegah cooldown (Smart Anti-Cooldown Guard).
"""

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# Base URL resmi InstaBox REST API
INSTABOX_API_BASE = "https://api.instabox.sh/v1"

# Inisialisasi logger fallback
try:
    import logger_manager
    logger = logger_manager
except Exception:
    logger = logging.getLogger("InstaBoxManager")

try:
    import config_manager
except Exception:
    config_manager = None


class InstaBoxManager:
    """Pengelola siklus hidup VM InstaBox dan integrasi Antigravity Remote."""

    @staticmethod
    def _get_config():
        """Membaca konfigurasi aplikasi secara dinamis."""
        if config_manager and hasattr(config_manager, "load_or_create_config"):
            return config_manager.load_or_create_config()
        return {}

    @staticmethod
    def _save_config(cfg):
        """Menyimpan konfigurasi aplikasi secara aman."""
        if config_manager and hasattr(config_manager, "save_config"):
            return config_manager.save_config(cfg)
        return False

    @classmethod
    def list_vms(cls):
        """
        Mengambil daftar virtual machine yang tersimpan dalam config.
        Jika belum ada konfigurasi VM, kembalikan daftar kosong (tanpa hardcoding).
        """
        cfg = cls._get_config()
        vms = cfg.get("instabox_vms", [])
        if not isinstance(vms, list):
            vms = []
        return vms

    @classmethod
    def get_vm(cls, vm_id):
        """Mencari VM berdasarkan ID."""
        vms = cls.list_vms()
        for v in vms:
            if v.get("id") == vm_id:
                return v
        return None

    @classmethod
    def add_vm(cls, vm_data):
        """
        Menambahkan virtual machine baru ke dalam konfigurasi pengguna.
        Format vm_data:
        {
            "name": str,
            "apiKey": str (ibk_...),
            "machineId": str (m_...),
            "ip": str,
            "sshPort": int (default 2222),
            "antigravityPort": int (default 8080),
            "specs": dict
        }
        """
        cfg = cls._get_config()
        vms = cfg.get("instabox_vms", [])
        if not isinstance(vms, list):
            vms = []

        vm_id = vm_data.get("id") or f"vm-{uuid.uuid4().hex[:8]}"
        new_vm = {
            "id": vm_id,
            "name": vm_data.get("name") or "InstaBox Cloud VM",
            "provider": "instabox",
            "apiKey": vm_data.get("apiKey", "").strip(),
            "machineId": vm_data.get("machineId", "").strip(),
            "ip": vm_data.get("ip", "").strip(),
            "sshPort": int(vm_data.get("sshPort") or 2222),
            "antigravityPort": int(vm_data.get("antigravityPort") or 8080),
            "specs": vm_data.get("specs") or {
                "cpu": "4 vCPU AMD EPYC",
                "ram": "8 GB DDR5",
                "storage": "20 GB NVMe"
            },
            "status": "sleeping",
            "runtimeMinutes": 0,
            "maxRuntimeMinutes": 480,
            "idleTimeoutMinutes": 30,
            "cooldownUntil": 0,
            "lastActive": "Just added"
        }

        vms.append(new_vm)
        cfg["instabox_vms"] = vms
        cls._save_config(cfg)
        logger.log_info(f"[InstaBox] Virtual Machine '{new_vm['name']}' ({vm_id}) berhasil ditambahkan.")
        return new_vm

    @classmethod
    def update_vm(cls, vm_id, updates):
        """Memperbarui pengaturan VM yang sudah tersimpan."""
        cfg = cls._get_config()
        vms = cfg.get("instabox_vms", [])
        target = None
        for v in vms:
            if v.get("id") == vm_id:
                target = v
                break

        if not target:
            return None

        # Update field yang diizinkan
        allowed_fields = ["name", "apiKey", "machineId", "ip", "sshPort", "antigravityPort", "specs", "status", "runtimeMinutes", "cooldownUntil"]
        for f in allowed_fields:
            if f in updates:
                target[f] = updates[f]

        cfg["instabox_vms"] = vms
        cls._save_config(cfg)
        logger.log_info(f"[InstaBox] Virtual Machine '{vm_id}' berhasil diperbarui.")
        return target

    @classmethod
    def delete_vm(cls, vm_id):
        """Menghapus VM dari konfigurasi."""
        cfg = cls._get_config()
        vms = cfg.get("instabox_vms", [])
        initial_len = len(vms)
        vms = [v for v in vms if v.get("id") != vm_id]
        if len(vms) < initial_len:
            cfg["instabox_vms"] = vms
            cls._save_config(cfg)
            logger.log_info(f"[InstaBox] Virtual Machine '{vm_id}' berhasil dihapus.")
            return True
        return False

    @classmethod
    def _api_request(cls, endpoint, method="GET", body=None, api_key=""):
        """
        Helper transmisi REST API ke https://api.instabox.sh/v1/
        Menyertakan Bearer token dan Idempotency-Key untuk mutasi aman.
        """
        if not api_key:
            return {"error": "API Key InstaBox belum dikonfigurasi.", "code": 401}

        url = f"{INSTABOX_API_BASE.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MyServer-Companion/4.4.0-Beta"
        }

        if method in ("POST", "PUT", "DELETE"):
            headers["Idempotency-Key"] = str(uuid.uuid4())

        data_bytes = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_text = resp.read().decode("utf-8")
                return json.loads(resp_text) if resp_text else {"status": "ok"}
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8") if hasattr(he, "read") else ""
            try:
                err_json = json.loads(err_body)
            except Exception:
                err_json = {"raw": err_body}
            logger.log_error(f"[InstaBox API] HTTP {he.code}: {err_json}")
            return {
                "error": err_json.get("message") or f"HTTP {he.code} {he.reason}",
                "code": he.code,
                "details": err_json,
                "retryAfterSeconds": err_json.get("retryAfterSeconds") or he.headers.get("Retry-After")
            }
        except Exception as ex:
            logger.log_error(f"[InstaBox API] Network error: {ex}")
            return {"error": str(ex), "code": 500}

    @classmethod
    def sync_vm_status(cls, vm_id):
        """
        Sinkronisasi status terkini VM dari API InstaBox.
        Memperbarui status running/sleeping/cooldown, uptime, dan sisa limit 8 jam.
        """
        vm = cls.get_vm(vm_id)
        if not vm:
            return {"error": f"VM ID '{vm_id}' tidak ditemukan.", "code": 404}

        machine_id = vm.get("machineId")
        api_key = vm.get("apiKey")
        if not machine_id or not api_key:
            # Jika belum ada machineId/apiKey, kembalikan data lokal
            return {"status": "ok", "vm": vm, "offline": True}

        res = cls._api_request(f"machines/{machine_id}", method="GET", api_key=api_key)
        if "error" in res:
            return res

        # Parsing status runtime
        machine_status = res.get("status", "sleeping")
        runtime_secs = res.get("currentRunSeconds", 0)
        runtime_mins = int(runtime_secs // 60)

        updates = {
            "status": machine_status,
            "runtimeMinutes": runtime_mins,
            "lastActive": "Just now" if machine_status == "running" else "Recently"
        }

        if res.get("ip"):
            updates["ip"] = res.get("ip")

        updated_vm = cls.update_vm(vm_id, updates)
        return {"status": "ok", "vm": updated_vm}

    @classmethod
    def resume_vm(cls, vm_id):
        """
        Membangunkan VM dari status idle pause (<1 detik).
        Menangani kasus batas cooldown jika telah mencapai 8 jam continuous.
        """
        vm = cls.get_vm(vm_id)
        if not vm:
            return {"error": f"VM ID '{vm_id}' tidak ditemukan.", "code": 404}

        machine_id = vm.get("machineId")
        api_key = vm.get("apiKey")
        if not machine_id or not api_key:
            # Mode simulasi/lokal jika kredensial belum diisi
            cls.update_vm(vm_id, {"status": "running", "lastActive": "Just now"})
            return {"status": "ok", "message": "VM simulasi berhasil dibangunkan.", "simulated": True}

        res = cls._api_request(f"machines/{machine_id}/resume", method="POST", body={}, api_key=api_key)
        if "error" in res:
            if res.get("code") == 409:
                retry_after = res.get("retryAfterSeconds", 300)
                cooldown_until = time.time() + retry_after
                cls.update_vm(vm_id, {"status": "cooldown", "cooldownUntil": cooldown_until})
                return {
                    "error": f"VM sedang dalam jeda pendinginan (cooldown). Sisa waktu: {int(retry_after//60)} menit.",
                    "code": 409,
                    "cooldownUntil": cooldown_until,
                    "retryAfterSeconds": retry_after
                }
            return res

        cls.update_vm(vm_id, {"status": "running", "lastActive": "Just now"})
        return {"status": "ok", "message": "VM berhasil dibangunkan."}

    @classmethod
    def pause_vm(cls, vm_id):
        """
        Mem-pause VM secara manual untuk menghemat batas harian dan mencegah cooldown paksa.
        """
        vm = cls.get_vm(vm_id)
        if not vm:
            return {"error": f"VM ID '{vm_id}' tidak ditemukan.", "code": 404}

        machine_id = vm.get("machineId")
        api_key = vm.get("apiKey")
        if not machine_id or not api_key:
            cls.update_vm(vm_id, {"status": "sleeping", "lastActive": "Just now"})
            return {"status": "ok", "message": "VM simulasi berhasil di-pause.", "simulated": True}

        res = cls._api_request(f"machines/{machine_id}/suspend", method="POST", body={}, api_key=api_key)
        if "error" in res:
            return res

        cls.update_vm(vm_id, {"status": "sleeping", "lastActive": "Just now"})
        return {"status": "ok", "message": "VM berhasil di-pause (tidur)."}

    @classmethod
    def preflight_launch(cls, vm_id, target_port=8080):
        """
        Pre-flight Launch Handler:
        Memastikan VM aktif sebelum membuka webapp Antigravity Remote.
        Jika mesin tidur $\to$ bangunkan terlebih dahulu, tunggu hingga running,
        lalu kembalikan URL tujuan.
        """
        vm = cls.get_vm(vm_id)
        if not vm:
            return {"error": f"VM ID '{vm_id}' tidak ditemukan.", "code": 404}

        current_status = vm.get("status", "sleeping")
        ip = vm.get("ip", "127.0.0.1")
        port = target_port or vm.get("antigravityPort", 8080)

        # 1. Jika VM sedang tidur, bangunkan otomatis
        if current_status != "running":
            resume_res = cls.resume_vm(vm_id)
            if "error" in resume_res:
                return resume_res

        # 2. Susun URL target akses Antigravity Remote
        # Jika menggunakan IP publik atau gateway InstaBox
        if ip and ip != "127.0.0.1":
            target_url = f"http://{ip}:{port}"
        else:
            target_url = f"http://localhost:{port}"

        return {
            "status": "ok",
            "message": "VM aktif dan siap diakses.",
            "url": target_url,
            "ip": ip,
            "port": port
        }

    @classmethod
    def smart_anti_cooldown_reset(cls, vm_id):
        """
        Siklus Pencegahan Cooldown:
        Pause mesin selama 2 detik lalu langsung me-resume kembali,
        sehingga counter continuous 8 jam di-reset dari nol tanpa terkena penalti cooldown wajib.
        """
        vm = cls.get_vm(vm_id)
        if not vm:
            return {"error": f"VM ID '{vm_id}' tidak ditemukan.", "code": 404}

        pause_res = cls.pause_vm(vm_id)
        if "error" in pause_res:
            return pause_res

        time.sleep(2)

        resume_res = cls.resume_vm(vm_id)
        if "error" in resume_res:
            return resume_res

        cls.update_vm(vm_id, {"runtimeMinutes": 0, "status": "running"})
        return {"status": "ok", "message": "Smart anti-cooldown reset berhasil! Timer 8 jam telah di-reset dari nol."}

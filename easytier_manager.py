"""
EasyTier Manager Module for MyServer Desktop Companion (Beta)
Pengontrol background daemon native EasyTier (easytier-core.exe) dan antarmuka
telemetri CLI (easytier-cli.exe) berbasis P2P mesh multi-protokol (UDP, TCP, WSS).
Mengadopsi standar embedded daemon Zima Client v2.3.5 untuk akses remote tanpa blokir firewall.
"""

import atexit
import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time

logger = logging.getLogger("EasyTierManager")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [EasyTierManager] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Default public discovery/relay nodes (fallback jika tidak ada custom relay)
DEFAULT_RELAY_PEERS = [
    "wss://39.96.54.49:443/",
    "wss://106.14.186.206:443/",
    "tcp://public.easytier.top:11010"
]

DEFAULT_RPC_PORT = 15888


def derive_easytier_params(remote_id: str):
    """
    Menurunkan network_name dan network_secret dari 16-digit Remote ID ZimaOS
    mengikuti standar integrasi ZimaNet di Zima Client v2.3.5.
    """
    clean_id = str(remote_id or "").strip().lower()
    if not clean_id:
        return {"network_name": "", "network_secret": "", "network_hash": "", "remote_id": ""}
    nhash = hashlib.sha256(f"zima-easytier-network-v1:{clean_id}".encode("utf-8")).hexdigest()
    net_name = f"zima-{clean_id}"
    net_secret = clean_id
    return {
        "network_name": net_name,
        "network_secret": net_secret,
        "network_hash": nhash,
        "remote_id": clean_id,
    }


def find_easytier_binaries():
    """
    Menemukan lokasi biner easytier-core.exe dan easytier-cli.exe
    baik di lingkungan development maupun bundle distribusi PyInstaller / Inno Setup.
    """
    candidates = []

    # 1. Lokasi PyInstaller temporary folder (_MEIPASS)
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "resources", "deps", "easytier", "win32", "x64"))

    # 2. Lokasi direktori executable (misal D:\Softwares\MyServer atau D:\Projek\MyServer\Beta\dist)
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidates.append(os.path.join(exe_dir, "resources", "deps", "easytier", "win32", "x64"))
    candidates.append(os.path.join(exe_dir, "easytier"))

    # 3. Lokasi direktori script saat ini (D:\Projek\MyServer\Beta)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(base_dir, "resources", "deps", "easytier", "win32", "x64"))
    candidates.append(os.path.join(base_dir, "dist", "resources", "deps", "easytier", "win32", "x64"))

    for c in candidates:
        core_exe = os.path.join(c, "easytier-core.exe")
        cli_exe = os.path.join(c, "easytier-cli.exe")
        if os.path.exists(core_exe) and os.path.exists(cli_exe):
            return {
                "base_dir": c,
                "core_path": core_exe,
                "cli_path": cli_exe,
                "wintun_path": os.path.join(c, "wintun.dll")
            }

    return None


class EasyTierManager:
    """Pengelola siklus hidup daemon EasyTier P2P Mesh."""

    def __init__(self):
        self._lock = threading.Lock()
        self._proc = None
        self._remote_id = None
        self._network_name = None
        self._network_secret = None
        self._ipv4 = None
        self._rpc_port = DEFAULT_RPC_PORT
        self._start_time = None
        self._binaries = find_easytier_binaries()

    def is_available(self):
        """Memeriksa apakah biner EasyTier tersedia di sistem."""
        if not self._binaries:
            self._binaries = find_easytier_binaries()
        return self._binaries is not None

    def get_binary_info(self):
        """Mengembalikan path dan versi biner EasyTier."""
        if not self.is_available():
            return {"available": False, "version": None, "error": "Biner EasyTier tidak ditemukan."}

        cli_path = self._binaries["cli_path"]
        try:
            res = subprocess.run(
                [cli_path, "--version"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=0x08000000 if os.name == "nt" else 0
            )
            version_str = res.stdout.strip()
            return {
                "available": True,
                "version": version_str,
                "core_path": self._binaries["core_path"],
                "cli_path": cli_path
            }
        except Exception as e:
            return {"available": True, "version": "unknown", "error": str(e)}

    def is_running(self):
        """Memeriksa apakah daemon EasyTier saat ini aktif."""
        with self._lock:
            if self._proc is not None:
                poll = self._proc.poll()
                if poll is None:
                    return True
                self._proc = None
            return False

    def start(self, network_name=None, network_secret=None, ipv4=None, peers=None, rpc_port=DEFAULT_RPC_PORT, remote_id=None):
        """
        Meluncurkan daemon easytier-core.exe secara headless di background.
        Mendukung peluncuran via remote_id ZimaOS (mengikuti standar Zima Client)
        maupun konfigurasi network_name & network_secret manual.
        """
        with self._lock:
            if not self.is_available():
                return False, "Biner EasyTier tidak ditemukan di resources/deps/easytier."

            clean_rid = str(remote_id or "").strip().lower()
            if clean_rid:
                params = derive_easytier_params(clean_rid)
                target_net_name = params["network_name"]
                target_net_secret = params["network_secret"]
            else:
                target_net_name = str(network_name or "").strip()
                target_net_secret = str(network_secret or "").strip()

            if not target_net_name:
                return False, "Parameter Remote ID atau Network Name wajib diisi."

            if self._proc is not None and self._proc.poll() is None:
                # Sudah berjalan, jika konfigurasi sama, gunakan yang ada
                if self._network_name == target_net_name and self._network_secret == target_net_secret:
                    logger.info("EasyTier daemon sudah berjalan dengan konfigurasi yang sama.")
                    return True, "Daemon sudah aktif."
                else:
                    logger.info("Konfigurasi berubah, me-restart EasyTier daemon...")
                    self._stop_internal()

            # Bersihkan proses yatim jika ada
            self._kill_orphaned_daemon()

            self._remote_id = clean_rid if clean_rid else None
            self._network_name = target_net_name
            self._network_secret = target_net_secret
            self._ipv4 = str(ipv4).strip() if ipv4 else None
            self._rpc_port = int(rpc_port)

            core_exe = self._binaries["core_path"]
            working_dir = self._binaries["base_dir"]

            cmd = [
                core_exe,
                "--network-name", self._network_name,
                "--network-secret", self._network_secret,
                "-r", f"127.0.0.1:{self._rpc_port}",
                "--listeners", "wss://0.0.0.0:0", "tcp://0.0.0.0:0", "udp://0.0.0.0:0"
            ]

            if self._ipv4:
                cmd.extend(["-i", self._ipv4])
            else:
                cmd.extend(["-d", "true"])  # DHCP auto-assign IP

            # Tambahkan relay peers
            relay_list = list(peers) if peers else DEFAULT_RELAY_PEERS
            for p in relay_list:
                clean_p = str(p).strip()
                if clean_p:
                    cmd.extend(["-p", clean_p])

            logger.info("Meluncurkan EasyTier Core: %s (network=%s)", core_exe, self._network_name)

            creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
            try:
                # Log ke file lokal agar tidak membanjiri stdout
                log_dir = os.path.expandvars(r"%LOCALAPPDATA%\MyServer\logs")
                os.makedirs(log_dir, exist_ok=True)
                stdout_log = open(os.path.join(log_dir, "easytier.stdout.log"), "w", encoding="utf-8")
                stderr_log = open(os.path.join(log_dir, "easytier.stderr.log"), "w", encoding="utf-8")

                self._proc = subprocess.Popen(
                    cmd,
                    cwd=working_dir,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    creationflags=creationflags
                )
                self._start_time = time.time()
                time.sleep(0.8)  # Tunggu socket init

                if self._proc.poll() is not None:
                    return False, f"EasyTier daemon gagal dijalankan (exit code: {self._proc.returncode})"

                logger.info("EasyTier daemon berhasil aktif dengan PID: %d", self._proc.pid)
                return True, f"EasyTier aktif (PID: {self._proc.pid})"
            except Exception as e:
                logger.error("Gagal meluncurkan EasyTier Core: %s", e)
                return False, str(e)

    def stop(self):
        """Menghentikan daemon EasyTier dan membersihkan virtual interface."""
        with self._lock:
            return self._stop_internal()

    def _stop_internal(self):
        if self._proc is None:
            self._kill_orphaned_daemon()
            return True, "Daemon tidak sedang berjalan."

        pid = self._proc.pid
        logger.info("Menghentikan EasyTier daemon (PID: %d)...", pid)
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                logger.warning("EasyTier tidak keluar setelah 3s, melakukan force kill...")
                self._proc.kill()
                self._proc.wait(timeout=1.0)
        except Exception as e:
            logger.error("Error saat menghentikan daemon: %s", e)
        finally:
            self._proc = None
            self._start_time = None

        self._kill_orphaned_daemon()
        return True, "EasyTier daemon berhasil dihentikan."

    def _kill_orphaned_daemon(self):
        """Membunuh proses easytier-core.exe yatim dari sesi sebelumnya jika ada."""
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "easytier-core.exe"],
                    capture_output=True,
                    timeout=2,
                    creationflags=0x08000000
                )
            except Exception:
                pass

    def run_cli(self, args, timeout=3.5):
        """
        Menjalankan perintah easytier-cli dengan opsi format JSON.
        Contoh: run_cli(["peer"]) atau run_cli(["route"])
        """
        if not self.is_available():
            return None, "Biner easytier-cli tidak ditemukan."

        cli_path = self._binaries["cli_path"]
        cmd = [cli_path, "-p", f"127.0.0.1:{self._rpc_port}", "-o", "json"] + args

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=0x08000000 if os.name == "nt" else 0
            )
            if res.returncode == 0:
                raw_out = res.stdout.strip()
                if not raw_out:
                    return {}, None
                try:
                    return json.loads(raw_out), None
                except json.JSONDecodeError:
                    return {"raw": raw_out}, None
            return None, res.stderr.strip() or f"CLI returned code {res.returncode}"
        except subprocess.TimeoutExpired:
            return None, "CLI query timeout."
        except Exception as e:
            return None, str(e)

    def get_node_info(self):
        """Mengambil data status node lokal."""
        if not self.is_running():
            return {
                "running": False,
                "network_name": self._network_name,
                "virtual_ipv4": None,
                "uptime": 0
            }

        data, err = self.run_cli(["node", "info"])
        if not data:
            data, err = self.run_cli(["node"])
        uptime = int(time.time() - self._start_time) if self._start_time else 0
        if data and isinstance(data, dict):
            vip = data.get("ipv4_addr") or data.get("ipv4") or self._ipv4
            return {
                "running": True,
                "network_name": self._network_name,
                "virtual_ipv4": vip,
                "hostname": data.get("hostname", ""),
                "node_id": str(data.get("peer_id") or data.get("node_id") or ""),
                "uptime": uptime,
                "raw": data
            }

        return {
            "running": True,
            "network_name": self._network_name,
            "virtual_ipv4": self._ipv4,
            "uptime": uptime,
            "error": err
        }

    def get_peers(self):
        """Mengambil daftar peer aktif dari jaringan mesh."""
        if not self.is_running():
            return []

        data, err = self.run_cli(["peer", "list"])
        if not data:
            data, err = self.run_cli(["peer"])
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "peers" in data:
            return data["peers"]
        return []

    def get_routes(self):
        """Mengambil tabel rute mesh EasyTier."""
        if not self.is_running():
            return []

        data, err = self.run_cli(["route", "list"])
        if not data:
            data, err = self.run_cli(["route"])
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "routes" in data:
            return data["routes"]
        return []

    def get_peer_ip(self):
        """Mencari alamat IPv4 dari peer server di jaringan mesh EasyTier."""
        if not self.is_running():
            return None
        node_info = self.get_node_info()
        local_ip = str(node_info.get("virtual_ipv4") or self._ipv4 or "").split("/")[0].strip()
        routes = self.get_routes()
        for r in routes:
            if isinstance(r, dict):
                ipv4 = r.get("ipv4") or r.get("ipv4_addr") or r.get("ip") or r.get("peer_ipv4")
                if ipv4:
                    clean = str(ipv4).split("/")[0].strip()
                    if clean and clean != local_ip and not clean.startswith("127."):
                        return clean
        peers = self.get_peers()
        for p in peers:
            if isinstance(p, dict):
                ipv4 = p.get("ipv4") or p.get("ipv4_addr") or p.get("ip") or p.get("peer_ipv4")
                if ipv4:
                    clean = str(ipv4).split("/")[0].strip()
                    if clean and clean != local_ip and not clean.startswith("127."):
                        return clean
        return None

    def get_summary(self):
        """Mengambil ringkasan telemetri komprehensif untuk antarmuka UI."""
        running = self.is_running()
        if not running:
            return {
                "running": False,
                "available": self.is_available(),
                "remote_id": self._remote_id,
                "network_name": self._network_name,
                "virtual_ipv4": None,
                "virtual_ip": None,
                "peers_count": 0,
                "peers": []
            }

        peers = self.get_peers()
        node_info = self.get_node_info()
        vip = node_info.get("virtual_ipv4") or self._ipv4
        return {
            "running": True,
            "available": True,
            "remote_id": self._remote_id,
            "network_name": self._network_name,
            "virtual_ipv4": vip,
            "virtual_ip": vip,
            "uptime": node_info.get("uptime", 0),
            "peers_count": len(peers),
            "peers": peers,
            "server_peer_ip": self.get_peer_ip()
        }


    def get_status_overview(self):
        """Alias untuk get_summary() demi kompatibilitas penuh."""
        return self.get_summary()

    def start_easytier(self, network_name=None, network_secret=None, ipv4=None, peers=None, use_no_tun=False, external_node=None, rpc_port=DEFAULT_RPC_PORT, remote_id=None):
        """Alias untuk start() dengan parameter fleksibel."""
        return self.start(network_name=network_name, network_secret=network_secret, ipv4=ipv4, peers=peers, rpc_port=rpc_port, remote_id=remote_id)

    def stop_easytier(self):
        """Alias untuk stop() demi kompatibilitas penuh."""
        return self.stop()

    def get_full_status(self):
        """Alias untuk get_summary() demi kompatibilitas penuh."""
        return self.get_summary()


# Global Singleton
_easytier_instance = None
_easytier_instance_lock = threading.Lock()


def get_easytier_manager():
    global _easytier_instance
    with _easytier_instance_lock:
        if _easytier_instance is None:
            _easytier_instance = EasyTierManager()
            atexit.register(_easytier_instance.stop)
        return _easytier_instance


easytier_instance = get_easytier_manager()

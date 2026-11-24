"""
EasyTier Manager Module for MyServer Desktop Companion (Beta)
Pengontrol background daemon native EasyTier (easytier-core.exe) dan antarmuka
telemetri CLI (easytier-cli.exe) berbasis P2P mesh multi-protokol (UDP, TCP, WSS).
Mengadopsi standar embedded daemon Zima Client v2.3.5 untuk akses remote tanpa blokir firewall.
"""

import atexit
import copy
import ctypes
import hashlib
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

logger = logging.getLogger("EasyTierManager")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [EasyTierManager] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Default public discovery/relay nodes (UDP-first regional relays before TCP; overseas WSS last)
DEFAULT_RELAY_PEERS = [
    "udp://139.162.29.247:11010",
    "udp://103.29.68.33:11010",
    "udp://172.239.28.141:11010",
    "tcp://139.162.29.247:11010",
    "tcp://103.29.68.33:11010",
    "tcp://172.239.28.141:11010",
    "tcp://public.easytier.top:11010",
    "wss://39.96.54.49:443/",
    "wss://106.14.186.206:443/",
]

DEFAULT_RPC_PORT = 15888
SUMMARY_CACHE_TTL_SEC = 12.0
NO_TUN_SMB_WARNING = (
    "EasyTier berjalan dalam mode --no-tun (adapter Wintun tidak aktif). "
    "Akses drive SMB via EasyTier memerlukan izin Administrator/UAC, atau gunakan LAN / ZeroTier."
)


def derive_easytier_params(remote_id: str):
    """
    Menurunkan network_name dan network_secret dari 16-digit Remote ID ZimaOS
    mengikuti standar integrasi ZimaNet di Zima Client v2.3.5.
    ZimaOS menggunakan 16-karakter Remote ID murni sebagai network_name dan network_secret.
    """
    clean_id = str(remote_id or "").strip().lower()
    if not clean_id:
        return {"network_name": "", "network_secret": "", "network_hash": "", "remote_id": ""}
    nhash = hashlib.sha256(f"zima-easytier-network-v1:{clean_id}".encode("utf-8")).hexdigest()
    return {
        "network_name": clean_id,
        "network_secret": clean_id,
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

    # 2. Lokasi direktori executable (misal <AppInstallDir> atau <RepoDir>/dist)
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidates.append(os.path.join(exe_dir, "resources", "deps", "easytier", "win32", "x64"))
    candidates.append(os.path.join(exe_dir, "easytier"))

    # 3. Lokasi direktori script saat ini (<RepoDir>)
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
        self._lock = threading.RLock()
        self._proc = None
        self._remote_id = None
        self._network_name = None
        self._network_secret = None
        self._ipv4 = None
        self._rpc_port = DEFAULT_RPC_PORT
        self._start_time = None
        self._tun_active = False
        self._no_tun_fallback = False
        self._disable_p2p = False
        self._p2p_failure_streak = 0
        self._last_peer_bytes = (0, 0)
        self._last_traffic_ts = 0.0
        self._last_start_kwargs = {}
        self._binaries = find_easytier_binaries()
        self._cached_summary = None
        self._cached_summary_ts = 0.0
        self._cli_cache = {}
        self._cli_verb_pref = {}
        self._local_host_ips_cache = None
        self._local_host_ips_ts = 0.0
        self._peer_reach_cache = {}

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
        """Memeriksa apakah daemon EasyTier saat ini aktif merespons RPC portal."""
        return self._is_rpc_reachable()

    def is_tun_active(self):
        """Mengembalikan True bila adapter Wintun aktif (atau daemon eksternal Admin), False saat --no-tun."""
        if self._no_tun_fallback:
            return False
        return bool(self._tun_active if self._start_time is not None else True)

    def _is_rpc_reachable(self):
        """Cek cepat apakah RPC portal 127.0.0.1:port aktif merespons (short socket timeout 0.15s)."""
        try:
            with socket.create_connection(("127.0.0.1", self._rpc_port), timeout=0.15):
                return True
        except Exception:
            return False

    def _is_process_running(self, name):
        if os.name == "nt":
            try:
                res = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {name}.exe"],
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                    creationflags=0x08000000
                )
                return f"{name}.exe" in res.stdout
            except Exception:
                return False
        return False

    def start(self, network_name=None, network_secret=None, ipv4=None, peers=None, rpc_port=DEFAULT_RPC_PORT, remote_id=None, use_no_tun=False, external_node=None, lazy_p2p=False, disable_p2p=False, _from_tun_fallback=False):
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

            if not _from_tun_fallback and self.is_running():
                eff_disable = bool(disable_p2p or self._p2p_failure_streak >= 3)
                if self._network_name == target_net_name and self._network_secret == target_net_secret and self._tun_active == (not bool(use_no_tun)) and self._disable_p2p == eff_disable:
                    logger.info("EasyTier daemon sudah berjalan dengan konfigurasi yang sama.")
                    return True, "Daemon sudah aktif."
                else:
                    logger.info("Konfigurasi berubah, me-restart EasyTier daemon...")
                    self._stop_internal()

            # Bersihkan proses lama jika ada
            self._kill_orphaned_daemon()

            self._remote_id = clean_rid if clean_rid else None
            self._network_name = target_net_name
            self._network_secret = target_net_secret
            self._rpc_port = int(rpc_port)

            core_exe = self._binaries["core_path"]
            working_dir = self._binaries["base_dir"]

            cmd = [
                core_exe,
                "--network-name", self._network_name,
                "--network-secret", self._network_secret,
                "-r", f"127.0.0.1:{self._rpc_port}",
                "-l", "udp://0.0.0.0:0",
                "-l", "tcp://0.0.0.0:0",
                "-l", "wss://0.0.0.0:0",
            ]
            if lazy_p2p:
                cmd.append("--lazy-p2p")

            if use_no_tun:
                cmd.append("--no-tun")
            if external_node:
                cmd.extend(["--external-node", str(external_node).strip()])

            # Konfigurasi IP Virtual EasyTier:
            # Sesuai standar Zima Client v2.3.5 dan topologi ZimaOS:
            # - Host ZimaOS berjalan di 10.126.126.1
            # - Klien desktop diberi IP awal 10.126.126.2/24 dengan flag -d untuk DHCP dynamic fallback.
            # JANGAN PERNAH gunakan -d sendirian tanpa -i, karena EasyTier DHCP akan mengalokasikan .1
            # ke klien lokal pertama, yang menyebabkan tabrakan IP dengan server ZimaOS.
            clean_ipv4 = str(ipv4 or "").strip()
            if clean_ipv4 and clean_ipv4.lower() != "dhcp":
                self._ipv4 = clean_ipv4
                cmd.extend(["-i", self._ipv4])
            else:
                self._ipv4 = "10.126.126.2/24"
                cmd.extend(["-i", self._ipv4, "-d"])

            # Gabungkan relay peers standar IceWhale + public relays
            relay_list = list(peers) if peers else DEFAULT_RELAY_PEERS
            for p in relay_list:
                clean_p = str(p).strip()
                if clean_p:
                    cmd.extend(["-p", clean_p])

            eff_disable_p2p = bool(disable_p2p or self._p2p_failure_streak >= 3)
            self._disable_p2p = eff_disable_p2p
            if eff_disable_p2p:
                cmd.append("--disable-p2p")

            self._last_start_kwargs = {
                "network_name": network_name,
                "network_secret": network_secret,
                "ipv4": ipv4,
                "peers": peers,
                "rpc_port": rpc_port,
                "remote_id": remote_id,
                "use_no_tun": use_no_tun,
                "external_node": external_node,
                "lazy_p2p": lazy_p2p,
            }

            logger.info("Meluncurkan EasyTier Core: %s (network=%s, ip=%s, no_tun=%s, disable_p2p=%s)", core_exe, self._network_name, self._ipv4 or "dhcp", use_no_tun, eff_disable_p2p)

            is_admin = False
            if os.name == "nt":
                try:
                    is_admin = (ctypes.windll.shell32.IsUserAnAdmin() != 0)
                except Exception:
                    is_admin = False

            creationflags = 0x08000000 if os.name == "nt" else 0
            try:
                if use_no_tun or is_admin or os.name != "nt":
                    # Mode tanpa TUN atau sudah Admin: dapat langsung dijalankan tanpa prompt UAC
                    local_app_data = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
                    if local_app_data:
                        log_dir = os.path.join(local_app_data, "MyServer", "logs")
                    else:
                        log_dir = os.path.join(tempfile.gettempdir(), "MyServer", "logs")
                    stdout_log = None
                    stderr_log = None
                    try:
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
                    finally:
                        for fh in (stdout_log, stderr_log):
                            if fh is not None:
                                try:
                                    fh.close()
                                except Exception:
                                    pass
                else:
                    # Mode dengan TUN membutuhkan elevasi UAC untuk membuat Wintun interface
                    logger.info("Proses berjalan tanpa hak Admin -> Meluncurkan EasyTier dengan elevasi ShellExecuteW RunAs...")
                    args_str = subprocess.list2cmdline(cmd[1:])
                    ret = ctypes.windll.shell32.ShellExecuteW(
                        None,
                        "runas",
                        core_exe,
                        args_str,
                        working_dir,
                        0  # SW_HIDE
                    )
                    if ret <= 32:
                        logger.warning("ShellExecuteW RunAs dikembalikan kode <= 32 (%d). Mencoba fallback powershell...", ret)
                        ps_cmd = f"Start-Process -FilePath '{core_exe}' -ArgumentList '{args_str}' -WorkingDirectory '{working_dir}' -Verb RunAs -WindowStyle Hidden"
                        subprocess.run(
                            ["powershell", "-NoProfile", "-Command", ps_cmd],
                            capture_output=True,
                            timeout=5
                        )

                self._start_time = time.time()
                self._cached_summary = None
                self._cached_summary_ts = 0.0

                # Berikan waktu tunggu RPC responsif (hingga 12 detik jika lewat UAC, 4 detik jika child langsung)
                max_checks = 60 if (not is_admin and not use_no_tun and os.name == "nt") else 20
                for _ in range(max_checks):
                    time.sleep(0.2)
                    if self._is_rpc_reachable():
                        self._tun_active = not bool(use_no_tun)
                        self._no_tun_fallback = bool(use_no_tun or _from_tun_fallback)
                        logger.info("EasyTier daemon berhasil aktif dan RPC reachable (tun_active=%s).", self._tun_active)
                        return True, "EasyTier aktif."
                    if self._proc is not None and self._proc.poll() is not None:
                        break

                if self._is_rpc_reachable():
                    self._tun_active = not bool(use_no_tun)
                    self._no_tun_fallback = bool(use_no_tun or _from_tun_fallback)
                    self._cli_cache.clear()
                    self._peer_reach_cache.clear()
                    return True, "EasyTier aktif."

                # Jika UAC gagal atau TUN gagal dibuat, coba fallback otomatis ke mode --no-tun
                if not use_no_tun and os.name == "nt":
                    logger.warning("EasyTier TUN gagal aktif. Mencoba fallback ke mode --no-tun (sub-node proxy)...")
                    return self.start(
                        network_name=network_name,
                        network_secret=network_secret,
                        ipv4=ipv4,
                        peers=peers,
                        rpc_port=rpc_port,
                        remote_id=remote_id,
                        use_no_tun=True,
                        external_node=external_node,
                        lazy_p2p=lazy_p2p,
                        disable_p2p=disable_p2p,
                        _from_tun_fallback=True,
                    )

                logger.warning("EasyTier RPC portal belum merespons setelah inisialisasi.")
                return False, "Gagal membuat virtual TUN adapter. Pastikan izin Administrator diberikan saat prompt UAC muncul."
            except Exception as e:
                logger.error("Gagal meluncurkan EasyTier Core: %s", e)
                return False, str(e)

    def stop(self):
        """Menghentikan daemon EasyTier dan membersihkan virtual interface."""
        with self._lock:
            return self._stop_internal()

    def _stop_internal(self):
        if self._proc is not None:
            pid = self._proc.pid
            logger.info("Menghentikan EasyTier daemon child (PID: %d)...", pid)
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=1.0)
            except Exception as e:
                logger.error("Error saat menghentikan child daemon: %s", e)
            finally:
                self._proc = None

        self._start_time = None
        self._tun_active = False
        self._no_tun_fallback = False
        self._cached_summary = None
        self._cached_summary_ts = 0.0
        self._cli_cache = {}
        self._cli_verb_pref = {}
        self._local_host_ips_cache = None
        self._local_host_ips_ts = 0.0
        self._peer_reach_cache = {}
        self._kill_orphaned_daemon()
        return True, "EasyTier daemon berhasil dihentikan."

    def _kill_orphaned_daemon(self):
        """Membunuh proses easytier-core.exe dari sesi sebelumnya jika ada."""
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
            if self._is_process_running("easytier-core"):
                try:
                    ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", "/c taskkill /F /IM easytier-core.exe", "", 0)
                except Exception:
                    pass

    def run_cli(self, args, timeout=2.0):
        """
        Menjalankan perintah easytier-cli dengan opsi format JSON.
        Melakukan short-circuit cek RPC portal agar tidak pernah timeout jika daemon mati.
        """
        if not self.is_available():
            return None, "Biner easytier-cli tidak ditemukan."
        if not self._is_rpc_reachable():
            return None, "RPC portal tidak aktif."

        cli_path = self._binaries["cli_path"]
        cmd = [cli_path, "--rpc-portal", f"127.0.0.1:{self._rpc_port}", "--output", "json"] + args

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

    def _query_cli_cached(self, cache_key, primary_args, fallback_args, ttl_sec=2.0):
        """Menjalankan query easytier-cli dengan memori subcommand & TTL cache singkat untuk mencegah badai fork."""
        now_m = time.time() if getattr(time.time, "__module__", "time") != "time" else time.monotonic()
        with self._lock:
            entry = self._cli_cache.get(cache_key)
            if entry is not None and (now_m - entry[0]) < ttl_sec:
                return entry[1], None
            pref = self._cli_verb_pref.get(cache_key)

        arg_order = [primary_args, fallback_args]
        if pref == tuple(fallback_args):
            arg_order = [fallback_args, primary_args]

        data = None
        err = None
        used_args = None
        for idx, cand_args in enumerate(arg_order):
            data, err = self.run_cli(list(cand_args))
            if data is not None:
                used_args = tuple(cand_args)
                break
            if idx == 0 and arg_order[1] == arg_order[0]:
                break

        with self._lock:
            if used_args is not None:
                self._cli_verb_pref[cache_key] = used_args
                now_store = time.time() if getattr(time.time, "__module__", "time") != "time" else time.monotonic()
                self._cli_cache[cache_key] = (now_store, data)
        return data, err

    def get_node_info(self):
        """Mengambil data status node lokal."""
        if not self.is_running():
            return {
                "running": False,
                "network_name": self._network_name,
                "virtual_ipv4": None,
                "uptime": 0
            }

        data, err = self._query_cli_cached("node", ["node", "info"], ["node"], ttl_sec=2.0)
        uptime = int(time.time() - self._start_time) if self._start_time else 0
        if data and isinstance(data, dict):
            raw_vip = data.get("virtual_ipv4") or data.get("ipv4_addr") or data.get("ipv4") or self._ipv4 or "10.126.126.2"
            clean_vip = str(raw_vip).split("/")[0].strip()
            return {
                "running": True,
                "network_name": self._network_name,
                "virtual_ipv4": clean_vip,
                "hostname": data.get("hostname", ""),
                "node_id": str(data.get("peer_id") or data.get("node_id") or ""),
                "uptime": uptime,
                "raw": data
            }

        fallback_ip = str(self._ipv4 or "10.126.126.2").split("/")[0].strip()
        return {
            "running": True,
            "network_name": self._network_name,
            "virtual_ipv4": fallback_ip,
            "uptime": uptime,
            "error": err
        }

    def get_peers(self):
        """Mengambil daftar peer aktif dari jaringan mesh."""
        if not self.is_running():
            return []

        data, err = self._query_cli_cached("peers", ["peer", "list"], ["peer"], ttl_sec=2.0)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            if "peers" in data and isinstance(data["peers"], list):
                return data["peers"]
            if "items" in data and isinstance(data["items"], list):
                return data["items"]
        return []

    def get_routes(self):
        """Mengambil tabel rute mesh EasyTier."""
        if not self.is_running():
            return []

        data, err = self._query_cli_cached("routes", ["route", "list"], ["route"], ttl_sec=2.0)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            if "routes" in data and isinstance(data["routes"], list):
                return data["routes"]
            if "items" in data and isinstance(data["items"], list):
                return data["items"]
        return []

    def get_remote_id(self):
        """Mengembalikan Remote ID jaringan EasyTier yang sedang aktif berjalan."""
        return self._remote_id

    def get_network_name(self):
        """Mengembalikan Network Name jaringan EasyTier yang sedang aktif berjalan."""
        return self._network_name

    def _get_local_machine_ips(self):
        """Membaca daftar IP adaptor lokal dengan TTL 30s (tanpa query DNS hostname berulang)."""
        host_fn_mocked = getattr(socket.gethostbyname_ex, "__module__", "socket") != "socket"
        now_m = time.monotonic()
        if not host_fn_mocked and self._local_host_ips_cache is not None and (now_m - self._local_host_ips_ts) < 30.0:
            return set(self._local_host_ips_cache)
        ips = set()
        try:
            h_name = socket.gethostname()
            for ip_cand in socket.gethostbyname_ex(h_name)[2]:
                ips.add(ip_cand)
        except Exception:
            pass
        if not host_fn_mocked:
            self._local_host_ips_cache = set(ips)
            self._local_host_ips_ts = now_m
        return ips

    def get_peer_ip(self, target_ip=None, target_hostname=None):
        """
        Mencari alamat IPv4 dari peer server di jaringan mesh EasyTier.
        - Jika target_ip diberikan, validasi apakah target_ip tersebut ada di tabel rute/peer atau merespons.
        - Jika target_hostname diberikan, cari peer yang nama host-nya cocok.
        - Jika tanpa parameter, ambil peer pertama yang bukan merupakan IP lokal adapter mesin sendiri.
        """
        if not self.is_running():
            return None
        node_info = self.get_node_info()
        local_ip = str(node_info.get("virtual_ipv4") or self._ipv4 or "").split("/")[0].strip()

        # Kumpulkan IP lokal mesin agar tidak pernah keliru mendeteksi adapter sendiri sebagai remote server
        local_ips = {"127.0.0.1", "0.0.0.0"}
        if local_ip:
            local_ips.add(local_ip)
        local_ips.update(self._get_local_machine_ips())

        clean_target = str(target_ip or "").split("/")[0].strip()
        if clean_target and clean_target in local_ips:
            return None

        routes = self.get_routes()
        peers = self.get_peers()
        all_entries = list(routes) + list(peers)

        # 1. Jika target_ip spesifik diminta, cek apakah ada di entri atau dapat dijangkau
        if clean_target:
            for item in all_entries:
                if isinstance(item, dict):
                    ipv4 = item.get("ipv4_addr") or item.get("ipv4") or item.get("ip") or item.get("peer_ipv4")
                    if ipv4 and str(ipv4).split("/")[0].strip() == clean_target:
                        return clean_target
            # Validasi apakah target_ip merespons HTTP port 80 jika belum sinkron di CLI
            if self.is_peer_reachable(clean_target, timeout=0.2):
                return clean_target
            return None

        # 2. Jika target_hostname diminta, cari kecocokan nama host
        if target_hostname:
            cand_host = target_hostname.strip().lower()
            for item in all_entries:
                if isinstance(item, dict):
                    h = str(item.get("hostname") or item.get("name") or "").strip().lower()
                    if h and (h == cand_host or cand_host in h or h in cand_host):
                        ipv4 = item.get("ipv4_addr") or item.get("ipv4") or item.get("ip") or item.get("peer_ipv4")
                        if ipv4:
                            clean = str(ipv4).split("/")[0].strip()
                            if clean and clean not in local_ips and not clean.startswith("127."):
                                return clean

        # 3. Fallback: ambil peer pertama yang valid dan bukan mesin lokal
        for item in all_entries:
            if isinstance(item, dict):
                ipv4 = item.get("ipv4_addr") or item.get("ipv4") or item.get("ip") or item.get("peer_ipv4")
                if ipv4:
                    clean = str(ipv4).split("/")[0].strip()
                    if clean and clean not in local_ips and not clean.startswith("127."):
                        return clean
        return None

    def is_peer_reachable(self, target_ip=None, timeout=0.3):
        """Memeriksa apakah peer server EasyTier benar-benar merespons web server (port 80)."""
        if not self.is_running():
            return False
        peer_ip = target_ip or self.get_peer_ip()
        if not peer_ip:
            return False

        # Jangan pernah menguji adapter sendiri atau loopback
        node_info = self.get_node_info()
        local_ip = str(node_info.get("virtual_ipv4") or self._ipv4 or "").split("/")[0].strip()
        if peer_ip == local_ip or peer_ip.startswith("127."):
            return False

        conn_mocked = getattr(socket.create_connection, "__module__", "socket") != "socket"
        now_m = time.monotonic()
        if not conn_mocked:
            cached = self._peer_reach_cache.get(peer_ip)
            if cached is not None and (now_m - cached[1]) < 2.5:
                return bool(cached[0])

        # Uji koneksi TCP nyata ke port HTTP (80)
        ok_reach = False
        try:
            with socket.create_connection((peer_ip, 80), timeout=timeout):
                ok_reach = True
        except Exception:
            ok_reach = False
        if not conn_mocked:
            self._peer_reach_cache[peer_ip] = (ok_reach, now_m)
        return ok_reach

    def _extract_peer_ip_from_entries(self, entries, local_ip=""):
        """Menarik IP peer non-lokal pertama langsung dari daftar peers/routes tanpa fork CLI tambahan."""
        local_ips = {"127.0.0.1", "0.0.0.0"}
        clean_local = str(local_ip or "").split("/")[0].strip()
        if clean_local:
            local_ips.add(clean_local)
        for item in entries or []:
            if isinstance(item, dict):
                ipv4 = item.get("ipv4_addr") or item.get("ipv4") or item.get("ip") or item.get("peer_ipv4")
                if ipv4:
                    clean = str(ipv4).split("/")[0].strip()
                    if clean and clean not in local_ips and not clean.startswith("127."):
                        return clean
        return None

    def get_summary(self, force_refresh=False):
        """Mengambil ringkasan telemetri komprehensif untuk antarmuka UI dengan TTL cache 12s."""
        now = time.time()
        with self._lock:
            if force_refresh:
                self._cli_cache.clear()
            elif self._cached_summary and (now - self._cached_summary_ts) < SUMMARY_CACHE_TTL_SEC:
                return copy.deepcopy(self._cached_summary)

        running = self.is_running()
        if not running:
            res = {
                "running": False,
                "available": self.is_available(),
                "remote_id": self._remote_id,
                "network_name": self._network_name,
                "virtual_ipv4": None,
                "virtual_ip": None,
                "peers_count": 0,
                "peers": [],
                "tun_active": False,
                "no_tun_fallback": False,
                "smb_warning": "",
            }
            with self._lock:
                self._cached_summary = res
                self._cached_summary_ts = now
            return copy.deepcopy(res)

        peers = self.get_peers()
        node_info = self.get_node_info()
        vip = node_info.get("virtual_ipv4") or (str(self._ipv4).split("/")[0].strip() if self._ipv4 else "10.126.126.2")
        tun_active = self.is_tun_active()
        server_peer_ip = self._extract_peer_ip_from_entries(peers, local_ip=vip)
        if not server_peer_ip:
            server_peer_ip = self.get_peer_ip()
        res = {
            "running": True,
            "available": True,
            "remote_id": self._remote_id,
            "network_name": self._network_name,
            "virtual_ipv4": vip,
            "virtual_ip": vip,
            "uptime": node_info.get("uptime", 0),
            "peers_count": len(peers),
            "peers": peers,
            "server_peer_ip": server_peer_ip,
            "tun_active": tun_active,
            "no_tun_fallback": bool(self._no_tun_fallback),
            "smb_warning": ("" if tun_active else NO_TUN_SMB_WARNING),
        }
        with self._lock:
            self._cached_summary = res
            self._cached_summary_ts = now
        return copy.deepcopy(res)

    def get_status_overview(self, force_refresh=False):
        """Alias untuk get_summary() demi kompatibilitas penuh."""
        return self.get_summary(force_refresh=force_refresh)

    def get_tunnel_traffic_stats(self):
        """
        Membaca total rx/tx bytes dan jumlah peer terhubung dari tabel peer EasyTier.
        Mengembalikan dict {running, peers_count, rx_bytes, tx_bytes, delta_bytes, active}.
        """
        if not self.is_running():
            return {"running": False, "peers_count": 0, "rx_bytes": 0, "tx_bytes": 0, "delta_bytes": 0, "active": False}

        peers = self.get_peers() or []
        total_rx = 0
        total_tx = 0
        for peer in peers:
            if not isinstance(peer, dict):
                continue
            stats_obj = peer.get("stats") if isinstance(peer.get("stats"), dict) else {}
            tun_obj = peer.get("tunnel_info") if isinstance(peer.get("tunnel_info"), dict) else {}
            rx = (
                peer.get("rx_bytes")
                or stats_obj.get("rx_bytes")
                or peer.get("bytes_rx")
                or tun_obj.get("rx_bytes")
                or 0
            )
            tx = (
                peer.get("tx_bytes")
                or stats_obj.get("tx_bytes")
                or peer.get("bytes_tx")
                or tun_obj.get("tx_bytes")
                or 0
            )
            try:
                total_rx += max(0, int(rx or 0))
                total_tx += max(0, int(tx or 0))
            except (TypeError, ValueError):
                pass

        now_mono = time.monotonic()
        with self._lock:
            prev_rx, prev_tx = self._last_peer_bytes
            delta = max(0, total_rx - prev_rx) + max(0, total_tx - prev_tx)
            self._last_peer_bytes = (total_rx, total_tx)
            if delta > 0:
                self._last_traffic_ts = now_mono
            recent_traffic = (now_mono - self._last_traffic_ts) < 10.0 if self._last_traffic_ts > 0 else False

        return {
            "running": True,
            "peers_count": len(peers),
            "rx_bytes": total_rx,
            "tx_bytes": total_tx,
            "delta_bytes": delta,
            "active": bool(delta > 0 or recent_traffic),
        }

    def is_tunnel_traffic_active(self, window_sec=10.0):
        """
        Traffic-Aware Congestion Guard ala Zima Client v2.3.5:
        Mengembalikan True bila trafik peer EasyTier aktif atau baru saja mengalir dalam window_sec terakhir,
        sehingga timeout probe HTTP sesaat tidak keliru dianggap tunnel mati.
        """
        st = self.get_tunnel_traffic_stats()
        if not st.get("running"):
            return False
        if st.get("delta_bytes", 0) > 0:
            return True
        now_mono = time.monotonic()
        with self._lock:
            if self._last_traffic_ts > 0 and (now_mono - self._last_traffic_ts) < float(window_sec):
                return True
        return False

    def record_p2p_probe_result(self, reachable):
        """
        Mencatat keberhasilan/kegagalan P2P. Setelah 3 kegagalan beruntun pada NAT simetris ketat,
        memicu mode fallback --disable-p2p (relay stabil).
        """
        if reachable:
            self._p2p_failure_streak = 0
            return False
        self._p2p_failure_streak += 1
        if self._p2p_failure_streak >= 3 and not self._disable_p2p:
            logger.warning("[EasyTier] Kegagalan P2P beruntun (%d kali); mengaktifkan fallback --disable-p2p...", self._p2p_failure_streak)
            if self._last_start_kwargs and self.is_running():
                kw = dict(self._last_start_kwargs)
                kw["disable_p2p"] = True
                ok, _ = self.start(**kw)
                if ok:
                    self._disable_p2p = True
            else:
                self._disable_p2p = True
            return True
        return False

    def start_easytier(self, network_name=None, network_secret=None, ipv4=None, peers=None, use_no_tun=False, external_node=None, rpc_port=DEFAULT_RPC_PORT, remote_id=None, lazy_p2p=False, disable_p2p=False):
        """Alias untuk start() dengan parameter fleksibel."""
        return self.start(
            network_name=network_name,
            network_secret=network_secret,
            ipv4=ipv4,
            peers=peers,
            rpc_port=rpc_port,
            remote_id=remote_id,
            use_no_tun=use_no_tun,
            external_node=external_node,
            lazy_p2p=lazy_p2p,
            disable_p2p=disable_p2p,
        )

    def stop_easytier(self):
        """Alias untuk stop() demi kompatibilitas penuh."""
        return self.stop()

    def get_full_status(self, force_refresh=False):
        """Alias untuk get_summary() demi kompatibilitas penuh."""
        return self.get_summary(force_refresh=force_refresh)


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

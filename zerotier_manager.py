"""
ZeroTier Manager Module for MyServer Desktop (Beta)
Modul pengontrol dan otomatisasi ZeroTier One (Local Node API via port 9993),
memungkinkan akses remote P2P ke server ZimaOS secara native dan mandiri.
Mendukung instalasi senyap otomatis (ZeroTier Silent Auto-Installer).
"""

import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ZEROTIER_LOCAL_API = "http://127.0.0.1:9993"


def get_zerotier_auth_token():
    """
    Mendeteksi dan membaca token autentikasi ZeroTier One di sistem Windows.
    Mencari pada lokasi user (%LOCALAPPDATA%) dan sistem (%PROGRAMDATA%).
    """
    # 1. Lokasi user aktif (dapat dibaca tanpa hak administrator)
    user_token_path = os.path.expandvars(r"%LOCALAPPDATA%\ZeroTier\authtoken.secret")
    if os.path.exists(user_token_path):
        try:
            with open(user_token_path, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token:
                    return token
        except Exception:
            pass

    # 2. Lokasi sistem bawaan service ZeroTier One
    sys_token_path = r"C:\ProgramData\ZeroTier\One\authtoken.secret"
    if os.path.exists(sys_token_path):
        try:
            with open(sys_token_path, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token:
                    return token
        except (PermissionError, Exception):
            pass

    return None


def validate_network_id(network_id):
    """
    Validasi format ZeroTier Network ID (harus tepat 16 karakter heksadesimal).
    Contoh: '0123456789abcdef'
    """
    if not network_id or not isinstance(network_id, str):
        return False
    clean = network_id.strip().lower()
    return bool(re.match(r"^[0-9a-f]{16}$", clean))


class ZeroTierClient:
    """Client REST API untuk mengontrol node ZeroTier One lokal."""

    def __init__(self, api_url=ZEROTIER_LOCAL_API, token=None):
        self.api_url = api_url.rstrip("/")
        self.token = token or get_zerotier_auth_token()

    def _make_request(self, endpoint, method="GET", data=None, timeout=3.0):
        if not self.token:
            return None, "Token autentikasi ZeroTier One tidak ditemukan."

        url = f"{self.api_url}{endpoint}"
        headers = {
            "X-ZT1-Auth": self.token,
            "Content-Type": "application/json",
            "User-Agent": "MyServer-Desktop-Beta/ZeroTierClient",
        }
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status in (200, 201):
                    res_text = resp.read().decode("utf-8")
                    try:
                        return json.loads(res_text), None
                    except json.JSONDecodeError:
                        return {"status": "ok", "raw": res_text}, None
                return None, f"HTTP Error {resp.status}"
        except urllib.error.HTTPError as he:
            return None, f"HTTP Error {he.code}: {he.reason}"
        except Exception as e:
            return None, str(e)

    def is_service_running(self):
        """Memeriksa apakah daemon service ZeroTier One aktif di 127.0.0.1:9993."""
        status_data, err = self._make_request("/status", timeout=1.5)
        if status_data and status_data.get("online") is not None:
            return True, status_data
        return False, err

    def get_node_status(self):
        """Mengambil data status node lokal (address, online, version)."""
        data, err = self._make_request("/status", timeout=2.0)
        if data:
            return {
                "online": bool(data.get("online")),
                "address": data.get("address", ""),
                "version": data.get("version", ""),
            }
        return {"online": False, "address": "", "version": "", "error": err}

    def get_joined_networks(self):
        """Mengambil daftar seluruh jaringan ZeroTier yang diikuti oleh laptop."""
        data, err = self._make_request("/network", timeout=2.5)
        if isinstance(data, list):
            networks = []
            for item in data:
                networks.append(
                    {
                        "nwid": item.get("nwid", ""),
                        "name": item.get("name", ""),
                        "status": item.get("status", ""),
                        "type": item.get("type", ""),
                        "assignedAddresses": item.get("assignedAddresses", []),
                        "routes": item.get("routes", []),
                    }
                )
            return networks
        return []

    def get_network_by_id(self, network_id):
        """Mencari data jaringan yang terdaftar berdasarkan network_id (case-insensitive)."""
        if not network_id:
            return None
        clean_id = str(network_id).strip().lower()
        networks = self.get_joined_networks()
        for net in networks:
            if str(net.get("nwid", "")).strip().lower() == clean_id:
                return net
        return None

    def join_network(self, network_id):
        """Menghubungkan laptop ke ZeroTier Network ID tertentu."""
        clean_id = str(network_id).strip().lower()
        if not validate_network_id(clean_id):
            return False, f"Format Network ID tidak valid: '{network_id}' (harus 16 hex)"

        res, err = self._make_request(f"/network/{clean_id}", method="POST", data={})
        if res:
            return True, res
        return False, err

    def leave_network(self, network_id):
        """Melepaskan koneksi laptop dari ZeroTier Network ID."""
        clean_id = str(network_id).strip().lower()
        if not validate_network_id(clean_id):
            return False, "Format Network ID tidak valid"

        res, err = self._make_request(f"/network/{clean_id}", method="DELETE")
        if res:
            return True, res
        return False, err

    def is_connected_to_network(self, network_id):
        """Memeriksa apakah laptop sudah bergabung dan mendapatkan status OK pada jaringan."""
        clean_id = str(network_id).strip().lower()
        networks = self.get_joined_networks()
        for net in networks:
            if net.get("nwid", "").lower() == clean_id:
                return net.get("status") == "OK", net
        return False, None

    def get_server_peer_status(self, server_virtual_ip=None, server_node_id=None):
        """
        Memeriksa apakah node server memiliki jalur fisik (paths > 0) dan latensi valid di ZeroTier One.
        Mengembalikan tuple: (is_peer_connected: bool, latency_ms: int, paths: list).
        """
        peers, err = self._make_request("/peer")
        if not peers or not isinstance(peers, list):
            return False, -1, []

        clean_node = (str(server_node_id).strip().lower() if server_node_id else "")
        # Jika node ID adalah 16 hex (NWID), ambil 10 hex pertama sebagai controller/peer ID
        if len(clean_node) == 16:
            clean_node = clean_node[:10]

        for p in peers:
            p_addr = str(p.get("address", "")).strip().lower()
            if clean_node and p_addr == clean_node:
                paths = p.get("paths", [])
                lat = p.get("latency", -1)
                is_ok = bool(len(paths) > 0 and lat >= 0)
                return is_ok, lat, paths

        # Jika server_virtual_ip diberikan, cocokkan dari assigned route
        if server_virtual_ip:
            # Periksa network status
            nets = self.get_joined_networks()
            for net in nets:
                routes = net.get("routes", [])
                for r in routes:
                    if r.get("target") and server_virtual_ip in r.get("target", ""):
                        # Ditemukan route, cari peer role LEAF
                        for p in peers:
                            if p.get("role") == "LEAF" and len(p.get("paths", [])) > 0:
                                return True, p.get("latency", 0), p.get("paths", [])

        return False, -1, []



_managed_subnets_cache = []
_managed_subnets_cache_time = 0.0
_managed_subnets_lock = threading.Lock()


def get_zerotier_managed_subnets(force_refresh=False):
    """
    Mengembalikan daftar subnet terkelola (list of ipaddress.IPv4Network) dari seluruh
    jaringan ZeroTier aktif yang berstatus OK di node lokal.
    100% Dinamis & Zero Hardcoded: membaca rute jaringan langsung dari daemon ZeroTier One.
    Menggunakan cache dengan TTL 20 detik dan thread-safe.
    """
    global _managed_subnets_cache, _managed_subnets_cache_time
    now = time.time()
    if not force_refresh:
        with _managed_subnets_lock:
            if _managed_subnets_cache and (now - _managed_subnets_cache_time < 20.0):
                return list(_managed_subnets_cache)

    subnets = []
    try:
        client = ZeroTierClient()
        if not client.token:
            return []
        running, _ = client.is_service_running()
        if not running:
            return []

        networks = client.get_joined_networks()
        for net in networks:
            if str(net.get("status", "")).upper() != "OK":
                continue
            # 1. Dari routes (tanpa via = direct subnet route milik jaringan ZT)
            for r in net.get("routes", []):
                if isinstance(r, dict) and not r.get("via"):
                    target = r.get("target")
                    if target and ":" not in str(target):
                        try:
                            net_obj = ipaddress.ip_network(str(target).strip(), strict=False)
                            if isinstance(net_obj, ipaddress.IPv4Network) and net_obj not in subnets:
                                subnets.append(net_obj)
                        except Exception:
                            pass
            # 2. Dari assignedAddresses IPv4
            for addr in net.get("assignedAddresses", []):
                if addr and ":" not in str(addr):
                    try:
                        net_obj = ipaddress.ip_interface(str(addr).strip()).network
                        if isinstance(net_obj, ipaddress.IPv4Network) and net_obj not in subnets:
                            subnets.append(net_obj)
                    except Exception:
                        pass
    except Exception:
        pass

    with _managed_subnets_lock:
        _managed_subnets_cache = subnets
        _managed_subnets_cache_time = now
    return list(subnets)


def is_zerotier_ip(ip_str):
    """
    Memeriksa secara dinamis apakah suatu alamat IP berada di dalam subnet terkelola ZeroTier.
    Zero Hardcoding: murni didasarkan pada rute adapter ZeroTier yang aktif di sistem.
    """
    if not ip_str:
        return False
    try:
        clean_ip = str(ip_str).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
        ip_obj = ipaddress.ip_address(clean_ip)
        if not isinstance(ip_obj, ipaddress.IPv4Address):
            return False
        subnets = get_zerotier_managed_subnets()
        return any(ip_obj in s for s in subnets)
    except Exception:
        return False


def is_zerotier_installed():
    """
    Memeriksa apakah perangkat lunak ZeroTier One sudah terpasang di sistem Windows.
    Mengecek berkas eksekusi biner, folder konfigurasi sistem, dan service Windows.
    """
    # 1. Cek biner eksekusi di Program Files
    possible_paths = [
        r"C:\Program Files\ZeroTier\One\zerotier-one_x64.exe",
        r"C:\Program Files (x86)\ZeroTier\One\zerotier-one_x86.exe",
        r"C:\ProgramData\ZeroTier\One\zerotier-one.port",
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return True

    # 2. Cek apakah token atau folder authtoken ada
    if get_zerotier_auth_token():
        return True

    # 3. Cek apakah service ZeroTierOneService terdaftar di Windows
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    try:
        res = subprocess.run(
            ["sc.exe", "query", "ZeroTierOneService"],
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=2.0
        )
        if res.returncode == 0 and "SERVICE_NAME" in res.stdout:
            return True
    except Exception:
        pass

    return False


def install_zerotier_silently(msi_url="https://download.zerotier.com/dist/ZeroTier%20One.msi", status_callback=None):
    """
    Mengunduh berkas MSI resmi ZeroTier One dan menjalankan instalasi senyap (silent)
    menggunakan msiexec /i /qn via elevasi UAC Windows (sama seperti Zima Client resmi).
    """
    if status_callback:
        status_callback("Mengunduh komponen resmi ZeroTier One...")

    temp_msi = os.path.join(tempfile.gettempdir(), "ZeroTierOne_Setup.msi")
    try:
        req = urllib.request.Request(
            msi_url,
            headers={"User-Agent": "MyServer-Desktop-Beta/Installer"}
        )
        with urllib.request.urlopen(req, timeout=45.0) as resp, open(temp_msi, "wb") as out_f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out_f.write(chunk)
    except Exception as e:
        return False, f"Gagal mengunduh berkas installer ZeroTier: {e}"

    if status_callback:
        status_callback("Memasang layanan ZeroTier One secara senyap (Konfirmasi UAC)...")

    # Jalankan msiexec secara senyap dengan hak administrator via PowerShell Start-Process -Verb RunAs
    ps_cmd = f"Start-Process -FilePath 'msiexec.exe' -ArgumentList '/i \"{temp_msi}\" /qn /norestart' -Verb RunAs -Wait"
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    try:
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=120.0
        )
        if res.returncode != 0:
            return False, f"Proses instalasi dibatalkan atau gagal: {res.stderr or res.stdout}"
    except Exception as e:
        return False, f"Gagal menjalankan installer: {e}"

    # Tunggu beberapa detik hingga service aktif dan membuat authtoken
    if status_callback:
        status_callback("Menunggu layanan ZeroTier One online...")

    client = ZeroTierClient()
    for _ in range(20):
        time.sleep(1.0)
        running, _ = client.is_service_running()
        if running:
            try:
                if os.path.exists(temp_msi):
                    os.remove(temp_msi)
            except Exception:
                pass
            return True, "ZeroTier One berhasil dipasang dan aktif!"

    return True, "Instalasi selesai. Menunggu sinkronisasi service ZeroTier."


# Backward compatibility alias
ZeroTierManager = ZeroTierClient

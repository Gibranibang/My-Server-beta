"""
SMB Mount Manager Module for MyServer Desktop (Beta)
Modul otomatisasi mounting share folder ZimaOS (Samba/SMB) langsung menjadi
Network Drive Windows (misal: Drive Z:, Y:, dst.) di File Explorer pengguna.
Mendukung multi-disk dinamis, deteksi rute (LAN/ZeroTier), pengalihan rute Domain ke ZeroTier IP,
registrasi Windows Credential Vault (cmdkey) ala Zima Client v2.3.5,
dan pelepasan atomik (unmount-before-remount) termasuk pembersihan drive Red-X (ERROR_CONNECTION_UNAVAIL).
100% DINAMIS - ZERO HARDCODED.
"""

import ctypes
import ipaddress
import logger_manager
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

_smb_host_cache_lock = threading.Lock()
_cached_resolved_smb_host = {"key": None, "target": "", "resolved": "", "ts": 0.0}
_cached_smb_shares = {"key": "", "host": "", "shares": [], "ts": 0.0}
_cached_1219_alias = {}


def invalidate_smb_host_cache():
    """Menghapus cache resolusi host SMB agar probe port 445 berikutnya dievaluasi ulang."""
    global _cached_resolved_smb_host
    with _smb_host_cache_lock:
        _cached_resolved_smb_host = {"key": None, "target": "", "resolved": "", "ts": 0.0}


def _is_easytier_tun_disabled():
    """Mengembalikan True hanya bila EasyTier berjalan tanpa adapter Wintun aktif (--no-tun)."""
    try:
        import easytier_manager
        mgr = easytier_manager.get_easytier_manager()
        if mgr is None:
            return False
        if not bool(getattr(mgr, "is_running", lambda: False)()):
            return False
        return not bool(getattr(mgr, "is_tun_active", lambda: True)())
    except Exception:
        return False


def _is_easytier_ip(ip_str, active_et_vip=""):
    """Memeriksa apakah alamat merupakan IP virtual EasyTier (10.126.126.x atau active_et_vip)."""
    clean = sanitize_input(ip_str).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()
    if not clean:
        return False
    if clean.startswith("10.126.126."):
        return True
    clean_et = sanitize_input(active_et_vip).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()
    return bool(clean_et and clean == clean_et)


def clear_smb_share_cache():
    """Menghapus cache daftar share SMB agar peralihan sumber atau host selalu membaca ulang."""
    global _cached_smb_shares
    _cached_smb_shares = {"key": "", "host": "", "shares": [], "ts": 0.0}


SHCNE_DRIVEREMOVED = 0x00000080
SHCNE_DRIVEADD = 0x00000100
SHCNF_PATHW = 0x0005


def _extract_unc_host_and_share(unc_path):
    """Mengekstrak pasangan (host_lowercase, share_name) dari path UNC Windows/POSIX."""
    if not unc_path or not isinstance(unc_path, str):
        return "", ""
    norm = unc_path.strip().replace("/", "\\")
    if not norm.startswith("\\\\"):
        return "", ""
    parts = [p for p in norm.lstrip("\\").split("\\") if p]
    if not parts:
        return "", ""
    host_part = parts[0].strip().lower()
    share_part = parts[1].strip() if len(parts) > 1 else ""
    return host_part, share_part


def get_active_1219_aliases():
    """Mengembalikan salinan peta alias aktif mitigasi Error 1219."""
    return dict(_cached_1219_alias)


def _collect_configured_myserver_hosts():
    """Mengumpulkan seluruh hostname/IP resmi milik server MyServer dari konfigurasi dan cache aktif."""
    hosts = set()
    try:
        import config_manager
        cfg = config_manager.load_or_create_config()
        servers = cfg.get("servers", []) if isinstance(cfg, dict) else []
        for srv in servers:
            if not isinstance(srv, dict):
                continue
            for key in ("host", "zerotier_virtual_ip", "easytier_virtual_ip"):
                val = sanitize_input(srv.get(key, "")).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()
                if val:
                    hosts.add(val)
            for conn in srv.get("connections", []) or []:
                if isinstance(conn, dict):
                    u = conn.get("url", "")
                    h = sanitize_input(u).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()
                    if h:
                        hosts.add(h)
    except Exception:
        pass
    for v in _cached_1219_alias.values():
        ch = sanitize_input(v).strip().lower()
        if ch:
            hosts.add(ch)
    resolved_cached = _cached_resolved_smb_host.get("resolved")
    if resolved_cached:
        hosts.add(str(resolved_cached).strip().lower())
    return hosts


def _get_dynamic_host_aliases(clean_host, zerotier_ip=None, alternate_local_hosts=None, allow_public_dns_alias=False):
    """
    Menghasilkan kandidat alias host dinamis yang aman untuk LAN (NetBIOS/PTR lokal cepat,
    alternate IP lokal, ZeroTier non-blocked; serta wildcard DNS publik hanya jika allow_public_dns_alias=True)
    untuk memitigasi Windows Error 1219 lintas-sesi.
    """
    aliases = []
    if not clean_host:
        return aliases
    # 1. Resolusi reverse DNS / NetBIOS lokal berbatas waktu (0.3s max)
    nb_clean = _reverse_lookup_fast(clean_host, timeout=0.3)
    if nb_clean and nb_clean.lower() != clean_host.lower() and nb_clean not in aliases:
        aliases.append(nb_clean)
    # 2. Kandidat IP LAN alternatif server yang port 445 merespons
    if alternate_local_hosts:
        for alt in alternate_local_hosts:
            alt_c = sanitize_input(alt).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
            if alt_c and alt_c.lower() != clean_host.lower() and alt_c not in aliases:
                if is_port_open(alt_c, 445, timeout=0.5):
                    aliases.append(alt_c)
    # 3. Kandidat ZeroTier / VPN IP jika tidak diblokir mode --no-tun EasyTier
    clean_zt = sanitize_input(zerotier_ip).strip() if zerotier_ip else ""
    if clean_zt and clean_zt.lower() != clean_host.lower() and clean_zt not in aliases:
        if not (_is_easytier_tun_disabled() and _is_easytier_ip(clean_zt)):
            if is_port_open(clean_zt, 445, timeout=0.8):
                aliases.append(clean_zt)
    # 4. Wildcard DNS publik (nip.io / sslip.io) dinonaktifkan secara default demi privasi & kecepatan LAN
    if allow_public_dns_alias:
        try:
            ip_obj = ipaddress.ip_address(clean_host)
            if ip_obj.version == 4 and ip_obj.is_private:
                for cand_dns in (f"{clean_host}.nip.io", f"{clean_host.replace('.', '-')}.sslip.io"):
                    try:
                        if socket.gethostbyname(cand_dns) == clean_host and cand_dns not in aliases:
                            aliases.append(cand_dns)
                    except Exception:
                        pass
        except Exception:
            pass
    return aliases


def _notify_windows_explorer_refresh(added_drives=None, removed_drives=None):
    """Memberitahu Windows Shell (Explorer) secara terarah per-drive tanpa flush asosiasi global."""
    if sys.platform != "win32":
        return

    def _norm_drive_root(drv):
        if not drv or not isinstance(drv, str):
            return ""
        c = drv.strip().rstrip("\\/").upper()
        if not c:
            return ""
        if not c.endswith(":"):
            c += ":"
        return f"{c}\\"

    seen_rem = []
    for d in (removed_drives or []):
        r = _norm_drive_root(d)
        if r and r not in seen_rem:
            seen_rem.append(r)

    seen_add = []
    for d in (added_drives or []):
        r = _norm_drive_root(d)
        if r and r not in seen_add:
            seen_add.append(r)

    if not seen_rem and not seen_add:
        return

    try:
        shell32 = ctypes.windll.shell32
        for r in seen_rem:
            shell32.SHChangeNotify(SHCNE_DRIVEREMOVED, SHCNF_PATHW, ctypes.c_wchar_p(r), None)
        for r in seen_add:
            shell32.SHChangeNotify(SHCNE_DRIVEADD, SHCNF_PATHW, ctypes.c_wchar_p(r), None)
    except Exception:
        pass


def _get_dos_lanman_target(drive_letter):
    """
    Memeriksa melalui QueryDosDeviceW apakah huruf drive (misal 'Z:') memiliki symbolic link
    kernel ke \\Device\\LanmanRedirector\\... (termasuk drive yatim/Red-X dengan WNet code 1203).
    """
    if sys.platform != "win32" or not drive_letter:
        return ""
    clean_drive = drive_letter.strip().rstrip("\\").upper()
    if not clean_drive.endswith(":"):
        clean_drive += ":"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.QueryDosDeviceW(clean_drive, buf, 1024) > 0:
            val = (buf.value or "").strip()
            if "LanmanRedirector" in val:
                return val
    except Exception:
        pass
    return ""


def _remove_dos_lanman_device(drive_letter):
    """
    Menghapus paksa symbolic link \\Device\\LanmanRedirector\\... yang yatim/nyangkut
    menggunakan DefineDosDeviceW (< 1ms) tanpa menyentuh partisi fisik lokal.
    """
    target = _get_dos_lanman_target(drive_letter)
    if not target:
        return False
    clean_drive = drive_letter.strip().rstrip("\\").upper()
    if not clean_drive.endswith(":"):
        clean_drive += ":"
    removed = False
    try:
        if ctypes.windll.kernel32.DefineDosDeviceW(0x00000007, clean_drive, target) != 0:
            removed = True
        if ctypes.windll.kernel32.DefineDosDeviceW(0x00000002, clean_drive, None) != 0:
            removed = True
    except Exception:
        pass
    return removed


def _get_wnet_remote_unc(drive_letter):
    """
    Mengecek status WNetGetConnectionW (serta fallback QueryDosDeviceW LanmanRedirector) untuk huruf drive.
    Mengembalikan tuple (ret_code, unc_path):
    - ret_code == 0 (NO_ERROR): Drive terhubung ke UNC path.
    - ret_code in (1201, 1203): Drive berstatus Disconnected / Red-X / Orphaned LanmanRedirector.
    - lainnya: Bukan network drive.
    """
    if sys.platform != "win32" or not drive_letter:
        return (-1, "")
    clean_drive = drive_letter.strip().rstrip("\\").upper()
    if not clean_drive.endswith(":"):
        clean_drive += ":"
    try:
        buf_len = ctypes.c_ulong(1024)
        buf = ctypes.create_unicode_buffer(1024)
        ret = ctypes.windll.mpr.WNetGetConnectionW(clean_drive, buf, ctypes.byref(buf_len))
        if ret in (0, 1201):
            return (ret, (buf.value or "").strip())
        lanman_target = _get_dos_lanman_target(clean_drive)
        if lanman_target:
            # Ekstrak UNC dari \Device\LanmanRedirector\;Z:000000000010017c\<ServerHost>\Share
            parts = [p for p in lanman_target.split("\\") if p]
            if len(parts) >= 4:
                unc_extracted = "\\\\" + "\\".join(parts[3:])
                return (1203, unc_extracted)
            return (1203, lanman_target)
        return (ret, "")
    except Exception:
        return (-1, "")


def _candidate_network_letters():
    """
    Daftar huruf drive (Z: mundur ke D:) yang berpotensi network drive: bit GetLogicalDrives aktif
    atau memiliki symbolic link kernel LanmanRedirector (termasuk drive yatim/Red-X).
    Menghindari pemanggilan WNetGetConnectionW yang bisa memblokir pada huruf drive yang kosong.
    """
    letters = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives() if sys.platform == "win32" else 0
    except Exception:
        bitmask = 0xFFFFFFFF
    for i in range(25, 2, -1):
        d = f"{chr(65 + i)}:"
        if (bitmask & (1 << i)) or _get_dos_lanman_target(d):
            letters.append(d)
    return letters


def _reverse_lookup_fast(ip_str, timeout=0.3):
    """
    Reverse DNS/NetBIOS dengan batas waktu ketat, hanya untuk alamat IPv4 privat (LAN/ZeroTier).
    Domain publik atau IP publik tidak pernah di-lookup agar tidak menggantung puluhan detik.
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        if ip_obj.version != 4 or not ip_obj.is_private:
            return ""
    except Exception:
        return ""
    box = [""]

    def _worker():
        try:
            box[0] = (socket.gethostbyaddr(ip_str)[0] or "").strip()
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=float(timeout))
    return box[0]


def _register_windows_credential(host, username, password):
    """
    Standar Zima Client v2.3.5 (service/smb.go):
    Mendaftarkan kredensial SMB ke Windows Credential Manager (cmdkey) agar Windows Explorer
    dan layanan background dapat melakukan autentikasi otomatis tanpa memunculkan popup/hang.
    """
    if sys.platform != "win32" or not host or not username:
        return False
    creationflags = 0x08000000
    clean_h = sanitize_input(host).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
    clean_u = sanitize_input(username)
    clean_p = sanitize_password(password)
    if not clean_h or not clean_u:
        return False
    try:
        subprocess.run(
            ["cmdkey.exe", f"/delete:{clean_h}"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            creationflags=creationflags,
            timeout=3.0,
        )
    except Exception:
        pass
    try:
        cmd = ["cmdkey.exe", f"/add:{clean_h}", f"/user:{clean_u}"]
        if clean_p:
            cmd.append(f"/pass:{clean_p}")
        res = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            creationflags=creationflags,
            timeout=3.0,
        )
        return res.returncode == 0
    except Exception:
        return False


def _delete_windows_credential(host):
    """Menghapus kredensial SMB host dari Windows Credential Manager saat sesi dibersihkan."""
    if sys.platform != "win32" or not host:
        return False
    creationflags = 0x08000000
    clean_h = sanitize_input(host).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
    if not clean_h:
        return False
    try:
        subprocess.run(
            ["cmdkey.exe", f"/delete:{clean_h}"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            creationflags=creationflags,
            timeout=3.0,
        )
        return True
    except Exception:
        return False


def _cancel_connection_safe(target_name, force=True, timeout=2.0):
    """Memanggil WNetCancelConnection2W dengan batas waktu ketat; mengembalikan (cancelled_ok, timed_out)."""
    if sys.platform != "win32" or not target_name:
        return False, False
    res_box = [False]

    def _worker():
        try:
            ret = ctypes.windll.mpr.WNetCancelConnection2W(target_name, 0x00000001, bool(force))
            if ret != 0:
                ret = ctypes.windll.mpr.WNetCancelConnection2W(target_name, 0, bool(force))
            res_box[0] = (ret == 0)
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=float(timeout))
    timed_out = t.is_alive()
    return (False if timed_out else res_box[0]), timed_out


def sanitize_input(val):
    """Menghapus karakter berbahaya yang dapat memicu shell injection untuk host/share."""
    if not val:
        return ""
    return re.sub(r'[;&|`$<>"\n\r]', '', str(val)).strip()


def sanitize_password(val):
    """Membersihkan newline/control char tanpa merusak karakter khusus simbol pada password."""
    if not val:
        return ""
    return re.sub(r'[\r\n\0]', '', str(val))


def is_port_open(host, port=445, timeout=1.0):
    """Memeriksa apakah port TCP (default SMB port 445) dapat dihubungi."""
    if not host:
        return False
    try:
        s = socket.create_connection((host, int(port)), timeout=float(timeout))
        s.close()
        return True
    except Exception:
        return False


def _is_domain_or_wan_host(host_str):
    """
    Memeriksa apakah host merupakan Domain FQDN publik atau IP WAN publik
    (memerlukan redirect SMB ke ZeroTier IP karena port 445 diblokir ISP/Cloudflare).
    """
    if not host_str:
        return False
    clean = sanitize_input(host_str).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()
    if not clean or clean in ("localhost", "127.0.0.1", "::1") or clean.endswith(".local") or clean.endswith(".lan"):
        return False
    try:
        ip = ipaddress.ip_address(clean)
        if ip.is_loopback:
            return False
        import zerotier_manager
        if zerotier_manager.is_zerotier_ip(clean):
            return False
        if ip in ipaddress.ip_network("100.64.0.0/10"):
            return False
        if ip.is_private:
            return False
        return True
    except ValueError:
        return True


def resolve_smb_host(target_host, server_connections=None, is_domain_route=None, zerotier_ip=None, max_age_seconds=15):
    """
    Menemukan alamat IP yang valid dan aktif untuk layanan Samba (port 445).
    Aturan Ketat Prioritas Jalur (LAN-first & fail-fast):
    1. Rute Domain/WAN: uji lan_candidates dulu (0.45s), lalu remote_candidates (1.0s).
    2. Rute non-Domain: uji clean_h (kecuali EasyTier saat --no-tun), mDNS .local,
       lan_candidates (0.45s), lalu remote_candidates (1.0s).
    3. Fail-fast: kembalikan None jika seluruh kandidat gagal di port 445.
    """
    global _cached_resolved_smb_host
    clean_h = sanitize_input(target_host).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
    clean_zt = sanitize_input(zerotier_ip).strip() if zerotier_ip else ""

    if is_domain_route is None:
        is_domain_route = _is_domain_or_wan_host(clean_h)

    remote_candidates = []
    if clean_zt:
        remote_candidates.append(clean_zt)
    active_et_vip = ""
    try:
        import config_manager
        cfg = config_manager.load_or_create_config()
        active_srv = config_manager.get_active_server(cfg)
        if active_srv:
            zt_vip = (active_srv.get("zerotier_virtual_ip") or "").strip()
            et_vip = (active_srv.get("easytier_virtual_ip") or "").strip()
            active_et_vip = et_vip
            if zt_vip and zt_vip not in remote_candidates:
                remote_candidates.append(zt_vip)
            if et_vip and et_vip not in remote_candidates:
                remote_candidates.append(et_vip)
    except Exception:
        pass

    lan_candidates = []
    if server_connections and isinstance(server_connections, list):
        for c in server_connections:
            if not isinstance(c, dict):
                continue
            c_url = c.get("url", "")
            h_cand = c_url.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
            if h_cand and h_cand not in lan_candidates and not h_cand.endswith(".local"):
                try:
                    ip_obj = ipaddress.ip_address(h_cand)
                    import zerotier_manager
                    is_zt = (h_cand in remote_candidates) or zerotier_manager.is_zerotier_ip(h_cand) or h_cand.startswith("10.126.126.")
                    if ip_obj.is_private and not is_zt:
                        lan_candidates.append(h_cand)
                except Exception:
                    pass

    et_tun_disabled = _is_easytier_tun_disabled()
    if et_tun_disabled:
        remote_candidates = [ip for ip in remote_candidates if not _is_easytier_ip(ip, active_et_vip)]
        if _is_easytier_ip(clean_zt, active_et_vip):
            clean_zt = ""
        if _is_easytier_ip(clean_h, active_et_vip):
            logger_manager.log_warning(
                f"[SMB Host Resolver] EasyTier dalam mode --no-tun (Wintun tidak aktif); melewati probe langsung ke {clean_h}:445."
            )

    cache_key = (
        clean_h.lower(),
        bool(is_domain_route),
        tuple(lan_candidates),
        tuple(remote_candidates),
        bool(et_tun_disabled),
    )

    if max_age_seconds and max_age_seconds > 0:
        with _smb_host_cache_lock:
            if (
                _cached_resolved_smb_host.get("key") == cache_key
                and _cached_resolved_smb_host.get("resolved")
                and (time.time() - float(_cached_resolved_smb_host.get("ts", 0.0))) < float(max_age_seconds)
            ):
                return _cached_resolved_smb_host["resolved"]

    def _store_cache(resolved_val):
        global _cached_resolved_smb_host
        with _smb_host_cache_lock:
            _cached_resolved_smb_host = {
                "key": cache_key,
                "target": clean_h,
                "resolved": resolved_val,
                "ts": time.time(),
            }

    # A. KONDISI 1: RUTE DOMAIN / WAN AKTIF (LAN-First per D-09.1, lalu Remote P2P)
    if is_domain_route:
        for cand in lan_candidates:
            if is_port_open(cand, 445, timeout=0.45):
                logger_manager.log_info(f"[SMB Host Resolver] Rute Domain aktif namun IP LAN ({cand}:445) responsif -> Menggunakan SMB LAN")
                _store_cache(cand)
                return cand

        for rem_ip in remote_candidates:
            if is_port_open(rem_ip, 445, timeout=1.0):
                logger_manager.log_info(f"[SMB Host Resolver] Rute Domain aktif & Remote P2P sehat -> Mengarahkan SMB ke ({rem_ip}:445)")
                _store_cache(rem_ip)
                return rem_ip

        logger_manager.log_warning(
            "[SMB Host Resolver] Rute Domain aktif namun seluruh probe port 445 (LAN/Remote P2P) gagal -> Fail-fast None."
        )
        return None

    # B. KONDISI 2: HOST RUTE AKTIF PILIHAN PENGGUNA
    if (
        clean_h
        and clean_h not in ("localhost", "127.0.0.1")
        and not (et_tun_disabled and _is_easytier_ip(clean_h, active_et_vip))
        and is_port_open(clean_h, 445, timeout=1.0)
    ):
        logger_manager.log_info(f"[SMB Host Resolver] Terhubung ke SMB Server via Host Rute Aktif ({clean_h}:445)")
        _store_cache(clean_h)
        return clean_h

    # C. KONDISI 3: HOSTNAME .local (mDNS)
    if clean_h.endswith(".local"):
        try:
            resolved_ip = socket.gethostbyname(clean_h)
            if resolved_ip and resolved_ip not in ("127.0.0.1", "localhost"):
                if is_port_open(resolved_ip, 445, timeout=1.0):
                    logger_manager.log_info(f"[SMB Host Resolver] mDNS {clean_h} -> {resolved_ip}")
                    _store_cache(resolved_ip)
                    return resolved_ip
        except Exception:
            pass

    # D. KONDISI 4: FALLBACK KE KANDIDAT LAN LAIN
    for cand in lan_candidates:
        if cand != clean_h and is_port_open(cand, 445, timeout=0.45):
            logger_manager.log_info(f"[SMB Host Resolver] Host rute tidak aktif -> Fallback ke IP LAN ({cand}:445)")
            _store_cache(cand)
            return cand

    # E. KONDISI 5: FALLBACK KE REMOTE CANDIDATES (ZeroTier / non-excluded VPN)
    remote_fallback_order = []
    if clean_zt:
        remote_fallback_order.append(clean_zt)
    for rem_ip in remote_candidates:
        if rem_ip not in remote_fallback_order:
            remote_fallback_order.append(rem_ip)
    for rem_ip in remote_fallback_order:
        if rem_ip != clean_h and is_port_open(rem_ip, 445, timeout=1.0):
            logger_manager.log_info(f"[SMB Host Resolver] Host lokal tidak merespons -> Fallback ke Remote IP ({rem_ip}:445)")
            _store_cache(rem_ip)
            return rem_ip

    logger_manager.log_warning(f"[SMB Host Resolver] Seluruh kandidat SMB untuk {clean_h or '(kosong)'} gagal di port 445 -> Fail-fast None.")
    return None


def fetch_shares_from_zimaos_api(base_url, auth_token, current_user=""):
    """
    Mengambil daftar share folder ZimaOS secara murni dinamis melalui REST API resmi.
    Mendukung CasaOS native local storage shares (/v2_1/files/share) serta
    Samba cloud / Google Drive / rclone shares (/v2/users/samba/user).
    """
    if not base_url or not auth_token:
        return []

    clean_url = base_url.rstrip("/")
    endpoints = ["/v2_1/files/share", "/v2/share/list", "/v2/share"]

    req_headers = {
        "Authorization": f"Bearer {auth_token}",
        "token": auth_token,
        "Accept": "application/json",
        "User-Agent": "MyServer-Desktop-App/3.10.21",
    }

    shares = []
    seen = set()
    current_user_clean = (current_user or "").strip().lower()
    ctx = ssl._create_unverified_context()

    # 1. Coba kueri CasaOS file share endpoints
    for ep in endpoints:
        try:
            url = f"{clean_url}{ep}"
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    data = body.get("data", body) if isinstance(body, dict) else body
                    if isinstance(data, list):
                        for item in data:
                            if not isinstance(item, dict):
                                continue
                            sh_name = item.get("name")
                            if not sh_name or sh_name in seen:
                                continue
                            status = str(item.get("status", "enable")).lower()
                            if status != "enable":
                                continue

                            # Verifikasi hak akses pengguna aktif jika didefinisikan (case-insensitive & multi-field)
                            permissions = item.get("permission", [])
                            users_list = [str(u).strip().lower() for u in item.get("users", [])]
                            if current_user_clean:
                                permitted = False
                                for p in permissions:
                                    p_user = str(p.get("user", "")).strip().lower()
                                    if p_user == current_user_clean and (p.get("read") or p.get("write")):
                                        permitted = True
                                        break
                                if not permitted and current_user_clean in users_list:
                                    permitted = True
                                if not permitted:
                                    continue

                            shares.append(sh_name)
                            seen.add(sh_name)
                        if shares:
                            break
        except Exception:
            continue

    # 2. Coba kueri Samba users endpoint (/v2/users/samba/user) untuk menangkap share cloud/Google Drive/rclone
    try:
        url = f"{clean_url}/v2/users/samba/user"
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                s_data = body.get("data", body) if isinstance(body, dict) else body
                items_list = s_data if isinstance(s_data, list) else [s_data]
                target_user = None
                for u in items_list:
                    if not isinstance(u, dict):
                        continue
                    u_name = str(u.get("username", "")).strip().lower()
                    if current_user_clean and u_name == current_user_clean:
                        target_user = u
                        break

                if target_user:
                    for perm in target_user.get("permissions", []):
                        if not isinstance(perm, dict):
                            continue
                        p_path = perm.get("path", "").strip()
                        if not p_path:
                            continue
                        b_name = os.path.basename(p_path.rstrip("/"))
                        if b_name and b_name not in seen:
                            shares.append(b_name)
                            seen.add(b_name)
    except Exception:
        pass

    return shares


def _normalize_backend_api_url(raw_url, fallback_host=""):
    """
    Menormalisasi URL rute active_u (LAN / Remote IP P2P / Domain WAN) ke URL REST API
    MyServer Backend (port default 8080) dengan tetap mempertahankan port kustom eksplisit.
    """
    def _extract_fb_host(fb_str):
        cleaned = sanitize_input(fb_str or "").strip()
        if not cleaned:
            return ""
        stripped_br = cleaned.strip("[]")
        try:
            ipaddress.ip_address(stripped_br)
            return stripped_br
        except ValueError:
            pass
        fb_to_parse = cleaned if "://" in cleaned else f"http://{cleaned}"
        try:
            return (urllib.parse.urlparse(fb_to_parse).hostname or "").strip()
        except Exception:
            return ""

    raw = str(raw_url or "").strip()
    fb_h = _extract_fb_host(fallback_host)

    if not raw:
        if not fb_h:
            return ""
        host_fmt = f"[{fb_h}]" if ":" in fb_h and not fb_h.startswith("[") else fb_h
        return f"http://{host_fmt}:8080"

    to_parse = raw if "://" in raw else f"http://{raw}"
    try:
        parsed = urllib.parse.urlparse(to_parse)
    except Exception:
        if not fb_h:
            return ""
        host_fmt = f"[{fb_h}]" if ":" in fb_h and not fb_h.startswith("[") else fb_h
        return f"http://{host_fmt}:8080"

    scheme = (parsed.scheme or "http").lower()
    if scheme not in ("http", "https"):
        scheme = "http"

    host = (parsed.hostname or "").strip()
    try:
        port = parsed.port
    except ValueError:
        port = None

    has_custom_backend_port = port is not None and port not in (80, 443)

    if not host:
        if not fb_h:
            return ""
        host = fb_h
        scheme = "http"
        port = 8080
    elif (
        _is_domain_or_wan_host(host)
        and fb_h
        and not _is_domain_or_wan_host(fb_h)
        and not has_custom_backend_port
    ):
        host = fb_h
        scheme = "http"
        port = 8080
    elif port is None or port in (80, 443):
        scheme = "http"
        port = 8080

    host_fmt = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"{scheme}://{host_fmt}:{port}"


def fetch_shares_from_backend_api(
    backend_url,
    username="",
    password="",
    auth_token="",
    fallback_host="",
    on_token_refreshed=None,
):
    """
    Mengambil daftar share disk yang diizinkan dari MyServer Backend (/api/v1/storage/disks).
    Jika auth_token kosong atau mengembalikan HTTP 401 (JWT kedaluwarsa), otomatis melakukan
    re-autentikasi satu kali ke POST /api/v1/auth/verify memakai backend_smb_auth dan
    memberi tahu caller lewat on_token_refreshed(new_token, auth_payload).
    """
    clean_url = _normalize_backend_api_url(backend_url, fallback_host=fallback_host)
    if not clean_url:
        return []

    clean_user = (username or "").strip()
    raw_pass = password if password is not None else ""
    use_https = clean_url.startswith("https://")
    ssl_ctx = ssl._create_unverified_context() if use_https else None

    def _open_url(req, timeout=4.0):
        if use_https and ssl_ctx is not None:
            return urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx)
        return urllib.request.urlopen(req, timeout=timeout)

    def _verify_backend_jwt():
        if not clean_user or not raw_pass:
            return ""
        payload = json.dumps({"username": clean_user, "password": raw_pass}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Connection": "close",
            "User-Agent": "MyServer-Desktop-App/4.6.3",
        }
        try:
            req = urllib.request.Request(
                f"{clean_url}/api/v1/auth/verify",
                data=payload,
                headers=headers,
                method="POST",
            )
            with _open_url(req, timeout=4.0) as resp:
                if resp.status == 200:
                    auth_data = json.loads(resp.read().decode("utf-8") or "{}")
                    if isinstance(auth_data, dict):
                        new_tok = str(auth_data.get("access_token") or "").strip()
                        if new_tok:
                            if callable(on_token_refreshed):
                                try:
                                    on_token_refreshed(new_tok, auth_data)
                                except Exception:
                                    pass
                            return new_tok
        except Exception:
            pass
        return ""

    def _request_disks(tok):
        if not tok:
            return 401, []
        headers = {
            "Authorization": f"Bearer {tok}",
            "Accept": "application/json",
            "Connection": "close",
            "User-Agent": "MyServer-Desktop-App/4.6.3",
        }
        try:
            req = urllib.request.Request(
                f"{clean_url}/api/v1/storage/disks",
                headers=headers,
                method="GET",
            )
            with _open_url(req, timeout=4.0) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8") or "{}")
                    shares_out = []
                    seen = set()
                    if isinstance(body, dict):
                        for d in body.get("disks", []) or []:
                            if (
                                isinstance(d, dict)
                                and d.get("is_accessible", True)
                                and d.get("name")
                                and d.get("relative_path", None) != ""
                            ):
                                name = str(d["name"]).strip()
                                if name and name not in seen:
                                    seen.add(name)
                                    shares_out.append(name)
                    return 200, shares_out
                return resp.status, []
        except urllib.error.HTTPError as he:
            return he.code, []
        except Exception:
            return 0, []

    token = (auth_token or "").strip()
    verified_this_call = False
    if not token:
        token = _verify_backend_jwt()
        verified_this_call = True
        if not token:
            return []

    status_code, shares = _request_disks(token)
    if status_code == 401 and not verified_this_call and clean_user and raw_pass:
        fresh_token = _verify_backend_jwt()
        if fresh_token:
            status_code, shares = _request_disks(fresh_token)

    return shares if status_code == 200 else []


def get_remote_smb_shares(
    host,
    username="",
    password="",
    auth_token="",
    base_url="",
    max_age_seconds=30,
    force_refresh=False,
    smb_source="zimaos",
    backend_url="",
    on_token_refreshed=None,
):
    """
    Mendeteksi daftar share folder SMB yang tersedia di server.
    Prioritas 1: Kueri Backend API (/api/v1/storage/disks) saat smb_source=='backend',
                 atau ZimaOS REST API resmi saat smb_source=='zimaos'.
    Prioritas 2: Sesi IPC$ terautentikasi Windows diikuti 'net view \\host'.
    Mengembalikan list nama share disk secara murni dinamis tanpa hardcode.
    """
    global _cached_smb_shares
    clean_h = sanitize_input(host).replace("http://", "").replace("https://", "").split(":")[0]
    if not clean_h:
        return []

    src_mode = (smb_source or "zimaos").strip().lower()
    if src_mode not in ("zimaos", "backend"):
        src_mode = "zimaos"

    now = time.time()
    cache_key = f"{src_mode}:{clean_h}:{username}"
    if not force_refresh and _cached_smb_shares.get("key") == cache_key and (now - _cached_smb_shares.get("ts", 0)) < max_age_seconds:
        return list(_cached_smb_shares.get("shares", []))

    # 1. Coba kueri API resmi sesuai sumber (Backend vs ZimaOS)
    if src_mode == "backend":
        target_backend_url = (backend_url or base_url or "").strip()
        if not (target_backend_url or clean_h):
            return []
        api_shares = fetch_shares_from_backend_api(
            target_backend_url,
            username=username,
            password=password,
            auth_token=auth_token,
            fallback_host=clean_h,
            on_token_refreshed=on_token_refreshed,
        )
        _cached_smb_shares = {"key": cache_key, "host": clean_h, "shares": api_shares, "ts": now}
        return api_shares
    else:
        if base_url and auth_token:
            api_shares = fetch_shares_from_zimaos_api(base_url, auth_token, current_user=username)
            if api_shares:
                _cached_smb_shares = {"key": cache_key, "host": clean_h, "shares": api_shares, "ts": now}
                return api_shares

    # 2. Coba kueri sistem via net.exe view
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    clean_user = sanitize_input(username)
    clean_pass = sanitize_password(password)

    # Autentikasi IPC$ sementara jika kredensial disediakan (mencegah Access Denied)
    ipc_opened = False
    if clean_user and clean_h:
        try:
            ipc_cmd = ["net.exe", "use", f"\\\\{clean_h}\\IPC$"]
            if clean_pass:
                ipc_cmd.append(clean_pass)
            ipc_cmd.extend([f"/USER:{clean_user}", "/PERSISTENT:NO"])
            ipc_res = subprocess.run(
                ipc_cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                creationflags=creationflags,
                timeout=4.0,
            )
            if ipc_res.returncode == 0:
                ipc_opened = True
        except Exception:
            pass

    shares = []
    try:
        res = subprocess.run(
            ["net.exe", "view", f"\\\\{clean_h}"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            timeout=5.0,
        )
        capture = False
        for line in res.stdout.splitlines():
            if line.startswith("---"):
                capture = True
                continue
            if capture:
                # Tangkap seluruh nama partisi/share hingga kolom tipe 'Disk' (termasuk share dengan karakter spasi)
                m = re.match(r'^(.*?)\s{2,}Disk\b', line, re.IGNORECASE)
                if m:
                    sh_name = m.group(1).strip()
                    if sh_name and not sh_name.endswith("$"):
                        shares.append(sh_name)
                else:
                    # Fallback jika format tabel berbeda namun tetap share bertipe Disk
                    parts = line.split()
                    if len(parts) >= 2 and parts[-1].lower() == "disk":
                        shares.append(" ".join(parts[:-1]))
    except Exception:
        pass
    finally:
        if ipc_opened:
            try:
                subprocess.run(
                    ["net.exe", "use", f"\\\\{clean_h}\\IPC$", "/DELETE", "/YES"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    creationflags=creationflags,
                    timeout=3.0,
                )
            except Exception:
                pass

    if shares:
        _cached_smb_shares = {"key": cache_key, "host": clean_h, "shares": shares, "ts": now}
    return shares


def is_drive_letter_in_use(drive_letter="Z:"):
    """
    Memeriksa secara O(1) via bitmask GetLogicalDrives() + QueryDosDeviceW apakah huruf drive
    sedang dipakai (tanpa pernah memanggil WNetGetConnectionW/MPR pada huruf kosong).
    """
    clean_drive = drive_letter.strip().rstrip("\\").upper()
    if not clean_drive.endswith(":"):
        clean_drive += ":"

    try:
        idx = ord(clean_drive[0].upper()) - 65
        if 0 <= idx < 26:
            raw_mask = ctypes.windll.kernel32.GetLogicalDrives()
            if isinstance(raw_mask, int) and not isinstance(raw_mask, bool):
                if raw_mask != 0 and bool(raw_mask & (1 << idx)):
                    return True
    except Exception:
        pass

    if _get_dos_lanman_target(clean_drive):
        return True

    return False


def get_available_drive_letters(exclude_letters=None):
    """
    Mendeteksi secara O(1) seluruh huruf drive Windows yang kosong via GetLogicalDrives() +
    _get_dos_lanman_target() (tanpa pernah memanggil _get_wnet_remote_unc).
    """
    excluded_set = set()
    if exclude_letters:
        for item in exclude_letters:
            if not item or not isinstance(item, str):
                continue
            c = item.strip().rstrip("\\/").upper()
            if c:
                if not c.endswith(":"):
                    c += ":"
                excluded_set.add(c)
    try:
        raw_mask = ctypes.windll.kernel32.GetLogicalDrives()
        bitmask = raw_mask if (isinstance(raw_mask, int) and not isinstance(raw_mask, bool)) else 0
        available = []
        for i in range(25, 2, -1):
            d = f"{chr(65 + i)}:"
            if d in excluded_set:
                continue
            if not (bitmask & (1 << i)) and not _get_dos_lanman_target(d):
                available.append(d)
        if available:
            return available
    except Exception:
        pass
    return [d for d in ("Z:", "Y:", "X:", "W:", "V:", "U:", "T:", "S:") if d not in excluded_set]


def get_available_drive_letter(preferred="Z:", exclude_letters=None):
    """
    Mencari satu huruf drive kosong secara O(1) tanpa memanggil WNetGetConnectionW.
    """
    excluded_set = set()
    if exclude_letters:
        for item in exclude_letters:
            if not item or not isinstance(item, str):
                continue
            c = item.strip().rstrip("\\/").upper()
            if c:
                if not c.endswith(":"):
                    c += ":"
                excluded_set.add(c)

    clean_p = preferred.strip().rstrip("\\").upper() if preferred else "Z:"
    if not clean_p.endswith(":"):
        clean_p += ":"
    if clean_p not in excluded_set and not is_drive_letter_in_use(clean_p):
        return clean_p

    avail = get_available_drive_letters(exclude_letters=excluded_set)
    return avail[0] if avail else None


def purge_smb_sessions(hosts=None, notify_explorer=True):
    """
    Membersihkan sesi koneksi SMB milik server MyServer secara terarah (mencegah Error 1219)
    tanpa pernah menyentuh network drive/sesi asing milik pengguna.
    """
    clear_smb_share_cache()
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    bs = chr(92)

    target_hosts = set()
    if hosts is None:
        target_hosts.update(_collect_configured_myserver_hosts())
    elif hosts:
        if isinstance(hosts, (list, tuple, set)):
            for h in hosts:
                ch = sanitize_input(h).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
                if ch:
                    target_hosts.add(ch)
        elif isinstance(hosts, str):
            ch = sanitize_input(hosts).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
            if ch:
                target_hosts.add(ch)

    for ch in list(target_hosts):
        nb = _reverse_lookup_fast(ch)
        if nb:
            target_hosts.add(nb)
        if ch in _cached_1219_alias:
            target_hosts.add(_cached_1219_alias[ch])
        elif ch.lower() in _cached_1219_alias:
            target_hosts.add(_cached_1219_alias[ch.lower()])

    target_hosts_lc = {h.lower() for h in target_hosts if h}
    if not target_hosts_lc:
        return

    for k in list(_cached_1219_alias.keys()):
        if k.lower() in target_hosts_lc:
            _cached_1219_alias.pop(k, None)

    net_use_out = ""
    if sys.platform == "win32":
        try:
            res_nu = subprocess.run(
                ["net.exe", "use"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors="replace",
                creationflags=creationflags,
                timeout=4.0,
            )
            net_use_out = res_nu.stdout or ""
        except Exception:
            net_use_out = ""

    session_hosts = set()
    session_drives = set()
    session_lines = []
    for line in net_use_out.splitlines():
        if f"{bs}{bs}" in line:
            m_unc = re.search(r'(\\[^\s].*?)(?:\s{2,}|\s*$)', line)
            unc_val = m_unc.group(1).strip() if m_unc else ""
            m_drv = re.search(r'\b([A-Za-z]:)\b', line)
            drv_val = m_drv.group(1).upper() if m_drv else ""
            if unc_val:
                h_u, _ = _extract_unc_host_and_share(unc_val)
                if h_u:
                    session_hosts.add(h_u)
            if drv_val:
                session_drives.add(drv_val)
            session_lines.append((unc_val, drv_val))

    # 1. Bersihkan drive WNet / LanmanRedirector strictly milik target_hosts_lc (termasuk 1203)
    handled_drives = set()
    if sys.platform == "win32":
        letters = list(_candidate_network_letters())
        for d in session_drives:
            if d not in letters:
                letters.append(d)
        for d in letters:
            wnet_code, wnet_unc = _get_wnet_remote_unc(d)
            if wnet_code in (0, 1201, 1203) and wnet_unc:
                h_part, _ = _extract_unc_host_and_share(wnet_unc)
                if h_part and h_part in target_hosts_lc:
                    _, timed_out = _cancel_connection_safe(d, force=True, timeout=1.5)
                    try:
                        subprocess.run(
                            ["net.exe", "use", d, "/DELETE", "/YES"],
                            stdin=subprocess.DEVNULL,
                            capture_output=True,
                            creationflags=creationflags,
                            timeout=3.0,
                        )
                    except Exception:
                        pass
                    if wnet_code == 1203 or not timed_out:
                        _remove_dos_lanman_device(d)
                    handled_drives.add(d)

    # 2. Bersihkan entri sesi di 'net use' strictly milik target_hosts_lc
    try:
        for unc, drv_code in session_lines:
            if drv_code and drv_code in handled_drives:
                continue
            h_part, _ = _extract_unc_host_and_share(unc) if unc else ("", "")
            if not h_part or h_part not in target_hosts_lc:
                continue
            _cancel_connection_safe(unc, force=True, timeout=1.5)
            subprocess.run(
                ["net.exe", "use", unc, "/DELETE", "/YES"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                creationflags=creationflags,
                timeout=3.0,
            )
            if drv_code:
                _, timed_out_drv = _cancel_connection_safe(drv_code, force=True, timeout=1.5)
                subprocess.run(
                    ["net.exe", "use", drv_code, "/DELETE", "/YES"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    creationflags=creationflags,
                    timeout=3.0,
                )
                if not timed_out_drv:
                    _remove_dos_lanman_device(drv_code)
                handled_drives.add(drv_code)
    except Exception:
        pass

    # 3. Hapus sesi IPC$/root UNC dan cmdkey lokal untuk target_hosts_lc
    for h in target_hosts:
        try:
            if sys.platform == "win32" and h.lower() in session_hosts:
                _cancel_connection_safe(f"{bs}{bs}{h}{bs}IPC$", force=True, timeout=1.5)
                _cancel_connection_safe(f"{bs}{bs}{h}", force=True, timeout=1.5)
                subprocess.run(
                    ["net.exe", "use", f"{bs}{bs}{h}{bs}IPC$", "/DELETE", "/YES"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    creationflags=creationflags,
                    timeout=3.0,
                )
                subprocess.run(
                    ["net.exe", "use", f"{bs}{bs}{h}", "/DELETE", "/YES"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    creationflags=creationflags,
                    timeout=3.0,
                )
            _delete_windows_credential(h)
        except Exception:
            pass

    if notify_explorer and handled_drives:
        _notify_windows_explorer_refresh(removed_drives=sorted(handled_drives))


def mount_smb_share(
    host,
    share_name,
    username="",
    password="",
    drive_letter="Z:",
    server_connections=None,
    is_domain_route=None,
    zerotier_ip=None,
    skip_ipc=False,
    notify_explorer=True,
):
    """
    Melakukan mounting share SMB server ZimaOS ke drive letter Windows.
    Menggunakan arsitektur Zima Client v2.3.5 (service/smb.go):
    1. Registrasi kredensial ke Windows Credential Vault (cmdkey) + pre-auth IPC$.
    2. Menghubungkan target drive ke UNC path via NET USE /PERSISTENT:NO dengan stdin=DEVNULL
       (menghindari interaktif password prompt yang membuat proses hang).
    3. Jika terjadi Error 1219 / 85 / 1202 (konflik sesi), otomatis melakukan purge_smb_sessions
       pada host tersebut dan mengulang pemasangan 1x dengan kredensial penuh.
    """
    if not share_name:
        return False, "Nama share folder tidak boleh kosong."

    resolved_host = resolve_smb_host(
        target_host=host,
        server_connections=server_connections,
        is_domain_route=is_domain_route,
        zerotier_ip=zerotier_ip,
    )
    if not resolved_host:
        return False, "Host SMB server tidak dapat dijangkau di port 445."
    clean_host = sanitize_input(resolved_host).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
    clean_user = sanitize_input(username)
    clean_pass = sanitize_password(password)

    bs = chr(92)
    target_drive = drive_letter.strip().rstrip(bs).upper()
    if not target_drive.endswith(":"):
        target_drive += ":"

    chosen_share = sanitize_input(share_name).lstrip("/" + bs)
    unc_path = f"{bs}{bs}{clean_host}{bs}{chosen_share}"

    logger_manager.log_info(f"[SMB Mount] Memulai pemasangan {target_drive} -> {unc_path} (User: {clean_user or 'Guest'}, Host: {clean_host})")

    creationflags = 0x08000000 if sys.platform == "win32" else 0

    if is_drive_letter_in_use(target_drive):
        unmount_smb_share(target_drive, notify_explorer=False)
        time.sleep(0.2)

    # Langkah 1 (Standar Zima Client v2.3.5): Daftarkan ke cmdkey & buka sesi IPC$ jika belum dilakukan di batch
    if clean_user and not skip_ipc:
        _register_windows_credential(clean_host, clean_user, clean_pass)
        try:
            ipc_target = f"{bs}{bs}{clean_host}{bs}IPC$"
            ipc_cmd = ["net.exe", "use", ipc_target]
            if clean_pass:
                ipc_cmd.append(clean_pass)
            ipc_cmd.extend([f"/USER:{clean_user}", "/PERSISTENT:NO"])
            subprocess.run(
                ipc_cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                creationflags=creationflags,
                timeout=4.5,
            )
        except Exception as e:
            logger_manager.log_warning(f"[SMB Mount] IPC$ pre-auth notice: {e}")

    # Langkah 2: Mount share folder ke target_drive dengan kredensial eksplisit & stdin=DEVNULL
    cmd = ["net.exe", "use", target_drive, unc_path]
    if clean_user:
        if clean_pass:
            cmd.append(clean_pass)
        cmd.append(f"/USER:{clean_user}")
    cmd.append("/PERSISTENT:NO")

    masked_cmd = " ".join([c if (not clean_pass or c != clean_pass) else "***" for c in cmd])
    logger_manager.log_info(f"[SMB Mount] Menjalankan: {masked_cmd}")

    try:
        res = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            timeout=18.0,
        )
        stdout_msg = (res.stdout or "").strip()
        stderr_msg = (res.stderr or "").strip()
        combined_out = f"{stdout_msg} {stderr_msg}".strip()
        logger_manager.log_info(f"[SMB Mount] Hasil kode {res.returncode}: {combined_out}")

        if res.returncode == 0:
            if notify_explorer:
                _notify_windows_explorer_refresh(added_drives=[target_drive])
            return True, f"Berhasil memasang {unc_path} ke {target_drive}"

        # Langkah 3 (Standar Zima Client service/smb.go): Jika gagal karena Error 1219 / 85 / 1202 (konflik sesi/drive),
        # bersihkan seluruh sesi lama ke host tersebut, registrasi ulang cmdkey, dan retry 1x dengan kredensial lengkap!
        if any(err_code in combined_out for err_code in ("1219", "85", "1202")):
            logger_manager.log_warning(f"[SMB Mount] Terdeteksi konflik sesi ({combined_out[:80]}). Menjalankan pembersihan otomatis ala Zima Client...")
            unmount_smb_share(target_drive, notify_explorer=False)
            purge_smb_sessions([clean_host], notify_explorer=False)
            time.sleep(0.25)
            if clean_user:
                _register_windows_credential(clean_host, clean_user, clean_pass)
                try:
                    ipc_cmd = ["net.exe", "use", f"{bs}{bs}{clean_host}{bs}IPC$"]
                    if clean_pass:
                        ipc_cmd.append(clean_pass)
                    ipc_cmd.extend([f"/USER:{clean_user}", "/PERSISTENT:NO"])
                    subprocess.run(
                        ipc_cmd,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        creationflags=creationflags,
                        timeout=4.5,
                    )
                except Exception:
                    pass

            if is_drive_letter_in_use(target_drive):
                alt_drive = get_available_drive_letter(preferred=target_drive)
                if alt_drive:
                    target_drive = alt_drive
                    cmd[2] = target_drive

            retry_res = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                timeout=18.0,
            )
            if retry_res.returncode == 0:
                logger_manager.log_info(f"[SMB Mount] Pemasangan berhasil setelah auto-recovery konflik sesi untuk {target_drive}")
                if notify_explorer:
                    _notify_windows_explorer_refresh(added_drives=[target_drive])
                return True, f"Berhasil memasang {unc_path} ke {target_drive}"
            stderr_msg = (retry_res.stderr or retry_res.stdout or stderr_msg).strip()

            # Langkah 4: Jika masih Error 1219 (misal proses/sesi lain di PC sedang menahan koneksi ke IP yang sama
            # dengan akun berbeda), gunakan alias host dinamis (NetBIOS/PTR lokal gethostbyaddr, nip.io, atau ZeroTier)!
            if "1219" in f"{retry_res.stdout or ''} {retry_res.stderr or ''}":
                alt_local_hosts = []
                if server_connections and isinstance(server_connections, list):
                    for conn in server_connections:
                        if isinstance(conn, dict):
                            u_alt = conn.get("url", "")
                            h_alt = sanitize_input(u_alt).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
                            if h_alt and h_alt.lower() != clean_host.lower() and not _is_easytier_ip(h_alt):
                                try:
                                    if ipaddress.ip_address(h_alt).is_private and h_alt not in alt_local_hosts:
                                        alt_local_hosts.append(h_alt)
                                except Exception:
                                    pass
                for alias_h in _get_dynamic_host_aliases(
                    clean_host,
                    zerotier_ip=zerotier_ip,
                    alternate_local_hosts=alt_local_hosts,
                ):
                    alias_unc = f"{bs}{bs}{alias_h}{bs}{chosen_share}"
                    if clean_user:
                        _register_windows_credential(alias_h, clean_user, clean_pass)
                    alias_cmd = ["net.exe", "use", target_drive, alias_unc]
                    if clean_user:
                        if clean_pass:
                            alias_cmd.append(clean_pass)
                        alias_cmd.append(f"/USER:{clean_user}")
                    alias_cmd.append("/PERSISTENT:NO")
                    alias_res = subprocess.run(
                        alias_cmd,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        creationflags=creationflags,
                        timeout=7.0,
                    )
                    if alias_res.returncode == 0:
                        _cached_1219_alias[clean_host] = alias_h
                        logger_manager.log_info(
                            f"[SMB Mount] Pemasangan {target_drive} berhasil via alias dinamis {alias_unc} (mitigasi Error 1219 lintas-sesi)"
                        )
                        if notify_explorer:
                            _notify_windows_explorer_refresh(added_drives=[target_drive])
                        return True, f"Berhasil memasang {alias_unc} ke {target_drive}"

        raw_err = stderr_msg or stdout_msg or "Gagal memasang network drive"
        logger_manager.log_error(f"[SMB Mount] Galat pemasangan {target_drive}: {raw_err}")
        return False, f"{raw_err.strip()} (Jalur: {unc_path})"
    except Exception as e:
        logger_manager.log_error(f"[SMB Mount] Exception saat memasang {target_drive}: {e}")
        return False, str(e)


def mount_all_smb_shares(
    host,
    username="",
    password="",
    server_connections=None,
    is_domain_route=None,
    zerotier_ip=None,
    auth_token="",
    base_url="",
    force_refresh=False,
    smb_source="zimaos",
    backend_url="",
    on_token_refreshed=None,
    known_server_hosts=None,
):
    """
    Melakukan mounting seluruh share folder disk server yang tersedia ke huruf drive Windows yang bebas.
    Memverifikasi host UNC & port 445 pada drive MyServer yang sudah terpasang dalam soft_mode
    agar drive zombie ber-IP lama atau tak terjangkau dicabut tanpa menyentuh drive asing.
    """
    resolved_host = resolve_smb_host(
        target_host=host,
        server_connections=server_connections,
        is_domain_route=is_domain_route,
        zerotier_ip=zerotier_ip,
    )
    if not resolved_host:
        return False, "Host SMB server tidak dapat dijangkau di port 445."
    clean_host = sanitize_input(resolved_host).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
    clean_user = sanitize_input(username)
    clean_pass = sanitize_password(password)
    bs = chr(92)

    shares = get_remote_smb_shares(
        host=resolved_host,
        username=username,
        password=password,
        auth_token=auth_token,
        base_url=base_url,
        force_refresh=force_refresh,
        smb_source=smb_source,
        backend_url=backend_url,
        on_token_refreshed=on_token_refreshed,
    )
    if not shares:
        return False, "Tidak ada share folder disk yang terdeteksi di server."

    known_hosts_lc = set(_collect_configured_myserver_hosts())
    for raw_kh in ([host, clean_host, resolved_host, zerotier_ip] + list(known_server_hosts or [])):
        if raw_kh:
            kh = sanitize_input(raw_kh).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()
            if kh:
                known_hosts_lc.add(kh)
    if server_connections and isinstance(server_connections, list):
        for conn in server_connections:
            if isinstance(conn, dict):
                ch_c = sanitize_input(conn.get("url", "")).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()
                if ch_c:
                    known_hosts_lc.add(ch_c)
    for av in _cached_1219_alias.values():
        if av:
            known_hosts_lc.add(str(av).strip().lower())

    valid_target_hosts_lc = {clean_host.lower()}
    if clean_host in _cached_1219_alias:
        valid_target_hosts_lc.add(str(_cached_1219_alias[clean_host]).strip().lower())
    elif clean_host.lower() in _cached_1219_alias:
        valid_target_hosts_lc.add(str(_cached_1219_alias[clean_host.lower()]).strip().lower())

    desired_shares_lc = {sanitize_input(sh).lstrip("/" + bs).strip().lower() for sh in shares if sh}

    already_mounted_map = {}
    removed_drives = []
    added_drives = []
    host_reachability_cache = {}

    if sys.platform == "win32":
        for d in _candidate_network_letters():
            wnet_code, wnet_unc = _get_wnet_remote_unc(d)
            unc_host, unc_share = _extract_unc_host_and_share(wnet_unc)
            # Abaikan sepenuhnya network drive milik server/NAS asing
            if unc_host and known_hosts_lc and unc_host not in known_hosts_lc:
                continue
            if wnet_code in (1201, 1203):
                if unc_host or not known_hosts_lc:
                    unmount_smb_share(d, notify_explorer=False)
                    removed_drives.append(d)
            elif wnet_code == 0 and wnet_unc:
                norm_unc = wnet_unc.rstrip(bs).lower()
                drv_type = ctypes.windll.kernel32.GetDriveTypeW(d + bs)
                host_matches = bool(unc_host and unc_host in valid_target_hosts_lc)
                share_wanted = bool(unc_share and unc_share.lower() in desired_shares_lc)
                reachable_ok = False
                if drv_type == 4 and host_matches and share_wanted:
                    if unc_host not in host_reachability_cache:
                        host_reachability_cache[unc_host] = bool(is_port_open(unc_host, 445, timeout=0.6))
                    reachable_ok = host_reachability_cache[unc_host]
                if drv_type != 4 or not host_matches or not share_wanted or not reachable_ok or norm_unc in already_mounted_map:
                    unmount_smb_share(d, notify_explorer=False)
                    removed_drives.append(d)
                else:
                    already_mounted_map[norm_unc] = d

    creationflags = 0x08000000 if sys.platform == "win32" else 0
    if clean_user and clean_host:
        _register_windows_credential(clean_host, clean_user, clean_pass)
        try:
            ipc_cmd = ["net.exe", "use", f"{bs}{bs}{clean_host}{bs}IPC$"]
            if clean_pass:
                ipc_cmd.append(clean_pass)
            ipc_cmd.extend([f"/USER:{clean_user}", "/PERSISTENT:NO"])
            subprocess.run(
                ipc_cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                creationflags=creationflags,
                timeout=4.5,
            )
        except Exception:
            pass

    mounted_count = 0
    messages = []

    for sh in shares:
        chosen_share = sanitize_input(sh).lstrip("/" + bs)
        effective_host = _cached_1219_alias.get(clean_host, resolved_host)
        expected_unc_lower = f"{bs}{bs}{clean_host}{bs}{chosen_share}".lower()
        alias_unc_lower = f"{bs}{bs}{effective_host}{bs}{chosen_share}".lower()
        if expected_unc_lower in already_mounted_map or alias_unc_lower in already_mounted_map:
            existing_drv = already_mounted_map.get(expected_unc_lower) or already_mounted_map.get(alias_unc_lower)
            mounted_count += 1
            messages.append(f"• [Drive {existing_drv}] {sh} (Aktif)")
            continue

        target_drive = get_available_drive_letter(preferred="Z:")
        if not target_drive:
            messages.append(f"• {sh}: Tidak ada huruf drive kosong yang tersedia")
            continue

        ok, msg = mount_smb_share(
            host=effective_host,
            share_name=sh,
            username=username,
            password=password,
            drive_letter=target_drive,
            server_connections=server_connections,
            is_domain_route=is_domain_route,
            zerotier_ip=zerotier_ip,
            skip_ipc=True,
            notify_explorer=False,
        )
        if ok:
            mounted_count += 1
            already_mounted_map[expected_unc_lower] = target_drive
            added_drives.append(target_drive)
            messages.append(f"• [Drive {target_drive}] {sh} (Terpasang)")
        else:
            messages.append(f"• [Drive {target_drive}] {sh} (Gagal: {msg})")

    if added_drives or removed_drives:
        _notify_windows_explorer_refresh(added_drives=added_drives, removed_drives=removed_drives)
    summary = f"Berhasil memasang {mounted_count} dari {len(shares)} partisi disk:\n" + "\n".join(messages)
    return (mounted_count > 0), summary


def unmount_all_smb_shares(allowed_hosts=None, allowed_prefixes=None):
    """
    Melepaskan hanya network drive milik host server MyServer (fail-safe host scoping).
    Tidak pernah menyentuh drive fisik lokal atau network drive asing milik pengguna.
    """
    if allowed_hosts is None and allowed_prefixes is None:
        allowed_hosts_lc = _collect_configured_myserver_hosts()
        prefix_list = ()
    else:
        allowed_hosts_lc = set()
        for h in (allowed_hosts or []):
            ch = sanitize_input(h).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()
            if ch:
                allowed_hosts_lc.add(ch)
        prefix_list = tuple(str(p).strip().lower() for p in (allowed_prefixes or []) if p and str(p).strip())

    if not allowed_hosts_lc and not prefix_list:
        logger_manager.log_warning("[SMB Unmount] allowed_hosts/allowed_prefixes kosong; melewati unmount demi keamanan drive asing.")
        return 0

    unmounted = 0
    removed_drives = []
    for d in _candidate_network_letters():
        try:
            drv_type = ctypes.windll.kernel32.GetDriveTypeW(d + "\\") if sys.platform == "win32" else 0
            wnet_code, wnet_unc = _get_wnet_remote_unc(d)
            if drv_type == 4 or wnet_code in (0, 1201, 1203):
                unc_host, _ = _extract_unc_host_and_share(wnet_unc)
                if not unc_host:
                    continue
                host_allowed = (unc_host in allowed_hosts_lc) or any(unc_host.startswith(p) for p in prefix_list)
                if not host_allowed:
                    continue
                if unmount_smb_share(d, notify_explorer=False):
                    unmounted += 1
                    removed_drives.append(d)
        except Exception:
            pass
    if removed_drives:
        _notify_windows_explorer_refresh(removed_drives=removed_drives)
    return unmounted


def unmount_smb_share(drive_letter="Z:", notify_explorer=True):
    """
    Melepaskan network mapping SMB secara bersih; membatasi DefineDosDeviceW strictly
    pada tautan yatim wnet_code == 1203 atau setelah WNetCancelConnection2W selesai tanpa timeout.
    """
    clean_drive = drive_letter.strip().rstrip("\\").upper()
    if not clean_drive.endswith(":"):
        clean_drive += ":"

    unmounted_ok = False
    initial_wnet_code = -1
    cancel_timed_out = False
    if sys.platform == "win32":
        initial_wnet_code, _ = _get_wnet_remote_unc(clean_drive)
        cancelled_ok, cancel_timed_out = _cancel_connection_safe(clean_drive, force=True, timeout=2.0)
        if cancelled_ok:
            unmounted_ok = True

    creationflags = 0x08000000 if sys.platform == "win32" else 0
    try:
        res = subprocess.run(
            ["net.exe", "use", clean_drive, "/DELETE", "/YES"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=4.0,
        )
        if res.returncode == 0:
            unmounted_ok = True
    except Exception:
        pass

    if sys.platform == "win32":
        allow_dos_cleanup = False
        if initial_wnet_code == 1203:
            allow_dos_cleanup = True
        elif not cancel_timed_out:
            post_code, _ = _get_wnet_remote_unc(clean_drive)
            if post_code != 0:
                allow_dos_cleanup = True
        if allow_dos_cleanup and _remove_dos_lanman_device(clean_drive):
            unmounted_ok = True

    if notify_explorer and unmounted_ok:
        _notify_windows_explorer_refresh(removed_drives=[clean_drive])
    return unmounted_ok


def preflight_smb_port(host, timeout=0.8):
    """Memeriksa keterjangkauan TCP port 445 sebelum meluncurkan File Explorer (batas <= 0.8s)."""
    clean_h = sanitize_input(host).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
    if not clean_h:
        return False
    bounded_timeout = min(float(timeout), 0.8) if timeout is not None else 0.8
    if bounded_timeout <= 0:
        bounded_timeout = 0.8
    return bool(is_port_open(clean_h, 445, timeout=bounded_timeout))


def open_drive_in_explorer(drive_letter="Z:", timeout=0.8):
    """
    Membuka drive network yang ter-mount di File Explorer setelah preflight status & TCP port 445.
    Mengembalikan tuple (bool, str).
    """
    clean_drive = drive_letter.strip().rstrip("\\").upper()
    if not clean_drive.endswith(":"):
        clean_drive += ":"

    target_path = f"{clean_drive}\\"
    if sys.platform == "win32":
        wnet_code, wnet_unc = _get_wnet_remote_unc(clean_drive)
        if wnet_code in (1201, 1203):
            return False, f"Drive {clean_drive} terputus atau tidak aktif; tidak membuka Explorer."
        if wnet_code == 0 and wnet_unc:
            unc_host, _ = _extract_unc_host_and_share(wnet_unc)
            if unc_host and not preflight_smb_port(unc_host, timeout=timeout):
                return False, f"Host SMB ({unc_host}:445) tidak merespons; pembukaan {clean_drive} dibatalkan agar Explorer tidak hang."

    try:
        if sys.platform == "win32":
            os.startfile(target_path)
            return True, f"Membuka {clean_drive} di File Explorer"
        else:
            subprocess.Popen(["explorer.exe", target_path])
            return True, f"Membuka {clean_drive} di File Explorer"
    except Exception as e:
        return False, str(e)


def open_unc_root_in_explorer(host, server_connections=None, is_domain_route=None, zerotier_ip=None, timeout=0.8):
    r"""
    Membuka folder akar jaringan server (\\IP_Server\) di File Explorer setelah preflight port 445.
    Mengembalikan tuple (bool, str).
    """
    resolved_host = resolve_smb_host(
        target_host=host,
        server_connections=server_connections,
        is_domain_route=is_domain_route,
        zerotier_ip=zerotier_ip,
    )
    if not resolved_host or not preflight_smb_port(resolved_host, timeout=timeout):
        return False, f"Host SMB ({resolved_host or host}:445) tidak dapat dijangkau; pembukaan UNC dibatalkan agar Explorer tidak hang."
    unc_path = f"\\\\{resolved_host}"
    try:
        if sys.platform == "win32":
            os.startfile(unc_path)
            return True, f"Membuka {unc_path} di File Explorer"
        else:
            subprocess.Popen(["explorer.exe", unc_path])
            return True, f"Membuka {unc_path} di File Explorer"
    except Exception as e:
        return False, str(e)
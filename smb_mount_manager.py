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
import urllib.request

_cached_resolved_smb_host = {"target": "", "resolved": "", "ts": 0.0}
_cached_smb_shares = {"host": "", "shares": [], "ts": 0.0}
_cached_1219_alias = {}


def _get_dynamic_host_aliases(clean_host, zerotier_ip=None):
    """
    Menghasilkan kandidat alias host dinamis (NetBIOS/PTR lokal via gethostbyaddr,
    DNS loopback LAN nip.io/sslip.io, dan ZeroTier IP) untuk memitigasi Windows Error 1219
    apabila proses/sesi lain di PC yang sama sedang menahan koneksi ke IP utama dengan akun berbeda.
    100% DINAMIS - ZERO HARDCODED.
    """
    aliases = []
    if not clean_host:
        return aliases
    # 1. Coba resolusi reverse DNS / NetBIOS lokal (100% LAN lokal, tanpa internet)
    try:
        nb_host = socket.gethostbyaddr(clean_host)[0]
        if nb_host:
            nb_clean = nb_host.strip()
            if nb_clean and nb_clean.lower() != clean_host.lower() and nb_clean not in aliases:
                aliases.append(nb_clean)
    except Exception:
        pass
    # 2. Jika clean_host adalah IPv4 privat, tambahkan wildcard DNS yang meresolusi kembali ke IP LAN lokal yang sama
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
    # 3. Kandidat ZeroTier IP jika berbeda dan port 445 terbuka
    clean_zt = sanitize_input(zerotier_ip).strip() if zerotier_ip else ""
    if clean_zt and clean_zt.lower() != clean_host.lower() and clean_zt not in aliases:
        if is_port_open(clean_zt, 445, timeout=0.8):
            aliases.append(clean_zt)
    return aliases


def _notify_windows_explorer_refresh():
    """Memberitahu Windows Shell (Explorer) secara asinkron bahwa daftar network drive telah berubah."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
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
            # Ekstrak UNC dari \Device\LanmanRedirector\;Z:000000000010017c\192.168.1.11\Share
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
    """Memanggil WNetCancelConnection2W dengan batas waktu ketat agar tidak memblokir thread saat sesi SMB macet."""
    if sys.platform != "win32" or not target_name:
        return False
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
    return res_box[0]


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
    Aturan Ketat Prioritas Jalur:
    1. Tier 1 (Rute Domain/WAN): Jika rute aktif adalah Domain FQDN publik (port 445 diblokir ISP),
       resolusi SMB dialihkan ke zerotier_ip jika port 445 merespons.
    2. Tier 2 (Host Rute Aktif Pilihan Pengguna): Jika host dari rute yang sedang aktif dipilih pengguna
       (baik IP LAN maupun IP virtual ZeroTier) merespons terbuka di port 445:
       WAJIB menggunakan host rute aktif tersebut! Dilarang dioverride oleh rute lain di server_connections.
    3. Tier 3 (Fallback Jalur Alternatif): Jika host rute yang dipilih sedang mati/offline,
       sistem mencoba kandidat LAN lain atau fallback ke ZeroTier IP.
    """
    global _cached_resolved_smb_host
    clean_h = sanitize_input(target_host).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
    clean_zt = sanitize_input(zerotier_ip).strip() if zerotier_ip else ""

    if is_domain_route is None:
        is_domain_route = _is_domain_or_wan_host(clean_h)

    # Kumpulkan kandidat LAN dari koneksi server untuk fallback
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
                    is_zt = (h_cand == clean_zt) or zerotier_manager.is_zerotier_ip(h_cand)
                    if ip_obj.is_private and not is_zt:
                        lan_candidates.append(h_cand)
                except Exception:
                    pass

    # A. KONDISI 1: RUTE DOMAIN / WAN AKTIF (Dukungan SMB over ZeroTier P2P Dinamis)
    if is_domain_route:
        # Cek apakah rute ZeroTier P2P aktif dan sehat (port 445 responsif)
        if clean_zt and is_port_open(clean_zt, 445, timeout=0.8):
            if _cached_resolved_smb_host.get("resolved") != clean_zt:
                logger_manager.log_info(f"[SMB Host Resolver] Rute Domain aktif & ZeroTier P2P sehat -> Mengarahkan SMB ke ({clean_zt}:445)")
                _cached_resolved_smb_host = {"target": clean_h, "resolved": clean_zt, "ts": time.time()}
            return clean_zt
        # Jika ZeroTier mati, cek apakah ada rute LAN lokal yang kebetulan satu jaringan
        for cand in lan_candidates:
            if is_port_open(cand, 445, timeout=0.6):
                if _cached_resolved_smb_host.get("resolved") != cand:
                    logger_manager.log_info(f"[SMB Host Resolver] Rute Domain aktif namun IP LAN ({cand}:445) terdeteksi lokal -> Menggunakan SMB LAN")
                    _cached_resolved_smb_host = {"target": clean_h, "resolved": cand, "ts": time.time()}
                return cand
        # Jika tidak ada jalur SMB yang hidup saat rute domain aktif, jangan kembalikan host domain
        # (karena port 445 diblokir di WAN dan memicu timeout 8 detik per drive di Windows!)
        logger_manager.log_warning(
            f"[SMB Host Resolver] Rute Domain aktif namun tidak ada jalur SMB (ZeroTier/LAN) yang aktif. Melewati koneksi port 445 publik."
        )
        return None

    # B. KONDISI 2: PRIORITAS MUTLAK HOST RUTE AKTIF PILIHAN PENGGUNA (Tier 2)
    # Jika user memilih rute IP host LAN atau ZeroTier, dan port 445 merespons:
    # WAJIB gunakan host tersebut!
    if clean_h and clean_h not in ("localhost", "127.0.0.1") and is_port_open(clean_h, 445, timeout=1.0):
        if _cached_resolved_smb_host.get("resolved") != clean_h:
            logger_manager.log_info(f"[SMB Host Resolver] Terhubung ke SMB Server via Host Rute Aktif ({clean_h}:445)")
            _cached_resolved_smb_host = {"target": clean_h, "resolved": clean_h, "ts": time.time()}
        return clean_h

    # C. KONDISI 3: HOSTNAME .local (mDNS)
    if clean_h.endswith(".local"):
        try:
            resolved_ip = socket.gethostbyname(clean_h)
            if resolved_ip and resolved_ip not in ("127.0.0.1", "localhost"):
                if is_port_open(resolved_ip, 445, timeout=1.0):
                    if _cached_resolved_smb_host.get("resolved") != resolved_ip:
                        logger_manager.log_info(f"[SMB Host Resolver] mDNS {clean_h} -> {resolved_ip}")
                        _cached_resolved_smb_host = {"target": clean_h, "resolved": resolved_ip, "ts": time.time()}
                    return resolved_ip
        except Exception:
            pass

    # D. KONDISI 4: JIKA HOST RUTE AKTIF MATI, FALLBACK KE KANDIDAT LAN LAIN
    for cand in lan_candidates:
        if cand != clean_h and is_port_open(cand, 445, timeout=1.0):
            if _cached_resolved_smb_host.get("resolved") != cand:
                logger_manager.log_info(f"[SMB Host Resolver] Host rute tidak aktif -> Fallback ke IP LAN ({cand}:445)")
                _cached_resolved_smb_host = {"target": clean_h, "resolved": cand, "ts": time.time()}
            return cand

    # E. KONDISI 5: FALLBACK ZEROTIER JIKA LAN OFFLINE
    if clean_zt and clean_zt != clean_h and is_port_open(clean_zt, 445, timeout=1.0):
        if _cached_resolved_smb_host.get("resolved") != clean_zt:
            logger_manager.log_info(f"[SMB Host Resolver] Host lokal tidak merespons -> Fallback ke ZeroTier IP ({clean_zt}:445)")
            _cached_resolved_smb_host = {"target": clean_h, "resolved": clean_zt, "ts": time.time()}
        return clean_zt

    return clean_h or clean_zt or "127.0.0.1"


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


def get_remote_smb_shares(host, username="", password="", auth_token="", base_url="", max_age_seconds=30, force_refresh=False):
    """
    Mendeteksi daftar share folder SMB yang tersedia di server.
    Prioritas 1: Kueri resmi ZimaOS REST API jika auth_token tersedia.
    Prioritas 2: Sesi IPC$ terautentikasi Windows diikuti 'net view \\host'.
    Mengembalikan list nama share disk secara murni dinamis tanpa hardcode.
    """
    global _cached_smb_shares
    clean_h = sanitize_input(host).replace("http://", "").replace("https://", "").split(":")[0]
    if not clean_h:
        return []

    now = time.time()
    cache_key = f"{clean_h}:{username}"
    if not force_refresh and _cached_smb_shares.get("key") == cache_key and (now - _cached_smb_shares.get("ts", 0)) < max_age_seconds:
        return list(_cached_smb_shares.get("shares", []))

    # 1. Coba kueri ZimaOS REST API resmi
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
    Memeriksa apakah huruf drive Windows (misal 'Z:') sedang digunakan
    oleh partisi lokal, disk fisik, atau network mapping (baik aktif maupun Disconnected/Red-X).
    """
    clean_drive = drive_letter.strip().rstrip("\\").upper()
    if not clean_drive.endswith(":"):
        clean_drive += ":"

    # 1. Cek GetLogicalDrives bitmask Win32 (instan, bebas blokir I/O jaringan)
    try:
        idx = ord(clean_drive[0].upper()) - 65
        if 0 <= idx < 26:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            if bitmask != 0 and bool(bitmask & (1 << idx)):
                return True
    except Exception:
        pass

    # 2. Cek apakah masih terdaftar di WNet atau LanmanRedirector (termasuk status 1201 / 1203 Red-X)
    wnet_code, _ = _get_wnet_remote_unc(clean_drive)
    if wnet_code in (0, 1201, 1203):
        return True

    return False


def get_available_drive_letters():
    """
    Mendeteksi secara dinamis seluruh huruf drive Windows yang saat ini
    benar-benar kosong dan belum digunakan oleh partisi fisik atau network mapping.
    Mengembalikan daftar huruf drive dari Z: mundur ke D:.
    """
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        available = []
        for i in range(25, 2, -1):
            d = f"{chr(65 + i)}:"
            if not (bitmask & (1 << i)):
                wnet_code, _ = _get_wnet_remote_unc(d)
                if wnet_code not in (0, 1201, 1203):
                    available.append(d)
        if available:
            return available
    except Exception:
        pass
    return ["Z:", "Y:", "X:", "W:", "V:", "U:", "T:", "S:"]


def get_available_drive_letter(preferred="Z:"):
    """
    Mencari huruf drive kosong yang tersedia secara dinamis.
    """
    clean_p = preferred.strip().rstrip("\\").upper() if preferred else "Z:"
    if not clean_p.endswith(":"):
        clean_p += ":"
    if not is_drive_letter_in_use(clean_p):
        return clean_p

    for d in get_available_drive_letters():
        if not is_drive_letter_in_use(d):
            return d
    return None


def purge_smb_sessions(hosts=None):
    """
    Membersihkan sesi koneksi SMB lama secara menyeluruh (mencegah Windows Error 1219).
    Mendukung pembersihan terhadap single host, list of hosts, atau seluruh sesi SMB aktif
    serta membersihkan drive Red-X (ERROR_CONNECTION_UNAVAIL).
    """
    global _cached_smb_shares
    _cached_smb_shares = {"host": "", "shares": [], "ts": 0.0}
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    bs = chr(92)

    target_hosts = set()
    if hosts:
        if isinstance(hosts, (list, tuple, set)):
            for h in hosts:
                ch = sanitize_input(h).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
                if ch:
                    target_hosts.add(ch)
        elif isinstance(hosts, str):
            ch = sanitize_input(hosts).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
            if ch:
                target_hosts.add(ch)

    # Satu kali 'net use' untuk seluruh fungsi: hanya host/drive yang benar-benar terdaftar di tabel sesi
    # Windows yang dibersihkan (tidak menyentuh WNet/net.exe terhadap host yang tidak punya sesi).
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
                session_hosts.add(unc_val.lstrip(bs).split(bs)[0].lower())
            if drv_val:
                session_drives.add(drv_val)
            session_lines.append((unc_val, drv_val))

    # Sertakan juga nama NetBIOS/PTR (hanya IPv4 privat, timeout ketat) agar sesi alias ikut dibersihkan
    for ch in list(target_hosts):
        nb = _reverse_lookup_fast(ch)
        if nb:
            target_hosts.add(nb)
        if ch in _cached_1219_alias:
            target_hosts.add(_cached_1219_alias[ch])
    _cached_1219_alias.clear()
    target_hosts_lc = {h.lower() for h in target_hosts}

    # 1. Bersihkan drive WNet / LanmanRedirector yang mengarah ke target_hosts (termasuk Disconnected/Red-X)
    handled_drives = set()
    if sys.platform == "win32":
        letters = list(_candidate_network_letters())
        for d in session_drives:
            if d not in letters:
                letters.append(d)
        for d in letters:
            wnet_code, wnet_unc = _get_wnet_remote_unc(d)
            if wnet_code in (0, 1201, 1203) and wnet_unc:
                h_part = wnet_unc.lstrip(bs).split(bs)[0].lower()
                if not target_hosts_lc or h_part in target_hosts_lc or wnet_code == 1203:
                    _cancel_connection_safe(d, force=True, timeout=1.5)
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
                    _remove_dos_lanman_device(d)
                    handled_drives.add(d)

    # 2. Bersihkan entri sesi di 'net use' (UNC target host & drive) yang belum tertangani di langkah 1
    try:
        for unc, drv_code in session_lines:
            if drv_code and drv_code in handled_drives:
                continue
            if unc:
                h_part = unc.lstrip(bs).split(bs)[0].lower()
                if not target_hosts_lc or h_part in target_hosts_lc:
                    _cancel_connection_safe(unc, force=True, timeout=1.5)
                    subprocess.run(
                        ["net.exe", "use", unc, "/DELETE", "/YES"],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        creationflags=creationflags,
                        timeout=3.0,
                    )
            if drv_code:
                _cancel_connection_safe(drv_code, force=True, timeout=1.5)
                subprocess.run(
                    ["net.exe", "use", drv_code, "/DELETE", "/YES"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    creationflags=creationflags,
                    timeout=3.0,
                )
    except Exception:
        pass

    # 3. Hapus sesi IPC$/root UNC hanya untuk host yang benar-benar punya sesi aktif; cmdkey lokal untuk semua host
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

    _notify_windows_explorer_refresh()


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
                _notify_windows_explorer_refresh()
            return True, f"Berhasil memasang {unc_path} ke {target_drive}"

        # Langkah 3 (Standar Zima Client service/smb.go): Jika gagal karena Error 1219 / 85 / 1202 (konflik sesi/drive),
        # bersihkan seluruh sesi lama ke host tersebut, registrasi ulang cmdkey, dan retry 1x dengan kredensial lengkap!
        if any(err_code in combined_out for err_code in ("1219", "85", "1202")):
            logger_manager.log_warning(f"[SMB Mount] Terdeteksi konflik sesi ({combined_out[:80]}). Menjalankan pembersihan otomatis ala Zima Client...")
            unmount_smb_share(target_drive, notify_explorer=False)
            purge_smb_sessions([clean_host])
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
                    _notify_windows_explorer_refresh()
                return True, f"Berhasil memasang {unc_path} ke {target_drive}"
            stderr_msg = (retry_res.stderr or retry_res.stdout or stderr_msg).strip()

            # Langkah 4: Jika masih Error 1219 (misal proses/sesi lain di PC sedang menahan koneksi ke IP yang sama
            # dengan akun berbeda), gunakan alias host dinamis (NetBIOS/PTR lokal gethostbyaddr, nip.io, atau ZeroTier)!
            if "1219" in f"{retry_res.stdout or ''} {retry_res.stderr or ''}":
                for alias_h in _get_dynamic_host_aliases(clean_host, zerotier_ip=zerotier_ip):
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
                            _notify_windows_explorer_refresh()
                        return True, f"Berhasil memasang {alias_unc} ke {target_drive}"

        raw_err = stderr_msg or stdout_msg or "Gagal memasang network drive"
        logger_manager.log_error(f"[SMB Mount] Galat pemasangan {target_drive}: {raw_err}")
        return False, f"{raw_err.strip()} (Jalur: {unc_path})"
    except Exception as e:
        logger_manager.log_error(f"[SMB Mount] Exception saat memasang {target_drive}: {e}")
        return False, str(e)


def mount_all_smb_shares(host, username="", password="", server_connections=None, is_domain_route=None, zerotier_ip=None, auth_token="", base_url="", force_refresh=False):
    """
    Melakukan mounting seluruh share folder disk server yang tersedia ke huruf drive Windows yang bebas.
    Mundur dari Z:, Y:, X:, W:, V:, U:, dst.
    Mencegah duplikasi drive untuk share yang sama serta mengeksekusi registrasi cmdkey & IPC$ cukup 1x per batch.
    """
    resolved_host = resolve_smb_host(
        target_host=host,
        server_connections=server_connections,
        is_domain_route=is_domain_route,
        zerotier_ip=zerotier_ip,
    )
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
    )
    if not shares:
        return False, "Tidak ada share folder disk yang terdeteksi di server."

    # 1. Periksa drive yang sudah ada: jika ada drive Red-X (1201 / 1203) ke host ini, bersihkan dulu.
    #    Jika sudah ada drive sehat (0) ke share yang sama pada host yang sama, catat agar tidak diduplikasi!
    already_mounted_map = {}
    if sys.platform == "win32":
        for d in _candidate_network_letters():
            wnet_code, wnet_unc = _get_wnet_remote_unc(d)
            if wnet_code in (1201, 1203):
                unmount_smb_share(d, notify_explorer=False)
            elif wnet_code == 0 and wnet_unc:
                norm_unc = wnet_unc.rstrip(bs).lower()
                drv_type = ctypes.windll.kernel32.GetDriveTypeW(d + bs)
                if drv_type == 4:
                    if norm_unc in already_mounted_map:
                        unmount_smb_share(d, notify_explorer=False)
                    else:
                        already_mounted_map[norm_unc] = d
                else:
                    unmount_smb_share(d, notify_explorer=False)

    # 2. Lakukan registrasi cmdkey dan pembukaan sesi IPC$ cukup 1x untuk seluruh batch
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
            messages.append(f"• [Drive {target_drive}] {sh} (Terpasang)")
        else:
            messages.append(f"• [Drive {target_drive}] {sh} (Gagal: {msg})")

    _notify_windows_explorer_refresh()
    summary = f"Berhasil memasang {mounted_count} dari {len(shares)} partisi disk:\n" + "\n".join(messages)
    return (mounted_count > 0), summary


def unmount_all_smb_shares():
    """
    Melepaskan seluruh network drive server secara aman.
    Sama sekali TIDAK PERNAH menyentuh drive fisik lokal (C:, D:, dll.).
    Menargetkan drive bertipe DRIVE_REMOTE (GetDriveTypeW == 4) MAUPUN drive jaringan
    yang berstatus Disconnected / Red-X (WNetGetConnectionW == 0, 1201, atau LanmanRedirector 1203).
    """
    unmounted = 0
    for d in _candidate_network_letters():
        try:
            drv_type = ctypes.windll.kernel32.GetDriveTypeW(d + "\\") if sys.platform == "win32" else 0
            wnet_code, _ = _get_wnet_remote_unc(d)
            if drv_type == 4 or wnet_code in (0, 1201, 1203):
                if unmount_smb_share(d, notify_explorer=False):
                    unmounted += 1
        except Exception:
            pass
    if unmounted > 0:
        _notify_windows_explorer_refresh()
    return unmounted


def unmount_smb_share(drive_letter="Z:", notify_explorer=True):
    """
    Melepaskan network mapping SMB secara bersih (termasuk drive berstatus Disconnected / Red-X / Orphaned LanmanRedirector).
    """
    clean_drive = drive_letter.strip().rstrip("\\").upper()
    if not clean_drive.endswith(":"):
        clean_drive += ":"

    unmounted_ok = False
    if sys.platform == "win32":
        if _cancel_connection_safe(clean_drive, force=True, timeout=2.0):
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
        if _remove_dos_lanman_device(clean_drive):
            unmounted_ok = True

    if notify_explorer and unmounted_ok:
        _notify_windows_explorer_refresh()
    return unmounted_ok


def open_drive_in_explorer(drive_letter="Z:"):
    """
    Membuka drive network yang ter-mount langsung di Windows File Explorer.
    """
    clean_drive = drive_letter.strip().rstrip("\\").upper()
    if not clean_drive.endswith(":"):
        clean_drive += ":"

    target_path = f"{clean_drive}\\"
    try:
        if sys.platform == "win32":
            try:
                os.startfile(target_path)
                return True
            except Exception:
                subprocess.Popen(["explorer.exe", target_path])
                return True
        else:
            subprocess.Popen(["explorer.exe", target_path])
            return True
    except Exception:
        return False


def open_unc_root_in_explorer(host, server_connections=None, is_domain_route=None, zerotier_ip=None):
    r"""
    Membuka folder akar jaringan server (\\IP_Server\) langsung di Windows File Explorer.
    """
    resolved_host = resolve_smb_host(
        target_host=host,
        server_connections=server_connections,
        is_domain_route=is_domain_route,
        zerotier_ip=zerotier_ip
    )
    unc_path = f"\\\\{resolved_host}"
    try:
        if sys.platform == "win32":
            os.startfile(unc_path)
            return True
        else:
            subprocess.Popen(["explorer.exe", unc_path])
            return True
    except Exception:
        return False

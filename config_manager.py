import os
import sys
import json
import time
import base64
import re
import socket
import urllib.parse
import urllib.request
import ssl
import shutil
import threading
import ipaddress

import ctypes
if sys.platform == "win32":
    from ctypes import wintypes

SALT_KEY = b'MyServer_ZimaOS_Vault_Salt_2026'
_config_lock = threading.RLock()

if sys.platform == "win32":
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    def _dpapi_protect(data_bytes):
        blob_in = DATA_BLOB()
        blob_in.cbData = len(data_bytes)
        blob_in.pbData = ctypes.cast(ctypes.create_string_buffer(data_bytes), ctypes.POINTER(ctypes.c_byte))
        blob_out = DATA_BLOB()
        if ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), "MyServerVault", None, None, None, 0x1, ctypes.byref(blob_out)
        ):
            out_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return out_bytes
        raise OSError("CryptProtectData failed")

    def _dpapi_unprotect(cipher_bytes):
        blob_in = DATA_BLOB()
        blob_in.cbData = len(cipher_bytes)
        blob_in.pbData = ctypes.cast(ctypes.create_string_buffer(cipher_bytes), ctypes.POINTER(ctypes.c_byte))
        blob_out = DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)
        ):
            out_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return out_bytes
        raise OSError("CryptUnprotectData failed")
else:
    def _dpapi_protect(data_bytes):
        raise NotImplementedError("DPAPI is only supported on Windows")

    def _dpapi_unprotect(cipher_bytes):
        raise NotImplementedError("DPAPI is only supported on Windows")

TRANSLATIONS = {
    "en": {
        "open_server": "Open MyServer",
        "open_fm": "Open File Manager",
        "open_backup": "Open Backup (Remote GUI)",
        "backup_app_info": "Backup App Info",
        "config_backup_app": "⚙ Configure Remote Backup (Dual-Route)...",
        "reload": "Reload (Ctrl+R)",
        "server_menu": "🖥️ Server",
        "add_server": "+ Add New Server...",
        "rename_server": "✏️ Rename Server",
        "delete_server": "- Delete Server",
        "routes_menu": "📶 Access Routes",
        "add_route": "+ Add Access Route...",
        "rename_route": "✏️ Edit / Rename Route",
        "delete_route": "- Delete Access Route",
        "auto_route": "Auto (Local / Failover)",
        "copy_url": "📋 Copy Active URL to Clipboard",
        "url_copied": "Active server URL copied to clipboard!",
        "account_dynamic": "👤 Account ({count}): [{user}]",
        "add_profile": "+ Add New Account...",
        "rename_profile": "✏️ Rename Account",
        "delete_profile": "- Delete Account",
        "store_credentials": "🔑 Save Auto-Login Credentials...",
        "credentials_saved": "Credentials safely encrypted and saved! Auto-login will trigger on server restart.",
        "web_apps_menu": "🌐 Web Apps / Bookmarks",
        "add_web_app": "+ Add New Web App...",
        "no_web_apps": "(No Web Apps configured)",
        "open_app": "▶ Open in New Window",
        "delete_app": "❌ Delete Web App",
        "backup_menu": "💾 Backup / Maintenance",
        "backup_data": "💾 Backup Application Data (ZIP)...",
        "restore_data": "📥 Restore Application Data (ZIP)...",
        "clean_cache_now": "🧹 Clean Browser Cache Now",
        "auto_clean_cache_toggle": "Auto-Clean Cache on Exit",
        "cache_cleaned_msg": "Browser cache cleared successfully! ({size} freed)",
        "preferences_menu": "⚙️ Options / Preferences",
        "reset_app": "⚠️ Reset to Default Setup...",
        "toast_notifications": "Windows Toast Notifications",
        "popup_notifications": "Dialog Popup Alerts",
        "language_menu": "Language / Bahasa",
        "startup_autorun": "Run Automatically on Startup",
        "open_dashboard_on_launch_toggle": "Open Dashboard on Startup",
        "exit": "Exit App",
        "notify_network_switch": "Switched connection to: {target}",
        "notify_server_switched": "Switched to server: {srv}",
        "notify_profile_switched": "Switched to account: {user}",
        "updates_menu": "🔄 System Updates",
        "auto_update_toggle": "Auto-Check Updates (Coming Soon)",
        "check_update_manual": "Check for Updates... (Coming Soon)",
        "install_update_zip": "📦 Install Update from ZIP...",
        "version_info": "Version: v{ver} ({chan})",
        "syncthing_menu": "🔄 Syncthing Manager",
        "open_local_syncthing": "🌐 Open Local Syncthing GUI",
        "open_server_syncthing": "🌐 Open Server Syncthing GUI",
        "start_local_syncthing": "▶ Start Local Syncthing Daemon",
        "stop_local_syncthing": "⏹ Stop Local Syncthing Daemon",
        "rescan_all": "⚡ Force Rescan All Folders",
        "resume_all": "▶ Resume All Sync",
        "pause_all": "⏸ Pause All Sync",
        "config_local_syncthing": "⚙ Configure Local Syncthing...",
        "devices_label": "📱 Devices",
        "tasks_label": "📁 Task Folders",
        "add_sync_task": "➕ Add New Backup Route...",
        "open_in_explorer": "📂 Open Folder in Explorer",
        "rescan_single_folder": "⚡ Rescan This Folder",
        "delete_sync_task": "❌ Delete Backup Task Route",
        "speed_indicator": "⚡ Speed: ⬆️ {up} | ⬇️ {down}",
        "no_items": "(None configured)",
        "server_metrics_menu": "📊 Server Performance (ZimaOS)",
        "cpu_usage": "⚡ CPU Usage",
        "ram_usage": "🧠 RAM Usage",
        "storage_label": "💾 Storage",
        "config_credentials": "🔑 Server Credentials",
        "credentials_configured": "Credentials Configured",
        "pause_my_tasks": "⏸ Pause All Folders",
        "resume_my_tasks": "▶ Resume All Folders",
        "view_changelog": "📋 View Release Notes",
        "config_github_repo": "🌐 GitHub Repository",
        "wake_on_lan": "⚡ Wake on LAN",
        "config_wol": "⚙ Configure Wake on LAN...",
        "power_menu": "⚡ Server Power & WoL"
    },
    "id": {
        "open_server": "Buka MyServer",
        "open_fm": "Buka File Manager",
        "open_backup": "Buka Backup (GUI Server)",
        "backup_app_info": "Info Aplikasi Backup",
        "config_backup_app": "⚙ Konfigurasi Backup Server (Dual-Route)...",
        "reload": "Muat Ulang (Ctrl+R)",
        "server_menu": "🖥️ Server",
        "add_server": "+ Tambah Server Baru...",
        "rename_server": "✏️ Ubah Nama Server",
        "delete_server": "- Hapus Server",
        "routes_menu": "📶 Jalur Akses",
        "add_route": "+ Tambah Jalur Akses Baru...",
        "rename_route": "✏️ Ubah Jalur Akses",
        "delete_route": "- Hapus Jalur Akses",
        "auto_route": "Otomatis (Cek Lokal / Failover)",
        "copy_url": "📋 Salin URL Aktif ke Clipboard",
        "url_copied": "URL server aktif berhasil disalin!",
        "account_dynamic": "👤 Akun ({count}): [{user}]",
        "add_profile": "+ Tambah Akun Baru...",
        "rename_profile": "✏️ Ubah Nama Akun",
        "delete_profile": "- Hapus Akun",
        "store_credentials": "🔑 Simpan Kredensial Auto-Login...",
        "credentials_saved": "Kredensial berhasil dienkripsi dan disimpan! Aplikasi akan login otomatis saat server dimuat ulang.",
        "web_apps_menu": "🌐 Web Apps / Tautan Cepat",
        "add_web_app": "+ Tambah Web App Baru...",
        "no_web_apps": "(Belum ada Web App tersimpan)",
        "open_app": "▶ Buka di Jendela Baru",
        "delete_app": "❌ Hapus Web App",
        "backup_menu": "💾 Backup / Pemeliharaan Data",
        "backup_data": "💾 Backup Data Aplikasi (ZIP)...",
        "restore_data": "📥 Pulihkan Data Aplikasi (ZIP)...",
        "clean_cache_now": "🧹 Bersihkan Cache Browser Sekarang",
        "auto_clean_cache_toggle": "Bersihkan Cache Otomatis saat Keluar",
        "cache_cleaned_msg": "Cache browser berhasil dibersihkan! ({size} dibebaskan)",
        "preferences_menu": "⚙️ Pengaturan / Preferensi",
        "reset_app": "⚠️ Reset ke Pengaturan Awal...",
        "toast_notifications": "Notifikasi Toast Windows",
        "popup_notifications": "Peringatan Dialog Munculan",
        "language_menu": "Pilihan Bahasa",
        "startup_autorun": "Buka Otomatis saat Startup",
        "open_dashboard_on_launch_toggle": "Buka Dashboard saat Aplikasi Dimulai",
        "exit": "Keluar Aplikasi",
        "notify_network_switch": "Koneksi otomatis beralih ke: {target}",
        "notify_server_switched": "Beralih ke server: {srv}",
        "notify_profile_switched": "Beralih ke akun: {user}",
        "updates_menu": "🔄 Pembaruan Sistem",
        "auto_update_toggle": "Pemeriksaan Pembaruan Otomatis (Segera Hadir)",
        "check_update_manual": "Periksa Pembaruan... (Segera Hadir)",
        "install_update_zip": "📦 Pasang Pembaruan dari ZIP...",
        "version_info": "Versi: v{ver} ({chan})",
        "syncthing_menu": "🔄 Manajemen Syncthing",
        "open_local_syncthing": "🌐 Buka GUI Syncthing Lokal",
        "open_server_syncthing": "🌐 Buka GUI Syncthing Server",
        "start_local_syncthing": "▶ Jalankan Daemon Syncthing Lokal",
        "stop_local_syncthing": "⏹ Hentikan Daemon Syncthing Lokal",
        "rescan_all": "⚡ Pindai Ulang Seluruh Folder",
        "resume_all": "▶ Lanjutkan Seluruh Sinkronisasi",
        "pause_all": "⏸ Jeda Seluruh Sinkronisasi",
        "config_local_syncthing": "⚙ Konfigurasi Syncthing Lokal...",
        "devices_label": "📱 Perangkat",
        "tasks_label": "📁 Folder Tugas",
        "add_sync_task": "➕ Tambah Jalur Backup Baru...",
        "open_in_explorer": "📂 Buka Folder di Explorer",
        "rescan_single_folder": "⚡ Pindai Ulang Folder Ini",
        "delete_sync_task": "❌ Hapus Jalur Tugas",
        "speed_indicator": "⚡ Kecepatan: ⬆️ {up} | ⬇️ {down}",
        "no_items": "(Tidak ada)",
        "server_metrics_menu": "📊 Performa Server (ZimaOS)",
        "cpu_usage": "⚡ Penggunaan CPU",
        "ram_usage": "🧠 Penggunaan RAM",
        "storage_label": "💾 Penyimpanan",
        "config_credentials": "🔑 Kredensial Server",
        "credentials_configured": "Kredensial Terkonfigurasi",
        "pause_my_tasks": "⏸ Jeda Semua Folder",
        "resume_my_tasks": "▶ Lanjutkan Semua Folder",
        "view_changelog": "📋 Catatan Rilis",
        "config_github_repo": "🌐 Repositori GitHub",
        "wake_on_lan": "⚡ Bangunkan Server (Wake on LAN)",
        "config_wol": "⚙ Konfigurasi Wake on LAN...",
        "power_menu": "⚡ Kontrol Daya Server"
    }
}



def is_dpapi_supported():
    """
    Melakukan probe runtime nyata ke Windows CryptProtectData in-memory.
    Mengembalikan True jika DPAPI aktif dan sehat, False jika gagal/non-Windows.
    NOL HARDCODE: 100% murni probe dinamis.
    """
    if sys.platform != "win32":
        return False
    try:
        test_probe = b"myserver_dpapi_runtime_probe"
        enc = _dpapi_protect(test_probe)
        dec = _dpapi_unprotect(enc)
        return dec == test_probe
    except Exception:
        return False

def get_base_dir():
    if getattr(sys, "frozen", False):
        d = os.path.dirname(sys.executable)
        if os.path.basename(d).lower() == "bin" and not os.path.exists(os.path.join(d, "config.json")):
            parent = os.path.dirname(d)
            if os.path.exists(os.path.join(parent, "config.json")):
                return parent
        return d
    d = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(d).lower() in ("bin", "sandbox") and not os.path.exists(os.path.join(d, "config.json")):
        parent = os.path.dirname(d)
        if os.path.exists(os.path.join(parent, "config.json")):
            return parent
    return d


def sanitize_name(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def encrypt_credential(raw_str):
    if not raw_str:
        return ""
    if raw_str.startswith("dpapi:") or raw_str.startswith("enc:"):
        return raw_str
    try:
        raw_b = raw_str.encode("utf-8")
        if sys.platform == "win32":
            enc_b = _dpapi_protect(raw_b)
            return "dpapi:" + base64.b64encode(enc_b).decode("ascii")
        else:
            xor_b = bytes([b ^ SALT_KEY[i % len(SALT_KEY)] for i, b in enumerate(raw_b)])
            return "enc:" + base64.b64encode(xor_b).decode("ascii")
    except Exception:
        try:
            raw_b = raw_str.encode("utf-8")
            xor_b = bytes([b ^ SALT_KEY[i % len(SALT_KEY)] for i, b in enumerate(raw_b)])
            return "enc:" + base64.b64encode(xor_b).decode("ascii")
        except Exception:
            return raw_str


def decrypt_credential(stored_str):
    if not stored_str:
        return ""
    curr = stored_str
    max_unwraps = 10
    while max_unwraps > 0 and (curr.startswith("dpapi:") or curr.startswith("enc:")):
        max_unwraps -= 1
        if curr.startswith("dpapi:"):
            try:
                cipher_b = base64.b64decode(curr[6:].encode("ascii"))
                dec_b = _dpapi_unprotect(cipher_b)
                unwrapped = dec_b.decode("utf-8", errors="ignore")
                if not unwrapped or unwrapped == curr:
                    break
                curr = unwrapped
            except Exception:
                break
        elif curr.startswith("enc:"):
            try:
                raw_b = base64.b64decode(curr[4:].encode("ascii"))
                xor_b = bytes([b ^ SALT_KEY[i % len(SALT_KEY)] for i, b in enumerate(raw_b)])
                unwrapped = xor_b.decode("utf-8", errors="ignore")
                if not unwrapped or unwrapped == curr:
                    break
                curr = unwrapped
            except Exception:
                break
    return curr


def get_server_credentials(server, profile_name=None):
    """
    Mengambil data kredensial login (username & decrypted password) untuk server dan profil tertentu
    secara dinamis, toleran, dan aman.
    """
    if not server or not isinstance(server, dict):
        return {"username": "", "password": ""}

    prof = profile_name or server.get("active_profile", "Admin")
    creds_dict = server.get("credentials", {})
    if not isinstance(creds_dict, dict):
        return {"username": "", "password": ""}

    # 1. Coba exact key matching
    c = creds_dict.get(prof)

    # 2. Coba case-insensitive matching
    if not c:
        for k, v in creds_dict.items():
            if k.lower() == str(prof).lower():
                c = v
                break

    # 3. Coba matching berdasarkan nilai username di dalam kredensial
    if not c:
        for k, v in creds_dict.items():
            if isinstance(v, dict) and str(v.get("username", "")).lower() == str(prof).lower():
                c = v
                break

    # 4. Fallback ke kredensial pertama jika hanya ada 1 kredensial tersimpan
    if not c and len(creds_dict) == 1:
        c = list(creds_dict.values())[0]

    if not c or not isinstance(c, dict):
        return {"username": "", "password": ""}

    u_val = c.get("username", "")
    p_enc = c.get("password", "")
    p_dec = decrypt_credential(p_enc) if p_enc else ""
    return {"username": u_val, "password": p_dec}


def save_server_credentials(config, server_id, profile_name, username, password):
    """
    Menyimpan kredensial server dan profil tertentu secara terenkripsi ke dalam konfigurasi.
    """
    if not config or not isinstance(config, dict):
        return False
    for s in config.get("servers", []):
        if s.get("id") == server_id:
            s.setdefault("credentials", {})[profile_name] = {
                "username": username,
                "password": encrypt_credential(password)
            }
            if profile_name not in s.setdefault("profiles", []):
                s["profiles"].append(profile_name)
            save_config(config)
            return True
    return False


def t(key, current_lang=None):
    if not current_lang:
        cfg = load_or_create_config()
        current_lang = cfg.get("language", "en")
    return TRANSLATIONS.get(current_lang, TRANSLATIONS["en"]).get(key, key)


def format_server_url(raw_url):
    url = raw_url.strip().rstrip("/")
    if url.startswith("//"):
        url = url[2:]
    if not url.startswith("http://") and not url.startswith("https://"):
        host = url.split("/")[0].split(":")[0]
        parts = host.split(".")
        is_ip = len(parts) == 4 and all(p.isdigit() for p in parts)
        if is_ip or "localhost" in host or host.endswith(".local"):
            url = "http://" + url
        else:
            url = "https://" + url
    return url


def get_default_config():
    return {
        "active_server_id": "srv_default",
        "servers": [
            {
                "id": "srv_default",
                "name": "Server Utama",
                "connections": [
                    {
                        "id": "conn_default",
                        "name": "Lokal",
                        "url": "http://zimaos.local"
                    }
                ],
                "active_connection": "auto",
                "profiles": [
                    "Admin"
                ],
                "active_profile": "Admin",
                "credentials": {},
                "backup_app": {
                    "lan_mode": "inherit",
                    "lan_ip": "",
                    "lan_port": "8384",
                    "wan_url": "",
                    "api_key": ""
                },
                "wake_on_lan": {
                    "mac_address": "",
                    "broadcast_ip": "255.255.255.255",
                    "port": 9
                }
            }
        ],
        "local_syncthing": {
            "enabled": True,
            "port": "8384",
            "api_key": "",
            "auto_start": True
        },
        "web_apps": [],
        "first_run_setup": True,
        "language": "en",
        "notifications_enabled": True,
        "popup_alerts_enabled": False,
        "auto_update_enabled": False,
        "auto_clean_cache": False,
        "open_dashboard_on_launch": False
    }


def migrate_config_schema(cfg):
    modified = False
    if "open_dashboard_on_launch" not in cfg:
        cfg["open_dashboard_on_launch"] = False
        modified = True
    servers = cfg.get("servers", [])
    base_dir = get_base_dir()

    needs_server_migration = any("connections" not in s for s in servers)
    if needs_server_migration:
        old_profiles = cfg.get("profiles", ["Admin"])
        old_active_p = cfg.get("active_profile", "Admin")
        new_servers = []
        for idx, s in enumerate(servers):
            srv_id = f"srv_{idx}_{int(time.time())}"
            s_name = s.get("name", f"Server {idx + 1}")
            s_url = s.get("url", "http://zimaos.local")
            new_servers.append({
                "id": srv_id,
                "name": s_name,
                "connections": [
                    {
                        "id": "conn_1",
                        "name": "Lokal / Default",
                        "url": s_url
                    }
                ],
                "active_connection": "auto",
                "profiles": list(old_profiles),
                "active_profile": old_active_p,
                "credentials": {},
                "backup_app": {
                    "lan_mode": "inherit",
                    "lan_ip": "",
                    "lan_port": "8384",
                    "wan_url": "",
                    "api_key": ""
                }
            })
            for p in old_profiles:
                old_p_dir = os.path.join(base_dir, "data", "profiles", sanitize_name(p))
                new_p_dir = os.path.join(base_dir, "data", "servers", sanitize_name(srv_id), "profiles", sanitize_name(p))
                if os.path.exists(old_p_dir) and not os.path.exists(new_p_dir):
                    try:
                        os.makedirs(os.path.dirname(new_p_dir), exist_ok=True)
                        shutil.copytree(old_p_dir, new_p_dir)
                    except Exception:
                        pass
        cfg["servers"] = new_servers
        cfg["active_server_id"] = new_servers[0]["id"]
        cfg.pop("profiles", None)
        cfg.pop("active_profile", None)
        cfg.pop("active_server", None)
        modified = True

    for s in cfg.get("servers", []):
        if "credentials" not in s:
            s["credentials"] = {}
            modified = True
        else:
            for u_k, u_v in s["credentials"].items():
                if isinstance(u_v, dict) and "password" in u_v:
                    p_plain = u_v["password"]
                    if p_plain:
                        if p_plain.startswith("dpapi:"):
                            pass
                        elif p_plain.startswith("enc:"):
                            dec_p = decrypt_credential(p_plain)
                            if dec_p:
                                u_v["password"] = encrypt_credential(dec_p)
                                modified = True
                        else:
                            u_v["password"] = encrypt_credential(p_plain)
                            modified = True

        if "backup_app" not in s:
            s["backup_app"] = {
                "route_mode": "auto",
                "lan_mode": "inherit",
                "lan_ip": "",
                "lan_port": "8384",
                "wan_url": "",
                "api_key": ""
            }
            modified = True
        else:
            b_app = s["backup_app"]
            if "route_mode" not in b_app:
                b_app["route_mode"] = "auto"
                modified = True
            if "lan_mode" not in b_app:
                b_app["lan_mode"] = "custom" if b_app.get("ip") else "inherit"
                b_app["lan_ip"] = b_app.get("ip", "")
                b_app["lan_port"] = b_app.get("port", "8384")
                b_app["wan_url"] = ""
                modified = True

        if "wake_on_lan" not in s:
            s["wake_on_lan"] = {
                "mac_address": "",
                "broadcast_ip": "255.255.255.255",
                "port": 9
            }
            modified = True
        else:
            w_cfg = s["wake_on_lan"]
            if "mac_address" not in w_cfg:
                w_cfg["mac_address"] = ""
                modified = True
            if "broadcast_ip" not in w_cfg:
                w_cfg["broadcast_ip"] = "255.255.255.255"
                modified = True
            if "port" not in w_cfg:
                w_cfg["port"] = 9
                modified = True

    if "local_syncthing" not in cfg:
        cfg["local_syncthing"] = {
            "enabled": True,
            "port": "8384",
            "api_key": "",
            "auto_start": True
        }
        modified = True

    if "language" not in cfg:
        cfg["language"] = "en"
        modified = True

    return cfg, modified


def load_or_create_config():
    with _config_lock:
        base_dir = get_base_dir()
        config_path = os.path.join(base_dir, "config.json")
        bak_path = os.path.join(base_dir, "config.json.bak")
        cfg = None
        loaded_from_bak = False

        if os.path.exists(config_path) and os.path.getsize(config_path) > 0:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    cfg = data
            except Exception:
                cfg = None

        if cfg is None and os.path.exists(bak_path) and os.path.getsize(bak_path) > 0:
            try:
                with open(bak_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    cfg = data
                    loaded_from_bak = True
            except Exception:
                cfg = None

        if cfg is None:
            default_cfg = get_default_config()
            save_config(default_cfg)
            return default_cfg

        cfg, modified = migrate_config_schema(cfg)
        if modified or loaded_from_bak:
            save_config(cfg)

        return cfg


def save_config(config):
    with _config_lock:
        base_dir = get_base_dir()
        config_path = os.path.join(base_dir, "config.json")
        bak_path = os.path.join(base_dir, "config.json.bak")
        tmp_path = os.path.join(base_dir, "config.json.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
                f.flush()
                os.fsync(f.fileno())

            if os.path.exists(config_path) and os.path.getsize(config_path) > 0:
                try:
                    with open(config_path, "r", encoding="utf-8") as f_chk:
                        chk_data = json.load(f_chk)
                    if isinstance(chk_data, dict):
                        shutil.copy2(config_path, bak_path)
                except Exception:
                    pass

            for attempt in range(5):
                try:
                    os.replace(tmp_path, config_path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05)

            if not os.path.exists(bak_path) and os.path.exists(config_path):
                try:
                    shutil.copy2(config_path, bak_path)
                except Exception:
                    pass
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass


def reset_config():
    with _config_lock:
        base_dir = get_base_dir()
        for fname in ("config.json", "config.json.bak", "config.json.tmp"):
            p = os.path.join(base_dir, fname)
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


def get_active_server(cfg):
    servers = cfg.get("servers", [])
    if not servers:
        return None
    act_id = cfg.get("active_server_id")
    for s in servers:
        if s.get("id") == act_id:
            return s
    return servers[0]


def is_private_or_local_host(hostname_or_ip):
    if not hostname_or_ip:
        return True
    host = hostname_or_ip.strip().lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback:
            return True
        import zerotier_manager
        return zerotier_manager.is_zerotier_ip(host)
    except (ValueError, Exception):
        return False


def is_domain_or_wan_host(host_str):
    """Memeriksa secara dinamis apakah host merupakan Domain FQDN publik atau IP WAN publik."""
    return not is_private_or_local_host(host_str)

def check_server_ping(url, timeout=1.5):
    """
    Hybrid Server Ping & Reachability Prober:
    1. Adaptive Timeout: 4.5s untuk Domain WAN / FQDN, 1.8s untuk LAN/ZeroTier lokal.
    2. Fast TCP Check: Memastikan port (80/443/custom) atau SMB (445) dapat dihubungi.
    3. HTTP Probe: Menguji respon web server dengan toleransi Cloudflare/Proxy status codes.
    4. Auto-Fallback HTTPS: Jika http:// gagal pada domain publik, coba uji https:// secara transparan.
    Mengembalikan tuple (is_online: bool, latency_ms: int).
    """
    if not url:
        return False, 0
    try:
        raw_u = url if "://" in url else f"http://{url}"
        parsed = urllib.parse.urlparse(raw_u)
        host = parsed.hostname
        if not host:
            return False, 0

        is_domain = is_domain_or_wan_host(host)
        eff_timeout = max(float(timeout or 1.5), 4.5 if is_domain else 1.8)
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

        # Lapis 1: TCP Port Probing cepat
        tcp_ok = False
        t0 = time.time()
        for p in (port, 445):
            try:
                with socket.create_connection((host, int(p)), timeout=min(eff_timeout, 2.5)):
                    tcp_ok = True
                    break
            except Exception:
                continue

        # Jika TCP ke port web dan SMB sama sekali tidak tersambung, rute dipastikan mati
        if not tcp_ok:
            return False, 0

        # Lapis 2: HTTP(S) Application Check
        ctx = ssl.create_default_context()
        if is_private_or_local_host(host):
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        schemes_to_try = [parsed.scheme.lower()]
        if is_domain and parsed.scheme.lower() == "http":
            schemes_to_try.append("https")

        for scheme in schemes_to_try:
            target_test_url = urllib.parse.urlunparse(parsed._replace(scheme=scheme))
            t_req = time.time()
            try:
                req = urllib.request.Request(
                    target_test_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MyServer/3.10.18"}
                )
                with urllib.request.urlopen(req, timeout=eff_timeout, context=ctx) as response:
                    lat_ms = max(1, int((time.time() - t_req) * 1000))
                    if response.status in (200, 204, 301, 302, 307, 308):
                        return True, lat_ms
            except urllib.error.HTTPError as he:
                lat_ms = max(1, int((time.time() - t_req) * 1000))
                # Kode 520-530 (Cloudflare Error 1033 / Origin Unreachable) menandakan origin mati!
                if he.code in (520, 521, 522, 523, 524, 530):
                    return False, 0
                # Respon aplikasi nyata dari web server origin:
                if he.code in (200, 204, 301, 302, 307, 308, 401, 403, 404, 405):
                    return True, lat_ms
            except Exception:
                pass

        # Jika TCP Lapis 1 OK, laporkan True dengan latensi socket
        lat_ms = max(1, int((time.time() - t0) * 1000))
        return True, lat_ms
    except Exception:
        return False, 0


_VIRTUAL_ADAPTER_PREFIXES = {
    "172.24.", "172.25.",   # ZeroTier Network subnets (STIMI & Algitha standard presets)
    "172.20.", "172.21.", "172.22.", "172.23.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.", # ZeroTier standard subnets
    "10.147.", "10.244.",  # ZeroTier Class A pools
    "10.0.5.",   # ZimaOS USB / Direct Cable
    "172.17.", "172.18."   # Docker Bridge
}
_VIRTUAL_ADAPTER_CACHE_TIME = 0


def get_virtual_adapter_prefixes():
    """
    Mengembalikan daftar prefix subnet IP yang terasosiasi dengan adapter virtual/VPN
    (seperti ZeroTier One, Tailscale, TAP/TUN, Docker, Hyper-V, dsb).
    Termasuk preset default ZeroTier (172.25.*) dan Zima Direct (10.0.5.*).
    """
    global _VIRTUAL_ADAPTER_PREFIXES, _VIRTUAL_ADAPTER_CACHE_TIME
    now = time.time()
    if now - _VIRTUAL_ADAPTER_CACHE_TIME < 300 and len(_VIRTUAL_ADAPTER_PREFIXES) > 9:
        return _VIRTUAL_ADAPTER_PREFIXES

    prefixes = set(_VIRTUAL_ADAPTER_PREFIXES)
    if sys.platform == "win32":
        try:
            import subprocess
            cmd = "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -match 'ZeroTier|Tailscale|TAP|TUN|VPN|WireGuard|Virtual|Hyper-V|vEthernet' } | Select-Object -ExpandProperty IPAddress"
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", cmd],
                text=True,
                timeout=1.5,
                creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )
            for line in out.splitlines():
                ip = line.strip()
                if ip and not ip.startswith("169.254.") and not ip.startswith("127."):
                    parts = ip.split(".")
                    if len(parts) >= 2:
                        prefixes.add(f"{parts[0]}.{parts[1]}.")
        except Exception:
            pass

    _VIRTUAL_ADAPTER_PREFIXES = prefixes
    _VIRTUAL_ADAPTER_CACHE_TIME = now
    return _VIRTUAL_ADAPTER_PREFIXES


def classify_connection_priority(conn_or_url):
    """
    Mengklasifikasikan rute koneksi server ke dalam 3-Tier Priority System:
    - Tier 1 (Prioritas 1): IP Lokal LAN Fisik (192.168.x.x, 10.x.x.x non-VPN, 172.16-31.x.x non-ZeroTier/VPN)
    - Tier 2 (Prioritas 2): Domain Publik (FQDN, DDNS, Cloudflare, *.com, *.id, *.my.id, *.duckdns.org, IP WAN)
    - Tier 3 (Prioritas 3): IP Khusus ZimaOS / ZeroTier / Tailscale / Direct Cable / mDNS / Docker (172.25.x.x, 10.0.5.x, zimaos.local, loopback)
    
    Menerima dictionary connection {"name": "...", "url": "...", "tier": ...} ATAU string URL.
    Mengembalikan tuple (tier: int, label: str).
    """
    if not conn_or_url:
        return 3, "Unknown"

    url = ""
    name = ""
    explicit_tier = None

    if isinstance(conn_or_url, dict):
        url = str(conn_or_url.get("url", "")).strip()
        name = str(conn_or_url.get("name", "")).strip().lower()
        explicit_tier = conn_or_url.get("tier")
    else:
        url = str(conn_or_url).strip()

    if not url:
        return 3, "Unknown"

    # Jika pengguna secara eksplisit menentukan tier (1, 2, atau 3)
    if explicit_tier in (1, 2, 3):
        lbl = "LAN" if explicit_tier == 1 else "Domain" if explicit_tier == 2 else "Zima"
        return int(explicit_tier), lbl

    # Cek kata kunci pada nama rute
    if name:
        t3_name_keywords = ("zerotier", "zt", "tailscale", "wireguard", "vpn", "direct cable", "zima direct", "ip khusus", "khusus", "special")
        if any(kw in name for kw in t3_name_keywords):
            return 3, "Zima"

    try:
        raw_u = url if "://" in url else f"http://{url}"
        parsed = urllib.parse.urlparse(raw_u)
        host = (parsed.hostname or url).lower().strip()

        # 1. Cek mDNS lokal ZimaOS / CasaOS
        if host in ("zimaos.local", "casaos.local", "zimaos", "casaos") or host.endswith(".local") or host.endswith(".lan"):
            return 3, "Zima"

        # 2. Cek apakah hostname adalah IP numerik
        try:
            ip_obj = ipaddress.ip_address(host)
            ip_str = str(ip_obj)

            # A. Loopback (127.0.0.1, ::1)
            if ip_obj.is_loopback:
                return 3, "Zima"

            # B. ZimaOS direct USB / cable IP (10.0.5.x)
            if ip_str.startswith("10.0.5."):
                return 3, "Zima"

            # C. Tailscale CGNAT subnet (100.64.0.0/10: 100.64.x.x - 100.127.x.x)
            if ip_str.startswith("100."):
                parts = ip_str.split(".")
                if len(parts) >= 2 and 64 <= int(parts[1]) <= 127:
                    return 3, "Zima"

            # D. ZeroTier subnets dinamis & adapter subnets
            try:
                import zerotier_manager
                if zerotier_manager.is_zerotier_ip(ip_str):
                    return 3, "Zima"
            except Exception:
                pass

            virtual_prefixes = get_virtual_adapter_prefixes()
            for vp in virtual_prefixes:
                if ip_str.startswith(vp):
                    return 3, "Zima"

            # E. Subnet LAN Fisik Standar (192.168.x.x)
            if ip_str.startswith("192.168."):
                return 1, "LAN"

            # F. Subnet 172.16.0.0 - 172.31.255.255 (selain yang sudah tercakup di virtual/ZeroTier di atas)
            if ip_str.startswith("172."):
                parts = ip_str.split(".")
                if len(parts) >= 2 and 16 <= int(parts[1]) <= 31:
                    return 1, "LAN"

            # G. Subnet 10.0.0.0/8 (selain 10.0.5.x dan ZeroTier 10.147/10.244 yang sudah disaring di atas)
            if ip_str.startswith("10."):
                return 1, "LAN"

            # IP publik langsung (bukan domain) -> Masuk Tier 2 (Domain/WAN)
            return 2, "Domain"
        except ValueError:
            # Bukan format IP numerik -> Berarti Hostname / Domain FQDN (Prioritas 2)
            return 2, "Domain"
    except Exception:
        return 3, "Unknown"


def get_dynamic_remote_info(server, config=None):
    """
    Menentukan informasi remote engine aktif secara dinamis (EasyTier vs ZeroTier)
    berdasarkan mode failover ('auto', 'easytier', 'zerotier').
    """
    if not isinstance(server, dict):
        return None
    if config is None:
        try:
            config = load_or_create_config()
        except Exception:
            config = {}

    r_mode = (server.get("remote_mode") or config.get("remote_mode", "auto")).lower()
    srv_zt_vip = (server.get("zerotier_virtual_ip") or "").strip()
    srv_et_vip = (server.get("easytier_virtual_ip") or "").strip()

    # Cek EasyTier jika modul tersedia
    et_peer_ip = None
    et_running = False
    try:
        import easytier_manager
        mgr = easytier_manager.get_easytier_manager()
        et_running = mgr.is_running()
        if et_running:
            et_peer_ip = mgr.get_peer_ip()
    except Exception:
        pass

    chosen_et_ip = et_peer_ip or srv_et_vip

    # 1. Jika mode paksa easytier
    if r_mode == "easytier":
        final_ip = chosen_et_ip or srv_et_vip or "10.126.126.1"
        return {
            "engine": "easytier",
            "name": "EasyTier Remote (P2P)",
            "ip": final_ip,
            "url": f"http://{final_ip}",
            "badge": "P2P"
        }

    # 2. Jika mode paksa zerotier
    if r_mode == "zerotier":
        if srv_zt_vip:
            return {
                "engine": "zerotier",
                "name": "ZeroTier Remote (P2P)",
                "ip": srv_zt_vip,
                "url": f"http://{srv_zt_vip}",
                "badge": "P2P"
            }
        return None

    # 3. Mode AUTO FAILOVER (Default: EasyTier Utama -> ZeroTier Cadangan)
    # EasyTier hanya dipromosikan jika daemon aktif DAN server peer terhubung / dapat dijangkau
    et_healthy = False
    if et_running:
        try:
            import easytier_manager
            mgr = easytier_manager.get_easytier_manager()
            target_check_ip = chosen_et_ip or srv_et_vip or "10.126.126.1"
            et_healthy = mgr.is_peer_reachable(target_check_ip, timeout=0.25)
        except Exception:
            et_healthy = False

    if et_running and et_healthy:
        final_et_ip = chosen_et_ip or srv_et_vip or "10.126.126.1"
        return {
            "engine": "easytier",
            "name": "EasyTier Remote (P2P)",
            "ip": final_et_ip,
            "url": f"http://{final_et_ip}",
            "badge": "P2P"
        }

    # Fallback OTOMATIS ke ZeroTier jika EasyTier tidak aktif atau server peer EasyTier tidak merespons
    if srv_zt_vip:
        return {
            "engine": "zerotier",
            "name": "ZeroTier Remote (P2P)",
            "ip": srv_zt_vip,
            "url": f"http://{srv_zt_vip}",
            "badge": "Fallback" if et_running else "P2P"
        }

    # Jika ZeroTier juga tidak ada, tetap kembalikan EasyTier jika daemon aktif
    if et_running:
        final_et_ip = chosen_et_ip or srv_et_vip or "10.126.126.1"
        return {
            "engine": "easytier",
            "name": "EasyTier Remote (P2P)",
            "ip": final_et_ip,
            "url": f"http://{final_et_ip}",
            "badge": "P2P"
        }

    return None


def resolve_target_connection(config, check_network=True, current_loaded_url=None, target_server=None):
    cur_l = config.get("language", "en")
    server = target_server if target_server else get_active_server(config)
    if not server:
        return "http://zimaos.local", "No Server Configured" if cur_l == "en" else "Belum Ada Server"
    
    connections = list(server.get("connections", []))
    
    # Injeksi Rute Dinamis Remote Tunggal (Tier 3) (EasyTier <-> ZeroTier Failover)
    rem_info = get_dynamic_remote_info(server, config)
    if rem_info and rem_info.get("url"):
        rem_u = rem_info["url"]
        if not any(c.get("url", "").rstrip("/") == rem_u.rstrip("/") for c in connections):
            connections.append({
                "id": "conn_remote_dynamic",
                "name": rem_info["name"],
                "url": rem_u,
                "tier": 3,
                "isRemoteDynamic": True,
                "isZeroTier": (rem_info["engine"] == "zerotier"),
                "isEasyTier": (rem_info["engine"] == "easytier"),
                "badge": rem_info["badge"]
            })

    if not connections:
        return "http://zimaos.local", f"{server['name']}: No Routes" if cur_l == "en" else f"{server['name']}: Tanpa Jalur"
    
    active_conn = server.get("active_connection", "auto")
    auto_txt = "Auto" if cur_l == "en" else "Otomatis"
    
    # 1. Rute Manual Spesifik yang dipilih pengguna
    if active_conn != "auto":
        # Periksa apakah pengguna memilih rute remote dinamis (EasyTier / ZeroTier)
        if rem_info and (active_conn in ("conn_remote_dynamic", "conn_zerotier_auto") or active_conn == rem_info["url"]):
            target_u = rem_info["url"]
            if check_network:
                ok, ms = check_server_ping(target_u, timeout=2.0)
                lat_str = f" ({ms}ms)" if ok else " (Offline)"
                return target_u, f"{rem_info['name']}: {target_u}{lat_str}"
            else:
                return target_u, f"{rem_info['name']}: {target_u}"

        for c in connections:
            if c["id"] == active_conn or c["url"] == active_conn:
                if check_network:
                    ok, ms = check_server_ping(c["url"], timeout=2.0)
                    lat_str = f" ({ms}ms)" if ok else " (Offline)"
                    return c["url"], f"{c['name']}: {c['url']}{lat_str}"
                else:
                    return c["url"], f"{c['name']}: {c['url']}"
        c = connections[0]
        return c["url"], f"{c['name']}: {c['url']}"
    
    # 2. Rute Otomatis: Klasifikasikan ke dalam 3-Tier Priority System
    # Tier 1: IP Lokal LAN Fisik (Prioritas 1)
    # Tier 2: Domain Publik (Prioritas 2)
    # Tier 3: IP Khusus Zima / ZeroTier / Direct Link / Fallback (Prioritas 3)
    tier1_conns = []
    tier2_conns = []
    tier3_conns = []

    for c in connections:
        tier, _ = classify_connection_priority(c)
        if tier == 1:
            tier1_conns.append(c)
        elif tier == 2:
            tier2_conns.append(c)
        else:
            tier3_conns.append(c)

    # A. Jika check_network=False: prioritaskan rute Tier 1 (LAN), lalu Tier 2 (Domain), lalu Tier 3 (Zima/ZeroTier)
    if not check_network:
        for c in tier1_conns:
            return c["url"], f"{auto_txt} (LAN: {c['url']})" if cur_l == "en" else f"{auto_txt} (Lokal LAN: {c['url']})"
        for c in tier2_conns:
            return c["url"], f"{auto_txt} (Domain: {c['url']})"
        for c in tier3_conns:
            lbl = "ZeroTier" if c.get("isZeroTier") else "Zima"
            return c["url"], f"{auto_txt} ({lbl}: {c['url']})"
        return connections[0]["url"], f"{auto_txt} ({connections[0]['name']}: {connections[0]['url']})"

    # B. Jika check_network=True:
    # Tahap 1: Cek IP Lokal LAN (Prioritas Utama di Rumah)
    for c in tier1_conns:
        ok, ms = check_server_ping(c["url"], timeout=1.5)
        if ok:
            return c["url"], f"{auto_txt} (LAN: {c['url']} - {ms}ms)" if cur_l == "en" else f"{auto_txt} (Lokal LAN: {c['url']} - {ms}ms)"

    # Tahap 2: Cek Domain Publik (Prioritas Utama saat di Luar Rumah)
    for c in tier2_conns:
        ok, ms = check_server_ping(c["url"], timeout=4.5)
        if ok:
            return c["url"], f"{auto_txt} (Domain: {c['url']} - {ms}ms)"

    # Tahap 3: Cek IP Khusus Zima / Direct Link / ZeroTier
    for c in tier3_conns:
        ok, ms = check_server_ping(c["url"], timeout=2.5)
        if ok:
            lbl = "EasyTier" if c.get("isEasyTier") else ("ZeroTier" if c.get("isZeroTier") else ("Special/Zima" if cur_l == "en" else "Khusus/Zima"))
            return c["url"], f"{auto_txt} ({lbl}: {c['url']} - {ms}ms)"

    # Fallback Cerdas jika seluruh rute offline (Anti-Banting ke LAN jika posisi remote):
    # Jika saat ini berada di rute remote (Domain / ZeroTier), pertahankan rute remote tersebut!
    if current_loaded_url:
        for c in tier2_conns + tier3_conns:
            if c["url"].rstrip("/") == current_loaded_url.rstrip("/"):
                return c["url"], f"{auto_txt} ({c['name']}: {c['url']} - Offline)"

    # Prioritaskan fallback ke Domain/ZeroTier alih-alih LAN jika ada rute remote
    fallback_ordered = tier2_conns + tier3_conns + tier1_conns
    fallback = fallback_ordered[0] if fallback_ordered else connections[0]
    return fallback["url"], f"{auto_txt} ({fallback['name']}: {fallback['url']} - Offline)"


_SYNCTHING_ROUTE_CACHE = {}


def clear_syncthing_route_cache():
    """Mengosongkan cache rute Syncthing agar konfigurasi atau kunci API baru langsung aktif."""
    global _SYNCTHING_ROUTE_CACHE
    _SYNCTHING_ROUTE_CACHE.clear()


def check_syncthing_ping(target_url, timeout=1.2):
    """
    Memeriksa ketersediaan endpoint Syncthing secara mandiri (tanpa bergantung pada IP ZimaOS).
    Menguji endpoint /rest/noauth/health atau /rest/system/ping atau root HTTP.
    Mengembalikan tuple (is_online: bool, latency_ms: int).
    """
    if not target_url:
        return False, 0
    t0 = time.time()
    try:
        url_health = target_url.rstrip("/") + "/rest/noauth/health"
        req = urllib.request.Request(url_health, headers={"User-Agent": "MyServer-Desktop-App/3.6.7"})
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                lat_ms = max(1, int((time.time() - t0) * 1000))
                return True, lat_ms
        except urllib.error.HTTPError as he:
            if he.code in (200, 301, 302, 401, 403, 404):
                lat_ms = max(1, int((time.time() - t0) * 1000))
                return True, lat_ms
        except Exception:
            pass

        # Fallback ke root URL
        try:
            req_root = urllib.request.Request(target_url.rstrip("/"), headers={"User-Agent": "MyServer-Desktop-App/3.6.7"})
            with urllib.request.urlopen(req_root, timeout=timeout, context=ctx) as resp:
                lat_ms = max(1, int((time.time() - t0) * 1000))
                return True, lat_ms
        except urllib.error.HTTPError as he2:
            if he2.code in (200, 301, 302, 401, 403, 404):
                lat_ms = max(1, int((time.time() - t0) * 1000))
                return True, lat_ms
        except Exception:
            pass

        return False, 0
    except Exception:
        return False, 0


def get_effective_backup_app_target(server, cfg=None, current_loaded_url=None, check_network=True):
    """
    Menghitung target rute Syncthing server yang efektif secara dinamis dan mandiri.
    Tidak bergantung pada IP atau status koneksi Web UI ZimaOS.
    Mengembalikan tuple: (host, port, api_key, full_url, active_route_name, use_https)
    """
    global _SYNCTHING_ROUTE_CACHE
    if not server:
        return "", "8384", "", "", "none", False

    srv_id = server.get("id", "srv_default")
    b_app = server.get("backup_app", {})
    api_key = b_app.get("api_key", "").strip()
    route_mode = str(b_app.get("route_mode", "auto")).strip().lower()
    lan_mode = str(b_app.get("lan_mode", "inherit")).strip().lower()
    lan_ip = str(b_app.get("lan_ip") or b_app.get("ip") or "").strip()
    lan_port = str(b_app.get("lan_port") or b_app.get("port") or "8384").strip() or "8384"
    wan_url = str(b_app.get("wan_url", "")).strip()

    # 1. Tentukan Kandidat Jalur Lokal (LAN Candidate)
    lan_host = ""
    lan_p = lan_port
    lan_https = False
    if lan_mode == "custom" and lan_ip:
        raw_l = lan_ip
        if "://" in raw_l:
            p_lan = urllib.parse.urlparse(raw_l)
            lan_host = p_lan.hostname or raw_l
            lan_p = str(p_lan.port or lan_port)
            lan_https = (p_lan.scheme.lower() == "https")
        elif ":" in raw_l:
            parts = raw_l.split(":")
            lan_host = parts[0]
            lan_p = parts[1] or lan_port
        else:
            lan_host = raw_l
    else:
        # Fallback lokal: coba cari koneksi lokal dari connections server
        conns = server.get("connections", [])
        for c in conns:
            u = c.get("url", "").lower()
            if any(k in u for k in ("192.168.", "10.", "172.", "localhost", "127.0.0.1", ".local", "lokal")):
                p_c = urllib.parse.urlparse(c.get("url", ""))
                if p_c.hostname:
                    lan_host = p_c.hostname
                    break
        if not lan_host and conns:
            p_c = urllib.parse.urlparse(conns[0].get("url", ""))
            lan_host = p_c.hostname or "127.0.0.1"
        if not lan_host:
            lan_host = "127.0.0.1"

    lan_scheme = "https" if lan_https else "http"
    lan_url = f"{lan_scheme}://{lan_host}:{lan_p}"
    lan_target = (lan_host, lan_p, api_key, lan_url, f"LAN Lokal ({lan_host}:{lan_p})", lan_https)

    # 2. Tentukan Kandidat Jalur Publik (WAN Candidate) & ZeroTier
    wan_target = None
    if wan_url:
        clean_wan = str(wan_url).strip()
        wan_p = str(b_app.get("wan_port", "")).strip() or "8384"
        wan_https_cfg = bool(b_app.get("wan_https", False))
        if "://" in clean_wan:
            p_wan = urllib.parse.urlparse(clean_wan)
            wan_host = p_wan.hostname or clean_wan
            wan_https = (p_wan.scheme.lower() == "https") or wan_https_cfg
            if p_wan.port:
                wan_p = str(p_wan.port)
            elif wan_https:
                wan_p = "443"
            else:
                wan_p = wan_p or "8384"
            clean_wan_url = f"{'https' if wan_https else 'http'}://{wan_host}:{wan_p}" if wan_p not in ("80", "443") else f"{'https' if wan_https else 'http'}://{wan_host}"
        elif ":" in clean_wan and not clean_wan.startswith("["):
            parts = clean_wan.split(":")
            wan_host = parts[0]
            wan_p = parts[1] or wan_p
            wan_https = wan_https_cfg
            clean_wan_url = f"{'https' if wan_https else 'http'}://{wan_host}:{wan_p}"
        else:
            wan_host = clean_wan
            wan_https = wan_https_cfg
            clean_wan_url = f"{'https' if wan_https else 'http'}://{wan_host}:{wan_p}"

        wan_target = (wan_host, wan_p, api_key, clean_wan_url, f"WAN / Subdomain ({wan_host})", wan_https)

    zt_target = None
    zt_ip = str(server.get("zerotier_virtual_ip") or "").strip()
    if zt_ip:
        zt_p = lan_port or "8384"
        zt_url = f"http://{zt_ip}:{zt_p}"
        zt_target = (zt_ip, zt_p, api_key, zt_url, f"ZeroTier ({zt_ip}:{zt_p})", False)

    # 3. Pemilihan Rute berdasarkan mode
    if route_mode == "lan":
        return lan_target
    if route_mode == "wan":
        return wan_target if wan_target else (zt_target or lan_target)

    # Mode 'auto' (Dinamis / Otomatis):
    # Jika check_network=False (misal saat render menu tray): gunakan cache jika masih valid
    now = time.time()
    cache_entry = _SYNCTHING_ROUTE_CACHE.get(srv_id)
    if cache_entry and len(cache_entry.get('target', ())) > 2:
        if cache_entry['target'][2] != api_key:
            cache_entry = None
            _SYNCTHING_ROUTE_CACHE.pop(srv_id, None)
    if not check_network:
        if cache_entry and (now - cache_entry.get("time", 0) < 15.0):
            return cache_entry["target"]
        # Fallback cepat tanpa blocking jika belum ada cache
        return lan_target if lan_target else (wan_target or zt_target or lan_target)

    # Lakukan deteksi dinamis mandiri (auto-probe independen dari ZimaOS IP)
    # A. Uji jalur LAN terlebih dahulu (prioritas kecepatan transfer)
    lan_ok, lan_lat = check_syncthing_ping(lan_url, timeout=0.8)
    if lan_ok:
        active_route_name = f"LAN Lokal ({lan_host}:{lan_p} - {lan_lat}ms)"
        res = (lan_host, lan_p, api_key, lan_url, active_route_name, lan_https)
        _SYNCTHING_ROUTE_CACHE[srv_id] = {"target": res, "time": now}
        return res

    # B. Jika LAN tidak aktif, uji jalur ZeroTier Virtual IP jika ada
    if zt_target:
        zt_ok, zt_lat = check_syncthing_ping(zt_target[3], timeout=1.2)
        if zt_ok:
            active_route_name = f"ZeroTier Remote ({zt_target[0]}:{zt_target[1]} - {zt_lat}ms)"
            res = (zt_target[0], zt_target[1], api_key, zt_target[3], active_route_name, zt_target[5])
            _SYNCTHING_ROUTE_CACHE[srv_id] = {"target": res, "time": now}
            return res

    # C. Jika belum aktif, uji jalur WAN / Subdomain jika ada
    if wan_target:
        wan_ok, wan_lat = check_syncthing_ping(wan_target[3], timeout=1.2)
        if wan_ok:
            active_route_name = f"WAN / Subdomain ({wan_target[0]} - {wan_lat}ms)"
            res = (wan_target[0], wan_target[1], api_key, wan_target[3], active_route_name, wan_target[5])
            _SYNCTHING_ROUTE_CACHE[srv_id] = {"target": res, "time": now}
            return res

    # D. Jika seluruhnya offline, gunakan entri cache terakhir jika ada, atau fallback kandidat
    if cache_entry and (now - cache_entry.get("time", 0) < 30.0):
        return cache_entry["target"]

    fallback_target = zt_target if zt_target else (wan_target if wan_target else lan_target)
    off_name = f"{fallback_target[4]} (Offline)"
    res = (fallback_target[0], fallback_target[1], api_key, fallback_target[3], off_name, fallback_target[5])
    _SYNCTHING_ROUTE_CACHE[srv_id] = {"target": res, "time": now}
    return res


def get_server_wol_config(server):
    """
    Mengambil konfigurasi Wake on LAN untuk server tertentu.
    Mengembalikan dict {"mac_address": str, "broadcast_ip": str, "port": int}
    """
    if not server or not isinstance(server, dict):
        return {"mac_address": "", "broadcast_ip": "255.255.255.255", "port": 9}
    wol = server.get("wake_on_lan")
    if not wol or not isinstance(wol, dict):
        wol = {"mac_address": "", "broadcast_ip": "255.255.255.255", "port": 9}
    return {
        "mac_address": str(wol.get("mac_address", "")).strip().upper(),
        "broadcast_ip": str(wol.get("broadcast_ip", "255.255.255.255")).strip() or "255.255.255.255",
        "port": int(wol.get("port", 9)) if str(wol.get("port", 9)).isdigit() else 9
    }


def save_server_wol_config(server_id, mac_address, broadcast_ip="255.255.255.255", port=9):
    """
    Menyimpan konfigurasi Wake on LAN untuk server dengan id tertentu ke config.json.
    """
    cfg = load_or_create_config()
    modified = False
    for s in cfg.get("servers", []):
        if s.get("id") == server_id or not server_id:
            s["wake_on_lan"] = {
                "mac_address": str(mac_address).strip().upper(),
                "broadcast_ip": str(broadcast_ip).strip() or "255.255.255.255",
                "port": int(port) if str(port).isdigit() else 9
            }
            modified = True
            break
    if modified:
        save_config(cfg)
    return modified



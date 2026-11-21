def get_active_remote_ip(srv, cfg=None):
    """Menentukan alamat IP remote aktif secara dinamis antara EasyTier dan ZeroTier."""
    if not isinstance(srv, dict):
        return ""
    try:
        rem_info = config_manager.get_dynamic_remote_info(srv, cfg)
        if rem_info and rem_info.get("ip"):
            return rem_info["ip"]
    except Exception as e:
        logger_manager.log_debug(f"[get_active_remote_ip] Error: {e}")
    r_mode = (srv.get("remote_mode") or (cfg.get("remote_mode") if cfg else "auto") or "auto").lower()
    if r_mode == "easytier":
        return (srv.get("easytier_virtual_ip") or "").strip()
    return (srv.get("zerotier_virtual_ip") or "").strip()


"""







MyServer Core Service v3.10.0 Beta (Headless Companion Backend)







Menggantikan pywebview WinForms engine dengan headless companion daemon.







Menyediakan REST API lokal (127.0.0.1) untuk dikonsumsi oleh antarmuka Tauri v2.







"""















import argparse







import ipaddress
import datetime







import ctypes







from ctypes import wintypes







import json







import re







import traceback







import os







import shutil







import subprocess







import sys







import threading







import time
import uuid







import urllib.error







import urllib.parse







import urllib.request







import webbrowser







import winreg







import zipfile







from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer















# Pastikan sys.path mencakup direktori parent (Beta/) agar modul manajer dapat diimpor







current_dir = os.path.dirname(os.path.abspath(__file__))







parent_dir = os.path.dirname(current_dir)







if parent_dir not in sys.path:







    sys.path.insert(0, parent_dir)







if current_dir not in sys.path:







    sys.path.insert(0, current_dir)















# Import manajer modular MyServer







import changelog_manager







import config_manager







import dialog_helper







import logger_manager







import smb_mount_manager







import syncthing_manager







import wol_manager







import zerotier_manager
try:
    import easytier_manager
except ImportError:
    easytier_manager = None







import zima_metrics_manager















try:
    import instabox_manager
except ImportError:
    instabox_manager = None

APP_VERSION_NUMBER = "4.6.5"

CORE_VERSION = f"{APP_VERSION_NUMBER}-beta"

APP_FULL_VERSION = f"MyServer v{APP_VERSION_NUMBER} [Beta]"







DEFAULT_PORT = 48123







REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"







AUTORUN_KEY_NAME = "MyServerCompanion"















# State global cache & pengukuran jaringan







_state_lock = threading.Lock()







_drives_cache_lock = threading.Lock()







_cached_live_drives = []



_inflight_live_drives = set()



_cached_live_drive_space = {}







_last_net_bytes = {"in": 0, "out": 0, "time": 0.0}







_last_speed_result = (0.0, 0.0)















_cached_state = {







    "server_name": "MyServer",







    "is_online": False,







    "route_name": "LAN Fisik",







    "ip": "127.0.0.1",







    "server_url": "http://127.0.0.1",







    "cpu_percent": 0,







    "ram_percent": 0,







    "disk_percent": 0,







    "ping_str": "OK",







    "speed_down": 0,







    "speed_up": 0,







    "sync_down": 0,







    "sync_up": 0,



    "is_admin": False,







    "cpu_temperature": None,







    "cpu_wattage": 0.0,







    "ram_used_bytes": 0,







    "ram_total_bytes": 0,







    "storage_used_bytes": 0,







    "storage_total_bytes": 0,







    "storage_partitions": [],







}















_cached_compose_apps = []







_last_compose_fetch_time = 0.0























def format_bytes_size(b):







    """Format bytes ke string terbaca manusia."""







    if b < 1024:







        return f"{b} B"







    elif b < 1024 * 1024:







        return f"{b / 1024:.1f} KB"







    elif b < 1024 * 1024 * 1024:







        return f"{b / (1024 * 1024):.1f} MB"







    elif b < 1024 * 1024 * 1024 * 1024:







        return f"{b / (1024 * 1024 * 1024):.1f} GB"







    else:







        return f"{b / (1024 * 1024 * 1024 * 1024):.1f} TB"























_gui_exe_cache = {"path": "", "parent_pid": 0}























def _query_process_image_path(pid):







    """Mengambil path executable proses berdasarkan PID (dinamis, tanpa nama biner yang ditanam)."""







    try:







        k32 = ctypes.windll.kernel32







        k32.OpenProcess.restype = ctypes.c_void_p







        handle = k32.OpenProcess(0x1000, False, int(pid))







        if not handle:







            return ""







        try:







            buf = ctypes.create_unicode_buffer(1024)







            size = ctypes.c_ulong(1024)







            if k32.QueryFullProcessImageNameW(ctypes.c_void_p(handle), 0, buf, ctypes.byref(size)):







                return buf.value or ""







        finally:







            k32.CloseHandle(ctypes.c_void_p(handle))







    except Exception:







        pass







    return ""























def _own_core_exe_name():







    """Nama executable proses backend ini (kosong jika berjalan dari source)."""







    if getattr(sys, "frozen", False):







        return os.path.basename(sys.executable).lower()







    return ""























def get_gui_executable_path():







    """







    Mencari biner GUI utama (Tauri shell + System Tray) secara 100% dinamis:







    1. Image path proses parent (GUI yang meluncurkan backend ini via --parent-pid).







    2. Pemindaian folder backend & parent-nya untuk executable dengan awalan nama produk yang sama







       dengan backend (diturunkan dari nama executable backend sendiri), selain backend & uninstaller.







    Tidak pernah mengembalikan executable backend itu sendiri.







    """







    own = _own_core_exe_name()







    cached = _gui_exe_cache.get("path", "")







    if cached and os.path.isfile(cached):







        return cached







    found = ""







    ppid = int(_gui_exe_cache.get("parent_pid", 0) or 0)







    if ppid > 0:







        cand = _query_process_image_path(ppid)







        if cand and os.path.isfile(cand) and os.path.basename(cand).lower() != own:







            found = cand







    if not found and own:







        prefix = re.split(r"[-_ .]", os.path.splitext(own)[0])[0]







        core_dir = os.path.dirname(os.path.abspath(sys.executable))







        scan_dirs = []







        for d in (core_dir, os.path.dirname(core_dir)):







            if d and d not in scan_dirs:







                scan_dirs.append(d)







        for d in scan_dirs:







            try:







                names = sorted(os.listdir(d))







            except Exception:







                continue







            for n in names:







                ln = n.lower()







                if not ln.endswith(".exe") or ln == own or ln.startswith("unins") or "core" in ln:







                    continue







                if prefix and ln.startswith(prefix):







                    found = os.path.join(d, n)







                    break







            if found:







                break







    if found:







        _gui_exe_cache["path"] = found







    return found























def _registry_exe_path(cmd_value):







    """Mengekstrak path executable dari nilai Registry Run (dengan/ tanpa tanda kutip & argumen)."""







    v = str(cmd_value or "").strip()







    if v.startswith('"'):







        end = v.find('"', 1)







        return v[1:end] if end > 0 else v[1:]







    idx = v.lower().find(".exe")







    return v[:idx + 4] if idx >= 0 else v























def _read_autorun_registry_value():







    try:







        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ)







        try:







            val, _ = winreg.QueryValueEx(key, AUTORUN_KEY_NAME)







        finally:







            winreg.CloseKey(key)







        return str(val) if val else ""







    except Exception:







        return ""























def is_autorun_enabled():







    """Memeriksa apakah MyServer terdaftar di Registry autorun Windows dan mengarah ke biner GUI yang valid."""







    val = _read_autorun_registry_value()







    if not val:







        return False







    exe = _registry_exe_path(val)







    if not exe or not os.path.isfile(exe):







        return False







    own = _own_core_exe_name()







    return not (own and os.path.basename(exe).lower() == own)























def ensure_autorun_registry_healthy(cfg=None):







    """







    Self-healing Registry autorun saat startup: entri lama yang menunjuk ke backend headless







    (atau path kadaluarsa) diperbaiki agar menunjuk ke biner GUI. Entri hanya dibuat/dipertahankan







    bila pengguna memang mengaktifkan autostart (config 'autostart' atau entri Registry sudah ada).







    """







    try:







        gui = get_gui_executable_path()







        if not gui:







            return False







        if cfg is None:







            cfg = config_manager.load_or_create_config()







        cur_val = _read_autorun_registry_value()







        wanted = bool(cfg.get("autostart", False)) or bool(cur_val)







        if not wanted:







            return False







        cur_exe = _registry_exe_path(cur_val) if cur_val else ""







        if cur_exe and os.path.normcase(os.path.abspath(cur_exe)) == os.path.normcase(os.path.abspath(gui)):







            healthy = True







        else:







            healthy = set_autorun(True)







            logger_manager.log_info(f"[CoreService] Registry autorun diperbaiki -> {gui}")







        if healthy and not cfg.get("autostart", False):







            cfg["autostart"] = True







            config_manager.save_config(cfg)







        return healthy







    except Exception as e:







        logger_manager.log_error(f"[CoreService] Gagal memeriksa Registry autorun: {e}")







        return False























def set_autorun(enable=True):







    """Menambah atau menghapus entri autorun Windows."""







    try:







        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_ALL_ACCESS)







        if enable:







            exe_path = get_gui_executable_path()







            if not exe_path:







                winreg.CloseKey(key)







                logger_manager.log_error("[CoreService] Biner GUI tidak ditemukan, autorun tidak diubah.")







                return False







            cmd = f'"{exe_path}"'







            winreg.SetValueEx(key, AUTORUN_KEY_NAME, 0, winreg.REG_SZ, cmd)







        else:







            try:







                winreg.DeleteValue(key, AUTORUN_KEY_NAME)







            except FileNotFoundError:







                pass







        winreg.CloseKey(key)







        return True







    except Exception:







        return False























def clean_webview_cache(base_dir=None):







    """Membersihkan cache WebView2 secara aman."""







    if not base_dir:







        base_dir = config_manager.get_base_dir()







    cache_dirs = [







        os.path.join(base_dir, "EBWebView", "Default", "Cache"),







        os.path.join(base_dir, "EBWebView", "Default", "Code Cache"),







        os.path.join(base_dir, "EBWebView", "Default", "GPUCache"),







        os.path.join(base_dir, "EBWebView", "Default", "Service Worker", "CacheStorage"),







    ]







    freed_bytes = 0







    for c_dir in cache_dirs:







        if os.path.exists(c_dir):







            for root, dirs, files in os.walk(c_dir):







                for f in files:







                    fp = os.path.join(root, f)







                    try:







                        freed_bytes += os.path.getsize(fp)







                    except Exception:







                        pass







            try:







                shutil.rmtree(c_dir, ignore_errors=True)







            except Exception:







                pass







    return freed_bytes























SHORTCUT_JS = """







if (!window._zima_shortcut_installed) {







    window._zima_shortcut_installed = true;







    document.addEventListener('keydown', function(e) {







        if ((e.ctrlKey && (e.key === 'r' || e.key === 'R')) || e.key === 'F5') {







            e.preventDefault();







            window.location.reload();







        }







    }, true);







}







"""























def _sanitize_profile_folder_name(val):



    if not val:



        return "Default"



    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(val)).strip() or "Default"











def is_zimaos_dashboard_target(target_url, cfg=None):

    """

    Memverifikasi apakah target_url mengarah ke Dashboard ZimaOS resmi (bukan aplikasi Docker / port kustom).

    Mencegah kebocoran kredensial OS ke form login aplikasi pihak ketiga.

    """

    clean_u = (target_url or "").strip()

    if not clean_u:

        return False

    try:

        parsed_target = urllib.parse.urlparse(clean_u)

        t_host = (parsed_target.hostname or "").lower()

        t_port = parsed_target.port or (443 if parsed_target.scheme.lower() == "https" else 80)

        t_path = (parsed_target.path or "/").rstrip("/")



        if cfg is None:

            cfg = config_manager.load_or_create_config()



        servers = cfg.get("servers", [])

        target_srv = None



        for s in servers:

            if not isinstance(s, dict):

                continue

            for conn in s.get("connections", []):

                c_url = conn.get("url", "")

                if not c_url:

                    continue

                parsed_c = urllib.parse.urlparse(c_url)

                c_host = (parsed_c.hostname or "").lower()

                c_port = parsed_c.port or (443 if parsed_c.scheme.lower() == "https" else 80)

                if t_host == c_host and t_port == c_port:

                    target_srv = s

                    break

            if target_srv:

                break

            zt_ip = (s.get("zerotier_virtual_ip") or "").strip().lower()

            if zt_ip and t_host == zt_ip and t_port in (80, 443):

                target_srv = s

                break



        if not target_srv:

            return False



        # Host dan port cocok dengan rute server aktif ZimaOS resmi milik pengguna
        # Izinkan dashboard dan modul resmi ZimaOS (icewhale_files dsb), tolak domain luar
        return True

    except Exception:

        return False





def generate_autologin_js(username, password, access_token="", refresh_token=""):



    if not username and not access_token:



        return ""



    safe_u = json.dumps(username or "")



    safe_p = json.dumps(password or "")



    safe_tok = json.dumps(access_token or "")



    safe_ref = json.dumps(refresh_token or "")



    return f"""



    (function() {{



        try {{



            const tok = {safe_tok};



            const ref = {safe_ref};



            if (tok) {{



                const curTok = localStorage.getItem('access_token') || localStorage.getItem('token') || '';



                localStorage.setItem('access_token', tok);



                localStorage.setItem('token', tok);



                sessionStorage.setItem('access_token', tok);



                sessionStorage.setItem('token', tok);



                if (ref) {{



                    localStorage.setItem('refresh_token', ref);



                    sessionStorage.setItem('refresh_token', ref);



                }}



                document.cookie = 'token=' + encodeURIComponent(tok) + '; path=/';



                document.cookie = 'access_token=' + encodeURIComponent(tok) + '; path=/';



                if (!curTok && (window.location.hash.toLowerCase().includes('login') || window.location.pathname.toLowerCase().includes('login'))) {{



                    window.location.hash = '#/';



                    window.location.reload();



                    return;



                }}



            }}



        }} catch (e) {{}}







                if (window._zima_autologin_injected) return;

        window._zima_autologin_injected = true;



        // Layer 2 Guard: Verifikasi tanda tangan DOM CasaOS / ZimaOS sebelum menyentuh form

        try {{

            const isCasaOrZima = document.querySelector('#app') && 

                (document.title.toLowerCase().includes('zima') || 

                 document.title.toLowerCase().includes('casa') ||

                 document.querySelector('meta[name="application-name"]')?.content?.toLowerCase()?.includes('casa') ||

                 window.location.hash.toLowerCase().includes('login') ||

                 window.location.pathname.toLowerCase().includes('login'));

            if (!isCasaOrZima) return;

        }} catch(e) {{ return; }}







        const uVal = {safe_u};



        const pVal = {safe_p};



        if (!uVal || !pVal) return;







        function setNativeValue(el, value) {{



            if (!el) return;



            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;



            if (setter) {{



                setter.call(el, value);



            }} else {{



                el.value = value;



            }}



            el.dispatchEvent(new Event('input', {{ bubbles: true }}));



            el.dispatchEvent(new Event('change', {{ bubbles: true }}));



        }}







        let _autologin_attempts = 0;



        function attemptAutoLogin() {{



            if (_autologin_attempts >= 3) return;



            const pInput = document.querySelector('input[type="password"]');



            if (!pInput) return;







            let uInput = document.querySelector('input[type="text"]') ||



                         document.querySelector('input[name="username"]') ||



                         document.querySelector('input[placeholder*="user" i]') ||



                         document.querySelector('input[placeholder*="akun" i]') ||



                         document.querySelector('input[placeholder*="name" i]');







            if (uInput && pInput) {{



                _autologin_attempts++;



                uInput.focus();



                setNativeValue(uInput, uVal);







                pInput.focus();



                setNativeValue(pInput, pVal);







                setTimeout(function() {{



                    const btn = document.querySelector('button[type="submit"]') ||



                                document.querySelector('.btn-primary') ||



                                document.querySelector('button.is-primary') ||



                                document.querySelector('.el-button--primary') ||



                                document.querySelector('button');



                    if (btn) {{
                        btn.click();
                        try {{ clearInterval(_autoLoginTimer); }} catch(e){{}}
                    }}



                }}, 350);



            }}



        }}







        let _autoLoginTicks = 0;
        const _autoLoginTimer = setInterval(function() {{
            _autoLoginTicks++;
            if (_autologin_attempts >= 3 || _autoLoginTicks > 30) {{
                clearInterval(_autoLoginTimer);
                return;
            }}
            if (document.querySelector('input[type="password"]')) {{
                attemptAutoLogin();
            }}
        }}, 600);
        setTimeout(attemptAutoLogin, 600);



    }})();



    """











def run_app_window(url, title=None, width=1150, height=750, target_server_id=None, target_vm_id=None):



    """



    Menjalankan jendela aplikasi PyWebView secara mandiri (Engine Lama) lengkap dengan:



    1. Isolasi sesi WebView2 per-server dan per-profile (WEBVIEW2_USER_DATA_FOLDER & storage_path).



    2. Auto-login kredensial akun aktif (JWT token injection + form auto-fill).



    Berjalan di proses independen (out-of-process) sehingga tidak mengunci UI Mini Tray.



    """



    clean_u = (url or "").strip()



    if not clean_u:



        return



    if not (clean_u.startswith("http://") or clean_u.startswith("https://")):



        clean_u = "http://" + clean_u







    win_title = title.strip() if title and title.strip() else "MyServer"







    # Baca konfigurasi server & profil akun aktif untuk isolasi WebView2 + Auto-Login



    profile_dir = None



    u_name = ""



    p_pass = ""



    jwt_token = ""



    jwt_refresh = ""



    try:



        cfg = config_manager.load_or_create_config()



        srv = None

        if target_server_id:

            for s in cfg.get("servers", []):

                if isinstance(s, dict) and s.get("id") == target_server_id:

                    srv = s

                    break

        if not srv:

            srv = config_manager.get_active_server(cfg)



        if srv:



            srv_id = srv.get("id", "srv_default")



            act_p = srv.get("active_profile", "Admin")



            creds = config_manager.get_server_credentials(srv, act_p)



            u_name = creds.get("username", "")



            p_pass = creds.get("password", "")







            base_dir = config_manager.get_base_dir()



            profile_dir = os.path.abspath(



                os.path.join(



                    base_dir,



                    "data",



                    "servers",



                    _sanitize_profile_folder_name(srv_id),



                    "profiles",



                    _sanitize_profile_folder_name(act_p),



                )



            )



            if target_vm_id:
                profile_dir = os.path.abspath(
                    os.path.join(
                        base_dir,
                        "data",
                        "vms",
                        _sanitize_profile_folder_name(target_vm_id),
                        "webview_profile",
                    )
                )
            os.makedirs(profile_dir, exist_ok=True)



            os.environ["WEBVIEW2_USER_DATA_FOLDER"] = profile_dir







            is_dashboard = is_zimaos_dashboard_target(clean_u, cfg=cfg)

            if not is_dashboard:

                logger_manager.log_info(f"[AppWindow] URL '{clean_u}' adalah aplikasi web/Docker terpisah. Proteksi kredensial aktif: autologin dinonaktifkan.")

                u_name = ""

                p_pass = ""



            # Ambil token JWT ZimaOS jika URL mengarah ke host server

            if is_dashboard and u_name and p_pass:



                parsed_target = urllib.parse.urlparse(clean_u)



                t_host = parsed_target.hostname or ""



                t_port = str(parsed_target.port) if parsed_target.port else ("443" if parsed_target.scheme.lower() == "https" else "80")



                if t_host:



                    client = zima_metrics_manager.ZimaMetricsClient(



                        host=t_host,



                        port=t_port,



                        use_https=(parsed_target.scheme.lower() == "https"),



                        username=u_name,



                        password=p_pass,



                        server_connections=srv.get("connections", []),



                        server_name=srv.get("name", ""),



                zerotier_ip=get_active_remote_ip(srv),



                    )



                    if client.authenticate():



                        jwt_token = client.token or ""



                        jwt_refresh = getattr(client, "refresh_token", "") or ""



    except Exception as e:



        logger_manager.log_warning(f"[AppWindow] Persiapan profil/autologin notice: {e}")







    try:



        import webview



        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False



        webview.settings["ALLOW_DOWNLOADS"] = True



        sub_win = webview.create_window(



            title=win_title,



            url=clean_u,



            width=width,



            height=height,



            resizable=True



        )







        def on_sub_loaded():

            try:

                if is_dashboard:

                    cur_cfg = config_manager.load_or_create_config()

                    cur_s = config_manager.get_active_server(cur_cfg)

                    cur_p = cur_s.get("active_profile", "Admin") if cur_s else "Admin"

                    saved_creds = config_manager.get_server_credentials(cur_s, cur_p) if cur_s else {}

                    cur_u = saved_creds.get("username", u_name)

                    cur_pw = saved_creds.get("password", p_pass)

                    autologin_js = generate_autologin_js(cur_u, cur_pw, access_token=jwt_token, refresh_token=jwt_refresh)

                    sub_win.evaluate_js(SHORTCUT_JS + "\n" + autologin_js)

                else:

                    sub_win.evaluate_js(SHORTCUT_JS)

            except Exception:

                pass







        sub_win.events.loaded += on_sub_loaded



        if profile_dir:



            webview.start(private_mode=False, storage_path=profile_dir)



        else:



            webview.start(private_mode=False)







    except Exception as e:







        logger_manager.log_error(f"[AppWindow] PyWebView gagal: {e}. Mengalihkan ke fallback.")







        # Fallback 1: Microsoft Edge App Mode







        try:







            edge_paths = [







                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),







                os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),







            ]







            edge_bin = next((p for p in edge_paths if os.path.exists(p)), "msedge.exe")







            subprocess.Popen([edge_bin, f"--app={clean_u}"], creationflags=0x08000000 if sys.platform == "win32" else 0)







        except Exception:







            # Fallback 2: Default System Browser







            if sys.platform == "win32":







                os.startfile(clean_u)







            else:







                webbrowser.open(clean_u)























def probe_url_endpoint(target_url, timeout=1.2):







    """







    Memeriksa keterjangkauan HTTP / TCP host sebelum membuka jendela (Adopsi Zima Client v2.3.5 probeDashboard).







    Mencegah jendela blank putih jika server offline atau port belum siap.







    """







    clean_u = (target_url or "").strip()







    if not clean_u:







        return {"reachable": False, "error": "URL kosong", "url": clean_u, "latency_ms": 0}















    import socket







    parsed = urllib.parse.urlparse(clean_u)







    host = parsed.hostname or "127.0.0.1"







    port = parsed.port or (443 if parsed.scheme == "https" else 80)















    t0 = time.time()







    try:







        s = socket.create_connection((host, port), timeout=timeout)







        s.close()







        latency_ms = int((time.time() - t0) * 1000)







        return {"reachable": True, "latency_ms": latency_ms, "url": clean_u}







    except Exception as e:







        latency_ms = int((time.time() - t0) * 1000)







        return {"reachable": False, "error": str(e), "latency_ms": latency_ms, "url": clean_u}























_deleted_vms_tombstone: dict = {}  # vm_id -> expiry_timestamp (TTL 60s)
_backend_url_cache: dict = {}      # srv_id -> (url, expiry_timestamp) (TTL 25s)
_recent_vm_mutations: dict = {}    # vm_id -> {"expires_at": float, "patch": dict}


def _record_recent_vm_mutation(vm_id, patch, ttl=12.0):
    """Mencatat mutasi VM terbaru (optimistic lock) agar polling 4 detik tidak menimpa state transisi."""
    if not vm_id or not isinstance(patch, dict):
        return
    now = time.time()
    existing = _recent_vm_mutations.get(vm_id)
    merged_patch = {}
    if existing and now < existing.get("expires_at", 0) and isinstance(existing.get("patch"), dict):
        merged_patch.update(existing["patch"])
    for k, v in patch.items():
        if v is not None:
            merged_patch[k] = v
    _recent_vm_mutations[vm_id] = {
        "expires_at": now + ttl,
        "patch": merged_patch,
    }


def _apply_recent_vm_mutation(vm):
    """Menerapkan patch mutasi terbaru ke objek VM hasil polling jika masih dalam masa grace period."""
    if not isinstance(vm, dict):
        return vm
    vid = vm.get("id")
    if not vid:
        return vm
    entry = _recent_vm_mutations.get(vid)
    if not entry:
        return vm
    if time.time() >= entry.get("expires_at", 0):
        _recent_vm_mutations.pop(vid, None)
        return vm
    patch = entry.get("patch") or {}
    for k, v in patch.items():
        if k in ("autoRestart", "autoOn") and isinstance(v, dict) and isinstance(vm.get(k), dict):
            vm[k] = {**vm[k], **v}
        else:
            vm[k] = v
    # Sinkronkan properti boolean camelCase <-> snake_case
    if "keepAliveEnabled" in patch:
        vm["keep_alive_enabled"] = bool(patch["keepAliveEnabled"])
    elif "keep_alive_enabled" in patch:
        vm["keepAliveEnabled"] = bool(patch["keep_alive_enabled"])
    if "autoRestart" in patch and isinstance(patch["autoRestart"], dict) and "enabled" in patch["autoRestart"]:
        vm["auto_restart_enabled"] = bool(patch["autoRestart"]["enabled"])
        vm["autoRestartEnabled"] = bool(patch["autoRestart"]["enabled"])
    if "autoOn" in patch and isinstance(patch["autoOn"], dict) and "enabled" in patch["autoOn"]:
        vm["auto_on_enabled"] = bool(patch["autoOn"]["enabled"])
        vm["autoOnEnabled"] = bool(patch["autoOn"]["enabled"])
    return vm


_wizard_commit_lock = threading.RLock()
_ORIG_ZIMA_METRICS_CLIENT = zima_metrics_manager.ZimaMetricsClient
ZimaMetricsClient = _ORIG_ZIMA_METRICS_CLIENT


def _handle_wizard_verify_zimaos(body):
    """Verify ZimaOS HTTP/S URL and Admin credentials without persisting or logging secrets."""
    if not isinstance(body, dict):
        return 400, {"success": False, "error": "invalid_payload", "message": "Payload tidak valid"}

    raw_url = str(body.get("url") or body.get("localUrl") or body.get("baseUrl") or "").strip()
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")

    if not raw_url or not username or not password:
        return 400, {
            "success": False,
            "error": "missing_fields",
            "message": "URL, username, dan password ZimaOS wajib diisi",
        }

    resolved_url = config_manager.format_server_url(raw_url)
    if not resolved_url:
        return 400, {
            "success": False,
            "error": "invalid_url",
            "message": "Format URL ZimaOS tidak valid",
        }

    client_cls = (
        ZimaMetricsClient
        if ZimaMetricsClient is not _ORIG_ZIMA_METRICS_CLIENT
        else zima_metrics_manager.ZimaMetricsClient
    )
    client = client_cls(
        base_url=resolved_url,
        username=username,
        password=password,
        allow_multi_route_failover=False,
    )

    try:
        authenticated = bool(client.authenticate())
    except Exception as exc:
        safe_err = str(exc).replace(password, "***") if password else str(exc)
        logger_manager.log_warning(f"[WizardVerify] Gagal menghubungi {resolved_url}: {type(exc).__name__}: {safe_err}")
        return 503, {
            "success": False,
            "error": "unreachable",
            "message": f"Gagal terhubung ke ZimaOS: {safe_err}",
        }

    if not authenticated:
        logger_manager.log_warning(f"[WizardVerify] Autentikasi gagal untuk user '{username}' di {resolved_url}")
        return 401, {
            "success": False,
            "error": "auth_failed",
            "message": "Username atau password ZimaOS salah",
        }

    zt_info = {}
    try:
        fetched = client.fetch_zerotier_network_info()
        if isinstance(fetched, dict):
            zt_info = fetched
    except Exception:
        zt_info = {}

    final_url = str(getattr(client, "base_url", None) or resolved_url).strip()
    return 200, {
        "success": True,
        "username": username,
        "resolvedUrl": final_url,
        "isAdmin": bool(getattr(client, "is_admin", False)),
        "zerotierNetworkId": str(zt_info.get("network_id") or "").strip(),
        "zerotierIp": str(zt_info.get("remote_ipv4") or "").strip(),
        "ztStatus": str(zt_info.get("status") or "").strip(),
    }


def _handle_wizard_commit_server(body):
    """Persist verified wizard server details atomically with DPAPI-encrypted credentials."""
    if not isinstance(body, dict):
        return 400, {"success": False, "error": "invalid_payload", "message": "Payload tidak valid"}

    name = str(body.get("name") or body.get("serverName") or "").strip() or "My Server"
    local_url_raw = str(body.get("localUrl") or body.get("local_url") or body.get("url") or "").strip()
    wan_url_raw = str(body.get("wanUrl") or body.get("wan_url") or "").strip()
    zt_nwid = str(
        body.get("zerotierNetworkId") or body.get("zerotier_network_id") or body.get("remoteId") or body.get("remote_id") or ""
    ).strip().lower()
    zt_vip = str(
        body.get("zerotierVirtualIp") or body.get("zerotier_virtual_ip") or body.get("zerotierIp") or ""
    ).strip()
    et_vip = str(
        body.get("easytierVirtualIp") or body.get("easytier_virtual_ip") or body.get("easytierIp") or zt_vip
    ).strip()
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    requested_id = str(body.get("serverId") or body.get("id") or "").strip()
    ssh_user = str(body.get("sshUser") or body.get("ssh_user") or "").strip()

    has_local = bool(local_url_raw and local_url_raw not in ("http://", "https://"))
    has_wan = bool(wan_url_raw and wan_url_raw not in ("http://", "https://"))
    if not has_local and not has_wan:
        return 400, {
            "success": False,
            "error": "missing_url",
            "message": "URL lokal atau WAN ZimaOS wajib diisi",
        }
    if not username:
        return 400, {
            "success": False,
            "error": "missing_username",
            "message": "Username ZimaOS wajib diisi",
        }

    with _wizard_commit_lock, config_manager._config_lock:
        cfg = config_manager.load_or_create_config()
        servers = cfg.setdefault("servers", [])

        target = None
        if requested_id:
            target = next((s for s in servers if isinstance(s, dict) and s.get("id") == requested_id), None)
        if target is None:
            target = next(
                (s for s in servers if isinstance(s, dict) and config_manager.is_placeholder_default_server(s)),
                None,
            )
        if target is None and len(servers) == 1 and isinstance(servers[0], dict) and servers[0].get("id") == "srv_default":
            target = servers[0]

        if target is None:
            new_id = requested_id or f"srv_{int(time.time() * 1000)}"
            target = {
                "id": new_id,
                "name": name,
                "connections": [],
                "credentials": {},
                "profiles": ["Admin"],
                "active_profile": "Admin",
            }
            servers.append(target)

        existing_creds = target.get("credentials") if isinstance(target.get("credentials"), dict) else {}
        existing_admin = existing_creds.get("Admin") if isinstance(existing_creds.get("Admin"), dict) else {}
        if not password and not str(existing_admin.get("password") or "").strip():
            return 400, {
                "success": False,
                "error": "missing_password",
                "message": "Password ZimaOS wajib diisi",
            }

        existing_conns = target.get("connections") if isinstance(target.get("connections"), list) else []
        conns = []
        if has_local:
            lan_id = (
                existing_conns[0].get("id")
                if existing_conns and isinstance(existing_conns[0], dict) and existing_conns[0].get("id")
                else "conn_lan"
            )
            conns.append(
                {
                    "id": lan_id,
                    "name": "LAN",
                    "type": "lan",
                    "url": config_manager.format_server_url(local_url_raw),
                }
            )
        if has_wan:
            conns.append(
                {
                    "id": "conn_wan",
                    "name": "Domain / WAN",
                    "type": "domain",
                    "url": config_manager.format_server_url(wan_url_raw),
                }
            )

        target["name"] = name
        target["connections"] = conns
        if conns:
            target["active_connection_id"] = conns[0]["id"]
        if zt_nwid:
            target["zerotier_network_id"] = zt_nwid
            target["remote_id"] = zt_nwid
        if zt_vip:
            target["zerotier_virtual_ip"] = zt_vip
        if et_vip:
            target["easytier_virtual_ip"] = et_vip
        if ssh_user:
            target["ssh_user"] = ssh_user

        profiles = target.get("profiles") if isinstance(target.get("profiles"), list) else []
        if "Admin" not in profiles:
            profiles.append("Admin")
        target["profiles"] = profiles
        target["active_profile"] = "Admin"
        cfg["active_server_id"] = target["id"]

        config_manager.save_config(cfg)
        if password:
            config_manager.save_server_credentials(cfg, target["id"], "Admin", username, password)
        else:
            existing_creds["Admin"] = {**existing_admin, "username": username}
            target["credentials"] = existing_creds
            config_manager.save_config(cfg)

        logger_manager.log_info(f"[WizardCommit] Server '{name}' (id={target['id']}) tersimpan")
        return 200, {
            "success": True,
            "serverId": target["id"],
            "name": name,
            "zerotierNetworkId": str(target.get("zerotier_network_id") or ""),
            "zerotierVirtualIp": str(target.get("zerotier_virtual_ip") or ""),
        }


def _handle_wizard_complete(_body=None):
    """Gate and mark first-run setup complete only when a valid server configuration exists."""
    with _wizard_commit_lock, config_manager._config_lock:
        cfg = config_manager.load_or_create_config()
        if not config_manager.has_valid_configured_server(cfg):
            return 400, {
                "success": False,
                "error": "wizard_incomplete",
                "message": "Selesaikan koneksi & login dulu",
            }
        cfg["first_run_setup"] = False
        config_manager.save_config(cfg)
        logger_manager.log_info("[WizardComplete] First-run setup selesai")
        return 200, {"success": True, "firstRunSetup": False}


def _prepare_vm_payload_for_backend(vm):
    """Mengharmonisasi payload VM ke format dual camelCase & snake_case untuk backend ZimaOS."""
    if not isinstance(vm, dict):
        return vm
    p = dict(vm)
    # Strip internal DB snapshot so stale snapshot values never override local edits on re-upload
    p.pop("_db_snapshot", None)

    # 1. Always-On / KeepAlive
    if "keepAliveEnabled" in p and p["keepAliveEnabled"] is not None:
        p["keep_alive_enabled"] = bool(p["keepAliveEnabled"])
        p["keepAliveEnabled"] = bool(p["keepAliveEnabled"])
    elif "keep_alive_enabled" in p and p["keep_alive_enabled"] is not None:
        p["keepAliveEnabled"] = bool(p["keep_alive_enabled"])
        p["keep_alive_enabled"] = bool(p["keep_alive_enabled"])

    alias_pairs = (
        ("apiKey", "api_key"),
        ("machineId", "machine_id"),
        ("runtimeMinutes", "runtime_minutes"),
        ("maxRuntimeMinutes", "max_runtime_minutes"),
        ("sshHost", "ssh_host"),
        ("sshPort", "ssh_port"),
        ("sshUser", "ssh_user"),
        ("screenUrl", "screen_url"),
        ("screenOpenTarget", "screen_target"),
        ("webPort", "web_port"),
        ("webUrl", "web_url"),
        ("tokenExpiry", "token_expiry"),
    )
    for camel_k, snake_k in alias_pairs:
        if camel_k in p:
            if p[camel_k] is not None or snake_k not in p:
                p[snake_k] = p[camel_k]

    # 2. Auto-Restart
    ar = p.get("autoRestart")
    if isinstance(ar, dict):
        if "enabled" in ar and ar["enabled"] is not None:
            p["auto_restart_enabled"] = bool(ar.get("enabled"))
            p["autoRestartEnabled"] = bool(ar.get("enabled"))
        if "mode" in ar:
            p["auto_restart_mode"] = str(ar.get("mode"))
        if "intervalValue" in ar:
            p["auto_restart_val"] = int(ar.get("intervalValue") or 7)
        if "intervalUnit" in ar:
            p["auto_restart_unit"] = str(ar.get("intervalUnit") or "hours")
        if "clockTime" in ar:
            p["auto_restart_time"] = str(ar.get("clockTime") or "03:00")
        if "resetCycleMode" in ar:
            p["smart_reset_cycle"] = str(ar.get("resetCycleMode") or "sleep_2s")
    elif "autoRestartEnabled" in p and p["autoRestartEnabled"] is not None:
        p["auto_restart_enabled"] = bool(p["autoRestartEnabled"])

    # 3. Auto-On
    ao = p.get("autoOn")
    DAY_NUM_TO_STR = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}
    if "autoOn" in p and isinstance(p["autoOn"], dict):
        ao = p["autoOn"]
        if "enabled" in ao and ao["enabled"] is not None:
            p["auto_on_enabled"] = bool(ao.get("enabled"))
            p["autoOnEnabled"] = bool(ao.get("enabled"))
        if "mode" in ao:
            p["auto_on_mode"] = str(ao.get("mode"))
        if "clockTime" in ao:
            p["auto_on_time"] = str(ao.get("clockTime") or "07:00")
        if "delayValue" in ao:
            p["auto_on_delay_min"] = int(ao.get("delayValue") or 60)
        if "delayUnit" in ao:
            p["auto_on_delay_unit"] = str(ao.get("delayUnit") or "minutes")
        if "days" in ao and isinstance(ao.get("days"), list):
            conv_days = []
            for d in ao.get("days", []):
                if isinstance(d, int) and d in DAY_NUM_TO_STR:
                    conv_days.append(DAY_NUM_TO_STR[d])
                elif str(d).strip():
                    conv_days.append(str(d).strip())
            p["auto_on_days"] = conv_days if conv_days else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    elif "autoOnEnabled" in p and p["autoOnEnabled"] is not None:
        p["auto_on_enabled"] = bool(p["autoOnEnabled"])

    tz_name = p.get("scheduleTimezone") or p.get("schedule_timezone") or p.get("timezone")
    if tz_name:
        p["schedule_timezone"] = str(tz_name).strip()
        p["scheduleTimezone"] = p["schedule_timezone"]
    raw_tz_offset = p.get("tzOffsetMinutes") if p.get("tzOffsetMinutes") is not None else p.get("tz_offset_minutes")
    if raw_tz_offset is not None:
        try:
            p["tz_offset_minutes"] = int(raw_tz_offset)
            p["tzOffsetMinutes"] = int(raw_tz_offset)
        except Exception:
            pass

    return p


def _normalize_day_indices(raw_days):
    """Mengonversi daftar hari JS index [0..6] maupun singkatan ['Mon', ...] ke index integer [0..6]."""
    str_to_num = {
        "sun": 0, "min": 0, "minggu": 0, "sunday": 0, "0": 0,
        "mon": 1, "sen": 1, "senin": 1, "monday": 1, "1": 1,
        "tue": 2, "sel": 2, "selasa": 2, "tuesday": 2, "2": 2,
        "wed": 3, "rab": 3, "rabu": 3, "wednesday": 3, "3": 3,
        "thu": 4, "kam": 4, "kamis": 4, "thursday": 4, "4": 4,
        "fri": 5, "jum": 5, "jumat": 5, "friday": 5, "5": 5,
        "sat": 6, "sab": 6, "sabtu": 6, "saturday": 6, "6": 6,
    }
    if not isinstance(raw_days, list) or len(raw_days) == 0:
        return [0, 1, 2, 3, 4, 5, 6]
    out = []
    for d in raw_days:
        if isinstance(d, int) and 0 <= d <= 6:
            if d not in out:
                out.append(d)
        else:
            key = str(d).strip().lower()
            if key in str_to_num and str_to_num[key] not in out:
                out.append(str_to_num[key])
    return out or [0, 1, 2, 3, 4, 5, 6]


def _normalize_server_vm_entry(svm, srv):
    """Menormalisasi properti camelCase/snake_case VM dari backend ZimaOS untuk UI & multi-device sync."""
    svm["scope"] = "server"
    svm["serverId"] = srv.get("id")
    svm["serverName"] = srv.get("name")
    if "keep_alive_enabled" in svm and "keepAliveEnabled" not in svm:
        svm["keepAliveEnabled"] = bool(svm["keep_alive_enabled"])
    if "api_key" in svm and "apiKey" not in svm:
        svm["apiKey"] = svm["api_key"]
    if "machine_id" in svm and "machineId" not in svm:
        svm["machineId"] = svm["machine_id"]
    if "runtime_minutes" in svm and "runtimeMinutes" not in svm:
        svm["runtimeMinutes"] = svm["runtime_minutes"]
    if "max_runtime_minutes" in svm and svm["max_runtime_minutes"] is not None and "maxRuntimeMinutes" not in svm:
        svm["maxRuntimeMinutes"] = svm["max_runtime_minutes"]
    elif "runtime_limit_hours" in svm and svm["runtime_limit_hours"] is not None and "maxRuntimeMinutes" not in svm:
        try:
            rlh = int(svm["runtime_limit_hours"])
            svm["maxRuntimeMinutes"] = -1 if rlh < 0 else (480 if rlh == 0 else rlh * 60)
        except Exception:
            pass
    if "schedule_timezone" in svm and "scheduleTimezone" not in svm:
        svm["scheduleTimezone"] = svm["schedule_timezone"]
    if "tz_offset_minutes" in svm and "tzOffsetMinutes" not in svm:
        svm["tzOffsetMinutes"] = svm["tz_offset_minutes"]
    if "auto_restart_enabled" in svm and "autoRestart" not in svm:
        svm["autoRestart"] = {
            "enabled": bool(svm.get("auto_restart_enabled")),
            "mode": svm.get("auto_restart_mode", "interval"),
            "intervalValue": svm.get("auto_restart_val", 7),
            "intervalUnit": svm.get("auto_restart_unit", "hours"),
            "clockTime": svm.get("auto_restart_time", "03:00"),
            "resetCycleMode": svm.get("smart_reset_cycle", "sleep_2s"),
        }
    if "auto_on_enabled" in svm and "autoOn" not in svm:
        svm["autoOn"] = {
            "enabled": bool(svm.get("auto_on_enabled")),
            "mode": svm.get("auto_on_mode", "clock"),
            "clockTime": svm.get("auto_on_time", "07:00"),
            "delayValue": svm.get("auto_on_delay_min", 60),
            "delayUnit": svm.get("auto_on_delay_unit", "minutes"),
            "days": svm.get("auto_on_days", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
        }
    _apply_recent_vm_mutation(svm)
    return svm


def _fetch_server_vms_from_backend(cfg, now_ts=None):
    """Mengambil daftar VM server secara otoritatif dari ZimaOS Backend (mengembalikan (server_vms, server_online))."""
    ts = now_ts if now_ts is not None else time.time()
    srv = config_manager.get_active_server(cfg) if config_manager else None
    backend_url = _get_active_server_backend_url(cfg)
    server_vms = []
    server_online = False
    if srv and backend_url:
        try:
            ok, data, code = _backend_http_request(f"{backend_url}/api/v1/vms", method="GET", timeout=5.0, retries=1)
            if ok and isinstance(data, dict):
                server_online = True
                for svm in (data.get("vms", []) or []):
                    if not isinstance(svm, dict):
                        continue
                    if _deleted_vms_tombstone.get(svm.get("id"), 0) > ts:
                        continue
                    server_vms.append(_normalize_server_vm_entry(svm, srv))
        except Exception as be:
            logger_manager.log_debug(f"[api/vms] Gagal sync server VMs dari backend ZimaOS: {be}")
    return server_vms, server_online


def _execute_vm_update_operation(body):
    """Menjalankan pembaruan VM secara atomik ke backend ZimaOS & config lokal. Return (http_status, response_dict)."""
    vm_id = (body.get("vmId") or body.get("vm_id") or body.get("id") or "").strip()
    if not vm_id:
        return 400, {"status": "error", "success": False, "message": "vmId is required"}

    updates = body.get("vm") or body.get("updates") or {}
    if not isinstance(updates, dict):
        updates = {}
    server_id = (body.get("serverId") or updates.get("serverId") or "").strip()

    cfg = config_manager.load_or_create_config()
    local_vms = cfg.get("vms", []) or []
    target_vm = next((v for v in local_vms if isinstance(v, dict) and v.get("id") == vm_id), None)

    if not server_id and target_vm:
        server_id = target_vm.get("serverId", "")

    req_scope = str(updates.get("scope") or (target_vm.get("scope") if target_vm else "") or "").strip().lower()
    is_server_scope = req_scope == "server" or bool(server_id) or (bool(target_vm) and bool(target_vm.get("serverId")))

    merged_vm = dict(target_vm) if isinstance(target_vm, dict) else {"id": vm_id}
    for k, val in updates.items():
        merged_vm[k] = val

    backend_url = _get_active_server_backend_url(cfg, target_server_id=server_id)
    backend_updated = False
    resp_data = None
    last_err = None

    if is_server_scope:
        if not backend_url:
            _recent_vm_mutations.pop(vm_id, None)
            return 503, {
                "status": "error",
                "success": False,
                "backend_updated": False,
                "vmId": vm_id,
                "message": "Server ZimaOS tidak terhubung atau offline.",
            }
        try:
            b_payload = _prepare_vm_payload_for_backend(updates)
            ok, data, code = _backend_http_request(
                f"{backend_url}/api/v1/vms/{vm_id}",
                method="PUT",
                json_body=b_payload,
                timeout=6.0,
                retries=1,
            )
            if not ok and code == 404 and _deleted_vms_tombstone.get(vm_id, 0) <= time.time() and merged_vm.get("name"):
                upsert_payload = _prepare_vm_payload_for_backend(merged_vm)
                ok, data, code = _backend_http_request(
                    f"{backend_url}/api/v1/vms",
                    method="POST",
                    json_body=upsert_payload,
                    timeout=6.0,
                    retries=1,
                )
            backend_updated = bool(ok)
            resp_data = data
            if not ok:
                last_err = f"Backend ZimaOS HTTP {code}: {data}"
                logger_manager.log_error(f"[/api/vms/update] Gagal update VM {vm_id} di ZimaOS: {last_err}")
            else:
                logger_manager.log_info(f"[/api/vms/update] VM {vm_id} berhasil diupdate di ZimaOS (code {code})")
        except Exception as ue:
            last_err = str(ue)
            logger_manager.log_error(f"[/api/vms/update] Gagal update VM {vm_id} di server ZimaOS: {ue}")

        if not backend_updated:
            _recent_vm_mutations.pop(vm_id, None)
            return 502, {
                "status": "error",
                "success": False,
                "backend_updated": False,
                "vmId": vm_id,
                "message": f"Gagal menyinkronkan ke server ZimaOS: {last_err or 'Unknown error'}",
            }

    prev_keep_alive = bool(target_vm.get("keepAliveEnabled")) if isinstance(target_vm, dict) else False

    if target_vm and updates:
        for k, val in updates.items():
            target_vm[k] = val
        config_manager.save_config(cfg)

    if updates:
        _record_recent_vm_mutation(vm_id, updates, ttl=12.0)

    if not is_server_scope and ("keepAliveEnabled" in updates or "keep_alive_enabled" in updates):
        ka_now = bool(merged_vm.get("keepAliveEnabled") if "keepAliveEnabled" in merged_vm else merged_vm.get("keep_alive_enabled"))
        if ka_now != prev_keep_alive and merged_vm.get("provider", "instabox") == "instabox":
            ka_key = str(merged_vm.get("apiKey") or "").strip()
            ka_mid = str(merged_vm.get("machineId") or "").strip()
            ka_status = str(merged_vm.get("status") or "").lower()
            if ka_key and ka_mid:
                if ka_now and ka_status == "running":
                    threading.Thread(
                        target=_instabox_maintain_keepalive,
                        args=(ka_key, ka_mid, vm_id, True),
                        daemon=True,
                    ).start()
                elif not ka_now:
                    threading.Thread(
                        target=_instabox_release_lease,
                        args=(ka_key, ka_mid, vm_id),
                        daemon=True,
                    ).start()

    return 200, {
        "status": "ok",
        "success": True,
        "backend_updated": backend_updated,
        "vmId": vm_id,
        "data": resp_data,
    }


def _execute_vm_migrate_operation(body):
    """Menjalankan migrasi VM antara Server ZimaOS dan Lokal secara atomik. Return (http_status, response_dict)."""
    if not isinstance(body, dict):
        body = {}
    vm_id = str(body.get("vmId") or body.get("vm_id") or body.get("id") or "").strip()
    target_scope = str(body.get("targetScope") or body.get("target_scope") or "").strip().lower()
    vm_data = body.get("vm") if isinstance(body.get("vm"), dict) else None
    if not vm_id or target_scope not in ("server", "local"):
        return 400, {
            "status": "error",
            "success": False,
            "message": "vmId dan targetScope ('server'|'local') wajib diisi",
        }

    cfg = config_manager.load_or_create_config()
    local_vms = cfg.get("vms", []) or []
    srv = config_manager.get_active_server(cfg)
    existing_local = next((v for v in local_vms if isinstance(v, dict) and v.get("id") == vm_id), None)

    if target_scope == "server":
        backend_url = _get_active_server_backend_url(cfg)
        if not backend_url or not srv:
            return 400, {
                "status": "error",
                "success": False,
                "message": "Server ZimaOS tidak terhubung atau offline",
            }
        merged_source = {**(existing_local or {}), **(vm_data or {})} if (existing_local or vm_data) else None
        if not merged_source:
            return 404, {
                "status": "error",
                "success": False,
                "message": f"VM '{vm_id}' tidak ditemukan",
            }

        target_vm = dict(merged_source)
        target_vm.pop("_db_snapshot", None)
        target_vm["id"] = vm_id
        target_vm["scope"] = "server"
        target_vm["serverId"] = srv.get("id")
        target_vm["serverName"] = srv.get("name")

        b_payload = _prepare_vm_payload_for_backend(target_vm)
        b_payload["force_recreate"] = True
        b_payload["_force_recreate"] = True

        try:
            ok, data, _code = _backend_http_request(
                f"{backend_url}/api/v1/vms",
                method="POST",
                json_body=b_payload,
                timeout=5.0,
                retries=1,
            )
            if not ok:
                return 500, {
                    "status": "error",
                    "success": False,
                    "message": f"Gagal migrasi ke ZimaOS: {data}",
                }
        except Exception as be:
            return 500, {
                "status": "error",
                "success": False,
                "message": f"Gagal migrasi ke ZimaOS: {be}",
            }

        # Clear any local delete tombstone and prior local-migration mutation ONLY after server create succeeds
        _deleted_vms_tombstone.pop(vm_id, None)
        _recent_vm_mutations.pop(vm_id, None)
        _record_recent_vm_mutation(
            vm_id,
            {"scope": "server", "serverId": srv.get("id"), "serverName": srv.get("name")},
            ttl=15.0,
        )
        if isinstance(data, dict) and data.get("id") == vm_id:
            normalized = _normalize_server_vm_entry(dict(data), srv)
            for field in ("status", "runtimeMinutes", "maxRuntimeMinutes", "telemetry"):
                if normalized.get(field) is not None:
                    target_vm[field] = normalized[field]
            target_vm["scope"] = "server"
            target_vm["serverId"] = srv.get("id")
            target_vm["serverName"] = srv.get("name")

        updated_list = []
        replaced = False
        for v in local_vms:
            if isinstance(v, dict) and v.get("id") == vm_id:
                updated_list.append(target_vm)
                replaced = True
            else:
                updated_list.append(v)
        if not replaced:
            updated_list.append(target_vm)
        cfg["vms"] = updated_list
        config_manager.save_config(cfg)
        return 200, {"status": "ok", "success": True, "vm": target_vm}

    # target_scope == "local"
    merged_source = {**(existing_local or {}), **(vm_data or {})} if (existing_local or vm_data) else None
    if not merged_source:
        return 404, {
            "status": "error",
            "success": False,
            "message": f"VM '{vm_id}' tidak ditemukan",
        }

    target_vm = dict(merged_source)
    target_vm.pop("_db_snapshot", None)
    target_vm["id"] = vm_id
    target_vm["scope"] = "local"
    target_vm.pop("serverId", None)
    target_vm.pop("serverName", None)

    _deleted_vms_tombstone.pop(vm_id, None)
    _recent_vm_mutations.pop(vm_id, None)
    _record_recent_vm_mutation(
        vm_id,
        {"scope": "local", "serverId": None, "serverName": None},
        ttl=15.0,
    )

    # Persist local scope BEFORE remote DELETE so concurrent 4s /api/vms/load polls never drop the VM
    updated_list = []
    replaced = False
    for v in local_vms:
        if isinstance(v, dict) and v.get("id") == vm_id:
            updated_list.append(target_vm)
            replaced = True
        else:
            updated_list.append(v)
    if not replaced:
        updated_list.append(target_vm)
    cfg["vms"] = updated_list
    config_manager.save_config(cfg)

    target_srv_id = (existing_local or {}).get("serverId") or (vm_data or {}).get("serverId")
    del_backend_url = _get_active_server_backend_url(cfg, target_server_id=target_srv_id) or _get_active_server_backend_url(cfg)
    if not del_backend_url:
        cfg["vms"] = local_vms
        config_manager.save_config(cfg)
        _recent_vm_mutations.pop(vm_id, None)
        return 503, {
            "status": "error",
            "success": False,
            "message": "Server ZimaOS tidak terhubung atau offline",
        }

    ok, data, code = False, "Unknown error", 0
    try:
        ok, data, code = _backend_http_request(
            f"{del_backend_url}/api/v1/vms/{vm_id}",
            method="DELETE",
            timeout=5.0,
            retries=1,
        )
    except Exception as be:
        data = str(be)
        ok = False

    if not ok and code != 404:
        cfg["vms"] = local_vms
        config_manager.save_config(cfg)
        _recent_vm_mutations.pop(vm_id, None)
        return 502, {
            "status": "error",
            "success": False,
            "message": f"Gagal menghapus VM dari ZimaOS saat migrasi ke lokal (HTTP {code}): {data}",
        }

    return 200, {"status": "ok", "success": True, "vm": target_vm}


def _parse_backend_semver(v_str):
    import re
    cleaned = (v_str or "").strip()
    if not cleaned:
        return ()
    m = re.search(r"(\d+(?:\.\d+)+)", cleaned)
    if m:
        return tuple(int(x) for x in m.group(1).split("."))
    parts = re.findall(r"\d+", cleaned)
    return tuple(int(x) for x in parts) if parts else ()


def _compare_backend_versions(ver_a, ver_b):
    pa = _parse_backend_semver(ver_a)
    pb = _parse_backend_semver(ver_b)
    if not pa and not pb:
        return 0
    max_len = max(len(pa), len(pb))
    pa_pad = pa + (0,) * (max_len - len(pa))
    pb_pad = pb + (0,) * (max_len - len(pb))
    if pa_pad > pb_pad:
        return 1
    if pa_pad < pb_pad:
        return -1
    return 0


def _extract_host_from_url(raw_url):
    u = (raw_url or "").strip()
    if not u:
        return ""
    if "://" not in u:
        u = f"http://{u}"
    try:
        parsed = urllib.parse.urlparse(u)
        return (parsed.hostname or "").strip()
    except Exception:
        return ""


def _format_backend_url(host, port=8080):
    h = (host or "").strip()
    if not h:
        return ""
    if ":" in h and not h.startswith("["):
        return f"http://[{h}]:{port}"
    return f"http://{h}:{port}"


def _is_wan_host_safe(host):
    h = (host or "").strip().lower()
    if not h:
        return False
    try:
        from smb_mount_manager import _is_domain_or_wan_host
        return bool(_is_domain_or_wan_host(h))
    except Exception:
        if h in ("localhost", "zimaos.local") or h.endswith(".local") or h.endswith(".lan"):
            return False
        try:
            ipaddress.ip_address(h)
            return False
        except ValueError:
            return True


def _select_target_server(cfg, target_server_id=None):
    if not isinstance(cfg, dict):
        return None
    servers = cfg.get("servers", []) or []
    if target_server_id:
        for s in servers:
            if s.get("id") == target_server_id or s.get("name") == target_server_id:
                return s
    if config_manager and hasattr(config_manager, "get_active_server"):
        return config_manager.get_active_server(cfg)
    return servers[0] if servers else None


def _get_backend_url_candidates(cfg, target_server_id=None, srv=None):
    """Membangun daftar URL kandidat API backend ZimaOS (port 8080) terurut prioritas failover."""
    try:
        if srv is None:
            srv = _select_target_server(cfg, target_server_id=target_server_id)
        if not srv:
            return []

        primary_host = ""
        if config_manager and hasattr(config_manager, "resolve_target_connection"):
            try:
                primary_url, _ = config_manager.resolve_target_connection(cfg, target_server=srv)
                primary_host = _extract_host_from_url(primary_url)
            except Exception as e:
                logger_manager.log_debug(f"[_get_backend_url_candidates] resolve_target_connection error: {e}")

        remote_hosts = []
        if config_manager and hasattr(config_manager, "get_dynamic_remote_info"):
            try:
                rem_info = config_manager.get_dynamic_remote_info(srv, cfg)
                rem_ip = (rem_info.get("ip") or "").strip() if isinstance(rem_info, dict) else ""
                if rem_ip:
                    remote_hosts.append(rem_ip)
            except Exception:
                pass
        for key in ("easytier_virtual_ip", "zerotier_virtual_ip", "remote_ip"):
            val = (srv.get(key) or "").strip()
            if val and val not in remote_hosts:
                remote_hosts.append(val)

        local_conn_hosts = []
        wan_conn_hosts = []
        for c in (srv.get("connections", []) or []):
            ch = _extract_host_from_url(c.get("url", ""))
            if not ch:
                continue
            if _is_wan_host_safe(ch):
                if ch not in wan_conn_hosts:
                    wan_conn_hosts.append(ch)
            else:
                if ch not in local_conn_hosts:
                    local_conn_hosts.append(ch)

        ordered_hosts = []
        if primary_host and _is_wan_host_safe(primary_host):
            # Port 8080 usually stays unexposed on WAN routers, so prefer P2P/LAN first.
            ordered_hosts.extend(remote_hosts)
            ordered_hosts.extend(local_conn_hosts)
            ordered_hosts.append(primary_host)
            ordered_hosts.extend(wan_conn_hosts)
        else:
            if primary_host:
                ordered_hosts.append(primary_host)
            ordered_hosts.extend(local_conn_hosts)
            ordered_hosts.extend(remote_hosts)
            ordered_hosts.extend(wan_conn_hosts)

        urls = []
        seen = set()
        for h in ordered_hosts:
            bu = _format_backend_url(h, 8080)
            if bu and bu not in seen:
                seen.add(bu)
                urls.append(bu)
        return urls
    except Exception as e:
        logger_manager.log_debug(f"[_get_backend_url_candidates] Error: {e}")
        return []


def _get_active_server_backend_url(cfg, target_server_id=None):
    """Menentukan URL REST API MyServer Backend di ZimaOS (port 8080) secara dinamis dengan failover WAN dan TTL Cache."""
    now = time.time()
    try:
        srv = _select_target_server(cfg, target_server_id=target_server_id)
        if not srv:
            return None

        srv_id = srv.get("id") or "default"
        cached = _backend_url_cache.get(srv_id)
        if cached and now < cached[1]:
            return cached[0]

        candidates = _get_backend_url_candidates(cfg, target_server_id=target_server_id, srv=srv)
        if not candidates:
            return None

        resolved_url = candidates[0]
        _backend_url_cache[srv_id] = (resolved_url, now + 25.0)
        return resolved_url
    except Exception as e:
        logger_manager.log_debug(f"[_get_active_server_backend_url] Error: {e}")
        return None


def _backend_http_request(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
    """
    Eksekutor HTTP tangguh ke backend ZimaOS (port 8080).
    Menggunakan header 'Connection: close' dan auto-retry saat terjadi [WinError 10054] / socket reset.
    Return (ok: bool, data_or_error: any, http_status: int).
    """
    req_headers = {
        "User-Agent": f"MyServer-Core/{APP_VERSION_NUMBER}",
        "Connection": "close",
        "Accept": "application/json",
    }
    if json_body is not None:
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)

    data = json.dumps(json_body).encode("utf-8") if json_body is not None else None

    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                parsed = json.loads(raw.decode("utf-8")) if raw else {}
                return True, parsed, resp.status
        except urllib.error.HTTPError as he:
            try:
                err_txt = he.read().decode("utf-8")
                err_data = json.loads(err_txt)
            except Exception:
                err_data = str(he)
            return False, err_data, he.code
        except Exception as ex:
            last_err = ex
            if attempt < retries:
                time.sleep(0.15)
                continue
    return False, f"Gagal menghubungi backend ZimaOS: {last_err}", 502


_cached_bundled_backend_version = {"timestamp": 0, "version": "", "source": ""}
_remote_backend_manifest_cache = {
    "timestamp": 0.0,
    "last_attempt": 0.0,
    "version": "",
    "package_zip": "",
    "package_tar": "",
}


def _get_resource_dir_candidates():
    candidates = []
    seen = set()

    def _add_dir(path_str):
        if not path_str:
            return
        norm = os.path.abspath(path_str)
        if norm not in seen and os.path.isdir(norm):
            seen.add(norm)
            candidates.append(norm)

    base_d = config_manager.get_base_dir() if (config_manager and hasattr(config_manager, "get_base_dir")) else os.path.dirname(os.path.abspath(__file__))
    if base_d:
        _add_dir(os.path.join(base_d, "resources"))
        _add_dir(os.path.join(os.path.dirname(os.path.abspath(base_d)), "resources"))

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        _add_dir(os.path.join(exe_dir, "resources"))
        _add_dir(os.path.join(os.path.dirname(exe_dir), "resources"))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            _add_dir(os.path.join(meipass, "resources"))

    return candidates


def _read_backend_manifest_info(res_dir):
    manifest_file = os.path.join(res_dir, "backend_manifest.json")
    if not os.path.isfile(manifest_file):
        return None
    try:
        with open(manifest_file, "r", encoding="utf-8") as f:
            mdata = json.load(f)
        if isinstance(mdata, dict):
            return mdata
    except Exception as e:
        logger_manager.log_debug(f"[_read_backend_manifest_info] Gagal membaca manifest {manifest_file}: {e}")
    return None


def _sort_backend_archives(res_dir, ext_tuple, preferred_names=()):
    try:
        names = [
            fn for fn in os.listdir(res_dir)
            if fn.startswith("MyServer-Backend") and fn.endswith(ext_tuple) and os.path.isfile(os.path.join(res_dir, fn))
        ]
    except Exception:
        return []
    preferred = []
    for p in preferred_names:
        if p and p in names and p not in preferred:
            preferred.append(p)
    others = [fn for fn in names if fn not in preferred]
    others.sort(key=lambda fn: (_parse_backend_semver(fn), fn), reverse=True)
    return [os.path.join(res_dir, fn) for fn in (preferred + others)]


def _extract_version_from_config_text(content):
    import re
    m = re.search(r'SERVER_VERSION\s*=\s*[\"\']([^\"\']+)[\"\']', content or "")
    return m.group(1).strip() if m else ""


def _extract_archive_backend_version(archive_path):
    """Membaca SERVER_VERSION dari config.py di dalam arsip .zip atau .tar.gz secara aman."""
    if not archive_path or not os.path.isfile(archive_path):
        return ""
    low = archive_path.lower()
    if low.endswith(".zip"):
        import zipfile
        try:
            with zipfile.ZipFile(archive_path, "r") as z:
                for name in z.namelist():
                    if name == "config.py" or name.endswith("/config.py") or name.endswith("\\config.py"):
                        content = z.read(name).decode("utf-8", errors="ignore")
                        v = _extract_version_from_config_text(content).lstrip("v")
                        if v:
                            return v
        except Exception as e:
            logger_manager.log_debug(f"[_extract_archive_backend_version] Gagal inspeksi ZIP {archive_path}: {e}")
    elif low.endswith((".tar.gz", ".tgz")):
        import tarfile
        try:
            with tarfile.open(archive_path, "r:gz") as t:
                for member in t.getmembers():
                    if member.isfile() and (member.name == "config.py" or member.name.endswith("/config.py")):
                        f = t.extractfile(member)
                        if f:
                            content = f.read().decode("utf-8", errors="ignore")
                            v = _extract_version_from_config_text(content).lstrip("v")
                            if v:
                                return v
        except Exception as e:
            logger_manager.log_debug(f"[_extract_archive_backend_version] Gagal inspeksi TAR {archive_path}: {e}")
    return ""


def _is_local_archive_stale_for_target(archive_path, target_ver):
    """True hanya jika arsip lokal memiliki versi valid yang lebih lama dari target_ver."""
    if not target_ver or not archive_path or not os.path.isfile(archive_path):
        return False
    pkg_ver = _extract_archive_backend_version(archive_path)
    if not pkg_ver:
        return False
    return _compare_backend_versions(target_ver, pkg_ver) > 0


_GITHUB_REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _resolve_github_repo_slug(cfg=None, body=None):
    """Resolve and strictly validate GitHub owner/repo slug (prevents URL path traversal)."""
    default_slug = (
        getattr(config_manager, "DEFAULT_GITHUB_REPO", "Gibranibang/My-Server-beta")
        if config_manager
        else "Gibranibang/My-Server-beta"
    )
    raw = ""
    if isinstance(body, dict):
        raw = str(body.get("githubRepo") or body.get("github_repo") or "").strip()
    if not raw and isinstance(cfg, dict):
        raw = str(cfg.get("github_repo") or "").strip()
    slug = (raw or default_slug).strip().strip("/")
    if ".." in slug or not _GITHUB_REPO_SLUG_RE.fullmatch(slug):
        return None, slug
    owner, repo = slug.split("/", 1)
    if owner in (".", "..") or repo in (".", ".."):
        return None, slug
    return slug, slug


def _fetch_remote_backend_manifest_info(cfg=None, timeout=2.5, force=False):
    """Mengambil metadata versi backend terbaru dari GitHub Release (tanpa bergantung versi app Desktop)."""
    global _remote_backend_manifest_cache
    now = time.time()
    cached_ts = float(_remote_backend_manifest_cache.get("timestamp") or 0.0)
    cached_ver = str(_remote_backend_manifest_cache.get("version") or "").strip().lstrip("v")
    positive_ttl = 10 if force else 300
    negative_cooldown = 10 if force else 60

    if cached_ver and cached_ts > 0 and (now - cached_ts < positive_ttl):
        return (
            cached_ver,
            str(_remote_backend_manifest_cache.get("package_zip") or "").strip(),
            str(_remote_backend_manifest_cache.get("package_tar") or "").strip(),
        )
    # Skip repeated network fetches when offline or right after check so polling stays responsive.
    last_attempt = float(_remote_backend_manifest_cache.get("last_attempt") or 0.0)
    if last_attempt > 0 and (now - last_attempt < negative_cooldown):
        if cached_ver and cached_ts > 0:
            return (
                cached_ver,
                str(_remote_backend_manifest_cache.get("package_zip") or "").strip(),
                str(_remote_backend_manifest_cache.get("package_tar") or "").strip(),
            )
        return "", "", ""

    _remote_backend_manifest_cache["last_attempt"] = now
    try:
        if cfg is None and config_manager and hasattr(config_manager, "load_or_create_config"):
            cfg = config_manager.load_or_create_config()
    except Exception:
        cfg = cfg or {}
    repo_slug, raw_slug = _resolve_github_repo_slug(cfg)
    if not repo_slug:
        logger_manager.log_debug(f"[_fetch_remote_backend_manifest_version] Invalid github_repo slug: {raw_slug}")
        return "", "", ""
    manifest_url = f"https://github.com/{repo_slug}/releases/latest/download/backend_manifest.json"
    try:
        req = urllib.request.Request(
            manifest_url,
            headers={
                "User-Agent": f"MyServer-Core/{APP_VERSION_NUMBER}",
                "Accept": "application/json",
                "Cache-Control": "no-cache",
                "Connection": "close",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            mdata = json.loads(raw) if raw else {}
            if isinstance(mdata, dict):
                v = (mdata.get("backend_version") or mdata.get("version") or "").strip().lstrip("v")
                p_zip = os.path.basename(str(mdata.get("package_zip") or "").strip())
                p_tar = os.path.basename(str(mdata.get("package_tar") or "").strip())
                if v:
                    _remote_backend_manifest_cache["timestamp"] = now
                    _remote_backend_manifest_cache["version"] = v
                    _remote_backend_manifest_cache["package_zip"] = p_zip
                    _remote_backend_manifest_cache["package_tar"] = p_tar
                    return v, p_zip, p_tar
    except Exception as e:
        logger_manager.log_debug(f"[_fetch_remote_backend_manifest_version] Remote manifest unavailable: {e}")
    if cached_ver and cached_ts > 0:
        return (
            cached_ver,
            str(_remote_backend_manifest_cache.get("package_zip") or "").strip(),
            str(_remote_backend_manifest_cache.get("package_tar") or "").strip(),
        )
    return "", "", ""


def _fetch_remote_backend_manifest_version(cfg=None, timeout=2.5, force=False):
    v, _, _ = _fetch_remote_backend_manifest_info(cfg=cfg, timeout=timeout, force=force)
    return v


def _get_local_bundled_backend_version():
    """Membaca versi backend ZimaOS dari folder resources lokal tanpa panggilan jaringan."""
    for res_dir in _get_resource_dir_candidates():
        mdata = _read_backend_manifest_info(res_dir)
        pref_zips = ["MyServer-Backend-ZimaOS.zip"]
        pref_tars = ["MyServer-Backend-ZimaOS.tar.gz"]
        if mdata:
            v = (mdata.get("backend_version") or mdata.get("version") or "").strip().lstrip("v")
            if v:
                return v
            p_zip = os.path.basename((mdata.get("package_zip") or "").strip())
            p_tar = os.path.basename((mdata.get("package_tar") or "").strip())
            if p_zip:
                pref_zips.insert(0, p_zip)
            if p_tar:
                pref_tars.insert(0, p_tar)

        for zpath in _sort_backend_archives(res_dir, (".zip",), preferred_names=pref_zips):
            v = _extract_archive_backend_version(zpath)
            if v:
                return v

        for tpath in _sort_backend_archives(res_dir, (".tar.gz", ".tgz"), preferred_names=pref_tars):
            v = _extract_archive_backend_version(tpath)
            if v:
                return v

    return ""


def _get_bundled_backend_version(cfg=None, allow_remote=True, force_remote=False):
    """
    Menemukan versi target backend ZimaOS dengan menggabungkan bundel lokal
    dan rilis GitHub terbaru (mengembalikan semver tertinggi agar update
    Backend tetap terdeteksi tanpa perlu update MyServer Desktop).
    """
    global _cached_bundled_backend_version
    now = time.time()
    cached_ver = _cached_bundled_backend_version.get("version", "")
    cached_src = _cached_bundled_backend_version.get("source", "")
    cache_ttl = 300 if cached_src == "remote" else 30
    if (
        not force_remote
        and cached_ver
        and (now - _cached_bundled_backend_version["timestamp"] < cache_ttl)
    ):
        if not allow_remote:
            if cached_src == "local":
                return cached_ver
        elif cached_src == "remote" or (_fetch_remote_backend_manifest_version(cfg=cfg) == "" and cached_src == "local"):
            return cached_ver

    local_ver = _get_local_bundled_backend_version()

    if allow_remote:
        remote_ver = _fetch_remote_backend_manifest_version(cfg=cfg, force=force_remote)
        if remote_ver and (not local_ver or _compare_backend_versions(remote_ver, local_ver) > 0):
            _cached_bundled_backend_version = {"timestamp": now, "version": remote_ver, "source": "remote"}
            return remote_ver

    if local_ver:
        _cached_bundled_backend_version = {"timestamp": now, "version": local_ver, "source": "local"}
        return local_ver

    if cached_ver and (allow_remote or cached_src != "remote"):
        return cached_ver
    return ""


def _download_stream_bounded(url, dest_path, headers=None, socket_timeout=25.0, total_timeout=35.0, max_bytes=None):
    """Download URL to dest_path enforcing both per-read socket timeout and total wall-clock deadline."""
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    deadline = time.monotonic() + max(float(total_timeout), float(socket_timeout), 1.0)
    downloaded = 0
    try:
        with urllib.request.urlopen(req, timeout=socket_timeout) as resp, open(dest_path, "wb") as out_f:
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"Unduhan melebihi batas waktu total ({int(total_timeout)}s)")
                chunk = resp.read(65536)
                if not chunk:
                    break
                downloaded += len(chunk)
                if max_bytes is not None and downloaded > max_bytes:
                    raise ValueError(f"Ukuran arsip GitHub melebihi batas {max_bytes} bytes")
                out_f.write(chunk)
        return downloaded
    except Exception:
        if dest_path and os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        raise


def _exec_ssh_command_bounded(ssh_client, cmd, timeout=30.0):
    """
    Execute an SSH command with active stdout/stderr draining and a hard wall-clock deadline.
    Avoids Paramiko's unbounded recv_exit_status() wait and channel window-full deadlocks.
    """
    _, stdout, stderr = ssh_client.exec_command(cmd, timeout=timeout)
    chan = getattr(stdout, "channel", None)
    if chan is None:
        out_raw = stdout.read() if hasattr(stdout, "read") else b""
        err_raw = stderr.read() if hasattr(stderr, "read") else b""
        return 0, out_raw, err_raw

    set_to = getattr(chan, "settimeout", None)
    if callable(set_to):
        try:
            set_to(timeout)
        except Exception:
            pass

    ready_fn = getattr(chan, "exit_status_ready", None)
    if not callable(ready_fn):
        exit_code = chan.recv_exit_status()
        out_raw = stdout.read() if hasattr(stdout, "read") else b""
        err_raw = stderr.read() if hasattr(stderr, "read") else b""
        return exit_code, out_raw, err_raw

    deadline = time.monotonic() + max(float(timeout), 1.0)
    out_chunks = []
    err_chunks = []

    def _drain():
        while callable(getattr(chan, "recv_ready", None)) and chan.recv_ready():
            chunk = chan.recv(65536)
            if not chunk:
                break
            out_chunks.append(chunk)
        while callable(getattr(chan, "recv_stderr_ready", None)) and chan.recv_stderr_ready():
            chunk = chan.recv_stderr(65536)
            if not chunk:
                break
            err_chunks.append(chunk)

    while not ready_fn():
        _drain()
        if time.monotonic() > deadline:
            close_fn = getattr(chan, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            raise TimeoutError(f"Perintah SSH melebihi batas waktu ({int(timeout)}s)")
        time.sleep(0.1)

    _drain()
    exit_code = chan.recv_exit_status()
    _drain()
    return exit_code, b"".join(out_chunks), b"".join(err_chunks)


def _download_remote_backend_archive(repo_slug, asset_name, suffix, expected_ver="", timeout=25.0):
    """Mengunduh paket rilis Backend terbaru (.zip/.tar.gz) dari GitHub Releases ke file sementara."""
    if not repo_slug:
        return None
    import tempfile

    default_name = "MyServer-Backend-ZimaOS.zip" if suffix == ".zip" else "MyServer-Backend-ZimaOS.tar.gz"
    safe_asset = os.path.basename(str(asset_name or "").strip()) or default_name
    dl_url = f"https://github.com/{repo_slug}/releases/latest/download/{safe_asset}"
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="myserver_backend_dl_", suffix=suffix)
        os.close(fd)
        downloaded = _download_stream_bounded(
            dl_url,
            tmp_path,
            headers={
                "User-Agent": f"MyServer-Core/{APP_VERSION_NUMBER}",
                "Cache-Control": "no-cache",
                "Connection": "close",
            },
            socket_timeout=timeout,
            total_timeout=max(float(timeout) + 15.0, 40.0),
            max_bytes=64 * 1024 * 1024,
        )
        if downloaded < 512:
            raise ValueError(f"Ukuran arsip GitHub terlalu kecil ({downloaded} bytes)")
        pkg_ver = _extract_archive_backend_version(tmp_path)
        if expected_ver and pkg_ver and _compare_backend_versions(pkg_ver, expected_ver) < 0:
            raise ValueError(f"Versi arsip GitHub ({pkg_ver}) lebih rendah dari manifest ({expected_ver})")
        return tmp_path
    except Exception as e:
        logger_manager.log_warning(f"[_download_remote_backend_archive] Gagal unduh {safe_asset} dari GitHub: {e}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return None


def _get_bundled_backend_packages():
    """
    Menemukan path berkas paket ZIP dan TAR.GZ di kandidat folder resources secara dinamis dan portabel.
    """
    zip_pkg = None
    tar_pkg = None

    for res_dir in _get_resource_dir_candidates():
        mdata = _read_backend_manifest_info(res_dir)
        pref_zips = ["MyServer-Backend-ZimaOS.zip"]
        pref_tars = ["MyServer-Backend-ZimaOS.tar.gz"]
        if mdata:
            p_zip = os.path.basename((mdata.get("package_zip") or "").strip())
            p_tar = os.path.basename((mdata.get("package_tar") or "").strip())
            if p_zip:
                pref_zips.insert(0, p_zip)
            if p_tar:
                pref_tars.insert(0, p_tar)

        if not zip_pkg:
            zips = _sort_backend_archives(res_dir, (".zip",), preferred_names=pref_zips)
            if zips:
                zip_pkg = zips[0]
        if not tar_pkg:
            tars = _sort_backend_archives(res_dir, (".tar.gz", ".tgz"), preferred_names=pref_tars)
            if tars:
                tar_pkg = tars[0]
        if zip_pkg and tar_pkg:
            break

    return zip_pkg, tar_pkg


_cached_backend_info = {
    "timestamp": 0,
    "server_id": "",
    "data": {"online": False, "version": "", "latestVersion": "", "url": ""}
}


def _get_backend_health_info(cfg=None, force=False, target_server_id=None):
    """Mengecek status kesehatan dan versi backend ZimaOS (port 8080) dengan multi-candidate failover."""
    now = time.time()
    if cfg is None:
        cfg = config_manager.load_or_create_config() if config_manager else {}

    srv = _select_target_server(cfg, target_server_id=target_server_id)
    srv_id = (srv.get("id") or "default") if isinstance(srv, dict) else ""

    if (
        not force
        and _cached_backend_info.get("server_id") == srv_id
        and _cached_backend_info.get("data", {}).get("online")
        and (now - _cached_backend_info["timestamp"] < 5)
    ):
        return dict(_cached_backend_info["data"])

    target_ver = _get_bundled_backend_version(cfg=cfg, force_remote=force)
    candidates = _get_backend_url_candidates(cfg, target_server_id=target_server_id, srv=srv)
    probe_list = []
    cached_entry = _backend_url_cache.get(srv_id) if srv_id else None
    if cached_entry and now < cached_entry[1] and cached_entry[0]:
        probe_list.append(cached_entry[0])
    for c_url in candidates:
        if c_url not in probe_list:
            probe_list.append(c_url)

    info = {
        "online": False,
        "version": "",
        "latestVersion": target_ver,
        "url": probe_list[0] if probe_list else ""
    }

    for idx, cand_url in enumerate(probe_list):
        req_timeout = 2.0 if idx == 0 else 1.2
        req_retries = 1 if idx == 0 else 0
        ok, data, _ = _backend_http_request(
            f"{cand_url}/health",
            method="GET",
            timeout=req_timeout,
            retries=req_retries,
        )
        if ok and isinstance(data, dict) and data.get("status") == "ok":
            info["online"] = True
            info["version"] = (data.get("version") or "").strip()
            info["url"] = cand_url
            if srv_id:
                _backend_url_cache[srv_id] = (cand_url, now + 25.0)
            break

    if info["online"]:
        _cached_backend_info["timestamp"] = now
        _cached_backend_info["server_id"] = srv_id
        _cached_backend_info["data"] = dict(info)
    else:
        if srv_id and srv_id in _backend_url_cache:
            _backend_url_cache.pop(srv_id, None)
        _cached_backend_info["timestamp"] = 0
        _cached_backend_info["server_id"] = srv_id
        _cached_backend_info["data"] = dict(info)

    return dict(info)


def _resolve_ssh_admin_credentials(srv):
    """Mengambil kredensial admin (prioritas profil Admin) untuk sesi SSH & verifikasi OTA."""
    creds = config_manager.get_server_credentials(srv, "Admin") if config_manager else {}
    user = (creds.get("username") or "").strip()
    pwd = (creds.get("password") or "").strip()
    if not user or not pwd:
        active_p = srv.get("active_profile", "")
        creds = config_manager.get_server_credentials(srv, active_p) if config_manager else {}
        user = (creds.get("username") or "").strip()
        pwd = (creds.get("password") or "").strip()
    if not user:
        user = srv.get("default_user") or srv.get("username") or "admin"
    return user, pwd


def _set_backend_health_cache(srv_id, online, version, latest_version, url):
    """Memperbarui cache status kesehatan & rute URL backend secara konsisten."""
    now_ts = time.time() if online else 0
    if online and url:
        _backend_url_cache[srv_id] = (url, now_ts + 25.0)
    else:
        _backend_url_cache.pop(srv_id, None)
    _cached_backend_info["timestamp"] = now_ts
    _cached_backend_info["server_id"] = srv_id
    _cached_backend_info["data"] = {
        "online": bool(online),
        "version": version,
        "latestVersion": latest_version,
        "url": url,
    }
    return dict(_cached_backend_info["data"])


_BACKEND_DEPLOY_GUARD = threading.Lock()
_ACTIVE_BACKEND_DEPLOYS = set()


def _mask_secret(text, secret):
    txt = str(text) if text is not None else ""
    if secret and secret in txt:
        return txt.replace(secret, "***")
    return txt


def handle_remote_backend_action(body):
    """
    Eksekusi 1-Klik Fresh Install atau Update OTA Backend ZimaOS via SSH & GitHub Release.
    Mendukung mode source ('auto', 'github', 'bundle'), override SSH opsional,
    lock konkurensi per server, dan deteksi authFailed terstruktur.
    """
    import shlex

    body = body if isinstance(body, dict) else {}
    pwd = ""
    srv_id = None
    lock_acquired = False
    temp_downloads = []

    try:
        action = (body.get("action") or "update").strip().lower()
        source = (body.get("source") or "auto").strip().lower()
        if source not in ("auto", "github", "bundle"):
            return {
                "success": False,
                "status": "error",
                "validationError": True,
                "stage": "validation",
                "message": f"Sumber instalasi backend tidak valid: {source}",
            }

        raw_ssh_port = body.get("sshPort") if body.get("sshPort") is not None else body.get("ssh_port")
        if raw_ssh_port is None or str(raw_ssh_port).strip() == "":
            ssh_port = 22
        elif isinstance(raw_ssh_port, bool):
            return {
                "success": False,
                "status": "error",
                "validationError": True,
                "stage": "validation",
                "message": "Port SSH tidak valid (harus 1-65535).",
            }
        else:
            try:
                ssh_port = int(str(raw_ssh_port).strip())
            except (TypeError, ValueError):
                ssh_port = 0
            if ssh_port < 1 or ssh_port > 65535:
                return {
                    "success": False,
                    "status": "error",
                    "validationError": True,
                    "stage": "validation",
                    "message": "Port SSH tidak valid (harus 1-65535).",
                }

        req_server_id = (body.get("serverId") or body.get("server_id") or "").strip()
        cfg = config_manager.load_or_create_config() if config_manager else {}

        repo_slug, raw_repo_slug = _resolve_github_repo_slug(cfg, body)
        if source == "github" and not repo_slug:
            return {
                "success": False,
                "status": "error",
                "validationError": True,
                "stage": "validation",
                "message": f"Format github_repo tidak valid (harus owner/repo): {raw_repo_slug}",
            }

        srv = _select_target_server(cfg, target_server_id=req_server_id)
        if not srv:
            return {"success": False, "status": "error", "message": "Server target tidak ditemukan."}

        srv_id = srv.get("id") or "default"

        with _BACKEND_DEPLOY_GUARD:
            if srv_id in _ACTIVE_BACKEND_DEPLOYS:
                return {
                    "success": False,
                    "status": "error",
                    "busy": True,
                    "stage": "locked",
                    "message": "Proses instalasi/pembaruan backend untuk server ini sedang berlangsung.",
                }
            _ACTIVE_BACKEND_DEPLOYS.add(srv_id)
            lock_acquired = True

        ota_applied = False
        ota_backend_state = None

        def _with_ota_state(res_payload):
            if ota_applied and isinstance(res_payload, dict) and not res_payload.get("success"):
                res_payload["otaApplied"] = True
                res_payload["rebuildPendingSshAuth"] = True
                if ota_backend_state and "backend" not in res_payload:
                    res_payload["backend"] = ota_backend_state
                if res_payload.get("authFailed"):
                    msg = (
                        "HTTP OTA sudah diterapkan pada backend, namun rebuild container via SSH "
                        "memerlukan autentikasi SSH."
                    )
                else:
                    orig_msg = (res_payload.get("message") or res_payload.get("error") or "").strip()
                    msg = (
                        "HTTP OTA sudah diterapkan pada backend, namun rebuild container via SSH "
                        f"gagal/memerlukan autentikasi SSH ({orig_msg})."
                        if orig_msg
                        else "HTTP OTA sudah diterapkan pada backend, namun rebuild container via SSH memerlukan autentikasi SSH."
                    )
                res_payload["message"] = msg
                res_payload["error"] = msg
            return res_payload

        target_ver = _get_bundled_backend_version(
            cfg=cfg,
            allow_remote=(source != "bundle"),
            force_remote=(source != "bundle"),
        )
        local_zip, local_bundle = _get_bundled_backend_packages()

        if source == "bundle":
            has_bundle = bool(local_bundle and os.path.exists(local_bundle))
            has_ota_zip = bool(action == "update" and local_zip and os.path.exists(local_zip))
            if not has_bundle and not has_ota_zip:
                return {
                    "success": False,
                    "status": "error",
                    "validationError": True,
                    "stage": "validation",
                    "message": "Paket bundle backend lokal tidak ditemukan di perangkat.",
                }

        ota_zip = local_zip
        ssh_bundle = local_bundle
        stale_local_zip = False
        stale_local_bundle = False
        if source == "auto" and target_ver:
            local_zip_exists = bool(local_zip and os.path.exists(local_zip))
            local_bundle_exists = bool(local_bundle and os.path.exists(local_bundle))
            stale_local_zip = local_zip_exists and _is_local_archive_stale_for_target(local_zip, target_ver)
            stale_local_bundle = local_bundle_exists and _is_local_archive_stale_for_target(local_bundle, target_ver)
            if action == "update" and repo_slug and (stale_local_zip or not local_zip_exists):
                remote_v, pkg_zip_name, _ = _fetch_remote_backend_manifest_info(cfg=cfg, force=False)
                if stale_local_zip or (remote_v and _compare_backend_versions(remote_v, target_ver) == 0):
                    logger_manager.log_info(
                        f"[handle_remote_backend_action] Mengunduh paket HTTP OTA Backend v{target_ver} dari GitHub..."
                    )
                    dl_zip = _download_remote_backend_archive(
                        repo_slug,
                        pkg_zip_name or "MyServer-Backend-ZimaOS.zip",
                        ".zip",
                        expected_ver=target_ver,
                    )
                    if dl_zip:
                        temp_downloads.append(dl_zip)
                        ota_zip = dl_zip
                    elif stale_local_zip:
                        # Jangan kirim arsip lokal lama saat versi rilis GitHub sudah lebih baru
                        ota_zip = None

        # Jalur Cepat 1: HTTP OTA langsung jika backend server saat ini sudah online (kecuali source="github")
        if source != "github" and action == "update" and ota_zip and os.path.exists(ota_zip):
            candidates = _get_backend_url_candidates(cfg, target_server_id=srv.get("id"), srv=srv)
            target_backend_url = _get_active_server_backend_url(cfg, target_server_id=srv.get("id"))
        else:
            candidates = []
            target_backend_url = ""

        if source != "github" and action == "update" and candidates and ota_zip and os.path.exists(ota_zip):
            ota_urls = []
            if target_backend_url:
                ota_urls.append(target_backend_url)
            for cu in candidates:
                if cu not in ota_urls:
                    ota_urls.append(cu)
            ota_secret_masks = []
            try:
                logger_manager.log_info(f"[handle_remote_backend_action] Mencoba pembaruan cepat HTTP OTA ke {ota_urls[0]}/api/v1/system/update (paket: {ota_zip})...")
                boundary = f"----WebKitFormBoundary{int(time.time()*1000)}"
                with open(ota_zip, "rb") as zf:
                    zip_bytes = zf.read()

                smb_cfg = (
                    config_manager.get_server_smb_source_config(srv)
                    if (config_manager and hasattr(config_manager, "get_server_smb_source_config"))
                    else {}
                )
                smb_role = str(smb_cfg.get("role") or "").strip().lower()
                smb_is_admin = smb_role in ("admin", "root")
                smb_token = str(smb_cfg.get("access_token") or "").strip() if smb_is_admin else ""
                smb_user = str(smb_cfg.get("username") or "").strip() if smb_is_admin else ""
                smb_pwd = str(smb_cfg.get("password") or "") if smb_is_admin else ""

                zima_user, zima_pwd = _resolve_ssh_admin_credentials(srv)
                zimaos_token = ""
                try:
                    mc = _active_metrics_client
                    if mc is None and cfg and (cfg.get("active_server_id") == srv_id or not srv_id):
                        au, _ = get_active_resolved_route(cfg)
                        if au:
                            mc = get_cached_metrics_client(srv, au)
                    if mc is not None:
                        zimaos_token = str(getattr(mc, "token", "") or "").strip()
                except Exception:
                    zimaos_token = ""

                ota_username = (smb_user if (smb_is_admin and smb_user and (smb_pwd or smb_token)) else zima_user) or "admin"
                ota_password = smb_pwd if (smb_is_admin and smb_user and smb_pwd) else zima_pwd
                ota_secret_masks = [s for s in (smb_token, smb_pwd, zima_pwd, zimaos_token, ota_password) if s]

                def _build_ota_body(uname_val, pwd_val, ztok_val):
                    parts = [
                        f"--{boundary}\r\nContent-Disposition: form-data; name=\"username\"\r\n\r\n{uname_val}\r\n".encode("utf-8")
                    ]
                    if pwd_val:
                        parts.append(
                            f"--{boundary}\r\nContent-Disposition: form-data; name=\"password\"\r\n\r\n{pwd_val}\r\n".encode("utf-8")
                        )
                    if ztok_val:
                        parts.append(
                            f"--{boundary}\r\nContent-Disposition: form-data; name=\"zimaos_token\"\r\n\r\n{ztok_val}\r\n".encode("utf-8")
                        )
                    parts.append(
                        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"update.zip\"\r\nContent-Type: application/zip\r\n\r\n".encode("utf-8")
                    )
                    parts.append(zip_bytes)
                    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
                    return b"".join(parts)

                def _verify_ota_jwt(cand_base, uname_val, pwd_val, ztok_val=""):
                    if not uname_val or not (pwd_val or ztok_val):
                        return "", None, None
                    v_payload = {"username": uname_val}
                    if pwd_val:
                        v_payload["password"] = pwd_val
                    elif ztok_val:
                        v_payload["zimaos_token"] = ztok_val
                    v_bytes = json.dumps(v_payload).encode("utf-8")
                    v_req = urllib.request.Request(
                        f"{cand_base}/api/v1/auth/verify",
                        data=v_bytes,
                        headers={"Content-Type": "application/json", "Connection": "close"},
                        method="POST",
                    )
                    try:
                        with urllib.request.urlopen(v_req, timeout=4) as v_resp:
                            v_data = json.loads(v_resp.read().decode("utf-8"))
                            if isinstance(v_data, dict):
                                tok = str(v_data.get("access_token") or "").strip()
                                v_role = str(v_data.get("role") or "").strip().lower()
                                if tok and v_role in ("admin", "root"):
                                    return tok, v_data, None
                    except urllib.error.HTTPError:
                        return "", None, None
                    except (urllib.error.URLError, TimeoutError, OSError) as net_ex:
                        return "", None, net_ex
                    except Exception:
                        pass
                    return "", None, None

                body_bytes = _build_ota_body(ota_username, ota_password, zimaos_token)

                ota_succeeded_url = None
                ota_resp_data = {}
                last_ota_err = None
                for cand_ota_url in ota_urls:
                    try:
                        bearer_token = smb_token
                        if not bearer_token and (ota_password or zimaos_token):
                            fetched_tok, _, verify_net_err = _verify_ota_jwt(cand_ota_url, ota_username, ota_password, zimaos_token)
                            if verify_net_err is not None:
                                last_ota_err = verify_net_err
                                continue
                            if fetched_tok:
                                bearer_token = fetched_tok

                        def _send_ota_upload(use_bearer, upload_bytes):
                            hdrs = {
                                "Content-Type": f"multipart/form-data; boundary={boundary}",
                                "Connection": "close",
                            }
                            if use_bearer:
                                hdrs["Authorization"] = f"Bearer {use_bearer}"
                            req = urllib.request.Request(
                                f"{cand_ota_url}/api/v1/system/update",
                                data=upload_bytes,
                                headers=hdrs,
                                method="POST",
                            )
                            with urllib.request.urlopen(req, timeout=20) as resp:
                                return json.loads(resp.read().decode("utf-8"))

                        try:
                            resp_data = _send_ota_upload(bearer_token, body_bytes)
                        except urllib.error.HTTPError as he:
                            if he.code == 401 and bearer_token:
                                fresh_tok, v_data, _ = _verify_ota_jwt(cand_ota_url, ota_username, ota_password, zimaos_token)
                                if not fresh_tok and zima_user and (zima_pwd or zimaos_token) and (
                                    ota_username != zima_user or ota_password != zima_pwd
                                ):
                                    fresh_tok, v_data, _ = _verify_ota_jwt(cand_ota_url, zima_user, zima_pwd, zimaos_token)
                                if fresh_tok:
                                    if smb_is_admin:
                                        _persist_refreshed_backend_token(srv_id, fresh_tok, v_data)
                                    resp_data = _send_ota_upload(fresh_tok, body_bytes)
                                elif ota_password or zimaos_token or zima_pwd:
                                    fb_bytes = _build_ota_body(zima_user or ota_username, zima_pwd or ota_password, zimaos_token)
                                    resp_data = _send_ota_upload("", fb_bytes)
                                else:
                                    raise
                            else:
                                raise

                        if isinstance(resp_data, dict) and resp_data.get("status") == "success":
                            ota_succeeded_url = cand_ota_url
                            ota_resp_data = resp_data
                            break
                    except Exception as cand_err:
                        last_ota_err = cand_err
                if ota_succeeded_url:
                    pre_boot_id = (ota_resp_data.get("boot_id") or "").strip()
                    has_ssh_override_pwd = bool(
                        body.get("sshPassword")
                        if body.get("sshPassword") is not None
                        else body.get("ssh_password")
                    )
                    has_ssh_creds = bool(_resolve_ssh_admin_credentials(srv)[1]) or has_ssh_override_pwd
                    cached_data = (
                        _cached_backend_info.get("data")
                        if isinstance(_cached_backend_info.get("data"), dict)
                        else {}
                    )
                    pre_ota_cached_ver = ""
                    if _cached_backend_info.get("server_id") == srv_id and cached_data.get("online"):
                        pre_ota_cached_ver = (cached_data.get("version") or "").strip()
                    old_ver = (ota_resp_data.get("old_version") or pre_ota_cached_ver or "").strip()
                    crossed_140_boundary = bool(
                        old_ver
                        and target_ver
                        and _compare_backend_versions(old_ver, "1.4.0") < 0
                        and _compare_backend_versions(target_ver, "1.4.0") >= 0
                    )
                    rebuild_required = bool(ota_resp_data.get("rebuild_required")) or crossed_140_boundary
                    logger_manager.log_info("[handle_remote_backend_action] HTTP OTA diterima! Menunggu proses restart & verifikasi /health...")

                    # Bersihkan cache lama agar status versi pra-restart tidak terbaca sebagai sukses palsu
                    offline_backend = _set_backend_health_cache(srv_id, False, "", target_ver, ota_succeeded_url)

                    # Backend menjadwalkan exit setelah ~1.5 detik; beri jeda awal lalu polling hingga 30 detik
                    time.sleep(2.5)
                    poll_ok = False
                    health_data = {}
                    last_poll_data = None
                    for _ in range(15):
                        h_ok, h_data, _ = _backend_http_request(f"{ota_succeeded_url}/health", method="GET", timeout=2.0, retries=0)
                        if h_ok and isinstance(h_data, dict) and h_data.get("status") == "ok":
                            last_poll_data = h_data
                            cand_ver = (h_data.get("version") or "").strip()
                            post_boot_id = (h_data.get("boot_id") or "").strip()
                            same_boot_id = bool(pre_boot_id and post_boot_id and post_boot_id == pre_boot_id)
                            older_ver = bool(target_ver and cand_ver and _compare_backend_versions(cand_ver, target_ver) < 0)
                            if not same_boot_id and not older_ver:
                                poll_ok = True
                                health_data = h_data
                                break
                        time.sleep(2.0)

                    if poll_ok:
                        ver = (health_data.get("version") or "").strip()
                        active_target_ver = target_ver or ver
                        backend_state = _set_backend_health_cache(srv_id, True, ver, active_target_ver, ota_succeeded_url)
                        if rebuild_required and has_ssh_creds:
                            ota_applied = True
                            ota_backend_state = backend_state
                            logger_manager.log_info(
                                "[handle_remote_backend_action] Perubahan Dockerfile/docker-compose.yml terdeteksi (rebuild_required=True); melanjutkan auto-chain rebuild via SSH..."
                            )
                            raise RuntimeError("Auto-chaining SSH rebuild because rebuild_required=True")
                        msg = f"Backend ZimaOS v{ver or active_target_ver} berhasil diperbarui!"
                        if rebuild_required:
                            msg += " Perubahan Dockerfile/requirements.txt terdeteksi; disarankan rebuild image container via SSH."
                        return {
                            "success": True,
                            "status": "ok",
                            "message": msg,
                            "rebuildRecommended": rebuild_required,
                            "backend": backend_state
                        }

                    if isinstance(last_poll_data, dict):
                        last_ver = (last_poll_data.get("version") or "").strip()
                        last_boot_id = (last_poll_data.get("boot_id") or "").strip()
                        active_target_ver = target_ver or last_ver
                        backend_state = _set_backend_health_cache(srv_id, True, last_ver, active_target_ver, ota_succeeded_url)
                        if target_ver and last_ver and _compare_backend_versions(last_ver, target_ver) < 0:
                            logger_manager.log_warning(f"[handle_remote_backend_action] HTTP OTA selesai namun versi server tetap v{last_ver} (< v{target_ver})")
                            return {
                                "success": False,
                                "status": "error",
                                "message": f"Update OTA selesai namun versi server tetap v{last_ver} (target v{target_ver}).",
                                "backend": backend_state
                            }
                        if pre_boot_id and last_boot_id and last_boot_id == pre_boot_id:
                            if has_ssh_creds:
                                raise RuntimeError("Backend merespons tetapi tidak me-restart (boot_id tidak berubah); melanjutkan pemulihan via SSH.")
                            return {
                                "success": False,
                                "status": "error",
                                "message": "Paket OTA dikirim, namun proses backend tidak ter-restart (boot_id tidak berubah) dan SSH belum terkonfigurasi.",
                                "backend": backend_state
                            }

                    if has_ssh_creds:
                        raise RuntimeError("Backend tidak kembali online dalam 32 detik pasca HTTP OTA; melanjutkan pemulihan via SSH.")
                    return {
                        "success": False,
                        "status": "error",
                        "message": "Paket OTA dikirim, namun backend tidak kembali merespons /health dalam 32 detik dan SSH belum terkonfigurasi.",
                        "backend": offline_backend
                    }
                elif last_ota_err:
                    raise last_ota_err
            except Exception as ota_err:
                safe_ota_err = str(ota_err)
                for s_val in ota_secret_masks:
                    safe_ota_err = _mask_secret(safe_ota_err, s_val)
                logger_manager.log_info(f"[handle_remote_backend_action] HTTP OTA dilewati / gagal ({safe_ota_err}), melanjutkan ke alur SSH...")

        # 1. Kumpulkan kandidat host SSH (utamakan sshHost override jika diberikan, lalu Remote P2P IP)
        ssh_host_override = str(body.get("sshHost") or body.get("ssh_host") or "").strip()
        ssh_user_override = str(body.get("sshUser") or body.get("ssh_user") or "").strip()
        ssh_pwd_override = body.get("sshPassword") if body.get("sshPassword") is not None else body.get("ssh_password")

        candidates = []
        if ssh_host_override:
            candidates.append(ssh_host_override)
        else:
            rem_info = config_manager.get_dynamic_remote_info(srv, cfg) if config_manager else None
            rem_ip = rem_info.get("ip") if rem_info else ""
            if not rem_ip:
                rem_ip = (srv.get("easytier_virtual_ip") or srv.get("zerotier_virtual_ip") or "").strip()
            if rem_ip:
                candidates.append(rem_ip)

            for c in srv.get("connections", []):
                curl = c.get("url", "")
                ch = urllib.parse.urlparse(curl if "://" in curl else f"http://{curl}").hostname
                if ch and ch not in candidates:
                    from smb_mount_manager import _is_domain_or_wan_host
                    if not _is_domain_or_wan_host(ch):
                        candidates.insert(0, ch)
                    else:
                        candidates.append(ch)

        if not candidates:
            return _with_ota_state({"success": False, "status": "error", "message": "Tidak ada alamat host IP yang dapat dihubungi."})

        # 2. Ambil kredensial admin (prioritaskan override wizard lalu 'Admin' untuk izin sudo)
        user, pwd = _resolve_ssh_admin_credentials(srv)
        if ssh_user_override:
            user = ssh_user_override
        if ssh_pwd_override is not None and str(ssh_pwd_override) != "":
            pwd = str(ssh_pwd_override)

        # 3. Hubungkan via Paramiko SSH
        ssh_client = None
        connected_host = None
        connect_error = None
        auth_failed_error = None
        try:
            import paramiko
        except ImportError as ie:
            logger_manager.log_error(f"[handle_remote_backend_action] Modul paramiko belum terpasang: {ie}")
            return _with_ota_state({"success": False, "status": "error", "message": f"Modul SSH (paramiko) belum terpasang: {ie}"})

        auth_exc_cls = getattr(paramiko, "AuthenticationException", None)
        for host_ip in candidates:
            try:
                logger_manager.log_info(f"[handle_remote_backend_action] Mencoba SSH ke {user}@{host_ip}:{ssh_port}...")
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(host_ip, port=ssh_port, username=user, password=pwd, timeout=5, banner_timeout=5)
                ssh_client = client
                connected_host = host_ip
                logger_manager.log_info(f"[handle_remote_backend_action] SSH berhasil tersambung ke {host_ip}!")
                break
            except Exception as ex:
                connect_error = ex
                is_auth_err = (
                    (auth_exc_cls is not None and isinstance(ex, auth_exc_cls))
                    or "authentication" in str(ex).lower()
                    or "auth fail" in str(ex).lower()
                )
                logger_manager.log_debug(
                    f"[handle_remote_backend_action] Gagal SSH ke {host_ip}: {_mask_secret(ex, pwd)}"
                )
                if is_auth_err:
                    auth_failed_error = ex
                    break

        if not ssh_client or not connected_host:
            if auth_failed_error is not None:
                return _with_ota_state({
                    "success": False,
                    "status": "error",
                    "authFailed": True,
                    "stage": "ssh_auth",
                    "message": "Autentikasi SSH gagal. Periksa kembali username dan password SSH Anda.",
                })
            return _with_ota_state({
                "success": False,
                "status": "error",
                "message": f"Gagal menghubungkan sesi SSH ke server: {_mask_secret(connect_error, pwd)}",
            })

        try:
            # 4. Unggah paket lokal via SFTP atau unduh dari GitHub Release sesuai mode source
            safe_user = re.sub(r"[^A-Za-z0-9_.-]", "_", user or "admin").strip("._") or "admin"
            deploy_dir = f"/tmp/myserver_deploy_{safe_user}"
            _exec_ssh_command_bounded(
                ssh_client,
                f"rm -rf {shlex.quote(deploy_dir)} && mkdir -p {shlex.quote(deploy_dir)}",
                timeout=15.0,
            )

            uploaded_local = False
            if source == "auto" and stale_local_bundle:
                ssh_bundle = None
                if repo_slug and target_ver:
                    _, _, pkg_tar_name = _fetch_remote_backend_manifest_info(cfg=cfg, force=False)
                    dl_tar = _download_remote_backend_archive(
                        repo_slug,
                        pkg_tar_name or "MyServer-Backend-ZimaOS.tar.gz",
                        ".tar.gz",
                        expected_ver=target_ver,
                    )
                    if dl_tar:
                        temp_downloads.append(dl_tar)
                        ssh_bundle = dl_tar

            if source != "github" and ssh_bundle and os.path.exists(ssh_bundle):
                try:
                    logger_manager.log_info(f"[handle_remote_backend_action] Mengunggah paket lokal {ssh_bundle} via SFTP...")
                    sftp = ssh_client.open_sftp()
                    sftp_chan = getattr(sftp, "get_channel", lambda: None)()
                    if sftp_chan is not None and callable(getattr(sftp_chan, "settimeout", None)):
                        sftp_chan.settimeout(30.0)
                    try:
                        sftp.put(ssh_bundle, f"{deploy_dir}/backend.tar.gz")
                    finally:
                        sftp.close()
                    uploaded_local = True
                    logger_manager.log_info("[handle_remote_backend_action] Paket lokal berhasil diunggah via SFTP.")
                except Exception as sftp_err:
                    if source == "bundle":
                        logger_manager.log_warning(f"[handle_remote_backend_action] Gagal upload SFTP dalam mode bundle: {sftp_err}")
                        return _with_ota_state({
                            "success": False,
                            "status": "error",
                            "message": f"Gagal mengunggah paket lokal via SFTP: {_mask_secret(sftp_err, pwd)}",
                        })
                    logger_manager.log_warning(f"[handle_remote_backend_action] Gagal upload SFTP ({sftp_err}), mencoba unduh dari GitHub...")

            if not uploaded_local:
                if source == "bundle":
                    return _with_ota_state({
                        "success": False,
                        "status": "error",
                        "validationError": True,
                        "stage": "validation",
                        "message": "Paket bundle backend lokal tidak tersedia untuk unggah SFTP.",
                    })
                if not repo_slug:
                    return _with_ota_state({
                        "success": False,
                        "status": "error",
                        "validationError": True,
                        "stage": "validation",
                        "message": f"Format github_repo tidak valid (harus owner/repo): {raw_repo_slug}",
                    })
                github_url = f"https://github.com/{repo_slug}/releases/latest/download/MyServer-Backend-ZimaOS.tar.gz"
                curl_cmd = f"cd {shlex.quote(deploy_dir)} && curl -sSL --connect-timeout 10 --max-time 30 -f {shlex.quote(github_url)} -o backend.tar.gz"
                exit_status, _, _ = _exec_ssh_command_bounded(ssh_client, curl_cmd, timeout=35.0)

                _, sz_raw, _ = _exec_ssh_command_bounded(
                    ssh_client,
                    f"wc -c < {shlex.quote(deploy_dir)}/backend.tar.gz 2>/dev/null || echo 0",
                    timeout=10.0,
                )
                sz_text = sz_raw.decode("utf-8", errors="ignore").strip() if isinstance(sz_raw, bytes) else str(sz_raw).strip()
                downloaded_bytes = int(sz_text or "0")

                if exit_status != 0 or downloaded_bytes < 1000:
                    return _with_ota_state({
                        "success": False,
                        "status": "error",
                        "message": "Paket installer backend tidak dapat diunggah via SFTP maupun diunduh dari GitHub."
                    })

            # 5. Eksekusi unpacking dan install_zimaos.sh dengan sudo (bounded 360s agar tidak deadlock di recv_exit_status)
            logger_manager.log_info("[handle_remote_backend_action] Menjalankan install_zimaos.sh dengan sudo...")
            exec_script = f"cd {shlex.quote(deploy_dir)} && tar -xzf backend.tar.gz && printf '%s\\n' {shlex.quote(pwd)} | sudo -S bash install_zimaos.sh"
            exec_exit, exec_out_raw, exec_err_raw = _exec_ssh_command_bounded(ssh_client, exec_script, timeout=360.0)
            exec_out_text = _mask_secret(exec_out_raw.decode("utf-8", errors="replace") if isinstance(exec_out_raw, bytes) else str(exec_out_raw), pwd)
            exec_err_text = _mask_secret(exec_err_raw.decode("utf-8", errors="replace") if isinstance(exec_err_raw, bytes) else str(exec_err_raw), pwd)
            logger_manager.log_info(f"[handle_remote_backend_action] Output instalasi (exit={exec_exit}): {exec_out_text[-500:]}")

            err_lower = exec_err_text.lower()
            if exec_exit != 0 and any(
                tok in err_lower
                for tok in ("incorrect password", "sorry, try again", "authentication failure", "permission denied", "a password is required")
            ):
                return _with_ota_state({
                    "success": False,
                    "status": "error",
                    "authFailed": True,
                    "stage": "ssh_auth",
                    "message": "Autentikasi sudo/SSH ditolak oleh server. Periksa username dan password SSH.",
                })

            # 6. Polling endpoint /health di port 8080 selama maksimal 30 detik (pakai kandidat dinamis)
            health_candidates = []
            conn_burl = _format_backend_url(connected_host, 8080) if connected_host else ""
            dynamic_burls = _get_backend_url_candidates(cfg, target_server_id=srv.get("id"), srv=srv) or []
            if ssh_host_override and conn_burl:
                health_candidates.append(conn_burl)
            for cu in dynamic_burls:
                if cu and cu not in health_candidates:
                    health_candidates.append(cu)
            if conn_burl and conn_burl not in health_candidates:
                health_candidates.append(conn_burl)
            if not health_candidates and connected_host:
                health_candidates.append(f"http://{connected_host}:8080")

            backend_url = health_candidates[0] if health_candidates else f"http://{connected_host}:8080"
            poll_ok = False
            health_data = {}
            logger_manager.log_info(f"[handle_remote_backend_action] Memulai verifikasi healthcheck ke kandidat {health_candidates}...")
            for _ in range(15):
                time.sleep(2.0)
                for cand_hurl in health_candidates:
                    h_ok, h_data, h_code = _backend_http_request(f"{cand_hurl}/health", method="GET", timeout=2.0, retries=0)
                    if h_ok and isinstance(h_data, dict) and h_data.get("status") == "ok":
                        poll_ok = True
                        health_data = h_data
                        backend_url = cand_hurl
                        break
                if poll_ok:
                    break

            if poll_ok:
                ver = (health_data.get("version") or "").strip()
                active_target_ver = target_ver or ver
                backend_state = _set_backend_health_cache(srv_id, True, ver, active_target_ver, backend_url)
                if target_ver and ver and _compare_backend_versions(ver, target_ver) < 0:
                    logger_manager.log_error(f"[handle_remote_backend_action] Versi aktif ({ver}) lebih rendah dari target ({target_ver}).")
                    return _with_ota_state({
                        "success": False,
                        "status": "error",
                        "message": f"Instalasi backend selesai, namun versi server tetap v{ver} (seharusnya v{target_ver}).",
                        "backend": backend_state
                    })
                msg = f"Backend server berhasil diperbarui ke v{ver or active_target_ver}!" if action == "update" else f"Backend server v{ver or active_target_ver} berhasil dipasang!"
                logger_manager.log_info(f"[handle_remote_backend_action] Sukses! Versi aktif: {ver}")
                return {
                    "success": True,
                    "status": "ok",
                    "message": msg,
                    "backend": backend_state
                }
            else:
                offline_backend = _set_backend_health_cache(srv_id, False, "", target_ver, backend_url)
                err_detail = ""
                if exec_exit != 0:
                    tail = (exec_err_text or exec_out_text).strip()[-240:]
                    err_detail = f" (install exit={exec_exit}: {tail})" if tail else f" (install exit={exec_exit})"
                return _with_ota_state({
                    "success": False,
                    "status": "error",
                    "message": f"Instalasi selesai namun healthcheck port 8080 tidak merespons dalam 30 detik.{err_detail}",
                    "backend": offline_backend
                })

        finally:
            try:
                ssh_client.close()
            except Exception:
                pass
    except Exception as ex:
        safe_ex = _mask_secret(ex, pwd)
        logger_manager.log_error(f"[handle_remote_backend_action] Exception unhandled: {safe_ex}")
        return _with_ota_state({
            "success": False,
            "status": "error",
            "message": f"Terjadi kesalahan saat memproses backend: {safe_ex}"
        })
    finally:
        for tmp_dl in temp_downloads:
            if tmp_dl and os.path.exists(tmp_dl):
                try:
                    os.remove(tmp_dl)
                except Exception:
                    pass
        if lock_acquired and srv_id is not None:
            with _BACKEND_DEPLOY_GUARD:
                _ACTIVE_BACKEND_DEPLOYS.discard(srv_id)


def spawn_app_window(target_url, title=None, width=1150, height=750, server_id=None, vm_id=None, force_window=False):







    """







    Meluncurkan jendela aplikasi sebagai subprocess terpisah (out-of-process)







    atau membuka di peramban default sesuai preferensi app_entry_open (Zima Client v2.3.5).







    """







    clean_u = (target_url or "").strip()







    if not clean_u:







        return False, "URL kosong"















    cfg = config_manager.load_or_create_config()







    open_mode = cfg.get("app_entry_open", "window")















    if open_mode == "browser" and not force_window:







        try:







            if sys.platform == "win32":







                os.startfile(clean_u)







            else:







                webbrowser.open(clean_u)







            logger_manager.log_info(f"[CoreService] Membuka URL di peramban default (appEntryOpen=browser): {clean_u}")







            return True, "Dibuka di browser default"







        except Exception as e:







            logger_manager.log_error(f"[CoreService] Gagal membuka browser: {e}")







            return False, str(e)















    win_title = title.strip() if title and title.strip() else "MyServer"















    try:







        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--window", clean_u, "--title", win_title]
        else:
            cmd = [sys.executable, os.path.abspath(__file__), "--window", clean_u, "--title", win_title]
        if server_id:
            cmd.extend(["--server-id", str(server_id)])
        if vm_id:
            cmd.extend(["--vm-id", str(vm_id)])















        creation_flags = 0







        if sys.platform == "win32":







            # DETACHED_PROCESS agar jendela aplikasi hidup mandiri







            creation_flags = 0x00000008















        subprocess.Popen(cmd, creationflags=creation_flags, close_fds=True)







        logger_manager.log_info(f"[CoreService] Meluncurkan jendela aplikasi mandiri: {win_title} -> {clean_u}")







        return True, "Jendela diluncurkan"







    except Exception as e:







        logger_manager.log_error(f"[CoreService] Gagal meluncurkan jendela: {e}")







        try:







            if sys.platform == "win32":







                os.startfile(clean_u)







            else:







                webbrowser.open(clean_u)







            return True, "Dibuka di browser default"







        except Exception as e2:







            return False, str(e2)































# ----------------------------------------------------------------------







# Dynamic Route Resolver & Speed Formatter (Zima v2.3.5 Pattern)







# ----------------------------------------------------------------------







def format_network_speed(bytes_per_sec):







    """Memformat kecepatan transfer byte/detik menjadi string persis seperti Zima Client v2.3.5."""







    try:







        val = float(bytes_per_sec or 0)







    except (ValueError, TypeError):







        val = 0.0







    if val <= 0:







        return "0 B/s"







    if val < 1024:







        return f"{int(val)} B/s"







    elif val < 1024 * 1024:







        return f"{val / 1024:.1f} KB/s"







    elif val < 1024 * 1024 * 1024:







        return f"{val / (1024 * 1024):.1f} MB/s"







    else:







        return f"{val / (1024 * 1024 * 1024):.1f} GB/s"























_cached_active_route = {







    "url": "",







    "label": "",







    "last_check": 0.0,







    "server_id": None,







    "active_conn": None,







    "lock": threading.Lock()







}























def invalidate_active_route_cache():







    """Membuang cache rute aktif, cache backend URL, & metrics client agar server/rute baru langsung diresolusi ulang."""







    global _active_metrics_client, _active_metrics_client_key







    with _cached_active_route["lock"]:







        _cached_active_route["url"] = ""







        _cached_active_route["label"] = ""







        _cached_active_route["last_check"] = 0.0







        _cached_active_route["server_id"] = None







        _cached_active_route["active_conn"] = None







    _active_metrics_client = None







    _active_metrics_client_key = None

    _backend_url_cache.clear()
    _cached_backend_info["timestamp"] = 0
    _cached_backend_info["server_id"] = ""
    _cached_backend_info["data"] = {"online": False, "version": "", "latestVersion": "", "url": ""}























def get_active_resolved_route(cfg=None, force_refresh=False):







    """







    Mengembalikan tuple (active_url, indicator_text) dengan cache cerdas non-blocking.







    Jika cache masih segar (< 10 detik) dan tidak force_refresh, langsung kembalikan dalam 0.01 ms.







    Jika kedaluwarsa atau force_refresh, jalankan resolusi dengan pengecekan jaringan nyata.







    """







    global _cached_active_route







    now = time.time()







    with _cached_active_route["lock"]:







        cached_url = _cached_active_route["url"]







        cached_lbl = _cached_active_route["label"]







        last_chk = _cached_active_route["last_check"]







        cached_sid = _cached_active_route["server_id"]







        cached_conn = _cached_active_route["active_conn"]







    # Cache hanya valid untuk server & jalur aktif yang sama (cegah kebocoran rute antar-server)







    if cfg is not None and not force_refresh and cached_url:







        _chk_srv = config_manager.get_active_server(cfg)







        if _chk_srv and (_chk_srv.get("id") != cached_sid or _chk_srv.get("active_connection", "auto") != cached_conn):







            cached_url = ""







    if not force_refresh and cached_url and (now - last_chk < 10.0):







        return cached_url, cached_lbl















    if cfg is None:







        cfg = config_manager.load_or_create_config()















    srv = config_manager.get_active_server(cfg)







    if not srv:







        return "http://zimaos.local", "No Server"







    srv_id = srv.get("id")







    act_conn = srv.get("active_connection", "auto")







    # Jika rute manual spesifik dipilih, langsung gunakan rute tersebut tanpa delay







    if act_conn != "auto":



        srv_zt_ip_val = (srv.get("zerotier_virtual_ip") or "").strip()



        if srv_zt_ip_val and (act_conn == "conn_zerotier_auto" or act_conn == f"http://{srv_zt_ip_val}"):



            url = f"http://{srv_zt_ip_val}"



            lbl = f"ZeroTier Remote: {url}"



            with _cached_active_route["lock"]:



                _cached_active_route["url"] = url



                _cached_active_route["label"] = lbl



                _cached_active_route["last_check"] = now



                _cached_active_route["server_id"] = srv_id



                _cached_active_route["active_conn"] = act_conn



            return url, lbl







        for c in srv.get("connections", []):







            if c.get("id") == act_conn or c.get("url") == act_conn:







                url = c.get("url", "")







                lbl = f"{c.get('name', 'Route')}: {url}"







                with _cached_active_route["lock"]:







                    _cached_active_route["url"] = url







                    _cached_active_route["label"] = lbl







                    _cached_active_route["last_check"] = now







                    _cached_active_route["server_id"] = srv_id







                    _cached_active_route["active_conn"] = act_conn







                return url, lbl















    # Jika rute otomatis (auto): lakukan pengecekan jaringan nyata dengan timeout cepat







    url, lbl = config_manager.resolve_target_connection(cfg, check_network=True, target_server=srv)







    with _cached_active_route["lock"]:







        _cached_active_route["url"] = url







        _cached_active_route["label"] = lbl







        _cached_active_route["last_check"] = now







        _cached_active_route["server_id"] = srv_id







        _cached_active_route["active_conn"] = act_conn







    return url, lbl























_auto_route_smb_lock = threading.Lock()
_auto_route_smb_tracker = {
    "server_id": None,
    "mounted_host": "",
    "pending_host": "",
    "pending_since_ts": 0.0,
}
AUTO_ROUTE_SMB_DEBOUNCE_SEC = 5.0

_shutdown_daemons_lock = threading.Lock()
_shutdown_daemons_done = False

WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012
DEVICE_NOTIFY_WINDOW_HANDLE = 0x00000000
POWER_RESUME_DEDUP_SEC = 5.0
POWER_RESUME_REBIND_DELAY_SEC = 2.5
SMB_OFFLINE_UNMOUNT_THRESHOLD = 5

_power_resume_lock = threading.Lock()
_last_power_resume_ts = 0.0
_active_power_wndproc_ref = None


def _collect_myserver_smb_hosts(cfg=None, server=None, include_all_servers=False):
    """Mengumpulkan seluruh host/IP resmi server MyServer agar unmount SMB strictly tidak menyentuh drive asing."""
    hosts = set()
    try:
        if cfg is None and config_manager is not None:
            cfg = config_manager.load_or_create_config()
    except Exception:
        cfg = None

    targets = []
    if include_all_servers and isinstance(cfg, dict):
        targets = [s for s in (cfg.get("servers") or []) if isinstance(s, dict)]
    elif isinstance(server, dict):
        targets = [server]
    elif isinstance(cfg, dict) and config_manager is not None:
        try:
            act = config_manager.get_active_server(cfg)
            if isinstance(act, dict):
                targets = [act]
        except Exception:
            pass

    for srv in targets:
        for conn in (srv.get("connections") or []):
            if isinstance(conn, dict) and conn.get("url"):
                ch = _extract_host_from_url(conn.get("url", ""))
                if ch:
                    hosts.add(ch.strip().lower())
        for key in ("host", "zerotier_virtual_ip", "easytier_virtual_ip"):
            val = (srv.get(key) or "").strip().lower()
            if val:
                hosts.add(val)
        srv_name = (srv.get("name") or "").strip()
        if srv_name and re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-.]{1,}$", srv_name):
            hosts.add(srv_name.lower())

    try:
        if isinstance(cfg, dict):
            act_u, _ = get_active_resolved_route(cfg)
            act_h = _extract_host_from_url(act_u) if act_u else ""
            if act_h:
                hosts.add(act_h.strip().lower())
    except Exception:
        pass

    try:
        alias_fn = getattr(smb_mount_manager, "get_active_1219_aliases", None)
        aliases = alias_fn() if callable(alias_fn) else {}
        for av in (aliases or {}).values():
            if av and str(av).strip():
                hosts.add(str(av).strip().lower())
    except Exception:
        pass

    return hosts


def _unmount_myserver_smb_drives(
    reason="lifecycle",
    cfg=None,
    server=None,
    include_all_servers=False,
    include_easytier_subnet=False,
    easytier_only=False,
):
    """Melepaskan hanya drive SMB milik MyServer dengan allowlist host ketat."""
    hosts = set()
    if easytier_only:
        try:
            if cfg is None and config_manager is not None:
                cfg = config_manager.load_or_create_config()
            srv_list = (cfg.get("servers") or []) if isinstance(cfg, dict) else []
            for s in srv_list:
                if isinstance(s, dict) and s.get("easytier_virtual_ip"):
                    hosts.add(str(s["easytier_virtual_ip"]).strip().lower())
        except Exception:
            pass
        prefixes = ("10.126.126.",)
    else:
        hosts = _collect_myserver_smb_hosts(
            cfg=cfg,
            server=server,
            include_all_servers=include_all_servers,
        )
        prefixes = ("10.126.126.",) if include_easytier_subnet else None

    try:
        unmounted = smb_mount_manager.unmount_all_smb_shares(
            allowed_hosts=hosts,
            allowed_prefixes=prefixes,
        )
        logger_manager.log_info(
            f"[SMB Lifecycle] Unmount terarah ({reason}): {unmounted} drive dilepaskan (hosts={len(hosts)})."
        )
        return unmounted
    except Exception as e:
        logger_manager.log_warning(f"[SMB Lifecycle] Gagal unmount terarah ({reason}): {e}")
        return 0


def _evaluate_auto_route_smb_transition(server_id, effective_host, now_ts=None, debounce_sec=AUTO_ROUTE_SMB_DEBOUNCE_SEC):
    """Mengevaluasi transisi host SMB efektif dengan debounce anti-flapping."""
    clean_host = (effective_host or "").strip().lower()
    if not clean_host:
        return False, ""
    now = float(now_ts if now_ts is not None else time.time())
    with _auto_route_smb_lock:
        if server_id != _auto_route_smb_tracker["server_id"]:
            _auto_route_smb_tracker["server_id"] = server_id
            _auto_route_smb_tracker["mounted_host"] = clean_host
            _auto_route_smb_tracker["pending_host"] = ""
            _auto_route_smb_tracker["pending_since_ts"] = 0.0
            return False, ""
        if not _auto_route_smb_tracker["mounted_host"]:
            _auto_route_smb_tracker["mounted_host"] = clean_host
            _auto_route_smb_tracker["pending_host"] = ""
            _auto_route_smb_tracker["pending_since_ts"] = 0.0
            return False, ""
        if clean_host == _auto_route_smb_tracker["mounted_host"]:
            _auto_route_smb_tracker["pending_host"] = ""
            _auto_route_smb_tracker["pending_since_ts"] = 0.0
            return False, ""
        if clean_host != _auto_route_smb_tracker["pending_host"]:
            _auto_route_smb_tracker["pending_host"] = clean_host
            _auto_route_smb_tracker["pending_since_ts"] = now
            return False, ""
        if (now - float(_auto_route_smb_tracker["pending_since_ts"])) >= float(debounce_sec):
            _auto_route_smb_tracker["mounted_host"] = clean_host
            _auto_route_smb_tracker["pending_host"] = ""
            _auto_route_smb_tracker["pending_since_ts"] = 0.0
            return True, clean_host
        return False, ""


def _record_mounted_smb_host(server_id, host_val):
    """Mencatat host SMB terbaru yang berhasil di-mount agar tracker auto-route sinkron."""
    clean_host = (host_val or "").strip().lower()
    if not clean_host:
        return
    with _auto_route_smb_lock:
        _auto_route_smb_tracker["server_id"] = server_id
        _auto_route_smb_tracker["mounted_host"] = clean_host
        _auto_route_smb_tracker["pending_host"] = ""
        _auto_route_smb_tracker["pending_since_ts"] = 0.0


def _check_effective_smb_host_transition_for_server(
    srv,
    active_url,
    auto_mount_enabled=True,
    is_online=True,
    now_ts=None,
    spawn_async=True,
):
    """Menguji apakah host SMB efektif berpindah (rute auto atau Domain LAN<->VPN) dan memicu rebind ter-debounce."""
    if not srv or not active_url or not auto_mount_enabled or not is_online:
        return False, ""
    host_p, is_dom_p, zt_p = _resolve_smb_route_params(srv, active_url)
    eff_host = smb_mount_manager.resolve_smb_host(
        host_p,
        srv.get("connections", []),
        is_dom_p,
        zt_p,
        max_age_seconds=15,
    )
    should_rebind, new_host = _evaluate_auto_route_smb_transition(
        srv.get("id"),
        eff_host,
        now_ts=now_ts,
    )
    if should_rebind:
        logger_manager.log_info(
            f"[SMB Lifecycle] Transisi host SMB efektif terdeteksi stabil -> '{new_host}'; memicu rebind_storage_pipeline('auto_route_changed')."
        )
        if spawn_async:
            threading.Thread(
                target=rebind_storage_pipeline,
                args=("auto_route_changed",),
                daemon=True,
            ).start()
        else:
            rebind_storage_pipeline("auto_route_changed")
        return True, new_host
    return False, ""


def _should_unmount_on_offline_streak(
    raw_on,
    offline_streak,
    already_unmounted,
    threshold=SMB_OFFLINE_UNMOUNT_THRESHOLD,
):
    """Menentukan apakah drive MyServer harus di-unmount satu kali setelah server offline beruntun."""
    return bool((not raw_on) and (offline_streak >= threshold) and (not already_unmounted))


def _handle_windows_power_event(event_type, now_ts=None, spawn_async=True):
    """Menangani event WM_POWERBROADCAST Windows (suspend -> unmount, resume -> dedup 5s + rebind 2.5s)."""
    global _last_power_resume_ts
    if event_type == PBT_APMSUSPEND:
        _unmount_myserver_smb_drives(
            reason="power_suspend",
            include_all_servers=True,
            include_easytier_subnet=True,
        )
        smb_mount_manager.invalidate_smb_host_cache()
        return "suspended"

    if event_type in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
        now = float(now_ts if now_ts is not None else time.time())
        with _power_resume_lock:
            if (now - float(_last_power_resume_ts)) < POWER_RESUME_DEDUP_SEC:
                return "resume_deduped"
            _last_power_resume_ts = now

        smb_mount_manager.invalidate_smb_host_cache()
        try:
            with _cached_active_route["lock"]:
                _cached_active_route["last_check"] = 0.0
        except Exception:
            pass

        def _delayed_resume_rebind():
            try:
                if spawn_async:
                    time.sleep(POWER_RESUME_REBIND_DELAY_SEC)
                cfg_now = config_manager.load_or_create_config()
                if bool(cfg_now.get("auto_mount_smb", True)):
                    rebind_storage_pipeline("power_resume")
            except Exception as _res_err:
                logger_manager.log_warning(f"[PowerMonitor] Gagal rebind pasca-resume: {_res_err}")

        if spawn_async:
            threading.Thread(target=_delayed_resume_rebind, daemon=True).start()
        else:
            _delayed_resume_rebind()
        return "resume_scheduled"

    return "ignored"


def _get_local_ipv4_snapshot():
    """Mengambil snapshot alamat IPv4 lokal antarmuka jaringan secara non-blocking."""
    ips = set()
    try:
        hostname = socket.gethostname()
        _, _, addr_list = socket.gethostbyname_ex(hostname)
        for ip in addr_list:
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("10.255.255.255", 1))
        local_ip = s.getsockname()[0]
        if local_ip and not local_ip.startswith("127."):
            ips.add(local_ip)
        s.close()
    except Exception:
        pass
    return sorted(ips)


def _handle_local_network_change(prev_ips, cur_ips):
    """Memvalidasi ulang cache host SMB dan rute aktif ketika himpunan IPv4 lokal berubah."""
    if set(prev_ips or ()) == set(cur_ips or ()):
        return False
    smb_mount_manager.invalidate_smb_host_cache()
    try:
        with _cached_active_route["lock"]:
            _cached_active_route["last_check"] = 0.0
    except Exception:
        pass
    logger_manager.log_info(
        f"[NetworkMonitor] Perubahan antarmuka jaringan terdeteksi ({len(prev_ips or [])} -> {len(cur_ips or [])} IP); cache rute & host SMB direset."
    )
    return True


def windows_power_monitor_loop():
    """Mendengarkan WM_POWERBROADCAST (termasuk Modern Standby S0ix) lewat hidden top-level window Win32."""
    global _active_power_wndproc_ref
    if sys.platform != "win32":
        return
    try:
        import ctypes.wintypes as wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT

        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HANDLE),
            ]

        user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
        user32.RegisterClassExW.restype = wintypes.ATOM

        def _wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_POWERBROADCAST:
                try:
                    _handle_windows_power_event(int(wparam))
                except Exception:
                    pass
                return 1
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        _active_power_wndproc_ref = WNDPROC(_wnd_proc)
        h_inst = kernel32.GetModuleHandleW(None)
        cls_name = "MyServerPowerMonitorHiddenWindow"

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = _active_power_wndproc_ref
        wc.hInstance = h_inst
        wc.lpszClassName = cls_name
        user32.RegisterClassExW(ctypes.byref(wc))

        # Hidden top-level window (hwndParent=None, dwStyle=0)
        hwnd = user32.CreateWindowExW(0, cls_name, cls_name, 0, 0, 0, 0, 0, None, None, h_inst, None)
        if not hwnd:
            return

        reg_suspend_fn = getattr(user32, "RegisterSuspendResumeNotification", None)
        if reg_suspend_fn is not None:
            try:
                reg_suspend_fn(hwnd, DEVICE_NOTIFY_WINDOW_HANDLE)
            except Exception:
                pass

        msg_struct = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg_struct), hwnd, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg_struct))
            user32.DispatchMessageW(ctypes.byref(msg_struct))
    except Exception as e:
        logger_manager.log_debug(f"[PowerMonitor] Loop berhenti: {e}")


def windows_network_change_monitor_loop():
    """Memantau perubahan alamat IPv4 lokal via Win32 NotifyAddrChange untuk invalidasi cepat."""
    if sys.platform != "win32":
        return
    prev_ips = _get_local_ipv4_snapshot()
    while True:
        try:
            iphlpapi = ctypes.windll.iphlpapi
            notify_fn = getattr(iphlpapi, "NotifyAddrChange", None)
            if callable(notify_fn):
                notify_fn(None, None)
                time.sleep(1.5)
            else:
                time.sleep(5.0)
        except Exception:
            time.sleep(5.0)
        try:
            cur_ips = _get_local_ipv4_snapshot()
            if _handle_local_network_change(prev_ips, cur_ips):
                prev_ips = cur_ips
        except Exception:
            pass

def update_route_resolver_loop():







    """







    Daemon latar belakang: menguji ketersediaan rute (Auto Route) setiap 10 detik.







    Jika server berpindah dari LAN ke Domain/ZeroTier (atau sebaliknya), cache segera diperbarui







    sehingga UI dan telemetri langsung mengikuti tanpa jeda.







    """







    while True:







        try:







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg)







            eff_url_for_smb = ""
            if srv and srv.get("active_connection", "auto") == "auto":
                url, lbl = config_manager.resolve_target_connection(cfg, check_network=True, target_server=srv)
                eff_url_for_smb = url or ""
                with _cached_active_route["lock"]:
                    _cached_active_route["url"] = url
                    _cached_active_route["label"] = lbl
                    _cached_active_route["last_check"] = time.time()
                    _cached_active_route["server_id"] = srv.get("id")
                    _cached_active_route["active_conn"] = srv.get("active_connection", "auto")
                parsed = urllib.parse.urlparse(url)
                ip_str = parsed.hostname or ""
                route_url_shifted = False
                with _state_lock:
                    if _cached_state.get("ip") != ip_str or _cached_state.get("server_url") != url.rstrip("/"):
                        route_url_shifted = True
                        _cached_state["ip"] = ip_str
                        _cached_state["server_url"] = url.rstrip("/")
                        _cached_state["route_name"] = "LAN Fisik" if "LAN" in lbl else ("ZeroTier P2P" if "ZeroTier" in lbl else "Domain / Internet")
                if route_url_shifted:
                    smb_mount_manager.invalidate_smb_host_cache()
            elif srv:
                eff_url_for_smb, _ = get_active_resolved_route(cfg)

            if srv and eff_url_for_smb:
                with _state_lock:
                    cur_on_smb = bool(_cached_state.get("is_online"))
                _check_effective_smb_host_transition_for_server(
                    srv,
                    eff_url_for_smb,
                    auto_mount_enabled=bool(cfg.get("auto_mount_smb", True)),
                    is_online=cur_on_smb,
                )







        except Exception as e:







            logger_manager.log_debug(f"[RouteResolver] Error in background resolver: {e}")







        with _state_lock:



            cur_online = _cached_state.get("is_online", True)



        time.sleep(3.0 if not cur_online else 8.0)























# ==============================================================================







# SYNTCHING REVOLUTION ENGINE & STATUS WORKER







# ==============================================================================















_syncthing_lock = threading.Lock()







_syncthing_cache = {







    "local": {







        "online": False,







        "device_id": "",







        "devices": [],







        "folders": [],







        "pending_devices": {},







        "metrics": {







            "active": False,







            "direction": "none",







            "percentage": 100.0,







            "completed_files": 0,







            "total_files": 0,







            "errors": 0,







            "in_speed": "0 B/s",







            "out_speed": "0 B/s",







            "state": "Idle",







        },







    },







    "server": {







        "online": False,







        "device_id": "",







        "devices": [],







        "folders": [],







        "pending_devices": {},







        "metrics": {







            "active": False,







            "direction": "none",







            "percentage": 100.0,







            "completed_files": 0,







            "total_files": 0,







            "errors": 0,







            "in_speed": "0 B/s",







            "out_speed": "0 B/s",







            "state": "Idle",







        },







    },







    "daemon": {







        "running": False,







        "port": "8384",







        "has_binary": False,







        "binary_path": "",







    },







    "paired": False,







    "last_update": 0,







}















_active_local_st_client = None







_active_srv_st_client = None







_active_local_st_key = None







_active_srv_st_key = None







_local_st_daemon = syncthing_manager.LocalSyncthingDaemon()























def get_local_syncthing_api_key(cfg=None):







    """Membaca API Key Syncthing lokal dari konfigurasi atau auto-detect dari config.xml."""







    if cfg:







        k = cfg.get("local_syncthing", {}).get("api_key", "").strip()







        if k:







            return k















    possible_paths = [







        os.path.expandvars(r"%LOCALAPPDATA%\Syncthing\config.xml"),







        os.path.expandvars(r"%APPDATA%\Syncthing\config.xml"),







        os.path.join(config_manager.get_base_dir(), "data", "syncthing", "config.xml"),







        os.path.join(config_manager.get_base_dir(), "bin", "syncthing", "config.xml"),







    ]







    for xml_path in possible_paths:







        if os.path.exists(xml_path):







            try:







                import xml.etree.ElementTree as ET







                tree = ET.parse(xml_path)







                key_elem = tree.find(".//apikey")







                if key_elem is not None and key_elem.text and key_elem.text.strip():







                    found_key = key_elem.text.strip()







                    if cfg:







                        cfg.setdefault("local_syncthing", {})["api_key"] = found_key







                        config_manager.save_config(cfg)







                    return found_key







            except Exception:







                pass







    return ""























def parse_speed_to_mbps(speed_str):







    """Mengonversi format kecepatan string Syncthing ke numeric MB/s float."""







    try:







        parts = speed_str.strip().split()







        if len(parts) >= 1:







            val = float(parts[0])







            unit = parts[1].upper() if len(parts) > 1 else "B/S"







            if "KB" in unit:







                return round(val / 1024.0, 2)







            elif "MB" in unit:







                return round(val, 2)







            elif "GB" in unit:







                return round(val * 1024.0, 2)







            elif "B" in unit:







                return round(val / (1024.0 * 1024.0), 3)







    except Exception:







        pass







    return 0.0























def syncthing_status_worker_loop():







    """Worker telemetri latar belakang Syncthing (Laptop & Server). Berjalan tiap 2.5s."""







    global _active_local_st_client, _active_srv_st_client







    global _active_local_st_key, _active_srv_st_key















    while True:







        try:







            cfg = config_manager.load_or_create_config()







            loc_cfg = cfg.get("local_syncthing", {})







            loc_port = loc_cfg.get("port", "8384")







            loc_key = get_local_syncthing_api_key(cfg)







            loc_key_tuple = (str(loc_port).strip(), str(loc_key).strip())















            # 1. Daemon binary detection & running state







            exe_path = _local_st_daemon._detect_syncthing_exe()







            has_binary = bool(exe_path and os.path.exists(exe_path))







            daemon_running = _local_st_daemon.is_running(port=loc_port)



            # Auto-start daemon on startup if configured (default True)

            global _first_st_auto_start_done

            if '_first_st_auto_start_done' not in globals():

                _first_st_auto_start_done = False



            if not _first_st_auto_start_done:

                _first_st_auto_start_done = True

                if has_binary and not daemon_running and loc_cfg.get("auto_start", True):

                    if logger_manager and hasattr(logger_manager, "log_info"):

                        logger_manager.log_info(f"[CoreService] Memulai daemon Syncthing lokal secara otomatis (auto_start: True, port: {loc_port})...")

                    _local_st_daemon.start(custom_port=loc_port)

                    daemon_running = _local_st_daemon.is_running(port=loc_port)















            # 2. Local Syncthing Client







            if _active_local_st_client is None or _active_local_st_key != loc_key_tuple:







                _active_local_st_client = syncthing_manager.SyncthingClient(







                    host="127.0.0.1", port=loc_port, api_key=loc_key







                )







                _active_local_st_key = loc_key_tuple







            loc_client = _active_local_st_client















            loc_online = loc_client.is_online()







            loc_id = ""







            loc_devices = []







            loc_folders = []







            loc_pending = {}







            loc_metrics = {







                "active": False,







                "direction": "none",







                "percentage": 100.0,







                "completed_files": 0,







                "total_files": 0,







                "errors": 0,







                "in_speed": "0 B/s",







                "out_speed": "0 B/s",







                "state": "Idle",







            }















            if loc_online:







                loc_id = loc_client.get_my_id() or ""







                loc_metrics = loc_client.calculate_sync_metrics()







                if loc_key:







                    loc_devices = loc_client.get_devices()







                    loc_folders = loc_client.get_folders()







                    loc_pending = loc_client.get_pending_devices()















            # 3. Server Syncthing Client (Dynamic Routing Aware)







            srv = config_manager.get_active_server(cfg)







            srv_online = False







            srv_id = ""







            srv_devices = []







            srv_folders = []







            srv_pending = {}







            srv_metrics = {







                "active": False,







                "direction": "none",







                "percentage": 100.0,







                "completed_files": 0,







                "total_files": 0,







                "errors": 0,







                "in_speed": "0 B/s",







                "out_speed": "0 B/s",







                "state": "Idle",







            }















            if srv:







                srv_host, srv_port, srv_key, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg)







                if srv_host:







                    srv_key_tuple = (str(srv_host).strip(), str(srv_port).strip(), str(srv_key).strip(), bool(srv_https))







                    if _active_srv_st_client is None or _active_srv_st_key != srv_key_tuple:







                        _active_srv_st_client = syncthing_manager.SyncthingClient(







                            host=srv_host, port=srv_port, api_key=srv_key, use_https=srv_https







                        )







                        _active_srv_st_key = srv_key_tuple







                    srv_client = _active_srv_st_client















                    srv_online = srv_client.is_online()







                    if srv_online:







                        srv_id = srv_client.get_my_id() or ""







                        if srv_key:







                            srv_devices = srv_client.get_devices()







                            srv_folders = srv_client.get_folders()







                            srv_pending = srv_client.get_pending_devices()







                        try:







                            srv_metrics = srv_client.calculate_sync_metrics()







                        except Exception:







                            pass















            # 4. Mutual pairing check







            paired = False







            if loc_id and srv_id:







                loc_has_srv = any(d.get("deviceID") == srv_id for d in loc_devices)







                srv_has_loc = any(d.get("deviceID") == loc_id for d in srv_devices)







                paired = loc_has_srv and srv_has_loc















            # 5. Atomically update _syncthing_cache







            with _syncthing_lock:







                _syncthing_cache["local"] = {







                    "online": loc_online,







                    "device_id": loc_id,







                    "devices": loc_devices,







                    "folders": loc_folders,







                    "pending_devices": loc_pending,







                    "metrics": loc_metrics,







                }







                _syncthing_cache["server"] = {







                    "online": srv_online,







                    "device_id": srv_id,







                    "devices": srv_devices,







                    "folders": srv_folders,







                    "pending_devices": srv_pending,







                    "metrics": srv_metrics,







                }







                _syncthing_cache["daemon"] = {







                    "running": daemon_running,







                    "port": str(loc_port),







                    "has_binary": has_binary,







                    "binary_path": exe_path or "",







                }







                _syncthing_cache["paired"] = paired







                _syncthing_cache["last_update"] = time.time()















            # 6. Salurkan ke _cached_state untuk Mini Tray metrics & header







            active_m = loc_metrics if loc_metrics.get("active") else srv_metrics







            sync_up_mb = parse_speed_to_mbps(active_m.get("out_speed", "0 B/s"))







            sync_down_mb = parse_speed_to_mbps(active_m.get("in_speed", "0 B/s"))







            with _state_lock:







                _cached_state["sync_up"] = sync_up_mb







                _cached_state["sync_down"] = sync_down_mb







                _cached_state["sync_active"] = active_m.get("active", False)







                _cached_state["sync_percentage"] = active_m.get("percentage", 100.0)







                _cached_state["syncthing_pending_count"] = len(loc_pending) + len(srv_pending)







                _cached_state["syncthing_local_online"] = loc_online







                _cached_state["syncthing_server_online"] = srv_online







                _cached_state["syncthing_paired"] = paired















        except Exception as e:







            logger_manager.log_error(f"[SyncthingWorker] Error in status worker loop: {e}")















        time.sleep(2.5)























def get_target_server_for_task(cfg, folder_id, fallback_to_active=True):

    """Mencari dictionary server tujuan untuk task tertentu berdasarkan mapping di config."""

    if not cfg:

        cfg = config_manager.load_or_create_config()

    if not folder_id:

        return config_manager.get_active_server(cfg) if fallback_to_active else None



    explicit_sid = cfg.get("sync_task_servers", {}).get(folder_id)

    if explicit_sid:

        for s in cfg.get("servers", []):

            if isinstance(s, dict) and s.get("id") == explicit_sid:

                return s



    for s in cfg.get("servers", []):

        if isinstance(s, dict) and folder_id in s.get("sync_task_owners", {}):

            return s



    if fallback_to_active:

        return config_manager.get_active_server(cfg)

    return None





def get_syncthing_tasks_list():



    """Mengembalikan daftar jalur backup (Sync Tasks) dengan pemetaan kepemilikan, server target, dan progres."""



    cfg = config_manager.load_or_create_config()



    srv = config_manager.get_active_server(cfg)



    active_srv_id = srv.get("id", "") if srv else ""



    active_srv_name = srv.get("name", "Server Utama") if srv else "Server Utama"



    owners = srv.get("sync_task_owners", {}) if srv else {}







    all_servers = cfg.get("servers", [])



    server_by_name = {}



    for s in all_servers:



        if isinstance(s, dict):



            s_name = s.get("name", "").strip().lower()



            if s_name:



                server_by_name[s_name] = s







    with _syncthing_lock:



        local_folders = list(_syncthing_cache["local"]["folders"])



        server_folders = list(_syncthing_cache["server"]["folders"])



        local_devices = list(_syncthing_cache["local"].get("devices", []))



        active_srv_device_id = _syncthing_cache["server"].get("device_id") or _syncthing_cache["server"].get("my_id", "")



        local_device_id = _syncthing_cache["local"].get("device_id") or _syncthing_cache["local"].get("my_id", "")



        loc_client = _active_local_st_client







    dev_name_map = {}



    for d in local_devices:



        did = d.get("deviceID") or d.get("id")



        dname = d.get("name") or ""



        if did:



            dev_name_map[did] = dname







    server_map = {sf.get("id"): sf for sf in server_folders}



    tasks = []







    for f in local_folders:



        fid = f.get("id")



        if not fid:



            continue



        flabel = f.get("label") or fid



        fpath = f.get("path", "")



        ftype = f.get("type", "sendonly")



        fpaused = f.get("paused", False)







        comp_pct = 100.0



        need_files = 0



        need_bytes = 0



        if loc_client and _syncthing_cache["local"]["online"]:



            try:



                comp = loc_client.get_completion(folder_id=fid)



                comp_pct = round(comp.get("completion", 100.0), 1)



                need_files = comp.get("needFiles", 0)



                need_bytes = comp.get("needBytes", 0)



            except Exception:



                pass







        srv_match = server_map.get(fid, {})



        srv_path = srv_match.get("path", "")

        if not srv_path:

            srv_path = cfg.get("sync_task_server_paths", {}).get(fid, "")



        owner_profile = owners.get(fid, "Semua")







        folder_devs = [d.get("deviceID") or d.get("id") for d in f.get("devices", []) if isinstance(d, dict)]



        remote_dev_ids = [d for d in folder_devs if d and d != local_device_id]







        is_active_server = False



        target_server_name = active_srv_name



        target_server_id = active_srv_id







        target_srv = get_target_server_for_task(cfg, fid, fallback_to_active=False)

        if target_srv:

            target_server_id = target_srv.get("id", "")

            target_server_name = target_srv.get("name", "")

            is_active_server = (target_server_id == active_srv_id)

            owner_profile = target_srv.get("sync_task_owners", {}).get(fid, "Semua")

        elif bool(srv_match) or (active_srv_device_id and active_srv_device_id in remote_dev_ids):

            is_active_server = True

            target_server_name = active_srv_name

            target_server_id = active_srv_id

            owner_profile = owners.get(fid, "Semua")

        else:



            found_other = False



            for rem_did in remote_dev_ids:



                dev_label = dev_name_map.get(rem_did, "")



                if dev_label:



                    match_s = server_by_name.get(dev_label.strip().lower())



                    if match_s:



                        target_server_name = match_s.get("name", dev_label)



                        target_server_id = match_s.get("id", "")



                        is_active_server = (target_server_id == active_srv_id)



                        found_other = True



                        break



                    else:



                        target_server_name = dev_label



                        target_server_id = ""



                        is_active_server = False



                        found_other = True



                        break



            if not found_other:



                if len(all_servers) <= 1:



                    is_active_server = True



                    target_server_name = active_srv_name



                    target_server_id = active_srv_id



                else:



                    is_active_server = False



                    target_server_name = "Server Lain"



                    target_server_id = ""







        tasks.append({



            "id": fid,



            "label": flabel,



            "localPath": fpath,



            "serverPath": srv_path,



            "type": ftype,



            "paused": fpaused,



            "completion": comp_pct,



            "needFiles": need_files,



            "needBytes": need_bytes,



            "owner": owner_profile,



            "existsOnServer": bool(srv_match) or bool(srv_path) or (fid in cfg.get("sync_task_servers", {})),



            "isActiveServer": is_active_server,



            "targetServerName": target_server_name,



            "targetServerId": target_server_id,



        })







    return tasks























def create_sync_task_route(local_path="", task_label="", server_path="", sync_mode="sendonly", target_server_id=None):







    """Membuat jalur backup baru menghubungkan direktori laptop ke server dengan auto-.stignore."""







    try:







        cfg = config_manager.load_or_create_config()







        cur_l = cfg.get("language", "en")



        srv = None

        if target_server_id:

            for s in cfg.get("servers", []):

                if isinstance(s, dict) and s.get("id") == target_server_id:

                    srv = s

                    break

        if not srv:

            srv = config_manager.get_active_server(cfg)

        if not srv:

            return {"success": False, "error": "Server tujuan tidak ditemukan atau tidak aktif."}















        loc_cfg = cfg.get("local_syncthing", {})







        loc_key = get_local_syncthing_api_key(cfg)







        srv_host, srv_port, srv_key, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg)















        if not loc_key:







            return {"success": False, "error": "REST API Key Syncthing Laptop belum tersedia. Pastikan Syncthing lokal sudah menyala."}







        if not srv_key or not srv_host:







            return {"success": False, "error": "REST API Key Syncthing Server belum dikonfigurasi. Silakan klik tombol 'API Server' di atas untuk memasukkan REST API Key."}















        loc_client = syncthing_manager.SyncthingClient("127.0.0.1", loc_cfg.get("port", "8384"), loc_key)







        srv_client = syncthing_manager.SyncthingClient(srv_host, srv_port, srv_key, use_https=srv_https)















        if not loc_client.is_online():







            return {"success": False, "error": "Syncthing Laptop lokal sedang offline. Silakan nyalakan daemon lokal terlebih dahulu."}







        if not srv_client.is_online():







            return {"success": False, "error": f"Syncthing Server ({srv_host}:{srv_port}) tidak merespons. Pastikan Syncthing di server ZimaOS aktif."}















        sel_folder = (local_path or "").strip()







        if not sel_folder:







            sel_folder = dialog_helper.prompt_choose_folder(







                "Pilih Folder di Laptop yang Ingin Dicadangkan ke Server" if cur_l == "id" else "Select Local Folder to Backup to Server"







            )







            if not sel_folder or not os.path.exists(sel_folder):







                return {"cancelled": True}















        if not os.path.exists(sel_folder):







            return {"success": False, "error": f"Direktori lokal '{sel_folder}' tidak ditemukan di Laptop."}















        folder_name = os.path.basename(os.path.normpath(sel_folder)) or "Backup"







        slug_id = re.sub(r'[^a-zA-Z0-9_-]', '', folder_name.lower().replace(' ', '-'))







        if not slug_id:







            slug_id = "backup"







        final_id = f"task-{slug_id}-{int(time.time()) % 10000}"















        if not task_label:







            task_label = folder_name







        if not server_path:







            server_path = f"/DATA/Backups/{folder_name}"















        if sync_mode == "sendonly":







            loc_type = "sendonly"







            srv_type = "receiveonly"







            mode_desc = "Mirroring (Send Only)"







        else:







            loc_type = "sendreceive"







            srv_type = "sendreceive"







            mode_desc = "2-Way (Send & Receive)"















        # Tulis perlindungan .stignore default







        stignore_path = os.path.join(sel_folder, ".stignore")







        if not os.path.exists(stignore_path):







            try:







                default_ignore = (







                    "(?d)(?i)desktop.ini\n"







                    "(?d)(?i)thumbs.db\n"







                    "(?d)(?i)$recycle.bin\n"







                    "(?d)(?i)System Volume Information\n"







                    "(?d)(?i).DS_Store\n"







                    "(?d)(?i)*.tmp\n"







                    "(?d)(?i)~*\n"







                )







                with open(stignore_path, "w", encoding="utf-8") as f_ign:







                    f_ign.write(default_ignore)







            except Exception:







                pass















        laptop_id = loc_client.get_my_id()







        server_id = srv_client.get_my_id()







        if not laptop_id or not server_id:







            return {"success": False, "error": "Gagal membaca Device ID Syncthing dari Laptop atau Server."}















        loc_client.add_device(server_id, srv.get("name", "Server"))







        srv_client.add_device(laptop_id, "Laptop")















        clean_local_path = os.path.normpath(sel_folder).replace("\\", "/")







        clean_server_path = server_path.rstrip("/")















        ok_loc = loc_client.add_folder(final_id, task_label, clean_local_path, folder_type=loc_type, remote_device_ids=[server_id])







        ok_srv = srv_client.add_folder(final_id, task_label, clean_server_path, folder_type=srv_type, remote_device_ids=[laptop_id])

















        if not ok_srv:

            try:

                for _ in range(6):

                    time.sleep(1.5)

                    c_f, b_f = srv_client._send_request(f"/rest/config/folders/{urllib.parse.quote(final_id)}", method="GET", timeout=6.0)

                    if c_f == 200 and isinstance(b_f, dict) and b_f.get("id") == final_id:

                        ok_srv = True

                        break

            except Exception:

                pass

        if not ok_loc:

            try:

                for _ in range(5):

                    time.sleep(1.0)

                    c_f, b_f = loc_client._send_request(f"/rest/config/folders/{urllib.parse.quote(final_id)}", method="GET", timeout=5.0)

                    if c_f == 200 and isinstance(b_f, dict) and b_f.get("id") == final_id:

                        ok_loc = True

                        break

            except Exception:

                pass



        if ok_loc and ok_srv:







            try:







                fresh_cfg = config_manager.load_or_create_config()







                target_id = srv.get("id") if srv else target_server_id

                s_cur = None

                if target_id:

                    for s in fresh_cfg.get("servers", []):

                        if isinstance(s, dict) and s.get("id") == target_id:

                            s_cur = s

                            break

                    fresh_cfg.setdefault("sync_task_servers", {})[final_id] = target_id

                    fresh_cfg.setdefault("sync_task_server_paths", {})[final_id] = clean_server_path

                if not s_cur:

                    s_cur = config_manager.get_active_server(fresh_cfg)







                if s_cur:







                    act_p = s_cur.get("active_profile", "Admin")







                    task_owners = s_cur.setdefault("sync_task_owners", {})







                    task_owners[final_id] = act_p







                    config_manager.save_config(fresh_cfg)







            except Exception:







                pass















            loc_client.force_rescan()







            srv_client.force_rescan()







            logger_manager.log_info(f"[Syncthing] Jalur [{mode_desc}] '{task_label}' berhasil dibuat! Sinkronisasi dimulai.")







            return {"success": True, "task_id": final_id, "label": task_label, "mode": mode_desc}







        else:







            return {"success": False, "error": f"Gagal mendaftarkan folder ke Syncthing (Laptop: {ok_loc}, Server: {ok_srv})."}







    except Exception as exc:







        logger_manager.log_error(f"[Syncthing] Gagal membuat jalur backup: {traceback.format_exc()}")







        return {"success": False, "error": f"Gagal membuat jalur backup: {str(exc)}"}























def prompt_local_syncthing_setup(cfg=None):







    """Membuka dialog konfigurasi port dan API Key Syncthing laptop lokal."""







    if cfg is None:







        cfg = config_manager.load_or_create_config()







    cur_l = cfg.get("language", "en")







    loc_cfg = cfg.setdefault("local_syncthing", {"enabled": True, "port": "8384", "api_key": "", "auto_start": True})















    title = "Local Syncthing (Laptop)" if cur_l == "en" else "Syncthing Lokal (Laptop)"







    msg = (







        "Configure local port and REST API Key (Optional, can be configured later):"







        if cur_l == "en"







        else "Konfigurasi port lokal dan API Key REST (Opsional, dapat diisi nanti):"







    )







    lbl1 = "Local Port (default: 8384):" if cur_l == "en" else "Port Lokal (default: 8384):"







    lbl2 = "API Key:" if cur_l == "en" else "API Key:"















    res = dialog_helper.run_powershell_dialog("two_inputs", title, msg, lbl1, loc_cfg.get("port", "8384"), lbl2, loc_cfg.get("api_key", ""))







    if res.get("status") == "ok":







        loc_cfg["port"] = res.get("val1", "").strip() or "8384"







        loc_cfg["api_key"] = res.get("val2", "").strip()







        config_manager.save_config(cfg)







        



        _active_local_st_client = None







        _active_local_st_key = None







        logger_manager.log_info(f"[Syncthing] API Key Laptop berhasil diperbarui (Port: {loc_cfg['port']}).")







        return True







    return False























def prompt_backup_app_setup(srv_target=None):







    """Membuka dialog konfigurasi rute ganda dan API Key Syncthing Server."""







    cfg = config_manager.load_or_create_config()







    cur_l = cfg.get("language", "en")







    srv = srv_target if srv_target else config_manager.get_active_server(cfg)







    if not srv:







        return False







    srv_name = srv.get("name", "Server")







    b_app = srv.setdefault(







        "backup_app",







        {







            "route_mode": "auto",







            "lan_mode": "inherit",







            "lan_ip": "",







            "lan_port": "8384",







            "wan_url": "",







            "api_key": "",







        },







    )







    title = (







        f"Configure Remote Backup ({srv_name})"







        if cur_l == "en"







        else f"Konfigurasi Backup Server ({srv_name})"







    )







    cur_route_mode = b_app.get("route_mode", "auto")







    cur_lan_mode = b_app.get("lan_mode", "inherit")







    cur_lan_ip = b_app.get("lan_ip", "")







    cur_lan_port = str(b_app.get("lan_port", "8384")) or "8384"







    cur_wan_url = b_app.get("wan_url", "")







    cur_key = b_app.get("api_key", "")















    res = dialog_helper.run_powershell_dialog(







        "config_backup_dual_dialog",







        title,







        srv_name,







        cur_lan_mode,







        cur_lan_ip,







        cur_lan_port,







        cur_wan_url,







        cur_key,







        cur_route_mode,







    )







    if res.get("status") == "ok":







        b_app["route_mode"] = res.get("routeMode", "auto")







        b_app["lan_mode"] = res.get("lanMode", "inherit")







        b_app["lan_ip"] = res.get("lanIp", "").strip()







        b_app["lan_port"] = res.get("lanPort", "").strip() or "8384"







        b_app["wan_url"] = res.get("wanUrl", "").strip()







        b_app["api_key"] = res.get("apiKey", "").strip()







        config_manager.save_config(cfg)







        



        _active_srv_st_client = None







        _active_srv_st_key = None







        logger_manager.log_info(f"[Syncthing] API Key Server berhasil diperbarui ({srv_name}: {b_app['lan_port']}).")







        return True







    return False























def execute_backup_dialog(target_file=""):







    """Membuat arsip backup konfigurasi dan data aplikasi yang bersih tanpa cache browser."""







    cur_l = config_manager.load_or_create_config().get("language", "en")







    now_str = time.strftime("%Y%m%d_%H%M%S")







    default_name = f"MyServer_Backup_{now_str}.zip"







    dest_zip = target_file







    if not dest_zip:







        title = "Save Application Backup" if cur_l == "en" else "Simpan Cadangan Data Aplikasi"







        res = dialog_helper.run_powershell_dialog("save_zip", title, default_name)







        if res.get("status") != "ok" or not res.get("file"):







            return {"cancelled": True}







        dest_zip = res["file"]















    base_dir = config_manager.get_base_dir()







    cfg_file = os.path.join(base_dir, "config.json")







    data_dir = os.path.join(base_dir, "data")















    try:







        with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:







            if os.path.exists(cfg_file):







                zf.write(cfg_file, "config.json")







            if os.path.exists(data_dir):







                for root, dirs, files in os.walk(data_dir):







                    rel_root = os.path.relpath(root, base_dir)







                    if "EBWebView" in rel_root or "__pycache__" in rel_root:







                        continue







                    for f in files:







                        if f.endswith((".tmp", ".log", ".lock", ".dmp")):







                            continue







                        full_p = os.path.join(root, f)







                        rel_p = os.path.relpath(full_p, base_dir)







                        try:







                            zf.write(full_p, rel_p)







                        except Exception:







                            pass







        logger_manager.log_info(f"[Backup] Cadangan berhasil disimpan ke {dest_zip}")







        return {"success": True, "file": os.path.basename(dest_zip), "path": dest_zip}







    except Exception as e:







        logger_manager.log_error(f"[Backup] Gagal membuat cadangan: {e}")







        return {"success": False, "error": str(e)}























def execute_restore_dialog(target_file=""):







    """Memvalidasi dan memulihkan data aplikasi dari arsip ZIP dengan proteksi .bak otomatis."""







    cur_l = config_manager.load_or_create_config().get("language", "en")







    backup_zip = target_file







    if not backup_zip:







        title = "Select MyServer Backup File (.zip)" if cur_l == "en" else "Pilih Berkas Cadangan MyServer (.zip)"







        res = dialog_helper.run_powershell_dialog("choose_zip", title)







        if res.get("status") != "ok" or not res.get("file"):







            return {"cancelled": True}







        backup_zip = res["file"]















    if not os.path.exists(backup_zip) or not zipfile.is_zipfile(backup_zip):







        return {"success": False, "error": "Berkas yang dipilih bukan berkas ZIP yang valid."}















    cfg_entry = None







    try:







        with zipfile.ZipFile(backup_zip, "r") as zf:







            for n in zf.namelist():







                if n == "config.json" or n.endswith("/config.json") or n.endswith("\\config.json"):







                    cfg_entry = n







                    break







    except Exception as e:







        return {"success": False, "error": f"Gagal membaca arsip ZIP: {e}"}















    if not cfg_entry:







        return {"success": False, "error": "Berkas cadangan tidak valid (config.json tidak ditemukan)."}















    # 1. Validasi integritas format config.json







    try:







        with zipfile.ZipFile(backup_zip, "r") as zf:







            raw_cfg_bytes = zf.read(cfg_entry)







            new_cfg_obj = json.loads(raw_cfg_bytes.decode("utf-8"))







        if not isinstance(new_cfg_obj, dict):







            raise ValueError("Format config.json bukan JSON Object yang valid.")







    except Exception as e:







        return {"success": False, "error": f"Berkas config.json dalam cadangan rusak: {e}"}















    # 2. Konfirmasi pemulihan pengguna







    confirm_title = "Confirm Restore" if cur_l == "en" else "Konfirmasi Pemulihan"







    confirm_msg = (







        "Restore all data from this backup?\n\n• Server settings and accounts will be restored.\n• Existing sessions and data will be overwritten.\n• The application will restart automatically."







        if cur_l == "en"







        else "Pulihkan seluruh data dari cadangan ini?\n\n• Pengaturan server dan seluruh akun akan dipulihkan.\n• Sesi login dan data yang ada saat ini akan ditimpa.\n• Aplikasi akan ditutup dan dibuka ulang secara otomatis."







    )







    if not dialog_helper.prompt_confirm(confirm_title, confirm_msg):







        return {"cancelled": True}















    app_dir = config_manager.get_base_dir()







    cfg_path = os.path.join(app_dir, "config.json")







    bak_path = os.path.join(app_dir, "config.json.bak")















    try:







        # 3. Amankan backup lokal config.json saat ini







        if os.path.exists(cfg_path):







            shutil.copy2(cfg_path, bak_path)















        # 4. Tulis config.json baru secara atomik







        with open(cfg_path, "w", encoding="utf-8") as f:







            json.dump(new_cfg_obj, f, indent=4)







            f.flush()







            os.fsync(f.fileno())















        # 5. Ekstrak data non-cache







        with zipfile.ZipFile(backup_zip, "r") as zf:







            for member in zf.infolist():







                m_name = member.filename







                if m_name == cfg_entry or "EBWebView" in m_name or m_name.endswith(("/", "\\")):







                    continue







                clean_m = os.path.normpath(m_name).lstrip("/\\")







                if clean_m.startswith(".."):







                    continue







                dest_path = os.path.join(app_dir, clean_m)







                try:







                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)







                    with zf.open(member) as s_file, open(dest_path, "wb") as d_file:







                        shutil.copyfileobj(s_file, d_file)







                except Exception:







                    pass















        logger_manager.log_info("[Restore] Berhasil memulihkan data. Menjadwalkan restart aplikasi...")















        # 6. Detached restart







        def _restart_soon():







            time.sleep(1.0)







            try:







                exe_path = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)







                creationflags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0







                if getattr(sys, "frozen", False):







                    subprocess.Popen([exe_path], cwd=app_dir, creationflags=creationflags)







                else:







                    subprocess.Popen([sys.executable, exe_path], cwd=app_dir, creationflags=creationflags)







            except Exception as e:







                logger_manager.log_error(f"[Restore] Gagal restart: {e}")







            os._exit(0)















        threading.Thread(target=_restart_soon, daemon=True).start()







        return {"success": True, "rollbackFile": "config.json.bak", "restarting": True}







    except Exception as err:







        logger_manager.log_error(f"[Restore] Gagal memulihkan cadangan: {err}")







        return {"success": False, "error": str(err)}























class MIB_IF_ROW2(ctypes.Structure):







    _fields_ = [







        ("InterfaceLuid", ctypes.c_uint64),







        ("InterfaceIndex", wintypes.DWORD),







        ("InterfaceGuid", ctypes.c_byte * 16),







        ("Alias", wintypes.WCHAR * 257),







        ("Description", wintypes.WCHAR * 257),







        ("PhysicalAddressLength", wintypes.DWORD),







        ("PhysicalAddress", ctypes.c_byte * 32),







        ("PermanentPhysicalAddress", ctypes.c_byte * 32),







        ("Mtu", wintypes.DWORD),







        ("Type", wintypes.DWORD),







        ("TunnelType", ctypes.c_int),







        ("MediaType", ctypes.c_int),







        ("PhysicalMediumType", ctypes.c_int),







        ("AccessType", ctypes.c_int),







        ("DirectionType", ctypes.c_int),







        ("InterfaceAndOperStatusFlags", ctypes.c_byte),







        ("OperStatus", ctypes.c_int),







        ("AdminStatus", ctypes.c_int),







        ("MediaConnectState", ctypes.c_int),







        ("NetworkGuid", ctypes.c_byte * 16),







        ("ConnectionType", ctypes.c_int),







        ("TransmitLinkSpeed", ctypes.c_uint64),







        ("ReceiveLinkSpeed", ctypes.c_uint64),







        ("InOctets", ctypes.c_uint64),







        ("InUcastPkts", ctypes.c_uint64),







        ("InNUcastPkts", ctypes.c_uint64),







        ("InDiscards", ctypes.c_uint64),







        ("InErrors", ctypes.c_uint64),







        ("InUnknownProtos", ctypes.c_uint64),







        ("InUcastOctets", ctypes.c_uint64),







        ("InMulticastOctets", ctypes.c_uint64),







        ("InBroadcastOctets", ctypes.c_uint64),







        ("OutOctets", ctypes.c_uint64),







        ("OutUcastPkts", ctypes.c_uint64),







        ("OutNUcastPkts", ctypes.c_uint64),







        ("OutDiscards", ctypes.c_uint64),







        ("OutErrors", ctypes.c_uint64),







        ("OutUcastOctets", ctypes.c_uint64),







        ("OutMulticastOctets", ctypes.c_uint64),







        ("OutBroadcastOctets", ctypes.c_uint64),







        ("OutQLen", ctypes.c_uint64),







    ]























class MIB_IF_TABLE2(ctypes.Structure):







    _fields_ = [("NumEntries", wintypes.ULONG)]























def get_network_speeds():







    """Mengembalikan (download_kb_s, upload_kb_s) via Windows GetIfTable2 (64-bit modern Vista-Win11 API)."""







    global _last_net_bytes, _last_speed_result







    if sys.platform != "win32":







        return 0.0, 0.0















    try:







        table_ptr = ctypes.POINTER(MIB_IF_TABLE2)()







        if ctypes.windll.iphlpapi.GetIfTable2(ctypes.byref(table_ptr)) != 0:







            return _last_speed_result















        num = table_ptr.contents.NumEntries







        row_size = ctypes.sizeof(MIB_IF_ROW2)







        base_addr = ctypes.cast(table_ptr, ctypes.c_void_p).value + 8







        tot_in = 0







        tot_out = 0















        for i in range(num):







            row = MIB_IF_ROW2.from_address(base_addr + i * row_size)







            flags = row.InterfaceAndOperStatusFlags







            filter_if = (flags >> 1) & 1







            # OperStatus == 1 (IfOperStatusUp), bukan filter interface, dan tipe ethernet (6) atau 802.11 WiFi (71)







            if row.OperStatus == 1 and filter_if == 0 and (row.Type in (6, 71)):







                if not row.Description.startswith("WAN Miniport"):







                    tot_in += row.InOctets







                    tot_out += row.OutOctets















        ctypes.windll.iphlpapi.FreeMibTable(table_ptr)















        now = time.time()







        if _last_net_bytes["time"] > 0 and now > _last_net_bytes["time"]:







            dt = now - _last_net_bytes["time"]







            diff_in = max(0, tot_in - _last_net_bytes["in"]) / dt / 1024.0







            diff_out = max(0, tot_out - _last_net_bytes["out"]) / dt / 1024.0







            _last_speed_result = (round(diff_in, 1), round(diff_out, 1))















        _last_net_bytes = {"in": tot_in, "out": tot_out, "time": now}







        return _last_speed_result







    except Exception as e:







        logger_manager.log_error(f"[CoreService] Gagal menghitung kecepatan jaringan: {e}")







    return _last_speed_result































# ----------------------------------------------------------------------







# Background In-Memory SMB Drive Cache (Optimasi Latensi 0 ms)







# ----------------------------------------------------------------------







_backend_disks_usage_lock = threading.Lock()
_cached_backend_disks_usage = {}


def _update_backend_disks_usage_cache(server_id, disks_list):
    """Menyimpan cache kapasitas REST (/api/v1/storage/disks) untuk _scan_live_drives_now() tanpa probe Win32 SMB."""
    if not disks_list or not isinstance(disks_list, list):
        return
    now_ts = time.time()
    sid = str(server_id or "").strip()
    with _backend_disks_usage_lock:
        for d in disks_list:
            if not isinstance(d, dict):
                continue
            d_name = str(d.get("name") or "").strip().lower()
            if not d_name:
                continue
            tot_b = int(d.get("total_bytes", 0) or 0)
            used_b = int(d.get("used_bytes", 0) or 0)
            raw_free = d.get("free_bytes", None)
            free_b = int(raw_free) if raw_free is not None else max(tot_b - used_b, 0)
            if tot_b > 0:
                _cached_backend_disks_usage[(sid, d_name)] = (tot_b, max(free_b, 0), now_ts)


def _unpack_explorer_result(res):
    """Menormalkan kembalian open_drive_in_explorer / open_unc_root_in_explorer menjadi tuple (ok, msg)."""
    if isinstance(res, tuple):
        ok = bool(res[0]) if len(res) > 0 else False
        msg = str(res[1] or "") if len(res) > 1 else ""
        return ok, msg
    return bool(res), ""


def _scan_live_drives_now():







    """Memindai seluruh drive huruf Windows secara komprehensif."""







    drives = []



    seen_shares = set()

    smb_cfg_scan = {"source": "zimaos", "allowed_disks": []}
    try:
        cfg_scan = config_manager.load_or_create_config() if config_manager else {}
        srv_scan = config_manager.get_active_server(cfg_scan) if config_manager else None
        if srv_scan and hasattr(config_manager, "get_server_smb_source_config"):
            smb_cfg_scan = config_manager.get_server_smb_source_config(srv_scan)
    except Exception:
        pass







    if sys.platform == "win32":



        with _state_lock:



            srv_online = bool(_cached_state.get("is_online", False))



            cached_parts = list(_cached_state.get("storage_partitions", []) or [])







        # Kumpulkan identitas server aktif & server lain secara dinamis (Nol Hardcode)



        active_server_identities = set()



        other_server_identities = set()



        try:



            cfg = config_manager.load_or_create_config()



            srv = config_manager.get_active_server(cfg)



            if srv:



                active_server_identities.add("127.0.0.1")



                active_server_identities.add("localhost")



                if srv.get("name"):



                    active_server_identities.add(str(srv["name"]).strip().lower())



                if srv.get("zerotier_virtual_ip"):



                    active_server_identities.add(str(srv["zerotier_virtual_ip"]).strip().lower())



                if srv.get("easytier_virtual_ip"):



                    active_server_identities.add(str(srv["easytier_virtual_ip"]).strip().lower())



                for c in srv.get("connections", []):



                    if isinstance(c, dict) and c.get("url"):



                        h = c["url"].replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()



                        if h:



                            active_server_identities.add(h)



                try:



                    active_u, _ = get_active_resolved_route(cfg)



                    if active_u:



                        h = active_u.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()



                        if h:



                            active_server_identities.add(h)



                except Exception:



                    pass







                for other_srv in cfg.get("servers", []):



                    if isinstance(other_srv, dict) and other_srv.get("id") != srv.get("id"):



                        if other_srv.get("name"):



                            other_server_identities.add(str(other_srv["name"]).strip().lower())



                        if other_srv.get("zerotier_virtual_ip"):



                            other_server_identities.add(str(other_srv["zerotier_virtual_ip"]).strip().lower())



                        if other_srv.get("easytier_virtual_ip"):



                            other_server_identities.add(str(other_srv["easytier_virtual_ip"]).strip().lower())



                        for c in other_srv.get("connections", []):



                            if isinstance(c, dict) and c.get("url"):



                                h = c["url"].replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()



                                if h:



                                    other_server_identities.add(h)



        except Exception as e:
            logger_manager.log_debug(f"[LiveDrives] Gagal mengumpulkan identitas server: {e}")

        try:
            alias_fn = getattr(smb_mount_manager, "get_active_1219_aliases", None)
            aliases_1219 = alias_fn() if callable(alias_fn) else {}
            for av in (aliases_1219 or {}).values():
                if av and str(av).strip():
                    active_server_identities.add(str(av).strip().lower())
        except Exception:
            pass

        logical_bitmask = 0xFFFFFFFF
        try:
            get_drv_fn = getattr(ctypes.windll.kernel32, "GetLogicalDrives", None)
            if callable(get_drv_fn):
                raw_mask = get_drv_fn()
                if isinstance(raw_mask, int) and not isinstance(raw_mask, bool):
                    logical_bitmask = raw_mask
        except Exception:
            logical_bitmask = 0xFFFFFFFF

        for i in range(25, 2, -1):
            if not (logical_bitmask & (1 << i)):
                continue
            d = f"{chr(65 + i)}:"
            try:
                if ctypes.windll.kernel32.GetDriveTypeW(d + "\\") == 4:







                    buf = ctypes.create_unicode_buffer(512)







                    size = ctypes.c_ulong(512)







                    res = ctypes.windll.mpr.WNetGetConnectionW(d, buf, ctypes.byref(size))







                    unc = buf.value if res == 0 else ""







                    clean_unc = unc.replace("/", "\\").rstrip("\\")







                    # Filter identitas server aktif: abaikan drive milik server lain



                    if clean_unc.startswith("\\\\"):



                        unc_parts = clean_unc.lstrip("\\").split("\\")



                        unc_host = unc_parts[0].strip().lower() if unc_parts else ""



                        if unc_host:



                            if other_server_identities and unc_host in other_server_identities and unc_host not in active_server_identities:



                                continue



                            if active_server_identities and unc_host not in active_server_identities:



                                is_zt = zerotier_manager.is_zerotier_ip(unc_host) if hasattr(zerotier_manager, "is_zerotier_ip") else False



                                if not is_zt:



                                    continue







                    share_name = clean_unc.split("\\")[-1] if "\\" in clean_unc else (clean_unc or f"Share {d}")



                    share_key = share_name.strip().lower()

                    if smb_cfg_scan.get("source") == "backend":
                        scan_role = str(smb_cfg_scan.get("role") or "user").strip().lower()
                        allowed_scan_keys = {
                            str(x).strip().lower()
                            for x in (smb_cfg_scan.get("allowed_disks") or [])
                            if str(x).strip()
                        }
                        if (allowed_scan_keys or scan_role not in ("admin", "root")) and share_key not in allowed_scan_keys:
                            continue

                    if share_key in seen_shares:



                        continue







                    tot = 0
                    fr = 0
                    if smb_cfg_scan.get("source") == "backend":
                        scan_srv_id = str((srv_scan or {}).get("id") or "").strip()
                        with _backend_disks_usage_lock:
                            b_ent = _cached_backend_disks_usage.get((scan_srv_id, share_key))
                            if b_ent and len(b_ent) >= 2:
                                tot, fr = int(b_ent[0]), int(b_ent[1])
                    else:
                        for cp in cached_parts:
                            if not isinstance(cp, dict):
                                continue
                            cp_raw = str(cp.get("raw_name") or cp.get("name") or "").strip().lower()
                            cp_drv = str(cp.get("drive_letter") or "").strip().upper()
                            if (cp_drv == d or cp_raw == share_key or cp_raw.startswith(share_key + " (")) and int(cp.get("total_bytes", 0)) > 0:
                                tot = int(cp.get("total_bytes", 0))
                                used_b = int(cp.get("used_bytes", 0))
                                fr = max(tot - used_b, 0)
                                break







                    used_pct = int(round(((tot - fr) / tot) * 100)) if tot > 0 else 0



                    seen_shares.add(share_key)







                    drives.append({







                        "letter": chr(65 + i),







                        "name": share_name,







                        "free": format_bytes_size(fr),







                        "total": format_bytes_size(tot),







                        "usedPct": used_pct,







                        "mounted": True,







                        "totalBytes": tot,







                        "usedBytes": max(tot - fr, 0),







                    })







            except Exception:







                pass







    if smb_cfg_scan.get("source") == "backend":
        try:
            used_letters = {
                str(item.get("letter", "")).rstrip(":").upper()
                for item in drives
                if isinstance(item, dict)
            }
            avail_pool = [
                str(lt).rstrip(":").upper()
                for lt in (smb_mount_manager.get_available_drive_letters() or [])
                if str(lt).rstrip(":").upper() not in used_letters
            ]
            for disk_name in (smb_cfg_scan.get("allowed_disks") or []):
                d_clean = str(disk_name).strip()
                if not d_clean:
                    continue
                d_key = d_clean.lower()
                if d_key in seen_shares:
                    continue
                seen_shares.add(d_key)
                next_letter = avail_pool.pop(0) if avail_pool else "–"
                if next_letter != "–":
                    used_letters.add(next_letter)
                drives.append({
                    "letter": next_letter,
                    "name": d_clean,
                    "free": "–",
                    "total": "–",
                    "usedPct": 0,
                    "mounted": False,
                })
        except Exception:
            pass

    if not drives:







        try:







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg)







            avail_letter = smb_mount_manager.get_available_drive_letter() or "Z"



            srv_name = srv.get("name", "") if srv else ""



            display_name = srv_name or (config_manager.t("primary_storage", cfg.get("language", "en")) if hasattr(config_manager, "t") else "Storage")



            drives.append({







                "letter": avail_letter,







                "name": display_name,







                "free": "–",







                "total": "–",







                "usedPct": 0,







                "mounted": False







            })







        except Exception:







            pass







    return drives























def update_drives_cache_loop():







    """Latar belakang daemon: memperbarui cache drive memori setiap 6 detik tanpa memblokir request UI."""







    global _cached_live_drives







    # Scan langsung di startup







    try:







        init_drives = _scan_live_drives_now()







        with _drives_cache_lock:







            _cached_live_drives = init_drives







    except Exception:







        pass















    while True:







        try:







            time.sleep(6)







            new_drives = _scan_live_drives_now()







            with _drives_cache_lock:







                _cached_live_drives = new_drives







        except Exception as e:







            logger_manager.log_debug(f"[CoreService] Cache update error: {e}")























def refresh_drives_cache_immediately():







    """Trigger update cache segera di background thread."""







    def _run():







        global _cached_live_drives







        try:







            time.sleep(0.3)







            new_drives = _scan_live_drives_now()







            with _drives_cache_lock:







                _cached_live_drives = new_drives







        except Exception:







            pass







    threading.Thread(target=_run, daemon=True).start()























def get_live_drives_list(force=False):







    """Mengembalikan daftar drive SMB remote langsung dari cache RAM (latensi 0 ms)."""







    global _cached_live_drives



    if not force:



        with _drives_cache_lock:



            if _cached_live_drives:



                return list(_cached_live_drives)



    new_drives = _scan_live_drives_now()



    with _drives_cache_lock:



        _cached_live_drives = new_drives



    return list(new_drives)























def get_primary_mounted_share():







    """Mengembalikan (share_name, drive_letter) untuk partisi SMB utama yang terpasang."""







    drives = get_live_drives_list()







    for d in drives:







        if d.get("mounted"):







            return d.get("name"), f"{d.get('letter')}:"







    return None, None























_smb_pipeline_lock = threading.Lock()



_pending_rebind_lock = threading.Lock()



_pending_rebind_reason = None











_last_zt_sync_times = {}



_zt_sync_lock = threading.Lock()











def sync_server_zerotier_ip(server_id, client=None):



    """



    Menemukan dan menyinkronkan zerotier_virtual_ip untuk server tertentu dari REST API ZimaOS



    (/v2/zimaos/zt/info). 100% Murni Dinamis - Zero Hardcoded.



    Aman, non-blocking, dengan throttle 10 menit jika sudah memiliki IP.



    """



    global _last_zt_sync_times



    if not server_id:



        return ""







    cfg = config_manager.load_or_create_config()



    target_srv = None



    for s in cfg.get("servers", []):



        if isinstance(s, dict) and s.get("id") == server_id:



            target_srv = s



            break







    if not target_srv:



        return ""







    cur_vip = (target_srv.get("zerotier_virtual_ip") or "").strip()



    cur_nwid = (target_srv.get("zerotier_network_id") or target_srv.get("remote_id") or "").strip().lower()



    now = time.time()







    with _zt_sync_lock:



        last_t = _last_zt_sync_times.get(server_id, 0)



        if cur_vip and (now - last_t < 600.0):



            return cur_vip







    metrics_client = client



    if metrics_client is None:



        try:



            active_u, _ = get_active_resolved_route(cfg)



            metrics_client = get_cached_metrics_client(target_srv, active_u)



        except Exception:



            pass







    if metrics_client is None:



        return cur_vip







    try:



        if hasattr(metrics_client, "is_server_reachable") and not metrics_client.is_server_reachable():



            return cur_vip







        info = metrics_client.fetch_zerotier_network_info()



        if not info or not isinstance(info, dict):



            return cur_vip







        remote_nwid = str(info.get("network_id", "")).strip().lower()



        remote_ip = str(info.get("remote_ipv4", "")).strip()







        valid_ip = False



        if remote_ip:



            try:



                ip_obj = ipaddress.ip_address(remote_ip)



                if isinstance(ip_obj, ipaddress.IPv4Address) and not ip_obj.is_loopback:



                    valid_ip = True



            except ValueError:



                valid_ip = False







        updated = False



        if not cur_nwid and remote_nwid and zerotier_manager.validate_network_id(remote_nwid):



            target_srv["zerotier_network_id"] = remote_nwid



            cur_nwid = remote_nwid



            updated = True



        elif cur_nwid and remote_nwid and cur_nwid != remote_nwid:



            logger_manager.log_warning(



                f"[ZeroTier Sync] Remote ID server ({remote_nwid}) berbeda dari konfigurasi lokal ({cur_nwid}). Melewati update IP."



            )



            return cur_vip







        if valid_ip and remote_ip != cur_vip:



            logger_manager.log_info(



                f"[ZeroTier Sync] Server '{target_srv.get('name')}' memperbarui Virtual IP ZeroTier: '{cur_vip}' -> '{remote_ip}'"



            )



            target_srv["zerotier_virtual_ip"] = remote_ip



            cur_vip = remote_ip



            updated = True







        if updated:



            config_manager.save_config(cfg)







        with _zt_sync_lock:



            _last_zt_sync_times[server_id] = now







        return cur_vip



    except Exception as e:



        logger_manager.log_debug(f"[ZeroTier Sync] Catatan sinkronisasi IP: {e}")



        return cur_vip











def _is_domain_or_wan_host(host_str):



    """



    Memeriksa apakah host merupakan Domain FQDN publik atau IP WAN publik



    (memerlukan redirect SMB ke ZeroTier IP karena port 445 diblokir ISP/Cloudflare).



    """



    if not host_str:



        return False



    clean = str(host_str).replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()



    if not clean or clean in ("localhost", "127.0.0.1", "::1") or clean.endswith(".local") or clean.endswith(".lan"):



        return False



    try:



        ip = ipaddress.ip_address(clean)



        if ip.is_loopback:



            return False



        if zerotier_manager.is_zerotier_ip(clean):



            return False



        if ip in ipaddress.ip_network("100.64.0.0/10"):



            return False



        if ip.is_private:



            return False



        return True



    except ValueError:



        return True











def _resolve_smb_route_params(srv, active_u):



    """Mengembalikan tuple (host, is_domain_route, zt_ip) untuk parameter SMB."""



    parsed = urllib.parse.urlparse(active_u) if active_u else None



    host = (parsed.hostname if parsed else "") or "127.0.0.1"



    is_domain = _is_domain_or_wan_host(host)



    zt_ip = get_active_remote_ip(srv) if isinstance(srv, dict) else ""



    return host, is_domain, zt_ip











def rebind_storage_pipeline(reason="manual", force_refresh=True, pre_unmounted=False):







    """Pipeline atomik dan tersinkronisasi untuk Storage SMB:







    1. Unmount seluruh drive SMB aktif (smb_mount_manager.unmount_all_smb_shares).







    2. Deep Purge seluruh sesi kredensial Windows (NET USE \\host /DELETE /Y & WNetCancelConnection2W).







    3. Tunggu 0.5s agar Windows OS melepaskan handle secara bersih.







    4. Ambil kredensial akun aktif baru dari config.json.







    5. Pasang ulang semua share disk ke huruf drive Windows yang tersedia (Z:, Y:, dst.).







    """



    global _pending_rebind_reason



    if not _smb_pipeline_lock.acquire(blocking=False):



        with _pending_rebind_lock:



            _pending_rebind_reason = reason



        logger_manager.log_info(f"[SMB Pipeline] Menjadwalkan ulang pemicu '{reason}' setelah pipeline aktif selesai.")



        return []







    try:







        logger_manager.log_info(f"[SMB Pipeline] Memulai sinkronisasi storage (Pemicu: {reason})...")







        # Pemicu otomatis (boot/pemulihan server) bersifat non-destruktif: drive yang sudah sehat



        # tidak dilepas; mount_all_smb_shares hanya membersihkan drive Red-X & memasang yang belum ada.



        soft_mode = reason in ("startup_auto", "server_recovered")







        if soft_mode:
            logger_manager.log_info("[SMB Pipeline] Mode non-destruktif: drive sehat dipertahankan, hanya melengkapi yang belum terpasang.")
        elif not pre_unmounted:
            unmounted_count = _unmount_myserver_smb_drives(reason=f"pipeline:{reason}", include_easytier_subnet=True)
            logger_manager.log_info(f"[SMB Pipeline] Berhasil melepaskan {unmounted_count} drive lama.")















        cfg = config_manager.load_or_create_config()







        srv = config_manager.get_active_server(cfg)







        if not srv:







            return []















        active_u, _ = get_active_resolved_route(cfg)

        if not soft_mode and not pre_unmounted:
            all_hosts = set()
            for c in srv.get("connections", []):
                if isinstance(c, dict) and c.get("url"):
                    h = c["url"].replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
                    if h:
                        all_hosts.add(h)
            if srv.get("zerotier_virtual_ip"):
                all_hosts.add(str(srv["zerotier_virtual_ip"]).strip())
            if srv.get("easytier_virtual_ip"):
                all_hosts.add(str(srv["easytier_virtual_ip"]).strip())
            if active_u:
                active_h = _extract_host_from_url(active_u)
                if active_h:
                    all_hosts.add(active_h)

            smb_mount_manager.clear_smb_share_cache()
            smb_mount_manager.purge_smb_sessions(all_hosts, notify_explorer=False)
            time.sleep(0.5)















        smb_cfg = config_manager.get_server_smb_source_config(srv)
        smb_source = smb_cfg.get("source", "zimaos")
        conns = srv.get("connections", [])
        host, is_domain, zt_ip = _resolve_smb_route_params(srv, active_u)
        backend_url = ""
        resolved_b_host = ""
        on_token_refreshed_cb = None
        if smb_source == "backend":
            u_val = smb_cfg.get("username", "")
            p_val = smb_cfg.get("password", "")
            auth_token = smb_cfg.get("access_token", "")
            raw_backend_url = _get_active_server_backend_url(cfg, target_server_id=srv.get("id")) or ""
            resolved_b_host = ""
            try:
                resolved_b_host = smb_mount_manager.resolve_smb_host(host, conns, is_domain, zt_ip) or ""
            except Exception:
                resolved_b_host = ""
            if raw_backend_url:
                backend_url = smb_mount_manager._normalize_backend_api_url(
                    raw_backend_url, fallback_host=resolved_b_host
                )
                if (
                    _is_wan_host_safe(_extract_host_from_url(backend_url))
                    and resolved_b_host
                    and not _is_wan_host_safe(resolved_b_host)
                ):
                    backend_url = _format_backend_url(resolved_b_host, 8080)
            elif active_u:
                backend_url = smb_mount_manager._normalize_backend_api_url(
                    active_u, fallback_host=resolved_b_host
                )
            elif resolved_b_host:
                backend_url = _format_backend_url(resolved_b_host, 8080)

            target_srv_id = srv.get("id")
            on_token_refreshed_cb = (
                lambda tok, data, sid=target_srv_id: _persist_refreshed_backend_token(sid, tok, data)
            )
        else:
            act_p = srv.get("active_profile", "Admin")
            creds = config_manager.get_server_credentials(srv, act_p)
            u_val = creds.get("username", "")
            p_val = creds.get("password", "")

            # Gunakan kembali token metrics client aktif & sinkronkan ZeroTier IP
            auth_token = ""
            try:
                client = get_cached_metrics_client(srv, active_u)
                if client is not None:
                    if not client.token:
                        client.authenticate()
                    auth_token = client.token or ""
                    sync_server_zerotier_ip(srv.get("id"), client=client)
                    cfg = config_manager.load_or_create_config()
                    srv = config_manager.get_active_server(cfg) or srv
            except Exception:
                pass
            host, is_domain, zt_ip = _resolve_smb_route_params(srv, active_u)

        known_srv_hosts = _collect_myserver_smb_hosts(cfg, srv, include_all_servers=True)
        res = smb_mount_manager.mount_all_smb_shares(
            host=host,
            username=u_val,
            password=p_val,
            server_connections=conns,
            is_domain_route=is_domain,
            zerotier_ip=zt_ip,
            auth_token=auth_token,
            base_url=(active_u or "").rstrip("/"),
            force_refresh=True,
            smb_source=smb_source,
            backend_url=backend_url,
            on_token_refreshed=on_token_refreshed_cb,
            known_server_hosts=known_srv_hosts,
        )
        logger_manager.log_info(f"[SMB Pipeline] Hasil pemasangan ulang ({reason}): {res}")
        if isinstance(res, tuple) and res[0]:
            mounted_host = (
                (getattr(smb_mount_manager, "_cached_resolved_smb_host", {}) or {}).get("resolved")
                or resolved_b_host
                or host
            )
            _record_mounted_smb_host(srv.get("id"), mounted_host)

        if smb_source == "backend" and config_manager:
            try:
                cached_sh = list((getattr(smb_mount_manager, "_cached_smb_shares", {}) or {}).get("shares") or [])
                if cached_sh:
                    cfg_latest = config_manager.load_or_create_config()
                    config_manager.save_server_smb_source_config(
                        cfg_latest,
                        srv.get("id"),
                        source="backend",
                        allowed_disks=cached_sh,
                    )
            except Exception:
                pass

        try:



            fresh_drives = _scan_live_drives_now()



            with _drives_cache_lock:



                _cached_live_drives = fresh_drives



        except Exception:



            pass







        return res







    except Exception as e:







        logger_manager.log_error(f"[SMB Pipeline] Gagal rebind storage: {e}")







        return []







    finally:



        next_reason = None



        with _pending_rebind_lock:



            if _pending_rebind_reason:



                next_reason = _pending_rebind_reason



                _pending_rebind_reason = None



        try:



            _smb_pipeline_lock.release()



        except Exception:



            pass



        if next_reason:



            threading.Thread(



                target=rebind_storage_pipeline,



                args=(next_reason, True),



                daemon=True,



            ).start()























def mount_active_server_smb():







    """Memasang seluruh SMB share server aktif secara dinamis."""







    return rebind_storage_pipeline("mount_all")


def _verify_backend_account(backend_url, username, password):
    """Memverifikasi kredensial akun Backend ke POST /api/v1/auth/verify tanpa fallback ZimaOS."""
    clean_url = str(backend_url or "").strip().rstrip("/")
    if not clean_url:
        return 400, {"error": "URL Backend tidak tersedia."}
    ok, data, status = _backend_http_request(
        f"{clean_url}/api/v1/auth/verify",
        method="POST",
        json_body={"username": username, "password": password},
        timeout=5.0,
        retries=1,
    )
    if ok and status == 200 and isinstance(data, dict):
        return 200, data
    if isinstance(data, dict):
        err_detail = data.get("detail") or data.get("error") or data.get("message") or f"HTTP {status}"
    else:
        err_detail = str(data or f"HTTP {status}")
    return (status or 502), {"error": _mask_secret(err_detail, password)}


def _persist_refreshed_backend_token(server_id, new_token, auth_data=None):
    """Memperbarui access_token JWT Backend terenkripsi DPAPI tanpa menyentuh password atau kredensial ZimaOS."""
    if not config_manager or not new_token:
        return False
    cfg = config_manager.load_or_create_config()
    srv = _select_target_server(cfg, target_server_id=server_id)
    if not srv:
        return False
    actual_srv_id = srv.get("id")
    smb_cfg = config_manager.get_server_smb_source_config(srv)
    auth_dict = auth_data if isinstance(auth_data, dict) else {}
    new_role = auth_dict.get("role") if auth_dict.get("role") is not None else None
    raw_disks = auth_dict.get("allowed_disks")
    eff_role = str(new_role if new_role is not None else smb_cfg.get("role", "user")).strip().lower()
    existing_role = str(smb_cfg.get("role", "user")).strip().lower()
    if isinstance(raw_disks, list):
        if len(raw_disks) == 0 and eff_role in ("admin", "root") and existing_role in ("admin", "root"):
            new_disks = None
        else:
            new_disks = raw_disks
    else:
        new_disks = None
    return config_manager.save_server_smb_source_config(
        cfg,
        actual_srv_id,
        source=smb_cfg.get("source", "zimaos"),
        role=new_role,
        allowed_disks=new_disks,
        access_token=str(new_token).strip(),
    )


def _backend_authenticated_request(backend_url, endpoint, smb_cfg, srv_id, method="GET", json_body=None):
    """
    Mengirim permintaan terautentikasi Bearer JWT ke MyServer Backend dengan silent re-auth
    satu kali ke POST /api/v1/auth/verify ketika token kosong atau kedaluwarsa (HTTP 401),
    memakai kredensial terisolasi backend_smb_auth tanpa pernah fallback ke ZimaOS.
    """
    clean_base = str(backend_url or "").strip().rstrip("/")
    ep = endpoint if str(endpoint).startswith("/") else f"/{endpoint}"
    pwd = str((smb_cfg or {}).get("password") or "")
    uname = str((smb_cfg or {}).get("username") or "").strip()
    has_creds = bool((smb_cfg or {}).get("hasCredentials") and uname and pwd)
    token = str((smb_cfg or {}).get("access_token") or "").strip()

    verified_this_call = False
    if not token:
        if has_creds:
            v_status, v_data = _verify_backend_account(clean_base, uname, pwd)
            verified_this_call = True
            if v_status == 200 and isinstance(v_data, dict) and v_data.get("access_token"):
                token = str(v_data.get("access_token") or "").strip()
                _persist_refreshed_backend_token(srv_id, token, v_data)
            else:
                err_msg = _mask_secret((v_data or {}).get("error") or "Autentikasi Backend diperlukan.", pwd)
                return v_status, {"success": False, "needsAuth": (v_status == 401), "error": err_msg}, ""
        else:
            return 401, {"success": False, "needsAuth": True, "error": "Kredensial akun Backend belum dikonfigurasi."}, ""

    ok, data, status_code = _backend_http_request(
        f"{clean_base}{ep}",
        method=method,
        json_body=json_body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=5.0,
        retries=1,
    )

    if status_code == 401:
        if not verified_this_call and has_creds:
            v_status, v_data = _verify_backend_account(clean_base, uname, pwd)
            if v_status == 200 and isinstance(v_data, dict) and v_data.get("access_token"):
                token = str(v_data.get("access_token") or "").strip()
                _persist_refreshed_backend_token(srv_id, token, v_data)
                ok, data, status_code = _backend_http_request(
                    f"{clean_base}{ep}",
                    method=method,
                    json_body=json_body,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0,
                    retries=1,
                )
                if status_code == 401:
                    err_detail = (
                        (data.get("detail") or data.get("error") or "Sesi Backend kedaluwarsa. Silakan login ulang.")
                        if isinstance(data, dict)
                        else str(data or "Unauthorized")
                    )
                    return 401, {
                        "success": False,
                        "needsAuth": True,
                        "error": _mask_secret(_mask_secret(err_detail, pwd), token),
                    }, ""
            else:
                err_detail = (v_data or {}).get("error") or "Sesi Backend kedaluwarsa. Silakan login ulang."
                return (401 if v_status == 401 else v_status), {
                    "success": False,
                    "needsAuth": True,
                    "error": _mask_secret(_mask_secret(err_detail, pwd), token),
                }, ""
        else:
            err_detail = (
                (data.get("detail") or data.get("error") or "Autentikasi Backend diperlukan.")
                if isinstance(data, dict)
                else str(data or "Unauthorized")
            )
            return 401, {
                "success": False,
                "needsAuth": True,
                "error": _mask_secret(_mask_secret(err_detail, pwd), token),
            }, ""

    if isinstance(data, dict):
        return status_code, data, token
    return status_code, {"raw": _mask_secret(_mask_secret(str(data), pwd), token)}, token


_BACKEND_ACL_REBIND_DEBOUNCE_SEC = 2.0
_acl_rebind_lock = threading.Lock()
_acl_rebind_timer = None
_acl_rebind_done_event = threading.Event()
_acl_rebind_done_event.set()


def _get_easytier_smb_status_fields():
    """Mengembalikan status adapter Wintun/TUN EasyTier untuk banner peringatan UI."""
    try:
        if easytier_manager is None:
            return {"easytierNoTun": False, "tunActive": True, "smbWarning": ""}
        st = easytier_manager.get_easytier_manager().get_status_overview() or {}
        running = bool(st.get("running", False))
        tun_active = bool(st.get("tun_active", True)) if running else True
        no_tun = bool(running and (st.get("no_tun_fallback") or not tun_active))
        return {
            "easytierNoTun": no_tun,
            "tunActive": tun_active,
            "smbWarning": str(st.get("smb_warning") or "") if no_tun else "",
        }
    except Exception:
        return {"easytierNoTun": False, "tunActive": True, "smbWarning": ""}


def _schedule_debounced_acl_rebind(reason="backend_acl_changed", delay_sec=None):
    """Menjadwalkan rebind ACL secara asinkron & ter-debounce agar GET /api/smb/source tidak memblokir UI."""
    global _acl_rebind_timer
    eff_delay = float(_BACKEND_ACL_REBIND_DEBOUNCE_SEC if delay_sec is None else delay_sec)

    def _run_acl_rebind():
        global _cached_live_drives
        try:
            rebind_storage_pipeline(reason)
            fresh_drives = _scan_live_drives_now()
            with _drives_cache_lock:
                _cached_live_drives = fresh_drives
        except Exception as _acl_err:
            logger_manager.log_warning(f"[SMB ACL] Gagal menjalankan debounced rebind: {_acl_err}")
        finally:
            _acl_rebind_done_event.set()

    with _acl_rebind_lock:
        if _acl_rebind_timer is not None:
            try:
                _acl_rebind_timer.cancel()
            except Exception:
                pass
        _acl_rebind_done_event.clear()
        timer = threading.Timer(max(eff_delay, 0.0), _run_acl_rebind)
        timer.daemon = True
        _acl_rebind_timer = timer
        timer.start()


def _flush_pending_acl_rebind_for_test(timeout=3.0):
    """Menunggu timer debounced ACL selesai (khusus helper unit test deterministik)."""
    return bool(_acl_rebind_done_event.wait(timeout=float(timeout)))


def _handle_smb_source_request(body=None):
    """Menangani GET/POST /api/smb/source dengan validasi kredensial dahulu, client-first teardown, async ACL debounce, dan status --no-tun."""
    global _cached_live_drives

    body = body if isinstance(body, dict) else {}
    req_server_id = str(body.get("serverId") or body.get("server_id") or "").strip() or None
    cfg = config_manager.load_or_create_config() if config_manager else {}
    srv = _select_target_server(cfg, target_server_id=req_server_id)
    if not srv:
        return 400, {"success": False, "source": "zimaos", "error": "Server aktif tidak ditemukan.", **_get_easytier_smb_status_fields()}

    srv_id = srv.get("id") or "default"
    smb_cfg = config_manager.get_server_smb_source_config(srv)

    raw_action = str(body.get("action") or "").strip().lower()
    if raw_action == "get" or (not raw_action and "source" not in body):
        action = "get"
    elif raw_action == "set" or "source" in body:
        action = "set"
    else:
        action = "get"

    def _collect_hosts(target_srv, target_cfg):
        return _collect_myserver_smb_hosts(cfg=target_cfg, server=target_srv, include_all_servers=False)

    def _resolve_backend_url(target_cfg, target_srv):
        raw_url = _get_active_server_backend_url(target_cfg, target_server_id=target_srv.get("id")) or ""
        if not raw_url:
            return ""
        try:
            au, _ = get_active_resolved_route(target_cfg)
            h, is_dom, zt_ip = _resolve_smb_route_params(target_srv, au)
            if _is_wan_host_safe(_extract_host_from_url(raw_url)):
                fb = smb_mount_manager.resolve_smb_host(h, target_srv.get("connections", []), is_dom, zt_ip) or ""
                if fb and not _is_wan_host_safe(fb):
                    return smb_mount_manager._normalize_backend_api_url(raw_url, fallback_host=fb)
        except Exception:
            pass
        return raw_url.rstrip("/")

    backend_url = _resolve_backend_url(cfg, srv)

    if action == "get":
        backend_online = False
        smb_mode = smb_cfg["source"]
        needs_auth = False

        if backend_url:
            h_ok, h_data, _ = _backend_http_request(
                f"{backend_url.rstrip('/')}/health", method="GET", timeout=2.0, retries=0
            )
            backend_online = bool(h_ok and isinstance(h_data, dict) and h_data.get("status") == "ok")
            if backend_online and (smb_cfg.get("access_token") or smb_cfg.get("hasCredentials")):
                st_code, st_data, _ = _backend_authenticated_request(
                    backend_url, "/api/v1/smb/status", smb_cfg, srv_id, method="GET"
                )
                if st_code == 200 and isinstance(st_data, dict):
                    smb_mode = str(st_data.get("mode") or smb_cfg["source"]).strip().lower()
                    cfg = config_manager.load_or_create_config()
                    srv = _select_target_server(cfg, target_server_id=srv_id) or srv
                    smb_cfg = config_manager.get_server_smb_source_config(srv)
                    if smb_cfg.get("source") == "backend":
                        d_code, d_data, _ = _backend_authenticated_request(
                            backend_url, "/api/v1/storage/disks", smb_cfg, srv_id, method="GET"
                        )
                        if d_code == 200 and isinstance(d_data, dict):
                            _update_backend_disks_usage_cache(srv_id, d_data.get("disks") or [])
                            fresh_permitted = []
                            for disk_item in (d_data.get("disks") or []):
                                if (
                                    isinstance(disk_item, dict)
                                    and disk_item.get("is_accessible", True)
                                    and disk_item.get("name")
                                    and disk_item.get("relative_path", None) != ""
                                ):
                                    d_name = str(disk_item["name"]).strip()
                                    if d_name and d_name not in fresh_permitted:
                                        fresh_permitted.append(d_name)
                            prev_disks = [
                                str(x).strip()
                                for x in (smb_cfg.get("allowed_disks") or [])
                                if str(x).strip()
                            ]
                            if {x.lower() for x in fresh_permitted} != {x.lower() for x in prev_disks}:
                                cfg = config_manager.load_or_create_config()
                                config_manager.save_server_smb_source_config(
                                    cfg,
                                    srv_id,
                                    source="backend",
                                    allowed_disks=fresh_permitted,
                                )
                                smb_mount_manager.clear_smb_share_cache()
                                fresh_drives = _scan_live_drives_now()
                                with _drives_cache_lock:
                                    _cached_live_drives = fresh_drives
                                _schedule_debounced_acl_rebind("backend_acl_changed")
                                cfg = config_manager.load_or_create_config()
                                srv = _select_target_server(cfg, target_server_id=srv_id) or srv
                                smb_cfg = config_manager.get_server_smb_source_config(srv)
                        elif d_code == 401:
                            needs_auth = True
                elif st_code == 401:
                    needs_auth = True

        return 200, {
            "success": True,
            "source": smb_cfg["source"],
            "username": smb_cfg["username"],
            "role": smb_cfg["role"],
            "allowedDisks": list(smb_cfg["allowed_disks"]),
            "hasCredentials": bool(smb_cfg["hasCredentials"]),
            "backendOnline": bool(backend_online),
            "backendUrl": backend_url,
            "smbMode": smb_mode,
            "needsAuth": bool(needs_auth),
            "drives": get_live_drives_list(),
            **_get_easytier_smb_status_fields(),
        }

    # action == "set"
    target_source = str(body.get("source") or "").strip().lower()
    if target_source not in ("zimaos", "backend"):
        return 400, {
            "success": False,
            "source": smb_cfg["source"],
            "error": f"Sumber File Manager tidak valid: {target_source}",
        }

    auto_mount = bool(body.get("autoMount", True))

    if target_source == "backend":
        if not backend_url:
            return 400, {
                "success": False,
                "source": smb_cfg["source"],
                "error": "Backend MyServer tidak ditemukan atau offline.",
            }

        req_uname = str(body.get("username") or "").strip()
        req_pwd = body.get("password")
        explicit_pwd = req_pwd is not None and str(req_pwd) != ""

        if explicit_pwd:
            uname = req_uname or smb_cfg.get("username", "")
            pwd = str(req_pwd)
            if not uname:
                return 400, {
                    "success": False,
                    "source": smb_cfg["source"],
                    "needsAuth": True,
                    "error": "Username dan password akun Backend wajib diisi.",
                }
            # Step 1 (Auth validation FIRST - before any unmount/purge!)
            v_status, v_data = _verify_backend_account(backend_url, uname, pwd)
            if v_status != 200:
                err_msg = _mask_secret((v_data or {}).get("error") or "Login akun Backend gagal.", pwd)
                return (v_status if v_status >= 400 else 401), {
                    "success": False,
                    "source": smb_cfg["source"],
                    "needsAuth": (v_status == 401),
                    "error": err_msg,
                }
            active_token = str((v_data or {}).get("access_token") or "").strip()
            role = (
                config_manager._normalize_smb_role((v_data or {}).get("role"))
                if hasattr(config_manager, "_normalize_smb_role")
                else ("admin" if str((v_data or {}).get("role") or "").strip().lower() == "admin" else ("root" if str((v_data or {}).get("role") or "").strip().lower() == "root" else "user"))
            )
            allowed_from_auth = (v_data or {}).get("allowed_disks") or []

            # Step 2 (Client-first Windows teardown BEFORE POST /api/v1/smb/mode!)
            server_hosts = _collect_hosts(srv, cfg)
            smb_mount_manager.clear_smb_share_cache()
            smb_mount_manager.unmount_all_smb_shares(allowed_hosts=server_hosts)
            smb_mount_manager.purge_smb_sessions(server_hosts, notify_explorer=False)
            time.sleep(0.3)

            # Step 3 (Server switch & disks fetch)
            m_ok, m_data, m_status = _backend_http_request(
                f"{backend_url.rstrip('/')}/api/v1/smb/mode",
                method="POST",
                json_body={"mode": "backend", "username": uname, "password": pwd},
                headers={"Authorization": f"Bearer {active_token}"},
                timeout=5.0,
                retries=1,
            )
            if not m_ok or m_status != 200:
                raw_m_err = (
                    (m_data.get("detail") or m_data.get("error") or f"HTTP {m_status}")
                    if isinstance(m_data, dict)
                    else str(m_data or f"HTTP {m_status}")
                )
                return (m_status if m_status >= 400 else 502), {
                    "success": False,
                    "source": smb_cfg["source"],
                    "needsAuth": (m_status == 401),
                    "error": _mask_secret(_mask_secret(raw_m_err, pwd), active_token),
                }

            d_ok, d_data, d_status = _backend_http_request(
                f"{backend_url.rstrip('/')}/api/v1/storage/disks",
                method="GET",
                headers={"Authorization": f"Bearer {active_token}"},
                timeout=5.0,
                retries=1,
            )
        else:
            if req_uname and smb_cfg.get("username") and req_uname.lower() != smb_cfg["username"].lower():
                return 400, {
                    "success": False,
                    "source": smb_cfg["source"],
                    "needsAuth": True,
                    "error": "Kata sandi wajib diisi untuk akun Backend baru.",
                }
            if not smb_cfg.get("hasCredentials"):
                return 400, {
                    "success": False,
                    "source": smb_cfg["source"],
                    "needsAuth": True,
                    "error": "Silakan masukkan username dan password akun Backend.",
                }

            uname = smb_cfg["username"]
            pwd = smb_cfg["password"]
            role = smb_cfg.get("role", "user")
            allowed_from_auth = smb_cfg.get("allowed_disks", [])

            # Step 1 (Auth validation FIRST using stored token/credentials before any unmount/purge!)
            pre_status, pre_data, _ = _backend_authenticated_request(
                backend_url, "/api/v1/smb/status", smb_cfg, srv_id, method="GET"
            )
            if pre_status == 401 or (isinstance(pre_data, dict) and pre_data.get("needsAuth")):
                return 401, {
                    "success": False,
                    "source": smb_cfg["source"],
                    "needsAuth": True,
                    "error": _mask_secret((pre_data or {}).get("error") or "Login akun Backend diperlukan.", pwd),
                }
            cfg = config_manager.load_or_create_config()
            srv = _select_target_server(cfg, target_server_id=srv_id) or srv
            smb_cfg = config_manager.get_server_smb_source_config(srv)
            role = smb_cfg.get("role", role)

            # Step 2 (Client-first Windows teardown BEFORE POST /api/v1/smb/mode!)
            server_hosts = _collect_hosts(srv, cfg)
            smb_mount_manager.clear_smb_share_cache()
            smb_mount_manager.unmount_all_smb_shares(allowed_hosts=server_hosts)
            smb_mount_manager.purge_smb_sessions(server_hosts, notify_explorer=False)
            time.sleep(0.3)

            # Step 3 (Server switch & disks fetch)
            m_status, m_data, active_token = _backend_authenticated_request(
                backend_url,
                "/api/v1/smb/mode",
                smb_cfg,
                srv_id,
                method="POST",
                json_body={"mode": "backend", "username": uname, "password": pwd},
            )
            if m_status != 200:
                if isinstance(m_data, dict) and m_data.get("needsAuth"):
                    return (401 if m_status == 401 else m_status), {
                        "success": False,
                        "source": smb_cfg["source"],
                        "needsAuth": True,
                        "error": _mask_secret(m_data.get("error") or "Login akun Backend diperlukan.", pwd),
                    }
                raw_m_err = (
                    (m_data.get("detail") or m_data.get("error") or f"HTTP {m_status}")
                    if isinstance(m_data, dict)
                    else str(m_data or f"HTTP {m_status}")
                )
                return (m_status if m_status >= 400 else 502), {
                    "success": False,
                    "source": smb_cfg["source"],
                    "needsAuth": (m_status == 401),
                    "error": _mask_secret(_mask_secret(raw_m_err, pwd), active_token),
                }

            cfg = config_manager.load_or_create_config()
            srv = _select_target_server(cfg, target_server_id=srv_id) or srv
            smb_cfg = config_manager.get_server_smb_source_config(srv)
            role = smb_cfg.get("role", role)

            d_status, d_data, active_token = _backend_authenticated_request(
                backend_url, "/api/v1/storage/disks", smb_cfg, srv_id, method="GET"
            )
            if d_status == 401:
                return 401, {
                    "success": False,
                    "source": smb_cfg["source"],
                    "needsAuth": True,
                    "error": _mask_secret((d_data or {}).get("error") or "Sesi Backend kedaluwarsa.", pwd),
                }

        permitted_disks = []
        if d_status == 200 and isinstance(d_data, dict):
            _update_backend_disks_usage_cache(srv_id, d_data.get("disks") or [])
            for disk_item in (d_data.get("disks") or []):
                if (
                    isinstance(disk_item, dict)
                    and disk_item.get("is_accessible", True)
                    and disk_item.get("name")
                    and disk_item.get("relative_path", None) != ""
                ):
                    d_name = str(disk_item["name"]).strip()
                    if d_name and d_name not in permitted_disks:
                        permitted_disks.append(d_name)
        elif isinstance(allowed_from_auth, list):
            permitted_disks = [str(x).strip() for x in allowed_from_auth if str(x).strip()]

        # Step 4 (Persist & mount with pre_unmounted=True)
        cfg = config_manager.load_or_create_config()
        config_manager.save_server_smb_source_config(
            cfg,
            srv_id,
            source="backend",
            username=uname,
            password=pwd,
            role=role,
            allowed_disks=permitted_disks,
            access_token=active_token,
        )

        if auto_mount:
            rebind_storage_pipeline("switch_source_backend", pre_unmounted=True)

        fresh_drives = _scan_live_drives_now()
        with _drives_cache_lock:
            _cached_live_drives = fresh_drives

        return 200, {
            "success": True,
            "source": "backend",
            "username": uname,
            "role": role,
            "allowedDisks": permitted_disks,
            "hasCredentials": True,
            "backendOnline": True,
            "backendUrl": backend_url,
            "smbMode": "backend",
            "needsAuth": False,
            "drives": fresh_drives,
            **_get_easytier_smb_status_fields(),
        }

    # target_source == "zimaos"
    # Step 1 (Client-first Windows teardown BEFORE POST /api/v1/smb/mode!)
    server_hosts = _collect_hosts(srv, cfg)
    smb_mount_manager.clear_smb_share_cache()
    smb_mount_manager.unmount_all_smb_shares(allowed_hosts=server_hosts)
    smb_mount_manager.purge_smb_sessions(server_hosts, notify_explorer=False)
    time.sleep(0.3)

    # Step 2 (Server switch best-effort)
    backend_online = False
    warning_msg = ""
    if backend_url and (smb_cfg.get("access_token") or smb_cfg.get("hasCredentials")):
        zimaos_payload = {"mode": "zimaos"}
        if smb_cfg.get("hasCredentials"):
            zimaos_payload["username"] = smb_cfg["username"]
            zimaos_payload["password"] = smb_cfg["password"]
        m_status, m_data, _ = _backend_authenticated_request(
            backend_url,
            "/api/v1/smb/mode",
            smb_cfg,
            srv_id,
            method="POST",
            json_body=zimaos_payload,
        )
        if m_status == 200:
            backend_online = True
        else:
            safe_err = _mask_secret(str(m_data), smb_cfg.get("password", ""))
            logger_manager.log_warning(
                f"[/api/smb/source] Gagal memberi tahu Backend beralih ke mode zimaos (best-effort): HTTP {m_status} {safe_err}"
            )
            warning_msg = "Mode SMB dialihkan ke ZimaOS; layanan SMB Backend tidak merespons."

    # Step 3 (Persist & mount with pre_unmounted=True)
    cfg = config_manager.load_or_create_config()
    config_manager.save_server_smb_source_config(cfg, srv_id, "zimaos")

    if auto_mount:
        rebind_storage_pipeline("switch_source_zimaos", pre_unmounted=True)

    fresh_drives = _scan_live_drives_now()
    with _drives_cache_lock:
        _cached_live_drives = fresh_drives

    cfg_after = config_manager.load_or_create_config()
    srv_after = _select_target_server(cfg_after, target_server_id=srv_id) or srv
    smb_cfg_after = config_manager.get_server_smb_source_config(srv_after)

    resp = {
        "success": True,
        "source": "zimaos",
        "username": smb_cfg_after["username"],
        "role": smb_cfg_after["role"],
        "allowedDisks": list(smb_cfg_after["allowed_disks"]),
        "hasCredentials": bool(smb_cfg_after["hasCredentials"]),
        "backendOnline": bool(backend_online),
        "backendUrl": backend_url,
        "smbMode": "zimaos",
        "needsAuth": False,
        "drives": fresh_drives,
        **_get_easytier_smb_status_fields(),
    }
    if warning_msg:
        resp["warning"] = warning_msg
    return 200, resp


_compose_apps_lock = threading.Lock()







_cached_compose_apps = []























def _scan_compose_apps_now():







    """Mengambil daftar aplikasi Docker/Compose ZimaOS via HTTP client."""







    try:







        cfg = config_manager.load_or_create_config()







        srv = config_manager.get_active_server(cfg)







        if srv:







            act_p = srv.get("active_profile", "Admin")







            creds = config_manager.get_server_credentials(srv, act_p)







            active_u, _ = get_active_resolved_route(cfg)







            parsed = urllib.parse.urlparse(active_u)







            client = zima_metrics_manager.ZimaMetricsClient(







                host=parsed.hostname or "127.0.0.1",







                port=str(parsed.port) if parsed.port else ("443" if parsed.scheme.lower() == "https" else "80"),







                use_https=(parsed.scheme.lower() == "https"),







                username=creds.get("username", ""),







                password=creds.get("password", ""),







                server_connections=srv.get("connections", []),







                server_name=srv.get("name", ""),



                zerotier_ip=get_active_remote_ip(srv),







            )







            apps = client.fetch_compose_apps()







            return apps if isinstance(apps, list) else []







    except Exception as e:







        logger_manager.log_debug(f"[CoreService] Background compose apps scan: {e}")







    return []























def update_web_apps_cache_loop():







    """Latar belakang daemon: memperbarui cache kontainer ZimaOS setiap 30 detik tanpa memblokir request UI."""







    global _cached_compose_apps







    try:







        init_apps = _scan_compose_apps_now()







        with _compose_apps_lock:







            _cached_compose_apps = init_apps







    except Exception:







        pass















    while True:







        try:







            time.sleep(30)







            apps = _scan_compose_apps_now()







            with _compose_apps_lock:







                _cached_compose_apps = apps







        except Exception as e:







            logger_manager.log_debug(f"[CoreService] Error in update_web_apps_cache_loop: {e}")























def get_web_apps_list():







    """Menggabungkan bookmark web kustom dan aplikasi Docker ZimaOS langsung dari RAM (latensi 0 ms)."""







    cfg = config_manager.load_or_create_config()







    custom_apps = cfg.get("web_apps", [])







    result = []







    for a in custom_apps:







        a_id = a.get("id") or f"app_{int(time.time() * 1000)}"







        a_name = a.get("name", "Web App")







        a_url = a.get("url", "")







        port = ""







        try:







            parsed = urllib.parse.urlparse(a_url)







            if parsed.port:







                port = str(parsed.port)







        except Exception:







            pass







        result.append({







            "id": a_id,







            "name": a_name,







            "url": a_url,







            "port": port,







            "status": "custom",







            "icon": "",







            "is_zima_container": False,







        })







    with _compose_apps_lock:







        zima_apps = list(_cached_compose_apps)







    result.extend(zima_apps)







    return result























def get_server_details_data(cfg=None):







    """Mengembalikan data komprehensif server, rute, profil, dan status ZeroTier."""







    if cfg is None:







        cfg = config_manager.load_or_create_config()







    srv = config_manager.get_active_server(cfg) or {}







    s_name = srv.get("name", "Server Utama")







    active_p = srv.get("active_profile", "Admin")







    profiles = srv.get("profiles", ["Admin"])







    conns = srv.get("connections", [])







    act_conn_id = srv.get("active_connection", "auto")















    active_u, _ = get_active_resolved_route(cfg)















    routes_list = []







    for c in conns:







        if not isinstance(c, dict):







            continue







        cid = c.get("id", "")







        cname = c.get("name", "")







        curl = c.get("url", "")







        parsed_curl = urllib.parse.urlparse(curl if "://" in curl else f"http://{curl}")



        curl_h = parsed_curl.hostname or curl



        srv_zt_ip_val = (srv.get("zerotier_virtual_ip") or "").strip()



        is_zt = ("ZeroTier" in cname) or (bool(srv_zt_ip_val) and curl_h == srv_zt_ip_val) or zerotier_manager.is_zerotier_ip(curl_h)







        is_act = (cid == act_conn_id) or (act_conn_id == "auto" and curl.rstrip("/") == active_u.rstrip("/"))







        act_p_ms = None



        if is_act:



            ok_p, lat_p = config_manager.check_server_ping(curl, timeout=1.2)



            act_p_ms = lat_p if ok_p else None







        routes_list.append({



            "id": cid,



            "name": cname,



            "url": curl,



            "active": is_act,



            "isZeroTier": is_zt,



            "pingMs": act_p_ms,



        })







    # Injeksi rute remote dinamis tunggal (EasyTier <-> ZeroTier Failover)
    rem_info = config_manager.get_dynamic_remote_info(srv, cfg)
    if rem_info and rem_info.get("url"):
        rem_u = rem_info["url"]
        rem_name = rem_info["name"]
        rem_engine = rem_info["engine"]
        rem_act = (act_conn_id in ("conn_remote_dynamic", "conn_zerotier_auto")) or (act_conn_id == "auto" and rem_u.rstrip("/") in active_u.rstrip("/"))
        rem_p_ms = None
        if rem_act:
            ok_r, lat_r = config_manager.check_server_ping(rem_u, timeout=1.5)
            rem_p_ms = lat_r if ok_r else None

        # Bersihkan rute remote duplikat agar hanya muncul 1 kartu tunggal
        routes_list = [r for r in routes_list if not r.get("isZeroTier") and not r.get("isRemoteDynamic") and not ("ZeroTier" in r.get("name", "") or "EasyTier" in r.get("name", ""))]

        routes_list.append({
            "id": "conn_remote_dynamic",
            "name": rem_name,
            "url": rem_u,
            "active": rem_act,
            "isZeroTier": (rem_engine == "zerotier"),
            "isEasyTier": (rem_engine == "easytier"),
            "isRemoteDynamic": True,
            "remoteEngine": rem_engine,
            "badge": rem_info.get("badge", "P2P"),
            "pingMs": rem_p_ms,
        })















    client = get_cached_metrics_client(srv, active_u)



    is_admin = False



    if client:



        if not getattr(client, "token", None):



            try:



                client.authenticate()



            except Exception:



                pass



        is_admin = bool(getattr(client, "is_admin", False))



    else:



        with _state_lock:



            is_admin = bool(_cached_state.get("is_admin", False))







    with _state_lock:



        _cached_state["is_admin"] = is_admin



        m = dict(_cached_state)







    cur_l = cfg.get("language", "en")



    uptime_sec = m.get("uptime", 0)







    if uptime_sec > 0:







        hrs = uptime_sec // 3600







        mins = (uptime_sec % 3600) // 60







        uptime_str = f"{hrs}j {mins}m"







    else:







        uptime_str = ("Aktif" if cur_l == "id" else "Active") if bool(m.get("is_online", m.get("online", False))) else "Offline"















    active_srv_id = cfg.get("active_server_id", "")







    servers_list = []







    for s in cfg.get("servers", []):







        if isinstance(s, dict):







            servers_list.append({







                "id": s.get("id", ""),







                "name": s.get("name", "Server"),







                "active": (s.get("id") == active_srv_id),
                "sshUser": (s.get("ssh_user") or "").strip(),
                "remote_id": s.get("remote_id") or s.get("zerotier_network_id") or "",
                "easytier_virtual_ip": s.get("easytier_virtual_ip") or "",
                "zerotier_network_id": s.get("zerotier_network_id") or "",
                "zerotier_virtual_ip": s.get("zerotier_virtual_ip") or "",
                "remote_mode": s.get("remote_mode") or "auto"







            })















    cfg_nwid = (srv.get("zerotier_network_id") or srv.get("remote_id") or "").strip().lower()



    srv_zt_vip = (srv.get("zerotier_virtual_ip") or "").strip()







    zt_info = {







        "running": False,







        "nodeId": "",







        "networkName": "",







        "networkStatus": "",







        "virtualIp": "",







        "configuredNwid": cfg_nwid,







        "joined": False,







        "serverVirtualIp": srv_zt_vip,







    }







    try:







        zt_client = zerotier_manager.ZeroTierClient()







        running, status = zt_client.is_service_running()







        zt_info["running"] = bool(running)







        if running:







            zt_info["nodeId"] = status.get("address", "") if isinstance(status, dict) else ""







            networks = zt_client.get_joined_networks()







            matched_net = None







            if cfg_nwid:







                matched_net = zt_client.get_network_by_id(cfg_nwid)







            elif len(networks) == 1:







                matched_net = networks[0]















            if matched_net:







                zt_info["joined"] = True







                zt_info["networkName"] = matched_net.get("name") or matched_net.get("nwid") or ""







                zt_info["networkStatus"] = matched_net.get("status", "")







                addrs = matched_net.get("assignedAddresses", [])







                for a in addrs:







                    if "." in a:







                        zt_info["virtualIp"] = a.split("/")[0]







                        break







                if not zt_info["virtualIp"] and addrs:







                    zt_info["virtualIp"] = addrs[0].split("/")[0]







            elif cfg_nwid:







                zt_info["joined"] = False







                zt_info["networkStatus"] = "Belum Terhubung"







    except Exception as e:







        logger_manager.log_debug(f"[CoreService] ZeroTier query note: {e}")















    parsed_u = urllib.parse.urlparse(active_u)







    active_host = parsed_u.hostname or ""















    return {







        "serverId": srv.get("id", ""),







        "serverName": s_name,







        "activeHost": active_host,







        "sshUser": (srv.get("ssh_user") or "").strip(),







        "servers": servers_list,







        "zeroTier": zt_info,
        "easyTier": (lambda s: (s.update({
            "remote_id": s.get("remote_id") or srv.get("remote_id") or srv.get("zerotier_network_id") or cfg.get("easytier", {}).get("remote_id"),
            "server_peer_ip": (rem_info.get("ip") if rem_info and rem_info.get("engine") == "easytier" else None) or srv.get("easytier_virtual_ip") or (s.get("server_peer_ip") if (not srv.get("remote_id") or srv.get("remote_id") == (easytier_manager.get_easytier_manager().get_remote_id() or "")) else "") or "",
            "running": bool(s.get("running") and (not srv.get("remote_id") or not easytier_manager.get_easytier_manager().get_remote_id() or srv.get("remote_id").strip().lower() == (easytier_manager.get_easytier_manager().get_remote_id() or "").strip().lower())),
        }), s)[1])(easytier_manager.get_easytier_manager().get_status_overview()) if easytier_manager else {"running": False},
        "remoteMode": srv.get("remote_mode") or cfg.get("remote_mode", "auto"),
        "activeRemoteEngine": rem_info.get("engine", "none") if rem_info else "none",
        "activeRemoteIp": rem_info.get("ip", "") if rem_info else "",







        "activeRoute": act_conn_id,







        "routes": routes_list,







        "activeProfile": active_p,







        "profiles": profiles,







        "uptimeStr": uptime_str,



        "isAdmin": is_admin,



        "accountStatus": {



            "username": active_p,



            "isAdmin": is_admin,



            "roleName": ("Administrator" if cur_l == "id" else "Administrator") if is_admin else ("Pengguna Standar" if cur_l == "id" else "Standard User"),



            "accessDescription": (



                ("Administrator (Samba & Kontrol Penuh)" if cur_l == "id" else "Administrator (Full Control & Samba)")



                if is_admin



                else ("Pengguna Standar (Hanya Akses Samba)" if cur_l == "id" else "Standard User (Samba Access Only)")



            ),



            "verified": bool(bool(m.get("is_online", m.get("online", True))) and client and getattr(client, "token", None)),



        },



        "macAddress": (srv.get("wake_on_lan", {}).get("mac_address") or "").strip().upper(),



        "appVersion": APP_VERSION_NUMBER,



        "appChannel": "Beta",



        "fullVersion": APP_FULL_VERSION,



        "dpapiActive": bool(config_manager.is_dpapi_supported()),
        "backend": _get_backend_health_info(cfg),







    }























_active_metrics_client = None







_active_metrics_client_key = None















def get_cached_metrics_client(srv, active_u):







    """Mengembalikan instance aktif ZimaMetricsClient dari server aktif."""







    global _active_metrics_client, _active_metrics_client_key







    if not srv:







        return None







    parsed = urllib.parse.urlparse(active_u)







    srv_host = parsed.hostname or "127.0.0.1"







    srv_port = str(parsed.port) if parsed.port else ("443" if parsed.scheme.lower() == "https" else "80")







    use_https = (parsed.scheme.lower() == "https")







    act_p = srv.get("active_profile", "Admin")







    creds = config_manager.get_server_credentials(srv, act_p)







    u_name = creds.get("username", "")







    p_pass = creds.get("password", "")







    srv_zt_ip = (srv.get("zerotier_virtual_ip") or "").strip()



    act_conn = srv.get("active_connection", "auto")



    is_auto = (act_conn == "auto")







    client_key = (srv_host, srv_port, use_https, u_name, p_pass, is_auto)







    smb_cfg = config_manager.get_server_smb_source_config(srv) if (config_manager and hasattr(config_manager, "get_server_smb_source_config")) else {}
    srv_smb_source = str((smb_cfg.get("source") if isinstance(smb_cfg, dict) else None) or srv.get("smb_source") or "zimaos").strip().lower()
    if srv_smb_source not in ("zimaos", "backend"):
        srv_smb_source = "zimaos"

    if _active_metrics_client is not None and _active_metrics_client_key == client_key:



        if active_u:



            _active_metrics_client.base_url = active_u.rstrip("/")



            _active_metrics_client.host = srv_host



        if getattr(_active_metrics_client, "zerotier_ip", "") != srv_zt_ip:



            _active_metrics_client.zerotier_ip = srv_zt_ip



            _active_metrics_client._cached_server_identities = None



        _active_metrics_client.allow_multi_route_failover = is_auto
        _active_metrics_client.smb_source = srv_smb_source



        return _active_metrics_client







    try:







        client = zima_metrics_manager.ZimaMetricsClient(







            host=srv_host,







            port=srv_port,







            use_https=use_https,







            username=u_name,







            password=p_pass,







            server_connections=srv.get("connections", []),







            server_name=srv.get("name", ""),







            zerotier_ip=srv_zt_ip,







            allow_multi_route_failover=is_auto,
            smb_source=srv_smb_source,







        )







        _active_metrics_client = client







        _active_metrics_client_key = client_key







        return client







    except Exception as e:







        logger_manager.log_error(f"[CoreService] Gagal inisialisasi metrics client: {e}")







        return None























_startup_auto_mount_attempted = False







OFFLINE_FAIL_THRESHOLD = 3







AUTO_MOUNT_MAX_ATTEMPTS = 4







AUTO_MOUNT_RETRY_STEP_SECONDS = 3.0















def run_auto_mount_with_retry(reason):







    """







    Memasang SMB otomatis (startup_auto / server_recovered) dengan retry adaptif karena jaringan







    (Wi-Fi/LAN/ZeroTier) sering baru siap beberapa detik setelah server terdeteksi reachable.







    Berhenti bila berhasil, server kembali offline, atau pipeline lain sedang berjalan.







    """







    for attempt in range(AUTO_MOUNT_MAX_ATTEMPTS):







        res = rebind_storage_pipeline(reason)







        if isinstance(res, tuple) and res and res[0]:







            return res







        if _smb_pipeline_lock.locked():







            return res







        with _state_lock:







            still_online = bool(_cached_state.get("is_online", False))







        if not still_online or attempt >= AUTO_MOUNT_MAX_ATTEMPTS - 1:







            return res







        logger_manager.log_info(f"[SMB Pipeline] Auto-mount ({reason}) belum berhasil, mencoba lagi (percobaan {attempt + 2}/{AUTO_MOUNT_MAX_ATTEMPTS})...")







        time.sleep(AUTO_MOUNT_RETRY_STEP_SECONDS * (attempt + 1))







    return []























def commit_fast_online(partial_m, s_name="", active_u="", route_lbl="", ip_str=""):



    """Menyimpan data metrik cepat (CPU, RAM, DISK, NET) ke _cached_state dan mematikan telemetry_loading."""



    fast_cpu = int(round(partial_m.get("cpu_usage_pct", 0) or 0))



    fast_ram = int(round(partial_m.get("ram_usage_pct", 0) or 0))



    fast_disk = int(round(partial_m.get("storage_usage_pct", 0) or 0))



    down_bps = int(partial_m.get("speed_down_bps", 0) or 0)



    up_bps = int(partial_m.get("speed_up_bps", 0) or 0)



    with _state_lock:



        update_dict = {



            "is_online": True,



            "cpu_percent": fast_cpu,



            "ram_percent": fast_ram,



            "ping_str": "OK",



            "is_admin": bool(partial_m.get("is_admin", False)),



            "telemetry_loading": False,



        }



        if s_name:



            update_dict["server_name"] = s_name



        if active_u:



            update_dict["server_url"] = active_u.rstrip("/")



        if route_lbl:



            update_dict["route_name"] = route_lbl



        if ip_str:



            update_dict["ip"] = ip_str



        if partial_m.get("storage_usage_pct") is not None:



            update_dict["disk_percent"] = fast_disk



        if partial_m.get("speed_down_bps") is not None:



            update_dict["speed_down_bps"] = down_bps



            update_dict["speed_up_bps"] = up_bps



            update_dict["speed_down_str"] = partial_m.get("speed_down_str") or format_network_speed(down_bps)



            update_dict["speed_up_str"] = partial_m.get("speed_up_str") or format_network_speed(up_bps)



        if partial_m.get("ram_used_bytes") is not None:



            update_dict["ram_used_bytes"] = partial_m.get("ram_used_bytes")



            update_dict["ram_total_bytes"] = partial_m.get("ram_total_bytes")



        if partial_m.get("storage_used_bytes") is not None:



            update_dict["storage_used_bytes"] = partial_m.get("storage_used_bytes")



            update_dict["storage_total_bytes"] = partial_m.get("storage_total_bytes")



        if partial_m.get("storage_partitions"):



            update_dict["storage_partitions"] = partial_m.get("storage_partitions")



        if partial_m.get("cpu_temperature") is not None:



            update_dict["cpu_temperature"] = partial_m.get("cpu_temperature")



        if partial_m.get("cpu_wattage") is not None:



            update_dict["cpu_wattage"] = partial_m.get("cpu_wattage")



        _cached_state.update(update_dict)











def update_metrics_loop():







    """Latar belakang: update telemetri CPU, RAM, & Disk berkala setiap 2 detik tanpa memblokir request UI."""







    global _startup_auto_mount_attempted







    offline_streak = 0
    smb_offline_unmounted = False
    last_srv_id = None
    last_conn_id = None
    last_resolved_url = None







    while True:







        try:







            cfg = config_manager.load_or_create_config()







            s = config_manager.get_active_server(cfg)







            s_name = s.get("name", "MyServer") if s else "MyServer"







            cur_srv_id = s.get("id") if s else None



            cur_conn_id = s.get("active_connection", "auto") if s else "auto"







            srv_changed = False



            route_changed = False







            active_u, ind_text = get_active_resolved_route(cfg)
            norm_active_u = (active_u or "").strip().rstrip("/")
            resolved_url_changed = bool(last_resolved_url and norm_active_u and norm_active_u != last_resolved_url)

            if cur_srv_id != last_srv_id or cur_conn_id != last_conn_id or resolved_url_changed:
                offline_streak = 0
                smb_offline_unmounted = False
                srv_changed = (cur_srv_id != last_srv_id)
                route_changed = (cur_conn_id != last_conn_id or resolved_url_changed)
                last_srv_id = cur_srv_id
                last_conn_id = cur_conn_id
                if resolved_url_changed:
                    smb_mount_manager.invalidate_smb_host_cache()

            if norm_active_u:
                last_resolved_url = norm_active_u







            parsed = urllib.parse.urlparse(active_u)







            ip_str = parsed.hostname or "127.0.0.1"















            route_lbl = "LAN Fisik" if ("LAN" in ind_text or "Lokal" in ind_text) else ("ZeroTier P2P" if ("ZeroTier" in ind_text or "172.24." in ind_text or "172.25." in ind_text) else "Domain / WAN")







            with _state_lock:



                was_online = bool(_cached_state.get("is_online", True))







            def _commit_fast_online(partial_m):



                commit_fast_online(partial_m, s_name, active_u, route_lbl, ip_str)







            # Ambil metrik telemetri nyata dari ZimaMetricsClient



            client = get_cached_metrics_client(s, active_u)







            m = client.fetch_metrics(on_online_callback=_commit_fast_online) if client else {}







            cpu_val = int(round(m.get("cpu_usage_pct", 0) or 0))







            ram_val = int(round(m.get("ram_usage_pct", 0) or 0))







            used_b = m.get("storage_used_bytes", 0) or 0







            tot_b = m.get("storage_total_bytes", 0) or 0







            disk_val = int(round(m.get("storage_usage_pct", 0) or 0))







            if disk_val == 0 and tot_b > 0:







                disk_val = int(round((used_b / tot_b) * 100))















            raw_on = bool(m.get("online", False)) if client else False







            held_online = False







            if raw_on:
                offline_streak = 0
                smb_offline_unmounted = False
                is_on = True
            else:
                offline_streak += 1
                held_online = was_online and not srv_changed and not route_changed and offline_streak < OFFLINE_FAIL_THRESHOLD
                is_on = held_online
                if _should_unmount_on_offline_streak(raw_on, offline_streak, smb_offline_unmounted):
                    smb_offline_unmounted = True
                    _offline_cfg = cfg
                    _offline_srv = s
                    def _do_offline_unmount(c_arg=_offline_cfg, s_arg=_offline_srv):
                        _unmount_myserver_smb_drives(
                            reason="server_offline_streak",
                            cfg=c_arg,
                            server=s_arg,
                            include_easytier_subnet=True,
                        )
                        smb_mount_manager.invalidate_smb_host_cache()
                    threading.Thread(target=_do_offline_unmount, daemon=True).start()

            if is_on and s and bool(cfg.get("auto_mount_smb", True)):
                _check_effective_smb_host_transition_for_server(
                    s,
                    active_u,
                    auto_mount_enabled=True,
                    is_online=True,
                )







            if not was_online and is_on:



                if bool(cfg.get("auto_mount_smb", True)):



                    mount_reason = "server_recovered" if _startup_auto_mount_attempted else "startup_auto"



                    _startup_auto_mount_attempted = True



                    logger_manager.log_info(f"[CoreService] Server '{s_name}' ONLINE ({active_u}), memasang/memulihkan koneksi storage (Pemicu: {mount_reason})...")



                    threading.Thread(target=run_auto_mount_with_retry, args=(mount_reason,), daemon=True).start()



                else:



                    _startup_auto_mount_attempted = True



                    logger_manager.log_info(f"[CoreService] Server '{s_name}' ONLINE ({active_u}), auto-mount SMB dinonaktifkan pengguna.")















            # Kecepatan jaringan Server Riil ZimaOS (v3.10.21 Beta)



            if client and is_on and m.get("speed_down_bps") is not None:



                down_bps = int(m.get("speed_down_bps", 0) or 0)



                up_bps = int(m.get("speed_up_bps", 0) or 0)



                down_kb = down_bps / 1024.0



                up_kb = up_bps / 1024.0



                down_str = m.get("speed_down_str") or format_network_speed(down_bps)



                up_str = m.get("speed_up_str") or format_network_speed(up_bps)



            else:



                down_bps = 0



                up_bps = 0



                down_kb = 0.0



                up_kb = 0.0



                down_str = "0 B/s"



                up_str = "0 B/s"







            is_admin_val = bool(m.get("is_admin", False))







            if held_online:







                # Gagal sesaat: pertahankan metrik terakhir yang valid, jangan tampilkan 0 palsu







                with _state_lock:







                    cpu_val = _cached_state.get("cpu_percent", cpu_val)







                    ram_val = _cached_state.get("ram_percent", ram_val)







                    disk_val = _cached_state.get("disk_percent", disk_val)







                    is_admin_val = bool(_cached_state.get("is_admin", is_admin_val))















            with _state_lock:







                _cached_state.update({







                    "server_name": s_name,







                    "is_online": is_on,







                    "route_name": route_lbl,







                    "ip": ip_str,







                    "server_url": active_u.rstrip("/"),







                    "cpu_percent": cpu_val,







                    "ram_percent": ram_val,







                    "disk_percent": disk_val,







                    "ping_str": "OK" if is_on else "--",







                    "speed_down": int(down_kb),







                    "speed_up": int(up_kb),







                    "speed_down_bps": down_bps,







                    "speed_up_bps": up_bps,







                    "speed_down_str": down_str,







                    "speed_up_str": up_str,



                    "is_admin": is_admin_val,







                    "cpu_temperature": m.get("cpu_temperature"),







                    "cpu_wattage": m.get("cpu_wattage", 0.0),







                    "ram_used_bytes": m.get("ram_used_bytes", 0),







                    "ram_total_bytes": m.get("ram_total_bytes", 0),







                    "storage_used_bytes": m.get("storage_used_bytes", used_b),







                    "storage_total_bytes": m.get("storage_total_bytes", tot_b),







                    "storage_partitions": m.get("storage_partitions", []),



                    "telemetry_loading": False,







                })







        except Exception as e:







            logger_manager.log_info(f"[CoreService] Error in update_metrics_loop: {e}")







        time.sleep(2.0)























# ==============================================================================







# DIALOG NATIVE HANDLERS (Powershell / Windows Forms)







# ==============================================================================















def dialog_add_server():







    cfg = config_manager.load_or_create_config()







    cur_l = cfg.get("language", "id")







    title = "Tambah Server Baru" if cur_l == "id" else "Add New Server"







    msg = "Tentukan nama server, URL akses, dan kredensial login (opsional):" if cur_l == "id" else "Specify server name, access URL, and optional login credentials:"







    lbl1 = "Nama Server (contoh: Server Kantor, Server Rumah):" if cur_l == "id" else "Server Name (e.g. Office Server):"







    lbl2 = "URL Jalur Akses (contoh: http://<ip-server>:<port>):" if cur_l == "id" else "Access Route URL (e.g. http://<server-ip>:<port>):"







    lbl3 = "Nama Pengguna (opsional):" if cur_l == "id" else "Username (optional):"







    lbl4 = "Kata Sandi (opsional):" if cur_l == "id" else "Password (optional):"















    res = dialog_helper.run_powershell_dialog("setup_wizard", title, msg, lbl1, "New Server", lbl2, "http://", lbl3, "Admin", lbl4, "", "", "")







    if res.get("status") == "ok":







        s_name = (res.get("val1") or res.get("server_name") or "").strip()







        raw_u = (res.get("val2") or res.get("server_url") or "").strip()







        u_name = (res.get("val3") or res.get("username") or "").strip()







        p_pass = (res.get("val4") or res.get("password") or "").strip()







        zt_nwid = (res.get("val5") or res.get("zerotier_network_id") or "").strip()







        zt_vip = (res.get("val6") or res.get("zerotier_virtual_ip") or "").strip()















        if not s_name or not raw_u or raw_u in ("http://", "https://"):







            return







        formatted_u = config_manager.format_server_url(raw_u)







        new_id = f"srv_{int(time.time() * 1000)}"















        prof_list = ["Admin"]







        act_prof = "Admin"







        creds = {}







        if u_name:







            creds[act_prof] = {







                "username": u_name,







                "password": config_manager.encrypt_credential(p_pass) if p_pass else ""







            }















        new_srv = {







            "id": new_id,







            "zerotier_network_id": zt_nwid,







            "zerotier_virtual_ip": zt_vip,







            "name": s_name,







            "connections": [







                {







                    "id": f"conn_{int(time.time())}",







                    "name": "Local / Primary",







                    "url": formatted_u,







                }







            ],







            "active_connection": "auto",







            "profiles": prof_list,







            "active_profile": act_prof,







            "credentials": creds,







            "wake_on_lan": {







                "mac_address": "",







                "broadcast_ip": "255.255.255.255",







                "port": 9,







            },







        }







        cfg.setdefault("servers", []).append(new_srv)







        config_manager.save_config(cfg)







        logger_manager.log_info(f"[CoreService] Server '{s_name}' berhasil ditambahkan.")























def dialog_edit_server(target_srv_id=""):







    cfg = config_manager.load_or_create_config()







    servers = cfg.get("servers", [])







    target_srv = next((s for s in servers if s.get("id") == target_srv_id), None) if target_srv_id else config_manager.get_active_server(cfg)







    if not target_srv:







        return







    old_name = target_srv.get("name", "Server")







    res = dialog_helper.run_powershell_dialog("one_input", "Ubah Nama Server", f"Masukkan nama baru untuk server '{old_name}':", "Nama Server:", old_name)







    if res.get("status") == "ok":







        new_name = res.get("val", "").strip()







        if new_name and new_name != old_name:







            target_srv["name"] = new_name







            config_manager.save_config(cfg)







            logger_manager.log_info(f"[CoreService] Server diubah namanya menjadi '{new_name}'.")























def dialog_delete_server(srv_id_to_del=""):







    cfg = config_manager.load_or_create_config()







    servers = cfg.get("servers", [])







    if len(servers) <= 1:







        dialog_helper.prompt_alert("Pemberitahuan", "Minimal harus ada 1 server tersimpan.")







        return







    target_srv = next((s for s in servers if s.get("id") == srv_id_to_del), None) if srv_id_to_del else config_manager.get_active_server(cfg)







    if not target_srv:







        return







    sid = target_srv.get("id")







    if dialog_helper.prompt_confirm("Hapus Server", f"Hapus server '{target_srv.get('name')}' secara permanen?"):







        cfg["servers"] = [s for s in servers if s.get("id") != sid]







        if cfg.get("active_server_id") == sid:







            cfg["active_server_id"] = cfg["servers"][0]["id"]







        config_manager.save_config(cfg)







        invalidate_active_route_cache()







        logger_manager.log_info(f"[CoreService] Server '{sid}' berhasil dihapus.")























def dialog_add_route():







    cfg = config_manager.load_or_create_config()







    srv = config_manager.get_active_server(cfg)







    if not srv:







        return







    res = dialog_helper.run_powershell_dialog(







        "two_inputs",







        f"Tambah Jalur Akses ({srv.get('name', 'Server')})",







        "Masukkan label jalur dan URL akses server ini:",







        "Nama Jalur (contoh: Domain Publik, IP Lokal 2):",







        "New Route",







        "URL Jalur (contoh: https://server.domain.com):",







        "http://"







    )







    if res.get("status") == "ok":







        c_name = res.get("val1", "").strip()







        raw_u = res.get("val2", "").strip()







        if c_name and raw_u and raw_u not in ("http://", "https://"):







            formatted_u = config_manager.format_server_url(raw_u)







            c_id = f"conn_{int(time.time() * 1000)}"







            srv.setdefault("connections", []).append({







                "id": c_id,







                "name": c_name,







                "url": formatted_u







            })







            config_manager.save_config(cfg)







            logger_manager.log_info(f"[CoreService] Jalur '{c_name}' ({formatted_u}) ditambahkan.")























def dialog_edit_route(c_id_to_edit):







    cfg = config_manager.load_or_create_config()







    srv = config_manager.get_active_server(cfg)







    if not srv:







        return







    conns = srv.get("connections", [])







    target_conn = next((c for c in conns if c.get("id") == c_id_to_edit), None)







    if not target_conn:







        return







    res = dialog_helper.run_powershell_dialog(







        "two_inputs",







        f"Ubah Jalur Akses ({srv.get('name', 'Server')})",







        "Ubah nama label dan URL akses jalur ini:",







        "Nama Jalur:",







        target_conn.get("name", "Route"),







        "URL Jalur:",







        target_conn.get("url", "http://")







    )







    if res.get("status") == "ok":







        new_name = res.get("val1", "").strip()







        raw_u = res.get("val2", "").strip()







        if new_name and raw_u and raw_u not in ("http://", "https://"):







            target_conn["name"] = new_name







            target_conn["url"] = config_manager.format_server_url(raw_u)







            config_manager.save_config(cfg)







            logger_manager.log_info(f"[CoreService] Jalur '{new_name}' diperbarui.")























def dialog_delete_route(c_id_to_del):







    cfg = config_manager.load_or_create_config()







    srv = config_manager.get_active_server(cfg)







    if not srv:







        return







    conns = srv.get("connections", [])







    if len(conns) <= 1:







        dialog_helper.prompt_alert("Pemberitahuan", "Minimal harus ada 1 jalur akses tersimpan.")







        return







    srv["connections"] = [c for c in conns if c.get("id") != c_id_to_del]







    if srv.get("active_connection") == c_id_to_del:







        srv["active_connection"] = "auto"







    config_manager.save_config(cfg)







    logger_manager.log_info(f"[CoreService] Jalur '{c_id_to_del}' dihapus.")























def dialog_add_profile():







    cfg = config_manager.load_or_create_config()







    srv = config_manager.get_active_server(cfg)







    if not srv:







        return







    profiles = srv.setdefault("profiles", ["Admin"])







    default_prof = f"User-{len(profiles) + 1}"















    res = dialog_helper.run_powershell_dialog(







        "account_setup",







        f"Tambah Akun ({srv.get('name', 'Server')})",







        "Masukkan nama akun dan kredensial login:",







        "Nama Profil:",







        default_prof,







        "Nama Pengguna:",







        "",







        "Kata Sandi:",







        ""







    )







    if res.get("status") == "ok":







        p_name = res.get("val1", "").strip()







        u_name = res.get("val2", "").strip()







        p_pass = res.get("val3", "").strip()







        if p_name and u_name:







            if p_name in profiles:







                dialog_helper.prompt_alert("Pemberitahuan", "Nama profil ini sudah digunakan.")







                return







            profiles.append(p_name)







            srv["active_profile"] = p_name







            srv.setdefault("credentials", {})[p_name] = {







                "username": u_name,







                "password": config_manager.encrypt_credential(p_pass) if p_pass else ""







            }







            config_manager.save_config(cfg)







            logger_manager.log_info(f"[CoreService] Profil '{p_name}' berhasil ditambahkan.")























def dialog_edit_profile(target_p=""):







    cfg = config_manager.load_or_create_config()







    srv = config_manager.get_active_server(cfg)







    if not srv:







        return







    p = target_p or srv.get("active_profile", "Admin")







    res = dialog_helper.run_powershell_dialog(







        "one_input",







        f"Ubah Nama Akun ({srv.get('name', 'Server')})",







        f"Masukkan nama baru untuk akun '{p}':",







        "Nama Akun:",







        p







    )







    if res.get("status") == "ok":







        new_name = res.get("val", "").strip()







        if new_name and new_name != p:







            profiles = srv.get("profiles", ["Admin"])







            if new_name in profiles:







                dialog_helper.prompt_alert("Pemberitahuan", "Nama akun ini sudah ada.")







                return







            idx = profiles.index(p) if p in profiles else -1







            if idx >= 0:







                profiles[idx] = new_name







            if srv.get("active_profile") == p:







                srv["active_profile"] = new_name







            creds = srv.get("credentials", {})







            if p in creds:







                creds[new_name] = creds.pop(p)







            config_manager.save_config(cfg)







            logger_manager.log_info(f"[CoreService] Profil '{p}' diubah menjadi '{new_name}'.")























def dialog_delete_profile(target_p=""):







    cfg = config_manager.load_or_create_config()







    srv = config_manager.get_active_server(cfg)







    if not srv:







        return







    p = target_p or srv.get("active_profile", "Admin")







    profiles = srv.get("profiles", ["Admin"])







    if len(profiles) <= 1:







        dialog_helper.prompt_alert("Pemberitahuan", "Minimal harus ada 1 profil tersimpan.")







        return







    if dialog_helper.prompt_confirm("Hapus Akun", f"Hapus profil akun '{p}'?"):







        srv["profiles"] = [x for x in profiles if x != p]







        if srv.get("active_profile") == p:







            srv["active_profile"] = srv["profiles"][0]







        srv.get("credentials", {}).pop(p, None)







        config_manager.save_config(cfg)







        logger_manager.log_info(f"[CoreService] Profil '{p}' dihapus.")























def dialog_config_credentials():







    cfg = config_manager.load_or_create_config()







    srv = config_manager.get_active_server(cfg)







    if not srv:







        return







    srv_name = srv.get("name", "Server")







    act_p = srv.get("active_profile", "Admin")







    creds = config_manager.get_server_credentials(srv, act_p)







    existing_u = creds.get("username", "") or (act_p if act_p != "Admin" else "")







    existing_p = creds.get("password", "")















    res = dialog_helper.run_powershell_dialog(







        "account_setup",







        f"Kredensial: {srv_name} [{act_p}]",







        f"Perbarui atau masukkan kredensial login untuk '{srv_name}' (Akun: {act_p}):",







        "Nama Profil:",







        act_p,







        "Nama Pengguna:",







        existing_u,







        "Kata Sandi:",







        existing_p







    )







    if res.get("status") == "ok":







        u_in = (res.get("val2") or res.get("username") or "").strip()







        p_in = (res.get("val3") or res.get("password") or "").strip()







        if u_in:







            srv.setdefault("credentials", {})[act_p] = {







                "username": u_in,







                "password": config_manager.encrypt_credential(p_in) if p_in else ""







            }







            config_manager.save_config(cfg)







            logger_manager.log_info(f"[CoreService] Kredensial untuk '{act_p}' berhasil diperbarui.")























def dialog_join_zerotier():







    if not zerotier_manager.is_zerotier_installed():







        if dialog_helper.prompt_confirm("ZeroTier Belum Terpasang", "Layanan ZeroTier belum terpasang.\nApakah Anda ingin memasang ZeroTier One otomatis sekarang?"):







            ok_inst, msg_inst = zerotier_manager.install_zerotier_silently()







            if not ok_inst:







                dialog_helper.prompt_alert("Instalasi Gagal", f"Tidak dapat memasang ZeroTier One:\n{msg_inst}")







                return







        else:







            return















    client = zerotier_manager.ZeroTierClient()







    ok, status = client.is_service_running()







    if not ok:







        dialog_helper.prompt_alert("ZeroTier One", "Service ZeroTier One belum merespons di port 9993.")







        return















    cfg = config_manager.load_or_create_config()







    srv = config_manager.get_active_server(cfg)







    target_nwid = (srv.get("zerotier_network_id") or srv.get("remote_id") or "").strip() if srv else ""















    if not target_nwid:







        res = dialog_helper.run_powershell_dialog(







            "one_input",







            "Konfigurasi Remote ID (ZeroTier)",







            "Masukkan 16-digit Remote ID dari menu Remote Access ZimaOS Anda:",







            "Remote ID (Network ID):",







            ""







        )







        if res.get("status") == "ok" and res.get("val"):







            input_val = str(res["val"]).strip().lower()







            if zerotier_manager.validate_network_id(input_val):







                target_nwid = input_val







                if srv:







                    srv["zerotier_network_id"] = target_nwid







                    config_manager.save_config(cfg)







            else:







                dialog_helper.prompt_alert("Format Salah", "Remote ID harus terdiri dari tepat 16 karakter heksadesimal.")







                return







        else:







            return















    success, res = client.join_network(target_nwid)







    if success:







        found_ip = ""







        for _ in range(8):







            time.sleep(1.0)







            is_ok, net_info = client.is_connected_to_network(target_nwid)







            if is_ok:







                break







        if srv:







            found_ip = sync_server_zerotier_ip(srv.get("id"))







        ip_info_str = f"\nIP Virtual Server: {found_ip}" if found_ip else ""







        dialog_helper.prompt_alert("ZeroTier Remote", f"Berhasil bergabung ke Remote ID ZimaOS ({target_nwid})!\nJaringan P2P terenkripsi sekarang aktif.{ip_info_str}")







    else:







        dialog_helper.prompt_alert("Koneksi ZeroTier Gagal", f"Gagal bergabung ke jaringan ZeroTier: {res}")























# ==============================================================================







# HTTP JSON API HANDLER







# ==============================================================================
























def cleanup_temp_update_artifacts():
    """
    Membersihkan HANYA berkas sisa artefak pembaruan MyServer di folder %TEMP% (> 60 detik).
    Mematuhi Pasal 2 (Zero Data Risk): hanya memindai %TEMP% dan hanya menyentuh berkas
    dengan prefix resmi ('myserver_update_', 'myserver_upd_', 'myserver_ext_').
    """
    try:
        temp_dir = os.environ.get("TEMP", tempfile.gettempdir())
        if not os.path.isdir(temp_dir):
            return
        now = time.time()
        ALLOWED_PREFIXES = ("myserver_update_", "myserver_upd_", "myserver_ext_")
        for item_name in os.listdir(temp_dir):
            lower_name = item_name.lower()
            if not any(lower_name.startswith(pfx) for pfx in ALLOWED_PREFIXES):
                continue
            full_path = os.path.join(temp_dir, item_name)
            try:
                # Lewati jika usia berkas kurang dari 60 detik
                if now - os.path.getmtime(full_path) < 60:
                    continue
                if os.path.isfile(full_path) or os.path.islink(full_path):
                    os.remove(full_path)
                elif os.path.isdir(full_path):
                    shutil.rmtree(full_path, ignore_errors=True)
            except Exception:
                pass
    except Exception:
        pass

def apply_zip_update(zip_file_path=None):



    """



    Menerapkan pembaruan aplikasi MyServer dari berkas ZIP portabel:



    1. Validasi berkas ZIP & ekstraksi ke direktori karantina sementara (%TEMP%).



    2. Pemindaian executable biner target secara dinamis.



    3. Dialog konfirmasi pengguna native Windows.



    4. Eksekusi skrip updater batch mandiri yang mematikan proses lama & mengganti biner tanpa mengganggu konfigurasi / sesi DPAPI (Pasal 2).



    """



    cfg = config_manager.load_or_create_config()



    cur_l = cfg.get("language", "en")







    if not zip_file_path:



        title = "Select MyServer Update Package (.zip)" if cur_l == "en" else "Pilih Berkas Pembaruan MyServer (.zip)"



        zip_file_path = dialog_helper.prompt_choose_file(title)



        if not zip_file_path:



            return {"cancelled": True}







    if not os.path.isfile(zip_file_path):



        msg = "ZIP file not found." if cur_l == "en" else "Berkas ZIP tidak ditemukan."



        dialog_helper.prompt_alert("Error", msg)



        return {"success": False, "error": msg}







    if not zipfile.is_zipfile(zip_file_path):



        msg = "Selected file is not a valid ZIP archive." if cur_l == "en" else "Berkas yang dipilih bukan arsip ZIP valid."



        dialog_helper.prompt_alert("Error", msg)



        return {"success": False, "error": msg}







    temp_extract_dir = os.path.join(



        os.environ.get("TEMP", os.path.expanduser("~")),



        f"myserver_ext_{int(time.time())}"



    )







    exe_full_path = None



    new_exe_name = None







    try:



        os.makedirs(temp_extract_dir, exist_ok=True)



        with zipfile.ZipFile(zip_file_path, "r") as zf:



            zf.extractall(temp_extract_dir)

        # Dynamic & prioritized binary selection (v3.12.0)
        found_exes = []
        for root, dirs, files in os.walk(temp_extract_dir):
            for fname in files:
                if fname.lower().endswith(".exe"):
                    found_exes.append((fname, os.path.join(root, fname)))

        primary_entry = None
        # 1. Exact match MyServer-Beta.exe or MyServer.exe
        for fname, fpath in found_exes:
            if fname.lower() in ("myserver-beta.exe", "myserver.exe"):
                primary_entry = (fname, fpath)
                break

        # 2. Starts with MyServer but not myserver-core and not syncthing
        if not primary_entry:
            for fname, fpath in found_exes:
                fl = fname.lower()
                if fl.startswith("myserver") and not fl.startswith("myserver-core") and "syncthing" not in fl:
                    primary_entry = (fname, fpath)
                    break

        # 3. Any non-core, non-syncthing exe
        if not primary_entry:
            for fname, fpath in found_exes:
                fl = fname.lower()
                if not fl.startswith("myserver-core") and "syncthing" not in fl:
                    primary_entry = (fname, fpath)
                    break

        if primary_entry:
            new_exe_name, exe_full_path = primary_entry
        elif found_exes:
            new_exe_name, exe_full_path = found_exes[0]

    except Exception as e:



        logger_manager.log_error(f"[ZipUpdate] Ekstraksi ZIP gagal: {e}")



        msg = f"Failed to extract ZIP: {e}" if cur_l == "en" else f"Gagal mengekstrak ZIP: {e}"



        dialog_helper.prompt_alert("Error", msg)



        shutil.rmtree(temp_extract_dir, ignore_errors=True)



        return {"success": False, "error": msg}







    if not new_exe_name or not exe_full_path:



        msg = "The ZIP archive does not contain a valid .exe executable." if cur_l == "en" else "Berkas ZIP tidak berisi biner executable (.exe) yang valid."



        dialog_helper.prompt_alert("Invalid Package" if cur_l == "en" else "Paket Tidak Valid", msg)



        shutil.rmtree(temp_extract_dir, ignore_errors=True)



        return {"success": False, "error": msg}







    source_copy_dir = os.path.dirname(exe_full_path)
    # Zero Data Risk (Pasal 2): Prevent overwriting live user configuration from ZIP package
    for cfg_f in ("config.json", "config.json.bak"):
        extracted_cfg = os.path.join(source_copy_dir, cfg_f)
        if os.path.isfile(extracted_cfg):
            try:
                os.remove(extracted_cfg)
            except Exception:
                pass







    confirm_title = "Confirm Update" if cur_l == "en" else "Konfirmasi Pembaruan"



    confirm_msg = (



        f"Apply update / version switch?\n\n"



        f"• Target executable: {new_exe_name}\n"



        f"• Settings & login sessions: SAFE.\n"



        f"• The application will restart to {new_exe_name} automatically."



        if cur_l == "en"



        else (



            f"Menerapkan Pembaruan / Perpindahan Versi?\n\n"



            f"• File target eksekusi: {new_exe_name}\n"



            f"• Pengaturan & sesi login: TETAP AMAN.\n"



            f"• Aplikasi akan beralih dan membuka {new_exe_name} secara otomatis."



        )



    )







    if not dialog_helper.prompt_confirm(confirm_title, confirm_msg):



        shutil.rmtree(temp_extract_dir, ignore_errors=True)



        return {"cancelled": True}







    gui_exe = get_gui_executable_path()



    if gui_exe and os.path.isfile(gui_exe):



        app_dir = os.path.dirname(gui_exe)



    else:



        app_dir = config_manager.get_base_dir()







    current_pid = os.getpid()



    gui_pid = int(_gui_exe_cache.get("parent_pid", 0) or 0)



    was_autorun = is_autorun_enabled()







    temp_updater_bat = os.path.join(



        os.environ.get("TEMP", os.path.expanduser("~")),



        f"myserver_upd_{int(time.time())}.bat"



    )







    autorun_cmd = (



        f'reg add "HKCU\\{REG_KEY}" /v "{APP_NAME}" /t REG_SZ /d "\"%APP_DIR%\\{new_exe_name}\" --tray" /f >nul 2>&1'



        if was_autorun



        else ""



    )







    # Hentikan daemon EasyTier & Syncthing terlebih dahulu secara teratur agar handle berkas dilepas
    shutdown_background_daemons()
    time.sleep(0.3)

    kill_gui_cmd = f"taskkill /PID {gui_pid} /F >nul 2>&1" if gui_pid > 0 else ""

    bat_content = f"""@echo off
chcp 65001 >nul
ping 127.0.0.1 -n 2 >nul
{kill_gui_cmd}
taskkill /F /IM MyServer-Beta.exe /IM MyServer.exe /IM syncthing.exe /IM easytier-core.exe /IM easytier-cli.exe >nul 2>&1
taskkill /PID {current_pid} /F >nul 2>&1
taskkill /F /IM myserver-core.exe /IM easytier-core.exe /IM easytier-cli.exe >nul 2>&1
ping 127.0.0.1 -n 4 >nul
set "APP_DIR={app_dir}"
set "TEMP_DIR={source_copy_dir}"
set "ROOT_TEMP_DIR={temp_extract_dir}"
set "TARGET_EXE={new_exe_name}"
robocopy "%TEMP_DIR%" "%APP_DIR%" /E /R:3 /W:1 /XF config.json config.json.bak /NFL /NDL /NJH /NJS >nul 2>&1
if errorlevel 8 (
    powershell -NoProfile -Command "Start-Process robocopy -ArgumentList '\"%TEMP_DIR%\" \"%APP_DIR%\" /E /R:3 /W:1 /XF config.json config.json.bak /NFL /NDL /NJH /NJS' -Verb RunAs -Wait" >nul 2>&1
)
cd /d "%APP_DIR%"
{autorun_cmd}
start "" "%APP_DIR%\\{new_exe_name}"
ping 127.0.0.1 -n 2 >nul
rmdir /s /q "%ROOT_TEMP_DIR%" >nul 2>&1
del "%~f0" >nul 2>&1
exit
"""



    try:



        with open(temp_updater_bat, "w", encoding="utf-8") as f:



            f.write(bat_content)







        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(["cmd.exe", "/c", temp_updater_bat], creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW)







        def _exit_later():



            time.sleep(1.0)



            os._exit(0)



        threading.Thread(target=_exit_later, daemon=True).start()







        return {"success": True, "restarting": True, "targetExe": new_exe_name}



    except Exception as err:



        logger_manager.log_error(f"[ZipUpdate] Eksekusi updater gagal: {err}")



        msg = f"Failed to execute update: {err}" if cur_l == "en" else f"Gagal menjalankan updater: {err}"



        dialog_helper.prompt_alert("Update Error" if cur_l == "en" else "Kesalahan Pembaruan", msg)



        return {"success": False, "error": str(err)}







_latest_github_update_cache = None
_last_update_balloon_time = 0.0

def _trigger_windows_balloon(title: str, msg: str) -> None:
    """Memicu notifikasi balon native Windows di system tray secara non-blocking."""
    try:
        import mini_tray_manager
        mini_tray_manager.show_balloon(title, msg)
        return
    except Exception:
        pass
    if sys.platform != "win32":
        return
    try:
        import base64
        clean_title = title.replace('"', '`"')
        clean_msg = msg.replace('"', '`"')
        ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.BalloonTipIcon = "Info"
$notify.BalloonTipTitle = "{clean_title}"
$notify.BalloonTipText = "{clean_msg}"
$notify.Visible = $true
$notify.ShowBalloonTip(4000)
Start-Sleep -Seconds 1
$notify.Dispose()
"""
        encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
            creationflags=0x08000000
        )
    except Exception as e:
        logger_manager.log_debug(f"[TrayBalloon] Gagal memicu notifikasi balon: {e}")


def check_github_update_core() -> dict:
    """Fungsi terpusat untuk memeriksa rilis terbaru dari repositori GitHub."""
    global _latest_github_update_cache
    cfg = config_manager.load_or_create_config()
    repo_slug = cfg.get("github_repo", "Gibranibang/My-Server-beta")
    url = f"https://api.github.com/repos/{repo_slug}/releases/latest"
    headers = {
        "User-Agent": f"MyServer-Companion/{APP_VERSION_NUMBER}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            rel_data = json.loads(resp.read().decode("utf-8"))
            tag = rel_data.get("tag_name", "").lstrip("v").strip()

            def _parse_ver(v_str):
                import re
                parts = re.findall(r"\d+", v_str)
                return tuple(map(int, parts)) if parts else (0, 0, 0)

            remote_ver = _parse_ver(tag)
            curr_ver = _parse_ver(APP_VERSION_NUMBER)

            if remote_ver > curr_ver:
                download_url = rel_data.get("html_url", "")
                setup_asset = None
                for asset in rel_data.get("assets", []):
                    aname = asset.get("name", "").lower()
                    if "setup" in aname and aname.endswith(".exe"):
                        setup_asset = asset.get("browser_download_url")
                        break
                    elif aname.endswith(".exe") and not setup_asset:
                        setup_asset = asset.get("browser_download_url")
                    elif aname.startswith("myserver") and aname.endswith(".zip") and not setup_asset:
                        setup_asset = asset.get("browser_download_url")
                if setup_asset:
                    download_url = setup_asset
                res = {
                    "upToDate": False,
                    "version": tag,
                    "currentVersion": APP_VERSION_NUMBER,
                    "htmlUrl": rel_data.get("html_url", ""),
                    "downloadUrl": download_url,
                    "name": rel_data.get("name", f"MyServer v{tag}"),
                    "body": rel_data.get("body", "")
                }
                _latest_github_update_cache = res
                return res
            else:
                res = {
                    "upToDate": True,
                    "version": APP_VERSION_NUMBER,
                    "currentVersion": APP_VERSION_NUMBER,
                    "message": "Aplikasi sudah menggunakan versi terbaru."
                }
                _latest_github_update_cache = res
                return res
    except urllib.error.HTTPError as he:
        if he.code == 404:
            return {
                "upToDate": True,
                "version": APP_VERSION_NUMBER,
                "currentVersion": APP_VERSION_NUMBER,
                "message": "Aplikasi sudah menggunakan versi terbaru (Belum ada rilis baru di GitHub)."
            }
        return {
            "upToDate": True,
            "version": APP_VERSION_NUMBER,
            "warning": f"HTTP {he.code}: {he.reason}"
        }
    except Exception as ex:
        return {
            "upToDate": True,
            "version": APP_VERSION_NUMBER,
            "warning": f"Gagal menghubungi GitHub: {str(ex)}"
        }


def auto_update_checker_loop():
    """Worker background periodik: memeriksa update GitHub setiap 45 menit (2700 detik)."""
    global _last_update_balloon_time
    time.sleep(15)  # Tunggu 15 detik setelah boot
    while True:
        try:
            cfg = config_manager.load_or_create_config()
            auto_check = cfg.get("auto_check_update", True)
            if auto_check:
                info = check_github_update_core()
                if info and not info.get("upToDate"):
                    now = time.time()
                    if now - _last_update_balloon_time > 2700:  # 1 notifikasi per siklus 45 menit jika update belum dipasang
                        _last_update_balloon_time = now
                        logger_manager.log_info(f"[AutoUpdateLoop] Update terdeteksi (v{info.get('version')}), memicu notifikasi Windows tray...")
                        _trigger_windows_balloon(
                            "Pembaruan Tersedia",
                            "MyServer versi terbaru telah dirilis di GitHub."
                        )
        except Exception as e:
            logger_manager.log_debug(f"[AutoUpdateLoop] Kesalahan: {e}")
        time.sleep(2700)


def auto_start_easytier_worker():
    """Memulai koneksi EasyTier di background saat startup jika dikonfigurasi aktif."""
    time.sleep(4)
    try:
        if easytier_manager:
            cfg = config_manager.load_or_create_config()
            et_cfg = cfg.get("easytier", {})
            if et_cfg.get("enabled"):
                rid = et_cfg.get("remote_id")
                net_name = et_cfg.get("network_name")
                net_secret = et_cfg.get("network_secret")
                ipv4 = et_cfg.get("ipv4")
                peers = et_cfg.get("peers") or []
                if rid or (net_name and net_secret):
                    logger_manager.log_info(f"[EasyTier] Memulai koneksi otomatis startup: {rid or net_name}")
                    mgr = easytier_manager.get_easytier_manager()
                    mgr.start_easytier(
                        remote_id=rid,
                        network_name=net_name,
                        network_secret=net_secret,
                        ipv4=ipv4,
                        peers=peers
                    )
    except Exception as e:
        logger_manager.log_debug(f"[EasyTierAutoStart] Error: {e}")


class CoreApiHandler(BaseHTTPRequestHandler):







    """Handler HTTP JSON API ringan dengan dukungan penuh CORS untuk WebView Tauri."""















    def _set_cors_headers(self):







        self.send_header("Access-Control-Allow-Origin", "*")







        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")







        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")















    def do_OPTIONS(self):







        self.send_response(200)







        self._set_cors_headers()







        self.end_headers()















    def _send_json(self, data, status=200):



        try:



            body = json.dumps(data).encode("utf-8")



            self.send_response(status)



            self.send_header("Content-Type", "application/json; charset=utf-8")



            self.send_header("Content-Length", str(len(body)))



            self.send_header("Connection", "close")



            self._set_cors_headers()



            self.end_headers()



            self.wfile.write(body)



            self.wfile.flush()



        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):



            pass







    def do_GET(self):







        path = urllib.parse.urlparse(self.path).path







        
        if path == "/api/get_log_directory":
            self._send_json(logger_manager.get_log_status() if hasattr(logger_manager, "get_log_status") else {"logDirectory": "", "defaultDirectory": "", "isCustom": False})
            return

        if path == "/api/ping":







            self._send_json({"status": "ok", "app": "MyServer-Core", "version": CORE_VERSION})







        elif path in ("/api/state", "/api/get_state"):







            with _state_lock:







                self._send_json(_cached_state)







        elif path == "/api/list_drives":







            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)



            force_flag = query.get("force", ["0"])[0].lower() in ("1", "true")



            self._send_json(get_live_drives_list(force=force_flag))







        elif path == "/api/probe_url":







            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)







            target_url = query.get("url", [""])[0]







            self._send_json(probe_url_endpoint(target_url))







        elif path == "/api/get_activity_log":







            log_summary = logger_manager.get_recent_log_summary(50)







            lines = [l.rstrip() for l in log_summary.splitlines() if l.strip()]







            self._send_json({"lines": lines})







        elif path == "/api/list_web_apps":







            self._send_json(get_web_apps_list())







        elif path == "/api/get_server_details":







            self._send_json(get_server_details_data())

        elif path in ("/api/server/backend_status", "/api/server_backend_status"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            req_srv_id = (query.get("serverId", [""])[0] or query.get("server_id", [""])[0]).strip() or None
            self._send_json(_get_backend_health_info(force=True, target_server_id=req_srv_id))

        elif path in ("/api/smb/source", "/api/smb_source"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            req_srv_id = (query.get("serverId", [""])[0] or query.get("server_id", [""])[0]).strip() or None
            get_body = {"action": "get"}
            if req_srv_id:
                get_body["serverId"] = req_srv_id
            status_code, res = _handle_smb_source_request(get_body)
            self._send_json(res, status=status_code)







        elif path in ("/api/easytier/status", "/api/easytier_status"):
            if easytier_manager:
                mgr = easytier_manager.get_easytier_manager()
                status = mgr.get_status_overview()
                self._send_json({"success": True, "data": status, **status})
            else:
                self._send_json({"success": False, "running": False, "error": "easytier_manager not available", "data": {"running": False}})
        elif path in ("/api/vms", "/api/vms/load"):
            cfg = config_manager.load_or_create_config()
            now_ts = time.time()
            local_vms = [
                v for v in (cfg.get("vms", []) or [])
                if isinstance(v, dict) and _deleted_vms_tombstone.get(v.get("id"), 0) <= now_ts
            ]
            for vm in local_vms:
                if not vm.get("scope"):
                    vm["scope"] = "local"
                _apply_recent_vm_mutation(vm)

            server_vms, server_online = _fetch_server_vms_from_backend(cfg, now_ts)

            seen_ids = set()
            combined = []
            for vm in server_vms:
                seen_ids.add(vm.get("id"))
                combined.append(vm)
            for vm in local_vms:
                if not isinstance(vm, dict):
                    continue
                vid = vm.get("id")
                vscope = vm.get("scope") or ("server" if vm.get("serverId") or vm.get("serverName") else "local")
                if vid not in seen_ids:
                    if vscope != "server" or not server_online:
                        seen_ids.add(vid)
                        combined.append(vm)

            if combined != cfg.get("vms"):
                cfg["vms"] = combined
                config_manager.save_config(cfg)

            self._send_json({"status": "ok", "vms": combined})
        elif path == "/api/instabox/vms":
            if instabox_manager:
                vms = instabox_manager.InstaBoxManager.list_vms()
                self._send_json({"status": "ok", "vms": vms})
            else:
                self._send_json({"status": "error", "message": "instabox_manager not available"}, status=500)
        elif path == "/api/instabox/status":
            vm_id = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id", [""])[0]
            if instabox_manager and vm_id:
                res = instabox_manager.InstaBoxManager.sync_vm_status(vm_id)
                self._send_json(res)
            elif instabox_manager:
                vms = instabox_manager.InstaBoxManager.list_vms()
                self._send_json({"status": "ok", "vms": vms})
            else:
                self._send_json({"status": "error", "message": "instabox_manager not available"}, status=500)
        elif path in ("/api/remote/status", "/api/remote_status"):
            et_status = easytier_manager.get_easytier_manager().get_status_overview() if easytier_manager else {"running": False}
            zt_client = zerotier_manager.ZeroTierClient() if "zerotier_manager" in globals() else None
            zt_node = zt_client.get_node_status() if zt_client else {"online": False}
            zt_nets = zt_client.get_joined_networks() if (zt_client and zt_node.get("online")) else []
            active_engine = "none"
            if et_status.get("running"):
                active_engine = "easytier"
            elif zt_node.get("online") and len(zt_nets) > 0:
                active_engine = "zerotier"
            self._send_json({
                "activeEngine": active_engine,
                "easytier": et_status,
                "zerotier": {
                    "running": zt_node.get("online", False),
                    "nodeId": zt_node.get("address", ""),
                    "version": zt_node.get("version", ""),
                    "networks": zt_nets
                }
            })
        else:
            self._send_json({"error": "Not Found"}, status=404)















    def do_POST(self):



        global _active_local_st_client, _active_local_st_key, _active_srv_st_client, _active_srv_st_key







        path = urllib.parse.urlparse(self.path).path







        content_length = int(self.headers.get("Content-Length", 0))







        body = {}







        if content_length > 0:







            try:







                body = json.loads(self.rfile.read(content_length).decode("utf-8"))







            except Exception:







                pass















        # ----------------------------------------------------------------------







        # SESI 1: Navigasi, Dashboard, Daya & WoL







        # ----------------------------------------------------------------------







        if path in ("/api/get_state", "/api/state"):







            with _state_lock:







                self._send_json(_cached_state)







            return















        if path == "/api/probe_url":







            target_url = (body.get("url") or body.get("arg") or "").strip()







            self._send_json(probe_url_endpoint(target_url))







            return















        if path == "/api/get_activity_log":







            log_summary = logger_manager.get_recent_log_summary(50)







            lines = [l.rstrip() for l in log_summary.splitlines() if l.strip()]







            self._send_json({"lines": lines})







            return















        if path == "/api/open_log_file":







            ok = logger_manager.open_log_in_editor()







            self._send_json({"success": ok})







            return















        if path == "/api/open_log_folder":







            ok = logger_manager.open_log_folder_in_explorer()







            self._send_json({"success": ok})







            return















        if path in ("/api/open_dashboard", "/api/open_url", "/api/open_app_window"):
            srv = None
            cfg = config_manager.load_or_create_config()
            srv = config_manager.get_active_server(cfg)
            target_url = (body.get("url") or body.get("arg") or "").strip()
            win_title = (body.get("title") or "").strip()
            if not target_url or target_url == "server" or "127.0.0.1" in target_url:
                target_url, _ = get_active_resolved_route(cfg)
                if not win_title and srv:
                    win_title = f"{srv.get('name', 'MyServer')} Dashboard"
            elif not win_title:
                win_title = "MyServer Web App"
            if target_url:
                srv_id = srv.get("id") if srv else None
                success, msg = spawn_app_window(target_url, win_title, server_id=srv_id)
                self._send_json({"success": success, "message": msg, "url": target_url, "title": win_title})







            else:







                self._send_json({"success": False, "message": "URL tidak valid"})







            return















        if path in ("/api/open_external_browser",):







            target_url = (body.get("url") or body.get("arg") or "").strip()







            if not target_url or target_url == "server" or "127.0.0.1" in target_url:







                cfg = config_manager.load_or_create_config()







                srv = config_manager.get_active_server(cfg)







                target_url, _ = get_active_resolved_route(cfg)







            if target_url:







                try:







                    if sys.platform == "win32":







                        os.startfile(target_url)







                    else:







                        webbrowser.open(target_url)







                    logger_manager.log_info(f"[CoreService] Membuka URL di browser luar: {target_url}")







                    self._send_json({"success": True, "url": target_url})







                except Exception as e:







                    logger_manager.log_error(f"[CoreService] Gagal membuka browser luar: {e}")







                    self._send_json({"success": False, "message": str(e)})







            else:







                self._send_json({"success": False, "message": "URL tidak valid"})







            return















        if path == "/api/power_action":







            self._send_json({"success": True, "action": "power_menu"})







            return















        if path == "/api/reboot":







            def _do_reboot():







                try:







                    cfg = config_manager.load_or_create_config()







                    srv = config_manager.get_active_server(cfg)







                    if not srv:







                        return False, "Server tidak ditemukan"







                    act_p = srv.get("active_profile", "Admin")







                    creds = config_manager.get_server_credentials(srv, act_p)







                    active_u, _ = get_active_resolved_route(cfg)







                    parsed = urllib.parse.urlparse(active_u)







                    client = zima_metrics_manager.ZimaMetricsClient(







                        host=parsed.hostname or "127.0.0.1",







                        port=str(parsed.port) if parsed.port else ("443" if parsed.scheme.lower() == "https" else "80"),







                        use_https=(parsed.scheme.lower() == "https"),







                        username=creds.get("username", ""),







                        password=creds.get("password", ""),







                        server_connections=srv.get("connections", []),







                        server_name=srv.get("name", ""),



                        zerotier_ip=get_active_remote_ip(srv),







                    )







                    client.authenticate()



                    try:



                        _unmount_myserver_smb_drives(reason="server_power_action", include_easytier_subnet=True)



                    except Exception:



                        pass



                    return client.system_control("restart")







                except Exception as e:







                    logger_manager.log_error(f"[CoreService] Gagal reboot server: {e}")







                    return False, str(e)







            ok, msg = _do_reboot()



            if ok:



                global _active_metrics_client, _active_metrics_client_key



                _active_metrics_client = None



                _active_metrics_client_key = None



                with _state_lock:



                    _cached_state["is_online"] = False



                    _cached_state["ping_str"] = "--"



                    _cached_state["cpu_percent"] = 0



                    _cached_state["ram_percent"] = 0







            self._send_json({"success": ok, "message": msg})







            return















        if path == "/api/shutdown":







            def _do_shutdown():







                try:







                    cfg = config_manager.load_or_create_config()







                    srv = config_manager.get_active_server(cfg)







                    if not srv:







                        return False, "Server tidak ditemukan"







                    act_p = srv.get("active_profile", "Admin")







                    creds = config_manager.get_server_credentials(srv, act_p)







                    active_u, _ = get_active_resolved_route(cfg)







                    parsed = urllib.parse.urlparse(active_u)







                    client = zima_metrics_manager.ZimaMetricsClient(







                        host=parsed.hostname or "127.0.0.1",







                        port=str(parsed.port) if parsed.port else ("443" if parsed.scheme.lower() == "https" else "80"),







                        use_https=(parsed.scheme.lower() == "https"),







                        username=creds.get("username", ""),







                        password=creds.get("password", ""),







                        server_connections=srv.get("connections", []),







                        server_name=srv.get("name", ""),



                        zerotier_ip=get_active_remote_ip(srv),







                    )







                    client.authenticate()



                    try:



                        _unmount_myserver_smb_drives(reason="server_power_action", include_easytier_subnet=True)



                    except Exception:



                        pass



                    return client.system_control("off")







                except Exception as e:







                    logger_manager.log_error(f"[CoreService] Gagal shutdown server: {e}")







                    return False, str(e)







            ok, msg = _do_shutdown()



            if ok:



                _active_metrics_client = None



                _active_metrics_client_key = None



                with _state_lock:



                    _cached_state["is_online"] = False



                    _cached_state["ping_str"] = "--"



                    _cached_state["cpu_percent"] = 0



                    _cached_state["ram_percent"] = 0







            self._send_json({"success": ok, "message": msg})







            return















        if path == "/api/wake_on_lan":







            mac = (body.get("mac") or body.get("arg") or "").strip()







            if not mac:







                cfg = config_manager.load_or_create_config()







                srv = config_manager.get_active_server(cfg)







                mac = (srv.get("wake_on_lan", {}).get("mac_address") or "").strip() if srv else ""







            if mac:







                wol_manager.send_magic_packet(mac)







                logger_manager.log_info(f"[CoreService] Mengirim Magic Packet WoL ke: {mac}")







                self._send_json({"success": True, "mac": mac})







            else:







                self._send_json({"success": False, "message": "No MAC provided"})







            return















        if path == "/api/detect_mac":







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg)







            srv_mac = (srv.get("wake_on_lan", {}).get("mac_address") or "").strip().upper() if srv else ""







            active_u, _ = get_active_resolved_route(cfg)







            parsed = urllib.parse.urlparse(active_u)







            host = parsed.hostname or "127.0.0.1"







            detected = (wol_manager.detect_mac_from_arp(host) if hasattr(wol_manager, "detect_mac_from_arp") else "") or ""



            detected = detected.strip().upper()







            if detected:







                if srv:







                    if "wake_on_lan" not in srv or not isinstance(srv.get("wake_on_lan"), dict):







                        srv["wake_on_lan"] = {}







                    srv["wake_on_lan"]["mac_address"] = detected







                    config_manager.save_config(cfg)







                logger_manager.log_info(f"[CoreService] MAC terdeteksi dari ARP ({host}): {detected}")







                self._send_json(detected)







            elif srv_mac:







                self._send_json(srv_mac)







            else:







                self._send_json("")







            return















        if path == "/api/save_mac":







            mac = (body.get("mac") or body.get("arg") or "").strip().upper()







            if mac:







                cfg = config_manager.load_or_create_config()







                srv = config_manager.get_active_server(cfg)







                if srv:







                    if "wake_on_lan" not in srv or not isinstance(srv.get("wake_on_lan"), dict):







                        srv["wake_on_lan"] = {}







                    srv["wake_on_lan"]["mac_address"] = mac







                    config_manager.save_config(cfg)







                    logger_manager.log_info(f"[CoreService] MAC address disimpan: {mac}")







                self._send_json({"success": True, "mac": mac})







            else:







                self._send_json({"success": False, "message": "MAC tidak valid"})







            return















        # ----------------------------------------------------------------------







        # SESI 2: File Management & SMB Mounting







        # ----------------------------------------------------------------------







        if path == "/api/list_drives":







            force_flag = bool(body.get("force", False))



            self._send_json(get_live_drives_list(force=force_flag))







            return















        if path == "/api/set_all_mounted":







            mounted = body.get("mounted") if "mounted" in body else body.get("arg", True)







            if mounted:







                mount_active_server_smb()







            else:







                _unmount_myserver_smb_drives(reason="manual_unmount_all", include_all_servers=True, include_easytier_subnet=True)







            refresh_drives_cache_immediately()







            time.sleep(0.3)







            self._send_json(get_live_drives_list())







            return















        if path == "/api/open_drive":







            letter = (body.get("letter") or body.get("arg") or "").strip()







            if letter:







                clean_letter = letter.strip(":").upper() + ":"







                ok_open, msg_open = _unpack_explorer_result(smb_mount_manager.open_drive_in_explorer(clean_letter))
                if ok_open:
                    self._send_json({"success": True, "drive": clean_letter})
                else:
                    self._send_json({"success": False, "error": msg_open or f"Gagal membuka {clean_letter} di Explorer", "drive": clean_letter})







            else:







                self._send_json({"success": False, "message": "Drive letter kosong"})







            return















        if path == "/api/open_primary_disk":







            sh_name, d_letter = get_primary_mounted_share()







            if d_letter:
                ok_open, msg_open = _unpack_explorer_result(smb_mount_manager.open_drive_in_explorer(d_letter))
                if ok_open:
                    self._send_json({"success": True, "drive": d_letter})
                else:
                    self._send_json({"success": False, "error": msg_open or f"Gagal membuka {d_letter} di Explorer", "drive": d_letter})







            else:







                # Coba pasang terlebih dahulu







                mount_active_server_smb()







                time.sleep(0.5)







                sh_name, d_letter = get_primary_mounted_share()







                if d_letter:
                    ok_open, msg_open = _unpack_explorer_result(smb_mount_manager.open_drive_in_explorer(d_letter))
                    if ok_open:
                        self._send_json({"success": True, "drive": d_letter})
                    else:
                        self._send_json({"success": False, "error": msg_open or f"Gagal membuka {d_letter} di Explorer", "drive": d_letter})







                else:







                    self._send_json({"success": False, "message": "Tidak ada partisi SMB terpasang"})







            return















        if path == "/api/open_unc":







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg)







            active_u, _ = get_active_resolved_route(cfg)







            conns = srv.get("connections", []) if srv else []







            host, is_domain, zt_ip = _resolve_smb_route_params(srv, active_u)







            ok_open, msg_open = _unpack_explorer_result(smb_mount_manager.open_unc_root_in_explorer(
                host,
                server_connections=conns,
                is_domain_route=is_domain,
                zerotier_ip=zt_ip,
            ))
            if ok_open:
                self._send_json({"success": True, "host": host})
            else:
                self._send_json({"success": False, "error": msg_open or f"Host SMB ({host}:445) tidak merespons", "host": host})







            return



        if path == "/api/open_file_explorer":



            sh_name, d_letter = get_primary_mounted_share()



            if not d_letter:



                mount_active_server_smb()



                time.sleep(0.5)



                sh_name, d_letter = get_primary_mounted_share()



            if d_letter:
                ok_open, msg_open = _unpack_explorer_result(smb_mount_manager.open_drive_in_explorer(d_letter))
                if ok_open:
                    self._send_json({"success": True, "drive": d_letter})
                else:
                    self._send_json({"success": False, "error": msg_open or f"Gagal membuka {d_letter} di Explorer", "drive": d_letter})
            else:
                cfg = config_manager.load_or_create_config()
                srv = config_manager.get_active_server(cfg)
                active_u, _ = get_active_resolved_route(cfg)
                conns = srv.get("connections", []) if srv else []
                host, is_domain, zt_ip = _resolve_smb_route_params(srv, active_u)
                ok_open, msg_open = _unpack_explorer_result(smb_mount_manager.open_unc_root_in_explorer(
                    host,
                    server_connections=conns,
                    is_domain_route=is_domain,
                    zerotier_ip=zt_ip,
                ))
                if ok_open:
                    self._send_json({"success": True, "unc": host})
                else:
                    self._send_json({"success": False, "error": msg_open or f"Host SMB ({host}:445) tidak merespons", "unc": host})



            return







        if path == "/api/open_zima_file_manager":



            cfg = config_manager.load_or_create_config()



            srv = config_manager.get_active_server(cfg)



            active_u, _ = get_active_resolved_route(cfg)



            if active_u:



                srv_name = srv.get("name", "MyServer") if srv else "MyServer"



                fm_url = active_u.rstrip("/") + "/modules/icewhale_files/index.html#/"



                spawn_app_window(fm_url, f"{srv_name} File Manager")



                self._send_json({"success": True, "url": fm_url})



            else:



                self._send_json({"success": False, "error": "No active route"}, status=400)



            return







        if path == "/api/open_file_manager":



            cfg = config_manager.load_or_create_config()



            target = str(cfg.get("file_manager_click_target", "explorer")).lower()



            if target == "zimaos":



                srv = config_manager.get_active_server(cfg)



                active_u, _ = get_active_resolved_route(cfg)



                if active_u:



                    srv_name = srv.get("name", "MyServer") if srv else "MyServer"



                    fm_url = active_u.rstrip("/") + "/modules/icewhale_files/index.html#/"



                    spawn_app_window(fm_url, f"{srv_name} File Manager")



                    self._send_json({"success": True, "target": "zimaos", "url": fm_url})



                else:



                    self._send_json({"success": False, "error": "No active route"}, status=400)



            else:



                sh_name, d_letter = get_primary_mounted_share()



                if not d_letter:



                    mount_active_server_smb()



                    time.sleep(0.5)



                    sh_name, d_letter = get_primary_mounted_share()



                if d_letter:
                    ok_open, msg_open = _unpack_explorer_result(smb_mount_manager.open_drive_in_explorer(d_letter))
                    if ok_open:
                        self._send_json({"success": True, "target": "explorer", "drive": d_letter})
                    else:
                        self._send_json({"success": False, "target": "explorer", "error": msg_open or f"Gagal membuka {d_letter} di Explorer", "drive": d_letter})
                else:
                    srv = config_manager.get_active_server(cfg)
                    active_u, _ = get_active_resolved_route(cfg)
                    conns = srv.get("connections", []) if srv else []
                    host, is_domain, zt_ip = _resolve_smb_route_params(srv, active_u)
                    ok_open, msg_open = _unpack_explorer_result(smb_mount_manager.open_unc_root_in_explorer(
                        host,
                        server_connections=conns,
                        is_domain_route=is_domain,
                        zerotier_ip=zt_ip,
                    ))
                    if ok_open:
                        self._send_json({"success": True, "target": "explorer", "unc": host})
                    else:
                        self._send_json({"success": False, "target": "explorer", "error": msg_open or f"Host SMB ({host}:445) tidak merespons", "unc": host})



            return















        if path == "/api/open_peerdrop":







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg)







            active_u, _ = get_active_resolved_route(cfg)







            peer_url = active_u.rstrip("/") + "/modules/icewhale_peerdrop"







            srv_name = srv.get("name", "MyServer") if srv else "MyServer"







            spawn_app_window(peer_url, f"{srv_name} PeerDrop", width=920, height=660)







            self._send_json({"success": True, "url": peer_url})







            return















        # ----------------------------------------------------------------------







        # SESI 3: Docker Web Apps & Custom Bookmarks







        # ----------------------------------------------------------------------







        if path == "/api/list_web_apps":







            self._send_json(get_web_apps_list())







            return















        if path == "/api/add_web_app":







            args = body.get("args") or []
            if len(args) >= 2:
                name = str(args[0]).strip()
                url = str(args[1]).strip()
            else:
                name = (body.get("name") or (args[0] if len(args) > 0 else "") or body.get("arg") or "").strip()
                url = (body.get("url") or (args[1] if len(args) > 1 else "") or "").strip()







            if name and url:







                url = config_manager.format_server_url(url)







                cfg = config_manager.load_or_create_config()







                web_apps = cfg.setdefault("web_apps", [])







                app_id = f"app_{int(time.time() * 1000)}"







                web_apps.append({"id": app_id, "name": name, "url": url})







                config_manager.save_config(cfg)







                logger_manager.log_info(f"[CoreService] Web App '{name}' ({url}) berhasil ditambahkan.")







            self._send_json(get_web_apps_list())







            return















        if path == "/api/delete_web_app":







            app_id = (body.get("appId") or body.get("id") or body.get("arg") or "").strip()







            if app_id:







                cfg = config_manager.load_or_create_config()







                web_apps = cfg.get("web_apps", [])







                cfg["web_apps"] = [a for a in web_apps if a.get("id") != app_id]







                config_manager.save_config(cfg)







                logger_manager.log_info(f"[CoreService] Web App '{app_id}' berhasil dihapus.")







            self._send_json(get_web_apps_list())







            return















        # ----------------------------------------------------------------------







        # SESI 4: Backup, Sync, Settings & Pemeliharaan







        # ----------------------------------------------------------------------







        # ----------------------------------------------------------------------







        # SESI 4: RESTORASI PENUH SYNCTHING & ATOMIC BACKUP







        # ----------------------------------------------------------------------







        if path == "/api/get_syncthing_api_keys":







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg) or {}







            loc_cfg = cfg.get("local_syncthing", {})







            loc_key = get_local_syncthing_api_key(cfg)







            b_app = srv.get("backup_app", {})







            self._send_json({







                "local": {







                    "port": str(loc_cfg.get("port", "8384")),







                    "api_key": loc_key,







                },







                "server": {







                    "server_name": srv.get("name", "Server"),







                    "port": str(b_app.get("lan_port", "8384")),







                    "api_key": str(b_app.get("api_key", "")),







                    "route_mode": str(b_app.get("route_mode", "auto")),







                    "wan_url": str(b_app.get("wan_url", "")),







                    "lan_ip": str(b_app.get("lan_ip", "")),







                }







            })







            return















        if path == "/api/save_syncthing_api_keys":







            target = (body.get("target") or "both").lower()







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg)







            if target in ("local", "both"):







                loc_cfg = cfg.setdefault("local_syncthing", {})







                if "local_port" in body:







                    loc_cfg["port"] = str(body["local_port"]).strip() or "8384"







                if "local_api_key" in body:







                    loc_cfg["api_key"] = str(body["local_api_key"]).strip()







                



                _active_local_st_client = None







                _active_local_st_key = None







            if target in ("server", "both") and srv:







                b_app = srv.setdefault("backup_app", {})







                if "server_port" in body:







                    b_app["lan_port"] = str(body["server_port"]).strip() or "8384"







                if "server_api_key" in body:







                    b_app["api_key"] = str(body["server_api_key"]).strip()







                



                _active_srv_st_client = None







                _active_srv_st_key = None







            config_manager.save_config(cfg)







            try:







                config_manager.clear_syncthing_route_cache()







            except Exception:







                pass







            logger_manager.log_info("[Syncthing] Konfigurasi REST API Key berhasil diperbarui.")







            self._send_json({"success": True})







            return















        if path == "/api/get_syncthing_config":







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg) or {}







            loc_cfg = cfg.get("local_syncthing", {})







            loc_key = get_local_syncthing_api_key(cfg)







            b_app = srv.get("backup_app", {})







            self._send_json({







                "success": True,







                "server_id": srv.get("id", ""),







                "server_name": srv.get("name", "Server"),







                "local": {







                    "port": str(loc_cfg.get("port", "8384")),







                    "api_key": loc_key,







                    "auto_start": bool(loc_cfg.get("auto_start", True)),







                    "binary_path": str(loc_cfg.get("binary_path", "")),







                },







                "server": {







                    "server_name": srv.get("name", "Server"),







                    "route_mode": str(b_app.get("route_mode", "auto")),







                    "lan_mode": str(b_app.get("lan_mode", "inherit")),







                    "lan_ip": str(b_app.get("lan_ip", "")),







                    "lan_port": str(b_app.get("lan_port", "8384")),







                    "lan_https": bool(b_app.get("lan_https", False)),







                    "wan_url": str(b_app.get("wan_url", "")),







                    "wan_port": str(b_app.get("wan_port", "8384")),







                    "wan_https": bool(b_app.get("wan_https", False)),







                    "api_key": str(b_app.get("api_key", "")),







                    "remote_ip": str(b_app.get("remote_ip") or srv.get("zerotier_virtual_ip") or ""),







                    "remote_port": str(b_app.get("remote_port") or "8384"),







                    "remote_https": bool(b_app.get("remote_https", False)),







                }







            })







            return















        if path == "/api/save_syncthing_server_route":







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg)







            if not srv:







                self._send_json({"success": False, "error": "No active server"})







                return







            b_app = srv.setdefault("backup_app", {})







            if "route_mode" in body:







                b_app["route_mode"] = str(body["route_mode"]).strip().lower() or "auto"







            if "lan_mode" in body:







                b_app["lan_mode"] = str(body["lan_mode"]).strip().lower() or "inherit"







            if "lan_ip" in body:







                b_app["lan_ip"] = str(body["lan_ip"]).strip()







            if "lan_port" in body:







                b_app["lan_port"] = str(body["lan_port"]).strip() or "8384"







            if "lan_https" in body:







                b_app["lan_https"] = bool(body["lan_https"])







            if "wan_url" in body:







                b_app["wan_url"] = str(body["wan_url"]).strip()







            if "wan_port" in body:







                b_app["wan_port"] = str(body["wan_port"]).strip() or "8384"







            if "wan_https" in body:







                b_app["wan_https"] = bool(body["wan_https"])







            if "remote_ip" in body:







                b_app["remote_ip"] = str(body["remote_ip"]).strip()







            if "remote_port" in body:







                b_app["remote_port"] = str(body["remote_port"]).strip() or "8384"







            if "remote_https" in body:







                b_app["remote_https"] = bool(body["remote_https"])







            if "api_key" in body:







                b_app["api_key"] = str(body["api_key"]).strip()







            







            



            _active_srv_st_client = None







            _active_srv_st_key = None







            config_manager.save_config(cfg)







            try:







                config_manager.clear_syncthing_route_cache()







            except Exception:







                pass







            logger_manager.log_info(f"[Syncthing] Konfigurasi rute server '{srv.get('name')}' berhasil disimpan.")







            self._send_json({"success": True})







            return















        if path == "/api/save_syncthing_local_config":







            cfg = config_manager.load_or_create_config()







            loc_cfg = cfg.setdefault("local_syncthing", {})







            if "port" in body:







                loc_cfg["port"] = str(body["port"]).strip() or "8384"







            if "api_key" in body:







                loc_cfg["api_key"] = str(body["api_key"]).strip()







            if "auto_start" in body:







                loc_cfg["auto_start"] = bool(body["auto_start"])







            if "binary_path" in body:







                loc_cfg["binary_path"] = str(body["binary_path"]).strip()







            







            



            _active_local_st_client = None







            _active_local_st_key = None







            config_manager.save_config(cfg)







            logger_manager.log_info(f"[Syncthing] Konfigurasi local Syncthing berhasil disimpan (Port: {loc_cfg.get('port')}).")







            self._send_json({"success": True})







            return















        if path == "/api/test_syncthing_target":







            target_url = str(body.get("url", "")).strip()







            if not target_url:







                self._send_json({"success": False, "online": False, "message": "Target URL is empty"})







                return







            if "://" not in target_url:







                target_url = ("https://" if body.get("use_https") else "http://") + target_url







            







            ok, lat = config_manager.check_syncthing_ping(target_url, timeout=2.5)







            self._send_json({







                "success": True,







                "online": ok,







                "latency_ms": lat if ok else 0,







                "url": target_url,







                "message": f"Online ({lat}ms)" if ok else "Host unreachable or Syncthing not responding"







            })







            return















        if path == "/api/dialog_configure_local_syncthing":







            threading.Thread(target=prompt_local_syncthing_setup, daemon=True).start()







            self._send_json({"success": True})







            return















        if path == "/api/dialog_configure_server_syncthing":







            threading.Thread(target=prompt_backup_app_setup, daemon=True).start()







            self._send_json({"success": True})







            return















        if path == "/api/get_syncthing_full_status":







            with _syncthing_lock:







                status_copy = json.loads(json.dumps(_syncthing_cache))







            self._send_json(status_copy)







            return















        if path == "/api/pair_laptop_and_server":







            def _pair_worker():







                cfg = config_manager.load_or_create_config()







                srv = config_manager.get_active_server(cfg)







                loc_key = get_local_syncthing_api_key(cfg)







                loc_cfg = cfg.get("local_syncthing", {})







                loc_port = loc_cfg.get("port", "8384")







                if not srv:







                    return {"success": False, "error": "Tidak ada server aktif."}







                srv_host, srv_port, srv_key, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg)







                loc_client = syncthing_manager.SyncthingClient("127.0.0.1", loc_port, loc_key)







                srv_client = syncthing_manager.SyncthingClient(srv_host, srv_port, srv_key, use_https=srv_https)







                loc_id = loc_client.get_my_id()







                srv_id = srv_client.get_my_id()







                if not loc_id or not srv_id:







                    return {"success": False, "error": "Syncthing belum aktif pada kedua sisi."}







                loc_client.add_device(srv_id, srv.get("name", "Server"))







                srv_client.add_device(loc_id, "Laptop")







                loc_client.accept_pending_device(srv_id, name=srv.get("name", "Server"))







                srv_client.accept_pending_device(loc_id, name="Laptop")







                logger_manager.log_info(f"[Syncthing] Pairing 1-Click berhasil antara Laptop ({loc_id[:7]}) dan Server ({srv_id[:7]}).")







                return {"success": True, "local_id": loc_id, "server_id": srv_id}







            self._send_json(_pair_worker())







            return















        if path == "/api/get_syncthing_tasks":







            self._send_json(get_syncthing_tasks_list())







            return















        if path == "/api/create_sync_task":







            l_path = (body.get("folder_path") or body.get("local_path") or "").strip()







            l_label = (body.get("task_label") or body.get("label") or "").strip()







            s_path = (body.get("server_path") or "").strip()







            s_mode = (body.get("sync_mode") or "sendonly").strip()







            t_server_id = (body.get("target_server_id") or "").strip() or None







            res = create_sync_task_route(local_path=l_path, task_label=l_label, server_path=s_path, sync_mode=s_mode, target_server_id=t_server_id)







            self._send_json(res)







            return















        if path == "/api/choose_folder":







            title = (body.get("title") or "Pilih Folder di Laptop").strip()







            sel = dialog_helper.prompt_choose_folder(title)







            self._send_json({"success": bool(sel), "path": sel or ""})







            return















        if path == "/api/delete_sync_task":







            folder_id = (body.get("folder_id") or body.get("id") or body.get("arg") or "").strip()







            if not folder_id:







                self._send_json({"success": False, "error": "Folder ID wajib diberikan."})







                return







            cfg = config_manager.load_or_create_config()







            loc_key = get_local_syncthing_api_key(cfg)







            loc_port = cfg.get("local_syncthing", {}).get("port", "8384")







            loc_client = syncthing_manager.SyncthingClient("127.0.0.1", loc_port, loc_key)







            loc_client.delete_folder(folder_id)















            srv = get_target_server_for_task(cfg, folder_id, fallback_to_active=True)



            if srv:



                srv_host, srv_port, srv_key, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg)



                if srv_host and srv_key:



                    srv_client = syncthing_manager.SyncthingClient(srv_host, srv_port, srv_key, use_https=srv_https)



                    srv_client.delete_folder(folder_id)



                if "sync_task_owners" in srv:



                    srv["sync_task_owners"].pop(folder_id, None)



            if "sync_task_servers" in cfg:



                cfg["sync_task_servers"].pop(folder_id, None)



            if "sync_task_server_paths" in cfg:

                cfg["sync_task_server_paths"].pop(folder_id, None)

            config_manager.save_config(cfg)



            logger_manager.log_info(f"[Syncthing] Jalur task '{folder_id}' telah dihapus.")







            self._send_json({"success": True})







            return















        if path == "/api/set_task_paused":







            folder_id = (body.get("folder_id") or body.get("id") or "").strip()







            paused = bool(body.get("paused", True))







            cfg = config_manager.load_or_create_config()







            loc_key = get_local_syncthing_api_key(cfg)







            loc_port = cfg.get("local_syncthing", {}).get("port", "8384")







            loc_client = syncthing_manager.SyncthingClient("127.0.0.1", loc_port, loc_key)







            loc_client.set_folder_paused(folder_id, paused=paused)



            srv = get_target_server_for_task(cfg, folder_id, fallback_to_active=True)







            if srv:







                srv_host, srv_port, srv_key, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg)







                if srv_host and srv_key:







                    srv_client = syncthing_manager.SyncthingClient(srv_host, srv_port, srv_key, use_https=srv_https)







                    srv_client.set_folder_paused(folder_id, paused=paused)







            self._send_json({"success": True, "paused": paused})







            return















        if path == "/api/rescan_task":







            folder_id = (body.get("folder_id") or body.get("id") or "").strip()







            cfg = config_manager.load_or_create_config()







            loc_key = get_local_syncthing_api_key(cfg)







            loc_port = cfg.get("local_syncthing", {}).get("port", "8384")







            loc_client = syncthing_manager.SyncthingClient("127.0.0.1", loc_port, loc_key)







            if folder_id:







                loc_client.rescan_folder(folder_id)







            else:







                loc_client.force_rescan()



            srv = get_target_server_for_task(cfg, folder_id, fallback_to_active=True) if folder_id else config_manager.get_active_server(cfg)







            if srv:







                srv_host, srv_port, srv_key, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg)







                if srv_host and srv_key:







                    srv_client = syncthing_manager.SyncthingClient(srv_host, srv_port, srv_key, use_https=srv_https)







                    if folder_id:







                        srv_client.rescan_folder(folder_id)







                    else:







                        srv_client.force_rescan()







            self._send_json({"success": True})







            return















        if path == "/api/open_task_folder":







            f_path = (body.get("path") or body.get("folder_path") or body.get("arg") or "").strip()







            if not f_path:







                fid = (body.get("folder_id") or body.get("id") or "").strip()







                if fid:







                    with _syncthing_lock:







                        for item in _syncthing_cache["local"]["folders"]:







                            if item.get("id") == fid:







                                f_path = item.get("path", "")







                                break







            if f_path and os.path.exists(f_path):







                subprocess.Popen(["explorer.exe", os.path.normpath(f_path)])







                self._send_json({"success": True, "path": f_path})







            else:







                self._send_json({"success": False, "error": "Folder tidak ditemukan di disk lokal."})







            return















        if path == "/api/get_my_device_ids":







            with _syncthing_lock:







                loc_id = _syncthing_cache["local"]["device_id"]







                srv_id = _syncthing_cache["server"]["device_id"]







            self._send_json({"local_id": loc_id, "server_id": srv_id})







            return















        if path == "/api/add_syncthing_device":







            target = (body.get("target") or "local").lower()







            dev_id = syncthing_manager.normalize_device_id(body.get("device_id") or body.get("id") or "")







            dev_name = (body.get("name") or "").strip()







            if not syncthing_manager.validate_device_id(dev_id):







                self._send_json({"success": False, "error": "Format Device ID tidak valid."})







                return







            cfg = config_manager.load_or_create_config()







            if target in ("local", "both"):







                loc_key = get_local_syncthing_api_key(cfg)







                loc_port = cfg.get("local_syncthing", {}).get("port", "8384")







                loc_client = syncthing_manager.SyncthingClient("127.0.0.1", loc_port, loc_key)







                loc_client.add_device(dev_id, dev_name)







            if target in ("server", "both"):







                srv = config_manager.get_active_server(cfg)







                if srv:







                    srv_host, srv_port, srv_key, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg)







                    if srv_host and srv_key:







                        srv_client = syncthing_manager.SyncthingClient(srv_host, srv_port, srv_key, use_https=srv_https)







                        srv_client.add_device(dev_id, dev_name)







            self._send_json({"success": True, "device_id": dev_id})







            return















        if path == "/api/remove_syncthing_device":







            target = (body.get("target") or "local").lower()







            dev_id = syncthing_manager.normalize_device_id(body.get("device_id") or body.get("id") or "")







            cfg = config_manager.load_or_create_config()







            if target in ("local", "both"):







                loc_key = get_local_syncthing_api_key(cfg)







                loc_port = cfg.get("local_syncthing", {}).get("port", "8384")







                loc_client = syncthing_manager.SyncthingClient("127.0.0.1", loc_port, loc_key)







                loc_client.remove_device(dev_id)







            if target in ("server", "both"):







                srv = config_manager.get_active_server(cfg)







                if srv:







                    srv_host, srv_port, srv_key, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg)







                    if srv_host and srv_key:







                        srv_client = syncthing_manager.SyncthingClient(srv_host, srv_port, srv_key, use_https=srv_https)







                        srv_client.remove_device(dev_id)







            self._send_json({"success": True})







            return















        if path == "/api/set_device_paused":







            target = (body.get("target") or "local").lower()







            dev_id = syncthing_manager.normalize_device_id(body.get("device_id") or body.get("id") or "")







            paused = bool(body.get("paused", True))







            cfg = config_manager.load_or_create_config()







            if target in ("local", "both"):







                loc_key = get_local_syncthing_api_key(cfg)







                loc_port = cfg.get("local_syncthing", {}).get("port", "8384")







                loc_client = syncthing_manager.SyncthingClient("127.0.0.1", loc_port, loc_key)







                if paused:







                    loc_client.pause(dev_id)







                else:







                    loc_client.resume(dev_id)







            if target in ("server", "both"):







                srv = config_manager.get_active_server(cfg)







                if srv:







                    srv_host, srv_port, srv_key, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg)







                    if srv_host and srv_key:







                        srv_client = syncthing_manager.SyncthingClient(srv_host, srv_port, srv_key, use_https=srv_https)







                        if paused:







                            srv_client.pause(dev_id)







                        else:







                            srv_client.resume(dev_id)







            self._send_json({"success": True, "paused": paused})







            return















        if path == "/api/resolve_pending_device":







            target = (body.get("target") or "local").lower()







            dev_id = (body.get("device_id") or body.get("id") or "").strip()







            action = (body.get("action") or "accept").lower()







            dev_name = (body.get("name") or "").strip()







            cfg = config_manager.load_or_create_config()







            client = None







            if target == "local":







                loc_key = get_local_syncthing_api_key(cfg)







                loc_port = cfg.get("local_syncthing", {}).get("port", "8384")







                client = syncthing_manager.SyncthingClient("127.0.0.1", loc_port, loc_key)







            else:







                srv = config_manager.get_active_server(cfg)







                if srv:







                    srv_host, srv_port, srv_key, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg)







                    if srv_host and srv_key:







                        client = syncthing_manager.SyncthingClient(srv_host, srv_port, srv_key, use_https=srv_https)







            if client:







                if action == "accept":







                    client.accept_pending_device(dev_id, name=dev_name)







                else:







                    client.dismiss_pending_device(dev_id)







            self._send_json({"success": True, "action": action})







            return















        if path == "/api/toggle_local_syncthing_daemon":







            action = (body.get("action") or "toggle").lower()







            cfg = config_manager.load_or_create_config()







            loc_port = cfg.get("local_syncthing", {}).get("port", "8384")







            loc_key = get_local_syncthing_api_key(cfg)







            if action == "start":







                _local_st_daemon.start(custom_port=loc_port)







            elif action == "stop":







                _local_st_daemon.stop(custom_port=loc_port, api_key=loc_key)







            else:







                if _local_st_daemon.is_running(port=loc_port):







                    _local_st_daemon.stop(custom_port=loc_port, api_key=loc_key)







                else:







                    _local_st_daemon.start(custom_port=loc_port)







            is_run = _local_st_daemon.is_running(port=loc_port)







            self._send_json({"success": True, "running": is_run})







            return















        if path in ("/api/open_backup", "/api/open_syncthing_web_gui"):







            target = (body.get("target") or "server").lower()







            cfg = config_manager.load_or_create_config()







            if target == "local":







                loc_port = cfg.get("local_syncthing", {}).get("port", "8384")







                syncthing_url = f"http://127.0.0.1:{loc_port}"







            else:







                srv = config_manager.get_active_server(cfg)







                srv_host, srv_port, _, _, _, srv_https = config_manager.get_effective_backup_app_target(srv, cfg) if srv else ("127.0.0.1", "8384", "", "", "", False)







                proto = "https" if srv_https else "http"







                syncthing_url = f"{proto}://{srv_host}:{srv_port}"







            webbrowser.open(syncthing_url)







            self._send_json({"success": True, "url": syncthing_url})







            return















        if path in ("/api/create_backup", "/api/execute_backup_dialog"):







            t_file = (body.get("target_file") or body.get("file") or "").strip()







            self._send_json(execute_backup_dialog(t_file))







            return















        if path in ("/api/restore_backup", "/api/execute_restore_dialog"):







            t_file = (body.get("target_file") or body.get("file") or "").strip()







            self._send_json(execute_restore_dialog(t_file))







            return















        if path == "/api/get_pending_sync_requests":







            with _syncthing_lock:







                cnt = len(_syncthing_cache["local"]["pending_devices"]) + len(_syncthing_cache["server"]["pending_devices"])







            self._send_json(cnt)







            return















        if path == "/api/accept_sync_request":







            cfg = config_manager.load_or_create_config()







            loc_key = get_local_syncthing_api_key(cfg)







            loc_port = cfg.get("local_syncthing", {}).get("port", "8384")







            loc_client = syncthing_manager.SyncthingClient("127.0.0.1", loc_port, loc_key)







            with _syncthing_lock:







                for p_id in list(_syncthing_cache["local"]["pending_devices"].keys()):







                    loc_client.accept_pending_device(p_id)







            self._send_json({"success": True})







            return















        if path == "/api/load_settings":







            cfg = config_manager.load_or_create_config()







            self._send_json({







                "autostart": is_autorun_enabled(),







                "openDashboard": bool(cfg.get("open_dashboard_on_launch", False)),







                "autoMountSmb": bool(cfg.get("auto_mount_smb", True)),







                "autoZeroTier": bool(cfg.get("auto_zerotier", True)),







                "autoCleanOnExit": bool(cfg.get("auto_clean_cache", True)),







                "appEntryOpen": str(cfg.get("app_entry_open", "window")),







                "showTraffic": bool(cfg.get("show_traffic", True)),



                "autoOpenMiniTray": bool(cfg.get("auto_open_mini_tray", True)),



                "fileManagerClickTarget": str(cfg.get("file_manager_click_target", "explorer")),



                "language": str(cfg.get("language", "en")),
                "theme": str(cfg.get("theme", "dark")) if str(cfg.get("theme", "")).lower() in ("dark", "light") else "dark",
                "dpapiActive": bool(config_manager.is_dpapi_supported()),
                "firstRunSetup": bool(config_manager.evaluate_first_run_setup(cfg)),
        "backend": _get_backend_health_info(cfg),







            })







            return















        if path == "/api/save_settings":







            settings = body.get("settings") if "settings" in body else body







            if isinstance(settings, dict):







                cfg = config_manager.load_or_create_config()







                if "autostart" in settings:







                    want_autostart = bool(settings["autostart"])







                    if set_autorun(want_autostart):







                        cfg["autostart"] = want_autostart







                if "openDashboard" in settings:







                    cfg["open_dashboard_on_launch"] = bool(settings["openDashboard"])







                if "autoMountSmb" in settings:







                    cfg["auto_mount_smb"] = bool(settings["autoMountSmb"])







                if "autoZeroTier" in settings:







                    cfg["auto_zerotier"] = bool(settings["autoZeroTier"])







                if "autoCleanOnExit" in settings:







                    cfg["auto_clean_cache"] = bool(settings["autoCleanOnExit"])







                if "appEntryOpen" in settings:







                    cfg["app_entry_open"] = str(settings["appEntryOpen"]).lower()



                if "showTraffic" in settings:



                    cfg["show_traffic"] = bool(settings["showTraffic"])







                if "autoOpenMiniTray" in settings:



                    cfg["auto_open_mini_tray"] = bool(settings["autoOpenMiniTray"])







                if "fileManagerClickTarget" in settings:



                    val = str(settings["fileManagerClickTarget"]).lower().strip()



                    if val in ("explorer", "zimaos"):



                        cfg["file_manager_click_target"] = val



                if "language" in settings:



                    lang_val = str(settings["language"]).lower().strip()



                    if lang_val in ("en", "id"):



                        cfg["language"] = lang_val
                if "theme" in settings:
                    theme_val = str(settings["theme"]).lower().strip()
                    if theme_val in ("dark", "light"):
                        cfg["theme"] = theme_val
                if "firstRunSetup" in settings:
                    want_frs = bool(settings["firstRunSetup"])
                    if not want_frs:
                        if config_manager.has_valid_configured_server(cfg):
                            cfg["first_run_setup"] = False
                    else:
                        cfg["first_run_setup"] = True











                config_manager.save_config(cfg)







                logger_manager.log_info("[CoreService] Pengaturan berhasil disimpan.")







            self._send_json({"success": True})







            return















        if path == "/api/clear_cache":







            freed = clean_webview_cache()







            self._send_json({"freedMb": round(freed / (1024 * 1024), 1)})







            return



















        if path == "/api/install_update_from_zip":
            fpath = (body.get("filePath") or "").strip()
            res = apply_zip_update(fpath if fpath else None)
            self._send_json(res)
            return

        if path == "/api/download_and_install_update":
            download_url = (body.get("downloadUrl") or "").strip()
            if not download_url:
                cfg = config_manager.load_or_create_config()
                repo_slug = cfg.get("github_repo", "Gibranibang/My-Server-beta")
                rel_url = f"https://api.github.com/repos/{repo_slug}/releases/latest"
                try:
                    req = urllib.request.Request(rel_url, headers={"User-Agent": f"MyServer-Companion/{APP_VERSION_NUMBER}", "Accept": "application/vnd.github.v3+json"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        r_data = json.loads(resp.read().decode())
                        for asset in r_data.get("assets", []):
                            aname = asset.get("name", "").lower()
                            if aname.endswith("-setup.exe") or aname.endswith(".exe"):
                                download_url = asset.get("browser_download_url", "")
                                break
                            if not download_url and aname.endswith(".zip"):
                                download_url = asset.get("browser_download_url", "")
                except Exception as ex:
                    logger_manager.log_error(f"[Updater] Gagal memperoleh URL rilis: {ex}")

            if not download_url:
                self._send_json({"success": False, "error": "URL berkas rilis pembaruan tidak ditemukan."})
                return

            is_zip = download_url.lower().endswith(".zip")
            suffix = ".zip" if is_zip else ".exe"
            temp_file = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), f"MyServer_Update_{int(time.time())}{suffix}")

            try:
                logger_manager.log_info(f"[Updater] Mengunduh pembaruan dari: {download_url} -> {temp_file}")
                downloaded_bytes = _download_stream_bounded(
                    download_url,
                    temp_file,
                    headers={"User-Agent": "MyServer-Updater/1.0", "Connection": "close"},
                    socket_timeout=30.0,
                    total_timeout=180.0,
                    max_bytes=512 * 1024 * 1024,
                )
                if downloaded_bytes < 1024:
                    raise ValueError(f"Berkas unduhan pembaruan tidak lengkap ({downloaded_bytes} bytes)")

                logger_manager.log_info(f"[Updater] Unduhan selesai ({os.path.getsize(temp_file):,} bytes)")

                if is_zip:
                    res = apply_zip_update(temp_file)
                    self._send_json(res)
                    return
                else:
                    # Hentikan daemon EasyTier terlebih dahulu agar Packet.dll & wintun.dll tidak terkunci saat installer menimpa berkas
                    try:
                        easytier_manager.get_easytier_manager().stop()
                    except Exception as _et_err:
                        logger_manager.log_error(f"[Updater] Gagal menghentikan EasyTier sebelum installer: {_et_err}")
                    try:
                        # Paksa taskkill proses easytier-core dan easytier-cli jika masih memegang file handle
                        subprocess.run(["taskkill.exe", "/F", "/IM", "easytier-core.exe", "/IM", "easytier-cli.exe"], capture_output=True, timeout=5)
                    except Exception:
                        pass
                    time.sleep(1.5)

                    # Gunakan os.startfile agar installer berjalan mandiri di bawah Windows Shell (Explorer),
                    # sehingga bebas dari pohon proses myserver-core dan tidak terimbas pematian proses.
                    try:
                        os.startfile(temp_file)
                    except Exception:
                        DETACHED_PROCESS = 0x00000008
                        CREATE_NEW_PROCESS_GROUP = 0x00000200
                        subprocess.Popen([temp_file], cwd=os.path.dirname(temp_file), creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
                    self._send_json({"success": True, "installerLaunched": True, "message": "Installer pembaruan berhasil diluncurkan. Ikuti petunjuk instalasi untuk menyelesaikan pembaruan."})
                    return
            except Exception as e:
                logger_manager.log_error(f"[Updater] Gagal mengunduh atau menjalankan pembaruan: {e}")
                self._send_json({"success": False, "error": f"Gagal mengunduh atau mengeksekusi installer: {str(e)}"})
                return







        # --- Dispatcher Fallback untuk call_core_api ---
        if path == "/api/call_core_api":
            ep = (body.get("endpoint") or body.get("arg") or "").strip().lower()
            if ep in ("easytier/status", "easytier_status"):
                path = "/api/easytier/status"
            elif ep in ("easytier/peers", "easytier_peers"):
                path = "/api/easytier/peers"
            elif ep in ("easytier/start", "easytier_start"):
                path = "/api/easytier/start"
            elif ep in ("easytier/stop", "easytier_stop"):
                path = "/api/easytier/stop"
            elif ep in ("remote/status", "remote_status"):
                path = "/api/remote/status"
            elif ep in ("server/backend_action", "server_backend_action"):
                path = "/api/server/backend_action"
            elif ep in ("server/backend_status", "server_backend_status"):
                path = "/api/server/backend_status"
            elif ep in ("vms/load", "vms_load"):
                path = "/api/vms/load"
            elif ep in ("vms/save", "vms_save"):
                path = "/api/vms/save"
            elif ep in ("vms/update", "vms_update"):
                path = "/api/vms/update"
            elif ep in ("vms/delete", "vms_delete"):
                path = "/api/vms/delete"
            elif ep in ("vms/migrate", "vms_migrate"):
                path = "/api/vms/migrate"
            elif ep in ("probe_url", "probe-url"):
                target_url = str(body.get("url") or body.get("arg") or "").strip()
                self._send_json(probe_url_endpoint(target_url))
                return
            elif ep in ("wizard/verify_zimaos", "wizard_verify_zimaos"):
                path = "/api/wizard/verify_zimaos"
            elif ep in ("wizard/commit_server", "wizard_commit_server"):
                path = "/api/wizard/commit_server"
            elif ep in ("wizard/complete", "wizard_complete"):
                path = "/api/wizard/complete"
            elif ep in ("smb/source", "smb_source"):
                if isinstance(body.get("payload"), dict):
                    body = {**body, **body["payload"]}
                path = "/api/smb/source"
            elif ep in ("open_backend_file_manager", "open/backend_file_manager"):
                if isinstance(body.get("payload"), dict):
                    body = {**body, **body["payload"]}
                path = "/api/open_backend_file_manager"

        # --- Endpoints Persisten VM, Migrasi Server & Terminal SSH (v4.5.5 Beta) ---
        if path in ("/api/vms/delete", "/api/vms_delete"):
            vm_id = (body.get("vmId") or body.get("vm_id") or body.get("id") or "").strip()
            if not vm_id:
                self._send_json({"status": "error", "message": "vmId is required"}, status=400)
                return

            server_id = (body.get("serverId") or body.get("server_id") or "").strip()
            cfg = config_manager.load_or_create_config()
            local_vms = cfg.get("vms", []) or []

            # Ambil serverId dari data VM jika belum diberikan
            if not server_id:
                found_v = next((v for v in local_vms if isinstance(v, dict) and v.get("id") == vm_id), None)
                if found_v:
                    server_id = found_v.get("serverId", "")

            # Daftarkan ke tombstone Core Service (TTL 60 detik) & bersihkan cache mutasi
            _deleted_vms_tombstone[vm_id] = time.time() + 60.0
            _recent_vm_mutations.pop(vm_id, None)

            cfg["vms"] = [v for v in local_vms if isinstance(v, dict) and v.get("id") != vm_id]
            if isinstance(cfg.get("instabox_vms"), list):
                cfg["instabox_vms"] = [v for v in cfg["instabox_vms"] if isinstance(v, dict) and v.get("id") != vm_id]
            config_manager.save_config(cfg)

            backend_url = _get_active_server_backend_url(cfg, target_server_id=server_id)
            server_deleted = False
            if backend_url:
                try:
                    ok, data, code = _backend_http_request(f"{backend_url}/api/v1/vms/{vm_id}", method="DELETE", timeout=5.0, retries=1)
                    server_deleted = ok
                    logger_manager.log_info(f"[/api/vms/delete] VM {vm_id} berhasil dihapus dari ZimaOS: {ok} (code {code})")
                except Exception as de:
                    logger_manager.log_error(f"[/api/vms/delete] Gagal hapus VM {vm_id} dari server ZimaOS: {de}")

            self._send_json({"status": "ok", "success": True, "server_deleted": server_deleted, "vmId": vm_id})
            return

        if path in ("/api/vms/update", "/api/vms_update"):
            http_status, resp_body = _execute_vm_update_operation(body)
            self._send_json(resp_body, status=http_status)
            return

        if path in ("/api/vms", "/api/vms/load"):
            cfg = config_manager.load_or_create_config()
            now_ts = time.time()
            if "vms" in body and isinstance(body.get("vms"), list):
                raw_list = body["vms"]
                # Saring VM yang berada dalam tombstone penghapusan
                vms_list = [v for v in raw_list if isinstance(v, dict) and _deleted_vms_tombstone.get(v.get("id"), 0) <= now_ts]
                cfg["vms"] = vms_list
                config_manager.save_config(cfg)

                for vm in vms_list:
                    if vm.get("scope") == "server" and _deleted_vms_tombstone.get(vm.get("id"), 0) <= time.time():
                        backend_url = _get_active_server_backend_url(cfg, target_server_id=vm.get("serverId"))
                        if backend_url:
                            try:
                                b_payload = _prepare_vm_payload_for_backend(vm)
                                _backend_http_request(f"{backend_url}/api/v1/vms", method="POST", json_body=b_payload, timeout=2.5)
                            except Exception as be:
                                logger_manager.log_debug(f"[api/vms] Gagal sync server VM {vm.get('id')}: {be}")

                self._send_json({"status": "ok", "success": True, "vms": vms_list})
            else:
                cached_vms = cfg.get("vms", []) or []
                # Bersihkan VM lokal dari tombstone
                cached_vms = [v for v in cached_vms if isinstance(v, dict) and _deleted_vms_tombstone.get(v.get("id"), 0) <= now_ts]
                for vm in cached_vms:
                    if not vm.get("scope"):
                        vm["scope"] = "local"
                    _apply_recent_vm_mutation(vm)

                server_vms, server_online = _fetch_server_vms_from_backend(cfg, now_ts)

                seen_ids = set()
                combined = []
                for vm in server_vms:
                    seen_ids.add(vm.get("id"))
                    combined.append(vm)
                # Pertahankan seluruh VM lokal murni; jangan hidupkan kembali server VM yang sudah dihapus jika server online
                for vm in cached_vms:
                    if not isinstance(vm, dict):
                        continue
                    vid = vm.get("id")
                    if _deleted_vms_tombstone.get(vid, 0) > time.time():
                        continue
                    vscope = vm.get("scope") or ("server" if vm.get("serverId") or vm.get("serverName") else "local")
                    if vid not in seen_ids:
                        if vscope != "server" or not server_online:
                            seen_ids.add(vid)
                            combined.append(vm)

                cfg["vms"] = combined
                config_manager.save_config(cfg)
                self._send_json({"status": "ok", "vms": combined})
            return

        if path == "/api/vms/save":
            cfg = config_manager.load_or_create_config()
            now_ts = time.time()
            vms_list = body.get("vms")
            if isinstance(vms_list, list):
                # Saring VM yang dalam tombstone
                vms_list = [v for v in vms_list if isinstance(v, dict) and _deleted_vms_tombstone.get(v.get("id"), 0) <= now_ts]
                # Pertahankan runtimeMinutes yang lebih baru dari cfg["vms"] jika payload mengirim 0 pada VM running
                existing_by_id = {
                    v.get("id"): v for v in (cfg.get("vms", []) or [])
                    if isinstance(v, dict) and v.get("id")
                }
                for v in vms_list:
                    vid = v.get("id")
                    old_v = existing_by_id.get(vid)
                    if old_v and v.get("status") == "running" and not v.get("runtimeMinutes") and old_v.get("runtimeMinutes"):
                        v["runtimeMinutes"] = old_v.get("runtimeMinutes")
                    if old_v and not v.get("telemetry") and old_v.get("telemetry"):
                        v["telemetry"] = old_v.get("telemetry")
                    _apply_recent_vm_mutation(v)

                prev_server_ids = {
                    v.get("id") for v in (cfg.get("vms", []) or [])
                    if isinstance(v, dict) and v.get("scope") == "server" and v.get("id")
                }
                new_server_ids = {
                    v.get("id") for v in vms_list
                    if isinstance(v, dict) and v.get("scope") == "server" and v.get("id")
                }
                cfg["vms"] = vms_list
                config_manager.save_config(cfg)

                backend_url = _get_active_server_backend_url(cfg)
                if backend_url:
                    try:
                        live_ok, live_data, _ = _backend_http_request(f"{backend_url}/api/v1/vms", method="GET", timeout=2.0)
                        if live_ok and isinstance(live_data, dict):
                            live_vms = live_data.get("vms", [])
                            for lv in live_vms:
                                if isinstance(lv, dict) and lv.get("id"):
                                    prev_server_ids.add(lv.get("id"))
                    except Exception:
                        pass

                    # Isolasi: VM yang dulu scope server tapi kini lokal / dihapus harus hilang dari ZimaOS
                    for gone_id in (prev_server_ids - new_server_ids):
                        try:
                            _backend_http_request(f"{backend_url}/api/v1/vms/{gone_id}", method="DELETE", timeout=5.0, retries=1)
                            logger_manager.log_info(f"[api/vms/save] VM {gone_id} dihapus dari server ZimaOS")
                        except Exception as de:
                            logger_manager.log_debug(f"[api/vms/save] Gagal hapus VM {gone_id} di server: {de}")
                    for vm in vms_list:
                        vid = vm.get("id")
                        # Cek ulang tombstone tepat sebelum POST agar delete paralel tidak ter-resurrect!
                        if isinstance(vm, dict) and vm.get("scope") == "server" and _deleted_vms_tombstone.get(vid, 0) <= time.time():
                            try:
                                b_payload = _prepare_vm_payload_for_backend(vm)
                                target_srv_url = _get_active_server_backend_url(cfg, target_server_id=vm.get("serverId")) or backend_url
                                _backend_http_request(f"{target_srv_url}/api/v1/vms", method="POST", json_body=b_payload, timeout=5.0, retries=1)
                            except Exception as be:
                                logger_manager.log_debug(f"[api/vms/save] Gagal sync server VM {vid}: {be}")

                self._send_json({"status": "ok", "success": True})
            else:
                self._send_json({"status": "error", "message": "Invalid vms list"}, status=400)
            return

        if path in ("/api/vms/migrate", "/api/vms_migrate"):
            http_status, resp_body = _execute_vm_migrate_operation(body)
            self._send_json(resp_body, status=http_status)
            return

        if path in ("/api/wizard/verify_zimaos", "/api/wizard_verify_zimaos"):
            status_code, res = _handle_wizard_verify_zimaos(body)
            self._send_json(res, status=status_code)
            return

        if path in ("/api/wizard/commit_server", "/api/wizard_commit_server"):
            status_code, res = _handle_wizard_commit_server(body)
            self._send_json(res, status=status_code)
            return

        if path in ("/api/wizard/complete", "/api/wizard_complete"):
            status_code, res = _handle_wizard_complete(body)
            self._send_json(res, status=status_code)
            return

        if path in ("/api/server/backend_status", "/api/server_backend_status"):
            req_srv_id = (body.get("serverId") or body.get("server_id") or "").strip() or None if isinstance(body, dict) else None
            self._send_json(_get_backend_health_info(force=True, target_server_id=req_srv_id))
            return

        if path in ("/api/server/backend_action", "/api/server_backend_action"):
            res = handle_remote_backend_action(body)
            if res.get("success"):
                status_code = 200
            elif res.get("busy"):
                status_code = 409
            elif res.get("authFailed"):
                status_code = 401
            elif res.get("validationError"):
                status_code = 400
            else:
                status_code = 500
            self._send_json(res, status=status_code)
            return

        if path in ("/api/smb/source", "/api/smb_source"):
            status_code, res = _handle_smb_source_request(body)
            self._send_json(res, status=status_code)
            return

        if path == "/api/open_backend_file_manager":
            cfg = config_manager.load_or_create_config()
            req_srv_id = (
                (body.get("serverId") or body.get("server_id") or "").strip() or None
                if isinstance(body, dict)
                else None
            )
            srv = _select_target_server(cfg, target_server_id=req_srv_id)
            backend_url = _get_active_server_backend_url(
                cfg, target_server_id=(srv.get("id") if srv else None)
            )
            if backend_url:
                clean_burl = backend_url.rstrip("/")
                h_ok, h_data, _ = _backend_http_request(
                    f"{clean_burl}/health", method="GET", timeout=2.0, retries=0
                )
                if not (h_ok and isinstance(h_data, dict) and h_data.get("status") == "ok"):
                    self._send_json(
                        {"success": False, "error": "Backend tidak dapat dijangkau atau belum aktif."},
                        status=503,
                    )
                    return
                srv_name = srv.get("name", "MyServer") if srv else "MyServer"
                fm_url = clean_burl + "/"
                spawn_app_window(fm_url, f"{srv_name} Backend Files")
                self._send_json({"success": True, "url": fm_url})
            else:
                self._send_json(
                    {"success": False, "error": "Backend MyServer tidak ditemukan atau offline."},
                    status=400,
                )
            return

        if path == "/api/server/ssh_terminal":
            cfg = config_manager.load_or_create_config()
            servers = cfg.get("servers", [])
            req_server_id = (body.get("serverId") or body.get("server_id") or "").strip()
            req_host = (body.get("host") or "").strip()

            srv = None
            if req_server_id:
                for s in servers:
                    if s.get("id") == req_server_id or s.get("name") == req_server_id:
                        srv = s
                        break
            if not srv and req_host:
                clean_h = req_host.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()
                for s in servers:
                    for c in s.get("connections", []):
                        curl = c.get("url", "")
                        chost = urllib.parse.urlparse(curl if "://" in curl else f"http://{curl}").hostname or ""
                        if chost.lower() == clean_h:
                            srv = s
                            break
                    if srv:
                        break
                    if s.get("zerotier_virtual_ip") == clean_h or s.get("easytier_virtual_ip") == clean_h:
                        srv = s
                        break
                    sname = (s.get("name") or "").lower()
                    if sname and sname in clean_h:
                        srv = s
                        break

            if not srv:
                srv = config_manager.get_active_server(cfg)

            url, _ = config_manager.resolve_target_connection(cfg, check_network=False, target_server=srv)
            default_host = (urllib.parse.urlparse(url).hostname or "zimaos.local").strip()
            host = req_host if req_host else default_host

            raw_port = body.get("port", 22)
            try:
                port = int(raw_port) if raw_port not in (None, "") else 22
            except (TypeError, ValueError):
                self._send_json(
                    {"status": "error", "success": False, "error": "Port SSH tidak valid (harus angka 1-65535)."},
                    status=400,
                )
                return
            if port < 1 or port > 65535:
                self._send_json(
                    {"status": "error", "success": False, "error": "Port SSH harus di antara 1 sampai 65535."},
                    status=400,
                )
                return

            # v4.5.2 Beta: Failover otomatis WAN/Domain publik -> Remote Virtual IP P2P (ZeroTier / EasyTier)
            from smb_mount_manager import _is_domain_or_wan_host
            if _is_domain_or_wan_host(host) and srv:
                rem_info = config_manager.get_dynamic_remote_info(srv, cfg)
                rem_ip = rem_info.get("ip") if rem_info else ""
                if not rem_ip:
                    rem_ip = (srv.get("easytier_virtual_ip") or srv.get("zerotier_virtual_ip") or "").strip()
                if rem_ip:
                    logger_manager.log_info(f"[api/server/ssh_terminal] Host WAN/Domain '{host}' terdeteksi -> Failover target SSH dialihkan ke Remote Virtual IP ({rem_ip}:{port})")
                    host = rem_ip

            # v4.5.1 / v4.6.5 Beta: Resolusi akun SSH eksplisit > tersimpan per server > kredensial profil aktif
            req_user = (body.get("user") or "").strip()
            user = ""
            if req_user:
                user = req_user
            elif srv:
                user = (srv.get("ssh_user") or "").strip()
                if not user:
                    active_p = srv.get("active_profile", "")
                    creds = srv.get("credentials", {})
                    if active_p and isinstance(creds, dict) and active_p in creds:
                        user = (creds[active_p].get("username") or "").strip()
                if not user:
                    user = (srv.get("default_user") or srv.get("username") or "").strip()
            if not user:
                user = "casaos"

            import re as _re
            if not _re.match(r"^[A-Za-z0-9._-]+$", user):
                self._send_json(
                    {
                        "status": "error",
                        "success": False,
                        "error": "Username SSH hanya boleh berisi huruf, angka, titik (.), garis bawah (_), atau tanda hubung (-).",
                    },
                    status=400,
                )
                return

            if not host or not _re.match(r"^[A-Za-z0-9._:-]+$", host):
                self._send_json(
                    {"status": "error", "success": False, "error": "Host / IP SSH tidak valid."},
                    status=400,
                )
                return

            save_ssh_user = bool(body.get("saveSshUser", True))
            if srv is not None and req_user and save_ssh_user:
                if (srv.get("ssh_user") or "").strip() != user:
                    srv["ssh_user"] = user
                    config_manager.save_config(cfg)

            ssh_cmd = f"ssh -p {port} {user}@{host}" if port != 22 else f"ssh {user}@{host}"
            launched = False
            try:
                ps_cmd = [
                    "powershell.exe",
                    "-NoExit",
                    "-Command",
                    f'Write-Host "Menghubungkan Terminal SSH ke Server ({user}@{host}:{port})..." -ForegroundColor Green; {ssh_cmd}'
                ]
                subprocess.Popen(ps_cmd)
                launched = True
            except Exception as te:
                logger_manager.log_debug(f"[api/server/ssh_terminal] Gagal meluncurkan terminal: {te}")
            self._send_json({"status": "ok", "success": True, "command": ssh_cmd, "host": host, "user": user, "port": port, "launched": launched})
            return

        if path == "/api/vm/open_window":
            target_url = (body.get("url") or "").strip()
            win_title = (body.get("title") or body.get("name") or "MyServer VM Screen").strip()
            vm_id = (body.get("vmId") or body.get("id") or "vm_default").strip()
            if target_url:
                success, msg = spawn_app_window(target_url, win_title, vm_id=vm_id, force_window=True)
                self._send_json({"success": success, "message": msg, "url": target_url, "title": win_title, "vmId": vm_id})
            else:
                self._send_json({"success": False, "message": "URL layar virtual kosong"}, status=400)
            return

        # --- Endpoints InstaBox & Antigravity Remote (v4.4.0 Beta) ---
        if path == "/api/instabox/vms/add":
            if instabox_manager:
                new_vm = instabox_manager.InstaBoxManager.add_vm(body)
                self._send_json({"status": "ok", "vm": new_vm})
            else:
                self._send_json({"status": "error", "message": "instabox_manager not available"}, status=500)
            return

        if path == "/api/instabox/vms/update":
            vm_id = body.get("id")
            if instabox_manager and vm_id:
                upd_vm = instabox_manager.InstaBoxManager.update_vm(vm_id, body)
                self._send_json({"status": "ok", "vm": upd_vm})
            else:
                self._send_json({"status": "error", "message": "VM ID missing or instabox_manager not available"}, status=400)
            return

        if path == "/api/instabox/vms/delete":
            vm_id = body.get("id")
            if instabox_manager and vm_id:
                ok = instabox_manager.InstaBoxManager.delete_vm(vm_id)
                self._send_json({"status": "ok", "success": ok})
            else:
                self._send_json({"status": "error", "message": "VM ID missing or instabox_manager not available"}, status=400)
            return

        if path in ("/api/instabox/wake", "/api/instabox/pause"):
            action_type = "resume" if path == "/api/instabox/wake" else "suspend"
            action_name = "dibangunkan" if action_type == "resume" else "ditidurkan"
            new_status = "running" if action_type == "resume" else "sleeping"

            vm_id = body.get("id") or body.get("vmId")
            api_key = (body.get("apiKey") or "").strip()
            machine_id = (body.get("machineId") or "").strip()
            vm_name = (body.get("vmName") or body.get("name") or "").strip()

            cfg = config_manager.load_or_create_config() if config_manager else {}
            all_vms = (cfg.get("vms", []) or []) + (cfg.get("instabox_vms", []) or [])

            # Isolasi: VM scope server dieksekusi oleh backend ZimaOS, bukan dari PC ini
            req_scope = str(body.get("scope") or "").strip().lower()
            req_server_id = (body.get("serverId") or "").strip() or None
            if _find_server_vm(cfg, vm_id) or req_scope == "server" or bool(req_server_id):
                srv_action = "wake" if action_type == "resume" else "sleep"
                patch_data = {"status": new_status}
                if new_status != "running":
                    patch_data["runtimeMinutes"] = 0
                _record_recent_vm_mutation(vm_id, patch_data, ttl=15.0)
                ok, data, code = _proxy_server_vm_action(cfg, vm_id, srv_action, target_server_id=req_server_id)
                if ok:
                    for v in cfg.get("vms", []):
                        if isinstance(v, dict) and v.get("id") == vm_id:
                            v["status"] = new_status
                            if new_status != "running":
                                v["runtimeMinutes"] = 0
                    if config_manager:
                        config_manager.save_config(cfg)
                    self._send_json({
                        "status": "ok",
                        "message": f"VM berhasil {action_name} (dieksekusi oleh server).",
                        "vmStatus": new_status,
                        "machineId": machine_id,
                        "executedBy": "server",
                        "result": data,
                    })
                else:
                    _recent_vm_mutations.pop(vm_id, None)
                    self._send_json({"status": "error", "message": str(data)}, status=code)
                return

            # Cari kredensial dari config jika tidak dikirim dari frontend
            if (not api_key or not machine_id) and vm_id:
                for v in all_vms:
                    if isinstance(v, dict) and v.get("id") == vm_id:
                        api_key = api_key or v.get("apiKey", "")
                        machine_id = machine_id or v.get("machineId", "")
                        vm_name = vm_name or v.get("name", "")
                        break

            # Jika apiKey masih kosong, ambil dari VM manapun yang memilikinya
            if not api_key:
                for v in all_vms:
                    if isinstance(v, dict) and v.get("apiKey"):
                        api_key = v.get("apiKey")
                        break

            if not api_key:
                self._send_json({"status": "error", "message": "API Key InstaBox belum diisi."}, status=400)
                return

            # Jika machine_id belum ada, temukan via list machines API
            if not machine_id:
                try:
                    m_req = urllib.request.Request("https://api.instabox.sh/v1/machines", headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
                    with urllib.request.urlopen(m_req, timeout=8) as m_resp:
                        raw_data = m_resp.read()
                        m_list = json.loads(raw_data.decode("utf-8")).get("machines", [])
                        if m_list:
                            if vm_name:
                                norm_target = re.sub(r"[^a-z0-9]", "", vm_name.lower())
                                for m in m_list:
                                    mn = m.get("name", "")
                                    if mn and (norm_target in re.sub(r"[^a-z0-9]", "", mn.lower()) or re.sub(r"[^a-z0-9]", "", mn.lower()) in norm_target):
                                        machine_id = m.get("id")
                                        break
                            if not machine_id:
                                machine_id = m_list[0].get("id")
                except Exception as me:
                    logger_manager.log_warn(f"[InstaBox {action_type}] Gagal auto-resolve machineId: {me}")

            if not machine_id:
                self._send_json({"status": "error", "message": "Machine ID InstaBox tidak ditemukan di akun ini."}, status=400)
                return

            req_url = f"https://api.instabox.sh/v1/machines/{machine_id}/{action_type}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Idempotency-Key": str(uuid.uuid4())
            }
            try:
                if action_type == "suspend":
                    try:
                        _instabox_release_lease(api_key, machine_id, vm_id)
                    except Exception:
                        pass
                req = urllib.request.Request(req_url, data=b"{}", headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=12) as resp:
                    raw_b = resp.read()
                    resp_data = json.loads(raw_b.decode("utf-8")) if raw_b else {"status": "ok"}

                if vm_id:
                    patch_data = {"status": new_status, "machineId": machine_id}
                    if new_status != "running":
                        patch_data["runtimeMinutes"] = 0
                    _record_recent_vm_mutation(vm_id, patch_data, ttl=15.0)

                # Update status secara persisten di config
                changed = False
                ka_enabled_local = False
                for v in cfg.get("vms", []):
                    if isinstance(v, dict) and (v.get("id") == vm_id or v.get("machineId") == machine_id):
                        v["status"] = new_status
                        v["machineId"] = machine_id
                        v["apiKey"] = api_key
                        ka_enabled_local = ka_enabled_local or bool(v.get("keepAliveEnabled"))
                        if new_status != "running":
                            v["runtimeMinutes"] = 0
                            v["sleepingSince"] = int(time.time() * 1000)
                        else:
                            v.pop("sleepingSince", None)
                        v["lastActive"] = "Just now" if new_status == "running" else "Sleeping"
                        changed = True
                if changed and config_manager:
                    config_manager.save_config(cfg)
                if action_type == "resume" and ka_enabled_local:
                    threading.Thread(
                        target=_instabox_maintain_keepalive,
                        args=(api_key, machine_id, vm_id or machine_id, True),
                        daemon=True,
                    ).start()

                self._send_json({
                    "status": "ok",
                    "message": f"VM berhasil {action_name}.",
                    "vmStatus": new_status,
                    "machineId": machine_id,
                    "result": resp_data
                })
            except urllib.error.HTTPError as he:
                err_txt = he.read().decode("utf-8") if hasattr(he, "read") else ""
                self._send_json({"status": "error", "message": f"InstaBox API HTTP {he.code}: {err_txt}", "code": he.code}, status=he.code)
            except Exception as ex:
                self._send_json({"status": "error", "message": f"Gagal mengeksekusi {action_type}: {ex}"}, status=500)
            return

        if path == "/api/instabox/preflight_launch":
            vm_id = body.get("id")
            target_port = body.get("target_port") or body.get("port") or 8080
            if instabox_manager and vm_id:
                res = instabox_manager.InstaBoxManager.preflight_launch(vm_id, target_port=target_port)
                self._send_json(res)
            else:
                self._send_json({"status": "error", "message": "VM ID missing or instabox_manager not available"}, status=400)
            return

        if path == "/api/instabox/smart_reset":
            api_key = (body.get("apiKey") or "").strip()
            machine_id = (body.get("machineId") or "").strip()
            vm_id = body.get("id") or body.get("vmId")
            _sr_cfg = config_manager.load_or_create_config() if config_manager else {}
            _sr_scope = str(body.get("scope") or "").strip().lower()
            _sr_srv_id = (body.get("serverId") or "").strip() or None
            if _find_server_vm(_sr_cfg, vm_id) or _sr_scope == "server" or bool(_sr_srv_id):
                _record_recent_vm_mutation(vm_id, {"status": "running", "runtimeMinutes": 0, "_lastResetAt": time.time()}, ttl=25.0)
                ok, data, code = _proxy_server_vm_action(_sr_cfg, vm_id, "smart-reset", timeout=60.0, target_server_id=_sr_srv_id)
                if ok:
                    for v in _sr_cfg.get("vms", []):
                        if isinstance(v, dict) and v.get("id") == vm_id:
                            v["status"] = "running"
                            v["runtimeMinutes"] = 0
                    if config_manager:
                        config_manager.save_config(_sr_cfg)
                    self._send_json({"success": True, "status": "ok", "executedBy": "server",
                                     "message": "Smart reset dieksekusi oleh server ZimaOS.", "result": data})
                else:
                    _recent_vm_mutations.pop(vm_id, None)
                    self._send_json({"success": False, "status": "error", "error": str(data), "message": str(data)}, status=code)
                return
            if not machine_id and vm_id:
                for v in _sr_cfg.get("vms", []):
                    if isinstance(v, dict) and v.get("id") == vm_id:
                        machine_id = machine_id or v.get("machineId", "")
                        api_key = api_key or v.get("apiKey", "")
                        break
            if not machine_id and instabox_manager and vm_id:
                vm_rec = instabox_manager.InstaBoxManager.get_vm(vm_id)
                if vm_rec:
                    machine_id = vm_rec.get("machineId", "")
                    api_key = api_key or vm_rec.get("apiKey", "")

            if machine_id and api_key:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(uuid.uuid4())
                }
                try:
                    p_req = urllib.request.Request(f"https://api.instabox.sh/v1/machines/{machine_id}/suspend", data=b"{}", headers=headers, method="POST")
                    urllib.request.urlopen(p_req, timeout=10)
                    time.sleep(3)
                    r_req = urllib.request.Request(f"https://api.instabox.sh/v1/machines/{machine_id}/resume", data=b"{}", headers=headers, method="POST")
                    urllib.request.urlopen(r_req, timeout=10)
                    if vm_id:
                        _record_recent_vm_mutation(vm_id, {"status": "running", "runtimeMinutes": 0, "_lastResetAt": time.time()}, ttl=25.0)
                        for v in _sr_cfg.get("vms", []):
                            if isinstance(v, dict) and v.get("id") == vm_id:
                                v["status"] = "running"
                                v["runtimeMinutes"] = 0
                        if config_manager:
                            config_manager.save_config(_sr_cfg)
                    self._send_json({"success": True, "status": "ok", "message": "Time limit 8 jam berhasil direset ke 0."})
                    return
                except Exception as ex:
                    self._send_json({"success": False, "error": str(ex)})
                    return
            elif instabox_manager and vm_id:
                res = instabox_manager.InstaBoxManager.smart_anti_cooldown_reset(vm_id)
                self._send_json(res)
                return
            else:
                self._send_json({"status": "error", "message": "Machine ID / API Key missing"}, status=400)
                return

        if path == "/api/instabox/sync":
            _sy_vm_id = (body.get("vmId") or "").strip()
            _sy_cfg = config_manager.load_or_create_config() if config_manager else {}
            _sy_scope = str(body.get("scope") or "").strip().lower()
            _sy_srv_id = (body.get("serverId") or "").strip() or None
            if _find_server_vm(_sy_cfg, _sy_vm_id) or _sy_scope == "server" or bool(_sy_srv_id):
                ok, data, code = _proxy_server_vm_action(_sy_cfg, _sy_vm_id, "sync", timeout=20.0, target_server_id=_sy_srv_id)
                if ok and isinstance(data, dict):
                    _apply_recent_vm_mutation(data)
                    st = str(data.get("status") or "").lower()
                    self._send_json({
                        "success": True,
                        "executedBy": "server",
                        "state": "running" if st == "running" else "suspended",
                        "machineId": data.get("machineId") or data.get("machine_id"),
                        "runtimeMinutes": data.get("runtimeMinutes", data.get("runtime_minutes", 0)),
                        "maxRuntimeMinutes": data.get("maxRuntimeMinutes", 480),
                        "sshHost": data.get("sshHost") or "ssh.instabox.sh",
                        "sshPort": data.get("sshPort") or 2222,
                        "sshUser": data.get("sshUser"),
                        "telemetry": data.get("telemetry"),
                    })
                else:
                    self._send_json({"success": False, "error": str(data)})
                return
            api_key = (body.get("apiKey") or "").strip()
            vm_name = (body.get("vmName") or "").strip()
            machine_id = (body.get("machineId") or "").strip()
            vm_id = (body.get("vmId") or "").strip()
            existing_local_vm = next((v for v in (_sy_cfg.get("vms", []) or []) if isinstance(v, dict) and v.get("id") == vm_id), None)
            if not api_key and existing_local_vm:
                api_key = existing_local_vm.get("apiKey", "")
                machine_id = machine_id or existing_local_vm.get("machineId", "")
                vm_name = vm_name or existing_local_vm.get("name", "")
            if not api_key and instabox_manager and vm_id:
                vm_rec = instabox_manager.InstaBoxManager.get_vm(vm_id)
                if vm_rec:
                    api_key = vm_rec.get("apiKey", "")
                    machine_id = machine_id or vm_rec.get("machineId", "")
                    vm_name = vm_name or vm_rec.get("name", "")

            if not api_key:
                self._send_json({"success": False, "error": "API Key InstaBox belum diisi."})
                return

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": "MyServer-Companion/4.4.4"
            }
            try:
                # 1. Fetch machines list from https://api.instabox.sh/v1/machines
                req = urllib.request.Request("https://api.instabox.sh/v1/machines", headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    m_data = json.loads(resp.read().decode())
                    machines = m_data.get("machines", [])
                    if not machines:
                        self._send_json({"success": False, "error": "Tidak ada microVM ditemukan di akun InstaBox ini."})
                        return

                    target = None
                    if machine_id:
                        target = next((m for m in machines if m.get("id") == machine_id), None)
                    if not target and vm_name:
                        target = next((m for m in machines if m.get("name", "").strip().lower() == vm_name.strip().lower()), None)
                    if not target and vm_name:
                        target = next((m for m in machines if vm_name.strip().lower() in m.get("name", "").strip().lower() or m.get("name", "").strip().lower() in vm_name.strip().lower()), None)
                    if not target and vm_name:
                        import re
                        s_vm = re.sub(r'[^a-z0-9]', '', vm_name.lower())
                        target = next((m for m in machines if s_vm and (s_vm in re.sub(r'[^a-z0-9]', '', m.get("name", "").lower()) or re.sub(r'[^a-z0-9]', '', m.get("name", "").lower()) in s_vm)), None)
                    if not target:
                        target = next((m for m in machines if str(m.get("state", "")).lower() == "running"), machines[0])

                    mid = target.get("id")

                    # Ambil detail mesin /v1/machines/{mid} jika runStartedAt tidak ada di list item
                    if mid and not (target.get("runStartedAt") or target.get("currentRunSeconds")):
                        try:
                            d_req = urllib.request.Request(f"https://api.instabox.sh/v1/machines/{mid}", headers=headers)
                            with urllib.request.urlopen(d_req, timeout=6) as d_resp:
                                d_raw = json.loads(d_resp.read().decode())
                                d_obj = d_raw.get("machine") if isinstance(d_raw.get("machine"), dict) else d_raw
                                if isinstance(d_obj, dict):
                                    target = {**target, **d_obj}
                        except Exception:
                            pass

                    state = str(target.get("state") or target.get("status") or "running").lower()
                    desired = str(target.get("desiredState") or "").lower()
                    if desired == "running" and state in ("starting", "resuming", "waking", "provisioning"):
                        state = "running"
                    elif desired == "suspended" and state in ("suspending", "stopping"):
                        state = "suspended"

                    # Hormati recent mutation lock jika user baru saja klik Wake/Sleep/Reset
                    mut_entry = _recent_vm_mutations.get(vm_id) if vm_id else None
                    last_reset_at = None
                    if mut_entry and time.time() < mut_entry.get("expires_at", 0):
                        mpatch = mut_entry.get("patch") or {}
                        if mpatch.get("status") == "running":
                            state = "running"
                        elif mpatch.get("status") in ("sleeping", "stopped"):
                            state = "suspended"
                        if mpatch.get("_lastResetAt"):
                            last_reset_at = float(mpatch["_lastResetAt"])

                    is_running = state in ("running", "active")

                    raw_max_run = target.get("maxRunMinutes")
                    if raw_max_run is not None:
                        try:
                            max_run_int = int(raw_max_run)
                            max_run_mins = -1 if max_run_int < 0 else max(1, max_run_int)
                        except Exception:
                            max_run_mins = 480
                    else:
                        max_run_mins = 480

                    # v4.5.2+ Beta: Ekstraksi durasi runtime riil dari seluruh kemungkinan field InstaBox
                    runtime_mins = 0
                    if is_running:
                        if last_reset_at and (time.time() - last_reset_at < 25.0):
                            runtime_mins = 0
                        else:
                            run_secs = target.get("currentRunSeconds") or target.get("uptimeSeconds") or target.get("runDurationSeconds")
                            run_started_at = target.get("runStartedAt") or target.get("startedAt")
                            if run_started_at:
                                try:
                                    clean_iso = str(run_started_at).replace("Z", "+00:00")
                                    dt = datetime.datetime.fromisoformat(clean_iso)
                                    if dt.tzinfo is None:
                                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                                    if last_reset_at:
                                        reset_dt = datetime.datetime.fromtimestamp(last_reset_at, tz=datetime.timezone.utc)
                                        if reset_dt > dt:
                                            dt = reset_dt
                                    now = datetime.datetime.now(datetime.timezone.utc)
                                    raw_mins = max(0, int((now - dt).total_seconds() / 60))
                                    runtime_mins = min(max_run_mins, raw_mins) if max_run_mins > 0 else raw_mins
                                except Exception:
                                    runtime_mins = int((existing_local_vm or {}).get("runtimeMinutes") or 0)
                            elif run_secs and run_secs > 0:
                                raw_mins = max(0, int(run_secs // 60))
                                runtime_mins = min(max_run_mins, raw_mins) if max_run_mins > 0 else raw_mins
                            else:
                                # Pertahankan runtimeMinutes sebelumnya jika API tidak mengembalikan runStartedAt
                                runtime_mins = int((existing_local_vm or {}).get("runtimeMinutes") or 0)

                    # 2. Spec fallback for RAM and Disk sizing
                    spec = target.get("spec") or {}
                    spec_mem_mib = spec.get("memMiB")
                    spec_disk_gib = (spec.get("persistentDiskGiB") or 0) + (spec.get("rootDiskGiB") or 0)

                    # 3. Fetch metrics for CPU %, RAM, Disk
                    metrics_res = {
                        "cpuPct": None,
                        "ramUsedBytes": None,
                        "ramTotalBytes": spec_mem_mib * 1024 * 1024 if spec_mem_mib else None,
                        "diskUsedBytes": None,
                        "diskTotalBytes": spec_disk_gib * (1024**3) if spec_disk_gib > 0 else None
                    }
                    try:
                        m_req = urllib.request.Request(f"https://api.instabox.sh/v1/machines/{mid}/metrics", headers=headers)
                        with urllib.request.urlopen(m_req, timeout=6) as m_resp:
                            m_raw = json.loads(m_resp.read().decode())
                            samples = m_raw.get("metrics", [])
                            disk_info = m_raw.get("disk", {})
                            if samples:
                                latest = samples[-1]
                                cpu_val = latest.get("cpuUsedPct") if latest.get("cpuUsedPct") is not None else latest.get("cpuPct")
                                if cpu_val is not None:
                                    metrics_res["cpuPct"] = round(float(cpu_val), 1)

                                mem_used = latest.get("memUsed") if latest.get("memUsed") is not None else latest.get("memoryUsedBytes")
                                if mem_used is not None:
                                    metrics_res["ramUsedBytes"] = mem_used

                                mem_total = latest.get("memTotal") if latest.get("memTotal") is not None else latest.get("memoryTotalBytes")
                                if mem_total:
                                    metrics_res["ramTotalBytes"] = mem_total

                                if latest.get("diskUsed") is not None:
                                    metrics_res["diskUsedBytes"] = latest.get("diskUsed")
                                if latest.get("diskTotal") is not None:
                                    metrics_res["diskTotalBytes"] = latest.get("diskTotal")

                            if disk_info and isinstance(disk_info, dict):
                                filesystems = disk_info.get("filesystems", [])
                                if filesystems:
                                    tot_used = sum(fs.get("usedBytes", 0) for fs in filesystems if fs.get("usedBytes"))
                                    tot_size = sum(fs.get("sizeBytes", 0) for fs in filesystems if fs.get("sizeBytes"))
                                    if tot_used > 0:
                                        metrics_res["diskUsedBytes"] = tot_used
                                    if tot_size > 0:
                                        metrics_res["diskTotalBytes"] = tot_size
                                elif disk_info.get("usedBytes"):
                                    metrics_res["diskUsedBytes"] = disk_info.get("usedBytes")
                                    if disk_info.get("totalBytes"):
                                        metrics_res["diskTotalBytes"] = disk_info.get("totalBytes")
                    except Exception as me:
                        logger_manager.log_warn(f"[InstaBox] Gagal mengambil metrics VM {mid}: {me}")

                    # Jika mesin dalam kondisi tidur/suspended, metrik aktif tidak valid (CPU 0/kosong)
                    if not is_running:
                        metrics_res["cpuPct"] = None
                        metrics_res["ramUsedBytes"] = None
                        metrics_res["diskUsedBytes"] = None

                    # 4. Connection Info for host / port / username
                    conn_host = "ssh.instabox.sh"
                    conn_port = 2222
                    conn_user = None
                    try:
                        ci_req = urllib.request.Request(f"https://api.instabox.sh/v1/machines/{mid}/connection-info", headers=headers)
                        with urllib.request.urlopen(ci_req, timeout=5) as ci_resp:
                            ci_data = json.loads(ci_resp.read().decode())
                            conn_host = ci_data.get("host") or conn_host
                            conn_port = ci_data.get("port") or conn_port
                            conn_user = ci_data.get("username") or ci_data.get("user")
                    except Exception:
                        pass

                    # Simpan hasil sinkronisasi ke cfg["vms"] agar loadVms (polling 4s) tidak menimpa runtimeMinutes ke 0!
                    if existing_local_vm and config_manager and _deleted_vms_tombstone.get(vm_id, 0) <= time.time():
                        existing_local_vm["machineId"] = mid
                        existing_local_vm["status"] = "running" if is_running else "sleeping"
                        existing_local_vm["runtimeMinutes"] = runtime_mins
                        existing_local_vm["maxRuntimeMinutes"] = max_run_mins
                        existing_local_vm["sshHost"] = conn_host or "ssh.instabox.sh"
                        existing_local_vm["sshPort"] = conn_port or 2222
                        existing_local_vm["sshUser"] = conn_user or mid
                        existing_local_vm["telemetry"] = metrics_res
                        config_manager.save_config(_sy_cfg)

                    self._send_json({
                        "success": True,
                        "machineId": mid,
                        "machineName": target.get("name"),
                        "state": state,
                        "runtimeMinutes": runtime_mins,
                        "maxRuntimeMinutes": max_run_mins,
                        "idleTimeoutMinutes": int(target.get("autoSuspendAfterSeconds", 1800) / 60),
                        "screenUrl": f"https://dashboard.instabox.sh/machines/{mid}",
                        "sshHost": conn_host or "ssh.instabox.sh",
                        "sshPort": conn_port or 2222,
                        "sshUser": conn_user or mid,
                        "telemetry": metrics_res
                    })
                    return
            except urllib.error.HTTPError as he:
                self._send_json({"success": False, "error": f"InstaBox API Error ({he.code}): {he.reason}"})
                return
            except Exception as ex:
                self._send_json({"success": False, "error": f"Koneksi InstaBox gagal: {ex}"})
                return

        # --- Endpoints EasyTier & Remote Mesh Network ---
        if path in ("/api/easytier/status", "/api/easytier_status"):
            if easytier_manager:
                mgr = easytier_manager.get_easytier_manager()
                status = mgr.get_status_overview()
                self._send_json({"success": True, "data": status, **status})
            else:
                self._send_json({"success": False, "running": False, "error": "easytier_manager not available", "data": {"running": False}})
            return

        if path in ("/api/easytier/peers", "/api/easytier_peers"):
            if easytier_manager:
                mgr = easytier_manager.get_easytier_manager()
                self._send_json({"peers": mgr.get_peers()})
            else:
                self._send_json({"peers": []})
            return

        if path in ("/api/easytier/start", "/api/easytier_start"):
            if not easytier_manager:
                self._send_json({"success": False, "message": "easytier_manager tidak tersedia"})
                return
            remote_id = (body.get("remote_id") or body.get("remoteId") or "").strip().lower()
            net_name = body.get("network_name") or body.get("networkName") or ""
            net_secret = body.get("network_secret") or body.get("networkSecret") or ""
            ipv4 = body.get("ipv4") or ""
            peers = body.get("peers") or []
            use_no_tun = bool(body.get("use_no_tun") or body.get("useNoTun", False))
            ext_node = body.get("external_node") or body.get("externalNode") or ""

            cfg = config_manager.load_or_create_config()
            srv = config_manager.get_active_server(cfg) or {}

            # Jika remote_id tidak dikirim, fallback ke Remote ID server aktif
            if not remote_id and not net_name:
                remote_id = (srv.get("zerotier_network_id") or srv.get("remote_id") or "").strip().lower()

            if remote_id:
                # Jika user memasukkan remote_id manual (misal setup baru beda jaringan), sinkronkan ke server aktif
                cur_nwid = (srv.get("zerotier_network_id") or srv.get("remote_id") or "").strip().lower()
                if remote_id != cur_nwid:
                    srv["zerotier_network_id"] = remote_id
                    srv["remote_id"] = remote_id
                params = easytier_manager.derive_easytier_params(remote_id)
                net_name = params["network_name"]
                net_secret = params["network_secret"]

            # Simpan ke config.json
            if "easytier" not in cfg:
                cfg["easytier"] = {}
            if remote_id:
                cfg["easytier"]["remote_id"] = remote_id
            cfg["easytier"]["network_name"] = net_name
            cfg["easytier"]["network_secret"] = net_secret
            cfg["easytier"]["ipv4"] = ipv4
            cfg["easytier"]["enabled"] = True
            config_manager.save_config(cfg)

            mgr = easytier_manager.get_easytier_manager()
            ok, msg = mgr.start_easytier(
                network_name=net_name,
                network_secret=net_secret,
                ipv4=ipv4,
                peers=peers,
                use_no_tun=use_no_tun,
                external_node=ext_node,
                remote_id=remote_id,
            )
            self._send_json({"success": ok, "message": msg, "status": mgr.get_status_overview()})
            return

        if path in ("/api/easytier/stop", "/api/easytier_stop"):
            if easytier_manager:
                cfg = config_manager.load_or_create_config()
                if "easytier" in cfg:
                    cfg["easytier"]["enabled"] = False
                    config_manager.save_config(cfg)
                _unmount_myserver_smb_drives(
                    reason="easytier_stop",
                    cfg=cfg,
                    include_easytier_subnet=True,
                    easytier_only=True,
                )
                smb_mount_manager.invalidate_smb_host_cache()
                mgr = easytier_manager.get_easytier_manager()
                ok, msg = mgr.stop_easytier()
                try:
                    refresh_drives_cache_immediately()
                except Exception:
                    pass
                self._send_json({"success": ok, "message": msg, "status": mgr.get_status_overview()})
            else:
                self._send_json({"success": False, "message": "easytier_manager tidak tersedia"})
            return

        if path in ("/api/remote/status", "/api/remote_status"):
            et_status = easytier_manager.get_easytier_manager().get_status_overview() if easytier_manager else {"running": False}
            zt_client = zerotier_manager.ZeroTierClient() if "zerotier_manager" in globals() else None
            zt_node = zt_client.get_node_status() if zt_client else {"online": False}
            zt_nets = zt_client.get_joined_networks() if (zt_client and zt_node.get("online")) else []

            active_engine = "none"
            if et_status.get("running"):
                active_engine = "easytier"
            elif zt_node.get("online") and len(zt_nets) > 0:
                active_engine = "zerotier"

            self._send_json({
                "activeEngine": active_engine,
                "easytier": et_status,
                "zerotier": {
                    "running": zt_node.get("online", False),
                    "nodeId": zt_node.get("address", ""),
                    "version": zt_node.get("version", ""),
                    "networks": zt_nets,
                }
            })
            return

        if path == "/api/check_for_update":
            update_res = check_github_update_core()
            self._send_json(update_res)
            return

        if False and path == "/api/check_for_update_legacy":
            cfg = config_manager.load_or_create_config()
            repo_slug = cfg.get("github_repo", "Gibranibang/My-Server-beta")
            url = f"https://api.github.com/repos/{repo_slug}/releases/latest"
            headers = {
                "User-Agent": f"MyServer-Companion/{APP_VERSION_NUMBER}",
                "Accept": "application/vnd.github.v3+json"
            }
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    rel_data = json.loads(resp.read().decode("utf-8"))
                    tag = rel_data.get("tag_name", "").lstrip("v").strip()
                    
                    def _parse_ver(v_str):
                        import re
                        parts = re.findall(r"\d+", v_str)
                        return tuple(map(int, parts)) if parts else (0, 0, 0)
                    
                    remote_ver = _parse_ver(tag)
                    curr_ver = _parse_ver(APP_VERSION_NUMBER)
                    
                    if remote_ver > curr_ver:
                        download_url = rel_data.get("html_url", "")
                        for asset in rel_data.get("assets", []):
                            aname = asset.get("name", "").lower()
                            if aname.endswith("-setup.exe") or aname.endswith(".exe") or aname.endswith(".zip"):
                                download_url = asset.get("browser_download_url", download_url)
                                break
                        self._send_json({
                            "upToDate": False,
                            "version": tag,
                            "currentVersion": APP_VERSION_NUMBER,
                            "htmlUrl": rel_data.get("html_url", ""),
                            "downloadUrl": download_url,
                            "name": rel_data.get("name", f"MyServer v{tag}"),
                            "body": rel_data.get("body", "")
                        })
                        return
                    else:
                        self._send_json({
                            "upToDate": True,
                            "version": APP_VERSION_NUMBER,
                            "currentVersion": APP_VERSION_NUMBER,
                            "message": "Aplikasi sudah menggunakan versi terbaru."
                        })
                        return
            except urllib.error.HTTPError as he:
                if he.code == 404:
                    self._send_json({
                        "upToDate": True,
                        "version": APP_VERSION_NUMBER,
                        "currentVersion": APP_VERSION_NUMBER,
                        "message": "Aplikasi sudah menggunakan versi terbaru (Belum ada rilis baru di GitHub)."
                    })
                    return
                self._send_json({
                    "upToDate": True,
                    "version": APP_VERSION_NUMBER,
                    "warning": f"HTTP {he.code}: {he.reason}"
                })
                return
            except Exception as ex:
                self._send_json({
                    "upToDate": True,
                    "version": APP_VERSION_NUMBER,
                    "warning": f"Gagal menghubungi GitHub: {str(ex)}"
                })
                return

        if path == "/api/copy_log":
            log_text = logger_manager.get_recent_log_summary(100) if hasattr(logger_manager, "get_recent_log_summary") else "No logs"
            try:
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", "Set-Clipboard -Value $input"],
                    stdin=subprocess.PIPE,
                    creationflags=0x08000000
                ).communicate(input=log_text.encode("utf-8"))
            except Exception:
                pass
            self._send_json({"success": True, "log": log_text})
            return

        
        if path == "/api/get_log_directory":
            self._send_json(logger_manager.get_log_status() if hasattr(logger_manager, "get_log_status") else {"logDirectory": "", "defaultDirectory": "", "isCustom": False})
            return

        if path == "/api/choose_log_folder":
            chosen = dialog_helper.prompt_choose_folder("Pilih Folder Penyimpanan Log MyServer") if hasattr(dialog_helper, "prompt_choose_folder") else None
            if chosen:
                res = logger_manager.set_configured_log_dir(chosen) if hasattr(logger_manager, "set_configured_log_dir") else {"success": False, "error": "LoggerManager not ready"}
                self._send_json(res)
            else:
                self._send_json({"success": False, "cancelled": True})
            return

        if path == "/api/reset_log_directory":
            res = logger_manager.reset_log_dir_to_default() if hasattr(logger_manager, "reset_log_dir_to_default") else {"success": False, "error": "LoggerManager not ready"}
            self._send_json(res)
            return

        if path == "/api/save_log_as":
            target_path = dialog_helper.prompt_save_log() if hasattr(dialog_helper, "prompt_save_log") else None
            if not target_path:
                self._send_json({"cancelled": True})
                return
            src_log = logger_manager.get_log_file_path() if hasattr(logger_manager, "get_log_file_path") else ""
            if src_log and os.path.exists(src_log):
                try:
                    shutil.copy2(src_log, target_path)
                    self._send_json({"success": True, "path": target_path})
                    return
                except Exception as e:
                    self._send_json({"success": False, "error": str(e)})
                    return
            else:
                try:
                    with open(target_path, "w", encoding="utf-8") as f:
                        f.write(logger_manager.get_recent_log_summary(100) if hasattr(logger_manager, "get_recent_log_summary") else "")
                    self._send_json({"success": True, "path": target_path})
                    return
                except Exception as e:
                    self._send_json({"success": False, "error": str(e)})
                    return















        if path == "/api/open_log_file":







            log_p = logger_manager.get_log_file_path()







            if os.path.exists(log_p):







                os.startfile(log_p)







            self._send_json({"success": True})







            return















        if path == "/api/open_log_folder":







            log_d = logger_manager.get_configured_log_dir() if hasattr(logger_manager, "get_configured_log_dir") else (logger_manager.get_log_dir_path() if hasattr(logger_manager, "get_log_dir_path") else "")







            if log_d and os.path.exists(log_d):







                os.startfile(log_d)







            self._send_json({"success": True})







            return















        if path == "/api/open_changelog":







            changelog_manager.open_changelog_window() if hasattr(changelog_manager, "open_changelog_window") else None







            self._send_json({"success": True})







            return















        # ----------------------------------------------------------------------







        # SESI 5: Multi-Server, Multi-Route, Profil & ZeroTier







        # ----------------------------------------------------------------------







        if path == "/api/get_server_details":
            self._send_json(get_server_details_data())
            return

        if path in ("/api/server/backend_status", "/api/server_backend_status"):
            req_srv_id = (body.get("serverId") or body.get("server_id") or "").strip() or None if isinstance(body, dict) else None
            self._send_json(_get_backend_health_info(force=True, target_server_id=req_srv_id))
            return















        if path == "/api/switch_server":







            server_id = (body.get("serverId") or body.get("arg") or "").strip()







            cfg = config_manager.load_or_create_config()







            servers = cfg.get("servers", [])







            target_srv = next((s for s in servers if s.get("id") == server_id), None)







            if target_srv:







                cfg["active_server_id"] = server_id







                config_manager.save_config(cfg)







                s_name = target_srv.get("name", "MyServer")







                logger_manager.log_info(f"[CoreService] Server aktif beralih ke: {server_id} ({s_name})")
                # Beralih jaringan EasyTier otomatis ke Remote ID milik server target jika berbeda
                target_rid = (target_srv.get("remote_id") or target_srv.get("zerotier_network_id") or "").strip().lower()
                r_mode = (target_srv.get("remote_mode") or cfg.get("remote_mode", "auto")).lower()
                if easytier_manager and r_mode in ("auto", "easytier"):
                    try:
                        et_mgr = easytier_manager.get_easytier_manager()
                        cur_rid = (et_mgr.get_remote_id() or "").strip().lower()
                        if target_rid and target_rid != cur_rid and et_mgr.is_running():
                            logger_manager.log_info(f"[CoreService] Beralih jaringan EasyTier ke Remote ID target: {target_rid}")
                            et_params = easytier_manager.derive_easytier_params(target_rid)
                            et_mgr.start_easytier(
                                network_name=et_params["network_name"],
                                network_secret=et_params["network_secret"],
                                remote_id=target_rid,
                                ipv4=target_srv.get("easytier_client_ipv4") or "10.126.126.2/24",
                            )
                    except Exception as et_switch_err:
                        logger_manager.log_error(f"[CoreService] Gagal beralih EasyTier ke server target: {et_switch_err}")







                invalidate_active_route_cache()







                with _drives_cache_lock:



                    _cached_live_drives = []







                with _state_lock:



                    _cached_state.update({



                        "server_name": s_name,



                        "is_online": False,



                        "ping_str": "--",



                        "cpu_percent": 0,



                        "ram_percent": 0,



                        "disk_percent": 0,



                        "speed_down": 0,



                        "speed_up": 0,



                        "speed_down_bps": 0,



                        "speed_up_bps": 0,



                        "speed_down_str": "0 B/s",



                        "speed_up_str": "0 B/s",



                        "cpu_temperature": None,



                        "cpu_wattage": 0.0,



                        "ram_used_bytes": 0,



                        "ram_total_bytes": 0,



                        "storage_used_bytes": 0,



                        "storage_total_bytes": 0,



                        "storage_partitions": [],



                        "telemetry_loading": True,



                    })







                def _trigger_fresh_server_telemetry():



                    try:



                        u, lbl = get_active_resolved_route(cfg, force_refresh=True)



                        parsed = urllib.parse.urlparse(u)



                        ip_str = parsed.hostname or ""



                        route_lbl = "LAN Fisik" if "LAN" in lbl else ("ZeroTier P2P" if "ZeroTier" in lbl else "Domain / Internet")



                        with _state_lock:



                            _cached_state["ip"] = ip_str



                            _cached_state["server_url"] = u.rstrip("/")



                            _cached_state["route_name"] = route_lbl



                        client = get_cached_metrics_client(target_srv, u)



                        if client:



                            m = client.fetch_metrics()



                            if m and m.get("online"):



                                commit_fast_online(m, s_name, u, route_lbl, ip_str)

                            else:

                                with _state_lock:

                                    _cached_state["is_online"] = False

                                    _cached_state["telemetry_loading"] = False



                    except Exception as e:



                        logger_manager.log_debug(f"[CoreService] Trigger fresh server telemetry error: {e}")



                    finally:



                        with _state_lock:



                            _cached_state["telemetry_loading"] = False







                threading.Thread(target=_trigger_fresh_server_telemetry, daemon=True).start()



                threading.Thread(target=mount_active_server_smb, daemon=True).start()







            self._send_json(get_server_details_data(cfg))







            return















        if path == "/api/switch_route":







            route_id = (body.get("routeId") or body.get("arg") or "").strip()







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg)







            if srv and route_id:







                srv["active_connection"] = route_id







                config_manager.save_config(cfg)







                logger_manager.log_info(f"[CoreService] Rute koneksi dialihkan ke: {route_id}")







                invalidate_active_route_cache()







                with _drives_cache_lock:



                    _cached_live_drives = []







                # Segera paksakan resolusi rute aktif seketika (force_refresh=True)







                new_u, new_lbl = get_active_resolved_route(cfg, force_refresh=True)







                parsed = urllib.parse.urlparse(new_u)







                ip_str = parsed.hostname or ""







                route_lbl = "LAN Fisik" if "LAN" in new_lbl else ("ZeroTier P2P" if "ZeroTier" in new_lbl else "Domain / Internet")







                with _state_lock:







                    _cached_state["ip"] = ip_str







                    _cached_state["server_url"] = new_u.rstrip("/")







                    _cached_state["route_name"] = route_lbl







                    _cached_state["speed_down"] = 0







                    _cached_state["speed_up"] = 0







                    _cached_state["speed_down_bps"] = 0







                    _cached_state["speed_up_bps"] = 0







                    _cached_state["speed_down_str"] = "0 B/s"







                    _cached_state["speed_up_str"] = "0 B/s"







                    _cached_state["telemetry_loading"] = True







                def _trigger_fresh_route_telemetry():



                    try:



                        client = get_cached_metrics_client(srv, new_u)



                        if client:



                            m = client.fetch_metrics()



                            if m and m.get("online"):



                                commit_fast_online(m, srv.get("name", "MyServer"), new_u, route_lbl, ip_str)

                            else:

                                with _state_lock:

                                    _cached_state["is_online"] = False

                                    _cached_state["telemetry_loading"] = False



                    except Exception as e:



                        logger_manager.log_debug(f"[CoreService] Trigger fresh route telemetry error: {e}")



                    finally:



                        with _state_lock:



                            _cached_state["telemetry_loading"] = False







                threading.Thread(target=_trigger_fresh_route_telemetry, daemon=True).start()



                threading.Thread(target=mount_active_server_smb, daemon=True).start()







            self._send_json(get_server_details_data(cfg))







            return















        if path == "/api/switch_profile":







            p_name = (body.get("profileName") or body.get("profile_name") or body.get("arg") or "Admin").strip()







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg)







            if srv:







                srv["active_profile"] = p_name







                config_manager.save_config(cfg)







                logger_manager.log_info(f"[CoreService] Profil aktif beralih ke: {p_name}")







                with _drives_cache_lock:



                    _cached_live_drives = []







                with _state_lock:



                    _cached_state["telemetry_loading"] = False







                def _do_profile_rebind():



                    try:



                        rebind_storage_pipeline("profile_switch")



                    except Exception as e:



                        logger_manager.log_debug(f"[CoreService] Profile rebind error: {e}")



                    finally:



                        try:

                            fresh_d = _scan_live_drives_now()

                            with _drives_cache_lock:

                                _cached_live_drives = fresh_d

                        except Exception:

                            pass

                        with _state_lock:



                            _cached_state["telemetry_loading"] = False







                threading.Thread(target=_do_profile_rebind, daemon=True).start()







            self._send_json(get_server_details_data(cfg))







            return



















        # ======================================================================



        # REST ENDPOINTS JSON LANGSUNG (Pengganti Dialog PowerShell WinForms)



        # ======================================================================



        if path == "/api/save_route":



            srv_id = (body.get("serverId") or body.get("server_id") or "").strip()



            r_id = (body.get("id") or body.get("routeId") or body.get("route_id") or "").strip()



            r_name = (body.get("name") or body.get("route_name") or "").strip()



            r_url = (body.get("url") or body.get("route_url") or "").strip()



            if not r_name or not r_url or r_url in ("http://", "https://"):



                self._send_json({"success": False, "message": "Nama dan URL rute wajib diisi"})



                return



            cfg = config_manager.load_or_create_config()



            srv = next((s for s in cfg.get("servers", []) if s.get("id") == srv_id), None) if srv_id else config_manager.get_active_server(cfg)



            if not srv:



                self._send_json({"success": False, "message": "Server tidak ditemukan"})



                return



            formatted_u = config_manager.format_server_url(r_url)



            conns = srv.setdefault("connections", [])



            target = next((c for c in conns if c.get("id") == r_id), None) if r_id else None



            if target:



                target["name"] = r_name



                target["url"] = formatted_u



                c_id = r_id



            else:



                c_id = f"conn_{int(time.time() * 1000)}"



                conns.append({"id": c_id, "name": r_name, "url": formatted_u})



            config_manager.save_config(cfg)



            invalidate_active_route_cache()



            logger_manager.log_info(f"[CoreService] Rute '{r_name}' ({formatted_u}) berhasil disimpan via REST.")



            self._send_json({"success": True, "route": {"id": c_id, "name": r_name, "url": formatted_u}})



            return







        if path == "/api/remove_route":



            srv_id = (body.get("serverId") or body.get("server_id") or "").strip()



            r_id = (body.get("id") or body.get("routeId") or body.get("route_id") or "").strip()



            cfg = config_manager.load_or_create_config()



            srv = next((s for s in cfg.get("servers", []) if s.get("id") == srv_id), None) if srv_id else config_manager.get_active_server(cfg)



            if not srv:



                self._send_json({"success": False, "message": "Server tidak ditemukan"})



                return



            conns = srv.get("connections", [])



            if len(conns) <= 1:



                self._send_json({"success": False, "message": "Minimal harus ada 1 jalur akses tersimpan."})



                return



            srv["connections"] = [c for c in conns if c.get("id") != r_id]



            if srv.get("active_connection") == r_id:



                srv["active_connection"] = "auto"



            config_manager.save_config(cfg)



            invalidate_active_route_cache()



            logger_manager.log_info(f"[CoreService] Rute '{r_id}' berhasil dihapus via REST.")



            self._send_json({"success": True})



            return







        if path == "/api/save_profile":



            srv_id = (body.get("serverId") or body.get("server_id") or "").strip()



            p_name = (body.get("profileName") or body.get("name") or body.get("profile_name") or "").strip()



            old_name = (body.get("oldProfileName") or body.get("old_profile_name") or "").strip()



            u_name = (body.get("username") or "").strip()



            p_pass = (body.get("password") or "").strip()



            if not p_name:



                self._send_json({"success": False, "message": "Nama profil tidak boleh kosong"})



                return



            cfg = config_manager.load_or_create_config()



            srv = next((s for s in cfg.get("servers", []) if s.get("id") == srv_id), None) if srv_id else config_manager.get_active_server(cfg)



            if not srv:



                self._send_json({"success": False, "message": "Server tidak ditemukan"})



                return



            profiles = srv.setdefault("profiles", ["Admin"])



            creds = srv.setdefault("credentials", {})



            if old_name and old_name in profiles:



                idx = profiles.index(old_name)



                profiles[idx] = p_name



                if srv.get("active_profile") == old_name:



                    srv["active_profile"] = p_name



                if old_name in creds:



                    creds[p_name] = creds.pop(old_name)



            else:



                if p_name not in profiles:



                    profiles.append(p_name)



                srv["active_profile"] = p_name



            if u_name:



                existing_p = creds.get(p_name, {}).get("password", "") if old_name else ""



                creds[p_name] = {



                    "username": u_name,



                    "password": config_manager.encrypt_credential(p_pass) if p_pass else existing_p



                }



            config_manager.save_config(cfg)



            logger_manager.log_info(f"[CoreService] Profil '{p_name}' berhasil disimpan via REST.")



            self._send_json({"success": True, "profileName": p_name})



            return







        if path == "/api/remove_profile":



            srv_id = (body.get("serverId") or body.get("server_id") or "").strip()



            p_name = (body.get("profileName") or body.get("name") or body.get("profile_name") or "").strip()



            cfg = config_manager.load_or_create_config()



            srv = next((s for s in cfg.get("servers", []) if s.get("id") == srv_id), None) if srv_id else config_manager.get_active_server(cfg)



            if not srv:



                self._send_json({"success": False, "message": "Server tidak ditemukan"})



                return



            profiles = srv.get("profiles", ["Admin"])



            if len(profiles) <= 1:



                self._send_json({"success": False, "message": "Minimal harus ada 1 profil tersimpan."})



                return



            srv["profiles"] = [x for x in profiles if x != p_name]



            if srv.get("active_profile") == p_name:



                srv["active_profile"] = srv["profiles"][0]



            srv.get("credentials", {}).pop(p_name, None)



            config_manager.save_config(cfg)



            logger_manager.log_info(f"[CoreService] Profil '{p_name}' berhasil dihapus via REST.")



            self._send_json({"success": True})



            return







        if path == "/api/save_server":



            s_id = (body.get("id") or body.get("serverId") or body.get("server_id") or "").strip()



            s_name = (body.get("name") or body.get("server_name") or "").strip()



            raw_u = (body.get("url") or body.get("server_url") or "").strip()



            u_name = (body.get("username") or "").strip()



            p_pass = (body.get("password") or "").strip()



            zt_nwid = (body.get("zerotierNetworkId") or body.get("zerotier_network_id") or "").strip()



            zt_vip = (body.get("zerotierVirtualIp") or body.get("zerotier_virtual_ip") or "").strip()



            if not s_name:



                self._send_json({"success": False, "message": "Nama server wajib diisi"})



                return



            cfg = config_manager.load_or_create_config()



            servers = cfg.setdefault("servers", [])



            target = next((s for s in servers if s.get("id") == s_id), None) if s_id else None



            if target:



                target["name"] = s_name



                if raw_u and raw_u not in ("http://", "https://"):



                    target.setdefault("connections", [])



                    if target["connections"]:



                        target["connections"][0]["url"] = config_manager.format_server_url(raw_u)
                        if not target["connections"][0].get("name"):
                            target["connections"][0]["name"] = "Primary"



                    else:



                        target["connections"].append({"id": f"conn_{int(time.time())}", "name": "Primary", "url": config_manager.format_server_url(raw_u)})



                if zt_nwid:



                    target["zerotier_network_id"] = zt_nwid



                if zt_vip:



                    target["zerotier_virtual_ip"] = zt_vip
                if u_name or p_pass:
                    act_prof = target.get("active_profile") or "Admin"
                    profs = target.setdefault("profiles", [])
                    if act_prof not in profs:
                        profs.append(act_prof)
                    creds = target.setdefault("credentials", {})
                    if p_pass:
                        curr_u = u_name or (creds.get(act_prof, {}).get("username") if isinstance(creds.get(act_prof), dict) else "") or "admin"
                        config_manager.save_server_credentials(cfg, target.get("id"), act_prof, curr_u, p_pass)
                    elif u_name:
                        prof_entry = creds.setdefault(act_prof, {})
                        prof_entry["username"] = u_name



            else:



                formatted_u = config_manager.format_server_url(raw_u) if raw_u and raw_u not in ("http://", "https://") else "http://127.0.0.1"



                s_id = f"srv_{int(time.time() * 1000)}"



                act_prof = "Admin"



                creds = {}



                if u_name:



                    creds[act_prof] = {



                        "username": u_name,



                        "password": config_manager.encrypt_credential(p_pass) if p_pass else ""



                    }



                new_srv = {



                    "id": s_id,



                    "zerotier_network_id": zt_nwid,



                    "zerotier_virtual_ip": zt_vip,



                    "name": s_name,



                    "connections": [



                        {"id": f"conn_{int(time.time())}", "name": "Primary", "url": formatted_u}



                    ],



                    "active_connection": "auto",



                    "profiles": ["Admin"],



                    "active_profile": act_prof,



                    "credentials": creds,



                    "wake_on_lan": {"mac_address": "", "broadcast_ip": "255.255.255.255", "port": 9}



                }



                servers.append(new_srv)
                if body.get("setActive", True) is not False:
                    cfg["active_server_id"] = s_id



            config_manager.save_config(cfg)



            invalidate_active_route_cache()



            logger_manager.log_info(f"[CoreService] Server '{s_name}' berhasil disimpan via REST.")



            self._send_json({"success": True, "serverId": s_id})



            return







        if path == "/api/remove_server":



            s_id = (body.get("id") or body.get("serverId") or body.get("server_id") or "").strip()



            cfg = config_manager.load_or_create_config()



            servers = cfg.get("servers", [])



            if len(servers) <= 1:



                self._send_json({"success": False, "message": "Minimal harus ada 1 server tersimpan."})



                return



            cfg["servers"] = [s for s in servers if s.get("id") != s_id]



            if cfg.get("active_server_id") == s_id:



                cfg["active_server_id"] = cfg["servers"][0]["id"]



            config_manager.save_config(cfg)



            invalidate_active_route_cache()



            logger_manager.log_info(f"[CoreService] Server '{s_id}' berhasil dihapus via REST.")



            self._send_json({"success": True})



            return







        if path == "/api/join_zerotier_network":



            nwid = (body.get("networkId") or body.get("network_id") or body.get("nwid") or "").strip()



            if not nwid:



                self._send_json({"success": False, "message": "Network ID tidak boleh kosong"})



                return



            client = zerotier_manager.ZeroTierClient()



            ok, msg = client.join_network(nwid)



            logger_manager.log_info(f"[CoreService] ZeroTier join_network '{nwid}': ok={ok}, msg={msg}")



            self._send_json({"success": ok, "message": msg})
            return









        if path == "/api/set_remote_mode":
            mode = (body.get("mode") or "auto").strip().lower()
            if mode not in ("auto", "easytier", "zerotier"):
                mode = "auto"
            cfg = config_manager.load_or_create_config()
            srv = config_manager.get_active_server(cfg)
            prev_mode = (srv.get("remote_mode") if isinstance(srv, dict) else None) or cfg.get("remote_mode", "auto")
            if srv:
                srv["remote_mode"] = mode
            cfg["remote_mode"] = mode
            config_manager.save_config(cfg)
            if mode != prev_mode:
                _unmount_myserver_smb_drives(
                    reason="remote_mode_changed",
                    cfg=cfg,
                    server=srv,
                    include_easytier_subnet=True,
                )
                smb_mount_manager.invalidate_smb_host_cache()
                try:
                    with _cached_active_route["lock"]:
                        _cached_active_route["last_check"] = 0.0
                except Exception:
                    pass
                if bool(cfg.get("auto_mount_smb", True)):
                    threading.Thread(
                        target=rebind_storage_pipeline,
                        args=("remote_mode_changed",),
                        daemon=True,
                    ).start()
            self._send_json({"success": True, "remote_mode": mode})
            return

        if path == "/api/leave_zerotier_network":



            nwid = (body.get("networkId") or body.get("network_id") or body.get("nwid") or "").strip()



            if not nwid:



                self._send_json({"success": False, "message": "Network ID tidak boleh kosong"})



                return



            client = zerotier_manager.ZeroTierClient()



            ok, msg = client.leave_network(nwid)



            logger_manager.log_info(f"[CoreService] ZeroTier leave_network '{nwid}': ok={ok}, msg={msg}")



            self._send_json({"success": ok, "message": msg})



            return







                # Trigger Dialog Native (Powershell GUI) di background thread







        if path == "/api/add_server":







            threading.Thread(target=dialog_add_server, daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/edit_server":







            sid = (body.get("serverId") or body.get("arg") or "").strip()







            threading.Thread(target=dialog_edit_server, args=(sid,), daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/delete_server":







            sid = (body.get("serverId") or body.get("arg") or "").strip()







            threading.Thread(target=dialog_delete_server, args=(sid,), daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/add_route":







            threading.Thread(target=dialog_add_route, daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/edit_route":







            rid = (body.get("routeId") or body.get("arg") or "").strip()







            threading.Thread(target=dialog_edit_route, args=(rid,), daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/delete_route":







            rid = (body.get("routeId") or body.get("arg") or "").strip()







            threading.Thread(target=dialog_delete_route, args=(rid,), daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/add_profile":







            threading.Thread(target=dialog_add_profile, daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/edit_profile":







            p = (body.get("profileName") or body.get("arg") or "").strip()







            threading.Thread(target=dialog_edit_profile, args=(p,), daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/delete_profile":







            p = (body.get("profileName") or body.get("arg") or "").strip()







            threading.Thread(target=dialog_delete_profile, args=(p,), daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/config_credentials":







            threading.Thread(target=dialog_config_credentials, daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/join_zerotier":







            threading.Thread(target=dialog_join_zerotier, daemon=True).start()







            self._send_json({"success": True, "action": "dialog_opened"})







            return















        if path == "/api/quit_app":







            self._send_json({"success": True})







            def _delayed_exit():







                time.sleep(0.15)







                shutdown_background_daemons()







                os._exit(0)







            threading.Thread(target=_delayed_exit, daemon=True).start()







            return















        if path == "/api/debug_log":







            with open(os.path.join(os.path.dirname(__file__), "dom_metrics.json"), "w") as f:







                json.dump(body, f, indent=2)







            self._send_json({"success": True})







            return















        self._send_json({"status": "ok", "action": path})















    def log_message(self, format, *args):







        # Mencegah spam konsol standar







        pass























def shutdown_background_daemons():
    """Melepaskan drive SMB MyServer terlebih dahulu lalu menghentikan EasyTier dan Syncthing lokal."""
    global _shutdown_daemons_done
    with _shutdown_daemons_lock:
        if _shutdown_daemons_done:
            return
        _shutdown_daemons_done = True

    try:
        _unmount_myserver_smb_drives(
            reason="app_shutdown",
            include_all_servers=True,
            include_easytier_subnet=True,
        )
        smb_mount_manager.invalidate_smb_host_cache()
    except Exception as _smb_err:
        logger_manager.log_error(f"[CoreService] Gagal unmount SMB saat shutdown: {_smb_err}")

    try:
        if easytier_manager is not None:
            easytier_manager.get_easytier_manager().stop()
    except Exception as _et_err:
        logger_manager.log_error(f"[CoreService] Gagal menghentikan EasyTier: {_et_err}")

    try:
        if _local_st_daemon is not None:
            cfg = None
            st_port = "8384"
            try:
                cfg = config_manager.load_or_create_config()
                st_port = str((cfg or {}).get("local_syncthing", {}).get("port") or "8384").strip() or "8384"
            except Exception:
                pass
            st_key = get_local_syncthing_api_key(cfg)
            _local_st_daemon.stop(custom_port=st_port, api_key=st_key)
    except Exception as _st_err:
        logger_manager.log_error(f"[CoreService] Gagal menghentikan Syncthing lokal: {_st_err}")


def parent_watchdog(parent_pid):







    """Memantau parent process ID (Tauri Shell). Jika parent tertutup/crash, matikan core service seketika."""







    if not parent_pid or parent_pid <= 0:







        return







    try:







        kernel32 = ctypes.windll.kernel32







        SYNCHRONIZE = 0x00100000







        process_handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(parent_pid))







        if process_handle:







            logger_manager.log_info(f"[CoreService] Watchdog aktif untuk parent PID {parent_pid}")







            kernel32.WaitForSingleObject(process_handle, 0xFFFFFFFF)







            kernel32.CloseHandle(process_handle)







            logger_manager.log_info(f"[CoreService] Parent process {parent_pid} berhenti, mematikan Core Service...")







            shutdown_background_daemons()







            os._exit(0)







        else:







            logger_manager.log_debug(f"[CoreService] Tidak dapat membuka handle proses parent {parent_pid}, watchdog dilewati.")







    except Exception as e:







        logger_manager.log_info(f"[CoreService] Watchdog error: {e}")























class ReusableThreadingHTTPServer(ThreadingHTTPServer):







    allow_reuse_address = True







    daemon_threads = True
























_vm_daemon_state = {
    "last_keepalive": {},
    "last_heartbeat": {},
    "last_lease": {},
    "last_exec": {},
}

_INSTABOX_LEASE_TASK_ID = "myserver-always-on"
_INSTABOX_LEASE_TTL_SEC = 600
_INSTABOX_LEASE_RENEW_SEC = 120.0
_INSTABOX_EXEC_KEEPALIVE_SEC = 180.0


def _instabox_lease_request(api_key, machine_id, method="PUT", ttl_seconds=_INSTABOX_LEASE_TTL_SEC):
    if not api_key or not machine_id:
        return False
    req_url = f"https://api.instabox.sh/v1/machines/{machine_id}/activity-leases/{_INSTABOX_LEASE_TASK_ID}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
        "User-Agent": f"MyServer-Companion/{APP_VERSION_NUMBER}",
    }
    body = None
    if method == "PUT":
        headers["Content-Type"] = "application/json"
        body = json.dumps({"ttlSeconds": max(30, min(3600, int(ttl_seconds)))}).encode("utf-8")
    req = urllib.request.Request(req_url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except urllib.error.HTTPError as he:
        if method == "DELETE" and he.code == 404:
            return True
        return False
    except Exception:
        return False


def _instabox_exec_keepalive(api_key, machine_id):
    if not api_key or not machine_id:
        return False
    req_url = f"https://api.instabox.sh/v1/machines/{machine_id}/exec"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
        "User-Agent": f"MyServer-Companion/{APP_VERSION_NUMBER}",
    }
    req = urllib.request.Request(req_url, data=b'{"cmd": "true"}', headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception:
        return False


def _instabox_release_lease(api_key, machine_id, vm_id=None):
    if vm_id:
        _vm_daemon_state["last_lease"].pop(vm_id, None)
        _vm_daemon_state["last_exec"].pop(vm_id, None)
    return _instabox_lease_request(api_key, machine_id, method="DELETE")


def _instabox_maintain_keepalive(api_key, machine_id, vm_id, force=False):
    res = {"lease_sent": False, "exec_sent": False}
    if not api_key or not machine_id:
        return res
    now_ts = time.time()
    key = str(vm_id or machine_id)
    if force or (now_ts - _vm_daemon_state["last_lease"].get(key, 0.0) >= _INSTABOX_LEASE_RENEW_SEC):
        if _instabox_lease_request(api_key, machine_id, method="PUT", ttl_seconds=_INSTABOX_LEASE_TTL_SEC):
            _vm_daemon_state["last_lease"][key] = now_ts
            res["lease_sent"] = True
    if force or (now_ts - _vm_daemon_state["last_exec"].get(key, 0.0) >= _INSTABOX_EXEC_KEEPALIVE_SEC):
        if _instabox_exec_keepalive(api_key, machine_id):
            _vm_daemon_state["last_exec"][key] = now_ts
            res["exec_sent"] = True
    return res

def _find_server_vm(cfg, vm_id):
    """Mengembalikan VM ber-scope server dari config lokal (None jika bukan VM server)."""
    if not vm_id:
        return None
    for v in (cfg.get("vms", []) or []):
        if isinstance(v, dict) and v.get("id") == vm_id and (v.get("scope") == "server" or bool(v.get("serverId"))):
            return v
    return None


def _proxy_server_vm_action(cfg, vm_id, action, timeout=40.0, target_server_id=None):
    """Meneruskan aksi VM ke backend ZimaOS. Return (ok, data_or_error, http_status)."""
    backend_url = _get_active_server_backend_url(cfg, target_server_id=target_server_id)
    if not backend_url:
        return False, "Server ZimaOS tidak terhubung atau offline. VM server hanya bisa dikontrol lewat server.", 503
    url = f"{backend_url}/api/v1/vms/{vm_id}/{action}"
    ok, data, code = _backend_http_request(url, method="POST", json_body={}, timeout=timeout, retries=1)
    if not ok:
        return False, f"Backend ZimaOS ({code}): {data}", code
    if isinstance(data, dict) and str(data.get("status") or "").lower() == "error":
        err_msg = data.get("message") or data.get("detail") or f"Aksi '{action}' gagal pada backend ZimaOS."
        return False, err_msg, 502
    return True, data, code


def _instabox_api_action(api_key, machine_id, action):
    req_url = f"https://api.instabox.sh/v1/machines/{machine_id}/{action}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
        "User-Agent": f"MyServer-Companion/{APP_VERSION_NUMBER}",
    }
    req = urllib.request.Request(req_url, data=b"{}", headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")

def vm_power_scheduler_loop():
    """
    Daemon latar belakang 24/7 untuk menjaga VM InstaBox & Manual SSH:
    1. Always-On (keepAliveEnabled): Membangunkan VM tidur seketika, mengirim heartbeat anti-idle,
       dan mereset siklus 8 jam sebelum batas 450 menit (7.5 jam).
    2. Auto-On (autoOn): Menyalakan VM sesuai jadwal jam tertentu (clock) atau jeda setelah mati (after_off).
    3. Auto-Restart (autoRestart): Menjalankan siklus restart otomatis sesuai interval atau jam tertentu.
    """
    time.sleep(8.0)
    while True:
        try:
            cfg = config_manager.load_or_create_config()
            vms = cfg.get("vms", [])
            if isinstance(vms, list) and len(vms) > 0:
                now_ts = time.time()
                now_ms = int(now_ts * 1000)
                now_dt = datetime.datetime.now()
                curr_hhmm = f"{now_dt.hour:02d}:{now_dt.minute:02d}"
                curr_day_js = (now_dt.weekday() + 1) % 7  # 0=Sun, 1=Mon, ..., 6=Sat
                daemon_patches = {}

                for vm in vms:
                    if not isinstance(vm, dict):
                        continue
                    vm_id = str(vm.get("id") or "")
                    if not vm_id or vm_id in _deleted_vms_tombstone:
                        continue
                    # Isolasi: VM scope server dikontrol 100% oleh daemon backend ZimaOS
                    if vm.get("scope") == "server" or bool(vm.get("serverId")):
                        continue

                    # Terapkan mutasi terbaru bila ada agar daemon membaca status/toggle paling mutakhir
                    vm = _apply_recent_vm_mutation(dict(vm))
                    recent_mut = _recent_vm_mutations.get(vm_id)
                    in_power_grace = bool(
                        recent_mut
                        and now_ts < recent_mut.get("expires_at", 0)
                        and "status" in (recent_mut.get("patch") or {})
                    )

                    provider = str(vm.get("provider") or "instabox")
                    api_key = str(vm.get("apiKey") or "").strip()
                    mid = str(vm.get("machineId") or "").strip()
                    if not mid:
                        ssh_u = str(vm.get("sshUser") or "").strip()
                        if ssh_u.startswith("m_"):
                            mid = ssh_u

                    patch = {}

                    # Sinkronisasi status & Keep-Alive untuk InstaBox
                    last_ka = _vm_daemon_state["last_keepalive"].get(vm_id, 0.0)
                    if provider == "instabox" and api_key and (now_ts - last_ka >= 45.0):
                        _vm_daemon_state["last_keepalive"][vm_id] = now_ts
                        try:
                            headers = {
                                "Authorization": f"Bearer {api_key}",
                                "Accept": "application/json",
                                "User-Agent": f"MyServer-Companion/{APP_VERSION_NUMBER}",
                            }
                            req = urllib.request.Request("https://api.instabox.sh/v1/machines", headers=headers)
                            with urllib.request.urlopen(req, timeout=10) as resp:
                                m_data = json.loads(resp.read().decode("utf-8") or "{}")
                                machines = m_data.get("machines", [])
                                target = None
                                if mid:
                                    target = next((m for m in machines if m.get("id") == mid), None)
                                if not target and machines:
                                    target = machines[0]
                                if target:
                                    mid = target.get("id") or mid
                                    if mid and not vm.get("machineId"):
                                        vm["machineId"] = mid
                                        patch["machineId"] = mid
                                    state = str(target.get("state", "running")).lower()
                                    real_status = "running" if state in ("running", "active", "starting", "resuming") else "sleeping"
                                    if in_power_grace:
                                        real_status = vm.get("status", real_status)
                                    elif vm.get("status") != real_status:
                                        vm["status"] = real_status
                                        patch["status"] = real_status
                                        if real_status != "running" and not vm.get("sleepingSince"):
                                            vm["sleepingSince"] = now_ms
                                            patch["sleepingSince"] = now_ms
                                        elif real_status == "running":
                                            vm.pop("sleepingSince", None)
                                            patch["sleepingSince"] = None

                                    # Ambil detail mesin bila runStartedAt atau maxRunMinutes tidak disertakan di endpoint list
                                    raw_max_run = target.get("maxRunMinutes")
                                    run_started = target.get("runStartedAt")
                                    if (not run_started or raw_max_run is None) and mid:
                                        try:
                                            d_req = urllib.request.Request(f"https://api.instabox.sh/v1/machines/{mid}", headers=headers)
                                            with urllib.request.urlopen(d_req, timeout=6) as d_resp:
                                                d_json = json.loads(d_resp.read().decode("utf-8") or "{}")
                                                d_obj = d_json.get("machine", d_json) if isinstance(d_json, dict) else {}
                                                if isinstance(d_obj, dict):
                                                    if not run_started:
                                                        run_started = d_obj.get("runStartedAt")
                                                    if raw_max_run is None:
                                                        raw_max_run = d_obj.get("maxRunMinutes")
                                        except Exception:
                                            pass

                                    if raw_max_run is not None:
                                        try:
                                            raw_max_int = int(raw_max_run)
                                            max_run_mins = -1 if raw_max_int < 0 else max(1, raw_max_int)
                                        except Exception:
                                            max_run_mins = int(vm.get("maxRuntimeMinutes") if vm.get("maxRuntimeMinutes") is not None else 480)
                                    else:
                                        max_run_mins = int(vm.get("maxRuntimeMinutes") if vm.get("maxRuntimeMinutes") is not None else 480)
                                    if vm.get("maxRuntimeMinutes") != max_run_mins:
                                        vm["maxRuntimeMinutes"] = max_run_mins
                                        patch["maxRuntimeMinutes"] = max_run_mins

                                    runtime_mins = int(vm.get("runtimeMinutes") or 0)
                                    if real_status != "running":
                                        runtime_mins = 0
                                        if vm.get("runtimeMinutes") != 0:
                                            vm["runtimeMinutes"] = 0
                                            patch["runtimeMinutes"] = 0
                                    elif run_started:
                                        try:
                                            dt = datetime.datetime.fromisoformat(str(run_started).replace("Z", "+00:00"))
                                            last_reset_ms = int(vm.get("lastResetAt") or 0)
                                            if last_reset_ms > 0:
                                                reset_dt = datetime.datetime.fromtimestamp(last_reset_ms / 1000.0, tz=datetime.timezone.utc)
                                                if reset_dt > dt:
                                                    dt = reset_dt
                                            raw_mins = max(0, int((datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 60))
                                            runtime_mins = min(max_run_mins, raw_mins) if max_run_mins > 0 else raw_mins
                                            vm["runtimeMinutes"] = runtime_mins
                                            patch["runtimeMinutes"] = runtime_mins
                                        except Exception:
                                            pass

                                    # 1. Always-On (keepAliveEnabled)
                                    if vm.get("keepAliveEnabled") and not in_power_grace:
                                        if real_status != "running" and mid:
                                            logger_manager.log_info(f"[VMDaemon] Always-On aktif: membangunkan VM InstaBox {vm.get('name')} ({mid})")
                                            _instabox_api_action(api_key, mid, "resume")
                                            _instabox_maintain_keepalive(api_key, mid, vm_id, force=True)
                                            vm["status"] = "running"
                                            vm.pop("sleepingSince", None)
                                            patch["status"] = "running"
                                            patch["sleepingSince"] = None
                                        elif real_status == "running" and mid:
                                            if max_run_mins > 0 and runtime_mins >= max(30, max_run_mins - 5):
                                                logger_manager.log_info(f"[VMDaemon] Always-On runtime guard ({max_run_mins}m): mereset siklus runtime VM {vm.get('name')} ({mid})")
                                                _instabox_release_lease(api_key, mid, vm_id)
                                                _instabox_api_action(api_key, mid, "suspend")
                                                time.sleep(5.0)
                                                _instabox_api_action(api_key, mid, "resume")
                                                _instabox_maintain_keepalive(api_key, mid, vm_id, force=True)
                                                vm["runtimeMinutes"] = 0
                                                vm["lastResetAt"] = int(time.time() * 1000)
                                                patch["runtimeMinutes"] = 0
                                                patch["lastResetAt"] = vm["lastResetAt"]
                                            else:
                                                # Akuisisi Activity Lease + eksekusi perintah /exec berkala agar InstaBox tidak menganggap VM idle
                                                _instabox_maintain_keepalive(api_key, mid, vm_id)
                        except Exception as e_ka:
                            logger_manager.log_debug(f"[VMDaemon] InstaBox sync/keepalive warning ({vm.get('name')}): {e_ka}")

                    # 2. Auto-On Scheduler
                    auto_on = vm.get("autoOn")
                    if isinstance(auto_on, dict) and auto_on.get("enabled") and vm.get("status") != "running" and not in_power_grace:
                        should_wake = False
                        mode_on = auto_on.get("mode", "clock")
                        last_trig = int(auto_on.get("lastTriggeredAt") or 0)
                        if mode_on == "clock":
                            target_hhmm = str(auto_on.get("clockTime") or "07:00")
                            active_days = _normalize_day_indices(auto_on.get("days"))
                            if curr_hhmm == target_hhmm and curr_day_js in active_days and (now_ms - last_trig > 65000):
                                should_wake = True
                        elif mode_on == "after_off":
                            sleep_since = int(vm.get("sleepingSince") or 0)
                            if sleep_since <= 0:
                                vm["sleepingSince"] = now_ms
                                patch["sleepingSince"] = now_ms
                            else:
                                d_val = max(1, int(auto_on.get("delayValue") or 30))
                                d_unit = str(auto_on.get("delayUnit") or "minutes")
                                mult = 1000 if d_unit == "seconds" else (3600000 if d_unit == "hours" else 60000)
                                delay_ms = d_val * mult
                                if (now_ms - sleep_since >= delay_ms) and (now_ms - last_trig > max(15000, delay_ms // 2)):
                                    should_wake = True

                        if should_wake:
                            patch["autoOn_lastTriggeredAt"] = now_ms
                            vm["status"] = "running"
                            vm.pop("sleepingSince", None)
                            patch["status"] = "running"
                            patch["sleepingSince"] = None
                            if provider == "instabox" and api_key and mid:
                                try:
                                    logger_manager.log_info(f"[VMDaemon] Auto-On mengeksekusi nyala otomatis untuk {vm.get('name')} ({mid})")
                                    _instabox_api_action(api_key, mid, "resume")
                                except Exception as e_on:
                                    logger_manager.log_warn(f"[VMDaemon] Auto-On gagal membangunkan {vm.get('name')}: {e_on}")

                    # 3. Auto-Restart Scheduler
                    auto_res = vm.get("autoRestart")
                    if isinstance(auto_res, dict) and auto_res.get("enabled") and vm.get("status") == "running" and not in_power_grace:
                        should_restart = False
                        mode_res = auto_res.get("mode", "interval")
                        last_run = int(auto_res.get("lastRunTimestamp") or 0)
                        if mode_res == "interval":
                            if last_run <= 0:
                                patch["autoRestart_lastRunTimestamp"] = now_ms
                            else:
                                i_val = max(1, int(auto_res.get("intervalValue") or 6))
                                i_unit = str(auto_res.get("intervalUnit") or "hours")
                                mult = 1000 if i_unit == "seconds" else (60000 if i_unit == "minutes" else 3600000)
                                if now_ms - last_run >= i_val * mult:
                                    should_restart = True
                        elif mode_res == "clock":
                            t_hhmm = str(auto_res.get("clockTime") or "04:00")
                            if curr_hhmm == t_hhmm and (now_ms - last_run > 65000):
                                should_restart = True

                        if should_restart:
                            patch["autoRestart_lastRunTimestamp"] = now_ms
                            patch["autoRestart_lastExecuted"] = now_dt.strftime("%H:%M:%S")
                            if provider == "instabox" and api_key and mid:
                                try:
                                    logger_manager.log_info(f"[VMDaemon] Auto-Restart mengeksekusi siklus reset untuk {vm.get('name')} ({mid})")
                                    _instabox_api_action(api_key, mid, "suspend")
                                    time.sleep(5.0)
                                    _instabox_api_action(api_key, mid, "resume")
                                    patch["runtimeMinutes"] = 0
                                    patch["lastResetAt"] = int(time.time() * 1000)
                                except Exception as e_res:
                                    logger_manager.log_warn(f"[VMDaemon] Auto-Restart gagal pada {vm.get('name')}: {e_res}")

                    if patch and vm_id not in _deleted_vms_tombstone:
                        daemon_patches[vm_id] = patch

                if daemon_patches:
                    fresh_cfg = config_manager.load_or_create_config()
                    fresh_vms = [
                        v for v in (fresh_cfg.get("vms", []) or [])
                        if isinstance(v, dict) and v.get("id") not in _deleted_vms_tombstone
                    ]
                    any_applied = False
                    for fv in fresh_vms:
                        fid = str(fv.get("id") or "")
                        if fid in daemon_patches:
                            # Jangan timpa status bila user baru saja melakukan aksi selama loop berjalan
                            rm = _recent_vm_mutations.get(fid)
                            rm_active = bool(rm and time.time() < rm.get("expires_at", 0))
                            rm_patch = (rm.get("patch") or {}) if rm_active else {}
                            p = daemon_patches[fid]
                            for k, val in p.items():
                                if k == "sleepingSince":
                                    if "status" in rm_patch:
                                        continue
                                    if val is None:
                                        fv.pop("sleepingSince", None)
                                    else:
                                        fv["sleepingSince"] = val
                                    any_applied = True
                                elif k == "autoOn_lastTriggeredAt":
                                    if isinstance(fv.get("autoOn"), dict):
                                        fv["autoOn"]["lastTriggeredAt"] = val
                                        any_applied = True
                                elif k == "autoRestart_lastRunTimestamp":
                                    if isinstance(fv.get("autoRestart"), dict):
                                        fv["autoRestart"]["lastRunTimestamp"] = val
                                        any_applied = True
                                elif k == "autoRestart_lastExecuted":
                                    if isinstance(fv.get("autoRestart"), dict):
                                        fv["autoRestart"]["lastExecuted"] = val
                                        any_applied = True
                                else:
                                    if k in rm_patch:
                                        continue
                                    fv[k] = val
                                    any_applied = True
                    if any_applied:
                        fresh_cfg["vms"] = fresh_vms
                        config_manager.save_config(fresh_cfg)
        except Exception as e:
            logger_manager.log_debug(f"[VMDaemon] Loop warning: {e}")
        time.sleep(20.0)


def start_server(port=DEFAULT_PORT, parent_pid=0):







    # Buat direktori app data jika belum ada







    app_data = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "MyServer")







    os.makedirs(app_data, exist_ok=True)







    port_file = os.path.join(app_data, "core.port")















    server = None







    actual_port = port







    for attempt in range(6):







        try:







            server = ReusableThreadingHTTPServer(("127.0.0.1", actual_port), CoreApiHandler)







            break







        except OSError:







            time.sleep(0.5)















    if server is None:







        logger_manager.log_error(f"[CoreService] Gagal mengikat port {actual_port}")







        return















    # Simpan info port untuk Tauri







    with open(port_file, "w") as f:







        f.write(str(actual_port))















    # Tulis juga ke sandbox lokal untuk kemudahan debug







    local_port_file = os.path.join(os.path.dirname(__file__), "core.port")







    try:







        with open(local_port_file, "w") as f:







            f.write(str(actual_port))







    except Exception:







        pass















    logger_manager.log_info(f"[CoreService] Headless companion backend berjalan di http://127.0.0.1:{actual_port}")







    print(f"[CoreService] Running on http://127.0.0.1:{actual_port}")















    # Jalankan watchdog jika parent PID diberikan







    if parent_pid and parent_pid > 0:







        _gui_exe_cache["parent_pid"] = int(parent_pid)







        wt = threading.Thread(target=parent_watchdog, args=(parent_pid,), daemon=True)







        wt.start()















    # Self-healing Registry autorun (entri lama yang menunjuk ke backend headless diarahkan ke GUI)







    threading.Thread(target=ensure_autorun_registry_healthy, daemon=True).start()
    threading.Thread(target=cleanup_temp_update_artifacts, daemon=True).start()















    # Jalankan background poller telemetri dan SMB cache







    t = threading.Thread(target=update_metrics_loop, daemon=True)







    t.start()







    t_drives = threading.Thread(target=update_drives_cache_loop, daemon=True)







    t_drives.start()







    t_apps = threading.Thread(target=update_web_apps_cache_loop, daemon=True)







    t_apps.start()







    t_route = threading.Thread(target=update_route_resolver_loop, daemon=True)







    t_route.start()

    t_update = threading.Thread(target=auto_update_checker_loop, daemon=True)
    t_update.start()

    t_easytier = threading.Thread(target=auto_start_easytier_worker, daemon=True)
    t_easytier.start()







    t_syncthing = threading.Thread(target=syncthing_status_worker_loop, daemon=True)







    t_syncthing.start()

    t_vm_daemon = threading.Thread(target=vm_power_scheduler_loop, daemon=True)
    t_vm_daemon.start()

    if sys.platform == "win32":
        threading.Thread(target=windows_power_monitor_loop, daemon=True).start()
        threading.Thread(target=windows_network_change_monitor_loop, daemon=True).start()















    try:







        server.serve_forever()







    except KeyboardInterrupt:







        logger_manager.log_info("[CoreService] Shutting down.")







    finally:
        try:
            shutdown_background_daemons()
        except Exception:
            pass
        server.server_close()







        try:







            os.remove(port_file)







        except Exception:







            pass























def launch_gui_if_orphaned():







    """







    Orphan Boot Guard: bila backend dijalankan tanpa parent GUI (mis. entri autorun lama yang menunjuk







    ke backend), perbaiki Registry lalu luncurkan biner GUI (beserta System Tray) dan kembalikan True







    agar backend orphan ini keluar. Mengembalikan False bila GUI tidak ditemukan atau sudah berjalan.







    """







    try:







        gui = get_gui_executable_path()







        if not gui:







            return False







        ensure_autorun_registry_healthy()







        gui_name = os.path.basename(gui)







        creationflags = 0x08000000







        try:







            out = subprocess.run(







                ["tasklist.exe", "/FI", f"IMAGENAME eq {gui_name}", "/NH"],







                stdin=subprocess.DEVNULL,







                capture_output=True,







                text=True,







                errors="replace",







                creationflags=creationflags,







                timeout=8.0,







            ).stdout or ""







            if gui_name.lower() in out.lower():







                return False







        except Exception:







            pass







        subprocess.Popen(







            [gui],







            cwd=os.path.dirname(gui),







            stdin=subprocess.DEVNULL,







            stdout=subprocess.DEVNULL,







            stderr=subprocess.DEVNULL,







            creationflags=0x00000008 | 0x00000200,







            close_fds=True,







        )







        logger_manager.log_info(f"[CoreService] Backend dijalankan tanpa GUI (boot/autorun lama), meluncurkan GUI: {gui}")







        return True







    except Exception as e:







        logger_manager.log_error(f"[CoreService] Orphan Boot Guard gagal: {e}")







        return False























if __name__ == "__main__":







    parser = argparse.ArgumentParser(description="MyServer Core Headless Backend")







    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port untuk loopback HTTP server")







    parser.add_argument("--parent-pid", type=int, default=0, help="PID dari parent process (Tauri)")







    parser.add_argument("--window", type=str, default="", help="Buka jendela aplikasi PyWebView untuk URL ini")
    parser.add_argument("--server-id", type=str, default="", help="Target Server ID untuk profil dan kredensial")
    parser.add_argument("--vm-id", type=str, default="", help="Target VM ID untuk isolasi sesi WebView2")







    parser.add_argument("--title", type=str, default="", help="Judul jendela aplikasi")







    parser.add_argument("--standalone", action="store_true", help="Jalankan backend saja tanpa meluncurkan GUI (debug)")







    args, _ = parser.parse_known_args()















    if args.window:







        run_app_window(args.window, args.title, target_server_id=getattr(args, 'server_id', None) or None, target_vm_id=getattr(args, 'vm_id', None) or None)







        sys.exit(0)















    if getattr(sys, "frozen", False) and not args.parent_pid and not args.standalone:







        if launch_gui_if_orphaned():







            sys.exit(0)















    start_server(args.port, args.parent_pid)







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
        return (srv.get("easytier_virtual_ip") or "10.126.126.1").strip()
    return (srv.get("zerotier_virtual_ip") or "").strip()


"""







MyServer Core Service v3.10.0 Beta (Headless Companion Backend)







Menggantikan pywebview WinForms engine dengan headless companion daemon.







Menyediakan REST API lokal (127.0.0.1) untuk dikonsumsi oleh antarmuka Tauri v2.







"""















import argparse







import ipaddress







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















APP_VERSION_NUMBER = "4.2.5"

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











def run_app_window(url, title=None, width=1150, height=750, target_server_id=None):



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























def spawn_app_window(target_url, title=None, width=1150, height=750, server_id=None):







    """







    Meluncurkan jendela aplikasi sebagai subprocess terpisah (out-of-process)







    atau membuka di peramban default sesuai preferensi app_entry_open (Zima Client v2.3.5).







    """







    clean_u = (target_url or "").strip()







    if not clean_u:







        return False, "URL kosong"















    cfg = config_manager.load_or_create_config()







    open_mode = cfg.get("app_entry_open", "window")















    if open_mode == "browser":







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







    """Membuang cache rute aktif & metrics client agar server/rute baru langsung diresolusi ulang."""







    global _active_metrics_client, _active_metrics_client_key







    with _cached_active_route["lock"]:







        _cached_active_route["url"] = ""







        _cached_active_route["label"] = ""







        _cached_active_route["last_check"] = 0.0







        _cached_active_route["server_id"] = None







        _cached_active_route["active_conn"] = None







    _active_metrics_client = None







    _active_metrics_client_key = None























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







            if srv and srv.get("active_connection", "auto") == "auto":







                url, lbl = config_manager.resolve_target_connection(cfg, check_network=True, target_server=srv)







                with _cached_active_route["lock"]:







                    _cached_active_route["url"] = url







                    _cached_active_route["label"] = lbl







                    _cached_active_route["last_check"] = time.time()







                    _cached_active_route["server_id"] = srv.get("id")







                    _cached_active_route["active_conn"] = srv.get("active_connection", "auto")















                parsed = urllib.parse.urlparse(url)







                ip_str = parsed.hostname or ""







                with _state_lock:







                    if _cached_state.get("ip") != ip_str or _cached_state.get("server_url") != url.rstrip("/"):







                        _cached_state["ip"] = ip_str







                        _cached_state["server_url"] = url.rstrip("/")







                        _cached_state["route_name"] = "LAN Fisik" if "LAN" in lbl else ("ZeroTier P2P" if "ZeroTier" in lbl else "Domain / Internet")







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







def _scan_live_drives_now():







    """Memindai seluruh drive huruf Windows secara komprehensif."""







    drives = []



    seen_shares = set()







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



                        for c in other_srv.get("connections", []):



                            if isinstance(c, dict) and c.get("url"):



                                h = c["url"].replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip().lower()



                                if h:



                                    other_server_identities.add(h)



        except Exception as e:



            logger_manager.log_debug(f"[LiveDrives] Gagal mengumpulkan identitas server: {e}")







        for i in range(25, 2, -1):







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



                    if share_key in seen_shares:



                        continue







                    tot = 0



                    fr = 0



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







                    if tot == 0:



                        free_bytes = ctypes.c_ulonglong(0)



                        total_bytes = ctypes.c_ulonglong(0)



                        total_free = ctypes.c_ulonglong(0)



                        pipeline_busy = _smb_pipeline_lock.locked()



                        now_ts = time.time()



                        with _drives_cache_lock:



                            c_space = _cached_live_drive_space.get(d)



                        if c_space and len(c_space) == 3 and (now_ts - c_space[2]) < 30.0:



                            tot, fr = c_space[0], c_space[1]



                        elif srv_online and not pipeline_busy:



                            with _drives_cache_lock:



                                drv_busy = (d in _inflight_live_drives)



                                if not drv_busy:



                                    _inflight_live_drives.add(d)



                            if not drv_busy:



                                def _query_space(drv_key=d, drv_path=d + "\\", fb=free_bytes, tb=total_bytes, tf=total_free):



                                    try:



                                        ctypes.windll.kernel32.GetDiskFreeSpaceExW(



                                            drv_path,



                                            ctypes.byref(fb),



                                            ctypes.byref(tb),



                                            ctypes.byref(tf)



                                        )



                                        if tb.value > 0:



                                            with _drives_cache_lock:



                                                _cached_live_drive_space[drv_key] = (tb.value, fb.value, time.time())



                                    except Exception:



                                        pass



                                    finally:



                                        with _drives_cache_lock:



                                            _inflight_live_drives.discard(drv_key)



                                t_sp = threading.Thread(target=_query_space, daemon=True)



                                t_sp.start()



                                t_sp.join(timeout=0.5)



                            tot = total_bytes.value



                            fr = free_bytes.value



                            if tot == 0:



                                with _drives_cache_lock:



                                    c_fb = _cached_live_drive_space.get(d, (0, 0, 0))



                                    tot, fr = c_fb[0], c_fb[1]







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











def rebind_storage_pipeline(reason="manual", force_refresh=True):







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







        else:







            unmounted_count = smb_mount_manager.unmount_all_smb_shares()







            logger_manager.log_info(f"[SMB Pipeline] Berhasil melepaskan {unmounted_count} drive lama.")















        cfg = config_manager.load_or_create_config()







        srv = config_manager.get_active_server(cfg)







        if not srv:







            return []















        if not soft_mode:







            all_hosts = set()







            for c in srv.get("connections", []):







                if isinstance(c, dict) and c.get("url"):







                    h = c["url"].replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()







                    if h:







                        all_hosts.add(h)







            if srv.get("zerotier_virtual_ip"):







                all_hosts.add(srv["zerotier_virtual_ip"].strip())















            smb_mount_manager.purge_smb_sessions(all_hosts)







            time.sleep(0.5)















        act_p = srv.get("active_profile", "Admin")







        creds = config_manager.get_server_credentials(srv, act_p)







        u_val = creds.get("username", "")







        p_val = creds.get("password", "")







        active_u, _ = get_active_resolved_route(cfg)







        conns = srv.get("connections", [])















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















        res = smb_mount_manager.mount_all_smb_shares(







            host=host,







            username=u_val,







            password=p_val,







            server_connections=conns,







            is_domain_route=is_domain,







            zerotier_ip=zt_ip,







            auth_token=auth_token,







            base_url=active_u.rstrip("/"),







            force_refresh=True,







        )







        logger_manager.log_info(f"[SMB Pipeline] Hasil pemasangan ulang ({reason}): {res}")







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







                "active": (s.get("id") == active_srv_id)







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







        "servers": servers_list,







        "zeroTier": zt_info,
        "easyTier": (lambda s: (s.update({"remote_id": s.get("remote_id") or srv.get("remote_id") or srv.get("zerotier_network_id") or cfg.get("easytier", {}).get("remote_id")}), s)[1])(easytier_manager.get_easytier_manager().get_status_overview()) if easytier_manager else {"running": False},
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







    if _active_metrics_client is not None and _active_metrics_client_key == client_key:



        if active_u:



            _active_metrics_client.base_url = active_u.rstrip("/")



            _active_metrics_client.host = srv_host



        if getattr(_active_metrics_client, "zerotier_ip", "") != srv_zt_ip:



            _active_metrics_client.zerotier_ip = srv_zt_ip



            _active_metrics_client._cached_server_identities = None



        _active_metrics_client.allow_multi_route_failover = is_auto



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







    last_srv_id = None



    last_conn_id = None







    while True:







        try:







            cfg = config_manager.load_or_create_config()







            s = config_manager.get_active_server(cfg)







            s_name = s.get("name", "MyServer") if s else "MyServer"







            cur_srv_id = s.get("id") if s else None



            cur_conn_id = s.get("active_connection", "auto") if s else "auto"







            srv_changed = False



            route_changed = False







            if cur_srv_id != last_srv_id or cur_conn_id != last_conn_id:







                offline_streak = 0







                srv_changed = (cur_srv_id != last_srv_id)



                route_changed = (cur_conn_id != last_conn_id)







                last_srv_id = cur_srv_id



                last_conn_id = cur_conn_id







            active_u, ind_text = get_active_resolved_route(cfg)







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







                is_on = True







            else:







                offline_streak += 1







                # Toleransi kegagalan berturut-turut: 1 timeout sesaat tidak menjatuhkan status Online



                # Jika server atau rute baru saja dialihkan secara manual, jangan pertahankan status online rute lama



                held_online = was_online and not srv_changed and not route_changed and offline_streak < OFFLINE_FAIL_THRESHOLD







                is_on = held_online







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







    kill_gui_cmd = f"taskkill /PID {gui_pid} /F >nul 2>&1" if gui_pid > 0 else ""

    bat_content = f"""@echo off
chcp 65001 >nul
ping 127.0.0.1 -n 2 >nul
{kill_gui_cmd}
taskkill /F /IM MyServer-Beta.exe /IM MyServer.exe /IM syncthing.exe >nul 2>&1
taskkill /PID {current_pid} /F >nul 2>&1
taskkill /F /IM myserver-core.exe >nul 2>&1
ping 127.0.0.1 -n 3 >nul
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
                for asset in rel_data.get("assets", []):
                    aname = asset.get("name", "").lower()
                    if aname.endswith("-setup.exe") or aname.endswith(".exe") or aname.endswith(".zip"):
                        download_url = asset.get("browser_download_url", download_url)
                        break
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







        elif path in ("/api/easytier/status", "/api/easytier_status"):
            if easytier_manager:
                mgr = easytier_manager.get_easytier_manager()
                self._send_json(mgr.get_status_overview())
            else:
                self._send_json({"running": False, "error": "easytier_manager not available"})
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



                        smb_mount_manager.unmount_all_smb_shares()



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



                        smb_mount_manager.unmount_all_smb_shares()



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







                smb_mount_manager.unmount_all_smb_shares()







            refresh_drives_cache_immediately()







            time.sleep(0.3)







            self._send_json(get_live_drives_list())







            return















        if path == "/api/open_drive":







            letter = (body.get("letter") or body.get("arg") or "").strip()







            if letter:







                clean_letter = letter.strip(":").upper() + ":"







                smb_mount_manager.open_drive_in_explorer(clean_letter)







                self._send_json({"success": True, "drive": clean_letter})







            else:







                self._send_json({"success": False, "message": "Drive letter kosong"})







            return















        if path == "/api/open_primary_disk":







            sh_name, d_letter = get_primary_mounted_share()







            if d_letter:







                smb_mount_manager.open_drive_in_explorer(d_letter)







                self._send_json({"success": True, "drive": d_letter})







            else:







                # Coba pasang terlebih dahulu







                mount_active_server_smb()







                time.sleep(0.5)







                sh_name, d_letter = get_primary_mounted_share()







                if d_letter:







                    smb_mount_manager.open_drive_in_explorer(d_letter)







                    self._send_json({"success": True, "drive": d_letter})







                else:







                    self._send_json({"success": False, "message": "Tidak ada partisi SMB terpasang"})







            return















        if path == "/api/open_unc":







            cfg = config_manager.load_or_create_config()







            srv = config_manager.get_active_server(cfg)







            active_u, _ = get_active_resolved_route(cfg)







            conns = srv.get("connections", []) if srv else []







            host, is_domain, zt_ip = _resolve_smb_route_params(srv, active_u)







            smb_mount_manager.open_unc_root_in_explorer(







                host,







                server_connections=conns,







                is_domain_route=is_domain,







                zerotier_ip=zt_ip,







            )







            self._send_json({"success": True, "host": host})







            return



        if path == "/api/open_file_explorer":



            sh_name, d_letter = get_primary_mounted_share()



            if not d_letter:



                mount_active_server_smb()



                time.sleep(0.5)



                sh_name, d_letter = get_primary_mounted_share()



            if d_letter:



                smb_mount_manager.open_drive_in_explorer(d_letter)



                self._send_json({"success": True, "drive": d_letter})



            else:



                cfg = config_manager.load_or_create_config()



                srv = config_manager.get_active_server(cfg)



                active_u, _ = get_active_resolved_route(cfg)



                conns = srv.get("connections", []) if srv else []



                host, is_domain, zt_ip = _resolve_smb_route_params(srv, active_u)



                smb_mount_manager.open_unc_root_in_explorer(



                    host,



                    server_connections=conns,



                    is_domain_route=is_domain,



                    zerotier_ip=zt_ip,



                )



                self._send_json({"success": True, "unc": host})



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



                    smb_mount_manager.open_drive_in_explorer(d_letter)



                    self._send_json({"success": True, "target": "explorer", "drive": d_letter})



                else:



                    srv = config_manager.get_active_server(cfg)



                    active_u, _ = get_active_resolved_route(cfg)



                    conns = srv.get("connections", []) if srv else []



                    host, is_domain, zt_ip = _resolve_smb_route_params(srv, active_u)



                    smb_mount_manager.open_unc_root_in_explorer(



                        host,



                        server_connections=conns,



                        is_domain_route=is_domain,



                        zerotier_ip=zt_ip,



                    )



                    self._send_json({"success": True, "target": "explorer", "unc": host})



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



                "dpapiActive": bool(config_manager.is_dpapi_supported()),







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
                req = urllib.request.Request(download_url, headers={"User-Agent": "MyServer-Updater/1.0"})
                with urllib.request.urlopen(req, timeout=180) as resp, open(temp_file, "wb") as out_f:
                    shutil.copyfileobj(resp, out_f)

                logger_manager.log_info(f"[Updater] Unduhan selesai ({os.path.getsize(temp_file):,} bytes)")

                if is_zip:
                    res = apply_zip_update(temp_file)
                    self._send_json(res)
                    return
                else:
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

        # --- Endpoints EasyTier & Remote Mesh Network ---
        if path in ("/api/easytier/status", "/api/easytier_status"):
            if easytier_manager:
                mgr = easytier_manager.get_easytier_manager()
                self._send_json(mgr.get_status_overview())
            else:
                self._send_json({"running": False, "error": "easytier_manager not available"})
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
                mgr = easytier_manager.get_easytier_manager()
                ok, msg = mgr.stop_easytier()
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



                    else:



                        target["connections"].append({"id": f"conn_{int(time.time())}", "name": "Primary", "url": config_manager.format_server_url(raw_u)})



                if zt_nwid:



                    target["zerotier_network_id"] = zt_nwid



                if zt_vip:



                    target["zerotier_virtual_ip"] = zt_vip



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

        if path == "/api/easytier_status":
            if easytier_manager:
                status = easytier_manager.easytier_instance.get_full_status()
                self._send_json({"success": True, "data": status})
            else:
                self._send_json({"success": False, "error": "EasyTier module not loaded", "data": {"running": False}})
            return

        if path == "/api/easytier_start":
            rid = (body.get("remote_id") or body.get("remoteId") or "").strip().lower()
            net_name = (body.get("network_name") or body.get("networkName") or "").strip()
            net_secret = (body.get("network_secret") or body.get("networkSecret") or "").strip()
            peers = body.get("peers") or []
            if not rid and not net_name:
                self._send_json({"success": False, "error": "Remote ID atau Network Name wajib diisi."})
                return
            if easytier_manager:
                mgr = easytier_manager.get_easytier_manager()
                ok, msg = mgr.start(
                    remote_id=rid or None,
                    network_name=net_name or None,
                    network_secret=net_secret or None,
                    peers=peers
                )
                if ok:
                    try:
                        cfg = config_manager.load_or_create_config()
                        et_cfg = cfg.setdefault("easytier", {})
                        et_cfg["enabled"] = True
                        if rid:
                            et_cfg["remote_id"] = rid
                            params = easytier_manager.derive_easytier_params(rid)
                            et_cfg["network_name"] = params["network_name"]
                            et_cfg["network_secret"] = params["network_secret"]
                            srv = config_manager.get_active_server(cfg)
                            if srv:
                                srv["remote_id"] = rid
                        config_manager.save_config(cfg)
                    except Exception as ce:
                        logger_manager.log_debug(f"[EasyTierStart] Gagal simpan config: {ce}")
                self._send_json({"success": ok, "message": msg, "status": mgr.get_status_overview()})
            else:
                self._send_json({"success": False, "error": "EasyTier module not available."})
            return

        if path == "/api/easytier_stop":
            if easytier_manager:
                ok, msg = easytier_manager.easytier_instance.stop()
                self._send_json({"success": ok, "message": msg})
            else:
                self._send_json({"success": False, "error": "EasyTier module not available."})
            return







        if path == "/api/set_remote_mode":
            mode = (body.get("mode") or "auto").strip().lower()
            if mode not in ("auto", "easytier", "zerotier"):
                mode = "auto"
            cfg = config_manager.load_or_create_config()
            srv = config_manager.get_active_server(cfg)
            if srv:
                srv["remote_mode"] = mode
            cfg["remote_mode"] = mode
            config_manager.save_config(cfg)
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







                time.sleep(0.5)







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







            os._exit(0)







        else:







            logger_manager.log_debug(f"[CoreService] Tidak dapat membuka handle proses parent {parent_pid}, watchdog dilewati.")







    except Exception as e:







        logger_manager.log_info(f"[CoreService] Watchdog error: {e}")























class ReusableThreadingHTTPServer(ThreadingHTTPServer):







    allow_reuse_address = True







    daemon_threads = True























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















    try:







        server.serve_forever()







    except KeyboardInterrupt:







        logger_manager.log_info("[CoreService] Shutting down.")







    finally:







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







    parser.add_argument("--title", type=str, default="", help="Judul jendela aplikasi")







    parser.add_argument("--standalone", action="store_true", help="Jalankan backend saja tanpa meluncurkan GUI (debug)")







    args, _ = parser.parse_known_args()















    if args.window:







        run_app_window(args.window, args.title, target_server_id=getattr(args, 'server_id', None) or None)







        sys.exit(0)















    if getattr(sys, "frozen", False) and not args.parent_pid and not args.standalone:







        if launch_gui_if_orphaned():







            sys.exit(0)















    start_server(args.port, args.parent_pid)







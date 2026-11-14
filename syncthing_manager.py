"""



Syncthing Manager for MyServer Desktop (v3.6.0 Beta)



Modul pengontrol REST API Syncthing, pemantau kecepatan transfer, & daemon lokal.



"""







import json



import os



import subprocess



import sys



import time



import urllib.error



import urllib.parse



import urllib.request







try:



    import logger_manager



except Exception:



    logger_manager = None











_CLIENT_SPEED_STATE = {}











def get_speed_state(host, port):



    """Menyimpan status metrik kecepatan secara persisten lintas instance SyncthingClient."""



    key = f"{host}:{port}"



    if key not in _CLIENT_SPEED_STATE:



        _CLIENT_SPEED_STATE[key] = {



            "last_in": None,



            "last_out": None,



            "last_time": None,



            "in_rate": 0.0,



            "out_rate": 0.0,



        }



    return _CLIENT_SPEED_STATE[key]











def format_transfer_speed(bytes_per_sec):



    if bytes_per_sec < 1024:



        return f"{bytes_per_sec:.0f} B/s"



    elif bytes_per_sec < 1024 * 1024:



        return f"{bytes_per_sec / 1024:.1f} KB/s"



    elif bytes_per_sec < 1024 * 1024 * 1024:



        return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"



    else:



        return f"{bytes_per_sec / (1024 * 1024 * 1024):.1f} GB/s"











def normalize_device_id(device_id):



    """Membersihkan dan menstandarkan format Device ID Syncthing."""



    if not device_id or not isinstance(device_id, str):



        return ""



    return device_id.strip()











def validate_device_id(device_id):



    """Validasi format string Device ID Syncthing (panjang alfanumerik 50-65)."""



    if not device_id or not isinstance(device_id, str):



        return False



    clean = device_id.strip().replace("-", "").replace(" ", "").upper()



    return bool(50 <= len(clean) <= 65 and clean.isalnum())











class SyncthingClient:



    """REST API Client untuk Syncthing lokal maupun server remote."""







    def __init__(self, host="127.0.0.1", port="8384", api_key="", use_https=False):



        self.host = str(host).strip()



        self.port = str(port).strip()



        self.api_key = str(api_key).strip()



        self.use_https = use_https







        state = get_speed_state(self.host, self.port)



        self._last_in_bytes = state["last_in"]



        self._last_out_bytes = state["last_out"]



        self._last_speed_time = state["last_time"]



        self._cached_in_rate = state["in_rate"]



        self._cached_out_rate = state["out_rate"]







    @property



    def base_url(self):



        protocol = "https" if self.use_https else "http"



        clean_host = self.host.replace("http://", "").replace("https://", "").rstrip("/")



        if ":" in clean_host:



            return f"{protocol}://{clean_host}"



        return f"{protocol}://{clean_host}:{self.port}"







    def _send_request(self, endpoint, method="GET", payload=None, timeout=3.0):



        url = f"{self.base_url}{endpoint}"



        data = None



        if payload is not None:



            data = json.dumps(payload).encode("utf-8")







        headers = {



            "User-Agent": "MyServer-Desktop-Syncthing/3.6.9",



            "Accept": "application/json",



        }



        if payload is not None:



            headers["Content-Type"] = "application/json"



        if self.api_key:



            headers["X-API-Key"] = self.api_key







        req = urllib.request.Request(url, data=data, headers=headers, method=method)



        try:



            with urllib.request.urlopen(req, timeout=timeout) as resp:



                status_code = resp.status



                body = resp.read().decode("utf-8", errors="replace")



                if body.strip():



                    try:



                        return status_code, json.loads(body)



                    except json.JSONDecodeError:



                        return status_code, body



                return status_code, None



        except urllib.error.HTTPError as he:

            try:

                err_body = he.read().decode('utf-8', errors='replace')

                return he.code, err_body

            except Exception:

                return he.code, None

        except Exception as exc:

            if logger_manager and not str(endpoint).endswith("/health"):

                logger_manager.log_warning(f"[SyncthingClient._send_request] {method} {url} error: {exc}")

            return None, None







    def is_online(self):



        code, _ = self._send_request("/rest/noauth/health", timeout=1.5)



        if code == 200:



            return True



        code, _ = self._send_request("/rest/system/ping", timeout=1.5)



        return code == 200







    def get_system_status(self):



        code, res = self._send_request("/rest/system/status", timeout=2.0)



        if code == 200 and isinstance(res, dict):



            return res



        return None







    def get_my_id(self):



        st = self.get_system_status()



        if st and isinstance(st, dict):



            return st.get("myID", "")



        return ""







    def get_connections(self):



        code, res = self._send_request("/rest/system/connections", timeout=2.0)



        if code == 200 and isinstance(res, dict):



            return res



        return {}







    def get_devices(self):



        code, res = self._send_request("/rest/config/devices", timeout=2.5)



        if code == 200 and isinstance(res, list):



            try:



                conns = self.get_connections().get("connections", {})



                my_id = self.get_my_id()



                for d in res:



                    d_id = d.get("deviceID")



                    c_info = conns.get(d_id, {}) if isinstance(conns, dict) else {}



                    d["is_self"] = bool(d_id and d_id == my_id)



                    d["connected"] = bool(c_info.get("connected", False))



                    d["address"] = str(c_info.get("address", ""))



                    d["client_version"] = str(c_info.get("clientVersion", ""))



            except Exception:



                pass



            return res



        return []







    def add_device(self, device_id, name="", addresses=None, auto_accept=True, introducer=False):



        clean_id = normalize_device_id(device_id)



        if not clean_id:



            return False







        devices = self.get_devices()



        for d in devices:



            if d.get("deviceID") == clean_id:



                return True







        if addresses is None:



            addresses = ["dynamic"]



        elif isinstance(addresses, str):



            addresses = [a.strip() for a in addresses.split(",") if a.strip()]



            if not addresses:



                addresses = ["dynamic"]







        payload = {



            "deviceID": clean_id,



            "name": name or (clean_id[:8] + "..."),



            "addresses": addresses,



            "autoAcceptFolders": bool(auto_accept),



            "introducer": bool(introducer),



        }



        code, _ = self._send_request("/rest/config/devices", method="POST", payload=payload, timeout=15.0)

        if code in (200, 201):

            return True

        try:

            time.sleep(0.8)

            for d in self.get_devices():

                if d.get("deviceID") == device_id or d.get("id") == device_id:

                    return True

        except Exception:

            pass

        return False







    def remove_device(self, device_id):



        """Menghapus perangkat dari konfigurasi Syncthing."""



        clean_id = normalize_device_id(device_id)



        if not clean_id:



            return False



        endpoint = f"/rest/config/devices/{urllib.parse.quote(clean_id)}"



        code, _ = self._send_request(endpoint, method="DELETE", timeout=3.5)



        return code in (200, 204)







    def get_pending_devices(self):



        """Mengambil daftar perangkat yang meminta koneksi ke Syncthing."""



        code, res = self._send_request("/rest/cluster/pending/devices", timeout=2.5)



        if code == 200 and isinstance(res, dict):



            return res



        return {}







    def dismiss_pending_device(self, device_id):



        """Menolak/menghapus permintaan perangkat dari daftar pending."""



        clean_id = normalize_device_id(device_id)



        if not clean_id:



            return False



        endpoint = f"/rest/cluster/pending/devices?device={urllib.parse.quote(clean_id)}"



        code, _ = self._send_request(endpoint, method="DELETE", timeout=3.5)



        return code in (200, 204)







    def accept_pending_device(self, device_id, name="", addresses=None, auto_accept=True):



        """Menerima permintaan perangkat pending dan menyimpannya ke konfigurasi."""



        ok = self.add_device(device_id, name=name, addresses=addresses, auto_accept=auto_accept)



        if ok:



            self.dismiss_pending_device(device_id)



        return ok







    def get_folders(self):



        code, res = self._send_request("/rest/config/folders", timeout=2.5)



        if code == 200 and isinstance(res, list):



            return res



        return []







    def get_folder_status(self, folder_id):



        endpoint = f"/rest/db/status?folder={urllib.parse.quote(folder_id)}"



        code, res = self._send_request(endpoint, timeout=2.0)



        if code == 200 and isinstance(res, dict):



            return res



        return None







    def add_folder(self, folder_id, label, path, folder_type="sendonly", remote_device_ids=None):
        # 1. Pre-check: jika folder sudah terdaftar di instance Syncthing ini, langsung anggap sukses
        try:
            c_pre, b_pre = self._send_request(f"/rest/config/folders/{urllib.parse.quote(folder_id)}", method="GET", timeout=4.0)
            if c_pre == 200 and isinstance(b_pre, dict) and b_pre.get("id") == folder_id:
                return True
        except Exception:
            pass

        my_id = self.get_my_id()
        devices = [{"deviceID": r_id} for r_id in (remote_device_ids or []) if r_id and r_id != my_id]
        clean_path = os.path.normpath(path).replace("\\", "/")

        payload = {
            "id": folder_id,
            "label": label,
            "path": clean_path,
            "type": folder_type,
            "devices": devices,
            "rescanIntervalS": 3600,
            "fsWatcherEnabled": True,
            "minDiskFree": {"value": 1, "unit": "%"},
            "ignorePerms": True,
        }

        code, body = self._send_request("/rest/config/folders", method="POST", payload=payload, timeout=45.0)
        if code in (200, 201):
            return True

        # Polling verifikasi direct endpoint jika timeout atau server lambat merespons (misal folder besar puluhan ribu berkas)
        try:
            for _ in range(6):
                time.sleep(1.5)
                f_code, f_body = self._send_request(f"/rest/config/folders/{urllib.parse.quote(folder_id)}", method="GET", timeout=6.0)
                if f_code == 200 and isinstance(f_body, dict) and f_body.get("id") == folder_id:
                    return True
        except Exception:
            pass

        if logger_manager:
            logger_manager.log_error(f"[Syncthing] Gagal menambahkan folder '{folder_id}' ({clean_path}): HTTP {code} - {body}")
        return False

    def delete_folder(self, folder_id):



        endpoint = f"/rest/config/folders/{urllib.parse.quote(folder_id)}"

        code, _ = self._send_request(endpoint, method="DELETE", timeout=15.0)

        if code in (200, 204):

            return True

        try:

            time.sleep(0.8)

            existing = [f.get("id") for f in self.get_folders()]

            if folder_id not in existing:

                return True

        except Exception:

            pass

        return False







    def get_completion(self, folder_id=None, device_id=None):



        params = []



        if folder_id:



            params.append(f"folder={urllib.parse.quote(folder_id)}")



        if device_id:



            params.append(f"device={urllib.parse.quote(device_id)}")



        qs = ("?" + "&".join(params)) if params else ""



        code, res = self._send_request(f"/rest/db/completion{qs}", timeout=2.5)



        if code == 200 and isinstance(res, dict):



            return res



        return None







    def get_folder_errors(self, folder_id):



        endpoint = f"/rest/folder/errors?folder={urllib.parse.quote(folder_id)}"



        code, res = self._send_request(endpoint, timeout=2.0)



        if code == 200 and isinstance(res, dict):



            return res.get("errors") or []



        return []







    def update_speed_rates(self, conn_data):



        now = time.time()



        state = get_speed_state(self.host, self.port)







        if not conn_data or not isinstance(conn_data, dict):



            return {



                "in_bps": state["in_rate"],



                "out_bps": state["out_rate"],



                "in_speed": format_transfer_speed(state["in_rate"]),



                "out_speed": format_transfer_speed(state["out_rate"]),



            }







        total_data = conn_data.get("total", {}) if isinstance(conn_data, dict) else {}



        curr_in = total_data.get("inBytesTotal") if isinstance(total_data, dict) else None



        curr_out = total_data.get("outBytesTotal") if isinstance(total_data, dict) else None







        active_conns = conn_data.get("connections", {}) if isinstance(conn_data, dict) else {}



        if curr_in is None or curr_out is None or (curr_in == 0 and curr_out == 0 and active_conns):



            sum_in = sum(c.get("inBytesTotal", 0) for c in active_conns.values() if isinstance(c, dict))



            sum_out = sum(c.get("outBytesTotal", 0) for c in active_conns.values() if isinstance(c, dict))



            if sum_in > 0 or sum_out > 0:



                curr_in = sum_in



                curr_out = sum_out







        curr_in = curr_in or 0



        curr_out = curr_out or 0







        last_in = state["last_in"]



        last_out = state["last_out"]



        last_time = state["last_time"]







        if last_time is not None and last_in is not None and last_out is not None:



            dt = max(0.5, now - last_time)



            if curr_in >= last_in and curr_out >= last_out:



                state["in_rate"] = max(0.0, (curr_in - last_in) / dt)



                state["out_rate"] = max(0.0, (curr_out - last_out) / dt)



            else:



                state["in_rate"] = 0.0



                state["out_rate"] = 0.0







        state["last_in"] = curr_in



        state["last_out"] = curr_out



        state["last_time"] = now







        self._cached_in_rate = state["in_rate"]



        self._cached_out_rate = state["out_rate"]



        self._last_in_bytes = curr_in



        self._last_out_bytes = curr_out



        self._last_speed_time = now







        return {



            "in_bps": state["in_rate"],



            "out_bps": state["out_rate"],



            "in_speed": format_transfer_speed(state["in_rate"]),



            "out_speed": format_transfer_speed(state["out_rate"]),



        }







    def calculate_sync_metrics(self):



        if not self.api_key:



            return {



                "active": False,



                "percentage": 100.0,



                "completed_files": 0,



                "total_files": 0,



                "errors": 0,



                "direction": "none",



                "in_speed": "0 B/s",



                "out_speed": "0 B/s",



                "state": "API Key Required",



            }







        conn_resp = self.get_connections()



        active_conns = conn_resp.get("connections", {}) if isinstance(conn_resp, dict) else {}



        speed_stats = self.update_speed_rates(conn_resp)







        folders = self.get_folders()



        if not folders:



            return {



                "active": False,



                "percentage": 100.0,



                "completed_files": 0,



                "total_files": 0,



                "errors": 0,



                "direction": "none",



                "in_speed": speed_stats["in_speed"],



                "out_speed": speed_stats["out_speed"],



                "state": "No Folders",



            }







        total_global_files = 0



        total_need_files = 0



        total_global_bytes = 0



        total_need_bytes = 0



        total_errors = 0







        is_downloading = False



        is_uploading = False







        upload_pct_list = []



        upload_stats = []







        for f in folders:



            f_id = f.get("id")



            if not f_id or f.get("paused", False):



                continue







            f_stat = self.get_folder_status(f_id)



            if f_stat:



                f_state = str(f_stat.get("state", "")).lower()



                g_files = f_stat.get("globalFiles", 0)



                n_files = f_stat.get("needFiles", 0)



                g_bytes = f_stat.get("globalBytes", 0)



                n_bytes = f_stat.get("needBytes", 0)







                total_global_files += g_files



                total_need_files += n_files



                total_global_bytes += g_bytes



                total_need_bytes += n_bytes







                # Download hanya aktif jika folder lokal benar-benar kekurangan berkas atau byte



                if n_files > 0 or n_bytes > 0:



                    is_downloading = True







            errs = self.get_folder_errors(f_id)



            if errs:



                total_errors += len(errs)







            folder_devices = [d.get("deviceID") for d in f.get("devices", []) if d.get("deviceID")]



            for dev_id in folder_devices:



                conn = active_conns.get(dev_id)



                if not conn or not conn.get("connected", False) or conn.get("paused", False):



                    continue







                comp = self.get_completion(folder_id=f_id, device_id=dev_id)



                if comp:



                    c_val = float(comp.get("completion", 100.0))



                    rem_items = comp.get("needItems", 0)



                    rem_bytes = comp.get("needBytes", 0)



                    g_items = comp.get("globalItems", 0)



                    g_bytes = comp.get("globalBytes", 0)







                    # PERBAIKAN BUG: Upload HANYA aktif jika remote benar-benar membutuhkan berkas/byte



                    # Mengabaikan c_val < 100 jika rem_items == 0 dan rem_bytes == 0 (artefak .stignore/metadata)



                    if (rem_items > 0 or rem_bytes > 0) and g_items > 0:



                        is_uploading = True



                        if g_bytes > 0 and rem_bytes > 0:



                            calc_p = max(0.1, ((g_bytes - rem_bytes) / g_bytes) * 100.0)



                            upload_pct_list.append(calc_p)



                        elif c_val < 100.0 and c_val > 0.0:



                            upload_pct_list.append(c_val)



                        else:



                            calc_p = max(0.1, ((g_items - rem_items) / g_items) * 100.0)



                            upload_pct_list.append(calc_p)







                        upload_stats.append((max(0, g_items - rem_items), g_items))







        # Hitung rasio berkas



        if is_uploading and upload_stats:



            completed_files = sum(s[0] for s in upload_stats)



            total_files = sum(s[1] for s in upload_stats)



        else:



            completed_files = max(0, total_global_files - total_need_files)



            total_files = max(total_global_files, completed_files)







        # GUARD LOGIC: Jika seluruh berkas sudah lengkap, paksa kembali ke status Idle



        if is_uploading and completed_files >= total_files:



            is_uploading = False







        if is_downloading and total_need_files == 0 and total_need_bytes == 0:



            is_downloading = False







        # Aktivitas transfer jaringan nyata (> 1 KB/s)



        has_net_out = speed_stats["out_bps"] > 1024



        has_net_in = speed_stats["in_bps"] > 1024







        # Penentuan arah dan persentase akhir



        if (is_uploading or has_net_out) and (is_downloading or has_net_in):



            direction = "both"



            active = True



            percentage = round((completed_files / total_files) * 100.0, 1) if total_files > 0 else 99.0



        elif is_uploading or has_net_out:



            direction = "upload"



            active = True



            if upload_pct_list:



                percentage = round(sum(upload_pct_list) / len(upload_pct_list), 1)



            elif total_files > 0:



                percentage = round((completed_files / total_files) * 100.0, 1)



            else:



                percentage = 99.0



            percentage = max(0.1, min(99.9, percentage))



        elif is_downloading or has_net_in:



            direction = "download"



            active = True



            if total_global_bytes > 0 and total_need_bytes > 0:



                percentage = round(((total_global_bytes - total_need_bytes) / total_global_bytes) * 100.0, 1)



            elif total_files > 0:



                percentage = round((completed_files / total_files) * 100.0, 1)



            else:



                percentage = 99.0



            percentage = max(0.1, min(99.9, percentage))



        else:



            direction = "none"



            active = False



            percentage = 100.0







        return {



            "active": active,



            "direction": direction,



            "percentage": percentage,



            "completed_files": completed_files,



            "total_files": total_files,



            "errors": total_errors,



            "in_speed": speed_stats["in_speed"],



            "out_speed": speed_stats["out_speed"],



            "state": "Syncing" if active else "Idle",



        }







    def resume(self, device_id=None):



        endpoint = f"/rest/system/resume?device={device_id}" if device_id else "/rest/system/resume"



        code, _ = self._send_request(endpoint, method="POST", timeout=2.5)



        return code == 200







    def pause(self, device_id=None):



        endpoint = f"/rest/system/pause?device={device_id}" if device_id else "/rest/system/pause"



        code, _ = self._send_request(endpoint, method="POST", timeout=2.5)



        return code == 200







    def set_folder_paused(self, folder_id, paused=True):



        endpoint = f"/rest/config/folders/{folder_id}"



        code, _ = self._send_request(endpoint, method="PATCH", payload={"paused": paused}, timeout=3.0)



        return code == 200







    def force_rescan(self):



        code, _ = self._send_request("/rest/db/scan", method="POST", timeout=2.5)



        return code == 200







    def rescan_folder(self, folder_id):



        endpoint = f"/rest/db/scan?folder={urllib.parse.quote(folder_id)}"



        code, _ = self._send_request(endpoint, method="POST", timeout=2.5)



        return code == 200







    def shutdown(self):



        code, _ = self._send_request("/rest/system/shutdown", method="POST", timeout=2.0)



        return code == 200











def ensure_syncthing_identity(target_dir=None):



    """



    Smart Identity Inheritance:



    Mendeteksi dan mengamankan sertifikat 'cert.pem' & 'key.pem' dari instalasi lama



    ke dalam direktori internal MyServer agar Device ID tidak berubah (0% re-pairing).



    """



    if not target_dir:



        target_dir = os.path.expandvars(r"%LOCALAPPDATA%\MyServer\sync_data")



    



    os.makedirs(target_dir, exist_ok=True)



    target_cert = os.path.join(target_dir, "cert.pem")



    target_key = os.path.join(target_dir, "key.pem")







    if os.path.exists(target_cert) and os.path.exists(target_key):



        return target_dir







    candidate_dirs = [



        os.path.expandvars(r"%LOCALAPPDATA%\Syncthing"),



        os.path.expandvars(r"%APPDATA%\Syncthing"),



        os.path.expandvars(r"%LOCALAPPDATA%\SyncTrayzor\data\syncthing"),



        os.path.expandvars(r"%APPDATA%\SyncTrayzor\data\syncthing"),



    ]







    import shutil



    for c_dir in candidate_dirs:



        c_cert = os.path.join(c_dir, "cert.pem")



        c_key = os.path.join(c_dir, "key.pem")



        if os.path.exists(c_cert) and os.path.exists(c_key):



            try:



                shutil.copy2(c_cert, target_cert)



                shutil.copy2(c_key, target_key)



                c_xml = os.path.join(c_dir, "config.xml")



                if os.path.exists(c_xml):



                    shutil.copy2(c_xml, os.path.join(target_dir, "config.xml"))



                if logger_manager and hasattr(logger_manager, "log_event"):



                    logger_manager.log_event("SYNCTHING", f"[Identity Inheritance] KTP digital cert.pem berhasil diimpor dari {c_dir}")



                break



            except Exception as e:



                if logger_manager and hasattr(logger_manager, "log_event"):



                    logger_manager.log_event("SYNCTHING", f"[Identity Inheritance Error] Gagal menyalin sertifikat: {e}")



                pass







    return target_dir











class LocalSyncthingDaemon:
    """Manajemen siklus hidup biner syncthing.exe lokal di Windows."""

    def __init__(self, exe_path=None, base_dir=None):
        self.base_dir = base_dir or os.getcwd()
        self.exe_path = exe_path or self._detect_syncthing_exe()
        self.process = None

    def _detect_syncthing_exe(self):
        app_bases = []
        if getattr(sys, "frozen", False):
            app_bases.append(os.path.dirname(sys.executable))
        app_bases.append(os.path.dirname(os.path.abspath(__file__)))
        if self.base_dir and self.base_dir not in app_bases:
            app_bases.append(self.base_dir)
        try:
            import config_manager
            b = config_manager.get_base_dir()
            if b and b not in app_bases:
                app_bases.append(b)
        except Exception:
            pass

        candidates = []
        for b in app_bases:
            candidates.append(os.path.join(b, "bin", "syncthing.exe"))
            candidates.append(os.path.join(b, "syncthing.exe"))
            candidates.append(os.path.join(b, "data", "syncthing", "syncthing.exe"))

        candidates.extend([
            os.environ.get("MYSERVER_SYNCTHING_PATH", ""),
            os.path.expandvars(r"%LOCALAPPDATA%\Syncthing\syncthing.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Syncthing\syncthing.exe"),
        ])

        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    def is_running(self, port=None):
        target_port = str(port or getattr(self, "port", "8384"))
        if self.process and self.process.poll() is None:
            return True
        client = SyncthingClient(host="127.0.0.1", port=target_port)
        return client.is_online()

    def start(self, custom_port="8384"):
        self.port = str(custom_port)
        if self.is_running(custom_port):
            return True

        try:
            ensure_syncthing_identity()
        except Exception:
            pass

        target_exe = self._detect_syncthing_exe()
        if not target_exe:
            if logger_manager and hasattr(logger_manager, "log_error"):
                logger_manager.log_error("[LocalSyncthingDaemon] Executable syncthing.exe tidak ditemukan di direktori bin MyServer maupun sistem.")
            return False

        cmd_v2 = [
            target_exe,
            "serve",
            "--no-browser",
            "--no-restart",
            f"--gui-address=http://127.0.0.1:{custom_port}",
        ]
        cmd_v1 = [
            target_exe,
            "-no-browser",
            "-no-restart",
            f"-gui-address=127.0.0.1:{custom_port}",
        ]
        try:
            creationflags = 0x08000000 if sys.platform == "win32" else 0
            exe_dir = os.path.dirname(target_exe)
            if logger_manager and hasattr(logger_manager, "log_info"):
                logger_manager.log_info(f"[LocalSyncthingDaemon] Meluncurkan daemon dari: {target_exe} (port {custom_port})")
            self.process = subprocess.Popen(
                cmd_v2,
                cwd=exe_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            time.sleep(1.2)
            if self.process.poll() is not None:
                self.process = subprocess.Popen(
                    cmd_v1,
                    cwd=exe_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                time.sleep(1.2)

            running = self.is_running(custom_port)
            if running:
                if logger_manager and hasattr(logger_manager, "log_info"):
                    logger_manager.log_info(f"[LocalSyncthingDaemon] Daemon lokal aktif di port {custom_port}")
            else:
                if logger_manager and hasattr(logger_manager, "log_warning"):
                    logger_manager.log_warning(f"[LocalSyncthingDaemon] Daemon belum merespons di port {custom_port} setelah diluncurkan.")
            return running
        except Exception as e:
            if logger_manager and hasattr(logger_manager, "log_error"):
                logger_manager.log_error(f"[LocalSyncthingDaemon] Gagal meluncurkan syncthing.exe: {e}")
            return False

    def stop(self, custom_port="8384", api_key=None):
        target_port = str(custom_port or getattr(self, "port", "8384"))
        if not api_key:
            try:
                import xml.etree.ElementTree as ET
                xml_path = os.path.expandvars(r"%LOCALAPPDATA%\Syncthing\config.xml")
                if os.path.exists(xml_path):
                    tree = ET.parse(xml_path)
                    elem = tree.find(".//apikey")
                    if elem is not None and elem.text:
                        api_key = elem.text.strip()
            except Exception:
                pass
        client = SyncthingClient(host="127.0.0.1", port=target_port, api_key=api_key or "")
        if client.is_online():
            try:
                client.shutdown()
                time.sleep(0.8)
            except Exception:
                pass

        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        elif client.is_online():
            try:
                subprocess.run(["taskkill", "/F", "/IM", "syncthing.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        if logger_manager and hasattr(logger_manager, "log_info"):
            logger_manager.log_info(f"[LocalSyncthingDaemon] Daemon lokal di port {target_port} dihentikan.")

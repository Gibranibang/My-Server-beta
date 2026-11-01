"""
MODULE: ZimaOS Metrics Manager (v3.6.0 Beta)
Features:
1. Dynamic API Role Verification (Suport Akun Admin Sekunder/Non-UID 1)
2. Dynamic Windows Network Drive Scanning (A-Z) & ZimaOS Ownership Filtering
3. Multi-Endpoint Fallback (CPU, RAM, & Instant Multi-Partition Storage)
4. RAPL CPU Wattage Calculation & Real-Time CPU Temperature (°C)
5. Stale Cache Fallback & CookieJar Session Management
6. System Power Control (Reboot/Shutdown for Admin)
"""

import base64
import ctypes
import http.cookiejar
import json
import os
import re
import shutil
import socket
import ssl
ipaddress = __import__('ipaddress')
import string
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_USER_AGENT = "MyServer-Desktop-App/3.10.13"


def is_domain_or_wan_host(host_str):
    """
    Memeriksa secara dinamis apakah host merupakan Domain FQDN publik atau IP WAN publik (Nol Hardcode).
    Digunakan untuk menentukan batas waktu adaptif ZimaOS API.
    """
    if not host_str:
        return False
    clean = (
        str(host_str)
        .replace("http://", "")
        .replace("https://", "")
        .split("/")[0]
        .split(":")[0]
        .strip()
        .lower()
    )
    if (
        not clean
        or clean in ("localhost", "127.0.0.1", "::1")
        or clean.endswith(".local")
        or clean.endswith(".lan")
    ):
        return False
    try:
        ip = ipaddress.ip_address(clean)
        if ip.is_loopback or ip.is_private:
            return False
        import zerotier_manager
        if zerotier_manager.is_zerotier_ip(clean):
            return False
        if ip in ipaddress.ip_network("100.64.0.0/10"):
            return False
        return True
    except (ValueError, Exception):
        return True

_du_inflight_lock = threading.Lock()
_du_inflight_drives = set()
_du_cached_usage = {}


def format_dynamic_bytes(size_bytes):
    """Format bytes ke B, KB, MB, GB, atau TB secara intuitif."""
    try:
        size_bytes = float(size_bytes)
    except (ValueError, TypeError):
        return "0.0 GB"

    if size_bytes <= 0:
        return "0.0 GB"

    gb = size_bytes / (1024**3)
    if gb >= 1024.0:
        tb = gb / 1024.0
        return f"{tb:.1f} TB"
    elif gb >= 1.0:
        return f"{gb:.1f} GB"
    elif size_bytes >= 1024 * 1024:
        mb = size_bytes / (1024**2)
        return f"{mb:.1f} MB"
    elif size_bytes >= 1024:
        kb = size_bytes / 1024.0
        return f"{kb:.1f} KB"
    else:
        return f"{int(size_bytes)} B"


def parse_size_hint_from_name(name):
    """Mendeteksi petunjuk kapasitas dari nama drive (contoh: 'Toshiba 1TB' -> 1000204886016 bytes)."""
    if not name or not isinstance(name, str):
        return 0
    m_tb = re.search(r"(\d+(?:\.\d+)?)\s*tb\b", name, re.IGNORECASE)
    if m_tb:
        try:
            return int(float(m_tb.group(1)) * 1000 * 1000 * 1000 * 1000)
        except Exception:
            pass
    m_gb = re.search(r"(\d+(?:\.\d+)?)\s*gb\b", name, re.IGNORECASE)
    if m_gb:
        try:
            return int(float(m_gb.group(1)) * 1000 * 1000 * 1000)
        except Exception:
            pass
    return 0


def decode_jwt_payload(token_str):
    """Mengekstrak payload JSON dari token JWT tanpa HTTP request tambahan."""
    if not token_str or not isinstance(token_str, str):
        return {}
    try:
        parts = token_str.split(".")
        if len(parts) < 2:
            return {}
        payload_segment = parts[1]
        remainder = len(payload_segment) % 4
        if remainder > 0:
            payload_segment += "=" * (4 - remainder)
        decoded_bytes = base64.urlsafe_b64decode(payload_segment)
        return json.loads(decoded_bytes.decode("utf-8"))
    except Exception:
        return {}


def _format_speed(val):
    """Format bytes per second into human-readable string."""
    try:
        v = float(val or 0)
    except (ValueError, TypeError):
        v = 0.0
    if v <= 0:
        return "0 B/s"
    if v < 1024:
        return f"{int(v)} B/s"
    elif v < 1024 * 1024:
        return f"{v / 1024:.1f} KB/s"
    elif v < 1024 * 1024 * 1024:
        return f"{v / (1024 * 1024):.1f} MB/s"
    else:
        return f"{v / (1024 * 1024 * 1024):.1f} GB/s"


class ZimaMetricsClient:
    """Client REST API ZimaOS dengan Dynamic Role Verification, RAPL Wattage, & Stale Cache."""

    def __init__(
        self,
        host=None,
        port=None,
        use_https=False,
        base_url=None,
        username="",
        password="",
        server_connections=None,
        server_name="",
        zerotier_ip="",
        allow_multi_route_failover=True,
    ):
        if base_url:
            self.base_url = base_url.rstrip("/")
        elif host:
            scheme = "https" if use_https else "http"
            if port and str(port) not in ("80", "443"):
                self.base_url = f"{scheme}://{host}:{port}"
            else:
                self.base_url = f"{scheme}://{host}"
        else:
            self.base_url = "http://127.0.0.1"

        parsed = urllib.parse.urlparse(self.base_url)
        self.host = host or parsed.hostname or "127.0.0.1"

        self.username = username
        self.password = password
        self.server_connections = server_connections or []
        self.server_name = server_name or ""
        self.zerotier_ip = (zerotier_ip or "").strip()
        self.allow_multi_route_failover = bool(allow_multi_route_failover)

        self._last_net_sample = None
        self.last_net_rates = {
            "speed_down_bps": 0,
            "speed_up_bps": 0,
            "speed_down_str": "0 B/s",
            "speed_up_str": "0 B/s",
        }
        self._cached_server_identities = None
        self._last_identities_refresh = 0
        self.token = None
        self.user_id = None
        self.role = ""
        self.is_admin = False

        # State untuk kalkulasi CPU Wattage
        self.prev_power_value = None
        self.prev_power_time = None

        # Stale Cache Storage untuk jaring pengaman saat spin-up/timeout
        self.last_storage_cache = {
            "total_bytes": 0,
            "used_bytes": 0,
            "usage_pct": 0.0,
            "label": "Storage",
            "partitions": [],
        }
        self.detailed_partitions_map = {}
        self._storage_bg_thread = None
        self._storage_bg_running = False
        self._last_bg_storage_fetch = 0
        self._failed_dev_paths = set()

        self.refresh_token = None

        # Adaptive SSL Context: Strict untuk domain FQDN publik, Unverified untuk IP privat lokal
        def _check_priv(h_str):
            if not h_str: return True
            h = h_str.strip().lower()
            if h in ("localhost", "127.0.0.1", "::1") or h.endswith(".local") or h.endswith(".lan"): return True
            try:
                ip = ipaddress.ip_address(h)
                if ip.is_private or ip.is_loopback:
                    return True
                import zerotier_manager
                return zerotier_manager.is_zerotier_ip(h)
            except (ValueError, Exception):
                return False

        if _check_priv(self.host):
            self.ssl_context = ssl._create_unverified_context()
        else:
            self.ssl_context = ssl.create_default_context()

        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self.ssl_context),
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
        )

    @property
    def connection_candidates(self):
        cands = []
        if self.base_url:
            cands.append(self.base_url.rstrip("/"))
        if getattr(self, "allow_multi_route_failover", True):
            for c in self.server_connections or []:
                if isinstance(c, dict) and c.get("url"):
                    u = c["url"].rstrip("/")
                    if u not in cands:
                        cands.append(u)
        if not cands:
            cands = ["http://127.0.0.1"]
        return cands

    @staticmethod
    def _format_speed(val):
        try:
            v = float(val or 0)
        except (ValueError, TypeError):
            v = 0.0
        if v <= 0:
            return "0 B/s"
        if v < 1024:
            return f"{int(v)} B/s"
        elif v < 1024 * 1024:
            return f"{v / 1024:.1f} KB/s"
        elif v < 1024 * 1024 * 1024:
            return f"{v / (1024 * 1024):.1f} MB/s"
        else:
            return f"{v / (1024 * 1024 * 1024):.1f} GB/s"

    def is_server_reachable(self, timeout=0.8):
        """
        Keterjangkauan jaringan nyata server aktif (TCP ke port rute aktif atau port SMB 445).
        Untuk Domain WAN publik (Cloudflare/CDN), wajib memvalidasi respon HTTP origin
        (menolak status 520-530 Cloudflare Error 1033 agar tidak terjadi False Online).
        """
        try:
            parsed = urllib.parse.urlparse(self.base_url)
            h = parsed.hostname or self.host
            if not h:
                return False
            web_port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

            # Jika Domain WAN: Verifikasi respon HTTP nyata origin
            if is_domain_or_wan_host(h):
                try:
                    probe_u = f"{parsed.scheme or 'http'}://{h}:{web_port}/"
                    req = urllib.request.Request(
                        probe_u,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MyServer/3.10.19"}
                    )
                    with urllib.request.urlopen(req, timeout=max(float(timeout), 2.5)) as resp:
                        return resp.status in (200, 204, 301, 302, 307, 308)
                except urllib.error.HTTPError as he:
                    # Kode 520-530 adalah error CDN (tunnel origin mati / error 1033)
                    if he.code in (520, 521, 522, 523, 524, 530):
                        return False
                    return he.code in (200, 204, 301, 302, 307, 308, 401, 403, 404, 405)
                except Exception:
                    return False

            # Jika LAN / IP Privat / ZeroTier lokal:
            # Cegah False Online akibat tabrakan IP di jaringan berbeda (misal perangkat router/printer/TV lain di Wi-Fi yang kebetulan memiliki IP yang sama).
            # Verifikasi bahwa target port web_port benar-benar merespon sebagai ZimaOS!
            try:
                with socket.create_connection((h, int(web_port)), timeout=float(timeout)):
                    pass
            except Exception:
                return False

            # Validasi identitas ZimaOS via HTTP probe cepat
            try:
                probe_scheme = parsed.scheme or "http"
                probe_u = f"{probe_scheme}://{h}:{web_port}/"
                req = urllib.request.Request(
                    probe_u,
                    headers={"User-Agent": "MyServer-Identity-Probe/3.10.21"}
                )
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=max(float(timeout), 1.5), context=ctx) as resp:
                    body = resp.read(1500).decode("utf-8", errors="ignore").lower()
                    h_str = str(resp.headers).lower()
                    if any(sig in body for sig in ("zimaos", "casaos", "icewhale", "images/zimaos-logo")) or any(sig in h_str for sig in ("zima", "casa")):
                        return True
            except urllib.error.HTTPError as he:
                if he.code == 401:
                    body = he.read(500).decode("utf-8", errors="ignore").lower()
                    if "unauthorized" in body or "casa" in body or "zima" in body:
                        return True
                h_str = str(he.headers).lower()
                if "zima" in h_str or "casa" in h_str:
                    return True
            except Exception:
                pass

            if self.token:
                try:
                    res = self._make_request("/v1/sys/hardware", timeout=1.5)
                    if res and isinstance(res, dict):
                        return True
                except Exception:
                    pass

            return False
        except Exception:
            pass
        return False

    def _make_request(
        self, endpoint, method="GET", data=None, headers=None, timeout=5.0
    ):
        """Helper HTTP Request dengan timeout adaptif & CookieJar."""
        try:
            cand_host = urllib.parse.urlparse(self.base_url).hostname or ""
            if is_domain_or_wan_host(cand_host):
                timeout = max(float(timeout or 5.0), 6.5)
        except Exception:
            pass
        url = f"{self.base_url}{endpoint}"
        req_headers = {
            "Content-Type": "application/json",
            "User-Agent": "MyServer-Desktop-App/3.6.10",
            "Accept": "application/json, text/plain, */*",
        }

        if self.token and isinstance(self.token, str):
            req_headers["Authorization"] = f"Bearer {self.token}"
            req_headers["token"] = self.token

        if headers:
            req_headers.update(headers)

        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(
            url, data=body, headers=req_headers, method=method
        )

        try:
            with self.opener.open(req, timeout=timeout) as resp:
                if resp.status in (200, 201):
                    res_body = resp.read().decode("utf-8")
                    try:
                        return json.loads(res_body)
                    except json.JSONDecodeError:
                        return {"status": "ok", "raw": res_body}
        except Exception:
            pass
        return None

    def authenticate(self):
        """Autentikasi ke ZimaOS & verifikasi role Admin secara dinamis dari API & JWT,
        lengkap dengan multi-route failover (Local IP, Domain, dll) dan timeout adaptif."""
        if not self.username or not self.password:
            return False

        login_data = {
            "username": self.username,
            "name": self.username,
            "password": self.password,
        }

        # Kumpulkan kandidat URL: jika allow_multi_route_failover=True, perbolehkan seluruh rute
        # Jika rute manual spesifik dipilih (allow_multi_route_failover=False), isolasi ketat pada base_url manual saja
        candidates = self.connection_candidates

        # Pre-probe soket paralel (0.8s total) untuk seluruh kandidat: kandidat yang mati dilewati tanpa
        # menambah waktu tunggu berurutan (mencegah login memakan belasan detik pada multi-rute/multi-server)
        def _probe_candidate(cand_url_probe):
            try:
                p_c = urllib.parse.urlparse(cand_url_probe)
                c_h = p_c.hostname or "127.0.0.1"
                c_p = p_c.port or (443 if p_c.scheme.lower() == "https" else 80)
                probe_timeout = 1.5 if is_domain_or_wan_host(c_h) else 0.8
                with socket.create_connection((c_h, c_p), timeout=probe_timeout):
                    return True
            except Exception:
                return False

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(candidates))) as pool:
            reach_flags = list(pool.map(_probe_candidate, candidates))
        reachable_map = dict(zip(candidates, reach_flags))

        for cand_url in candidates:
            if not reachable_map.get(cand_url):
                continue

            url = f"{cand_url}/v1/users/login"
            req_headers = {
                "Content-Type": "application/json",
                "User-Agent": "MyServer-Desktop-App/3.6.10",
                "Accept": "application/json, text/plain, */*",
            }
            body = json.dumps(login_data).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, headers=req_headers, method="POST"
            )

            try:
                # Timeout adaptif dinamis (10.0s Domain/WAN, 5.0s LAN fisik)
                cand_h = urllib.parse.urlparse(cand_url).hostname or ""
                login_timeout = 10.0 if is_domain_or_wan_host(cand_h) else 5.0
                with self.opener.open(req, timeout=login_timeout) as resp:
                    if resp.status in (200, 201):
                        res_body = resp.read().decode("utf-8")
                        try:
                            res = json.loads(res_body)
                        except json.JSONDecodeError:
                            res = {"status": "ok", "raw": res_body}

                        if res and isinstance(res, dict):
                            data = res.get("data", res)

                            raw_token = None
                            if isinstance(data, dict):
                                raw_token = (
                                    data.get("token")
                                    or data.get("access_token")
                                    or data.get("token_pair")
                                )
                            elif isinstance(data, str):
                                raw_token = data

                            if isinstance(raw_token, dict):
                                self.token = (
                                    raw_token.get("access_token")
                                    or raw_token.get("token")
                                    or str(raw_token)
                                )
                            elif isinstance(raw_token, str):
                                self.token = raw_token
                            else:
                                self.token = None

                            if isinstance(data, dict) and data.get("refresh_token"):
                                self.refresh_token = data.get("refresh_token")

                            if self.token:
                                # Update base_url ke route kandidat yang berhasil
                                self.base_url = cand_url
                                try:
                                    p = urllib.parse.urlparse(cand_url)
                                    if p.hostname:
                                        self.host = p.hostname
                                except Exception:
                                    pass

                                # 1. Ekstraksi Metadata JWT Payload
                                jwt_meta = decode_jwt_payload(self.token)
                                jwt_role = str(jwt_meta.get("role", "")).lower()
                                jwt_is_admin = jwt_meta.get("is_admin") is True
                                self.user_id = (
                                    jwt_meta.get("id")
                                    or jwt_meta.get("uid")
                                    or jwt_meta.get("sub")
                                )

                                # 2. Query Profile Endpoint Resmi ZimaOS untuk Verifikasi Hak Akses
                                cur_user = self._make_request("/v1/users/current", timeout=8.0)
                                api_is_admin = False
                                if cur_user and isinstance(cur_user, dict):
                                    c_data = cur_user.get("data", cur_user)
                                    role_str = str(
                                        c_data.get("role", "")
                                        or c_data.get("role_name", "")
                                        or c_data.get("group", "")
                                    ).lower()
                                    uid_val = c_data.get("id", c_data.get("uid"))
                                    if uid_val:
                                        self.user_id = uid_val

                                    api_is_admin = (
                                        role_str in ("admin", "administrator", "1")
                                        or c_data.get("is_admin") is True
                                        or c_data.get("role_id") == 1
                                    )

                                # 3. Penentuan Admin Dinamis 100% dari respons server ZimaOS (Zero Hardcoding)
                                self.is_admin = bool(
                                    jwt_role in ("admin", "administrator")
                                    or jwt_is_admin
                                    or api_is_admin
                                    or self.user_id in (1, "1")
                                )

                                return True
            except Exception:
                continue

        return False

    def refresh_access_token(self):
        """Pembaruan token JWT ZimaOS secara diam-diam (silent refresh) menggunakan refresh_token."""
        if not self.refresh_token or not self.base_url:
            return False
        try:
            url = f"{self.base_url}/v1/users/refresh"
            body = json.dumps({"refresh_token": self.refresh_token}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "MyServer-Desktop-App/3.8.0",
                },
                method="POST",
            )
            with self.opener.open(req, timeout=8.0) as resp:
                if resp.status in (200, 201):
                    res_body = resp.read().decode("utf-8")
                    data = json.loads(res_body).get("data", {})
                    new_tok = data.get("token") or data.get("access_token")
                    if new_tok:
                        self.token = new_tok
                        new_ref = data.get("refresh_token")
                        if new_ref:
                            self.refresh_token = new_ref
                        return True
        except Exception:
            pass
        return False

    def fetch_compose_apps(self):
        """
        Mengambil daftar kontainer aplikasi Docker yang terpasang di ZimaOS
        melalui endpoint resmi /v2/app_management/compose secara aman, dinamis,
        dan terotentikasi penuh dengan failover koneksi.
        """
        if not self.token:
            if not self.authenticate():
                return []

        res = self._make_request("/v2/app_management/compose", method="GET", timeout=6.0)
        if not res or not isinstance(res, dict):
            return []

        c_data = res.get("data", {})
        if not isinstance(c_data, dict):
            return []

        parsed_list = []
        for app_id, app_info in c_data.items():
            if not isinstance(app_info, dict):
                continue
            comp = app_info.get("compose", {}) or {}
            x_meta = comp.get("x-casaos", {}) or {}

            title = x_meta.get("title", {})
            if isinstance(title, dict):
                name = title.get("en_US") or title.get("id_ID") or (list(title.values())[0] if title else app_id)
            else:
                name = title or app_id

            if not name or not str(name).strip():
                name = str(app_id).replace("big-bear-", "").replace("-", " ").title()

            port_map = x_meta.get("port_map")
            scheme = x_meta.get("scheme") or "http"
            index = x_meta.get("index") or "/"
            status = app_info.get("status", "running")
            icon = x_meta.get("icon", "")

            # URL 100% dinamis mengikuti host client aktif
            target_host = self.host
            if is_domain_or_wan_host(self.host) and getattr(self, "zerotier_ip", None) and str(self.zerotier_ip).strip():
                target_host = str(self.zerotier_ip).strip()

            app_url = f"{scheme}://{target_host}:{port_map}{index}" if port_map else (
                f"{scheme}://{target_host}" if is_domain_or_wan_host(self.host) and getattr(self, "zerotier_ip", None) and str(self.zerotier_ip).strip() else f"{self.base_url}"
            )

            parsed_list.append({
                "id": f"zima_{app_id}",
                "name": str(name),
                "url": app_url,
                "port": str(port_map) if port_map else "",
                "status": status,
                "icon": icon,
                "is_zima_container": True
            })

        return parsed_list

    def fetch_zerotier_network_info(self):
        """
        Mengambil informasi konfigurasi ZeroTier Network ID dan Remote IPv4 dari ZimaOS REST API.
        Memanggil endpoint resmi: GET /v2/zimaos/zt/info.
        Mengembalikan dict: {'network_id': str, 'remote_ipv4': str, 'status': str} atau None.
        100% Murni Dinamis - Zero Hardcoded.
        """
        if not self.token:
            if not self.authenticate():
                return None

        endpoint = "/v2/zimaos/zt/info"
        res = self._make_request(endpoint, method="GET", timeout=4.0)
        if not res or not isinstance(res, dict):
            res = self._make_request("/zt/info", method="GET", timeout=4.0)

        if res and isinstance(res, dict):
            data = res.get("data", res)
            if isinstance(data, dict):
                net_id = data.get("network_id") or data.get("networkId") or data.get("id")
                remote_ip = data.get("remote_ipv4") or data.get("remoteIpv4") or data.get("ip")
                status = data.get("status", "unknown")
                if net_id:
                    return {
                        "network_id": str(net_id).strip(),
                        "remote_ipv4": str(remote_ip).strip() if remote_ip else "",
                        "status": str(status).strip(),
                    }
        return None

    def _calculate_cpu_wattage(self, cpu_obj):
        """Menghitung Wattage CPU berdasarkan selisih RAPL Energy."""
        try:
            p_obj = cpu_obj.get("power", {}) if isinstance(cpu_obj, dict) else {}
            if not isinstance(p_obj, dict):
                return 0.0

            raw_val = p_obj.get("value")
            if raw_val is None:
                return 0.0

            curr_val = float(raw_val)
            curr_time = time.time()

            wattage = 0.0
            if (
                self.prev_power_value is not None
                and self.prev_power_time is not None
            ):
                d_energy = curr_val - self.prev_power_value
                d_time = curr_time - self.prev_power_time

                if d_time > 0 and d_energy >= 0:
                    wattage = (d_energy / 1000000.0) / d_time

            self.prev_power_value = curr_val
            self.prev_power_time = curr_time
            return max(0.0, round(wattage, 1))
        except Exception:
            return 0.0

    @staticmethod
    def _canonical_vol_key(val):
        """Menghasilkan kunci kanonikal untuk partisi/volume agar deduplikasi akurat."""
        if not val:
            return ""
        s = str(val).strip().lower()
        s = s.replace("\\", "/")
        if s.startswith("/media/"):
            s = s[len("/media/"):].strip("/")
        elif s.startswith("/mnt/"):
            s = s[len("/mnt/"):].strip("/")
        elif s == "/data" or s == "system storage (/data)" or s.startswith("system storage"):
            return "data"

        # Hilangkan tanda kurung drive letter atau fstype seperti (Z:), (Z: exfat), (exfat), (btrfs), (ext4)
        s = re.sub(r"\s*\([^)]*\)", "", s).strip()
        return s

    def _fetch_storage_partitions_fast(self):
        """Mengambil data partisi & disk server ZimaOS secara cepat dan andal."""
        self._last_bg_storage_fetch = time.time()
        new_map = {}

        # 1. Coba endpoint resmi ZimaOS /v2/local_storage/storage?system=show (timeout 3.0s)
        try:
            st_res = self._make_request("/v2/local_storage/storage?system=show", timeout=3.0)
            s_data = st_res.get("data") if isinstance(st_res, dict) else st_res
            if not s_data:
                st_res = self._make_request("/v2/local_storage/storage", timeout=2.0)
                s_data = st_res.get("data") if isinstance(st_res, dict) else st_res
            if not s_data:
                st_res = self._make_request("/v2/zimaos/storage", timeout=2.0)
                s_data = st_res.get("data") if isinstance(st_res, dict) else st_res

            if s_data:
                disks_list = []
                if isinstance(s_data, list):
                    disks_list = s_data
                elif isinstance(s_data, dict):
                    disks_list = (
                        s_data.get("disks", [])
                        or s_data.get("partitions", [])
                        or s_data.get("storages", [])
                        or [s_data]
                    )

                for item in disks_list:
                    if not isinstance(item, dict):
                        continue
                    self._extract_disk_item(item, new_map)
                    child_list = item.get("children", []) or item.get("partitions", [])
                    if isinstance(child_list, list):
                        for child in child_list:
                            if isinstance(child, dict):
                                self._extract_disk_item(child, new_map)
        except Exception:
            pass

        # 2. Ambil statistik disk/USB/SATA dari /v2/local_storage/storage/stats untuk melengkapi dev_name & size
        try:
            stats_res = self._make_request("/v2/local_storage/storage/stats", timeout=2.0)
            if stats_res and isinstance(stats_res, dict):
                s_data = stats_res.get("data", stats_res)
                if isinstance(s_data, dict):
                    for k in ("sys_usb", "sys_sata", "sys_pci", "sys_nvme", "storages", "disks"):
                        val = s_data.get(k)
                        if not val:
                            continue
                        items = []
                        if isinstance(val, str):
                            try:
                                items = json.loads(val)
                            except Exception:
                                pass
                        elif isinstance(val, list):
                            items = val
                        elif isinstance(val, dict):
                            items = [val]
                        for item in items:
                            if isinstance(item, dict):
                                self._extract_disk_item(item, new_map)
                                child_list = item.get("children", []) or item.get("partitions", [])
                                if isinstance(child_list, list):
                                    for child in child_list:
                                        if isinstance(child, dict):
                                            self._extract_disk_item(child, new_map)
        except Exception:
            pass

        # 3. Ambil seluruh hardware disk fisik (SATA/NVMe/USB) dari /v1/sys/hardware
        try:
            hw_res = self._make_request("/v1/sys/hardware", timeout=2.0)
            if hw_res and isinstance(hw_res, dict):
                hw_data = hw_res.get("data", hw_res)
                disks = hw_data.get("disks", []) if isinstance(hw_data, dict) else []
                for d in disks:
                    if isinstance(d, dict):
                        self._extract_disk_item(d, new_map)
                        child_list = d.get("children", []) or d.get("partitions", [])
                        if isinstance(child_list, list):
                            for child in child_list:
                                if isinstance(child, dict):
                                    self._extract_disk_item(child, new_map)
        except Exception:
            pass

        if new_map:
            self.detailed_partitions_map.update(new_map)

    def _start_bg_storage_fetch(self):
        """Menjalankan pembacaan storage ZimaOS di latar belakang jika diperlukan."""
        if self._storage_bg_running:
            return

        now = time.time()
        # Jika baru saja fetch dalam 30 detik terakhir, lewati
        if now - self._last_bg_storage_fetch < 30.0:
            return

        def _bg_worker():
            self._storage_bg_running = True
            self._last_bg_storage_fetch = time.time()
            try:
                self._fetch_storage_partitions_fast()
            except Exception:
                pass
            finally:
                self._storage_bg_running = False

        self._last_bg_storage_fetch = now
        self._storage_bg_thread = threading.Thread(target=_bg_worker, daemon=True)
        self._storage_bg_thread.start()

    def _extract_disk_item(self, item, target_map):
        """Ekstraksi item partisi/disk dari respon API storage ZimaOS."""
        try:
            p_size = int(
                item.get("size", 0)
                or item.get("total", 0)
                or item.get("size_bytes", 0)
                or 0
            )
            p_used = int(item.get("used", 0) or item.get("used_bytes", 0) or 0)
            p_avail = int(item.get("avail", 0) or item.get("free", 0) or 0)
            if p_size > 0 and p_used == 0 and p_avail > 0:
                p_used = max(p_size - p_avail, 0)
            elif p_size > 0 and p_avail == 0 and p_used > 0:
                p_avail = max(p_size - p_used, 0)

            # Utamakan nama atau label volume yang mudah dibaca (e.g. "Disk_Aldhy", "Toshiba 1TB")
            p_name = item.get("name") or item.get("label") or item.get("drive_name") or item.get("path", "Disk")
            p_type = item.get("fs_type") or item.get("disk_type", "")
            m_point = item.get("mount_point") or item.get("mountpoint")

            p_pct = (p_used / p_size * 100.0) if p_size > 0 else 0.0
            label_str = f"{p_name} ({p_type})" if p_type else p_name

            data_obj = {
                "name": label_str,
                "raw_name": p_name,
                "mount_point": m_point,
                "fs_type": p_type,
                "used_bytes": p_used,
                "total_bytes": p_size,
                "avail_bytes": p_avail,
                "pct": round(p_pct, 1),
                "formatted_str": (
                    f"{format_dynamic_bytes(p_used)} / {format_dynamic_bytes(p_size)} ({p_pct:.1f}%)"
                    if p_size > 0
                    else "Ready"
                ),
            }

            # Indeks ke target_map dengan semua variasi key agar mudah dicocokkan
            c_key = self._canonical_vol_key(p_name)
            if c_key:
                target_map[c_key] = data_obj

            if m_point:
                target_map[m_point] = data_obj
                target_map[m_point.rstrip("/")] = data_obj
                target_map[m_point.lower()] = data_obj
                c_mp = self._canonical_vol_key(m_point)
                if c_mp:
                    target_map[c_mp] = data_obj

            if p_name:
                target_map[p_name] = data_obj
                target_map[p_name.lower()] = data_obj

            raw_label = item.get("label")
            if raw_label:
                target_map[raw_label] = data_obj
                target_map[raw_label.lower()] = data_obj

            drive_name = item.get("drive_name")
            if drive_name:
                target_map[drive_name] = data_obj
                target_map[drive_name.lower()] = data_obj

            dev_path = item.get("path")
            if dev_path and isinstance(dev_path, str):
                target_map[dev_path] = data_obj
                d_clean = dev_path.replace("/dev/", "").strip().lower()
                target_map[d_clean] = data_obj
                d_b = re.sub(r"[0-9]+$", "", d_clean).lower()
                if d_b:
                    target_map[d_b] = data_obj
                    target_map[f"/dev/{d_b}"] = data_obj

            disk_prop = item.get("device") or item.get("disk")
            if disk_prop and isinstance(disk_prop, str):
                target_map[disk_prop] = data_obj
                d_clean = disk_prop.replace("/dev/", "").strip().lower()
                target_map[d_clean] = data_obj
                d_b = re.sub(r"[0-9]+$", "", d_clean).lower()
                if d_b:
                    target_map[d_b] = data_obj
                    target_map[f"/dev/{d_b}"] = data_obj

            model = item.get("model")
            if model and isinstance(model, str):
                target_map[model] = data_obj
                target_map[model.lower()] = data_obj

            if p_name:
                p_norm1 = p_name.replace(" ", "_")
                p_norm2 = p_name.replace("_", " ")
                target_map[p_norm1] = data_obj
                target_map[p_norm1.lower()] = data_obj
                target_map[p_norm2] = data_obj
                target_map[p_norm2.lower()] = data_obj
        except Exception:
            pass

    def _get_zimaos_server_identities(self, server_connections=None):
        """Mengumpulkan seluruh hostname, IP, dan alias resmi server ZimaOS ini untuk validasi network drive."""
        now = time.time()
        if (
            self._cached_server_identities
            and (now - getattr(self, "_last_identities_refresh", 0)) < 60.0
        ):
            return self._cached_server_identities

        known_hosts = set()
        known_ips = set()

        # 1. Host aktif & base_url
        if self.host:
            known_hosts.add(str(self.host).lower().strip())
        if self.base_url:
            parsed = urllib.parse.urlparse(self.base_url)
            if parsed.hostname:
                known_hosts.add(str(parsed.hostname).lower().strip())

        # 1b. ZeroTier Virtual IP server aktif
        if getattr(self, "zerotier_ip", None):
            zt_h = str(self.zerotier_ip).lower().strip()
            if zt_h:
                known_hosts.add(zt_h)
                known_ips.add(zt_h)

        # 2. Host dari rute koneksi server
        conns = server_connections or self.server_connections or []
        for c in conns:
            if isinstance(c, dict):
                u = c.get("url", "")
                if u:
                    try:
                        p = urllib.parse.urlparse(u)
                        if p.hostname:
                            known_hosts.add(str(p.hostname).lower().strip())
                    except Exception:
                        pass

        # 3. Loopback lokal standar
        known_hosts.update({"localhost", "127.0.0.1"})

        # 4. Nama server yang dikonfigurasi pengguna (murni dinamis tanpa mDNS hardcode)
        if self.server_name:
            s_clean = re.sub(r"[^\w\-.]", "", str(self.server_name).strip().lower())
            if s_clean:
                known_hosts.add(s_clean)

        # 5. Resolusi DNS IPv4 non-blocking (timeout 0.4s) hanya untuk domain valid
        for h in list(known_hosts):
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", h):
                known_ips.add(h)
            elif "." in h and not h.endswith(".local"):
                res_ip = [None]
                def _resolve_h(target_h=h):
                    try:
                        res_ip[0] = socket.gethostbyname(target_h)
                    except Exception:
                        pass
                t_dns = threading.Thread(target=_resolve_h, daemon=True)
                t_dns.start()
                t_dns.join(timeout=0.4)
                if res_ip[0]:
                    known_ips.add(res_ip[0].strip().lower())

        for ip_cand in list(known_ips):
            try:
                nb_name = socket.gethostbyaddr(ip_cand)[0]
                if nb_name and nb_name.strip():
                    known_hosts.add(nb_name.strip().lower())
            except Exception:
                pass

        identities = {
            "hosts": known_hosts,
            "ips": known_ips,
        }
        self._cached_server_identities = identities
        self._last_identities_refresh = now
        return identities

    def get_user_authorized_shares(self):
        """Mengambil daftar share & path yang diizinkan untuk pengguna aktif via API Samba ZimaOS."""
        allowed = set()
        if self.is_admin:
            return allowed

        smb_res = self._make_request("/v2/users/samba/user", timeout=3.5)
        if smb_res and isinstance(smb_res, dict):
            smb_data = smb_res.get("data", smb_res)
            items_list = smb_data if isinstance(smb_data, list) else [smb_data]

            target_user = None
            for u in items_list:
                if not isinstance(u, dict):
                    continue
                u_name = str(u.get("username", "")).lower().strip()
                u_id = u.get("user_id")
                if (self.username and u_name == str(self.username).lower().strip()) or (
                    self.user_id and str(u_id) == str(self.user_id)
                ):
                    target_user = u
                    break

            if target_user:
                permissions = target_user.get("permissions", [])
                for perm in permissions:
                    if not isinstance(perm, dict):
                        continue
                    p_path = perm.get("path", "").strip()
                    if not p_path:
                        continue
                    clean_name = p_path.replace("/media/", "").replace("/DATA/", "").strip("/")
                    b_name = os.path.basename(p_path.rstrip("/"))
                    share_name = b_name or clean_name or p_path

                    for cand_n in (share_name, clean_name, b_name):
                        if not cand_n:
                            continue
                        allowed.add(cand_n)
                        allowed.add(cand_n.lower())
                        c_k = self._canonical_vol_key(cand_n)
                        if c_k:
                            allowed.add(c_k)
                        allowed.add(cand_n.replace(" ", "_"))
                        allowed.add(cand_n.replace(" ", "_").lower())
                        allowed.add(cand_n.replace("_", " "))
                        allowed.add(cand_n.replace("_", " ").lower())

                    allowed.add(p_path)
                    allowed.add(p_path.lower())
                    c_p = self._canonical_vol_key(p_path)
                    if c_p:
                        allowed.add(c_p)
        return allowed

    def _scan_windows_network_drives(self, server_connections=None, user_allowed_shares=None):
        """Mendeteksi network drives Windows (Zima Client / SMB) yang terhubung ke server ini
        dengan pemindaian dinamis di seluruh partisi (A-Z) dan filter kepemilikan via API ZimaOS."""
        if os.name != "nt":
            return []

        discovered = []
        try:
            mpr = ctypes.windll.mpr
            kernel32 = ctypes.windll.kernel32

            identities = self._get_zimaos_server_identities(server_connections)
            known_hosts = identities["hosts"]
            known_ips = identities["ips"]

            # Jika user_allowed_shares belum diberikan dan bukan admin, ambil dari API ZimaOS
            if user_allowed_shares is None and not self.is_admin:
                user_allowed_shares = self.get_user_authorized_shares()

            seen_net_shares = set()
            for letter in reversed(string.ascii_uppercase):
                drive_root = f"{letter}:\\"
                # 4 = DRIVE_REMOTE
                try:
                    drive_type = kernel32.GetDriveTypeW(drive_root)
                except Exception:
                    continue

                if drive_type == 4:
                    buf = ctypes.create_unicode_buffer(512)
                    buf_len = ctypes.c_ulong(512)
                    res = mpr.WNetGetConnectionW(f"{letter}:", buf, ctypes.byref(buf_len))
                    if res == 0:
                        remote_unc = buf.value
                        unc_clean = remote_unc.strip("\\")
                        parts = unc_clean.split("\\")
                        unc_host = parts[0].lower().strip() if parts else ""
                        share_name = parts[1] if len(parts) > 1 else unc_clean

                        # FILTER TAHAP 1: Apakah remote UNC ini benar milik ZimaOS?
                        is_zimaos = False
                        if unc_host:
                            if unc_host in known_hosts or unc_host in known_ips:
                                is_zimaos = True
                            elif any(h in unc_host or unc_host in h for h in known_hosts if len(h) >= 3):
                                is_zimaos = True
                            else:
                                try:
                                    unc_ip = socket.gethostbyname(unc_host)
                                    if unc_ip.lower().strip() in known_ips:
                                        is_zimaos = True
                                except Exception:
                                    pass

                        # Tolak jika drive ini milik aplikasi, PC, atau NAS lain
                        if not is_zimaos:
                            continue

                        c_key = self._canonical_vol_key(share_name)
                        dedup_key = c_key or share_name.strip().lower()
                        if dedup_key in seen_net_shares:
                            continue

                        # FILTER TAHAP 2: Apakah share ini milik akun pengguna aktif?
                        # Untuk non-admin: wajib diverifikasi terhadap izin Samba ZimaOS pengguna
                        if not self.is_admin and user_allowed_shares:
                            s_clean = share_name.strip().lower()
                            is_owned = (
                                share_name in user_allowed_shares
                                or s_clean in user_allowed_shares
                                or (c_key and c_k_val in user_allowed_shares if (c_k_val := c_key) else False)
                                or s_clean.replace(" ", "_") in user_allowed_shares
                                or s_clean.replace("_", " ") in user_allowed_shares
                            )
                            if not is_owned:
                                # Share ini di server ZimaOS tetapi bukan milik pengguna ini
                                continue

                        try:
                            # Prioritaskan data kapasitas dari REST API ZimaOS (/v2/local_storage/mount)
                            # agar tidak membanjiri SMB/Windows Explorer dengan GetDiskFreeSpaceExW setiap 2 detik!
                            existing_m = (
                                (self.detailed_partitions_map.get(c_key) if c_key else None)
                                or self.detailed_partitions_map.get(share_name)
                                or self.detailed_partitions_map.get(share_name.lower())
                                or self.detailed_partitions_map.get(f"/media/{share_name}")
                                or self.detailed_partitions_map.get(f"/media/{share_name.lower()}")
                            )
                            if (
                                existing_m
                                and isinstance(existing_m, dict)
                                and existing_m.get("total_bytes", 0) > 0
                                and not existing_m.get("is_network_drive")
                            ):
                                u_tot = int(existing_m.get("total_bytes", 0))
                                u_used = int(existing_m.get("used_bytes", 0))
                                u_avail = int(existing_m.get("avail_bytes", max(u_tot - u_used, 0)))
                                existing_fs = existing_m.get("fs_type", "")
                            else:
                                existing_fs = existing_m.get("fs_type", "") if isinstance(existing_m, dict) else ""
                                cache_k = (letter, remote_unc)
                                now_ts = time.time()
                                with _du_inflight_lock:
                                    cached_entry = _du_cached_usage.get(cache_k)
                                if (
                                    cached_entry
                                    and isinstance(cached_entry, tuple)
                                    and len(cached_entry) == 2
                                    and (now_ts - cached_entry[1]) < 30.0
                                ):
                                    usage = cached_entry[0]
                                else:
                                    usage_box = [None]
                                    with _du_inflight_lock:
                                        already_running = (letter in _du_inflight_drives)
                                        if not already_running:
                                            _du_inflight_drives.add(letter)
                                    if not already_running:
                                        def _read_du(dr=drive_root, d_let=letter, ck=cache_k):
                                            try:
                                                u_res = shutil.disk_usage(dr)
                                                usage_box[0] = u_res
                                                with _du_inflight_lock:
                                                    _du_cached_usage[ck] = (u_res, time.time())
                                            except Exception:
                                                pass
                                            finally:
                                                with _du_inflight_lock:
                                                    _du_inflight_drives.discard(d_let)
                                        t_du = threading.Thread(target=_read_du, daemon=True)
                                        t_du.start()
                                        t_du.join(timeout=0.5)
                                    with _du_inflight_lock:
                                        c_ent = _du_cached_usage.get(cache_k)
                                        usage = usage_box[0] or (c_ent[0] if isinstance(c_ent, tuple) else c_ent)
                                if usage is None:
                                    continue
                                u_tot = usage.total
                                u_used = usage.used
                                u_avail = usage.free

                            u_pct = round((u_used / u_tot * 100.0), 1) if u_tot > 0 else 0.0
                            fmt_str = f"{format_dynamic_bytes(u_used)} / {format_dynamic_bytes(u_tot)} ({u_pct:.1f}%)"

                            drive_data = {
                                "name": f"{share_name} ({letter}:)",
                                "raw_name": share_name,
                                "mount_point": f"/media/{share_name}",
                                "drive_letter": f"{letter}:",
                                "fs_type": existing_fs,
                                "remote_unc": remote_unc,
                                "used_bytes": u_used,
                                "total_bytes": u_tot,
                                "avail_bytes": u_avail,
                                "pct": u_pct,
                                "formatted_str": fmt_str,
                                "is_network_drive": True,
                            }
                            seen_net_shares.add(dedup_key)
                            discovered.append(drive_data)

                            # Daftarkan ke detailed_partitions_map dengan berbagai variasi key
                            if c_key:
                                self.detailed_partitions_map[c_key] = drive_data
                            self.detailed_partitions_map[share_name] = drive_data
                            self.detailed_partitions_map[share_name.lower()] = drive_data
                            self.detailed_partitions_map[f"/media/{share_name}"] = drive_data
                            self.detailed_partitions_map[f"/media/{share_name.lower()}"] = drive_data
                        except Exception:
                            pass
        except Exception:
            pass

        return discovered

    def fetch_metrics(self, on_online_callback=None):
        """Mengambil telemetri CPU, RAM, & Storage adaptif berdasarkan role asli pengguna."""
        result = {
            "online": False,
            "need_auth": False,
            "is_admin": self.is_admin,
            "cpu_temperature": None,
            "cpu_usage_pct": 0.0,
            "cpu_wattage": 0.0,
            "ram_usage_pct": 0.0,
            "ram_used_bytes": 0,
            "ram_total_bytes": 0,
            "storage_used_bytes": self.last_storage_cache["used_bytes"],
            "storage_total_bytes": self.last_storage_cache["total_bytes"],
            "storage_usage_pct": self.last_storage_cache["usage_pct"],
            "storage_label": self.last_storage_cache["label"],
            "storage_partitions": self.last_storage_cache["partitions"],
            "speed_down_bps": self.last_net_rates["speed_down_bps"],
            "speed_up_bps": self.last_net_rates["speed_up_bps"],
            "speed_down_str": self.last_net_rates["speed_down_str"],
            "speed_up_str": self.last_net_rates["speed_up_str"],
        }

        if not self.username or not self.password:
            result["need_auth"] = True
            result["online"] = self.is_server_reachable()
            return result

        if not self.token:
            if not self.authenticate():
                # Autentikasi API gagal belum tentu server mati: status Online ditentukan keterjangkauan jaringan
                result["need_auth"] = True
                result["online"] = self.is_server_reachable()
                return result

        u_data = {}
        result["online"] = True
        result["is_admin"] = self.is_admin

        # 1. Query CPU & RAM (Multi-endpoint fallback)
        util = self._make_request("/v1/sys/utilization", timeout=4.0)
        if not util:
            util = self._make_request("/v2/zimaos/sys/status", timeout=4.0)

        if not util and self.username:
            if self.authenticate():
                util = self._make_request("/v1/sys/utilization", timeout=4.0)
                if not util:
                    util = self._make_request("/v2/zimaos/sys/status", timeout=4.0)

        if not util:
            # Endpoint telemetri timeout/gagal sesaat: server tetap Online bila masih terjangkau di jaringan
            result["online"] = self.is_server_reachable()
            return result

        if util and isinstance(util, dict):
            u_data = util.get("data", util) if isinstance(util, dict) else {}

            # Parsing CPU & Wattage
            cpu_obj = u_data.get("cpu", {}) if isinstance(u_data, dict) else {}
            if isinstance(cpu_obj, dict):
                cpu_val = cpu_obj.get("percent") or cpu_obj.get("usage", 0.0)
            else:
                cpu_val = u_data.get("cpu_percent", 0.0)

            result["cpu_usage_pct"] = float(cpu_val) if cpu_val else 0.0
            result["cpu_wattage"] = self._calculate_cpu_wattage(cpu_obj)

            # Parsing Server Network Traffic (sys_net) - Telemetri Riil Server ZimaOS
            sys_net = u_data.get("sys_net") or u_data.get("net") or []
            if not sys_net and isinstance(util, dict):
                sys_net = util.get("sys_net") or util.get("net") or []
            if isinstance(sys_net, list) and sys_net:
                tot_recv = 0
                tot_sent = 0
                for iface in sys_net:
                    if not isinstance(iface, dict):
                        continue
                    iname = str(iface.get("name", "")).lower()
                    if iname.startswith("lo") or iname.startswith("docker") or iname.startswith("veth") or iname.startswith("br-"):
                        continue
                    tot_recv += int(iface.get("bytesRecv") or iface.get("bytes_recv") or 0)
                    tot_sent += int(iface.get("bytesSent") or iface.get("bytes_sent") or 0)

                now_ts = time.time()
                if self._last_net_sample:
                    prev_ts, prev_recv, prev_sent = self._last_net_sample
                    dt = max(now_ts - prev_ts, 0.5)
                    d_recv = max(tot_recv - prev_recv, 0)
                    d_sent = max(tot_sent - prev_sent, 0)
                    r_down = int(round(d_recv / dt))
                    r_up = int(round(d_sent / dt))
                    self.last_net_rates = {
                        "speed_down_bps": r_down,
                        "speed_up_bps": r_up,
                        "speed_down_str": self._format_speed(r_down),
                        "speed_up_str": self._format_speed(r_up),
                    }
                self._last_net_sample = (now_ts, tot_recv, tot_sent)
                result["speed_down_bps"] = self.last_net_rates["speed_down_bps"]
                result["speed_up_bps"] = self.last_net_rates["speed_up_bps"]
                result["speed_down_str"] = self.last_net_rates["speed_down_str"]
                result["speed_up_str"] = self.last_net_rates["speed_up_str"]

            # Parsing CPU Temperature & Hardware Fallback
            raw_temp = None
            if isinstance(cpu_obj, dict):
                raw_temp = cpu_obj.get("temperature")
                if raw_temp is None:
                    raw_temp = cpu_obj.get("temp")
            if raw_temp is None and isinstance(u_data, dict):
                raw_temp = u_data.get("temperature")

            if raw_temp is None:
                hw = self._make_request("/v1/sys/hardware", timeout=4.0)
                if hw and isinstance(hw, dict):
                    hw_data = hw.get("data", hw) if isinstance(hw, dict) else {}
                    if isinstance(hw_data, dict):
                        hw_cpu = hw_data.get("cpu")
                        if isinstance(hw_cpu, dict):
                            raw_temp = hw_cpu.get("temperature")
                            if raw_temp is None:
                                raw_temp = hw_cpu.get("temp")
                        elif isinstance(hw_cpu, list):
                            for c in hw_cpu:
                                if isinstance(c, dict):
                                    raw_temp = c.get("temperature")
                                    if raw_temp is None:
                                        raw_temp = c.get("temp")
                                    if raw_temp is not None:
                                        break
                        if raw_temp is None:
                            raw_temp = hw_data.get("temperature")

            if raw_temp is not None:
                try:
                    t_val = float(raw_temp)
                    if t_val >= 1000.0:
                        cand = t_val / 1000.0
                        t_val = cand if -40.0 <= cand <= 200.0 else None
                    elif t_val > 200.0 or t_val < -40.0:
                        t_val = None
                    result["cpu_temperature"] = t_val
                except (ValueError, TypeError):
                    result["cpu_temperature"] = None

            # Parsing RAM
            mem_obj = (
                u_data.get("mem", {})
                or u_data.get("ram", {})
                or u_data.get("memory", {})
            )
            if isinstance(mem_obj, dict):
                r_used = int(mem_obj.get("used", 0))
                r_tot = int(mem_obj.get("total", 0))
                r_pct = float(
                    mem_obj.get("usedPercent", mem_obj.get("percent", 0.0))
                )

                if r_tot > 0 and not r_pct:
                    r_pct = (r_used / r_tot) * 100.0

                result["ram_used_bytes"] = r_used
                result["ram_total_bytes"] = r_tot
                result["ram_usage_pct"] = round(r_pct, 1)

        # Komit instan status Online, CPU, & RAM (< 50ms) sebelum pemindaian Storage/SMB
        if callable(on_online_callback):
            try:
                on_online_callback(result)
            except Exception:
                pass

        # 2. Query Storage (Admin vs Non-Admin Dynamic Branching)
        # Pre-populate detailed_partitions_map di background agar tidak pernah memblokir thread telemetri
        now = time.time()
        if (now - self._last_bg_storage_fetch > 30.0):
            self._start_bg_storage_fetch()

        # Ambil seluruh mount points server dari /v2/local_storage/mount (respons instan ~20ms)
        # dan daftarkan ke detailed_partitions_map agar partisi seperti /media/Disk_Aldhy memiliki size dan used
        mount_res = self._make_request("/v2/local_storage/mount", timeout=2.5)
        raw_mount_items = []
        if mount_res and isinstance(mount_res, dict):
            raw_mount_items = mount_res.get("data", [])
            if isinstance(raw_mount_items, list):
                for m in raw_mount_items:
                    if not isinstance(m, dict):
                        continue
                    mp = m.get("mount_point", "")
                    m_size = int(m.get("size", 0) or m.get("total", 0) or 0)
                    m_used = int(m.get("used", 0) or 0)
                    m_avail = int(m.get("avail", 0) or m.get("free", 0) or 0)
                    if m_size > 0 and m_used == 0 and m_avail > 0:
                        m_used = max(m_size - m_avail, 0)
                    m_pct = (m_used / m_size * 100.0) if m_size > 0 else 0.0

                    p_name = None
                    if mp.startswith("/media/") and mp.count("/") == 2:
                        p_name = mp.replace("/media/", "").strip("/")
                    elif mp.startswith("/mnt/") and mp.count("/") == 2:
                        p_name = mp.replace("/mnt/", "").strip("/")
                    elif mp == "/DATA" or mp.lower() == "/data":
                        p_name = "System Storage (/DATA)"

                    if p_name and m_size > 0:
                        m_data = {
                            "name": p_name,
                            "raw_name": p_name,
                            "mount_point": mp,
                            "fs_type": m.get("fstype", ""),
                            "used_bytes": m_used,
                            "total_bytes": m_size,
                            "avail_bytes": m_avail,
                            "pct": round(m_pct, 1),
                            "formatted_str": f"{format_dynamic_bytes(m_used)} / {format_dynamic_bytes(m_size)} ({m_pct:.1f}%)",
                        }
                        c_k = self._canonical_vol_key(p_name)
                        if c_k:
                            self.detailed_partitions_map[c_k] = m_data
                        self.detailed_partitions_map[p_name] = m_data
                        self.detailed_partitions_map[p_name.lower()] = m_data
                        self.detailed_partitions_map[mp] = m_data
                        self.detailed_partitions_map[mp.lower()] = m_data

        # Ambil izin Samba user aktif jika non-admin
        user_allowed = self.get_user_authorized_shares() if not self.is_admin else None

        # Deteksi network drives Windows secara dinamis di seluruh partisi (A-Z) dan filter kepemilikan
        network_drives = self._scan_windows_network_drives(
            server_connections=self.server_connections,
            user_allowed_shares=user_allowed,
        )
        net_drives_by_key = {}
        for nd in network_drives:
            r_name = nd.get("raw_name") or nd.get("name") or ""
            c_k = self._canonical_vol_key(r_name)
            if c_k:
                net_drives_by_key[c_k] = nd
            if r_name:
                net_drives_by_key[r_name] = nd
                net_drives_by_key[r_name.lower()] = nd
            mp_nd = nd.get("mount_point")
            if mp_nd:
                net_drives_by_key[mp_nd] = nd
                net_drives_by_key[mp_nd.lower()] = nd

        RAW_DEV_REGEX = re.compile(
            r"^(?:sd[a-z][0-9]*|nvme[0-9]+[a-z0-9_]*|hd[a-z][0-9]*|vd[a-z][0-9]*|loop[0-9]*)$",
            re.IGNORECASE,
        )

        if self.is_admin:
            # 1. Global sys_disk dari /v1/sys/utilization (respons instan ~20ms)
            sys_disk = u_data.get("sys_disk", {}) if isinstance(u_data, dict) else {}
            sys_tot = int(sys_disk.get("size", 0) or sys_disk.get("total", 0) or 0)
            sys_used = int(sys_disk.get("used", 0) or 0)
            sys_pct = (sys_used / sys_tot * 100.0) if sys_tot > 0 else 0.0

            partitions = []
            seen_vol_keys = set()

            # Filesystem virtual/sistem yang WAJIB diabaikan
            EXCLUDED_FSTYPES = {
                "tmpfs", "devtmpfs", "overlay", "squashfs", "proc", "sysfs",
                "cgroup", "cgroup2", "pstore", "bpf", "autofs", "mqueue",
                "hugetlbfs", "debugfs", "tracefs", "fusectl", "configfs",
                "ramfs", "devpts", "binfmt_misc", "securityfs"
            }

            # Prefix path sistem internal Linux yang WAJIB diabaikan
            SYSTEM_PATH_PREFIXES = (
                "/proc", "/sys", "/dev", "/run", "/tmp", "/etc", "/usr",
                "/boot", "/var", "/opt", "/root", "/bin", "/sbin", "/lib"
            )

            # 3. Mount points server dari /v2/local_storage/mount
            data_partition_obj = None
            mount_items = raw_mount_items
            for m in mount_items:
                if not isinstance(m, dict):
                    continue
                mp = m.get("mount_point", "")
                fs = m.get("fstype", "")
                fs_lower = fs.lower()

                # Filter ketat: tolak fstype virtual/overlay
                if fs_lower in EXCLUDED_FSTYPES:
                    continue

                # Tolak path sistem, docker layer, containerd, atau bind mounts internal
                if not mp or mp == "/" or mp.startswith(SYSTEM_PATH_PREFIXES):
                    continue
                mp_lower = mp.lower()
                if "docker" in mp_lower or "containerd" in mp_lower or "overlay2" in mp_lower or "/.media" in mp_lower:
                    continue
                if mp.startswith("/mnt/overlay") or mp.startswith("/mnt/boot"):
                    continue

                # Simpan info /DATA untuk evaluasi cerdas nanti
                if mp == "/DATA" or mp.lower() == "/data" or mp.startswith("/DATA/"):
                    data_partition_obj = {
                        "name": "System Storage (/DATA)",
                        "raw_name": "System Storage",
                        "mount_point": "/DATA",
                        "used_bytes": sys_used,
                        "total_bytes": sys_tot,
                        "pct": round(sys_pct, 1),
                        "formatted_str": f"{format_dynamic_bytes(sys_used)} / {format_dynamic_bytes(sys_tot)} ({sys_pct:.1f}%)",
                    }
                    continue

                p_name = None
                if mp.startswith("/media/") and mp.count("/") == 2:
                    p_name = mp.replace("/media/", "").strip("/")
                elif mp.startswith("/mnt/") and mp.count("/") == 2:
                    p_name = mp.replace("/mnt/", "").strip("/")

                if not p_name:
                    continue

                c_key = self._canonical_vol_key(p_name)
                if not c_key or c_key in seen_vol_keys or c_key == "data":
                    continue
                seen_vol_keys.add(c_key)
                seen_vol_keys.add(p_name.lower())
                seen_vol_keys.add(mp.lower())

                # Ekstrak dev source Linux (e.g. /dev/sdd1 -> sdd1, sdd)
                src = str(m.get("source") or m.get("device") or "").strip()
                dev_raw = src.replace("/dev/", "").strip().lower()
                dev_base = re.sub(r"[0-9]+$", "", dev_raw).lower() if dev_raw else ""
                if dev_raw:
                    seen_vol_keys.add(dev_raw)
                if dev_base:
                    seen_vol_keys.add(dev_base)

                # A. Cek Network Drive terlebih dahulu (Dynamic Replacement jika terhubung di Windows!)
                nd_match = (
                    net_drives_by_key.get(c_key)
                    or net_drives_by_key.get(p_name)
                    or net_drives_by_key.get(p_name.lower())
                    or net_drives_by_key.get(mp)
                    or net_drives_by_key.get(mp.lower())
                )

                # B. Jika terhubung sebagai Network Drive: gunakan data Network Drive dinamis secara instan!
                if nd_match and nd_match.get("total_bytes", 0) > 0:
                    d_let = nd_match.get("drive_letter", "")
                    tag_parts = []
                    if d_let:
                        tag_parts.append(d_let)
                    if fs:
                        tag_parts.append(fs)
                    tag = f" ({' '.join(tag_parts)})" if tag_parts else ""
                    partitions.append({
                        "name": f"{p_name}{tag}",
                        "raw_name": p_name,
                        "mount_point": mp,
                        "drive_letter": d_let,
                        "used_bytes": nd_match["used_bytes"],
                        "total_bytes": nd_match["total_bytes"],
                        "pct": nd_match["pct"],
                        "formatted_str": nd_match["formatted_str"],
                        "is_network_drive": True,
                    })
                    continue

                # C. Cari info detail dari detailed_partitions_map (USB/SATA stats, disks, dev_base)
                p_info = (
                    self.detailed_partitions_map.get(c_key)
                    or self.detailed_partitions_map.get(mp)
                    or self.detailed_partitions_map.get(p_name)
                    or self.detailed_partitions_map.get(p_name.lower())
                    or (self.detailed_partitions_map.get(dev_raw) if dev_raw else None)
                    or (self.detailed_partitions_map.get(dev_base) if dev_base else None)
                    or (self.detailed_partitions_map.get(src) if src else None)
                )

                m_size = int(m.get("size", 0) or m.get("total", 0) or 0)
                m_used = int(m.get("used", 0) or 0)

                # D. Jika ukuran partisi masih 0, coba disk fallback query ke /v2/local_storage/disk/info
                if (not p_info or p_info.get("total_bytes", 0) <= 0) and m_size <= 0 and dev_base:
                    if dev_base not in self._failed_dev_paths:
                        try:
                            d_info = self._make_request(
                                f"/v2/local_storage/disk/info?path=/dev/{dev_base}",
                                timeout=1.5,
                            )
                            if d_info and isinstance(d_info, dict):
                                d_data = d_info.get("data", d_info)
                                if isinstance(d_data, dict):
                                    self._extract_disk_item(d_data, self.detailed_partitions_map)
                                    p_info = (
                                        self.detailed_partitions_map.get(c_key)
                                        or self.detailed_partitions_map.get(dev_base)
                                        or self.detailed_partitions_map.get(dev_raw)
                                    )
                            else:
                                self._failed_dev_paths.add(dev_base)
                        except Exception:
                            self._failed_dev_paths.add(dev_base)

                # E. Cek petunjuk kapasitas dari nama drive (contoh: "Toshiba 1TB" -> 1 TB)
                hint_size = parse_size_hint_from_name(p_name)
                if (not p_info or p_info.get("total_bytes", 0) <= 0) and m_size <= 0 and hint_size > 0:
                    p_info = {
                        "used_bytes": 0,
                        "total_bytes": hint_size,
                        "pct": 0.0,
                        "formatted_str": f"0.0 GB / {format_dynamic_bytes(hint_size)} (0.0%)",
                    }

                if p_info and p_info.get("total_bytes", 0) > 0:
                    d_let = p_info.get("drive_letter", "")
                    p_fs = fs or p_info.get("fs_type", "")
                    tag_parts = []
                    if d_let:
                        tag_parts.append(d_let)
                    if p_fs:
                        tag_parts.append(p_fs)
                    tag = f" ({' '.join(tag_parts)})" if tag_parts else ""
                    partitions.append({
                        "name": f"{p_name}{tag}",
                        "raw_name": p_name,
                        "mount_point": mp,
                        "drive_letter": d_let,
                        "used_bytes": p_info["used_bytes"],
                        "total_bytes": p_info["total_bytes"],
                        "pct": p_info["pct"],
                        "formatted_str": p_info["formatted_str"],
                    })
                elif m_size > 0:
                    m_pct = (m_used / m_size * 100.0) if m_size > 0 else 0.0
                    partitions.append({
                        "name": f"{p_name} ({fs})" if fs else p_name,
                        "raw_name": p_name,
                        "mount_point": mp,
                        "used_bytes": m_used,
                        "total_bytes": m_size,
                        "pct": round(m_pct, 1),
                        "formatted_str": f"{format_dynamic_bytes(m_used)} / {format_dynamic_bytes(m_size)} ({m_pct:.1f}%)",
                    })
                else:
                    partitions.append({
                        "name": f"{p_name} ({fs})" if fs else p_name,
                        "raw_name": p_name,
                        "mount_point": mp,
                        "used_bytes": 0,
                        "total_bytes": 0,
                        "pct": 0.0,
                        "formatted_str": f"Aktif ({mp})",
                    })

            if sys_tot > 0 and not data_partition_obj:
                data_partition_obj = {
                    "name": "System Storage (/DATA)",
                    "raw_name": "System Storage",
                    "mount_point": "/DATA",
                    "used_bytes": sys_used,
                    "total_bytes": sys_tot,
                    "pct": round(sys_pct, 1),
                    "formatted_str": f"{format_dynamic_bytes(sys_used)} / {format_dynamic_bytes(sys_tot)} ({sys_pct:.1f}%)",
                }

            # 5. Tambahkan partisi/pool dari detailed_partitions_map yang belum terdaftar:
            # PERHATIAN: Blokir semua nama device block Linux mentah (sdc, sdd, sde, nvme, dll.) dan umbrella /DATA
            if self.detailed_partitions_map:
                for key, p_data in self.detailed_partitions_map.items():
                    if not isinstance(p_data, dict):
                        continue
                    r_name = str(p_data.get("raw_name") or p_data.get("name") or "").strip()
                    # Jangan pernah menampilkan nama device kernel mentah sebagai partisi terpisah
                    if RAW_DEV_REGEX.match(r_name) or RAW_DEV_REGEX.match(str(key)):
                        continue
                    c_key = self._canonical_vol_key(r_name or p_data.get("mount_point"))
                    if not c_key or c_key in seen_vol_keys or RAW_DEV_REGEX.match(c_key):
                        continue
                    if c_key == "data":
                        continue
                    if p_data.get("total_bytes", 0) <= 0:
                        continue
                    seen_vol_keys.add(c_key)
                    partitions.append(p_data)

            # 6. Tambahkan network drives Windows yang belum terdaftar:
            for nd in network_drives:
                c_key = self._canonical_vol_key(nd.get("raw_name") or nd.get("name"))
                if not c_key or c_key in seen_vol_keys or c_key == "data":
                    continue
                seen_vol_keys.add(c_key)
                partitions.append(nd)

            # 6b. Evaluasi cerdas apakah /DATA merupakan umbrella pool agregat dari disk-disk individual:
            # Pada ZimaOS, jika pengguna memiliki 2+ disk fisik/network (/media/*, network drives)
            # dan kapasitas disk-disk tersebut mendekati atau sama dengan sys_tot,
            # maka sys_tot/DATA adalah pool total gabungan seluruh disk, BUKAN partisi fisik tersendiri!
            # Menampilkannya akan menduplikasi kapasitas (misal: 3.3TB + 3.3TB = 5.6TB / 6.6TB).
            user_disks = [p for p in partitions if p.get("mount_point") != "/DATA" and p.get("total_bytes", 0) > 0]
            user_disks_size = sum(p.get("total_bytes", 0) for p in user_disks)

            is_data_umbrella_pool = False
            if len(user_disks) >= 2 and sys_tot > 0:
                if user_disks_size >= sys_tot * 0.7 or abs(sys_tot - user_disks_size) < (sys_tot * 0.35):
                    is_data_umbrella_pool = True

            if not is_data_umbrella_pool and data_partition_obj and "data" not in seen_vol_keys:
                seen_vol_keys.add("data")
                partitions.insert(0, data_partition_obj)

            # 7. Hitung total penyimpanan seluruh partisi server secara akurat (deduplikasi kanonikal ketat)
            tot_p_size = 0
            tot_p_used = 0
            counted_volumes = set()

            for p in partitions:
                p_sz = p.get("total_bytes", 0)
                p_us = p.get("used_bytes", 0)
                if p_sz <= 0:
                    continue
                c_key = self._canonical_vol_key(p.get("raw_name") or p.get("name") or p.get("mount_point"))
                if c_key and c_key not in counted_volumes:
                    counted_volumes.add(c_key)
                    tot_p_size += p_sz
                    tot_p_used += p_us

            # Rekonsiliasi used_bytes jika ada disk berukuran > 0 tetapi used_bytes == 0 dan sys_used > tot_p_used
            if sys_used > tot_p_used:
                unmeasured = [p for p in partitions if p.get("total_bytes", 0) > 0 and p.get("used_bytes", 0) == 0]
                if len(unmeasured) == 1:
                    target_p = unmeasured[0]
                    diff_used = sys_used - tot_p_used
                    target_p["used_bytes"] = diff_used
                    t_pct = (diff_used / target_p["total_bytes"] * 100.0) if target_p["total_bytes"] > 0 else 0.0
                    target_p["pct"] = round(t_pct, 1)
                    target_p["formatted_str"] = f"{format_dynamic_bytes(diff_used)} / {format_dynamic_bytes(target_p['total_bytes'])} ({t_pct:.1f}%)"
                    tot_p_used += diff_used

            if tot_p_size > 0:
                tot_p_pct = (tot_p_used / tot_p_size * 100.0) if tot_p_size > 0 else 0.0
                self.last_storage_cache = {
                    "total_bytes": tot_p_size,
                    "used_bytes": tot_p_used,
                    "usage_pct": round(tot_p_pct, 1),
                    "label": "Server Storage",
                    "partitions": partitions,
                }
            elif sys_tot > 0:
                self.last_storage_cache = {
                    "total_bytes": sys_tot,
                    "used_bytes": sys_used,
                    "usage_pct": round(sys_pct, 1),
                    "label": "System Storage",
                    "partitions": partitions,
                }
            elif partitions:
                self.last_storage_cache = {
                    "total_bytes": 0,
                    "used_bytes": 0,
                    "usage_pct": 0.0,
                    "label": "Server Storage",
                    "partitions": partitions,
                }

        else:
            # AKUN NON-ADMIN:
            # Query /v2/users/samba/user (respons instan ~30ms)
            smb_res = self._make_request("/v2/users/samba/user", timeout=5.0)
            partitions = []
            tot_size = 0
            tot_used = 0

            if smb_res and isinstance(smb_res, dict):
                smb_data = smb_res.get("data", smb_res)
                items_list = smb_data if isinstance(smb_data, list) else [smb_data]

                # Filter khusus user aktif (berdasarkan username atau user_id dinamis)
                target_user = None
                for u in items_list:
                    if not isinstance(u, dict):
                        continue
                    u_name = str(u.get("username", "")).lower()
                    u_id = u.get("user_id")
                    if (self.username and u_name == self.username.lower()) or (
                        self.user_id and str(u_id) == str(self.user_id)
                    ):
                        target_user = u
                        break

                if target_user:
                    permissions = target_user.get("permissions", [])
                    seen_paths = set()

                    # Normalisasi path untuk menghindari duplikasi
                    valid_paths = []
                    for perm in permissions:
                        if not isinstance(perm, dict):
                            continue
                        p_path = perm.get("path", "").strip()
                        if p_path and p_path not in seen_paths:
                            seen_paths.add(p_path)
                            valid_paths.append(perm)

                    seen_drive_letters = set()
                    for perm in valid_paths:
                        p_path = perm.get("path", "")
                        ro = perm.get("read_only", False)
                        mode_str = "Read-Only" if ro else "Read-Write"
                        clean_name = p_path.replace("/media/", "").replace("/DATA/", "").strip("/")
                        b_name = os.path.basename(p_path.rstrip("/"))
                        share_name = b_name or clean_name or p_path

                        c_key = self._canonical_vol_key(share_name)

                        # Cek apakah ada data granular disk dari detailed_partitions_map (network drive live / mount API)
                        p_info = (
                            self.detailed_partitions_map.get(c_key)
                            or self.detailed_partitions_map.get(share_name)
                            or self.detailed_partitions_map.get(share_name.lower())
                            or self.detailed_partitions_map.get(clean_name)
                            or self.detailed_partitions_map.get(clean_name.lower())
                            or self.detailed_partitions_map.get(p_path)
                            or self.detailed_partitions_map.get(p_path.lower())
                        )
                        if not p_info:
                            for mp, info in self.detailed_partitions_map.items():
                                if p_path.startswith(mp) or str(mp).startswith(p_path):
                                    p_info = info
                                    break

                        # Fallback kapasitas dari nama disk (contoh: Toshiba 1TB -> 1 TB)
                        if not p_info or p_info.get("total_bytes", 0) <= 0:
                            hint_sz = parse_size_hint_from_name(share_name)
                            if hint_sz > 0:
                                p_info = {
                                    "used_bytes": 0,
                                    "total_bytes": hint_sz,
                                    "pct": 0.0,
                                    "formatted_str": f"0.0 GB / {format_dynamic_bytes(hint_sz)} (0.0%)",
                                }

                        if p_info and p_info.get("total_bytes", 0) > 0:
                            p_used = p_info["used_bytes"]
                            p_size = p_info["total_bytes"]
                            p_pct = p_info["pct"]
                            d_letter = p_info.get("drive_letter")
                            display_tag = f"{d_letter} {mode_str}" if d_letter else mode_str
                            partitions.append({
                                "name": f"{share_name} ({display_tag})",
                                "raw_name": share_name,
                                "mount_point": p_path,
                                "drive_letter": d_letter,
                                "used_bytes": p_used,
                                "total_bytes": p_size,
                                "pct": p_pct,
                                "formatted_str": f"{format_dynamic_bytes(p_used)} / {format_dynamic_bytes(p_size)} ({p_pct:.1f}%)",
                            })
                            # Cegah perhitungan ganda jika satu drive letter memiliki banyak sub-folder share
                            vol_id = d_letter or c_key or p_path
                            if vol_id not in seen_drive_letters:
                                seen_drive_letters.add(vol_id)
                                tot_size += p_size
                                tot_used += p_used
                        else:
                            partitions.append({
                                "name": share_name,
                                "used_bytes": 0,
                                "total_bytes": 0,
                                "pct": 0.0,
                                "formatted_str": f"Akses {mode_str} ({p_path})",
                            })

            # Jika API Samba kosong atau gagal, tetapi Windows Network Drives terdeteksi:
            if not partitions and network_drives:
                for nd in network_drives:
                    partitions.append(nd)
                    tot_size += nd.get("total_bytes", 0)
                    tot_used += nd.get("used_bytes", 0)

            if partitions:
                tot_pct = (tot_used / tot_size * 100.0) if tot_size > 0 else 0.0
                self.last_storage_cache = {
                    "total_bytes": tot_size,
                    "used_bytes": tot_used,
                    "usage_pct": round(tot_pct, 1),
                    "label": f"Workspace ({self.username})",
                    "partitions": partitions,
                }
            else:
                self.last_storage_cache = {
                    "total_bytes": 0,
                    "used_bytes": 0,
                    "usage_pct": 0.0,
                    "label": f"Workspace ({self.username})",
                    "partitions": [{
                        "name": f"User {self.username}",
                        "formatted_str": "Tidak ada direktori share khusus",
                    }],
                }

        # Sync result dengan Stale Cache
        result["storage_used_bytes"] = self.last_storage_cache["used_bytes"]
        result["storage_total_bytes"] = self.last_storage_cache["total_bytes"]
        result["storage_usage_pct"] = self.last_storage_cache["usage_pct"]
        result["storage_label"] = self.last_storage_cache["label"]
        result["storage_partitions"] = self.last_storage_cache["partitions"]

        return result

    def system_control(self, action):
        """Mengirim perintah Reboot ('restart') atau Shutdown ('off') via HTTP PUT."""
        if not self.is_admin:
            return False, "Aksi ini memerlukan hak akses Admin."

        if action not in ("restart", "off"):
            return False, "Aksi tidak valid."

        res = self._make_request(f"/v1/sys/state/{action}", method="PUT", timeout=5.0)
        if res:
            act_name = "Reboot" if action == "restart" else "Shutdown"
            return True, f"Perintah {act_name} berhasil dikirim ke server."
        return False, f"Gagal mengeksekusi perintah {action} ke server."

    def determine_task_owner(self, server_path, folder_id="", folder_label=""):
        """Menentukan pemilik task sinkronisasi berdasarkan path folder dan izin Samba ZimaOS."""
        if not server_path:
            return None
        try:
            smb_res = self._make_request("/v2/users/samba/user", timeout=3.0)
            if smb_res and isinstance(smb_res, dict):
                smb_data = smb_res.get("data", smb_res)
                items = smb_data if isinstance(smb_data, list) else [smb_data]
                norm_path = server_path.replace("\\", "/").rstrip("/").lower()
                for u in items:
                    if not isinstance(u, dict):
                        continue
                    u_name = u.get("username", "")
                    perms = u.get("permissions", [])
                    for p in perms:
                        if not isinstance(p, dict):
                            continue
                        p_p = str(p.get("path", "")).replace("\\", "/").rstrip("/").lower()
                        if p_p and (norm_path == p_p or norm_path.startswith(p_p) or p_p.startswith(norm_path)):
                            return u_name
        except Exception:
            pass
        return None

    def is_user_authorized_for_path(self, username, server_path):
        """Memeriksa apakah pengguna memiliki hak akses ke server_path berdasarkan izin Samba ZimaOS."""
        if not username or not server_path:
            return False
        if self.is_admin:
            return True
        try:
            allowed = self.get_user_authorized_shares()
            norm_path = server_path.replace("\\", "/").rstrip("/").lower()
            clean = norm_path.replace("/media/", "").replace("/data/", "").strip("/")
            return (norm_path in allowed or clean in allowed or self._canonical_vol_key(clean) in allowed)
        except Exception:
            return False
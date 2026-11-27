import ctypes
import ctypes.wintypes
import http.server
import io
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import zipfile
from unittest import mock

BETA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BETA_DIR not in sys.path:
    sys.path.insert(0, BETA_DIR)


def _install_linux_win_stubs():
    """Install minimal Windows module stubs so myserver_core_service imports on Linux test runners."""
    if not hasattr(ctypes, "windll"):
        class _DummyDll:
            def __getattr__(self, _name):
                return types.SimpleNamespace(argtypes=None, restype=None, __call__=lambda *a, **k: 0)

        class _Windll:
            def __getattr__(self, _name):
                return _DummyDll()

        ctypes.windll = _Windll()
        ctypes.WinDLL = lambda *a, **k: _DummyDll()

    if "winreg" not in sys.modules:
        sys.modules["winreg"] = types.SimpleNamespace(
            HKEY_CURRENT_USER=0,
            HKEY_LOCAL_MACHINE=1,
            KEY_READ=0,
            REG_SZ=1,
            OpenKey=lambda *a, **k: None,
            QueryValueEx=lambda *a, **k: ("", 0),
            CloseKey=lambda *a, **k: None,
        )


_install_linux_win_stubs()
import myserver_core_service as core  # noqa: E402


class _FakeHttpResponse:
    def __init__(self, payload_obj, status=200):
        self._raw = json.dumps(payload_obj).encode("utf-8")
        self.status = status

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestBackendDetection(unittest.TestCase):
    def setUp(self):
        self._orig_backend_info = dict(core._cached_backend_info)
        self._orig_bundled_ver = dict(core._cached_bundled_backend_version)
        self._orig_remote_manifest = dict(core._remote_backend_manifest_cache)
        self._orig_url_cache = dict(core._backend_url_cache)
        self._reset_caches()

    def tearDown(self):
        core._cached_backend_info.clear()
        core._cached_backend_info.update(self._orig_backend_info)
        core._cached_bundled_backend_version.clear()
        core._cached_bundled_backend_version.update(self._orig_bundled_ver)
        core._remote_backend_manifest_cache.clear()
        core._remote_backend_manifest_cache.update(self._orig_remote_manifest)
        core._backend_url_cache.clear()
        core._backend_url_cache.update(self._orig_url_cache)

    def _reset_caches(self):
        core._backend_url_cache.clear()
        core._cached_backend_info["timestamp"] = 0
        core._cached_backend_info["server_id"] = ""
        core._cached_backend_info["data"] = {
            "online": False,
            "version": "",
            "latestVersion": "",
            "url": "",
        }
        core._cached_bundled_backend_version["timestamp"] = 0
        core._cached_bundled_backend_version["version"] = ""
        core._cached_bundled_backend_version["source"] = ""
        core._remote_backend_manifest_cache["timestamp"] = 0.0
        core._remote_backend_manifest_cache["last_attempt"] = 0.0
        core._remote_backend_manifest_cache["version"] = ""

    def test_real_workspace_resources_bundled_and_git_tracked(self):
        self.assertEqual(core._get_bundled_backend_version(allow_remote=False), "2.2.2")
        zip_pkg, tar_pkg = core._get_bundled_backend_packages()
        self.assertIsNotNone(zip_pkg)
        self.assertIsNotNone(tar_pkg)
        self.assertTrue(os.path.isfile(zip_pkg))
        self.assertTrue(os.path.isfile(tar_pkg))
        self.assertEqual(os.path.basename(zip_pkg), "MyServer-Backend-ZimaOS.zip")
        self.assertEqual(os.path.basename(tar_pkg), "MyServer-Backend-ZimaOS.tar.gz")

        with zipfile.ZipFile(zip_pkg, "r") as zf:
            zip_entries = sorted(zf.namelist())
            zip_sh_mode = (zf.getinfo("install_zimaos.sh").external_attr >> 16) & 0o777
        with tarfile.open(tar_pkg, "r:gz") as tf:
            tar_entries = sorted(m.name for m in tf.getmembers() if m.isfile())
            tar_sh_mode = tf.getmember("install_zimaos.sh").mode & 0o777

        self.assertEqual(len(zip_entries), 35)
        self.assertIn("app/routers/share.py", zip_entries)
        self.assertIn("app/services/dashboard_service.py", zip_entries)
        self.assertIn("app/static/icons/icon-192.png", zip_entries)
        self.assertIn("app/static/icons/icon-512.png", zip_entries)
        self.assertIn("app/static/icons/icon-maskable-512.png", zip_entries)
        self.assertIn("app/static/icons/logo-dark-mark.svg", zip_entries)
        self.assertIn("app/static/pdfjs/pdf.min.mjs", zip_entries)
        self.assertIn("app/static/pdfjs/pdf.worker.min.mjs", zip_entries)
        self.assertIn("app/static/vendor/uqr.mjs", zip_entries)
        self.assertEqual(zip_entries, tar_entries)
        self.assertIn("app/services/smb_manager.py", zip_entries)
        self.assertIn("app/routers/smb.py", zip_entries)
        self.assertEqual(zip_sh_mode, 0o755)
        self.assertEqual(tar_sh_mode, 0o755)
        for entry in zip_entries:
            self.assertFalse(entry.startswith("tests/"), f"Unexpected test entry: {entry}")
            self.assertNotEqual(entry, "dev_server.py")
            self.assertNotIn("__pycache__", entry)
            self.assertFalse(entry.endswith(".pyc"), f"Unexpected .pyc entry: {entry}")
            self.assertNotIn("sync-conflict", entry)
            self.assertFalse(entry.startswith(("data/", "storage/", "backup/", ".git/")))

        proc = subprocess.run(
            [
                "git",
                "check-ignore",
                "resources/backend_manifest.json",
                "resources/MyServer-Backend-ZimaOS.zip",
                "resources/MyServer-Backend-ZimaOS.tar.gz",
            ],
            cwd=BETA_DIR,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0, f"Canonical backend resources must not be ignored: {proc.stdout}")

    def test_semver_comparison_boundaries(self):
        self.assertEqual(core._compare_backend_versions("1.2.3", "1.2.5"), -1)
        self.assertEqual(core._compare_backend_versions("v1.2.4", "1.2.5"), -1)
        self.assertEqual(core._compare_backend_versions("1.2.5", "v1.2.5"), 0)
        self.assertEqual(core._compare_backend_versions("1.2.6", "1.2.5"), 1)
        self.assertEqual(core._compare_backend_versions("v1.10.0", "1.2.5"), 1)
        self.assertEqual(core._compare_backend_versions("1.2", "1.2.0"), 0)

    def test_bin_parent_and_meipass_resource_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = os.path.join(tmp, "app")
            bin_dir = os.path.join(app_dir, "bin")
            res_dir = os.path.join(app_dir, "resources")
            os.makedirs(bin_dir, exist_ok=True)
            os.makedirs(res_dir, exist_ok=True)
            with open(os.path.join(res_dir, "backend_manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"version": "1.2.5"}, f)
            open(os.path.join(res_dir, "MyServer-Backend-ZimaOS.zip"), "wb").close()
            open(os.path.join(res_dir, "MyServer-Backend-ZimaOS.tar.gz"), "wb").close()

            with mock.patch.object(core.config_manager, "get_base_dir", return_value=bin_dir):
                self._reset_caches()
                self.assertEqual(core._get_bundled_backend_version(allow_remote=False), "1.2.5")
                z, t = core._get_bundled_backend_packages()
                self.assertEqual(os.path.abspath(z), os.path.abspath(os.path.join(res_dir, "MyServer-Backend-ZimaOS.zip")))
                self.assertEqual(os.path.abspath(t), os.path.abspath(os.path.join(res_dir, "MyServer-Backend-ZimaOS.tar.gz")))

            meipass_dir = os.path.join(tmp, "meipass")
            mei_res = os.path.join(meipass_dir, "resources")
            os.makedirs(mei_res, exist_ok=True)
            with open(os.path.join(mei_res, "backend_manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"version": "1.2.9"}, f)
            isolated_dir = os.path.join(tmp, "isolated", "bin")
            os.makedirs(isolated_dir, exist_ok=True)
            with (
                mock.patch.object(core.config_manager, "get_base_dir", return_value=isolated_dir),
                mock.patch.object(sys, "frozen", True, create=True),
                mock.patch.object(sys, "executable", os.path.join(isolated_dir, "myserver-core.exe")),
                mock.patch.object(sys, "_MEIPASS", meipass_dir, create=True),
            ):
                self._reset_caches()
                self.assertEqual(core._get_bundled_backend_version(allow_remote=False), "1.2.9")

    def test_bundled_version_priority_and_sorted_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            res_dir = os.path.join(tmp, "resources")
            os.makedirs(res_dir, exist_ok=True)

            # Corrupt manifest + multiple versioned ZIPs -> must pick highest semver ZIP (1.10.0 > 1.2.5 > 1.2.3).
            with open(os.path.join(res_dir, "backend_manifest.json"), "w", encoding="utf-8") as f:
                f.write("{invalid json")

            for fn, ver in [
                ("MyServer-Backend-v1.2.3-ZimaOS.zip", "1.2.3"),
                ("MyServer-Backend-v1.2.5-ZimaOS.zip", "1.2.5"),
                ("MyServer-Backend-v1.10.0-ZimaOS.zip", "1.10.0"),
            ]:
                with zipfile.ZipFile(os.path.join(res_dir, fn), "w") as zf:
                    zf.writestr("app/config.py", f'SERVER_VERSION = "{ver}"\n')

            with mock.patch.object(core.config_manager, "get_base_dir", return_value=tmp):
                self._reset_caches()
                self.assertEqual(core._get_bundled_backend_version(allow_remote=False), "1.10.0")

                # Canonical archive name takes precedence when present.
                with zipfile.ZipFile(os.path.join(res_dir, "MyServer-Backend-ZimaOS.zip"), "w") as zf:
                    zf.writestr("app/config.py", 'SERVER_VERSION = "1.2.5"\n')
                self._reset_caches()
                self.assertEqual(core._get_bundled_backend_version(allow_remote=False), "1.2.5")

            # Remove all ZIPs and test TAR.GZ fallback.
            for fn in os.listdir(res_dir):
                if fn.endswith(".zip"):
                    os.remove(os.path.join(res_dir, fn))
            tar_path = os.path.join(res_dir, "MyServer-Backend-ZimaOS.tar.gz")
            with tarfile.open(tar_path, "w:gz") as tf:
                payload = b'SERVER_VERSION = "1.2.7"\n'
                ti = tarfile.TarInfo("app/config.py")
                ti.size = len(payload)
                tf.addfile(ti, io.BytesIO(payload))
            with mock.patch.object(core.config_manager, "get_base_dir", return_value=tmp):
                self._reset_caches()
                self.assertEqual(core._get_bundled_backend_version(allow_remote=False), "1.2.7")

    def test_remote_manifest_fallback_and_negative_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(core.config_manager, "get_base_dir", return_value=tmp),
                mock.patch("urllib.request.urlopen", side_effect=OSError("network down")) as m_open,
            ):
                self._reset_caches()
                self.assertEqual(core._get_bundled_backend_version(cfg={}, allow_remote=True), "")
                self.assertEqual(m_open.call_count, 1)
                # Second call inside 60s cooldown must not block on network again.
                self.assertEqual(core._get_bundled_backend_version(cfg={}, allow_remote=True), "")
                self.assertEqual(m_open.call_count, 1)

            with (
                mock.patch.object(core.config_manager, "get_base_dir", return_value=tmp),
                mock.patch("urllib.request.urlopen", return_value=_FakeHttpResponse({"version": "1.2.5"})) as m_open_ok,
            ):
                self._reset_caches()
                self.assertEqual(core._get_bundled_backend_version(cfg={}, allow_remote=True), "1.2.5")
                self.assertEqual(m_open_ok.call_count, 1)
                self._reset_caches()
                self.assertEqual(core._get_bundled_backend_version(cfg={}, allow_remote=False), "")

    def test_url_normalization_and_wan_to_p2p_candidate_ordering(self):
        self.assertEqual(core._extract_host_from_url("192.168.1.50"), "192.168.1.50")
        self.assertEqual(core._extract_host_from_url("192.168.1.50:80"), "192.168.1.50")
        self.assertEqual(core._extract_host_from_url("https://zima.example.com/ui"), "zima.example.com")
        self.assertEqual(core._format_backend_url("::1", 8080), "http://[::1]:8080")

        cfg = {
            "active_server_id": "srv1",
            "servers": [
                {
                    "id": "srv1",
                    "name": "ZimaHome",
                    "easytier_virtual_ip": "10.126.126.1",
                    "connections": [
                        {"id": "c_wan", "url": "nas.example.com"},
                        {"id": "c_lan", "url": "192.168.1.40"},
                    ],
                }
            ],
        }
        with (
            mock.patch.object(core.config_manager, "resolve_target_connection", return_value=("nas.example.com", "WAN")),
            mock.patch.object(core.config_manager, "get_dynamic_remote_info", return_value={"ip": "10.126.126.1"}),
        ):
            candidates = core._get_backend_url_candidates(cfg, target_server_id="srv1")
            self.assertEqual(candidates[0], "http://10.126.126.1:8080")
            self.assertIn("http://192.168.1.40:8080", candidates)
            self.assertEqual(candidates[-1], "http://nas.example.com:8080")

    def test_health_failover_winerror_10054_retry_and_cache_rules(self):
        cfg = {
            "active_server_id": "srv1",
            "servers": [
                {
                    "id": "srv1",
                    "name": "Zima1",
                    "easytier_virtual_ip": "10.126.126.2",
                    "connections": [
                        {"id": "c_mdns", "url": "http://zimaos.local"},
                        {"id": "c_lan", "url": "192.168.1.55"},
                    ],
                },
                {
                    "id": "srv2",
                    "name": "Zima2",
                    "connections": [{"id": "c2", "url": "http://192.168.1.99"}],
                },
            ],
        }

        calls = []

        def fake_urlopen(req, timeout=2.0):
            calls.append(req.full_url)
            if "zimaos.local" in req.full_url:
                raise OSError("DNS lookup failed")
            if "192.168.1.55" in req.full_url:
                # Fail first hit with WinError 10054 reset semantics, then recover on retry/next call.
                if calls.count("http://192.168.1.55:8080/health") == 1:
                    raise ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")
                return _FakeHttpResponse({"status": "ok", "version": "1.2.3"})
            if "10.126.126.2" in req.full_url:
                return _FakeHttpResponse({"status": "ok", "version": "1.2.3"})
            return _FakeHttpResponse({"status": "ok", "version": "1.2.5"})

        with (
            mock.patch.object(core.config_manager, "resolve_target_connection", return_value=("http://zimaos.local", "LAN")),
            mock.patch.object(core.config_manager, "get_dynamic_remote_info", return_value={"ip": "10.126.126.2"}),
            mock.patch.object(core, "_get_bundled_backend_version", return_value="1.2.5"),
            mock.patch("urllib.request.urlopen", side_effect=fake_urlopen),
            mock.patch("time.sleep", return_value=None),
        ):
            info = core._get_backend_health_info(cfg=cfg, force=True, target_server_id="srv1")
            self.assertTrue(info["online"])
            self.assertEqual(info["version"], "1.2.3")
            self.assertEqual(info["latestVersion"], "1.2.5")
            self.assertIn(info["url"], ("http://192.168.1.55:8080", "http://10.126.126.2:8080"))

            # Switching server_id must not return srv1 cached response when force=False.
            info2 = core._get_backend_health_info(cfg=cfg, force=False, target_server_id="srv2")
            self.assertEqual(info2["version"], "1.2.5")
            self.assertEqual(info2["url"], "http://192.168.1.99:8080")

            # invalidate_active_route_cache must wipe backend caches.
            core.invalidate_active_route_cache()
            self.assertEqual(core._backend_url_cache, {})
            self.assertEqual(core._cached_backend_info["timestamp"], 0)

        # Offline status must NOT be cached across calls.
        state = {"up": False}

        def toggling_urlopen(req, timeout=2.0):
            if not state["up"]:
                raise ConnectionRefusedError("offline")
            return _FakeHttpResponse({"status": "ok", "version": "1.2.4"})

        with (
            mock.patch.object(core.config_manager, "resolve_target_connection", return_value=("http://192.168.1.77", "LAN")),
            mock.patch.object(core.config_manager, "get_dynamic_remote_info", return_value=None),
            mock.patch.object(core, "_get_bundled_backend_version", return_value="1.2.5"),
            mock.patch("urllib.request.urlopen", side_effect=toggling_urlopen),
            mock.patch("time.sleep", return_value=None),
        ):
            self._reset_caches()
            off_info = core._get_backend_health_info(cfg=cfg, force=False, target_server_id="srv1")
            self.assertFalse(off_info["online"])
            state["up"] = True
            on_info = core._get_backend_health_info(cfg=cfg, force=False, target_server_id="srv1")
            self.assertTrue(on_info["online"])
            self.assertEqual(on_info["version"], "1.2.4")

    def test_winerror_10054_direct_http_request_retry(self):
        attempts = {"count": 0}

        def flaky_open(req, timeout=2.0):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")
            return _FakeHttpResponse({"status": "ok", "version": "1.2.5"})

        with (
            mock.patch("urllib.request.urlopen", side_effect=flaky_open),
            mock.patch("time.sleep", return_value=None),
        ):
            ok, data, status = core._backend_http_request("http://127.0.0.1:8080/health", retries=1, timeout=1.0)
            self.assertTrue(ok)
            self.assertEqual(status, 200)
            self.assertEqual(data["version"], "1.2.5")
            self.assertEqual(attempts["count"], 2)

    def test_ota_semver_verification_allows_equal_or_newer_and_rejects_older(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "MyServer-Backend-ZimaOS.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.2.5"\n')

            cfg = {
                "active_server_id": "srv1",
                "servers": [{"id": "srv1", "name": "Zima1", "connections": [{"id": "c1", "url": "http://127.0.0.1"}]}],
            }

            for reported_ver, expected_ok in [("1.2.3", False), ("1.2.5", True), ("1.2.6", True)]:
                with (
                    mock.patch.object(core.config_manager, "load_or_create_config", return_value=cfg),
                    mock.patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]),
                    mock.patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"),
                    mock.patch.object(core, "_get_bundled_backend_version", return_value="1.2.5"),
                    mock.patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, None)),
                    mock.patch("urllib.request.urlopen", return_value=_FakeHttpResponse({"status": "success"})),
                    mock.patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": reported_ver}, 200)),
                    mock.patch("time.sleep", return_value=None),
                ):
                    res = core.handle_remote_backend_action({"action": "update", "serverId": "srv1"})
                    self.assertEqual(res["success"], expected_ok, f"Unexpected result for ver={reported_ver}: {res}")

    def test_live_loopback_http_health_request(self):
        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/health":
                    body = json.dumps({"status": "ok", "version": "1.2.3"}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                return

        with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as httpd:
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            try:
                ok, data, status = core._backend_http_request(f"http://127.0.0.1:{port}/health", timeout=2.0, retries=0)
                self.assertTrue(ok)
                self.assertEqual(status, 200)
                self.assertEqual(data, {"status": "ok", "version": "1.2.3"})
            finally:
                httpd.shutdown()

    def test_http_ota_waits_for_real_restart_boot_id_and_surfaces_rebuild_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "MyServer-Backend-ZimaOS.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.2.7"\n')

            cfg = {
                "active_server_id": "srv1",
                "servers": [{"id": "srv1", "name": "Zima1", "connections": [{"id": "c1", "url": "http://127.0.0.1"}]}],
            }
            sleep_calls = []
            poll_seq = [
                (True, {"status": "ok", "version": "1.2.6", "boot_id": "boot-old"}, 200),
                (False, {}, 0),
                (True, {"status": "ok", "version": "1.2.7", "boot_id": "boot-new"}, 200),
            ]

            with (
                mock.patch.object(core.config_manager, "load_or_create_config", return_value=cfg),
                mock.patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]),
                mock.patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"),
                mock.patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"),
                mock.patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, None)),
                mock.patch(
                    "urllib.request.urlopen",
                    return_value=_FakeHttpResponse({
                        "status": "success",
                        "boot_id": "boot-old",
                        "rebuild_required": True,
                    }),
                ),
                mock.patch.object(core, "_backend_http_request", side_effect=poll_seq),
                mock.patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)),
            ):
                res = core.handle_remote_backend_action({"action": "update", "serverId": "srv1"})

            self.assertTrue(res["success"])
            self.assertTrue(res["rebuildRecommended"])
            self.assertEqual(res["backend"]["version"], "1.2.7")
            self.assertGreaterEqual(len(sleep_calls), 3)
            self.assertEqual(sleep_calls[0], 2.5)

    def test_http_ota_never_fabricates_online_success_when_backend_stays_unreachable(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "MyServer-Backend-ZimaOS.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.2.7"\n')

            cfg = {
                "active_server_id": "srv1",
                "servers": [{"id": "srv1", "name": "Zima1", "connections": [{"id": "c1", "url": "http://127.0.0.1"}]}],
            }

            with (
                mock.patch.object(core.config_manager, "load_or_create_config", return_value=cfg),
                mock.patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]),
                mock.patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"),
                mock.patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"),
                mock.patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, None)),
                mock.patch("urllib.request.urlopen", return_value=_FakeHttpResponse({"status": "success", "boot_id": "boot-1"})),
                mock.patch.object(core, "_backend_http_request", return_value=(False, {}, 0)),
                mock.patch("time.sleep", return_value=None),
            ):
                res = core.handle_remote_backend_action({"action": "update", "serverId": "srv1"})

            self.assertFalse(res["success"])
            self.assertFalse(res["backend"]["online"])
            self.assertEqual(res["backend"]["version"], "")
            self.assertFalse(core._cached_backend_info["data"]["online"])

    def test_http_ota_unchanged_boot_id_rejects_without_ssh_and_falls_back_with_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "MyServer-Backend-ZimaOS.zip")
            tar_path = os.path.join(tmp, "MyServer-Backend-ZimaOS.tar.gz")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.2.7"\n')
            with tarfile.open(tar_path, "w:gz") as tf:
                info = tarfile.TarInfo("app/config.py")
                data = b'SERVER_VERSION = "1.2.7"\n'
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))

            cfg_no_ssh = {
                "active_server_id": "srv1",
                "servers": [{"id": "srv1", "name": "Zima1", "connections": [{"id": "c1", "url": "http://127.0.0.1"}]}],
            }
            with (
                mock.patch.object(core.config_manager, "load_or_create_config", return_value=cfg_no_ssh),
                mock.patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]),
                mock.patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"),
                mock.patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"),
                mock.patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, tar_path)),
                mock.patch("urllib.request.urlopen", return_value=_FakeHttpResponse({"status": "success", "boot_id": "boot-same"})),
                mock.patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.2.7", "boot_id": "boot-same"}, 200)),
                mock.patch("time.sleep", return_value=None),
            ):
                res_no_ssh = core.handle_remote_backend_action({"action": "update", "serverId": "srv1"})

            self.assertFalse(res_no_ssh["success"])
            self.assertIn("boot_id", res_no_ssh["message"])

            recorded_cmds = []

            class _FakeStream:
                def __init__(self, text=b"", exit_code=0):
                    self._text = text
                    self.channel = types.SimpleNamespace(recv_exit_status=lambda: exit_code)

                def read(self):
                    return self._text

            class _FakeSftp:
                def put(self, local_path, remote_path):
                    return None

                def close(self):
                    return None

            class _FakeSshClient:
                def set_missing_host_key_policy(self, policy):
                    return None

                def connect(self, *args, **kwargs):
                    return None

                def open_sftp(self):
                    return _FakeSftp()

                def exec_command(self, cmd, timeout=None):
                    recorded_cmds.append((cmd, timeout))
                    return None, _FakeStream(b"ok", 0), _FakeStream(b"", 0)

                def close(self):
                    return None

            fake_paramiko = types.SimpleNamespace(
                SSHClient=lambda: _FakeSshClient(),
                AutoAddPolicy=lambda: object(),
            )
            cfg_with_ssh = {
                "active_server_id": "srv1",
                "servers": [{
                    "id": "srv1",
                    "name": "Zima1",
                    "connections": [{"id": "c1", "url": "http://127.0.0.1"}],
                    "credentials": {"Admin": {"username": "algitha", "password": "secret"}},
                }],
            }
            poll_http_fail_then_ssh_ok = ([(False, {}, 0)] * 15) + [(True, {"status": "ok", "version": "1.2.7", "boot_id": "boot-ssh"}, 200)]

            with (
                mock.patch.dict(sys.modules, {"paramiko": fake_paramiko}),
                mock.patch.object(core.config_manager, "load_or_create_config", return_value=cfg_with_ssh),
                mock.patch.object(core.config_manager, "get_server_credentials", return_value={"username": "algitha", "password": "secret"}),
                mock.patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]),
                mock.patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"),
                mock.patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"),
                mock.patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, tar_path)),
                mock.patch("urllib.request.urlopen", return_value=_FakeHttpResponse({"status": "success", "boot_id": "boot-1"})),
                mock.patch.object(core, "_backend_http_request", side_effect=poll_http_fail_then_ssh_ok),
                mock.patch("time.sleep", return_value=None),
            ):
                res_ssh = core.handle_remote_backend_action({"action": "update", "serverId": "srv1"})

            self.assertTrue(res_ssh["success"])
            self.assertEqual(res_ssh["backend"]["version"], "1.2.7")
            install_cmds = [c for c in recorded_cmds if "install_zimaos.sh" in c[0]]
            self.assertEqual(len(install_cmds), 1)
            self.assertGreaterEqual(install_cmds[0][1], 180)

    def test_remote_github_backend_update_overrides_older_local_bundle(self):
        """Desktop must detect & install newer GitHub Backend (e.g. 1.4.1) even when local resources has 1.4.0."""
        with tempfile.TemporaryDirectory() as tmp:
            res_dir = os.path.join(tmp, "resources")
            os.makedirs(res_dir, exist_ok=True)
            with open(os.path.join(res_dir, "backend_manifest.json"), "w", encoding="utf-8") as f:
                json.dump({"version": "1.4.0", "package_zip": "MyServer-Backend-ZimaOS.zip", "package_tar": "MyServer-Backend-ZimaOS.tar.gz"}, f)

            old_zip = os.path.join(res_dir, "MyServer-Backend-ZimaOS.zip")
            with zipfile.ZipFile(old_zip, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.4.0"\n')

            old_tar = os.path.join(res_dir, "MyServer-Backend-ZimaOS.tar.gz")
            with tarfile.open(old_tar, "w:gz") as tf:
                d = b'SERVER_VERSION = "1.4.0"\n'
                ti = tarfile.TarInfo("app/config.py")
                ti.size = len(d)
                tf.addfile(ti, io.BytesIO(d))

            # Build real 1.4.1 remote ZIP & TAR payloads in memory
            buf_zip = io.BytesIO()
            with zipfile.ZipFile(buf_zip, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.4.1"\n')
            remote_zip_bytes = buf_zip.getvalue() * 4 if len(buf_zip.getvalue()) < 512 else buf_zip.getvalue()
            # Padded valid ZIP (>= 512 bytes) by adding dummy README
            buf_zip2 = io.BytesIO()
            with zipfile.ZipFile(buf_zip2, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.4.1"\n')
                zf.writestr("README.md", "MyServer Backend 1.4.1\n" * 40)
            remote_zip_bytes = buf_zip2.getvalue()

            buf_tar = io.BytesIO()
            with tarfile.open(fileobj=buf_tar, mode="w:gz") as tf:
                unique_blob = "".join(f"line_{i}_{hex(i * 7919)}\n" for i in range(120)).encode("utf-8")
                for fn, payload in [
                    ("app/config.py", b'SERVER_VERSION = "1.4.1"\n'),
                    ("README.md", unique_blob),
                ]:
                    ti = tarfile.TarInfo(fn)
                    ti.size = len(payload)
                    tf.addfile(ti, io.BytesIO(payload))
            remote_tar_bytes = buf_tar.getvalue()
            self.assertGreaterEqual(len(remote_tar_bytes), 512)

            class _BytesResp:
                def __init__(self, raw_bytes):
                    self._bio = io.BytesIO(raw_bytes)
                def read(self, n=-1):
                    return self._bio.read(n)
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False

            cfg = {
                "active_server_id": "srv1",
                "github_repo": "Gibranibang/My-Server-beta",
                "servers": [{
                    "id": "srv1",
                    "name": "Zima1",
                    "connections": [{"id": "c1", "url": "http://127.0.0.1"}],
                    "credentials": {"Admin": {"username": "nasadmin", "password": "pw"}},
                }],
            }

            manifest_141 = json.dumps({
                "version": "1.4.1",
                "package_zip": "MyServer-Backend-ZimaOS.zip",
                "package_tar": "MyServer-Backend-ZimaOS.tar.gz",
            }).encode("utf-8")

            # 1. Version check with local=1.4.0 & GitHub=1.4.1 must report latestVersion=1.4.1
            def _urlopen_detect(req, timeout=2.5):
                if "backend_manifest.json" in req.full_url:
                    return _BytesResp(manifest_141)
                raise AssertionError(f"Unexpected URL: {req.full_url}")

            with (
                mock.patch.object(core.config_manager, "get_base_dir", return_value=tmp),
                mock.patch("urllib.request.urlopen", side_effect=_urlopen_detect),
                mock.patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.4.0"}, 200)),
            ):
                self._reset_caches()
                info = core._get_backend_health_info(cfg=cfg, force=True, target_server_id="srv1")
            self.assertTrue(info["online"])
            self.assertEqual(info["version"], "1.4.0")
            self.assertEqual(info["latestVersion"], "1.4.1")

            # 2. If GitHub is older (1.3.9), local bundled 1.4.0 must still win cleanly
            manifest_139 = json.dumps({"version": "1.3.9"}).encode("utf-8")
            with (
                mock.patch.object(core.config_manager, "get_base_dir", return_value=tmp),
                mock.patch("urllib.request.urlopen", return_value=_BytesResp(manifest_139)),
            ):
                self._reset_caches()
                self.assertEqual(core._get_bundled_backend_version(cfg=cfg, allow_remote=True, force_remote=True), "1.4.0")

            # 3. handle_remote_backend_action(update, auto) must fetch 1.4.1 ZIP from GitHub & upload 1.4.1 (NOT stale 1.4.0)
            uploaded_payloads = []
            def _urlopen_ota(req, timeout=20):
                if req.full_url.endswith("/backend_manifest.json"):
                    return _BytesResp(manifest_141)
                if req.full_url.endswith("/MyServer-Backend-ZimaOS.zip"):
                    return _BytesResp(remote_zip_bytes)
                if req.full_url.endswith("/api/v1/system/update"):
                    uploaded_payloads.append(req.data)
                    return _FakeHttpResponse({"status": "success", "old_version": "1.4.0", "boot_id": "boot-old"})
                raise AssertionError(f"Unexpected URL: {req.full_url}")

            with (
                mock.patch.object(core.config_manager, "get_base_dir", return_value=tmp),
                mock.patch.object(core.config_manager, "load_or_create_config", return_value=cfg),
                mock.patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]),
                mock.patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"),
                mock.patch("urllib.request.urlopen", side_effect=_urlopen_ota),
                mock.patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.4.1", "boot_id": "boot-new"}, 200)),
                mock.patch("time.sleep", return_value=None),
            ):
                self._reset_caches()
                res = core.handle_remote_backend_action({"action": "update", "serverId": "srv1"})

            self.assertTrue(res["success"], res)
            self.assertEqual(res["backend"]["version"], "1.4.1")
            self.assertEqual(res["backend"]["latestVersion"], "1.4.1")
            self.assertEqual(len(uploaded_payloads), 1)
            self.assertIn(remote_zip_bytes, uploaded_payloads[0])

            # 4. SSH fallback when HTTP OTA fails & local bundle is stale 1.4.0 -> skips stale local 1.4.0, SFTP uploads remote 1.4.1 tarball (NOT 1.4.0)
            sftp_uploaded_versions = []
            ssh_cmds_recorded = []
            class _SftpCapture:
                def put(self, local_p, _remote_p):
                    sftp_uploaded_versions.append(core._extract_archive_backend_version(local_p))
                def close(self):
                    return None
            class _SshCapture:
                def set_missing_host_key_policy(self, _p):
                    return None
                def connect(self, *a, **kw):
                    return None
                def open_sftp(self):
                    return _SftpCapture()
                def exec_command(self, cmd, timeout=None):
                    ssh_cmds_recorded.append(cmd)
                    st = types.SimpleNamespace(recv_exit_status=lambda: 0)
                    out = b"50000\n" if "wc -c" in cmd else b"ok"
                    return None, types.SimpleNamespace(channel=st, read=lambda: out), types.SimpleNamespace(channel=st, read=lambda: b"")
                def close(self):
                    return None
            fake_p = types.SimpleNamespace(SSHClient=lambda: _SshCapture(), AutoAddPolicy=lambda: object())

            def _urlopen_ssh_fallback(req, timeout=20):
                if req.full_url.endswith("/backend_manifest.json"):
                    return _BytesResp(manifest_141)
                if req.full_url.endswith("/MyServer-Backend-ZimaOS.zip"):
                    raise OSError("zip blocked; test tar path")
                if req.full_url.endswith("/MyServer-Backend-ZimaOS.tar.gz"):
                    return _BytesResp(remote_tar_bytes)
                raise AssertionError(f"Unexpected URL: {req.full_url}")

            with (
                mock.patch.dict(sys.modules, {"paramiko": fake_p}),
                mock.patch.object(core.config_manager, "get_base_dir", return_value=tmp),
                mock.patch.object(core.config_manager, "load_or_create_config", return_value=cfg),
                mock.patch.object(core.config_manager, "get_server_credentials", return_value={"username": "nasadmin", "password": "pw"}),
                mock.patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]),
                mock.patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"),
                mock.patch("urllib.request.urlopen", side_effect=_urlopen_ssh_fallback),
                mock.patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.4.1", "boot_id": "boot-ssh-141"}, 200)),
                mock.patch("time.sleep", return_value=None),
            ):
                self._reset_caches()
                res_ssh = core.handle_remote_backend_action({"action": "update", "serverId": "srv1"})

            self.assertTrue(res_ssh["success"], res_ssh)
            self.assertEqual(sftp_uploaded_versions, ["1.4.1"])

            # 5. If both Desktop .zip & .tar.gz downloads fail when local is stale 1.4.0, skip stale SFTP & let NAS curl GitHub directly
            sftp_uploaded_versions.clear()
            ssh_cmds_recorded.clear()

            def _urlopen_nas_curl_only(req, timeout=20):
                if req.full_url.endswith("/backend_manifest.json"):
                    return _BytesResp(manifest_141)
                raise OSError("desktop direct download blocked")

            with (
                mock.patch.dict(sys.modules, {"paramiko": fake_p}),
                mock.patch.object(core.config_manager, "get_base_dir", return_value=tmp),
                mock.patch.object(core.config_manager, "load_or_create_config", return_value=cfg),
                mock.patch.object(core.config_manager, "get_server_credentials", return_value={"username": "nasadmin", "password": "pw"}),
                mock.patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]),
                mock.patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"),
                mock.patch("urllib.request.urlopen", side_effect=_urlopen_nas_curl_only),
                mock.patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.4.1", "boot_id": "boot-curl-141"}, 200)),
                mock.patch("time.sleep", return_value=None),
            ):
                self._reset_caches()
                res_curl = core.handle_remote_backend_action({"action": "update", "serverId": "srv1"})

            self.assertTrue(res_curl["success"], res_curl)
            self.assertEqual(sftp_uploaded_versions, [])
            self.assertTrue(any("curl " in c and "MyServer-Backend-ZimaOS.tar.gz" in c for c in ssh_cmds_recorded))

    def test_ssh_bounded_exec_drains_large_output_and_times_out_cleanly(self):
        class _DrainChannel:
            def __init__(self, chunks):
                self._chunks = list(chunks)
                self._idx = 0
                self.timeout_set = None
                self.closed = False

            def settimeout(self, t):
                self.timeout_set = t

            def exit_status_ready(self):
                return self._idx >= len(self._chunks)

            def recv_ready(self):
                return self._idx < len(self._chunks)

            def recv(self, _n):
                c = self._chunks[self._idx]
                self._idx += 1
                return c

            def recv_stderr_ready(self):
                return False

            def recv_exit_status(self):
                return 0

            def close(self):
                self.closed = True

        chan = _DrainChannel([b"line1\n", b"line2\n"])
        fake_client = types.SimpleNamespace(
            exec_command=lambda cmd, timeout=None: (None, types.SimpleNamespace(channel=chan), types.SimpleNamespace(channel=chan))
        )
        code, out_b, err_b = core._exec_ssh_command_bounded(fake_client, "echo ok", timeout=5.0)
        self.assertEqual(code, 0)
        self.assertEqual(out_b, b"line1\nline2\n")
        self.assertEqual(err_b, b"")
        self.assertEqual(chan.timeout_set, 5.0)

        # Verify hanging channel times out cleanly instead of blocking forever in recv_exit_status()
        class _HangingChannel:
            def __init__(self):
                self.closed = False
            def settimeout(self, _t):
                pass
            def exit_status_ready(self):
                return False
            def recv_ready(self):
                return False
            def recv_stderr_ready(self):
                return False
            def recv_exit_status(self):
                raise AssertionError("recv_exit_status must not be called before exit_status_ready")
            def close(self):
                self.closed = True

        hang_chan = _HangingChannel()
        hang_client = types.SimpleNamespace(
            exec_command=lambda cmd, timeout=None: (None, types.SimpleNamespace(channel=hang_chan), types.SimpleNamespace(channel=hang_chan))
        )
        with mock.patch("time.monotonic", side_effect=[0.0, 2.5]):
            with self.assertRaises(TimeoutError):
                core._exec_ssh_command_bounded(hang_client, "curl hang", timeout=1.0)
        self.assertTrue(hang_chan.closed)

    def test_ota_skips_upload_when_verify_jwt_unreachable_and_archive_download_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "MyServer-Backend-ZimaOS.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.4.4"\n')

            cfg = {
                "active_server_id": "srv1",
                "servers": [{
                    "id": "srv1",
                    "name": "Zima1",
                    "connections": [{"id": "c1", "url": "http://192.0.2.1"}],
                    "credentials": {"Admin": {"username": "nasadmin", "password": "pw"}},
                }],
            }
            seen_urls = []

            def _urlopen_unreachable(req, timeout=20):
                seen_urls.append(req.full_url)
                if req.full_url.endswith("/api/v1/auth/verify"):
                    raise TimeoutError("timed out")
                raise AssertionError(f"Should skip _send_ota_upload after verify TimeoutError, got {req.full_url}")

            with (
                mock.patch.object(core.config_manager, "load_or_create_config", return_value=cfg),
                mock.patch.object(core.config_manager, "get_server_credentials", return_value={"username": "nasadmin", "password": "pw"}),
                mock.patch.object(core, "_get_backend_url_candidates", return_value=["http://192.0.2.1:8080"]),
                mock.patch.object(core, "_get_active_server_backend_url", return_value="http://192.0.2.1:8080"),
                mock.patch.object(core, "_get_bundled_backend_version", return_value="1.4.4"),
                mock.patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, None)),
                mock.patch("urllib.request.urlopen", side_effect=_urlopen_unreachable),
                mock.patch.dict(sys.modules, {"paramiko": types.SimpleNamespace(SSHClient=lambda: types.SimpleNamespace(set_missing_host_key_policy=lambda *a: None, connect=lambda *a, **k: (_ for _ in ()).throw(OSError("no ssh"))), AutoAddPolicy=lambda: object())}),
            ):
                res = core.handle_remote_backend_action({"action": "update", "serverId": "srv1"})

            self.assertFalse(res["success"])
            self.assertEqual(seen_urls, ["http://192.0.2.1:8080/api/v1/auth/verify"])
            self.assertNotIn("srv1", core._ACTIVE_BACKEND_DEPLOYS)

            # Verify slow trickle download hits wall-clock deadline and cleans temp file
            class _SlowResp:
                def read(self, _n=-1):
                    return b"x" * 1024
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False

            with (
                mock.patch("urllib.request.urlopen", return_value=_SlowResp()),
                mock.patch("time.monotonic", side_effect=[0.0, 999.0]),
            ):
                dl_res = core._download_remote_backend_archive("Gibranibang/My-Server-beta", "MyServer-Backend-ZimaOS.zip", ".zip", timeout=1.0)
            self.assertIsNone(dl_res)

    def test_tauri_core_api_timeout_covers_installer_and_backend_deploy(self):
        lib_rs_path = os.path.join(BETA_DIR, "src-tauri", "src", "lib.rs")
        with open(lib_rs_path, "r", encoding="utf-8") as f:
            lib_src = f.read()
        self.assertIn("download_and_install_update", lib_src)
        self.assertIn("210000", lib_src)
        self.assertIn("420000", lib_src)


if __name__ == "__main__":
    unittest.main(verbosity=2)

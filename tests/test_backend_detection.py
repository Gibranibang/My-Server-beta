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
        self.assertEqual(core._get_bundled_backend_version(allow_remote=False), "1.2.6")
        zip_pkg, tar_pkg = core._get_bundled_backend_packages()
        self.assertIsNotNone(zip_pkg)
        self.assertIsNotNone(tar_pkg)
        self.assertTrue(os.path.isfile(zip_pkg))
        self.assertTrue(os.path.isfile(tar_pkg))
        self.assertEqual(os.path.basename(zip_pkg), "MyServer-Backend-ZimaOS.zip")
        self.assertEqual(os.path.basename(tar_pkg), "MyServer-Backend-ZimaOS.tar.gz")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)

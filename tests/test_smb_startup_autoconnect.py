import ctypes
import http.server
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch


def _install_linux_win_stubs():
    """Install minimal Windows stubs when running unit tests on Linux."""
    if not hasattr(ctypes, "windll"):
        class _DummyFunc:
            def __call__(self, *args, **kwargs):
                return 0

        class _DummyDll:
            def __getattr__(self, _name):
                return _DummyFunc()

        class _DummyWinDll:
            def __getattr__(self, _name):
                return _DummyDll()

        ctypes.windll = _DummyWinDll()

    if "winreg" not in sys.modules:
        winreg_stub = types.ModuleType("winreg")
        winreg_stub.HKEY_CURRENT_USER = 0x80000001
        winreg_stub.KEY_READ = 0x20019
        winreg_stub.KEY_WRITE = 0x20006
        winreg_stub.REG_SZ = 1
        winreg_stub.OpenKey = lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError())
        winreg_stub.QueryValueEx = lambda *_args, **_kwargs: ("", 1)
        winreg_stub.CreateKey = lambda *_args, **_kwargs: None
        winreg_stub.SetValueEx = lambda *_args, **_kwargs: None
        winreg_stub.CloseKey = lambda *_args, **_kwargs: None
        sys.modules["winreg"] = winreg_stub


_install_linux_win_stubs()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config_manager  # noqa: E402
import myserver_core_service as core  # noqa: E402
import smb_mount_manager  # noqa: E402


class _MockBackendServer:
    def __init__(self, initial_mode="zimaos", running=False):
        self.mode = initial_mode
        self.running = running
        self.status_calls = 0
        self.mode_calls = []

    def make_handler(self):
        state = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def _send(self, code, payload):
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/api/v1/smb/status":
                    state.status_calls += 1
                    self._send(200, {"mode": state.mode, "running": state.running})
                    return
                self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}") if length else {}
                if self.path == "/api/v1/smb/mode":
                    state.mode_calls.append(body)
                    state.mode = str(body.get("mode") or state.mode).lower()
                    state.running = True
                    self._send(200, {"success": True, "mode": state.mode, "running": True})
                    return
                self._send(404, {"error": "not found"})

        return _Handler


class TestSmbStartupAutoConnect(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._base_dir_patch = patch.object(config_manager, "get_base_dir", return_value=self._tmp.name)
        self._base_dir_patch.start()
        cfg = config_manager.load_or_create_config()
        cfg["active_server_id"] = "srv_1"
        cfg["auto_mount_smb"] = True
        cfg["servers"] = [
            {
                "id": "srv_1",
                "name": "HomeNAS",
                "active_connection": "c_lan",
                "connections": [{"id": "c_lan", "url": "http://192.168.1.50:80"}],
                "zerotier_virtual_ip": "",
                "easytier_virtual_ip": "10.126.126.1",
                "smb_source": "backend",
            }
        ]
        config_manager.save_server_smb_source_config(
            cfg,
            "srv_1",
            source="backend",
            username="alice",
            password="SecretPassword1!",
            role="admin",
            allowed_disks=["Media"],
            access_token="tok_backend_valid",
        )
        config_manager.save_config(cfg)

        core.clear_smb_mount_failure_cooldown()
        core._backend_url_cache.clear()
        core._last_mounted_server_id = None
        core._startup_auto_mount_attempted = False
        core._startup_auto_mount_inflight = False
        with core._smb_pipeline_gen_lock:
            core._smb_suppressed_until_ts = 0.0
        with core._state_lock:
            core._cached_state["is_online"] = True
        smb_mount_manager.invalidate_smb_host_cache()
        smb_mount_manager.clear_smb_share_cache()

    def tearDown(self):
        core.clear_smb_mount_failure_cooldown()
        core._backend_url_cache.clear()
        core._last_mounted_server_id = None
        core._startup_auto_mount_attempted = False
        core._startup_auto_mount_inflight = False
        self._base_dir_patch.stop()
        self._tmp.cleanup()

    def test_01_run_auto_mount_with_retry_bypasses_cooldown_and_switches_off_soft_mode(self):
        attempts = []

        def fake_mount_all(**_kw):
            attempts.append(len(attempts))
            if len(attempts) == 1:
                return (False, "Host SMB server tidak dapat dijangkau di port 445.")
            return (True, "Berhasil memasang 1 dari 1 partisi disk")

        with patch.object(core, "get_active_resolved_route", return_value=("http://192.168.1.50:80", "LAN")), \
             patch.object(core, "_get_active_server_backend_url", return_value="http://192.168.1.50:8080"), \
             patch.object(smb_mount_manager, "resolve_smb_host", return_value="192.168.1.50"), \
             patch.object(smb_mount_manager, "mount_all_smb_shares", side_effect=fake_mount_all), \
             patch.object(smb_mount_manager, "invalidate_smb_host_cache") as mock_inv_host, \
             patch.object(smb_mount_manager, "clear_smb_share_cache") as mock_clr_share, \
             patch.object(core, "_unmount_myserver_smb_drives", return_value=0) as mock_unmount, \
             patch.object(smb_mount_manager, "purge_smb_sessions") as mock_purge, \
             patch.object(core, "_scan_live_drives_now", return_value=[]), \
             patch.object(core.time, "sleep", return_value=None):
            res = core.run_auto_mount_with_retry("startup_auto")

        self.assertTrue(res[0])
        self.assertEqual(len(attempts), 2)
        self.assertGreaterEqual(mock_inv_host.call_count, 1)
        self.assertGreaterEqual(mock_clr_share.call_count, 2)
        # Attempt 0 uses soft_mode (foreign only), attempt 1 disables soft_mode and performs full unmount + purge
        unmount_reasons = [c.kwargs.get("reason") for c in mock_unmount.call_args_list]
        self.assertIn("pipeline:startup_auto:foreign", unmount_reasons)
        self.assertIn("pipeline:startup_auto", unmount_reasons)
        self.assertGreaterEqual(mock_purge.call_count, 1)
        self.assertFalse(core._startup_auto_mount_inflight)

    def test_02_backend_url_falls_back_to_reachable_resolved_smb_host(self):
        def fake_is_port_open(host, port=445, timeout=1.0):
            if host == "10.126.126.1" and int(port) == 8080:
                return False
            if host == "192.168.1.50" and int(port) == 8080:
                return True
            return True

        with patch.object(core, "get_active_resolved_route", return_value=("http://192.168.1.50:80", "LAN")), \
             patch.object(core, "_get_active_server_backend_url", return_value="http://10.126.126.1:8080"), \
             patch.object(smb_mount_manager, "resolve_smb_host", return_value="192.168.1.50"), \
             patch.object(smb_mount_manager, "is_port_open", side_effect=fake_is_port_open), \
             patch.object(smb_mount_manager, "mount_all_smb_shares", return_value=(True, "ok")) as mock_mount, \
             patch.object(core, "_unmount_myserver_smb_drives", return_value=0), \
             patch.object(core, "_scan_live_drives_now", return_value=[]), \
             patch.object(core.time, "sleep", return_value=None):
            res = core.rebind_storage_pipeline("startup_auto")

        self.assertTrue(res[0])
        self.assertEqual(mock_mount.call_args.kwargs.get("backend_url"), "http://192.168.1.50:8080")

    def test_03_backend_smb_mode_self_heals_when_initial_startup_mount_fails(self):
        state = _MockBackendServer(initial_mode="zimaos", running=False)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), state.make_handler())
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            backend_url = f"http://127.0.0.1:{port}"
            mount_calls = []

            def fake_mount_all(**_kw):
                mount_calls.append(state.mode)
                if state.mode == "backend" and state.running:
                    return (True, "Mounted backend shares")
                return (False, "System error 1326 / backend smbd off")

            with patch.object(core, "get_active_resolved_route", return_value=("http://127.0.0.1:80", "LAN")), \
                 patch.object(core, "_get_active_server_backend_url", return_value=backend_url), \
                 patch.object(smb_mount_manager, "resolve_smb_host", return_value="127.0.0.1"), \
                 patch.object(smb_mount_manager, "is_port_open", return_value=True), \
                 patch.object(smb_mount_manager, "mount_all_smb_shares", side_effect=fake_mount_all), \
                 patch.object(smb_mount_manager, "purge_smb_sessions") as mock_purge, \
                 patch.object(core, "_unmount_myserver_smb_drives", return_value=0), \
                 patch.object(core, "_scan_live_drives_now", return_value=[]), \
                 patch.object(core.time, "sleep", return_value=None):
                res = core.rebind_storage_pipeline("startup_auto")

            self.assertTrue(res[0])
            self.assertEqual(mount_calls, ["zimaos", "backend"])
            self.assertEqual(state.status_calls, 1)
            self.assertEqual(len(state.mode_calls), 1)
            self.assertEqual(state.mode_calls[0].get("mode"), "backend")
            self.assertGreaterEqual(mock_purge.call_count, 1)
            self.assertFalse(core._is_smb_mount_in_cooldown("srv_1"))
        finally:
            server.shutdown()
            server.server_close()

    def test_04_easytier_autostart_clears_cooldown_and_deferred_startup_mount_recovers(self):
        cfg = config_manager.load_or_create_config()
        cfg["easytier"] = {
            "enabled": True,
            "remote_id": "net-1",
            "network_name": "myserver-net",
            "network_secret": "secret",
            "ipv4": "10.126.126.2",
            "peers": [],
        }
        config_manager.save_config(cfg)

        core._record_smb_mount_outcome("srv_1", False)
        self.assertTrue(core._is_smb_mount_in_cooldown("srv_1"))

        fake_mgr = types.SimpleNamespace(start_easytier=lambda **_kw: None)
        with patch.object(core.time, "sleep", return_value=None), \
             patch.object(core.easytier_manager, "get_easytier_manager", return_value=fake_mgr), \
             patch.object(smb_mount_manager, "invalidate_smb_host_cache") as mock_inv:
            core.auto_start_easytier_worker()

        self.assertFalse(core._is_smb_mount_in_cooldown("srv_1"))
        mock_inv.assert_called()

        # Deferred startup recovery triggers when _startup_auto_mount_attempted=True and _last_mounted_server_id != srv_1
        srv = config_manager.load_or_create_config()["servers"][0]
        core._startup_auto_mount_attempted = True
        core._startup_auto_mount_inflight = False
        core._last_mounted_server_id = None
        triggered = []

        def fake_retry(reason):
            triggered.append(reason)
            core._last_mounted_server_id = "srv_1"
            return (True, "ok")

        with patch.object(smb_mount_manager, "resolve_smb_host", return_value="10.126.126.1"), \
             patch.object(core, "run_auto_mount_with_retry", side_effect=fake_retry):
            did_run = core._maybe_trigger_deferred_startup_smb_mount(
                srv, "http://10.126.126.1:80", auto_mount_enabled=True, is_online=True, spawn_async=False
            )
            self.assertTrue(did_run)
            self.assertEqual(triggered, ["startup_auto"])

            # Once mounted (_last_mounted_server_id == srv_1), subsequent ticks must not re-trigger
            did_run_again = core._maybe_trigger_deferred_startup_smb_mount(
                srv, "http://10.126.126.1:80", auto_mount_enabled=True, is_online=True, spawn_async=False
            )
            self.assertFalse(did_run_again)
            self.assertEqual(triggered, ["startup_auto"])

    def test_05_switch_server_clears_backend_http_pool_and_jwt_url_caches(self):
        import io

        cfg = config_manager.load_or_create_config()
        cfg["servers"].append({
            "id": "srv_2",
            "name": "OfficeNAS",
            "active_connection": "c_et",
            "connections": [{"id": "c_et", "url": "http://10.126.126.1:80"}],
            "easytier_virtual_ip": "10.126.126.1",
            "smb_source": "backend",
        })
        config_manager.save_server_smb_source_config(
            cfg,
            "srv_2",
            source="backend",
            username="bob",
            password="BobSecretPassword1!",
            role="user",
            allowed_disks=["Docs"],
            access_token="tok_srv2",
        )
        config_manager.save_config(cfg)

        closed_flags = []

        class _DummyConn:
            def close(self):
                closed_flags.append(True)

        with core._BACKEND_HTTP_POOL_LOCK:
            core._BACKEND_HTTP_POOL[("http", "10.126.126.1:8080")] = {"conn": _DummyConn(), "ts": 100.0}
        core._backend_url_cache["srv_1"] = ("http://10.126.126.1:8080", 9999999999.0)
        with core._BACKEND_JWT_CACHE_LOCK:
            core._BACKEND_JWT_CACHE[("srv_1", "http://10.126.126.1:8080", "default")] = {"token": "tok_old", "fail_until": 0.0}

        payload = json.dumps({"serverId": "srv_2"}).encode("utf-8")
        handler = core.CoreApiHandler.__new__(core.CoreApiHandler)
        handler.path = "/api/switch_server"
        handler.rfile = io.BytesIO(payload)
        handler.headers = {
            "Content-Length": str(len(payload)),
            "X-MyServer-Core-Token": core.get_core_auth_token(),
        }
        sent = {}
        handler._send_json = lambda obj, code=200: sent.update({"obj": obj, "code": code})

        class _NoopThread:
            def __init__(self, target=None, daemon=None, **kw):
                pass

            def start(self):
                pass

        with patch.object(core, "get_server_details_data", return_value={"activeServerId": "srv_2"}), \
             patch.object(core, "invalidate_active_route_cache"), \
             patch.object(core.threading, "Thread", _NoopThread):
            handler.do_POST()

        self.assertEqual(sent.get("code"), 200)
        self.assertTrue(closed_flags)
        with core._BACKEND_HTTP_POOL_LOCK:
            self.assertEqual(core._BACKEND_HTTP_POOL, {})
        self.assertEqual(core._backend_url_cache, {})
        with core._BACKEND_JWT_CACHE_LOCK:
            self.assertEqual(core._BACKEND_JWT_CACHE, {})

    def test_06_get_smb_source_skips_backend_probe_during_switch_server_sync(self):
        with core._state_lock:
            core._cached_state["smb_syncing"] = True
            core._cached_state["smb_sync_reason"] = "switch_server"
        try:
            with patch.object(core, "_get_active_server_backend_url", return_value="http://10.126.126.1:8080"), \
                 patch.object(core, "_backend_http_request", side_effect=AssertionError("Must not probe backend during switch_server")), \
                 patch.object(core, "_backend_authenticated_request", side_effect=AssertionError("Must not auth-probe backend during switch_server")), \
                 patch.object(core, "get_live_drives_list", return_value=[]):
                code, res = core._handle_smb_source_request({"action": "get"})

            self.assertEqual(code, 200)
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("source"), "backend")
            self.assertTrue(res.get("hasCredentials"))
            self.assertFalse(res.get("needsAuth"))
        finally:
            with core._state_lock:
                core._cached_state["smb_syncing"] = False
                core._cached_state["smb_sync_reason"] = ""


if __name__ == "__main__":
    unittest.main()

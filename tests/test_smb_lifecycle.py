import ast
import ctypes
import http.server
import json
import os
import sys
import tempfile
import threading
import types
import unittest
import urllib.request
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


class _StopMetricsLoop(BaseException):
    pass


class TestSmbLifecycleTask1(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None
        smb_mount_manager.invalidate_smb_host_cache()
        smb_mount_manager.clear_smb_share_cache()

        cfg = config_manager.get_default_config()
        cfg["auto_mount_smb"] = True
        cfg["servers"] = [
            {
                "id": "srv_1",
                "name": "HomeNAS",
                "active_connection": "auto",
                "zerotier_virtual_ip": "10.147.20.9",
                "easytier_virtual_ip": "10.126.126.1",
                "connections": [
                    {"id": "c_lan", "url": "http://192.168.1.50:80", "label": "LAN"},
                    {"id": "c_dom", "url": "https://nas.example.com", "label": "Domain"},
                ],
                "profiles_credentials": {
                    "Admin": {
                        "username": "zima",
                        "password": config_manager.encrypt_credential("pw"),
                    }
                },
                "profiles": ["Admin"],
                "active_profile": "Admin",
            }
        ]
        cfg["active_server_id"] = "srv_1"
        config_manager.save_config(cfg)

        with core._auto_route_smb_lock:
            core._auto_route_smb_tracker.update({
                "server_id": None,
                "mounted_host": "",
                "pending_host": "",
                "pending_since_ts": 0.0,
            })
        with core._shutdown_daemons_lock:
            core._shutdown_daemons_done = False
        with core._power_resume_lock:
            core._last_power_resume_ts = 0.0

        self.core_srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), core.CoreApiHandler)
        self.core_port = self.core_srv.server_port
        self.core_thread = threading.Thread(target=self.core_srv.serve_forever, daemon=True)
        self.core_thread.start()

    def tearDown(self):
        self.core_srv.shutdown()
        self.core_srv.server_close()
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()

    def _post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.core_port}{path}",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(data)),
                "X-MyServer-Core-Token": core.get_core_auth_token(),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_01_auto_and_domain_route_smb_transition_debounce_and_metrics_url_tracking(self):
        """SMBS-01 / D-01: Debounce >=5s anti-flapping, auto & Domain LAN<->VPN transitions, and last_resolved_url tracking."""
        # A. Pure transition evaluator with 5s debounce & flap immunity
        self.assertEqual(core._evaluate_auto_route_smb_transition("srv_1", "192.168.1.50", now_ts=10.0), (False, ""))
        self.assertEqual(core._evaluate_auto_route_smb_transition("srv_1", "10.126.126.1", now_ts=11.0), (False, ""))
        self.assertEqual(core._evaluate_auto_route_smb_transition("srv_1", "10.126.126.1", now_ts=14.0), (False, ""))
        # Flap back to LAN resets pending
        self.assertEqual(core._evaluate_auto_route_smb_transition("srv_1", "192.168.1.50", now_ts=15.0), (False, ""))
        self.assertEqual(core._evaluate_auto_route_smb_transition("srv_1", "10.126.126.1", now_ts=16.0), (False, ""))
        self.assertEqual(core._evaluate_auto_route_smb_transition("srv_1", "10.126.126.1", now_ts=21.0), (True, "10.126.126.1"))
        # Server switch resets cleanly
        self.assertEqual(core._evaluate_auto_route_smb_transition("srv_2", "192.168.2.10", now_ts=22.0), (False, ""))

        # B. Explicit Domain route LAN <-> VPN effective host transition triggers rebind
        with core._auto_route_smb_lock:
            core._auto_route_smb_tracker.update({
                "server_id": "srv_1",
                "mounted_host": "192.168.1.50",
                "pending_host": "",
                "pending_since_ts": 0.0,
            })
        srv = config_manager.load_or_create_config()["servers"][0]
        srv["active_connection"] = "c_dom"
        rebind_reasons = []
        with patch.object(smb_mount_manager, "resolve_smb_host", return_value="10.126.126.1"), \
             patch.object(core, "rebind_storage_pipeline", side_effect=lambda r="manual": rebind_reasons.append(r)):
            self.assertEqual(
                core._check_effective_smb_host_transition_for_server(
                    srv, "https://nas.example.com", auto_mount_enabled=True, is_online=True, now_ts=100.0, spawn_async=False
                ),
                (False, ""),
            )
            self.assertEqual(
                core._check_effective_smb_host_transition_for_server(
                    srv, "https://nas.example.com", auto_mount_enabled=True, is_online=True, now_ts=105.5, spawn_async=False
                ),
                (True, "10.126.126.1"),
            )
        self.assertEqual(rebind_reasons, ["auto_route_changed"])

        # C. update_metrics_loop tracks last_resolved_url so auto-route URL switch resets held_online & invalidates cache
        routes = [("http://192.168.1.50:80", "LAN"), ("http://10.126.126.1:80", "EasyTier"), ("http://10.126.126.1:80", "EasyTier")]
        route_iter = iter(routes)
        sleep_calls = [0]

        def fake_sleep(_sec):
            sleep_calls[0] += 1
            if sleep_calls[0] >= 2:
                raise _StopMetricsLoop()

        fake_client = types.SimpleNamespace(fetch_metrics=lambda: {"is_online": True, "cpu": 10.0, "ram": 20.0, "disk": 30.0})
        inv_calls = []
        with patch.object(core, "get_active_resolved_route", side_effect=lambda *_a, **_kw: next(route_iter)), \
             patch.object(core, "get_cached_metrics_client", return_value=fake_client), \
             patch.object(smb_mount_manager, "invalidate_smb_host_cache", side_effect=lambda: inv_calls.append("inv")), \
             patch.object(core, "_check_effective_smb_host_transition_for_server"), \
             patch.object(core.time, "sleep", side_effect=fake_sleep):
            with self.assertRaises(_StopMetricsLoop):
                core.update_metrics_loop()
        self.assertGreaterEqual(len(inv_calls), 1)

    def test_02_unmount_strictly_before_easytier_stop_and_idempotent_shutdown(self):
        """SMBS-01 / SMBS-02 / D-03 / D-05.2 / T-07-08: unmount_all_smb_shares(allowed_hosts=...) runs before EasyTier stop across all paths."""
        timeline = []
        seen_allowlists = []

        def fake_unmount(allowed_hosts=None, allowed_prefixes=None):
            timeline.append("unmount")
            seen_allowlists.append((set(allowed_hosts or ()), tuple(allowed_prefixes or ())))
            return 1

        fake_et_mgr = types.SimpleNamespace(
            stop=lambda: timeline.append("et_stop"),
            stop_easytier=lambda: (timeline.append("et_stop_easytier") or (True, "stopped")),
            get_status_overview=lambda: {"running": False},
        )
        fake_st = types.SimpleNamespace(stop=lambda **_kw: timeline.append("st_stop"))

        with patch.object(smb_mount_manager, "unmount_all_smb_shares", side_effect=fake_unmount), \
             patch.object(smb_mount_manager, "invalidate_smb_host_cache"), \
             patch.object(core.easytier_manager, "get_easytier_manager", return_value=fake_et_mgr), \
             patch.object(core, "_local_st_daemon", fake_st):
            core.shutdown_background_daemons()
            core.shutdown_background_daemons()  # idempotent 2nd call

        self.assertEqual(timeline, ["unmount", "et_stop", "st_stop"])
        hosts_arg, prefixes_arg = seen_allowlists[0]
        self.assertIn("192.168.1.50", hosts_arg)
        self.assertNotIn("corp-nas", hosts_arg)
        self.assertEqual(prefixes_arg, ("10.126.126.",))

        # /api/easytier/stop unmounts BEFORE stop_easytier
        timeline.clear()
        with patch.object(smb_mount_manager, "unmount_all_smb_shares", side_effect=fake_unmount), \
             patch.object(smb_mount_manager, "invalidate_smb_host_cache"), \
             patch.object(core.easytier_manager, "get_easytier_manager", return_value=fake_et_mgr), \
             patch.object(core, "refresh_drives_cache_immediately"):
            st, body = self._post("/api/easytier/stop", {})
        self.assertEqual(st, 200)
        self.assertTrue(body["success"])
        self.assertEqual(timeline, ["unmount", "et_stop_easytier"])

        # /api/set_remote_mode unmounts scoped MyServer hosts and spawns rebind when mode changes
        timeline.clear()
        rebind_reasons = []
        with patch.object(smb_mount_manager, "unmount_all_smb_shares", side_effect=fake_unmount), \
             patch.object(smb_mount_manager, "invalidate_smb_host_cache"), \
             patch.object(core, "rebind_storage_pipeline", side_effect=lambda r="manual": rebind_reasons.append(r)):
            st_rm, body_rm = self._post("/api/set_remote_mode", {"mode": "zerotier"})
            threading.Event().wait(0.05)
        self.assertEqual(st_rm, 200)
        self.assertEqual(body_rm["remote_mode"], "zerotier")
        self.assertIn("unmount", timeline)
        self.assertEqual(rebind_reasons, ["remote_mode_changed"])

    def test_03_power_suspend_resume_dedup_nic_change_and_win32_loop_ast(self):
        """SMBS-01 / D-04: WM_POWERBROADCAST suspend/resume dedup, NotifyAddrChange helper, and AST safety for 64-bit hidden window."""
        unmount_reasons = []
        rebind_reasons = []

        with patch.object(core, "_unmount_myserver_smb_drives", side_effect=lambda reason="lifecycle", **_kw: unmount_reasons.append(reason) or 1), \
             patch.object(smb_mount_manager, "invalidate_smb_host_cache") as mock_inv, \
             patch.object(core, "rebind_storage_pipeline", side_effect=lambda r="manual": rebind_reasons.append(r)):
            self.assertEqual(core._handle_windows_power_event(core.PBT_APMSUSPEND), "suspended")
            self.assertEqual(unmount_reasons, ["power_suspend"])
            mock_inv.assert_called()

            res1 = core._handle_windows_power_event(core.PBT_APMRESUMEAUTOMATIC, now_ts=500.0, spawn_async=False)
            res2 = core._handle_windows_power_event(core.PBT_APMRESUMESUSPEND, now_ts=501.0, spawn_async=False)
            self.assertEqual(res1, "resume_scheduled")
            self.assertEqual(res2, "resume_deduped")
            self.assertEqual(rebind_reasons, ["power_resume"])

        # Network change handler
        with patch.object(smb_mount_manager, "invalidate_smb_host_cache") as mock_inv:
            self.assertFalse(core._handle_local_network_change(["192.168.1.10"], ["192.168.1.10"]))
            mock_inv.assert_not_called()
            self.assertTrue(core._handle_local_network_change(["192.168.1.10"], ["10.0.0.5"]))
            mock_inv.assert_called_once()

        # AST check on windows_power_monitor_loop: hidden top-level window (never -3), 64-bit argtypes/restype, RegisterSuspendResumeNotification
        src_path = os.path.join(REPO_ROOT, "myserver_core_service.py")
        with open(src_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        pwr_fn = fns["windows_power_monitor_loop"]
        consts = {n.value for n in ast.walk(pwr_fn) if isinstance(n, ast.Constant)}
        names = {n.id for n in ast.walk(pwr_fn) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(pwr_fn) if isinstance(n, ast.Attribute)}
        self.assertNotIn(-3, consts)
        self.assertNotIn("HWND_MESSAGE", names)
        self.assertIn("argtypes", attrs)
        self.assertIn("restype", attrs)
        self.assertIn("CreateWindowExW", attrs)
        self.assertTrue(
            any(isinstance(n, ast.Constant) and n.value == "RegisterSuspendResumeNotification" for n in ast.walk(pwr_fn))
        )

    def test_04_offline_streak_5_tick_threshold_and_single_unmount(self):
        """SMBS-01 / D-04: Offline streak tolerates 1..4 ticks, triggers once at tick 5, skips 6+, resets on recovery."""
        for streak in range(1, 5):
            self.assertFalse(core._should_unmount_on_offline_streak(False, streak, False))
        self.assertTrue(core._should_unmount_on_offline_streak(False, 5, False))
        self.assertFalse(core._should_unmount_on_offline_streak(False, 5, False, smb_port_alive=True))
        self.assertFalse(core._should_unmount_on_offline_streak(False, 6, True))
        self.assertFalse(core._should_unmount_on_offline_streak(True, 5, False))


class TestSmbLifecycleTask2(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None
        smb_mount_manager.invalidate_smb_host_cache()
        smb_mount_manager.clear_smb_share_cache()
        with core._backend_disks_usage_lock:
            core._cached_backend_disks_usage.clear()

        cfg = config_manager.get_default_config()
        cfg["auto_mount_smb"] = True
        cfg["servers"] = [
            {
                "id": "srv_1",
                "name": "HomeNAS",
                "active_connection": "c_lan",
                "zerotier_virtual_ip": "10.147.20.9",
                "easytier_virtual_ip": "10.126.126.1",
                "connections": [{"id": "c_lan", "url": "http://192.168.1.50:80", "label": "LAN"}],
                "profiles_credentials": {
                    "Admin": {"username": "zima", "password": config_manager.encrypt_credential("pw")}
                },
                "profiles": ["Admin"],
                "active_profile": "Admin",
            }
        ]
        cfg["active_server_id"] = "srv_1"
        config_manager.save_config(cfg)

        self.core_srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), core.CoreApiHandler)
        self.core_port = self.core_srv.server_port
        self.core_thread = threading.Thread(target=self.core_srv.serve_forever, daemon=True)
        self.core_thread.start()

    def tearDown(self):
        self.core_srv.shutdown()
        self.core_srv.server_close()
        with core._backend_disks_usage_lock:
            core._cached_backend_disks_usage.clear()
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()

    def _post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.core_port}{path}",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(data)),
                "X-MyServer-Core-Token": core.get_core_auth_token(),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_01_scan_live_drives_now_uses_rest_cache_no_getdiskfreespace_and_recognizes_1219_alias(self):
        """SMBS-03 / SMBS-02 / D-06.1 / D-05.4: Backend capacity comes from REST cache, never GetDiskFreeSpaceExW, and 1219 alias drives stay visible."""
        cfg = config_manager.load_or_create_config()
        config_manager.save_server_smb_source_config(
            cfg, "srv_1", source="backend", username="u1", password="p1", role="user", allowed_disks=["Media"]
        )
        core._update_backend_disks_usage_cache(
            "srv_1",
            [{"name": "Media", "total_bytes": 2_000_000_000, "free_bytes": 500_000_000}],
        )

        class FakeK32:
            @staticmethod
            def GetLogicalDrives():
                return 1 << 25  # Z:

            @staticmethod
            def GetDriveTypeW(_p):
                return 4

            @staticmethod
            def GetDiskFreeSpaceExW(*_args, **_kwargs):
                raise AssertionError("GetDiskFreeSpaceExW must NEVER be called")

        class FakeMpr:
            @staticmethod
            def WNetGetConnectionW(_d, buf, _sz):
                buf.value = r"\\192.168.1.51\Media"  # Error-1219 alias host!
                return 0

        fake_windll = types.SimpleNamespace(kernel32=FakeK32(), mpr=FakeMpr(), iphlpapi=ctypes.windll.iphlpapi)
        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core.ctypes, "windll", fake_windll), \
             patch.object(smb_mount_manager, "get_active_1219_aliases", return_value={"192.168.1.50": "192.168.1.51"}):
            drives = core._scan_live_drives_now()

        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]["letter"], "Z")
        self.assertEqual(drives[0]["name"], "Media")
        self.assertEqual(drives[0]["total"], core.format_bytes_size(2_000_000_000))
        self.assertEqual(drives[0]["free"], core.format_bytes_size(500_000_000))
        self.assertEqual(drives[0]["usedPct"], 75)
        self.assertTrue(drives[0]["mounted"])

        # AST check: zero GetDiskFreeSpaceExW inside _scan_live_drives_now
        with open(os.path.join(REPO_ROOT, "myserver_core_service.py"), "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        scan_attrs = {n.attr for n in ast.walk(fns["_scan_live_drives_now"]) if isinstance(n, ast.Attribute)}
        self.assertNotIn("GetDiskFreeSpaceExW", scan_attrs)

    def test_02_client_first_smb_source_switch_order_and_401_no_teardown(self):
        """SMBS-04 / D-08.1: Client unmount+purge run strictly BEFORE POST /api/v1/smb/mode and pre_unmounted=True prevents double purge; 401 aborts zero-teardown."""
        timeline = []

        # Case A: 401 before unmount -> zero teardown calls
        with patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
             patch.object(core, "_verify_backend_account", return_value=(401, {"error": "Bad creds"})), \
             patch.object(smb_mount_manager, "unmount_all_smb_shares", side_effect=lambda **_kw: timeline.append("unmount") or 0), \
             patch.object(smb_mount_manager, "purge_smb_sessions", side_effect=lambda *_a, **_kw: timeline.append("purge")):
            code_401, res_401 = core._handle_smb_source_request({
                "action": "set", "source": "backend", "username": "u1", "password": "bad"
            })
        self.assertEqual(code_401, 401)
        self.assertFalse(res_401["success"])
        self.assertEqual(timeline, [])

        # Case B: Stored creds 401 pre-check aborts zero-teardown
        cfg = config_manager.load_or_create_config()
        config_manager.save_server_smb_source_config(
            cfg, "srv_1", source="zimaos", username="u1", password="p1", role="user", allowed_disks=["Media"], access_token="expired"
        )
        with patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
             patch.object(core, "_backend_authenticated_request", return_value=(401, {"needsAuth": True, "error": "Expired"}, "")), \
             patch.object(smb_mount_manager, "unmount_all_smb_shares", side_effect=lambda **_kw: timeline.append("unmount") or 0), \
             patch.object(smb_mount_manager, "purge_smb_sessions", side_effect=lambda *_a, **_kw: timeline.append("purge")):
            code_st_401, _ = core._handle_smb_source_request({"action": "set", "source": "backend"})
        self.assertEqual(code_st_401, 401)
        self.assertEqual(timeline, [])

        # Case C: Successful zimaos -> backend client-first order: [unmount, purge, POST /api/v1/smb/mode, rebind(pre_unmounted=True)]
        timeline.clear()

        def fake_http(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/smb/mode"):
                timeline.append("post_mode_backend")
                return True, {"mode": "backend"}, 200
            if url.endswith("/api/v1/storage/disks"):
                return True, {"disks": [{"name": "Media", "total_bytes": 1000, "free_bytes": 500}]}, 200
            return False, {}, 404

        with patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
             patch.object(core, "_verify_backend_account", return_value=(200, {"access_token": "tok1", "role": "user", "allowed_disks": ["Media"]})), \
             patch.object(core, "_backend_http_request", side_effect=fake_http), \
             patch.object(smb_mount_manager, "unmount_all_smb_shares", side_effect=lambda **_kw: timeline.append("unmount") or 1), \
             patch.object(smb_mount_manager, "purge_smb_sessions", side_effect=lambda *_a, **_kw: timeline.append("purge")), \
             patch.object(core, "rebind_storage_pipeline", side_effect=lambda r="manual", pre_unmounted=False: timeline.append(f"rebind:{pre_unmounted}") or []) as _mock_reb, \
             patch.object(core.time, "sleep"):
            code_ok, res_ok = core._handle_smb_source_request({
                "action": "set", "source": "backend", "username": "u1", "password": "p1"
            })
        self.assertEqual(code_ok, 200)
        self.assertTrue(res_ok["success"])
        self.assertEqual(timeline, ["unmount", "purge", "post_mode_backend", "rebind:True"])

        # Case D: Successful backend -> zimaos client-first order: [unmount, purge, POST /api/v1/smb/mode, rebind:True]
        timeline.clear()

        def fake_auth_req(_base, ep, _cfg, _sid, method="GET", json_body=None):
            if ep == "/api/v1/smb/mode":
                timeline.append("post_mode_zimaos")
                return 200, {"mode": "zimaos"}, "tok1"
            return 200, {}, "tok1"

        with patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
             patch.object(core, "_backend_authenticated_request", side_effect=fake_auth_req), \
             patch.object(smb_mount_manager, "unmount_all_smb_shares", side_effect=lambda **_kw: timeline.append("unmount") or 1), \
             patch.object(smb_mount_manager, "purge_smb_sessions", side_effect=lambda *_a, **_kw: timeline.append("purge")), \
             patch.object(core, "rebind_storage_pipeline", side_effect=lambda r="manual", pre_unmounted=False: timeline.append(f"rebind:{pre_unmounted}") or []), \
             patch.object(core.time, "sleep"):
            code_z, res_z = core._handle_smb_source_request({"action": "set", "source": "zimaos"})
        self.assertEqual(code_z, 200)
        self.assertTrue(res_z["success"])
        self.assertEqual(timeline, ["unmount", "purge", "post_mode_zimaos", "rebind:True"])

    def test_03_get_smb_source_coalescing_acl_debounce_and_easytier_no_tun_fields(self):
        """SMBS-03 / SMBS-06 / D-07.2 / D-10.2: Debounce coalesces rapid ACL changes asynchronously and exposes easytierNoTun/tunActive/smbWarning."""
        rebind_calls = []
        with patch.object(core, "_BACKEND_ACL_REBIND_DEBOUNCE_SEC", 0.04), \
             patch.object(core, "rebind_storage_pipeline", side_effect=lambda r="manual": rebind_calls.append(r) or []), \
             patch.object(core, "_scan_live_drives_now", return_value=[]):
            core._schedule_debounced_acl_rebind("backend_acl_changed")
            core._schedule_debounced_acl_rebind("backend_acl_changed")
            self.assertEqual(rebind_calls, [])
            self.assertTrue(core._flush_pending_acl_rebind_for_test(timeout=2.0))
        self.assertEqual(rebind_calls, ["backend_acl_changed"])

        fake_et = types.SimpleNamespace(
            get_status_overview=lambda: {
                "running": True,
                "tun_active": False,
                "no_tun_fallback": True,
                "smb_warning": "Adapter Wintun tidak aktif.",
            }
        )
        with patch.object(core.easytier_manager, "get_easytier_manager", return_value=fake_et), \
             patch.object(core, "_get_active_server_backend_url", return_value=""):
            code_g, res_g = core._handle_smb_source_request({"action": "get"})
        self.assertEqual(code_g, 200)
        self.assertIs(res_g["easytierNoTun"], True)
        self.assertIs(res_g["tunActive"], False)
        self.assertEqual(res_g["smbWarning"], "Adapter Wintun tidak aktif.")

    def test_04_explorer_endpoints_propagate_preflight_445_errors(self):
        """SMBS-02 / D-05.5: /api/open_drive, /api/open_unc, /api/open_file_explorer return {success: False, error} when port-445 preflight fails."""
        with patch.object(smb_mount_manager, "open_drive_in_explorer", return_value=(False, "Host SMB (192.168.1.50:445) tidak merespons")):
            st_d, b_d = self._post("/api/open_drive", {"letter": "Z"})
            self.assertEqual(st_d, 200)
            self.assertIs(b_d["success"], False)
            self.assertIn("445", b_d["error"])

        with patch.object(smb_mount_manager, "open_unc_root_in_explorer", return_value=(False, "Host SMB (192.168.1.50:445) tidak dapat dijangkau")):
            st_u, b_u = self._post("/api/open_unc", {})
            self.assertEqual(st_u, 200)
            self.assertIs(b_u["success"], False)
            self.assertIn("445", b_u["error"])

            with patch.object(core, "get_primary_mounted_share", return_value=("", "")), \
                 patch.object(core, "mount_active_server_smb"), \
                 patch.object(core.time, "sleep"):
                st_fe, b_fe = self._post("/api/open_file_explorer", {})
                self.assertEqual(st_fe, 200)
                self.assertIs(b_fe["success"], False)
                self.assertIn("445", b_fe["error"])


if __name__ == "__main__":
    unittest.main()

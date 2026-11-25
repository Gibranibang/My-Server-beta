"""
Phase 08 Plan 03 regression tests (FIXD-01, FIXD-02, FIXD-03):
- smb_mount_manager._run_subprocess_bounded Popen kill on TimeoutExpired
- Thread-safe _cached_1219_alias with _alias_1219_lock
- Multi-share Error 85/1202 isolation (no host purge) & real alt_drive tracking/rollback
- Backend API error (None) vs authoritative empty share list ([])
- myserver_core_service top-level socket import, global cache declarations,
  dynamic EasyTier drive recognition, non-mutating get_server_details_data(),
  smb_offline_unmounted latch, and switch-epoch telemetry guards.
"""

import ast
import ctypes
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch


def _install_linux_win_stubs():
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
        ctypes.WinDLL = lambda *a, **k: _DummyDll()

    if "winreg" not in sys.modules:
        winreg_stub = types.ModuleType("winreg")
        winreg_stub.HKEY_CURRENT_USER = 0x80000001
        winreg_stub.HKEY_LOCAL_MACHINE = 0x80000002
        winreg_stub.KEY_READ = 0x20019
        winreg_stub.KEY_WRITE = 0x20006
        winreg_stub.KEY_ALL_ACCESS = 0xF003F
        winreg_stub.REG_SZ = 1
        winreg_stub.OpenKey = lambda *_a, **_kw: (_ for _ in ()).throw(FileNotFoundError())
        winreg_stub.QueryValueEx = lambda *_a, **_kw: ("", 1)
        winreg_stub.CreateKey = lambda *_a, **_kw: None
        winreg_stub.SetValueEx = lambda *_a, **_kw: None
        winreg_stub.CloseKey = lambda *_a, **_kw: None
        sys.modules["winreg"] = winreg_stub


_install_linux_win_stubs()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config_manager  # noqa: E402
import easytier_manager  # noqa: E402
import myserver_core_service as core  # noqa: E402
import smb_mount_manager as smb  # noqa: E402


class _StopLoop(BaseException):
    pass


class TestSmbMountManagerPhase08(unittest.TestCase):
    def setUp(self):
        smb.invalidate_smb_host_cache()
        smb.clear_smb_share_cache()
        with smb._alias_1219_lock:
            smb._cached_1219_alias.clear()

    def tearDown(self):
        smb.invalidate_smb_host_cache()
        smb.clear_smb_share_cache()
        with smb._alias_1219_lock:
            smb._cached_1219_alias.clear()

    def test_01_run_subprocess_bounded_kills_timed_out_popen(self):
        """D-11: _run_subprocess_bounded uses Popen, kills & reaps timed-out subprocesses, and raises TimeoutExpired."""
        fake_proc = MagicMock()
        fake_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(["net.exe", "use"], 0.2),
            ("", ""),
        ]
        with patch.object(smb.subprocess, "Popen", return_value=fake_proc) as mock_popen:
            with self.assertRaises(subprocess.TimeoutExpired):
                smb._run_subprocess_bounded(["net.exe", "use"], timeout_sec=0.2)
        mock_popen.assert_called_once()
        fake_proc.kill.assert_called_once()
        self.assertEqual(fake_proc.communicate.call_count, 2)

        # Real OS child process test: sleeping Python subprocess is killed without lingering
        t0 = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            smb._run_subprocess_bounded(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                timeout_sec=0.15,
            )
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 2.0)

    def test_02_backend_api_error_none_vs_empty_list_never_caches_or_unmounts(self):
        """D-12: HTTP 500/URLError returns None, does not cache [] for 30s, and does not unmount healthy drives."""
        # Case A: HTTP 500 -> None when return_none_on_error=True (and [] by default for backward compat)
        http_500 = urllib.error.HTTPError(
            url="http://127.0.0.1:8080/api/v1/storage/disks",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )
        with patch.object(smb.urllib.request, "urlopen", side_effect=http_500):
            res_500 = smb.fetch_shares_from_backend_api(
                "http://127.0.0.1:8080",
                username="u1",
                password="p1",
                auth_token="tok",
                return_none_on_error=True,
            )
        self.assertIsNone(res_500)

        # Case B: URLError -> None when return_none_on_error=True
        with patch.object(smb.urllib.request, "urlopen", side_effect=urllib.error.URLError("timed out")):
            res_url = smb.fetch_shares_from_backend_api(
                "http://127.0.0.1:8080",
                username="u1",
                password="p1",
                auth_token="tok",
                return_none_on_error=True,
            )
        self.assertIsNone(res_url)

        # Case C: HTTP 200 with 0 disks -> [] (authoritative empty list)
        fake_resp = MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = json.dumps({"disks": []}).encode("utf-8")
        fake_resp.__enter__ = lambda s: s
        fake_resp.__exit__ = lambda *_a: False
        with patch.object(smb.urllib.request, "urlopen", return_value=fake_resp):
            res_200 = smb.fetch_shares_from_backend_api(
                "http://127.0.0.1:8080",
                username="u1",
                password="p1",
                auth_token="tok",
                return_none_on_error=True,
            )
        self.assertEqual(res_200, [])

        # Case D: get_remote_smb_shares does not cache None for 30s; second call re-queries API
        smb.clear_smb_share_cache()
        with patch.object(
            smb,
            "fetch_shares_from_backend_api",
            side_effect=[None, ["DiskA"]],
        ) as mock_fetch:
            first = smb.get_remote_smb_shares(
                host="192.168.1.50",
                username="u1",
                password="p1",
                auth_token="tok",
                smb_source="backend",
                backend_url="http://192.168.1.50:8080",
            )
            second = smb.get_remote_smb_shares(
                host="192.168.1.50",
                username="u1",
                password="p1",
                auth_token="tok",
                smb_source="backend",
                backend_url="http://192.168.1.50:8080",
            )
        self.assertIsNone(first)
        self.assertEqual(second, ["DiskA"])
        self.assertEqual(mock_fetch.call_count, 2)

        # Case E: mount_all_smb_shares on None does NOT unmount existing healthy drives
        smb.clear_smb_share_cache()
        unmounted = []
        with patch.object(smb.sys, "platform", "win32"), \
             patch.object(smb, "resolve_smb_host", return_value="192.168.1.50"), \
             patch.object(smb, "fetch_shares_from_backend_api", return_value=None), \
             patch.object(smb, "_candidate_network_letters", return_value=["Z:"]), \
             patch.object(smb, "_get_wnet_remote_unc", return_value=(0, r"\\192.168.1.50\DiskA")), \
             patch.object(smb, "unmount_smb_share", side_effect=lambda d, **_kw: unmounted.append(d) or True):
            ok, msg = smb.mount_all_smb_shares(
                host="192.168.1.50",
                username="u1",
                password="p1",
                auth_token="tok",
                smb_source="backend",
                backend_url="http://192.168.1.50:8080",
            )
        self.assertFalse(ok)
        self.assertIn("terputus", msg.lower())
        self.assertEqual(unmounted, [])

    def test_03_error_85_preserves_prior_shares_and_tracks_actual_alt_drive_rollback(self):
        """D-11: Error 85/1202 swaps drive letter without purge_smb_sessions; mount_all_smb_shares tracks & rolls back real alt_drive."""
        # Part 1: mount_smb_share Error 85 swaps Z: -> Y: and does NOT call purge_smb_sessions
        used_letters = {"Z:"}

        def fake_in_use(d):
            return d.upper() in used_letters

        def fake_avail(preferred="Z:", exclude_letters=None):
            excl = set(exclude_letters or set())
            for cand in ("Z:", "Y:", "X:"):
                if cand not in excl and cand not in used_letters:
                    return cand
            return None

        def fake_subproc(cmd, **_kw):
            if cmd[:2] == ["net.exe", "use"] and len(cmd) >= 3:
                drv = cmd[2].upper()
                if drv == "Z:":
                    return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="System error 85 has occurred.")
                if drv == "Y:":
                    return subprocess.CompletedProcess(cmd, 0, stdout="OK", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        drive_out = []
        with patch.object(smb, "resolve_smb_host", return_value="192.168.1.50"), \
             patch.object(smb, "is_drive_letter_in_use", side_effect=fake_in_use), \
             patch.object(smb, "get_available_drive_letter", side_effect=fake_avail), \
             patch.object(smb, "unmount_smb_share", return_value=True), \
             patch.object(smb, "_register_windows_credential"), \
             patch.object(smb, "purge_smb_sessions", side_effect=AssertionError("purge_smb_sessions must NOT run on Error 85")), \
             patch.object(smb, "_run_subprocess_bounded", side_effect=fake_subproc):
            ok, msg = smb.mount_smb_share(
                host="192.168.1.50",
                share_name="Disk2",
                username="u1",
                password="p1",
                drive_letter="Z:",
                skip_ipc=True,
                notify_explorer=False,
                mounted_drive_out=drive_out,
            )
        self.assertTrue(ok, msg)
        self.assertEqual(drive_out, ["Y:"])
        self.assertIn("Y:", msg)

        # Part 2: mount_all_smb_shares tracks actual alt_drive (Y:) and rolls back Y: (not Z:) on abort
        abort_state = {"abort": False}
        unmounted = []
        notify_calls = []

        def fake_mount_for_all(**kw):
            out = kw.get("mounted_drive_out")
            if kw["share_name"] == "Disk1":
                # Simulate swap Z: -> Y:
                if isinstance(out, list):
                    out.clear()
                    out.append("Y:")
                return True, r"Berhasil memasang \\192.168.1.50\Disk1 ke Y:"
            # Trigger abort right after Disk2 starts
            abort_state["abort"] = True
            if isinstance(out, list):
                out.clear()
                out.append("X:")
            return True, r"Berhasil memasang \\192.168.1.50\Disk2 ke X:"

        with patch.object(smb.sys, "platform", "linux"), \
             patch.object(smb, "resolve_smb_host", return_value="192.168.1.50"), \
             patch.object(smb, "get_remote_smb_shares", return_value=["Disk1", "Disk2"]), \
             patch.object(smb, "get_available_drive_letter", side_effect=["Z:", "X:"]), \
             patch.object(smb, "mount_smb_share", side_effect=fake_mount_for_all), \
             patch.object(smb, "unmount_smb_share", side_effect=lambda d, **_kw: unmounted.append(d) or True), \
             patch.object(smb, "_notify_windows_explorer_refresh", side_effect=lambda **kw: notify_calls.append(kw)), \
             patch.object(smb, "_register_windows_credential"), \
             patch.object(smb, "_run_subprocess_bounded", return_value=subprocess.CompletedProcess([], 0, "", "")):
            ok_ab, _ = smb.mount_all_smb_shares(
                host="192.168.1.50",
                username="u1",
                password="p1",
                abort_check=lambda: abort_state["abort"],
            )
        self.assertFalse(ok_ab)
        self.assertIn("X:", unmounted)
        self.assertIn("Y:", unmounted)
        self.assertNotIn("Z:", unmounted)

    def test_04_alias_1219_lock_concurrent_safety(self):
        """D-11: _alias_1219_lock protects concurrent reads/writes of _cached_1219_alias."""
        self.assertTrue(hasattr(smb, "_alias_1219_lock"))
        errors = []

        def _writer(idx):
            try:
                for j in range(50):
                    with smb._alias_1219_lock:
                        smb._cached_1219_alias[f"192.168.1.{idx}"] = f"192.168.2.{j}"
                    _ = smb.get_active_1219_aliases()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
        self.assertEqual(errors, [])


class TestCoreServicePhase08(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None

        cfg = config_manager.get_default_config()
        cfg["servers"] = [
            {
                "id": "srv_1",
                "name": "ServerOne",
                "remote_id": "rid-alpha-111",
                "remote_mode": "easytier",
                "easytier_virtual_ip": "",
                "active_connection": "c_lan",
                "connections": [{"id": "c_lan", "url": "http://192.168.1.50:80", "label": "LAN"}],
                "profiles": ["Admin"],
                "active_profile": "Admin",
                "profiles_credentials": {
                    "Admin": {"username": "zima", "password": config_manager.encrypt_credential("pw")}
                },
            },
            {
                "id": "srv_2",
                "name": "ServerTwo",
                "remote_id": "rid-beta-222",
                "active_connection": "c2_lan",
                "connections": [{"id": "c2_lan", "url": "http://192.168.2.50:80", "label": "LAN"}],
                "profiles": ["Admin"],
                "active_profile": "Admin",
            },
        ]
        cfg["active_server_id"] = "srv_1"
        config_manager.save_config(cfg)

    def tearDown(self):
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()

    def test_01_top_level_socket_import_and_ipv4_snapshot(self):
        """D-09: myserver_core_service imports socket at module scope and _get_local_ipv4_snapshot runs without NameError."""
        self.assertTrue(hasattr(core, "socket"))
        fake_sock = MagicMock()
        fake_sock.getsockname.return_value = ("192.168.1.100", 12345)
        with patch.object(core.socket, "gethostname", return_value="testhost"), \
             patch.object(core.socket, "gethostbyname_ex", return_value=("testhost", [], ["192.168.1.100"])), \
             patch.object(core.socket, "socket", return_value=fake_sock):
            ips = core._get_local_ipv4_snapshot()
        self.assertIsInstance(ips, list)
        self.assertIn("192.168.1.100", ips)

    def test_02_global_cache_declarations_rebind_do_post_and_syncthing(self):
        """D-09: rebind_storage_pipeline & do_POST update/clear module-global _cached_live_drives; Syncthing setup clears globals."""
        # 1. rebind_storage_pipeline updates module-global core._cached_live_drives
        expected_drives = [{"letter": "Z", "name": "Media", "mounted": True}]
        with patch.object(core, "_unmount_myserver_smb_drives", return_value=0), \
             patch.object(core, "get_active_resolved_route", return_value=("http://192.168.1.50:80", "LAN")), \
             patch.object(core, "get_cached_metrics_client", return_value=None), \
             patch.object(smb, "clear_smb_share_cache"), \
             patch.object(smb, "invalidate_smb_host_cache"), \
             patch.object(smb, "purge_smb_sessions"), \
             patch.object(smb, "mount_all_smb_shares", return_value=(True, "ok")), \
             patch.object(smb, "get_last_mount_summary", return_value={"failed_shares": []}), \
             patch.object(core, "_scan_live_drives_now", return_value=expected_drives):
            core._cached_live_drives = [{"letter": "X", "name": "Stale"}]
            core.rebind_storage_pipeline("manual")
            self.assertEqual(core._cached_live_drives, expected_drives)
            core._set_smb_sync_state(False)

        # 2. CoreApiHandler.do_POST clears module-global core._cached_live_drives on switch_server / switch_route / switch_profile
        srv = http.server.HTTPServer(("127.0.0.1", 0), core.CoreApiHandler)
        port = srv.server_port
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            def _post(path, payload):
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}{path}",
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

            with patch.object(core.threading, "Thread", return_value=MagicMock()), \
                 patch.object(core, "get_active_resolved_route", return_value=("http://192.168.2.50:80", "LAN")), \
                 patch.object(core, "get_server_details_data", return_value={"ok": True}):
                for ep, body in (
                    ("/api/switch_server", {"serverId": "srv_2"}),
                    ("/api/switch_route", {"routeId": "c2_lan"}),
                    ("/api/switch_profile", {"profileName": "Admin"}),
                ):
                    with core._drives_cache_lock:
                        core._cached_live_drives = [{"letter": "Z", "name": "Old"}]
                    st, _ = _post(ep, body)
                    self.assertEqual(st, 200)
                    with core._drives_cache_lock:
                        self.assertEqual(core._cached_live_drives, [], f"{ep} did not clear module-global _cached_live_drives")
        finally:
            srv.shutdown()
            srv.server_close()

        # 3. Syncthing setup prompts declare and clear module globals
        core._active_local_st_client = object()
        core._active_local_st_key = ("127.0.0.1", 8384, "k")
        with patch.object(core.dialog_helper, "run_powershell_dialog", return_value={"status": "ok", "val1": "8384", "val2": "newk"}):
            self.assertTrue(core.prompt_local_syncthing_setup())
        self.assertIsNone(core._active_local_st_client)
        self.assertIsNone(core._active_local_st_key)

        core._active_srv_st_client = object()
        core._active_srv_st_key = ("192.168.1.50", 8384, "k")
        with patch.object(core.dialog_helper, "run_powershell_dialog", return_value={"status": "ok", "lanPort": "8384", "apiKey": "srvk"}):
            self.assertTrue(core.prompt_backup_app_setup())
        self.assertIsNone(core._active_srv_st_client)
        self.assertIsNone(core._active_srv_st_key)

    def test_03_scan_live_drives_easytier_identity_and_non_mutating_summary(self):
        """D-09: _scan_live_drives_now keeps dynamic 10.126.126.x EasyTier drive; get_server_details_data does not mutate _cached_summary."""
        class FakeK32:
            @staticmethod
            def GetLogicalDrives():
                return 1 << 25  # Z:

            @staticmethod
            def GetDriveTypeW(_p):
                return 4

        class FakeMpr:
            @staticmethod
            def WNetGetConnectionW(_d, buf, _sz):
                buf.value = r"\\10.126.126.1\Media"
                return 0

        fake_windll = types.SimpleNamespace(kernel32=FakeK32(), mpr=FakeMpr(), iphlpapi=ctypes.windll.iphlpapi)
        fake_et_mgr = types.SimpleNamespace(
            is_running=lambda: True,
            get_remote_id=lambda: "rid-alpha-111",
        )
        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core.ctypes, "windll", fake_windll), \
             patch.object(core, "get_active_remote_ip", return_value="10.126.126.1"), \
             patch.object(core.easytier_manager, "get_easytier_manager", return_value=fake_et_mgr), \
             patch.object(smb, "get_active_1219_aliases", return_value={}):
            drives = core._scan_live_drives_now()

        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]["letter"], "Z")
        self.assertEqual(drives[0]["name"], "Media")

        # Also verify fallback recognition when get_active_remote_ip is empty but easytier_manager is running on active remote_id
        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core.ctypes, "windll", fake_windll), \
             patch.object(core, "get_active_remote_ip", return_value=""), \
             patch.object(core.easytier_manager, "get_easytier_manager", return_value=fake_et_mgr), \
             patch.object(smb, "get_active_1219_aliases", return_value={}):
            drives_fb = core._scan_live_drives_now()
        self.assertEqual(len(drives_fb), 1)

        # Verify get_server_details_data does not mutate EasyTierManager._cached_summary
        mgr = easytier_manager.EasyTierManager()
        original_summary = {"running": True, "remote_id": "", "server_peer_ip": "10.126.126.9", "tun_active": True}
        mgr._cached_summary = dict(original_summary)
        mgr._cached_summary_ts = time.time() + 60.0

        with patch.object(core.easytier_manager, "get_easytier_manager", return_value=mgr), \
             patch.object(mgr, "get_status_overview", return_value=mgr._cached_summary), \
             patch.object(mgr, "get_remote_id", return_value="rid-alpha-111"), \
             patch.object(core, "get_active_resolved_route", return_value=("http://192.168.1.50:80", "LAN")), \
             patch.object(core.config_manager, "get_dynamic_remote_info", return_value={"engine": "easytier", "ip": "10.126.126.1"}):
            details = core.get_server_details_data()

        self.assertEqual(details["easyTier"]["remote_id"], "rid-alpha-111")
        self.assertEqual(details["easyTier"]["server_peer_ip"], "10.126.126.1")
        self.assertEqual(mgr._cached_summary, original_summary)

    def test_04_offline_latch_waits_for_actual_unmount_and_switch_epoch_guards(self):
        """D-10: smb_offline_unmounted stays False while port 445 alive and latches only after actual unmount; switch epoch guards else/finally."""
        # Part A: update_metrics_loop offline latch
        unmount_calls = []
        port_alive_seq = [True, False]
        sleep_ticks = [0]

        def fake_sleep(_sec):
            sleep_ticks[0] += 1
            if sleep_ticks[0] >= 6:
                raise _StopLoop()

        fake_client = types.SimpleNamespace(fetch_metrics=lambda **_kw: {"online": False, "is_online": False})
        with patch.object(core, "get_active_resolved_route", return_value=("http://192.168.1.50:80", "LAN")), \
             patch.object(core, "get_cached_metrics_client", return_value=fake_client), \
             patch.object(core, "_is_server_smb_port_alive", side_effect=lambda **_kw: port_alive_seq.pop(0) if port_alive_seq else False), \
             patch.object(core, "_unmount_myserver_smb_drives", side_effect=lambda **kw: unmount_calls.append(kw.get("reason")) or 1), \
             patch.object(smb, "invalidate_smb_host_cache"), \
             patch.object(core, "_check_effective_smb_host_transition_for_server"), \
             patch.object(core.threading, "Thread", side_effect=lambda target, daemon=True: types.SimpleNamespace(start=target)), \
             patch.object(core.time, "sleep", side_effect=fake_sleep):
            with self.assertRaises(_StopLoop):
                core.update_metrics_loop()

        # Tick 5: port 445 alive -> skipped unmount, latch stayed False
        # Tick 6: port 445 dead -> unmount actually executed once!
        self.assertEqual(unmount_calls, ["server_offline_streak"])

        # Part B: switch-epoch guards in CoreApiHandler.do_POST _trigger_fresh_server_telemetry & _trigger_fresh_route_telemetry
        srv = http.server.HTTPServer(("127.0.0.1", 0), core.CoreApiHandler)
        port = srv.server_port
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        captured_targets = []
        try:
            def _capture_thread(target=None, daemon=True, **_kw):
                captured_targets.append(target)
                return MagicMock()

            for ep, payload in (
                ("/api/switch_server", {"serverId": "srv_2"}),
                ("/api/switch_route", {"routeId": "c2_lan"}),
            ):
                captured_targets.clear()
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}{ep}",
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(data)),
                        "X-MyServer-Core-Token": core.get_core_auth_token(),
                    },
                    method="POST",
                )
                with patch.object(core.threading, "Thread", side_effect=_capture_thread), \
                     patch.object(core, "get_active_resolved_route", return_value=("http://192.168.2.50:80", "LAN")), \
                     patch.object(core, "get_server_details_data", return_value={"ok": True}):
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        self.assertEqual(resp.status, 200)

                telemetry_worker = captured_targets[0]
                # Bump epoch before stale worker runs and returns offline (None)
                core._bump_metrics_switch_epoch(reset_client=False)
                with core._state_lock:
                    core._cached_state["is_online"] = True
                    core._cached_state["telemetry_loading"] = True

                with patch.object(core, "get_active_resolved_route", return_value=("http://192.168.2.50:80", "LAN")), \
                     patch.object(core, "get_cached_metrics_client", return_value=types.SimpleNamespace(fetch_metrics=lambda **_kw: None)):
                    telemetry_worker()

                with core._state_lock:
                    self.assertTrue(core._cached_state["is_online"], f"{ep} stale worker cleared is_online")
                    self.assertTrue(core._cached_state["telemetry_loading"], f"{ep} stale worker cleared telemetry_loading")
        finally:
            with core._state_lock:
                core._cached_state["telemetry_loading"] = False
            srv.shutdown()
            srv.server_close()

    def test_fetch_shares_skips_remote_fuse_disks_by_default(self):
        import smb_mount_manager as smb

        payload = json.dumps({
            "disks": [
                {"name": "LocalDiskA", "relative_path": "LocalDiskA", "is_accessible": True, "is_remote": False},
                {"name": "RemoteCloudB", "relative_path": "RemoteCloudB", "is_accessible": True, "is_remote": True},
            ]
        }).encode("utf-8")

        class _Resp:
            status = 200
            def read(self): return payload
            def __enter__(self): return self
            def __exit__(self, *a): return False

        with patch.object(smb.urllib.request, "urlopen", return_value=_Resp()):
            default_shares = smb.fetch_shares_from_backend_api("http://192.0.2.10:8080", auth_token="tok")
            all_shares = smb.fetch_shares_from_backend_api("http://192.0.2.10:8080", auth_token="tok", skip_remote=False)

        self.assertEqual(default_shares, ["LocalDiskA"])
        self.assertEqual(all_shares, ["LocalDiskA", "RemoteCloudB"])

    def test_smb_source_get_excludes_is_remote_to_prevent_acl_remount_loop(self):
        import config_manager
        import myserver_core_service as core

        fake_cfg = {
            "active_server_id": "srv_1",
            "servers": [{
                "id": "srv_1",
                "name": "TestSrv",
                "host": "192.0.2.20",
                "smb_source": "backend",
                "backend_smb_auth": {
                    "username": "alice",
                    "password": "pw",
                    "access_token": "tok",
                    "role": "admin",
                    "allowed_disks": ["LocalDiskA"],
                },
            }],
        }

        def _fake_http(url, method="GET", timeout=2.0, retries=0):
            return True, {"status": "ok"}, 200

        def _fake_auth_req(b_url, path, smb_cfg, srv_id, method="GET"):
            if path == "/api/v1/smb/status":
                return 200, {"mode": "backend"}, "tok"
            if path == "/api/v1/storage/disks":
                return 200, {
                    "disks": [
                        {"name": "LocalDiskA", "relative_path": "LocalDiskA", "is_accessible": True, "is_remote": False},
                        {"name": "RemoteCloudB", "relative_path": "RemoteCloudB", "is_accessible": True, "is_remote": True},
                    ]
                }, "tok"
            return 404, {}, "tok"

        with patch.object(config_manager, "load_or_create_config", return_value=fake_cfg), \
             patch.object(core, "_backend_http_request", side_effect=_fake_http), \
             patch.object(core, "_backend_authenticated_request", side_effect=_fake_auth_req), \
             patch.object(core, "_schedule_debounced_acl_rebind") as mock_rebind, \
             patch.object(core, "get_live_drives_list", return_value=[]):
            st, payload = core._handle_smb_source_request({"action": "get"})

        self.assertEqual(st, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["allowedDisks"], ["LocalDiskA"])
        mock_rebind.assert_not_called()


if __name__ == "__main__":
    unittest.main()

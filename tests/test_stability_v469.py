"""
Unit & Regression Tests for My-Server Desktop v4.6.9 Beta Stability Upgrades:
- EasyTier Traffic-Aware Congestion Guard & --disable-p2p fallback
- Active-Transfer Path Freeze & Mount Failure Cooldown
- cmdkey-first SMB mounting & bounded read-only Explorer liveness check
- Virtual adapter filtering & HTTP Keep-Alive / Bearer JWT auto-auth
"""

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
from unittest.mock import patch, MagicMock

BETA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BETA_DIR not in sys.path:
    sys.path.insert(0, BETA_DIR)

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

import easytier_manager  # noqa: E402
import smb_mount_manager  # noqa: E402
import myserver_core_service as core  # noqa: E402


class TestDesktopStabilityV469(unittest.TestCase):
    def setUp(self):
        core.clear_smb_mount_failure_cooldown()
        core._clear_backend_http_pool()

    def test_01_easytier_traffic_congestion_guard_and_disable_p2p_fallback(self):
        mgr = easytier_manager.EasyTierManager()
        peer_seq = [
            [{"peer_id": "1", "rx_bytes": 1000, "tx_bytes": 2000}],
            [{"peer_id": "1", "rx_bytes": 500000, "tx_bytes": 900000}],
        ]
        with patch.object(mgr, "is_running", return_value=True), \
             patch.object(mgr, "get_peers", side_effect=lambda: peer_seq.pop(0)):
            st1 = mgr.get_tunnel_traffic_stats()
            self.assertTrue(st1["active"])
            self.assertEqual(st1["delta_bytes"], 3000)
            st2 = mgr.get_tunnel_traffic_stats()
            self.assertTrue(st2["active"])
            self.assertGreater(st2["delta_bytes"], 1000000)

        # 3 consecutive P2P failures enable --disable-p2p fallback
        mgr2 = easytier_manager.EasyTierManager()
        with patch.object(mgr2, "is_available", return_value=True), \
             patch.object(mgr2, "is_running", return_value=False), \
             patch.object(mgr2, "_kill_orphaned_daemon"), \
             patch.object(mgr2, "_is_rpc_reachable", return_value=True), \
             patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            mgr2.start(remote_id="1a2b3c4d5e6f7089", use_no_tun=True, disable_p2p=True)
            cmd = mock_popen.call_args[0][0]
            self.assertIn("--disable-p2p", cmd)

        self.assertFalse(mgr2.record_p2p_probe_result(True))
        mgr2._disable_p2p = False
        self.assertFalse(mgr2.record_p2p_probe_result(False))
        self.assertFalse(mgr2.record_p2p_probe_result(False))
        with patch.object(mgr2, "is_running", return_value=True), \
             patch.object(mgr2, "start", return_value=(True, "ok")) as mock_restart:
            triggered = mgr2.record_p2p_probe_result(False)
            self.assertTrue(triggered)
            self.assertTrue(mock_restart.called)
            self.assertTrue(mock_restart.call_args[1]["disable_p2p"])

    def test_02_cmdkey_first_smb_mount_hides_password_on_primary_argv(self):
        seen_cmds = []

        def fake_run(cmd, **kwargs):
            seen_cmds.append(list(cmd))
            # First call is cmdkey, second is IPC$ without pw, third is net use without pw
            return subprocess.CompletedProcess(cmd, 0, stdout="OK", stderr="")

        with patch.object(smb_mount_manager, "resolve_smb_host", return_value="192.168.1.50"), \
             patch.object(smb_mount_manager, "is_drive_letter_in_use", return_value=False), \
             patch.object(smb_mount_manager, "_register_windows_credential") as mock_cmdkey, \
             patch.object(smb_mount_manager, "_notify_windows_explorer_refresh"), \
             patch("subprocess.run", side_effect=fake_run):
            ok, _ = smb_mount_manager.mount_smb_share(
                host="192.168.1.50",
                share_name="Media",
                username="alice",
                password="SuperSecretPassword!",
                drive_letter="Z:",
                notify_explorer=False,
            )
        self.assertTrue(ok)
        self.assertTrue(mock_cmdkey.called)
        for c in seen_cmds:
            self.assertNotIn("SuperSecretPassword!", c)

        # Fallback sends password only if primary cmdkey-first fails with non-1219 error
        fb_cmds = []

        def fake_run_fallback(cmd, **kwargs):
            fb_cmds.append(list(cmd))
            if "SuperSecretPassword!" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="OK", stderr="")
            return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="System error 1326")

        with patch.object(smb_mount_manager, "resolve_smb_host", return_value="192.168.1.50"), \
             patch.object(smb_mount_manager, "is_drive_letter_in_use", return_value=False), \
             patch.object(smb_mount_manager, "_register_windows_credential"), \
             patch.object(smb_mount_manager, "_notify_windows_explorer_refresh"), \
             patch("subprocess.run", side_effect=fake_run_fallback):
            ok2, _ = smb_mount_manager.mount_smb_share(
                host="192.168.1.50",
                share_name="Media",
                username="alice",
                password="SuperSecretPassword!",
                drive_letter="Y:",
                skip_ipc=True,
                notify_explorer=False,
            )
        self.assertTrue(ok2)
        self.assertNotIn("SuperSecretPassword!", fb_cmds[0])
        self.assertIn("SuperSecretPassword!", fb_cmds[1])

    def test_03_bounded_readonly_probe_and_explorer_expected_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, _ = smb_mount_manager._probe_drive_readonly_liveness(tmp, timeout=0.5)
            self.assertTrue(ok)

        def slow_scandir(_p):
            time.sleep(0.6)
            raise OSError("timeout")

        with patch("os.scandir", side_effect=slow_scandir):
            ok_slow, msg_slow = smb_mount_manager._probe_drive_readonly_liveness("/fake", timeout=0.1)
            self.assertFalse(ok_slow)
            self.assertIn("macet", msg_slow)

        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(0, r"\\10.126.126.1\DATA")), \
             patch.object(smb_mount_manager, "preflight_smb_port", return_value=True):
            ok_host, msg_host = smb_mount_manager.open_drive_in_explorer("Z:", expected_host="192.168.1.50")
            self.assertFalse(ok_host)
            self.assertIn("tidak cocok", msg_host)

    def test_04_transfer_path_freeze_cooldown_virtual_adapters_and_congestion_unmount(self):
        self.assertTrue(core._is_virtual_adapter_name("vEthernet (WSL)"))
        self.assertTrue(core._is_virtual_adapter_name("VMware Network Adapter VMnet8"))
        self.assertFalse(core._is_virtual_adapter_name("Wi-Fi"))

        # Active transfer freezes auto-route SMB rebind
        srv = {"id": "srv_1", "ip": "192.168.1.50", "connections": []}
        with patch.object(core, "_evaluate_auto_route_smb_transition", return_value=(True, "10.126.126.1")):
            ran, host = core._check_effective_smb_host_transition_for_server(
                srv, "http://10.126.126.1:8080", transfer_active=True, spawn_async=False
            )
            self.assertFalse(ran)
            self.assertEqual(host, "")

        # Mount failure cooldown prevents storm retry
        core._record_smb_mount_outcome("srv_cool", False, now_mono=100.0)
        self.assertTrue(core._is_smb_mount_in_cooldown("srv_cool", now_mono=120.0))
        self.assertFalse(core._is_smb_mount_in_cooldown("srv_cool", now_mono=200.0))

        # Congestion guard skips offline unmount even when streak >= threshold
        self.assertFalse(
            core._should_unmount_on_offline_streak(False, 5, False, smb_port_alive=False, tunnel_traffic_active=True)
        )

    def test_05_http_keepalive_pool_and_auto_bearer_injection(self):
        seen_auth = []
        seen_conn = []

        class _Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                seen_auth.append(self.headers.get("Authorization"))
                seen_conn.append(self.headers.get("Connection"))
                body = json.dumps({"vms": []}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with patch.object(core, "_resolve_backend_bearer_token_for_url", return_value="jwt_test_token_123"):
                ok1, d1, code1 = core._backend_http_request(f"http://127.0.0.1:{port}/api/v1/vms", method="GET", retries=0)
                ok2, d2, code2 = core._backend_http_request(f"http://127.0.0.1:{port}/api/v1/vms", method="GET", retries=0)
            self.assertTrue(ok1 and ok2)
            self.assertEqual(code1, 200)
            self.assertEqual(code2, 200)
            self.assertEqual(seen_auth, ["Bearer jwt_test_token_123", "Bearer jwt_test_token_123"])
            self.assertEqual(seen_conn, ["keep-alive", "keep-alive"])
        finally:
            core._clear_backend_http_pool()
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()

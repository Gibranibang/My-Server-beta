"""
Phase 08 Plan 02 regression tests (FIXD-01 & FIXD-03):
- Admin DISK % calculation with mounted local NAS drives & DSK-01 backend isolation
- Thread-safe detailed_partitions_map, exact IP/host & '/' path boundaries
- Virtual adapter CIDR classification (192.168.56.1/24 vs 192.168.1.x LAN)
- HTTP >= 500 & domain SSL/timeout offline behavior in check_server_ping()
- EasyTier --disable-p2p restart, get_summary() defensive copy, log FD closing
"""

import ctypes
import io
import json
import os
import ssl
import subprocess
import sys
import threading
import types
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config_manager  # noqa: E402
import easytier_manager  # noqa: E402
import zima_metrics_manager  # noqa: E402

if not hasattr(ctypes, "windll"):
    class _DummyDll:
        def __getattr__(self, _name):
            return types.SimpleNamespace(argtypes=None, restype=None, __call__=lambda *a, **k: 0)

    class _Windll:
        def __getattr__(self, _name):
            return _DummyDll()

    ctypes.windll = _Windll()
    ctypes.WinDLL = lambda *a, **k: _DummyDll()

try:
    import winreg  # noqa: F401
except ImportError:
    sys.modules["winreg"] = types.SimpleNamespace(
        HKEY_CURRENT_USER=0,
        HKEY_LOCAL_MACHINE=1,
        KEY_READ=0,
        REG_SZ=1,
        OpenKey=lambda *a, **k: None,
        QueryValueEx=lambda *a, **k: ("", 0),
        CloseKey=lambda *a, **k: None,
    )


def _make_admin_client(smb_source="zimaos", host="192.168.1.42"):
    client = zima_metrics_manager.ZimaMetricsClient(
        host=host,
        username="admin",
        password="secret",
        smb_source=smb_source,
    )
    client.is_admin = True
    client.token = "tok"
    client._last_bg_storage_fetch = 9e18
    return client


def _build_fake_windll(drive_map):
    class FakeKernel32:
        @staticmethod
        def GetLogicalDrives():
            mask = 0
            for letter in drive_map:
                mask |= 1 << (ord(letter.upper()) - 65)
            return mask

        @staticmethod
        def GetDriveTypeW(drive_root):
            return 4 if drive_root[0].upper() in drive_map else 1

    class FakeMpr:
        @staticmethod
        def WNetGetConnectionW(local_name, buf, buf_len_ref):
            letter = local_name[0].upper()
            if letter in drive_map:
                buf.value = drive_map[letter]
                return 0
            return 2250

    return types.SimpleNamespace(kernel32=FakeKernel32(), mpr=FakeMpr())


class TestPhase08DiskMetrics(unittest.TestCase):
    def test_admin_zimaos_mounted_nas_drives_included_in_totals(self):
        client = _make_admin_client(smb_source="zimaos", host="192.168.1.42")
        gb = 1024 ** 3
        tb = 1024 ** 4

        util_payload = {
            "data": {
                "cpu": {"percent": 12.0},
                "mem": {"used": 4 * gb, "total": 16 * gb, "usedPercent": 25.0},
                "sys_disk": {"size": 2000 * gb, "used": 600 * gb},
            }
        }
        mount_payload = {
            "data": [
                {"mount_point": "/DATA", "fstype": "ext4", "size": 2000 * gb, "used": 600 * gb},
                {"mount_point": "/media/Disk_Alpha", "fstype": "ext4", "source": "/dev/sdb1", "size": 1000 * gb, "used": 400 * gb},
                {"mount_point": "/media/Disk_Beta", "fstype": "ext4", "source": "/dev/sdc1", "size": 1000 * gb, "used": 200 * gb},
                {"mount_point": "/media/CloudGDrive", "fstype": "fuse.rclone", "source": "rclone:gdrive", "size": 100 * tb, "used": 50 * gb},
            ]
        }

        def fake_req(endpoint, **_kw):
            if endpoint == "/v1/sys/utilization":
                return util_payload
            if endpoint == "/v2/local_storage/mount":
                return mount_payload
            return None

        drive_map = {
            "Z": r"\\192.168.1.42\Disk_Alpha",
            "Y": r"\\192.168.1.42\Disk_Beta",
            "X": r"\\192.168.1.42\CloudGDrive",
        }
        fake_windll = _build_fake_windll(drive_map)

        with patch.object(client, "_make_request", side_effect=fake_req), \
             patch.object(zima_metrics_manager.os, "name", "nt"), \
             patch.object(zima_metrics_manager.ctypes, "windll", fake_windll, create=True):
            metrics = client.fetch_metrics()

        self.assertEqual(metrics["storage_total_bytes"], 2000 * gb)
        self.assertEqual(metrics["storage_used_bytes"], 600 * gb)
        self.assertEqual(metrics["storage_usage_pct"], 30.0)
        by_raw = {p.get("raw_name"): p for p in metrics["storage_partitions"]}
        self.assertTrue(by_raw["Disk_Alpha"]["is_network_drive"])
        self.assertFalse(by_raw["Disk_Alpha"]["is_remote"])
        self.assertEqual(by_raw["Disk_Alpha"]["drive_letter"], "Z:")
        self.assertTrue(by_raw["CloudGDrive"]["is_remote"])

    def test_admin_backend_smb_preserves_dsk01_isolation(self):
        client = _make_admin_client(smb_source="backend", host="192.168.1.42")
        client.detailed_partitions_map = {
            "z:": {"name": "Z:", "raw_name": "Z:", "total_bytes": 500, "is_network_drive": True}
        }
        gb = 1024 ** 3
        util_payload = {
            "data": {
                "cpu": {"percent": 8.0},
                "mem": {"used": 4 * gb, "total": 16 * gb, "usedPercent": 25.0},
                "sys_disk": {"size": 2000 * gb, "used": 400 * gb},
            }
        }
        mount_payload = {
            "data": [
                {"mount_point": "/DATA", "fstype": "ext4", "size": 2000 * gb, "used": 400 * gb},
                {"mount_point": "/media/Disk_Alpha", "fstype": "ext4", "source": "/dev/sdb1", "size": 1000 * gb, "used": 250 * gb},
                {"mount_point": "/media/Disk_Beta", "fstype": "ext4", "source": "/dev/sdc1", "size": 1000 * gb, "used": 150 * gb},
            ]
        }

        def fake_req(endpoint, **_kw):
            if endpoint == "/v1/sys/utilization":
                return util_payload
            if endpoint == "/v2/local_storage/mount":
                return mount_payload
            return None

        scan_mock = MagicMock(return_value=[{"raw_name": "Disk_Alpha", "total_bytes": 1000 * gb, "is_network_drive": True}])
        with patch.object(client, "_make_request", side_effect=fake_req), \
             patch.object(client, "_scan_windows_network_drives", scan_mock):
            metrics = client.fetch_metrics()

        scan_mock.assert_not_called()
        self.assertNotIn("z:", client.detailed_partitions_map)
        self.assertEqual(metrics["storage_total_bytes"], 2000 * gb)
        self.assertEqual(metrics["storage_used_bytes"], 400 * gb)
        self.assertEqual(metrics["storage_usage_pct"], 20.0)

    def test_fallback_network_drive_counts_local_excludes_cloud(self):
        client = _make_admin_client(smb_source="zimaos", host="192.168.1.42")
        gb = 1024 ** 3
        tb = 1024 ** 4
        util_payload = {
            "data": {
                "cpu": {"percent": 5.0},
                "mem": {"used": 2 * gb, "total": 8 * gb, "usedPercent": 25.0},
            }
        }

        def fake_req(endpoint, **_kw):
            if endpoint == "/v1/sys/utilization":
                return util_payload
            if endpoint == "/v2/local_storage/mount":
                return {"data": []}
            return None

        fallback_drives = [
            {
                "name": "Disk_Extra (Z:)",
                "raw_name": "Disk_Extra",
                "mount_point": "/media/Disk_Extra",
                "drive_letter": "Z:",
                "fs_type": "ext4",
                "remote_unc": r"\\192.168.1.42\Disk_Extra",
                "used_bytes": 250 * gb,
                "total_bytes": 1000 * gb,
                "pct": 25.0,
                "formatted_str": "250 GB / 1000 GB (25.0%)",
                "is_network_drive": True,
            },
            {
                "name": "CloudBox (Y:)",
                "raw_name": "CloudBox",
                "mount_point": "/media/CloudBox",
                "drive_letter": "Y:",
                "fs_type": "fuse.rclone",
                "remote_unc": r"\\192.168.1.42\CloudBox",
                "used_bytes": 10 * gb,
                "total_bytes": 10 * tb,
                "pct": 0.1,
                "formatted_str": "10 GB / 10 TB (0.1%)",
                "is_network_drive": True,
            },
        ]
        with patch.object(client, "_make_request", side_effect=fake_req), \
             patch.object(client, "_scan_windows_network_drives", return_value=fallback_drives):
            metrics = client.fetch_metrics()

        self.assertEqual(metrics["storage_total_bytes"], 1000 * gb)
        self.assertEqual(metrics["storage_used_bytes"], 250 * gb)
        self.assertEqual(metrics["storage_usage_pct"], 25.0)

    def test_determine_task_owner_and_non_admin_path_respect_slash_boundary(self):
        client = _make_admin_client(smb_source="zimaos")
        samba_payload = {
            "data": [
                {"username": "alice", "permissions": [{"path": "/media/Disk1", "read_only": False}]},
                {"username": "bob", "permissions": [{"path": "/media/Disk10", "read_only": False}]},
            ]
        }
        with patch.object(client, "_make_request", return_value=samba_payload):
            self.assertEqual(client.determine_task_owner("/media/Disk10/Sync"), "bob")
            self.assertEqual(client.determine_task_owner("/media/Disk1/Sync"), "alice")
            self.assertIsNone(client.determine_task_owner("/media/Disk100/Sync"))

        # Non-admin prefix fallback in detailed_partitions_map must not match /media/Disk1 to /media/Disk10
        non_admin = zima_metrics_manager.ZimaMetricsClient(
            host="192.168.1.42", username="bob", password="secret", smb_source="backend"
        )
        non_admin.is_admin = False
        non_admin.token = "tok"
        non_admin._last_bg_storage_fetch = 9e18
        non_admin.detailed_partitions_map = {
            "/media/Disk1": {
                "name": "Disk1",
                "raw_name": "Disk1",
                "mount_point": "/media/Disk1",
                "fs_type": "ext4",
                "used_bytes": 100,
                "total_bytes": 1000,
                "pct": 10.0,
                "formatted_str": "100 / 1000",
            }
        }

        def fake_non_admin_req(endpoint, **_kw):
            if endpoint == "/v1/sys/utilization":
                return {"data": {"cpu": {"percent": 1.0}, "mem": {"used": 10, "total": 100}}}
            if endpoint == "/v2/users/samba/user":
                return {"data": [{"username": "bob", "permissions": [{"path": "/media/Disk10", "read_only": False}]}]}
            return None

        with patch.object(non_admin, "_make_request", side_effect=fake_non_admin_req):
            m = non_admin.fetch_metrics()
        self.assertEqual(m["storage_total_bytes"], 0)
        self.assertEqual(m["storage_partitions"][0]["total_bytes"], 0)

    def test_scan_windows_network_drives_exact_ip_no_substring_match(self):
        client = _make_admin_client(host="192.168.1.1")
        client.detailed_partitions_map = {
            "media": {
                "name": "Media",
                "mount_point": "/media/Media",
                "total_bytes": 5000,
                "used_bytes": 1000,
                "avail_bytes": 4000,
                "fs_type": "ext4",
            }
        }
        drive_map = {
            "Z": r"\\192.168.1.10\Media",
            "Y": r"\\192.168.1.1\Media",
        }
        fake_windll = _build_fake_windll(drive_map)
        with patch.object(zima_metrics_manager.os, "name", "nt"), \
             patch.object(zima_metrics_manager.ctypes, "windll", fake_windll, create=True):
            discovered = client._scan_windows_network_drives(
                server_connections=[{"url": "http://192.168.1.1"}]
            )
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["drive_letter"], "Y:")
        self.assertEqual(discovered[0]["remote_unc"], r"\\192.168.1.1\Media")

    def test_detailed_partitions_map_concurrent_access_no_runtime_error(self):
        client = _make_admin_client(smb_source="backend")
        errors = []
        stop_evt = threading.Event()

        def fake_req(endpoint, **_kw):
            if endpoint == "/v1/sys/utilization":
                return {"data": {"cpu": {"percent": 2.0}, "mem": {"used": 10, "total": 100}}}
            if endpoint == "/v2/local_storage/mount":
                return {"data": [{"mount_point": "/media/DiskA", "fstype": "ext4", "size": 1000, "used": 100}]}
            return None

        def mutator():
            i = 0
            try:
                while not stop_evt.is_set():
                    with client._partitions_map_lock:
                        client.detailed_partitions_map[f"dyn_{i % 20}"] = {
                            "raw_name": f"Dyn{i % 20}",
                            "mount_point": f"/media/Dyn{i % 20}",
                            "total_bytes": 1000,
                            "used_bytes": 100,
                            "fs_type": "ext4",
                        }
                        if i % 5 == 0:
                            client.detailed_partitions_map.pop(f"dyn_{(i - 1) % 20}", None)
                    i += 1
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=mutator, daemon=True)
        t.start()
        try:
            with patch.object(client, "_make_request", side_effect=fake_req):
                for _ in range(30):
                    client.fetch_metrics()
        except Exception as exc:
            errors.append(exc)
        finally:
            stop_evt.set()
            t.join(timeout=2.0)

        self.assertEqual(errors, [])


class TestPhase08NetworkRoutingAndPing(unittest.TestCase):
    def setUp(self):
        self._orig_cache_time = config_manager._VIRTUAL_ADAPTER_CACHE_TIME
        self._orig_prefixes = set(config_manager._VIRTUAL_ADAPTER_PREFIXES)
        self._orig_networks = set(config_manager._VIRTUAL_ADAPTER_NETWORKS)

    def tearDown(self):
        config_manager._VIRTUAL_ADAPTER_CACHE_TIME = self._orig_cache_time
        config_manager._VIRTUAL_ADAPTER_PREFIXES = self._orig_prefixes
        config_manager._VIRTUAL_ADAPTER_NETWORKS = self._orig_networks

    def test_virtual_adapter_192_168_cidr_preserves_physical_lan_tier1(self):
        config_manager._VIRTUAL_ADAPTER_CACHE_TIME = 0
        ps_json = json.dumps([
            {"IPAddress": "192.168.56.1", "PrefixLength": 24},
            {"IPAddress": "169.254.12.34", "PrefixLength": 16},
            {"IPAddress": "127.0.0.1", "PrefixLength": 8},
        ])
        with patch.object(config_manager.sys, "platform", "win32"), \
             patch("subprocess.check_output", return_value=ps_json):
            prefixes = config_manager.get_virtual_adapter_prefixes()

        self.assertNotIn("192.168.", prefixes)
        self.assertIn("192.168.56.0/24", prefixes)
        self.assertEqual(config_manager.classify_connection_priority("http://192.168.1.42"), (1, "LAN"))
        self.assertEqual(config_manager.classify_connection_priority("http://192.168.56.25"), (3, "Zima"))

        cfg = {
            "language": "en",
            "servers": [{
                "id": "srv1",
                "name": "HomeNAS",
                "active_connection": "auto",
                "connections": [
                    {"id": "c_dom", "name": "Public", "url": "https://nas.example.com"},
                    {"id": "c_lan", "name": "LAN", "url": "http://192.168.1.42"},
                ],
            }],
            "active_server_id": "srv1",
        }
        with patch.object(config_manager, "get_dynamic_remote_info", return_value=None):
            url, _ = config_manager.resolve_target_connection(cfg, check_network=False)
        self.assertEqual(url, "http://192.168.1.42")

    def test_check_server_ping_http_5xx_and_domain_ssl_errors_return_offline(self):
        fake_sock = MagicMock()
        fake_sock.__enter__ = MagicMock(return_value=fake_sock)
        fake_sock.__exit__ = MagicMock(return_value=False)

        for code in (500, 502, 503, 504, 521):
            err = urllib.error.HTTPError("https://nas.example.com", code, "Server Error", {}, None)
            with patch("config_manager.socket.create_connection", return_value=fake_sock), \
                 patch("config_manager.urllib.request.urlopen", side_effect=err):
                ok, lat = config_manager.check_server_ping("https://nas.example.com")
            self.assertFalse(ok, f"HTTP {code} should be offline")
            self.assertEqual(lat, 0)

        with patch("config_manager.socket.create_connection", return_value=fake_sock), \
             patch("config_manager.urllib.request.urlopen", side_effect=ssl.SSLError("handshake failed")):
            ok_ssl, lat_ssl = config_manager.check_server_ping("http://nas.example.com")
        self.assertFalse(ok_ssl)
        self.assertEqual(lat_ssl, 0)

        with patch("config_manager.socket.create_connection", return_value=fake_sock), \
             patch("config_manager.urllib.request.urlopen", side_effect=TimeoutError("read timed out")):
            ok_to, lat_to = config_manager.check_server_ping("https://nas.example.com")
        self.assertFalse(ok_to)
        self.assertEqual(lat_to, 0)

        err_401 = urllib.error.HTTPError("https://nas.example.com", 401, "Unauthorized", {}, None)
        with patch("config_manager.socket.create_connection", return_value=fake_sock), \
             patch("config_manager.urllib.request.urlopen", side_effect=err_401):
            ok_401, lat_401 = config_manager.check_server_ping("https://nas.example.com")
        self.assertTrue(ok_401)
        self.assertGreaterEqual(lat_401, 1)


class TestPhase08EasyTierFixes(unittest.TestCase):
    def test_record_p2p_probe_result_triggers_actual_restart_with_disable_p2p(self):
        mgr = easytier_manager.EasyTierManager()
        spawned_cmds = []

        def fake_popen(cmd, **_kw):
            spawned_cmds.append(list(cmd))
            proc = MagicMock()
            proc.poll.return_value = None
            proc.pid = 1000 + len(spawned_cmds)
            return proc

        rpc_state = {"running": False}

        def fake_rpc():
            return rpc_state["running"]

        with patch.object(mgr, "is_available", return_value=True), \
             patch.object(mgr, "_kill_orphaned_daemon"), \
             patch.object(mgr, "_is_rpc_reachable", side_effect=fake_rpc), \
             patch("easytier_manager.time.sleep"), \
             patch("subprocess.Popen", side_effect=fake_popen):
            def popen_sets_rpc(cmd, **_kw):
                rpc_state["running"] = True
                return fake_popen(cmd, **_kw)

            with patch("subprocess.Popen", side_effect=popen_sets_rpc):
                ok, _ = mgr.start(remote_id="1a2b3c4d5e6f7089", use_no_tun=True)
                self.assertTrue(ok)
                self.assertEqual(len(spawned_cmds), 1)
                self.assertNotIn("--disable-p2p", spawned_cmds[0])
                self.assertFalse(mgr._disable_p2p)

                self.assertFalse(mgr.record_p2p_probe_result(False))
                self.assertFalse(mgr.record_p2p_probe_result(False))
                triggered = mgr.record_p2p_probe_result(False)
                self.assertTrue(triggered)

        self.assertEqual(len(spawned_cmds), 2)
        self.assertIn("--disable-p2p", spawned_cmds[1])
        self.assertTrue(mgr._disable_p2p)

    def test_get_summary_returns_defensive_copy(self):
        mgr = easytier_manager.EasyTierManager()
        with patch.object(mgr, "is_running", return_value=False), \
             patch.object(mgr, "is_available", return_value=True):
            s_off = mgr.get_summary()
            s_off["running"] = True
            s_off["peers"].append({"fake": 1})
            s_off2 = mgr.get_summary()
            self.assertFalse(s_off2["running"])
            self.assertEqual(s_off2["peers"], [])

        with patch.object(mgr, "is_running", return_value=True), \
             patch.object(mgr, "get_peers", return_value=[{"ipv4_addr": "10.126.126.1/24"}]), \
             patch.object(mgr, "get_node_info", return_value={"virtual_ipv4": "10.126.126.2", "uptime": 10}):
            s_on = mgr.get_summary(force_refresh=True)
            s_on["running"] = False
            s_on["peers"].append({"injected": True})
            s_on2 = mgr.get_summary()
            self.assertTrue(s_on2["running"])
            self.assertEqual(len(s_on2["peers"]), 1)

    def test_start_closes_log_handles_in_parent_and_skips_in_uac_branch(self):
        mgr = easytier_manager.EasyTierManager()
        captured_streams = []

        def fake_popen(cmd, **kwargs):
            captured_streams.append((kwargs.get("stdout"), kwargs.get("stderr")))
            proc = MagicMock()
            proc.poll.return_value = None
            return proc

        with patch.object(mgr, "is_available", return_value=True), \
             patch.object(mgr, "is_running", return_value=False), \
             patch.object(mgr, "_kill_orphaned_daemon"), \
             patch.object(mgr, "_is_rpc_reachable", return_value=True), \
             patch("subprocess.Popen", side_effect=fake_popen):
            ok, _ = mgr.start(remote_id="1a2b3c4d5e6f7089", use_no_tun=True)
        self.assertTrue(ok)
        self.assertEqual(len(captured_streams), 1)
        out_fh, err_fh = captured_streams[0]
        self.assertTrue(out_fh.closed)
        self.assertTrue(err_fh.closed)

        # UAC branch should NOT open stdout/stderr log handles
        fake_shell32 = types.SimpleNamespace(
            IsUserAnAdmin=MagicMock(return_value=0),
            ShellExecuteW=MagicMock(return_value=42),
        )
        fake_windll = types.SimpleNamespace(shell32=fake_shell32)
        real_open = open
        opened_paths = []

        def tracking_open(file, *args, **kwargs):
            opened_paths.append(str(file))
            return real_open(file, *args, **kwargs)

        mgr2 = easytier_manager.EasyTierManager()
        with patch.object(mgr2, "is_available", return_value=True), \
             patch.object(mgr2, "is_running", return_value=False), \
             patch.object(mgr2, "_kill_orphaned_daemon"), \
             patch.object(mgr2, "_is_rpc_reachable", side_effect=[False, True]), \
             patch("easytier_manager.os.name", "nt"), \
             patch("easytier_manager.ctypes.windll", fake_windll, create=True), \
             patch("easytier_manager.time.sleep"), \
             patch("builtins.open", side_effect=tracking_open):
            ok_uac, _ = mgr2.start(remote_id="1a2b3c4d5e6f7089", use_no_tun=False)
        self.assertTrue(ok_uac)
        self.assertFalse(any("easytier.std" in p for p in opened_paths))


if __name__ == "__main__":
    unittest.main()

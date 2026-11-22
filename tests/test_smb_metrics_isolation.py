import ast
import inspect
import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zima_metrics_manager  # noqa: E402


def _make_client():
    client = zima_metrics_manager.ZimaMetricsClient(
        host="192.168.1.50", username="admin", password="pw"
    )
    client.is_admin = True
    client.token = "tok"
    return client


def _build_fake_windll(drive_map, bitmask=None):
    """Build fake ctypes.windll with kernel32 & mpr stubs."""
    calls = {"GetDriveTypeW": [], "WNetGetConnectionW": []}

    class FakeKernel32:
        if bitmask is not None:
            @staticmethod
            def GetLogicalDrives():
                return bitmask

        @staticmethod
        def GetDriveTypeW(drive_root):
            calls["GetDriveTypeW"].append(drive_root)
            letter = drive_root[0].upper()
            return 4 if letter in drive_map else 1

    class FakeMpr:
        @staticmethod
        def WNetGetConnectionW(local_name, buf, buf_len_ref):
            calls["WNetGetConnectionW"].append(local_name)
            letter = local_name[0].upper()
            if letter in drive_map:
                buf.value = drive_map[letter]
                return 0
            return 2250

    windll = types.SimpleNamespace(kernel32=FakeKernel32(), mpr=FakeMpr())
    return windll, calls


class TestSmbMetricsIsolation(unittest.TestCase):
    def test_01_identities_never_calls_gethostbyaddr(self):
        client = _make_client()
        conns = [{"url": "http://192.168.1.50:80"}, {"url": "http://10.126.126.1:80"}]
        with patch(
            "zima_metrics_manager.socket.gethostbyaddr",
            side_effect=AssertionError("gethostbyaddr must never be called"),
        ):
            ids = client._get_zimaos_server_identities(conns)
        self.assertIn("192.168.1.50", ids["ips"])
        self.assertIn("10.126.126.1", ids["ips"])

    def test_02_scan_skips_empty_letters_and_never_calls_disk_usage_or_gethostbyname(self):
        client = _make_client()
        drive_map = {
            "Z": r"\\192.168.1.50\Media",
            "Y": r"\\192.168.1.50\UnmatchedShare",
            "X": r"\\corp-nas\Finance",
        }
        # Bitmask strictly for X(23), Y(24), Z(25)
        bitmask = (1 << 23) | (1 << 24) | (1 << 25)
        fake_windll, calls = _build_fake_windll(drive_map, bitmask=bitmask)
        client.detailed_partitions_map = {
            "media": {
                "name": "Media",
                "total_bytes": 1_000_000,
                "used_bytes": 250_000,
                "avail_bytes": 750_000,
                "fs_type": "ext4",
            }
        }

        with patch.object(zima_metrics_manager.os, "name", "nt"), patch.object(
            zima_metrics_manager.ctypes, "windll", fake_windll, create=True
        ), patch(
            "zima_metrics_manager.shutil.disk_usage",
            side_effect=AssertionError("shutil.disk_usage must never be called"),
        ), patch(
            "zima_metrics_manager.socket.gethostbyname",
            side_effect=AssertionError("socket.gethostbyname must never be called"),
        ):
            discovered = client._scan_windows_network_drives(
                server_connections=[{"host": "192.168.1.50"}]
            )

        self.assertEqual(sorted(calls["GetDriveTypeW"]), ["X:\\", "Y:\\", "Z:\\"])
        self.assertEqual(sorted(calls["WNetGetConnectionW"]), ["X:", "Y:", "Z:"])
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["raw_name"], "Media")
        self.assertEqual(discovered[0]["drive_letter"], "Z:")

    def test_02b_scan_falls_back_gracefully_when_get_logical_drives_missing(self):
        client = _make_client()
        drive_map = {"Z": r"\\192.168.1.50\Media"}
        fake_windll, calls = _build_fake_windll(drive_map, bitmask=None)
        client.detailed_partitions_map = {
            "media": {"total_bytes": 1_000_000, "used_bytes": 100_000, "fs_type": "ext4"}
        }

        with patch.object(zima_metrics_manager.os, "name", "nt"), patch.object(
            zima_metrics_manager.ctypes, "windll", fake_windll, create=True
        ):
            discovered = client._scan_windows_network_drives(
                server_connections=[{"host": "192.168.1.50"}]
            )

        self.assertEqual(len(calls["GetDriveTypeW"]), 26)
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["drive_letter"], "Z:")

    def test_03_detailed_partitions_map_not_overwritten_across_polls(self):
        client = _make_client()
        rest_entry = {
            "name": "Media",
            "total_bytes": 1_000_000,
            "used_bytes": 250_000,
            "avail_bytes": 750_000,
            "fs_type": "ext4",
        }
        client.detailed_partitions_map = {"media": rest_entry}
        drive_map = {"Z": r"\\192.168.1.50\Media"}
        bitmask = 1 << 25
        fake_windll, _ = _build_fake_windll(drive_map, bitmask=bitmask)

        with patch.object(zima_metrics_manager.os, "name", "nt"), patch.object(
            zima_metrics_manager.ctypes, "windll", fake_windll, create=True
        ), patch(
            "zima_metrics_manager.shutil.disk_usage",
            side_effect=AssertionError("shutil.disk_usage must never be called"),
        ):
            poll1 = client._scan_windows_network_drives(
                server_connections=[{"host": "192.168.1.50"}]
            )
            poll2 = client._scan_windows_network_drives(
                server_connections=[{"host": "192.168.1.50"}]
            )

        self.assertEqual(len(poll1), 1)
        self.assertEqual(len(poll2), 1)
        self.assertEqual(poll1[0]["total_bytes"], 1_000_000)
        self.assertEqual(poll2[0]["total_bytes"], 1_000_000)
        self.assertIs(client.detailed_partitions_map["media"], rest_entry)
        self.assertFalse(client.detailed_partitions_map["media"].get("is_network_drive", False))
        self.assertEqual(client.detailed_partitions_map["media"].get("drive_letter"), "Z:")

    def test_04_unmatched_share_never_poisons_map_and_fetch_signature_preserved(self):
        client = _make_client()
        client.detailed_partitions_map = {}
        drive_map = {"Y": r"\\192.168.1.50\UnmatchedShare"}
        bitmask = 1 << 24
        fake_windll, _ = _build_fake_windll(drive_map, bitmask=bitmask)

        with patch.object(zima_metrics_manager.os, "name", "nt"), patch.object(
            zima_metrics_manager.ctypes, "windll", fake_windll, create=True
        ), patch(
            "zima_metrics_manager.shutil.disk_usage",
            side_effect=AssertionError("shutil.disk_usage must never be called"),
        ):
            discovered = client._scan_windows_network_drives(
                server_connections=[{"host": "192.168.1.50"}]
            )

        self.assertEqual(discovered, [])
        self.assertEqual(client.detailed_partitions_map, {})
        sig = inspect.signature(zima_metrics_manager.ZimaMetricsClient.fetch_metrics)
        self.assertEqual(list(sig.parameters.keys()), ["self", "on_online_callback"])

    def test_05_ast_no_blocking_disk_usage_or_dns_calls(self):
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "zima_metrics_manager.py",
        )
        with open(src_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        scan_attrs = {
            n.attr for n in ast.walk(fns["_scan_windows_network_drives"]) if isinstance(n, ast.Attribute)
        }
        id_attrs = {
            n.attr for n in ast.walk(fns["_get_zimaos_server_identities"]) if isinstance(n, ast.Attribute)
        }
        self.assertNotIn("disk_usage", scan_attrs)
        self.assertNotIn("gethostbyname", scan_attrs)
        self.assertNotIn("gethostbyaddr", id_attrs)

    def test_06_umbrella_pool_ignores_fuse_cloud_and_preserves_valid_storage_cache(self):
        client = _make_client()
        client.smb_source = "backend"
        client._last_bg_storage_fetch = 9e18  # skip background thread spawn

        tb = 1024 ** 4
        gb = 1024 ** 3
        util_payload = {
            "data": {
                "cpu": {"percent": 55.0},
                "mem": {"used": 8 * gb, "total": 16 * gb, "usedPercent": 50.0},
                "net": [{"rxBytesPerSec": 130000, "txBytesPerSec": 0}],
                "sys_disk": {"size": 476 * gb, "used": 165 * gb},
            }
        }
        mount_payload_with_cloud = {
            "data": [
                {"mount_point": "/DATA", "fstype": "ext4", "size": 476 * gb, "used": 165 * gb},
                {"mount_point": "/media/CloudDrive_A", "fstype": "fuse.rclone", "source": "rclone:gdrive", "size": 100 * tb, "used": 100 * gb},
                {"mount_point": "/media/CloudDrive_B", "fstype": "fuse.rclone", "source": "rclone:gdrive2", "size": 5 * tb, "used": 10 * gb},
            ]
        }

        def fake_req(endpoint, **_kw):
            if endpoint == "/v1/sys/utilization":
                return util_payload
            if endpoint == "/v2/local_storage/mount":
                return mount_payload_with_cloud
            return None

        with patch.object(client, "_make_request", side_effect=fake_req):
            m1 = client.fetch_metrics()

        self.assertGreater(m1["storage_usage_pct"], 30.0)
        self.assertEqual(m1["storage_total_bytes"], 476 * gb)

        # Transient timeout/size=0 on /v2/local_storage/mount must NOT reset valid last_storage_cache to 0.0
        def fake_req_timeout(endpoint, **_kw):
            if endpoint == "/v1/sys/utilization":
                return {"data": {"cpu": {"percent": 20.0}, "mem": {"used": 8 * gb, "total": 16 * gb, "usedPercent": 50.0}}}
            if endpoint == "/v2/local_storage/mount":
                return {"data": [{"mount_point": "/media/USB", "fstype": "ext4", "size": 0, "used": 0}]}
            return None

        with patch.object(client, "_make_request", side_effect=fake_req_timeout):
            m2 = client.fetch_metrics()

        self.assertGreater(m2["storage_usage_pct"], 30.0)
        self.assertEqual(m2["storage_total_bytes"], 476 * gb)

    def test_07_core_commit_fast_online_and_client_carryover_preserve_disk_percent(self):
        import myserver_core_service as core

        with core._state_lock:
            saved_state = dict(core._cached_state)
        saved_client = core._active_metrics_client
        saved_key = core._active_metrics_client_key
        saved_srv_id = core._active_metrics_client_srv_id
        try:
            with core._state_lock:
                core._cached_state["disk_percent"] = 35
                core._cached_state["storage_total_bytes"] = 476 * (1024 ** 3)
                core._cached_state["storage_used_bytes"] = 165 * (1024 ** 3)
                core._cached_state["storage_partitions"] = [{"name": "System Storage (/DATA)"}]

            # Fast callback right after /v1/sys/utilization (before storage fetched) must not overwrite 35% with 0%
            core.commit_fast_online(
                {"cpu_usage_pct": 55.0, "ram_usage_pct": 31.0, "storage_usage_pct": 0.0, "storage_total_bytes": 0},
                s_name="STIMI-Server",
                smb_source="backend",
            )
            with core._state_lock:
                self.assertEqual(core._cached_state["disk_percent"], 35)
                self.assertEqual(core._cached_state["smb_source"], "backend")

            # Route change for same server_id carries over valid last_storage_cache
            srv = {
                "id": "srv_test_1",
                "name": "STIMI-Server",
                "connections": [{"url": "https://example.com"}],
                "active_connection": "auto",
                "active_profile": "Admin",
            }
            c1 = core.get_cached_metrics_client(srv, "https://example.com")
            c1.last_storage_cache = {
                "total_bytes": 476 * (1024 ** 3),
                "used_bytes": 165 * (1024 ** 3),
                "usage_pct": 34.7,
                "label": "Server Storage",
                "partitions": [{"name": "System Storage (/DATA)"}],
            }
            c2 = core.get_cached_metrics_client(srv, "http://192.168.1.50:80")
            self.assertIsNot(c1, c2)
            self.assertEqual(c2.last_storage_cache["usage_pct"], 34.7)
        finally:
            with core._state_lock:
                core._cached_state.clear()
                core._cached_state.update(saved_state)
            core._active_metrics_client = saved_client
            core._active_metrics_client_key = saved_key
            core._active_metrics_client_srv_id = saved_srv_id


if __name__ == "__main__":
    unittest.main()

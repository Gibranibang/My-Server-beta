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


if __name__ == "__main__":
    unittest.main()

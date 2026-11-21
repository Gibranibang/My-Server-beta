import inspect
import os
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zima_metrics_manager  # noqa: E402


def _make_client(**kwargs):
    client = zima_metrics_manager.ZimaMetricsClient(
        host="192.168.1.100", username="u", password="p", **kwargs
    )
    client.token = "tok"
    return client


def _fake_request(path, *args, **kwargs):
    if path == "/v1/sys/utilization":
        return {"data": {"cpu": {"percent": 5.0}, "mem": {"total": 100, "used": 10}}}
    return None


class TestDiskTelemetryIsolation(unittest.TestCase):
    def test_default_smb_source_is_zimaos(self):
        self.assertEqual(_make_client().smb_source, "zimaos")
        self.assertEqual(_make_client(smb_source=" Backend ").smb_source, "backend")
        self.assertEqual(_make_client(smb_source=None).smb_source, "zimaos")

    def test_backend_skips_scan_and_purges_network_drives(self):
        client = _make_client(smb_source="backend")
        client.detailed_partitions_map = {
            "z:": {"is_network_drive": True, "name": "Z:"},
            "/media/zima": {"is_network_drive": False, "name": "ZimaOS"},
        }
        scan = MagicMock(return_value=[{"name": "Z:", "is_network_drive": True}])
        with patch.object(client, "_make_request", side_effect=_fake_request), \
                patch.object(client, "_scan_windows_network_drives", scan), \
                patch.object(client, "get_user_authorized_shares", return_value=None):
            client.fetch_metrics()
        scan.assert_not_called()
        self.assertNotIn("z:", client.detailed_partitions_map)
        self.assertIn("/media/zima", client.detailed_partitions_map)

    def test_switch_zimaos_to_backend_purges_on_next_poll(self):
        client = _make_client(smb_source="zimaos")
        scan = MagicMock(return_value=[])
        with patch.object(client, "_make_request", side_effect=_fake_request), \
                patch.object(client, "_scan_windows_network_drives", scan), \
                patch.object(client, "get_user_authorized_shares", return_value=None):
            client.fetch_metrics()
            self.assertEqual(scan.call_count, 1)
            client.detailed_partitions_map["y:"] = {"is_network_drive": True}
            client.smb_source = "backend"
            client.fetch_metrics()
        self.assertEqual(scan.call_count, 1)
        self.assertNotIn("y:", client.detailed_partitions_map)

    def test_zimaos_still_scans_network_drives(self):
        for kwargs in ({}, {"smb_source": "zimaos"}):
            client = _make_client(**kwargs)
            scan = MagicMock(return_value=[])
            with patch.object(client, "_make_request", side_effect=_fake_request), \
                    patch.object(client, "_scan_windows_network_drives", scan), \
                    patch.object(client, "get_user_authorized_shares", return_value=None):
                client.fetch_metrics()
            scan.assert_called_once()

    def test_fetch_metrics_signature_preserved_for_phase7(self):
        sig = inspect.signature(zima_metrics_manager.ZimaMetricsClient.fetch_metrics)
        self.assertEqual(tuple(sig.parameters.keys()), ("self", "on_online_callback"))
        self.assertIsNone(sig.parameters["on_online_callback"].default)

    def test_core_service_syncs_smb_source_on_hit_and_new_instance(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "myserver_core_service.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        start = src.index("def get_cached_metrics_client(srv, active_u):")
        body = src[start:start + 12000]
        end = body.find("\ndef ", 10)
        body = body[:end] if end > 0 else body
        self.assertIn("config_manager.get_server_smb_source_config(srv)", body)
        self.assertIn("_active_metrics_client.smb_source = srv_smb_source", body)
        self.assertIn("smb_source=srv_smb_source", body)
        self.assertGreaterEqual(len(re.findall(r"srv_smb_source", body)), 3)


if __name__ == "__main__":
    unittest.main()

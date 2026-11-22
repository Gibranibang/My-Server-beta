import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

DESKTOP_ROOT = Path(__file__).resolve().parents[1]
if str(DESKTOP_ROOT) not in sys.path:
    sys.path.insert(0, str(DESKTOP_ROOT))

import myserver_core_service as core
import smb_mount_manager as smb
import zima_metrics_manager as zmm


class TestSmbServerSwitchAndDiskFixes(unittest.TestCase):
    def test_01_rebind_unmounts_all_servers_and_soft_mode_cleans_foreign_on_switch(self):
        cfg_srv_b = {
            "active_server_id": "srv_b",
            "servers": [
                {"id": "srv_a", "name": "Server A", "connections": [{"url": "http://192.168.1.11"}]},
                {"id": "srv_b", "name": "Server B", "connections": [{"url": "http://172.24.0.1"}]},
            ],
        }
        prev_last_sid = core._last_mounted_server_id
        try:
            core._last_mounted_server_id = "srv_a"
            with (
                patch.object(core.config_manager, "load_or_create_config", return_value=cfg_srv_b),
                patch.object(core.config_manager, "get_active_server", return_value=cfg_srv_b["servers"][1]),
                patch.object(
                    core.config_manager,
                    "get_server_smb_source_config",
                    return_value={"source": "zimaos", "username": "", "password": "", "allowed_disks": []},
                ),
                patch.object(core, "get_active_resolved_route", return_value=("http://172.24.0.1", "Remote")),
                patch.object(core, "_unmount_myserver_smb_drives", return_value=2) as mock_unmount,
                patch.object(core, "get_cached_metrics_client", return_value=None),
                patch.object(core, "_scan_live_drives_now", return_value=[]),
                patch.object(core.smb_mount_manager, "clear_smb_share_cache"),
                patch.object(core.smb_mount_manager, "invalidate_smb_host_cache"),
                patch.object(core.smb_mount_manager, "purge_smb_sessions"),
                patch.object(core.smb_mount_manager, "mount_all_smb_shares", return_value=(False, "no shares")),
                patch.object(core.smb_mount_manager, "get_last_mount_summary", return_value={"failed_shares": []}),
            ):
                # Even "server_recovered" must perform full unmount when last mounted server != active server
                core.rebind_storage_pipeline("server_recovered")

            self.assertGreaterEqual(mock_unmount.call_count, 1)
            _, kwargs = mock_unmount.call_args
            self.assertTrue(kwargs.get("include_all_servers"))
        finally:
            core._last_mounted_server_id = prev_last_sid
            core._set_smb_sync_state(False)

    def test_02_mount_all_cleans_foreign_drives_when_shares_empty_or_host_down(self):
        unmounted_calls = []

        def fake_wnet(drive):
            if drive == "Z:":
                return (0, r"\\192.168.1.11\Gdrive_01")
            return (2250, "")

        with (
            patch.object(smb.sys, "platform", "win32"),
            patch.object(smb, "_collect_configured_myserver_hosts", return_value={"192.168.1.11", "172.24.0.1"}),
            patch.object(smb, "_candidate_network_letters", return_value=["Z:", "Y:"]),
            patch.object(smb, "_get_wnet_remote_unc", side_effect=fake_wnet),
            patch.object(smb, "unmount_smb_share", side_effect=lambda d, **kw: unmounted_calls.append(d) or True),
            patch.object(smb, "_notify_windows_explorer_refresh"),
            patch.object(smb, "resolve_smb_host", return_value=None),
        ):
            ok, msg = smb.mount_all_smb_shares(host="172.24.0.1", known_server_hosts=["192.168.1.11"])

        self.assertFalse(ok)
        self.assertIn("Z:", unmounted_calls)

        unmounted_calls.clear()
        with (
            patch.object(smb.sys, "platform", "win32"),
            patch.object(smb, "_collect_configured_myserver_hosts", return_value={"192.168.1.11", "172.24.0.1"}),
            patch.object(smb, "_candidate_network_letters", return_value=["Z:"]),
            patch.object(smb, "_get_wnet_remote_unc", side_effect=fake_wnet),
            patch.object(smb, "unmount_smb_share", side_effect=lambda d, **kw: unmounted_calls.append(d) or True),
            patch.object(smb, "_notify_windows_explorer_refresh"),
            patch.object(smb, "resolve_smb_host", return_value="172.24.0.1"),
            patch.object(smb, "get_remote_smb_shares", return_value=[]),
        ):
            ok2, _ = smb.mount_all_smb_shares(host="172.24.0.1", known_server_hosts=["192.168.1.11"])

        self.assertFalse(ok2)
        self.assertIn("Z:", unmounted_calls)

    def test_03_mount_smb_share_retries_once_on_timeout_expired_and_succeeds(self):
        attempts = {"count": 0}

        def fake_subproc(cmd, **kwargs):
            if cmd[:2] == ["net.exe", "use"] and cmd[2] == "U:":
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise subprocess.TimeoutExpired(cmd=cmd, timeout=18.0)
                return MagicMock(returncode=0, stdout="The command completed successfully.", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch.object(smb, "resolve_smb_host", return_value="172.24.0.1"),
            patch.object(smb, "is_drive_letter_in_use", return_value=False),
            patch.object(smb, "_register_windows_credential"),
            patch.object(smb, "unmount_smb_share", return_value=True),
            patch.object(smb, "is_port_open", return_value=True),
            patch.object(smb, "_notify_windows_explorer_refresh"),
            patch.object(smb.time, "sleep"),
            patch.object(smb.subprocess, "run", side_effect=fake_subproc),
        ):
            ok, msg = smb.mount_smb_share(
                host="172.24.0.1",
                share_name="STIMI",
                username="Marcom",
                password="secret",
                drive_letter="U:",
                skip_ipc=True,
                notify_explorer=True,
            )

        self.assertTrue(ok, msg)
        self.assertEqual(attempts["count"], 2)

    def test_04_mount_all_tracks_partial_failures_for_deferred_retry(self):
        def fake_mount(host, share_name, **kwargs):
            if share_name == "STIMI":
                return False, "timed out after 18.0 seconds"
            return True, f"Mounted {share_name}"

        with (
            patch.object(smb.sys, "platform", "linux"),
            patch.object(smb, "resolve_smb_host", return_value="172.24.0.1"),
            patch.object(smb, "get_remote_smb_shares", return_value=["Marcom", "STIMI"]),
            patch.object(smb, "get_available_drive_letter", side_effect=["Z:", "Y:"]),
            patch.object(smb, "mount_smb_share", side_effect=fake_mount),
            patch.object(smb, "_register_windows_credential"),
            patch.object(smb.subprocess, "run", return_value=MagicMock(returncode=0)),
        ):
            ok, summary = smb.mount_all_smb_shares(host="172.24.0.1", username="Marcom", smb_source="backend")

        self.assertTrue(ok)
        self.assertIn("1 dari 2", summary)
        stats = smb.get_last_mount_summary()
        self.assertEqual(stats["mounted"], 1)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["failed_shares"], ["STIMI"])

    def test_05_zima_metrics_nonadmin_excludes_remote_and_deduplicates_shared_mount(self):
        client = zmm.ZimaMetricsClient(host="192.168.1.11", username="gibran", password="secret")
        client.token = "tok"
        client.is_admin = False

        mount_payload = {
            "data": [
                {
                    "mount_point": "/DATA",
                    "source": "/dev/nvme0n1p2",
                    "fstype": "ext4",
                    "size": 500 * 1024**3,
                    "used": 100 * 1024**3,
                },
                {
                    "mount_point": "/media/Gdrive_01",
                    "source": "rclone:gdrive",
                    "fstype": "fuse.rclone",
                    "size": 100 * 1024**4,
                    "used": 1 * 1024**3,
                },
            ]
        }
        samba_user_payload = {
            "data": [
                {
                    "username": "gibran",
                    "permissions": [
                        {"path": "/media/Gdrive_01", "read_only": False},
                        {"path": "/DATA/gibran1", "read_only": False},
                        {"path": "/DATA/gibran2", "read_only": False},
                    ],
                }
            ]
        }

        def fake_req(endpoint, method="GET", timeout=5.0):
            if endpoint.startswith("/v1/sys/utilization"):
                return {"data": {"cpu": {"percent": 12}, "mem": {"percent": 40, "total": 8 * 1024**3, "used": 3 * 1024**3}, "sys_disk": {"size": 500 * 1024**3, "used": 100 * 1024**3}}}
            if endpoint.startswith("/v2/local_storage/mount"):
                return mount_payload
            if endpoint.startswith("/v2/users/samba/user"):
                return samba_user_payload
            return None

        with (
            patch.object(client, "_make_request", side_effect=fake_req),
            patch.object(client, "is_server_reachable", return_value=True),
            patch.object(client, "_start_bg_storage_fetch"),
            patch.object(client, "_scan_windows_network_drives", return_value=[]),
            patch.object(client, "get_user_authorized_shares", return_value=["gdrive_01", "gibran1", "gibran2"]),
        ):
            res = client.fetch_metrics()

        self.assertEqual(res["storage_total_bytes"], 500 * 1024**3)
        self.assertEqual(res["storage_used_bytes"], 100 * 1024**3)
        parts_by_name = {p.get("raw_name"): p for p in res["storage_partitions"]}
        self.assertTrue(parts_by_name["Gdrive_01"]["is_remote"])
        self.assertFalse(parts_by_name["gibran1"]["is_remote"])
        self.assertFalse(parts_by_name["gibran2"]["is_remote"])


if __name__ == "__main__":
    unittest.main()

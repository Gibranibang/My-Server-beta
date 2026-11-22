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

    def test_06_mount_all_aborts_mid_loop_and_rolls_back_on_switch(self):
        state = {"aborted": False, "mounted": [], "unmounted": []}

        def fake_mount(host, share_name, **kwargs):
            drv = kwargs.get("drive_letter")
            state["mounted"].append((share_name, drv))
            if share_name == "Disk_A":
                # Simulate server switch arriving right after Disk_A finishes
                state["aborted"] = True
            return True, f"Mounted {share_name}"

        with (
            patch.object(smb.sys, "platform", "linux"),
            patch.object(smb, "resolve_smb_host", return_value="172.24.0.1"),
            patch.object(smb, "get_remote_smb_shares", return_value=["Disk_A", "Disk_B", "Disk_C"]),
            patch.object(smb, "get_available_drive_letter", side_effect=["Z:", "Y:", "X:"]),
            patch.object(smb, "mount_smb_share", side_effect=fake_mount),
            patch.object(smb, "unmount_smb_share", side_effect=lambda d, **kw: state["unmounted"].append(d) or True),
            patch.object(smb, "_register_windows_credential"),
            patch.object(smb.subprocess, "run", return_value=MagicMock(returncode=0)),
        ):
            ok, msg = smb.mount_all_smb_shares(
                host="172.24.0.1",
                username="Marcom",
                smb_source="backend",
                abort_check=lambda: state["aborted"],
            )

        self.assertFalse(ok)
        self.assertIn("dibatalkan", msg.lower())
        # Disk_B and Disk_C must NOT be attempted after abort, and Disk_A (Z:) rolled back
        self.assertEqual(state["mounted"], [("Disk_A", "Z:")])
        self.assertIn("Z:", state["unmounted"])

    def test_07_queued_switch_preserves_pre_unmounted_false_and_suppresses_auto_recovery(self):
        events = []

        def fake_rebind(reason="manual", force_refresh=True, pre_unmounted=False, expected_gen=None):
            events.append((reason, force_refresh, pre_unmounted, expected_gen))
            return []

        core._smb_pipeline_lock.acquire()
        with core._pending_rebind_lock:
            core._pending_rebind_reason = None
            core._pending_rebind_pre_unmounted = False
            core._pending_rebind_gen = None
        try:
            gen = core._bump_smb_pipeline_epoch(suppress_auto_sec=10.0)
            self.assertTrue(core._is_smb_auto_suppressed())

            # Queue user-priority switch_server while lock is busy
            core.rebind_storage_pipeline("switch_server", pre_unmounted=False, expected_gen=gen)
            # Background server_recovered must NOT overwrite switch_server!
            core.rebind_storage_pipeline("server_recovered", pre_unmounted=False)

            with core._pending_rebind_lock:
                self.assertEqual(core._pending_rebind_reason, "switch_server")
                self.assertFalse(core._pending_rebind_pre_unmounted)
                self.assertEqual(core._pending_rebind_gen, gen)
        finally:
            with core._pending_rebind_lock:
                core._pending_rebind_reason = None
                core._pending_rebind_pre_unmounted = False
                core._pending_rebind_gen = None
            core._smb_pipeline_lock.release()
            with core._smb_pipeline_gen_lock:
                core._smb_suppressed_until_ts = 0.0
            core._set_smb_sync_state(False)

        # Also check stale expected_gen exits early without touching lock or pipeline
        stale_gen = gen - 1
        self.assertEqual(core.rebind_storage_pipeline("switch_server", expected_gen=stale_gen), [])
        self.assertEqual(events, [])

    def test_08_unmount_smb_share_cleans_1201_red_x_and_parallel_unmount(self):
        # 1201 (ERROR_CONNECTION_UNAVAIL / Red-X) must clean DosLanman even if WNetCancelConnection2W times out
        with (
            patch.object(smb.sys, "platform", "win32"),
            patch.object(smb, "_get_wnet_remote_unc", return_value=(1201, r"\\172.24.0.1\STIMI")),
            patch.object(smb, "_cancel_connection_safe", return_value=(False, True)),
            patch.object(smb.subprocess, "run", return_value=MagicMock(returncode=2, stdout="", stderr="")),
            patch.object(smb, "_remove_dos_lanman_device", return_value=True) as mock_dos,
            patch.object(smb, "_notify_windows_explorer_refresh"),
        ):
            ok = smb.unmount_smb_share("U:")

        self.assertTrue(ok)
        mock_dos.assert_called_once_with("U:")

        # Parallel unmount across multiple stale drives cleans all matching drives safely
        wnet_map = {
            "U:": (1201, r"\\172.24.0.1\STIMI"),
            "V:": (0, r"\\172.24.0.1\Marcom"),
            "W:": (0, r"\\corp-nas\Other"),
        }
        removed = []

        class FakeK32:
            @staticmethod
            def GetDriveTypeW(path):
                return 4

        fake_windll = MagicMock()
        fake_windll.kernel32 = FakeK32()
        with (
            patch.object(smb.sys, "platform", "win32"),
            patch.object(smb.ctypes, "windll", fake_windll),
            patch.object(smb, "_candidate_network_letters", return_value=["U:", "V:", "W:"]),
            patch.object(smb, "_get_wnet_remote_unc", side_effect=lambda d: wnet_map.get(d, (-1, ""))),
            patch.object(smb, "unmount_smb_share", side_effect=lambda d, notify_explorer=True: removed.append(d) or True),
            patch.object(smb, "_notify_windows_explorer_refresh") as mock_notif,
        ):
            cnt = smb.unmount_all_smb_shares(allowed_hosts={"172.24.0.1"})

        self.assertEqual(cnt, 2)
        self.assertEqual(sorted(removed), ["U:", "V:"])
        mock_notif.assert_called_once()

    def test_09_switch_server_offloads_easytier_restart_off_http_handler(self):
        import io
        import json

        cfg_data = {
            "active_server_id": "srv_a",
            "remote_mode": "easytier",
            "servers": [
                {"id": "srv_a", "name": "Srv A", "remote_id": "rid-aaa", "connections": [{"url": "http://192.168.1.11"}]},
                {"id": "srv_b", "name": "Srv B", "remote_id": "rid-bbb", "connections": [{"url": "http://172.24.0.1"}]},
            ],
        }
        et_mock = MagicMock()
        et_mock.is_running.return_value = True
        et_mock.get_remote_id.return_value = "rid-aaa"

        handler = core.CoreApiHandler.__new__(core.CoreApiHandler)
        handler.path = "/api/switch_server"
        handler.rfile = io.BytesIO(json.dumps({"serverId": "srv_b"}).encode("utf-8"))
        handler.headers = {"Content-Length": str(len(json.dumps({"serverId": "srv_b"})))}
        sent = {}
        handler._send_json = lambda obj, code=200: sent.update({"obj": obj, "code": code})

        spawned_targets = []

        class FakeThread:
            def __init__(self, target=None, daemon=None, **kw):
                self._target = target

            def start(self):
                spawned_targets.append(self._target)

        with (
            patch.object(core.config_manager, "load_or_create_config", return_value=cfg_data),
            patch.object(core.config_manager, "save_config"),
            patch.object(core.config_manager, "get_server_smb_source_config", return_value={"source": "zimaos"}),
            patch.object(core, "get_server_details_data", return_value={"activeServerId": "srv_b"}),
            patch.object(core, "invalidate_active_route_cache"),
            patch.object(core.easytier_manager, "get_easytier_manager", return_value=et_mock),
            patch.object(core.threading, "Thread", FakeThread),
        ):
            handler.do_POST()

        # HTTP response must NOT wait for et_mock.start_easytier synchronously
        et_mock.start_easytier.assert_not_called()
        self.assertEqual(sent.get("code"), 200)
        self.assertGreaterEqual(len(spawned_targets), 2)
        with core._smb_pipeline_gen_lock:
            core._smb_suppressed_until_ts = 0.0
        core._set_smb_sync_state(False)

    def test_10_wnet_scan_cache_avoids_repeated_mpr_calls_when_bitmask_unchanged(self):
        import ctypes as real_ctypes
        import types

        client = zmm.ZimaMetricsClient(host="192.168.1.11", username="gibran", password="secret")
        client.is_admin = True
        client.detailed_partitions_map = {
            "gdrive_01": {
                "name": "Gdrive_01",
                "total_bytes": 1000,
                "used_bytes": 200,
                "avail_bytes": 800,
                "fs_type": "fuse.rclone",
            }
        }
        wnet_calls = []

        class FakeK32:
            current_mask = 1 << 25

            @classmethod
            def GetLogicalDrives(cls):
                return cls.current_mask

            @staticmethod
            def GetDriveTypeW(path):
                return 4

        class FakeMpr:
            @staticmethod
            def WNetGetConnectionW(drv, buf, sz):
                wnet_calls.append(drv)
                buf.value = r"\\192.168.1.11\Gdrive_01"
                return 0

        fake_windll = types.SimpleNamespace(kernel32=FakeK32(), mpr=FakeMpr())
        with patch.object(zmm.os, "name", "nt"), patch.object(zmm.ctypes, "windll", fake_windll, create=True):
            # Poll 1: hits WNetGetConnectionW once
            r1 = client._scan_windows_network_drives(server_connections=[{"url": "http://192.168.1.11"}])
            # Poll 2 & 3 with same bitmask: served from 15s cache, ZERO extra WNetGetConnectionW calls
            r2 = client._scan_windows_network_drives(server_connections=[{"url": "http://192.168.1.11"}])
            self.assertEqual(len(wnet_calls), 1)
            self.assertEqual(len(r1), 1)
            self.assertEqual(len(r2), 1)
            # Bitmask change forces immediate rescan
            FakeK32.current_mask = (1 << 25) | (1 << 24)
            client._scan_windows_network_drives(server_connections=[{"url": "http://192.168.1.11"}])
            self.assertEqual(len(wnet_calls), 3)

    def test_11_run_subprocess_bounded_aborts_on_pipe_hang_within_deadline(self):
        import threading
        import time

        unblock = threading.Event()

        def hanging_subproc(*args, **kwargs):
            unblock.wait(timeout=5.0)
            return MagicMock(returncode=0, stdout="", stderr="")

        t0 = time.monotonic()
        with patch.object(smb.subprocess, "run", side_effect=hanging_subproc):
            with self.assertRaises(subprocess.TimeoutExpired):
                smb._run_subprocess_bounded(["net.exe", "use", "X:"], timeout_sec=0.2)
        elapsed = time.monotonic() - t0
        unblock.set()
        self.assertLess(elapsed, 2.5)


if __name__ == "__main__":
    unittest.main()

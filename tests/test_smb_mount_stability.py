import ctypes
import os
import sys
import types
import unittest
from unittest.mock import patch


def _install_linux_win_stubs():
    """Install minimal Windows ctypes stubs when running unit tests on Linux."""
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


_install_linux_win_stubs()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config_manager  # noqa: E402
import easytier_manager  # noqa: E402
import smb_mount_manager  # noqa: E402


class TestResolveSmbHostStability(unittest.TestCase):
    def setUp(self):
        if hasattr(smb_mount_manager, "invalidate_smb_host_cache"):
            smb_mount_manager.invalidate_smb_host_cache()
        smb_mount_manager.clear_smb_share_cache()
        self.cfg_patch = patch.object(
            config_manager,
            "load_or_create_config",
            return_value={"servers": [], "active_server_id": None},
        )
        self.cfg_patch.start()
        self.et_patch = patch.object(
            easytier_manager,
            "get_easytier_manager",
            return_value=types.SimpleNamespace(
                is_running=lambda: False,
                is_tun_active=lambda: True,
            ),
        )
        self.et_patch.start()

    def tearDown(self):
        self.et_patch.stop()
        self.cfg_patch.stop()
        if hasattr(smb_mount_manager, "invalidate_smb_host_cache"):
            smb_mount_manager.invalidate_smb_host_cache()

    def test_01_domain_route_lan_first_then_vpn_fallback(self):
        """SMBS-05 / D-09.1: Domain route probes LAN (<=0.5s) before VPN and falls back to VPN only if LAN fails."""
        probed = []

        def fake_port_open(host, port=445, timeout=1.0):
            probed.append((host, port, timeout))
            return host in ("192.168.1.50", "10.126.126.1")

        with patch.object(smb_mount_manager, "is_port_open", side_effect=fake_port_open):
            resolved = smb_mount_manager.resolve_smb_host(
                "nas.example.com",
                server_connections=[{"url": "http://192.168.1.50:80"}],
                is_domain_route=True,
                zerotier_ip="10.126.126.1",
            )

        self.assertEqual(resolved, "192.168.1.50")
        self.assertEqual(len(probed), 1)
        self.assertEqual(probed[0][0], "192.168.1.50")
        self.assertEqual(probed[0][1], 445)
        self.assertLessEqual(probed[0][2], 0.5)

        # Fallback to VPN when LAN probe fails
        smb_mount_manager.invalidate_smb_host_cache()
        probed.clear()

        def fake_port_open_vpn_only(host, port=445, timeout=1.0):
            probed.append((host, port, timeout))
            return host == "10.126.126.1"

        with patch.object(smb_mount_manager, "is_port_open", side_effect=fake_port_open_vpn_only):
            resolved_vpn = smb_mount_manager.resolve_smb_host(
                "nas.example.com",
                server_connections=[{"url": "http://192.168.1.50:80"}],
                is_domain_route=True,
                zerotier_ip="10.126.126.1",
            )

        self.assertEqual(resolved_vpn, "10.126.126.1")
        self.assertEqual([p[0] for p in probed], ["192.168.1.50", "10.126.126.1"])

    def test_02_resolve_smb_host_15s_cache_and_invalidation(self):
        """SMBS-05 / D-09.2: Repeated calls within max_age_seconds hit cache; invalidate_smb_host_cache() and max_age_seconds=0 force re-probe."""
        calls = []

        def fake_port_open(host, port=445, timeout=1.0):
            calls.append(host)
            return host == "192.168.1.50"

        with patch.object(smb_mount_manager, "is_port_open", side_effect=fake_port_open):
            first = smb_mount_manager.resolve_smb_host(
                "nas.example.com",
                server_connections=[{"url": "http://192.168.1.50:80"}],
                is_domain_route=True,
                zerotier_ip="10.126.126.1",
                max_age_seconds=15,
            )
            second = smb_mount_manager.resolve_smb_host(
                "nas.example.com",
                server_connections=[{"url": "http://192.168.1.50:80"}],
                is_domain_route=True,
                zerotier_ip="10.126.126.1",
                max_age_seconds=15,
            )
            self.assertEqual(first, "192.168.1.50")
            self.assertEqual(second, "192.168.1.50")
            self.assertEqual(len(calls), 1)

            smb_mount_manager.invalidate_smb_host_cache()
            third = smb_mount_manager.resolve_smb_host(
                "nas.example.com",
                server_connections=[{"url": "http://192.168.1.50:80"}],
                is_domain_route=True,
                zerotier_ip="10.126.126.1",
                max_age_seconds=15,
            )
            self.assertEqual(third, "192.168.1.50")
            self.assertEqual(len(calls), 2)

            fourth = smb_mount_manager.resolve_smb_host(
                "nas.example.com",
                server_connections=[{"url": "http://192.168.1.50:80"}],
                is_domain_route=True,
                zerotier_ip="10.126.126.1",
                max_age_seconds=0,
            )
            self.assertEqual(fourth, "192.168.1.50")
            self.assertEqual(len(calls), 3)

    def test_03_easytier_no_tun_excludes_10_126_126_candidates(self):
        """SMBS-06 / D-10.2 / T-07-05: EasyTier running with tun_active=False excludes 10.126.126.x from all probes."""
        probed_hosts = []

        def fake_port_open(host, port=445, timeout=1.0):
            probed_hosts.append(host)
            return host == "10.147.20.5"

        no_tun_mgr = types.SimpleNamespace(is_running=lambda: True, is_tun_active=lambda: False)
        cfg_with_et = {
            "servers": [
                {
                    "id": "srv1",
                    "zerotier_virtual_ip": "10.147.20.5",
                    "easytier_virtual_ip": "10.126.126.1",
                }
            ],
            "active_server_id": "srv1",
        }

        with patch.object(easytier_manager, "get_easytier_manager", return_value=no_tun_mgr), \
             patch.object(config_manager, "load_or_create_config", return_value=cfg_with_et), \
             patch.object(smb_mount_manager, "is_port_open", side_effect=fake_port_open):
            # Case A: Domain route with EasyTier VIP as zerotier_ip + active_srv having both ET and ZT
            res_dom = smb_mount_manager.resolve_smb_host(
                "nas.example.com",
                server_connections=[{"url": "http://192.168.1.50:80"}],
                is_domain_route=True,
                zerotier_ip="10.126.126.1",
            )
            self.assertEqual(res_dom, "10.147.20.5")
            self.assertFalse(any(h.startswith("10.126.126.") for h in probed_hosts))

            # Case B: Direct EasyTier IP passed as target_host -> skips 10.126.126.1, only falls back to ZeroTier 10.147.20.5
            smb_mount_manager.invalidate_smb_host_cache()
            probed_hosts.clear()
            with patch.object(smb_mount_manager, "is_port_open", side_effect=lambda h, p=445, timeout=1.0: probed_hosts.append(h) or False):
                res_direct = smb_mount_manager.resolve_smb_host(
                    "10.126.126.1",
                    server_connections=[],
                    is_domain_route=False,
                    zerotier_ip="10.126.126.1",
                )
            self.assertIsNone(res_direct)
            self.assertEqual(probed_hosts, ["10.147.20.5"])

            # Case C: Direct EasyTier IP with no ZeroTier/LAN configured -> zero probes, fail-fast None
            smb_mount_manager.invalidate_smb_host_cache()
            probed_hosts.clear()
            with patch.object(config_manager, "load_or_create_config", return_value={"servers": [], "active_server_id": None}), \
                 patch.object(smb_mount_manager, "is_port_open", side_effect=lambda h, p=445, timeout=1.0: probed_hosts.append(h) or False):
                res_none = smb_mount_manager.resolve_smb_host(
                    "10.126.126.1",
                    server_connections=[],
                    is_domain_route=False,
                    zerotier_ip="10.126.126.1",
                )
            self.assertIsNone(res_none)
            self.assertEqual(probed_hosts, [])

    def test_04_fail_fast_none_and_caller_guards(self):
        """SMBS-05 / D-09.3: Returns None when all port-445 probes fail and callers fail fast without net.exe/cmdkey/os.startfile."""
        with patch.object(smb_mount_manager, "is_port_open", return_value=False):
            res_dom = smb_mount_manager.resolve_smb_host(
                "nas.example.com",
                server_connections=[{"url": "http://192.168.1.50:80"}],
                is_domain_route=True,
                zerotier_ip="10.126.126.1",
            )
            self.assertIsNone(res_dom)

            smb_mount_manager.invalidate_smb_host_cache()
            res_lan = smb_mount_manager.resolve_smb_host(
                "192.168.1.50",
                server_connections=[{"url": "http://192.168.1.51:80"}],
                is_domain_route=False,
                zerotier_ip="10.147.20.5",
            )
            self.assertIsNone(res_lan)

            with patch.object(smb_mount_manager.subprocess, "run", side_effect=AssertionError("subprocess.run must NOT be called")):
                ok_one, msg_one = smb_mount_manager.mount_smb_share(
                    host="192.168.1.50",
                    share_name="DATA",
                    drive_letter="Z:",
                )
                self.assertFalse(ok_one)
                self.assertIn("445", msg_one)

                with patch.object(smb_mount_manager, "get_remote_smb_shares", side_effect=AssertionError("get_remote_smb_shares must NOT be called")):
                    ok_all, msg_all = smb_mount_manager.mount_all_smb_shares(
                        host="192.168.1.50",
                    )
                    self.assertFalse(ok_all)
                    self.assertIn("445", msg_all)

            res_open = smb_mount_manager.open_unc_root_in_explorer("192.168.1.50")
            self.assertIsInstance(res_open, tuple)
            self.assertFalse(res_open[0])


class TestSmbMountStabilityTask2(unittest.TestCase):
    def setUp(self):
        smb_mount_manager.invalidate_smb_host_cache()
        smb_mount_manager.clear_smb_share_cache()
        smb_mount_manager._cached_1219_alias.clear()

    def tearDown(self):
        smb_mount_manager._cached_1219_alias.clear()

    def test_01_targeted_per_drive_sh_change_notify(self):
        """SMBS-02 / D-05.1: SHChangeNotify uses SHCNE_DRIVEREMOVED/SHCNE_DRIVEADD + SHCNF_PATHW per drive, never 0x08000000."""
        notify_calls = []

        class FakeShell32:
            @staticmethod
            def SHChangeNotify(event_id, flags, item1, item2):
                val = getattr(item1, "value", item1) if item1 is not None else None
                notify_calls.append((event_id, flags, val, item2))

        fake_windll = types.SimpleNamespace(shell32=FakeShell32(), kernel32=ctypes.windll.kernel32, mpr=ctypes.windll.mpr)
        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager.ctypes, "windll", fake_windll):
            smb_mount_manager._notify_windows_explorer_refresh(added_drives=[], removed_drives=[])
            self.assertEqual(notify_calls, [])

            smb_mount_manager._notify_windows_explorer_refresh(
                added_drives=["Z:", "z:"],
                removed_drives=["Y"],
            )
        self.assertEqual(len(notify_calls), 2)
        self.assertEqual(notify_calls[0][0], smb_mount_manager.SHCNE_DRIVEREMOVED)
        self.assertEqual(notify_calls[0][1], smb_mount_manager.SHCNF_PATHW)
        self.assertEqual(notify_calls[0][2], "Y:\\")
        self.assertEqual(notify_calls[1][0], smb_mount_manager.SHCNE_DRIVEADD)
        self.assertEqual(notify_calls[1][1], smb_mount_manager.SHCNF_PATHW)
        self.assertEqual(notify_calls[1][2], "Z:\\")
        self.assertTrue(all(ev != 0x08000000 for ev, _, _, _ in notify_calls))

    def test_02_scoped_unmount_and_purge_never_touch_foreign_or_1203_foreign(self):
        """SMBS-02 / D-05.2 / T-07-06: Foreign corp-nas and foreign 1203 orphans are never unmounted or purged."""
        wnet_table = {
            "Z:": (0, r"\\192.168.1.50\DATA"),
            "X:": (0, r"\\corp-nas\Finance"),
            "W:": (1203, r"\\corp-nas\Old"),
        }
        unmounted = []

        def fake_get_wnet(d):
            return wnet_table.get(d, (-1, ""))

        class FakeK32:
            @staticmethod
            def GetDriveTypeW(path):
                return 4

        fake_windll = types.SimpleNamespace(kernel32=FakeK32(), mpr=ctypes.windll.mpr, shell32=ctypes.windll.shell32)
        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager.ctypes, "windll", fake_windll), \
             patch.object(smb_mount_manager, "_candidate_network_letters", return_value=["Z:", "X:", "W:"]), \
             patch.object(smb_mount_manager, "_get_wnet_remote_unc", side_effect=fake_get_wnet), \
             patch.object(smb_mount_manager, "unmount_smb_share", side_effect=lambda d, notify_explorer=True: unmounted.append(d) or True), \
             patch.object(smb_mount_manager, "_notify_windows_explorer_refresh") as mock_notif:
            count_empty = smb_mount_manager.unmount_all_smb_shares(allowed_hosts=set())
            self.assertEqual(count_empty, 0)
            self.assertEqual(unmounted, [])

            count_scoped = smb_mount_manager.unmount_all_smb_shares(allowed_hosts={"192.168.1.50"})
            self.assertEqual(count_scoped, 1)
            self.assertEqual(unmounted, ["Z:"])
            mock_notif.assert_called_once_with(removed_drives=["Z:"])

        # Also test purge_smb_sessions scoping (even with code 1203 on W:)
        canceled = []
        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager, "_candidate_network_letters", return_value=["Z:", "X:", "W:"]), \
             patch.object(smb_mount_manager, "_get_wnet_remote_unc", side_effect=fake_get_wnet), \
             patch.object(smb_mount_manager, "_reverse_lookup_fast", return_value=""), \
             patch.object(smb_mount_manager, "_cancel_connection_safe", side_effect=lambda tgt, force=True, timeout=1.5: canceled.append(tgt) or (True, False)), \
             patch.object(smb_mount_manager, "_remove_dos_lanman_device"), \
             patch.object(smb_mount_manager, "_delete_windows_credential"), \
             patch.object(smb_mount_manager.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout="")), \
             patch.object(smb_mount_manager, "_notify_windows_explorer_refresh") as mock_notif:
            smb_mount_manager.purge_smb_sessions(["192.168.1.50"], notify_explorer=False)
            self.assertEqual(canceled, ["Z:"])
            mock_notif.assert_not_called()

    def test_03_guarded_define_dos_device_w_on_timeout_vs_1203(self):
        """SMBS-02 / D-05.3 / T-07-06: Skip _remove_dos_lanman_device on cancel timeout unless 1203 orphan."""
        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(0, r"\\192.168.1.50\DATA")), \
             patch.object(smb_mount_manager, "_cancel_connection_safe", return_value=(False, True)), \
             patch.object(smb_mount_manager.subprocess, "run", return_value=types.SimpleNamespace(returncode=2, stdout="", stderr="busy")), \
             patch.object(smb_mount_manager, "_remove_dos_lanman_device") as mock_dos, \
             patch.object(smb_mount_manager, "_notify_windows_explorer_refresh"):
            ok = smb_mount_manager.unmount_smb_share("Z:")
            self.assertFalse(ok)
            mock_dos.assert_not_called()

        # Case B: initial code == 1203 -> permitted
        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(1203, "")), \
             patch.object(smb_mount_manager, "_cancel_connection_safe", return_value=(False, False)), \
             patch.object(smb_mount_manager.subprocess, "run", return_value=types.SimpleNamespace(returncode=2, stdout="", stderr="")), \
             patch.object(smb_mount_manager, "_remove_dos_lanman_device", return_value=True) as mock_dos, \
             patch.object(smb_mount_manager, "_notify_windows_explorer_refresh"):
            ok = smb_mount_manager.unmount_smb_share("Z:")
            self.assertTrue(ok)
            mock_dos.assert_called_once_with("Z:")

    def test_04_soft_mode_evicts_stale_myserver_drive_never_touches_foreign(self):
        """SMBS-01 / D-02: mount_all_smb_shares evicts stale MyServer drive Z: and remounts Z:, leaves X: corp-nas untouched."""
        wnet_table = {
            "Z:": (0, r"\\192.168.1.50\DATA"),
            "X:": (0, r"\\corp-nas\Finance"),
        }
        unmounted = []
        mounted_calls = []

        def fake_get_wnet(d):
            if d in unmounted:
                return (-1, "")
            return wnet_table.get(d, (-1, ""))

        class FakeK32:
            @staticmethod
            def GetDriveTypeW(path):
                return 4

            @staticmethod
            def GetLogicalDrives():
                # C(2) + X(23); Z(25) becomes free when unmounted
                mask = (1 << 2) | (1 << 23)
                if "Z:" not in unmounted:
                    mask |= (1 << 25)
                return mask

        fake_windll = types.SimpleNamespace(kernel32=FakeK32(), mpr=ctypes.windll.mpr, shell32=ctypes.windll.shell32)
        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager.ctypes, "windll", fake_windll), \
             patch.object(smb_mount_manager, "resolve_smb_host", return_value="10.126.126.1"), \
             patch.object(smb_mount_manager, "get_remote_smb_shares", return_value=["DATA"]), \
             patch.object(smb_mount_manager, "_candidate_network_letters", return_value=["Z:", "X:"]), \
             patch.object(smb_mount_manager, "_get_wnet_remote_unc", side_effect=fake_get_wnet), \
             patch.object(smb_mount_manager, "is_port_open", return_value=True), \
             patch.object(smb_mount_manager, "_get_dos_lanman_target", return_value=""), \
             patch.object(smb_mount_manager, "_register_windows_credential"), \
             patch.object(smb_mount_manager.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)), \
             patch.object(smb_mount_manager, "unmount_smb_share", side_effect=lambda d, notify_explorer=True: unmounted.append(d) or True), \
             patch.object(smb_mount_manager, "mount_smb_share", side_effect=lambda **kw: mounted_calls.append(kw) or (True, "ok")), \
             patch.object(smb_mount_manager, "_notify_windows_explorer_refresh") as mock_notif:
            ok, _ = smb_mount_manager.mount_all_smb_shares(
                host="10.126.126.1",
                known_server_hosts={"192.168.1.50", "10.126.126.1"},
            )

        self.assertTrue(ok)
        self.assertEqual(unmounted, ["Z:"])
        self.assertEqual(len(mounted_calls), 1)
        self.assertEqual(mounted_calls[0]["drive_letter"], "Z:")
        self.assertEqual(mounted_calls[0]["host"], "10.126.126.1")
        mock_notif.assert_called_once_with(added_drives=["Z:"], removed_drives=["Z:"])

    def test_05_lan_safe_error_1219_aliases_no_public_dns_and_export(self):
        """SMBS-02 / D-05.4 / T-07-07: Error-1219 aliases exclude nip.io/sslip.io by default and export get_active_1219_aliases()."""
        smb_mount_manager._cached_1219_alias["192.168.1.50"] = "192.168.1.51"
        exported = smb_mount_manager.get_active_1219_aliases()
        self.assertEqual(exported, {"192.168.1.50": "192.168.1.51"})
        exported["x"] = "y"
        self.assertNotIn("x", smb_mount_manager._cached_1219_alias)

        with patch.object(smb_mount_manager, "_reverse_lookup_fast", return_value=""), \
             patch.object(smb_mount_manager, "is_port_open", side_effect=lambda h, p=445, timeout=0.5: h == "192.168.1.51"), \
             patch.object(smb_mount_manager.socket, "gethostbyname", side_effect=AssertionError("public wildcard DNS must not be queried")):
            aliases = smb_mount_manager._get_dynamic_host_aliases(
                "192.168.1.50",
                alternate_local_hosts=["192.168.1.51"],
            )
        self.assertEqual(aliases, ["192.168.1.51"])
        self.assertFalse(any("nip.io" in a or "sslip.io" in a for a in aliases))

    def test_06_o1_drive_letter_helpers_never_call_wnet(self):
        """SMBS-03 / D-06.3: is_drive_letter_in_use / get_available_drive_letters / get_available_drive_letter never invoke _get_wnet_remote_unc."""
        class FakeK32:
            @staticmethod
            def GetLogicalDrives():
                # C:(2) & Z:(25) used
                return (1 << 2) | (1 << 25)

        fake_windll = types.SimpleNamespace(kernel32=FakeK32(), mpr=ctypes.windll.mpr, shell32=ctypes.windll.shell32)
        with patch.object(smb_mount_manager.ctypes, "windll", fake_windll), \
             patch.object(smb_mount_manager, "_get_dos_lanman_target", return_value=""), \
             patch.object(smb_mount_manager, "_get_wnet_remote_unc", side_effect=AssertionError("_get_wnet_remote_unc must never be called")):
            self.assertTrue(smb_mount_manager.is_drive_letter_in_use("Z:"))
            self.assertFalse(smb_mount_manager.is_drive_letter_in_use("Y:"))
            avail = smb_mount_manager.get_available_drive_letters(exclude_letters={"Y:"})
            self.assertNotIn("Z:", avail)
            self.assertNotIn("Y:", avail)
            self.assertEqual(avail[0], "X:")
            best = smb_mount_manager.get_available_drive_letter(preferred="Z:")
            self.assertEqual(best, "Y:")

    def test_07_explorer_launch_port_445_preflight_and_tuple_return(self):
        """SMBS-02 / D-05.5 / T-07-07: open_drive_in_explorer and open_unc_root_in_explorer preflight port 445 <=0.8s and return (bool, str)."""
        timeouts_seen = []

        def fake_is_port(h, p=445, timeout=0.8):
            timeouts_seen.append(timeout)
            return h == "192.168.1.50"

        with patch.object(smb_mount_manager, "is_port_open", side_effect=fake_is_port):
            self.assertFalse(smb_mount_manager.preflight_smb_port("10.0.0.9", timeout=5.0))
            self.assertEqual(timeouts_seen[-1], 0.8)

        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(1203, "")), \
             patch.object(smb_mount_manager.os, "startfile", create=True, side_effect=AssertionError("startfile must not be called")):
            ok, msg = smb_mount_manager.open_drive_in_explorer("Z:")
            self.assertFalse(ok)
            self.assertIn("Z:", msg)

        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(0, r"\\192.168.1.50\DATA")), \
             patch.object(smb_mount_manager, "preflight_smb_port", return_value=False), \
             patch.object(smb_mount_manager.os, "startfile", create=True, side_effect=AssertionError("startfile must not be called")):
            ok, msg = smb_mount_manager.open_drive_in_explorer("Z:")
            self.assertFalse(ok)
            self.assertIn("445", msg)

        opened = []
        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(0, r"\\192.168.1.50\DATA")), \
             patch.object(smb_mount_manager, "preflight_smb_port", return_value=True), \
             patch.object(smb_mount_manager.os, "startfile", create=True, side_effect=lambda p: opened.append(p)):
            ok, _ = smb_mount_manager.open_drive_in_explorer("Z:")
            self.assertTrue(ok)
            self.assertEqual(opened, ["Z:\\"])

        with patch.object(smb_mount_manager.sys, "platform", "win32"), \
             patch.object(smb_mount_manager, "resolve_smb_host", return_value="192.168.1.50"), \
             patch.object(smb_mount_manager, "preflight_smb_port", return_value=False), \
             patch.object(smb_mount_manager.os, "startfile", create=True, side_effect=AssertionError("startfile must not be called")):
            ok, msg = smb_mount_manager.open_unc_root_in_explorer("192.168.1.50")
            self.assertFalse(ok)
            self.assertIn("445", msg)

    def test_08_ast_no_global_sh_flush_or_wnet_in_drive_helpers(self):
        import ast
        src_path = os.path.join(REPO_ROOT, "smb_mount_manager.py")
        with open(src_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        notif_consts = {n.value for n in ast.walk(fns["_notify_windows_explorer_refresh"]) if isinstance(n, ast.Constant)}
        self.assertNotIn(0x08000000, notif_consts)
        for fn in ("is_drive_letter_in_use", "get_available_drive_letters", "get_available_drive_letter"):
            names = {n.id for n in ast.walk(fns[fn]) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(fns[fn]) if isinstance(n, ast.Attribute)}
            self.assertNotIn("_get_wnet_remote_unc", names)
            self.assertNotIn("WNetGetConnectionW", attrs)


if __name__ == "__main__":
    unittest.main()

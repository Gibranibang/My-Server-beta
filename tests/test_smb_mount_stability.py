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


if __name__ == "__main__":
    unittest.main()

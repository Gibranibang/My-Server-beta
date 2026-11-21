"""
Tests for EasyTierManager functionality and regression coverage.
"""

import unittest
from unittest.mock import patch, MagicMock
import easytier_manager


class TestEasyTierManager(unittest.TestCase):
    def setUp(self):
        self.mgr = easytier_manager.EasyTierManager()

    def test_derive_easytier_params(self):
        res = easytier_manager.derive_easytier_params("1a2b3c4d5e6f7089")
        self.assertEqual(res["network_name"], "1a2b3c4d5e6f7089")
        self.assertEqual(res["network_secret"], "1a2b3c4d5e6f7089")
        self.assertTrue(len(res["network_hash"]) == 64)

    def test_get_node_info_reads_virtual_ipv4(self):
        mock_cli_out = {
            "virtual_ipv4": "10.126.126.15/24",
            "hostname": "TestNode",
            "peer_id": "12345"
        }
        with patch.object(self.mgr, "is_running", return_value=True), \
             patch.object(self.mgr, "run_cli", return_value=(mock_cli_out, None)):
            info = self.mgr.get_node_info()
            self.assertEqual(info["virtual_ipv4"], "10.126.126.15")
            self.assertEqual(info["hostname"], "TestNode")
            self.assertEqual(info["node_id"], "12345")

    def test_get_peers_and_routes_handles_items_dict(self):
        mock_peers_data = {
            "items": [
                {"peer_id": "99", "ipv4_addr": "10.126.126.1/24"}
            ]
        }
        with patch.object(self.mgr, "is_running", return_value=True), \
             patch.object(self.mgr, "run_cli", return_value=(mock_peers_data, None)):
            peers = self.mgr.get_peers()
            self.assertEqual(len(peers), 1)
            self.assertEqual(peers[0]["peer_id"], "99")

            routes = self.mgr.get_routes()
            self.assertEqual(len(routes), 1)
            self.assertEqual(routes[0]["ipv4_addr"], "10.126.126.1/24")

            peer_ip = self.mgr.get_peer_ip()
            self.assertEqual(peer_ip, "10.126.126.1")

    def test_start_easytier_dhcp_and_no_tun_flags(self):
        with patch.object(self.mgr, "is_available", return_value=True), \
             patch.object(self.mgr, "is_running", return_value=False), \
             patch.object(self.mgr, "_kill_orphaned_daemon"), \
             patch.object(self.mgr, "_is_rpc_reachable", return_value=True), \
             patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            # Start with use_no_tun and default IP (should request 10.126.126.2/24 with -d and --no-tun)
            ok, msg = self.mgr.start_easytier(
                remote_id="1a2b3c4d5e6f7089",
                use_no_tun=True,
                external_node="tcp://relay.example.com:11010"
            )
            self.assertTrue(ok)
            cmd_called = mock_popen.call_args[0][0]
            self.assertIn("--no-tun", cmd_called)
            self.assertIn("-d", cmd_called)
            self.assertIn("-i", cmd_called)
            self.assertIn("10.126.126.2/24", cmd_called)
            self.assertIn("-l", cmd_called)
            self.assertIn("--external-node", cmd_called)
            self.assertIn("tcp://relay.example.com:11010", cmd_called)

    def test_run_cli_uses_rpc_portal_and_output_flags(self):
        with patch.object(self.mgr, "is_available", return_value=True), \
             patch.object(self.mgr, "_is_rpc_reachable", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = '{"test": 123}'
            mock_run.return_value = mock_res

            res, err = self.mgr.run_cli(["peer"])
            self.assertEqual(res, {"test": 123})
            self.assertIsNone(err)
            cmd_called = mock_run.call_args[0][0]
            self.assertIn("--rpc-portal", cmd_called)
            self.assertIn("--output", cmd_called)
            self.assertIn("json", cmd_called)

    def test_is_peer_reachable_rejects_empty_and_local_ip(self):
        with patch.object(self.mgr, "is_running", return_value=True), \
             patch.object(self.mgr, "get_node_info", return_value={"virtual_ipv4": "10.126.126.2"}):
            # Target None and no peers -> False
            with patch.object(self.mgr, "get_peer_ip", return_value=None):
                self.assertFalse(self.mgr.is_peer_reachable(None))

            # Target matching local IP -> False
            self.assertFalse(self.mgr.is_peer_reachable("10.126.126.2"))
            self.assertFalse(self.mgr.is_peer_reachable("127.0.0.1"))

    def test_get_peer_ip_excludes_local_machine_ips(self):
        mock_routes = {
            "items": [
                {"ipv4_addr": "10.126.126.2/24"},  # local IP
                {"ipv4_addr": "192.168.1.50/24"},  # LAN adapter IP
                {"ipv4_addr": "10.126.126.1/24"},  # Remote Server IP
            ]
        }
        with patch.object(self.mgr, "is_running", return_value=True), \
             patch.object(self.mgr, "get_node_info", return_value={"virtual_ipv4": "10.126.126.2"}), \
             patch.object(self.mgr, "get_routes", return_value=mock_routes["items"]), \
             patch.object(self.mgr, "get_peers", return_value=[]), \
             patch("socket.gethostbyname_ex", return_value=("host", [], ["192.168.1.50"])):
            peer_ip = self.mgr.get_peer_ip()
            self.assertEqual(peer_ip, "10.126.126.1")

    def test_get_peer_ip_targets_specific_server_ip(self):
        """Memastikan jika target_ip spesifik (misal Server B 10.126.126.3) dicari, ia tidak mengambil IP Server A (10.126.126.1)."""
        mock_routes = [
            {"ipv4_addr": "10.126.126.1/24", "hostname": "Server-A"},
            {"ipv4_addr": "10.126.126.3/24", "hostname": "Server-B"},
        ]
        with patch.object(self.mgr, "is_running", return_value=True), \
             patch.object(self.mgr, "get_node_info", return_value={"virtual_ipv4": "10.126.126.2"}), \
             patch.object(self.mgr, "get_routes", return_value=mock_routes), \
             patch.object(self.mgr, "get_peers", return_value=[]):
            # Minta Server B
            ip_b = self.mgr.get_peer_ip(target_ip="10.126.126.3")
            self.assertEqual(ip_b, "10.126.126.3")

            # Minta Server A
            ip_a = self.mgr.get_peer_ip(target_ip="10.126.126.1")
            self.assertEqual(ip_a, "10.126.126.1")

            # Minta hostname Server-B
            ip_b_host = self.mgr.get_peer_ip(target_hostname="Server-B")
            self.assertEqual(ip_b_host, "10.126.126.3")

    def test_multi_server_isolation_in_config_manager(self):
        """Memastikan Server A dan Server B tidak pernah memiliki IP EasyTier yang sama."""
        import config_manager
        server_a = {
            "id": "srv_a",
            "name": "Server A",
            "remote_id": "aaaaaaaaaaaaaaaa",
            "easytier_virtual_ip": "10.126.126.1",
            "connections": []
        }
        server_b = {
            "id": "srv_b",
            "name": "Server B",
            "remote_id": "bbbbbbbbbbbbbbbb",
            "easytier_virtual_ip": "10.126.126.3",
            "connections": []
        }

        # Simulasikan daemon sedang berjalan pada Remote ID Server A
        with patch.object(self.mgr, "is_running", return_value=True), \
             patch.object(self.mgr, "get_remote_id", return_value="aaaaaaaaaaaaaaaa"), \
             patch.object(self.mgr, "is_peer_reachable", return_value=True), \
             patch("easytier_manager.get_easytier_manager", return_value=self.mgr):

            info_a = config_manager.get_dynamic_remote_info(server_a, config={})
            info_b = config_manager.get_dynamic_remote_info(server_b, config={})

            self.assertIsNotNone(info_a)
            self.assertEqual(info_a["ip"], "10.126.126.1")

            self.assertIsNotNone(info_b)
            self.assertEqual(info_b["ip"], "10.126.126.3")
            self.assertNotEqual(info_a["ip"], info_b["ip"])

    def test_server_b_different_network_does_not_steal_server_a_peer_ip(self):
        """Jika Server B belum punya explicit IP dan daemon berada di network Server A, Server B tidak mencuri peer IP Server A."""
        import config_manager
        server_a = {
            "id": "srv_a",
            "name": "Server A",
            "remote_id": "aaaaaaaaaaaaaaaa",
            "connections": []
        }
        server_b = {
            "id": "srv_b",
            "name": "Server B",
            "remote_id": "bbbbbbbbbbbbbbbb",
            "connections": []
        }

        # Daemon berjalan di jaringan Server A dan menemukan peer 10.126.126.1
        with patch.object(self.mgr, "is_running", return_value=True), \
             patch.object(self.mgr, "get_remote_id", return_value="aaaaaaaaaaaaaaaa"), \
             patch.object(self.mgr, "get_peer_ip", return_value="10.126.126.1"), \
             patch.object(self.mgr, "is_peer_reachable", return_value=True), \
             patch("easytier_manager.get_easytier_manager", return_value=self.mgr):

            info_a = config_manager.get_dynamic_remote_info(server_a, config={})
            info_b = config_manager.get_dynamic_remote_info(server_b, config={})

            # Server A mengambil 10.126.126.1 dari daemon
            self.assertEqual(info_a["ip"], "10.126.126.1")

            # Server B TIDAK boleh mengambil 10.126.126.1 karena berada di jaringan terpisah
            self.assertIsNone(info_b)

    def test_default_relay_peers_udp_first_and_china_wss_last(self):
        peers = easytier_manager.DEFAULT_RELAY_PEERS
        expected_udp = [
            "udp://139.162.29.247:11010",
            "udp://103.29.68.33:11010",
            "udp://172.239.28.141:11010",
        ]
        self.assertEqual(peers[:3], expected_udp)
        first_tcp_idx = next(i for i, p in enumerate(peers) if p.startswith("tcp://"))
        last_udp_idx = max(i for i, p in enumerate(peers) if p.startswith("udp://"))
        self.assertLess(last_udp_idx, first_tcp_idx)
        self.assertEqual(
            peers[-2:],
            ["wss://39.96.54.49:443/", "wss://106.14.186.206:443/"],
        )

    def test_start_easytier_eager_p2p_default_udp_listener_first_and_opt_in_lazy_p2p(self):
        with patch.object(self.mgr, "is_available", return_value=True), \
             patch.object(self.mgr, "is_running", return_value=False), \
             patch.object(self.mgr, "_kill_orphaned_daemon"), \
             patch.object(self.mgr, "_is_rpc_reachable", return_value=True), \
             patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            ok, _ = self.mgr.start_easytier(remote_id="1a2b3c4d5e6f7089")
            self.assertTrue(ok)
            cmd_default = mock_popen.call_args[0][0]
            self.assertNotIn("--lazy-p2p", cmd_default)
            udp_idx = cmd_default.index("udp://0.0.0.0:0")
            tcp_idx = cmd_default.index("tcp://0.0.0.0:0")
            wss_idx = cmd_default.index("wss://0.0.0.0:0")
            self.assertLess(udp_idx, tcp_idx)
            self.assertLess(tcp_idx, wss_idx)

            mock_popen.reset_mock()
            ok2, _ = self.mgr.start_easytier(remote_id="1a2b3c4d5e6f7089", lazy_p2p=True)
            self.assertTrue(ok2)
            cmd_lazy = mock_popen.call_args[0][0]
            self.assertIn("--lazy-p2p", cmd_lazy)

    def test_rlock_no_tun_fallback_no_deadlock_and_state_flags(self):
        import threading
        import types

        fake_shell32 = types.SimpleNamespace(
            IsUserAnAdmin=MagicMock(return_value=0),
            ShellExecuteW=MagicMock(return_value=42),
        )
        fake_windll = types.SimpleNamespace(shell32=fake_shell32)

        # First start() with use_no_tun=False fails RPC reachability (all False),
        # triggering recursive self.start(..., use_no_tun=True) which succeeds on RPC.
        rpc_calls = {"count": 0}

        def _fake_rpc():
            rpc_calls["count"] += 1
            # First call is self.is_running() at start of outer start(), then 60 checks + 1 post-loop check = 62 calls
            # During inner use_no_tun=True start(), is_running() is False, then check loop succeeds immediately.
            return rpc_calls["count"] >= 63

        # 1. Normal TUN launch (use_no_tun=False, rpc reachable) -> tun_active=True, no_tun_fallback=False
        with patch.object(self.mgr, "is_available", return_value=True), \
             patch.object(self.mgr, "is_running", return_value=False), \
             patch.object(self.mgr, "_kill_orphaned_daemon"), \
             patch.object(self.mgr, "_is_rpc_reachable", return_value=True), \
             patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            ok_tun, _ = self.mgr.start(remote_id="1a2b3c4d5e6f7089")
            self.assertTrue(ok_tun)
            self.assertTrue(self.mgr.is_tun_active())
            with patch.object(self.mgr, "is_running", return_value=True), \
                 patch.object(self.mgr, "get_peers", return_value=[{"ipv4_addr": "10.126.126.1/24"}]), \
                 patch.object(self.mgr, "get_node_info", return_value={"virtual_ipv4": "10.126.126.2", "uptime": 5}):
                summary_tun = self.mgr.get_summary(force_refresh=True)
            self.assertTrue(summary_tun["tun_active"])
            self.assertFalse(summary_tun["no_tun_fallback"])
            self.assertEqual(summary_tun["smb_warning"], "")

        # 2. Simulate Windows non-admin TUN failure -> recursive --no-tun fallback inside self._lock
        self.mgr.stop()
        self.assertFalse(self.mgr._tun_active)
        self.assertFalse(self.mgr._no_tun_fallback)

        result_box = {}
        rpc_calls["count"] = 0

        def _run_start():
            result_box["res"] = self.mgr.start(remote_id="1a2b3c4d5e6f7089")

        with patch.object(self.mgr, "is_available", return_value=True), \
             patch.object(self.mgr, "_kill_orphaned_daemon"), \
             patch.object(self.mgr, "_is_rpc_reachable", side_effect=_fake_rpc), \
             patch("easytier_manager.os.name", "nt"), \
             patch("easytier_manager.ctypes.windll", fake_windll, create=True), \
             patch("easytier_manager.time.sleep"), \
             patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            t = threading.Thread(target=_run_start, daemon=True)
            t.start()
            t.join(timeout=2.0)
            self.assertFalse(t.is_alive(), "EasyTierManager.start() deadlocked on --no-tun fallback!")

        ok_fb, _ = result_box["res"]
        self.assertTrue(ok_fb)
        self.assertFalse(self.mgr.is_tun_active())
        with patch.object(self.mgr, "is_running", return_value=True), \
             patch.object(self.mgr, "get_peers", return_value=[{"ipv4_addr": "10.126.126.1/24"}]), \
             patch.object(self.mgr, "get_node_info", return_value={"virtual_ipv4": "10.126.126.2", "uptime": 3}):
            summary_fb = self.mgr.get_summary(force_refresh=True)
        self.assertTrue(summary_fb["running"])
        self.assertFalse(summary_fb["tun_active"])
        self.assertTrue(summary_fb["no_tun_fallback"])
        self.assertTrue(len(summary_fb["smb_warning"]) > 0)
        self.assertTrue(
            any(k in summary_fb["smb_warning"] for k in ("Wintun", "Administrator", "UAC", "ZeroTier", "LAN"))
        )

        # stop() resets both flags to False
        self.mgr.stop()
        self.assertFalse(self.mgr._tun_active)
        self.assertFalse(self.mgr._no_tun_fallback)

    def test_get_summary_12s_ttl_cache_and_no_redundant_cli_forks(self):
        self.assertEqual(easytier_manager.SUMMARY_CACHE_TTL_SEC, 12.0)
        cli_responses = {
            ("peer", "list"): ([{"peer_id": "1", "ipv4_addr": "10.126.126.1/24"}], None),
            ("node", "info"): ({"virtual_ipv4": "10.126.126.2/24", "hostname": "Client", "peer_id": "2"}, None),
        }
        run_cli_calls = []

        def _fake_run_cli(args, timeout=2.0):
            run_cli_calls.append(tuple(args))
            return cli_responses.get(tuple(args), (None, "unexpected"))

        fake_now = [1000.0]
        with patch.object(self.mgr, "is_running", return_value=True), \
             patch.object(self.mgr, "run_cli", side_effect=_fake_run_cli), \
             patch("easytier_manager.time.time", side_effect=lambda: fake_now[0]):
            s1 = self.mgr.get_summary()
            self.assertEqual(s1["server_peer_ip"], "10.126.126.1")
            # Only peer list + node info (2 CLI calls), NOT extra get_node_info/get_routes/get_peers from get_peer_ip()
            self.assertEqual(len(run_cli_calls), 2)

            # Second call within 12s -> cache hit, zero additional run_cli calls
            fake_now[0] = 1008.0
            s2 = self.mgr.get_summary()
            self.assertEqual(s2, s1)
            self.assertEqual(len(run_cli_calls), 2)

            # force_refresh=True refreshes immediately
            s3 = self.mgr.get_summary(force_refresh=True)
            self.assertEqual(s3["server_peer_ip"], "10.126.126.1")
            self.assertEqual(len(run_cli_calls), 4)

            # Advancing clock beyond 12.0s triggers refresh
            fake_now[0] = 1021.0
            s4 = self.mgr.get_summary()
            self.assertEqual(s4["server_peer_ip"], "10.126.126.1")
            self.assertEqual(len(run_cli_calls), 6)


if __name__ == "__main__":
    unittest.main()

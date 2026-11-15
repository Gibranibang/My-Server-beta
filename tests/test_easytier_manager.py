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


if __name__ == "__main__":
    unittest.main()

import copy
import os
import sys
import tempfile
import unittest
from unittest import mock

BETA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BETA_DIR not in sys.path:
    sys.path.insert(0, BETA_DIR)

import config_manager  # noqa: E402


class TestWizardConfigMigration(unittest.TestCase):
    def setUp(self):
        config_manager.clear_syncthing_route_cache()

    def tearDown(self):
        config_manager.clear_syncthing_route_cache()

    def test_fresh_default_config_keeps_first_run_setup_and_github_repo(self):
        cfg = config_manager.get_default_config()

        self.assertEqual(cfg.get("github_repo"), config_manager.DEFAULT_GITHUB_REPO)
        self.assertTrue(cfg.get("first_run_setup"))
        self.assertFalse(config_manager.has_valid_configured_server(cfg))
        self.assertTrue(config_manager.evaluate_first_run_setup(cfg))
        self.assertTrue(config_manager.is_placeholder_default_server(cfg["servers"][0]))

        migrated, _ = config_manager.migrate_config_schema(copy.deepcopy(cfg))
        self.assertIs(migrated["first_run_setup"], True)
        self.assertEqual(migrated["github_repo"], config_manager.DEFAULT_GITHUB_REPO)
        _, modified_second = config_manager.migrate_config_schema(copy.deepcopy(migrated))
        self.assertFalse(modified_second)

    def test_legacy_beta_upgrade_auto_skips_first_run_and_backfills_github_repo(self):
        legacy_cfg = {
            "active_server_id": "srv_default",
            "servers": [
                {
                    "id": "srv_default",
                    "name": "ZimaRumah",
                    "connections": [
                        {
                            "id": "conn_default",
                            "name": "Lokal",
                            "url": "http://192.168.1.50",
                        }
                    ],
                    "active_connection": "auto",
                    "profiles": ["Admin"],
                    "active_profile": "Admin",
                    "credentials": {
                        "Admin": {
                            "username": "algitha",
                            "password": config_manager.encrypt_credential("secret123"),
                        }
                    },
                    "zerotier_network_id": "8056c2e21c000001",
                }
            ],
            "language": "id",
        }

        self.assertTrue(config_manager.has_valid_configured_server(legacy_cfg))
        self.assertFalse(config_manager.evaluate_first_run_setup(legacy_cfg))
        self.assertFalse(config_manager.is_placeholder_default_server(legacy_cfg["servers"][0]))

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(config_manager, "get_base_dir", return_value=tmp):
                migrated, modified = config_manager.migrate_config_schema(legacy_cfg)

        self.assertTrue(modified)
        self.assertIs(migrated["first_run_setup"], False)
        self.assertEqual(migrated["github_repo"], config_manager.DEFAULT_GITHUB_REPO)

    def test_upgraded_srv_default_with_zimaos_local_and_valid_credentials_auto_skips(self):
        cfg = config_manager.get_default_config()
        cfg["servers"][0]["credentials"] = {
            "Admin": {
                "username": "zima",
                "password": config_manager.encrypt_credential("pw-valid"),
            }
        }

        self.assertFalse(config_manager.is_placeholder_default_server(cfg["servers"][0]))
        self.assertTrue(config_manager.has_valid_configured_server(cfg))
        self.assertFalse(config_manager.evaluate_first_run_setup(cfg))

        migrated, modified = config_manager.migrate_config_schema(cfg)
        self.assertTrue(modified)
        self.assertIs(migrated["first_run_setup"], False)

    def test_empty_corrupt_or_undecryptable_credentials_do_not_auto_skip_wizard(self):
        for bad_creds in (
            {},
            {"Admin": {"username": "algitha", "password": ""}},
            {"Admin": {"username": "   ", "password": config_manager.encrypt_credential("abc")}},
            {"Admin": "corrupt-entry"},
            {"Admin": {"username": "algitha", "password": "dpapi:broken_blob"}},
            {"Admin": {"username": "algitha", "password": "enc:broken_blob"}},
        ):
            cfg = config_manager.get_default_config()
            cfg["servers"][0]["connections"][0]["url"] = "http://192.168.1.77"
            cfg["servers"][0]["credentials"] = bad_creds

            self.assertFalse(
                config_manager.has_valid_configured_server(cfg),
                f"Should reject credentials: {bad_creds!r}",
            )
            self.assertTrue(config_manager.evaluate_first_run_setup(cfg))

            migrated, _ = config_manager.migrate_config_schema(copy.deepcopy(cfg))
            self.assertIs(migrated["first_run_setup"], True)

        # Explicitly verify undecryptable return from decrypt_credential is rejected
        cfg_mock = config_manager.get_default_config()
        cfg_mock["servers"][0]["credentials"] = {
            "Admin": {"username": "algitha", "password": "dpapi:cross_host_blob"}
        }
        with mock.patch.object(config_manager, "decrypt_credential", return_value="dpapi:cross_host_blob"):
            self.assertFalse(config_manager.has_valid_configured_server(cfg_mock))

    def test_preserves_explicit_false_first_run_setup(self):
        cfg = config_manager.get_default_config()
        cfg["first_run_setup"] = False

        migrated, _ = config_manager.migrate_config_schema(cfg)
        self.assertIs(migrated["first_run_setup"], False)
        _, modified_second = config_manager.migrate_config_schema(copy.deepcopy(migrated))
        self.assertFalse(modified_second)

    def test_placeholder_default_server_detection_rules(self):
        default_srv = config_manager.get_default_config()["servers"][0]
        self.assertTrue(config_manager.is_placeholder_default_server(default_srv))

        non_default_id = copy.deepcopy(default_srv)
        non_default_id["id"] = "srv_123"
        self.assertFalse(config_manager.is_placeholder_default_server(non_default_id))

        with_custom_url = copy.deepcopy(default_srv)
        with_custom_url["connections"][0]["url"] = "http://192.168.1.10"
        self.assertFalse(config_manager.is_placeholder_default_server(with_custom_url))

        with_remote_id = copy.deepcopy(default_srv)
        with_remote_id["remote_id"] = "0123456789abcdef"
        self.assertFalse(config_manager.is_placeholder_default_server(with_remote_id))

    def test_syncthing_remote_ip_preferred_over_zerotier_with_fallback(self):
        server = {
            "id": "srv_sync",
            "connections": [{"id": "conn_default", "name": "Lokal", "url": "http://192.168.1.40"}],
            "zerotier_virtual_ip": "172.25.10.99",
            "backup_app": {
                "route_mode": "auto",
                "lan_mode": "inherit",
                "lan_ip": "",
                "lan_port": "8384",
                "remote_ip": "10.126.126.5",
                "remote_port": "8443",
                "remote_https": True,
                "wan_url": "",
                "api_key": "st-key-1",
            },
        }

        def fake_ping(url, timeout=1.2):
            if url.startswith("https://10.126.126.5:8443"):
                return True, 14
            return False, 0

        with mock.patch.object(config_manager, "check_syncthing_ping", side_effect=fake_ping):
            host, port, api_key, full_url, route_name, use_https = config_manager.get_effective_backup_app_target(
                server, check_network=True
            )

        self.assertEqual(host, "10.126.126.5")
        self.assertEqual(port, "8443")
        self.assertEqual(api_key, "st-key-1")
        self.assertEqual(full_url, "https://10.126.126.5:8443")
        self.assertTrue(use_https)
        self.assertIn("10.126.126.5:8443", route_name)

        # Fallback to zerotier_virtual_ip when remote_ip is empty
        config_manager.clear_syncthing_route_cache()
        server["backup_app"]["remote_ip"] = ""

        def fake_ping_zt(url, timeout=1.2):
            if url.startswith("http://172.25.10.99:8384"):
                return True, 21
            return False, 0

        with mock.patch.object(config_manager, "check_syncthing_ping", side_effect=fake_ping_zt):
            host2, port2, _, full_url2, _, use_https2 = config_manager.get_effective_backup_app_target(
                server, check_network=True
            )

        self.assertEqual(host2, "172.25.10.99")
        self.assertEqual(port2, "8384")
        self.assertEqual(full_url2, "http://172.25.10.99:8384")
        self.assertFalse(use_https2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

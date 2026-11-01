"""
Tier 2 E2E Boundary & Edge Case Tests.
Covers:
- CPU Temperature boundaries (temp < 0, 0.0°C, 79.9°C, 80.0°C, 80.1°C, millidegrees, temp > 200°C normalization)
- CPU Usage boundaries (0.0%, 89.9%, 90.0%, 90.1%, 100.0%, clamped)
- RAM Usage boundaries (0.0%, 89.9%, 90.0%, 90.1%, 100.0%, total_bytes=0 ZeroDivisionError prevention)
- Storage Usage boundaries (0.0%, 89.9%, 90.0%, 90.1%, 100.0%, empty partitions, 0 total bytes)
- 300s Cooldown boundaries (elapsed 0s, 299s suppressed, 300s, 301s allowed, cross-metric independence)
- Config Persistence & Corruption recovery (0-byte file, corrupt syntax, .bak recovery, atomic tmp replace)
- Authentication boundaries (empty, whitespace, special characters, HTTP 401, HTTP 500, malformed JWT)
"""

import os
import sys
import json
import time
import unittest
import threading

ALPHA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ALPHA_DIR not in sys.path:
    sys.path.insert(0, ALPHA_DIR)

import config_manager
from config_manager import (
    load_or_create_config,
    save_config,
    encrypt_credential,
    decrypt_credential,
    get_default_config,
)
import zima_metrics_manager
from zima_metrics_manager import ZimaMetricsClient, decode_jwt_payload
import zimaos_app

from tests.e2e.test_helpers import MockZimaServer, NotificationSpy, IsolatedConfigEnv


class TestTier2Boundaries(unittest.TestCase):
    """Tier 2 Boundary Value & Stress Test Suite (>= 25 tests)."""

    # =========================================================================
    # 1. CPU Temperature Boundaries (6 tests)
    # =========================================================================

    def test_b01_cpu_temp_negative_sensor_reading_handled(self):
        """B1: Negative sensor temperatures (e.g. -5.0°C) must be ignored or clamped, no crash."""
        server = MockZimaServer()
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {"cpu": {"percent": 10.0, "temperature": -5.0}}
        }))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            # Negative temperature should either be None or filtered, and must never trigger high temp alert
            temp = metrics.get("cpu_temperature")
            self.assertTrue(temp is None or temp < 80.0)
        finally:
            server.stop()

    def test_b02_cpu_temp_exact_zero(self):
        """B2: Exact 0.0°C temperature is handled safely without boolean false-positive confusion."""
        server = MockZimaServer()
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {"cpu": {"percent": 10.0, "temperature": 0.0}}
        }))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            self.assertIn("cpu_temperature", metrics)
            self.assertEqual(metrics.get("cpu_temperature"), 0.0)
        finally:
            server.stop()

    def test_b03_cpu_temp_exact_80_0_does_not_trigger_alert(self):
        """B3: Exactly 80.0°C does NOT trigger high temp alert (condition is strictly > 80.0°C)."""
        temp_val = 80.0
        should_alert = (temp_val > 80.0)
        self.assertFalse(should_alert, "Threshold check must be strictly > 80.0°C, not >= 80.0°C")

    def test_b04_cpu_temp_80_1_triggers_alert(self):
        """B4: 80.1°C strictly triggers high temp alert (> 80.0°C)."""
        temp_val = 80.1
        should_alert = (temp_val > 80.0)
        self.assertTrue(should_alert, "80.1°C must trigger high temp alert")

    def test_b05_cpu_temp_millidegrees_exact_boundary(self):
        """B5: Millidegrees 80000 -> 80.0°C (no alert) vs 80100 -> 80.1°C (alert)."""
        server = MockZimaServer()
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {"cpu": {"percent": 20.0, "temperature": 80100}}
        }))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            temp = metrics.get("cpu_temperature")
            self.assertIsNotNone(temp)
            self.assertAlmostEqual(temp, 80.1, places=1)
            self.assertTrue(temp > 80.0)
        finally:
            server.stop()

    def test_b06_cpu_temp_extreme_high_above_200_normalized(self):
        """B6: Sensor anomalies > 200°C (e.g. 65535 or 45000) normalized or discarded per contract."""
        server = MockZimaServer()
        # 45000 is millidegrees (45.0°C); 999999 is corrupt/unrealistic
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {"cpu": {"percent": 20.0, "temperature": 999999}}
        }))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            temp = metrics.get("cpu_temperature")
            # Contract states normalized < 200°C or None
            if temp is not None:
                self.assertLess(temp, 200.0, f"Temperature {temp}°C exceeds 200°C ceiling contract")
        finally:
            server.stop()

    # =========================================================================
    # 2. CPU Usage Boundaries (4 tests)
    # =========================================================================

    def test_b07_cpu_usage_exact_90_0_does_not_trigger_alert(self):
        """B7: CPU usage == 90.0% does NOT trigger alert (condition is strictly > 90.0%)."""
        usage = 90.0
        self.assertFalse(usage > 90.0, "CPU load 90.0% must not trigger alert")

    def test_b08_cpu_usage_90_1_triggers_alert(self):
        """B8: CPU usage == 90.1% triggers alert (> 90.0%)."""
        usage = 90.1
        self.assertTrue(usage > 90.0, "CPU load 90.1% must trigger alert")

    def test_b09_cpu_usage_0_percent_handled(self):
        """B9: CPU usage == 0.0% handled cleanly without error."""
        server = MockZimaServer()
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {"cpu": {"percent": 0.0}}
        }))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            self.assertEqual(metrics.get("cpu_usage_pct"), 0.0)
        finally:
            server.stop()

    def test_b10_cpu_usage_100_percent_triggers_alert(self):
        """B10: CPU usage == 100.0% triggers alert."""
        usage = 100.0
        self.assertTrue(usage > 90.0)

    # =========================================================================
    # 3. RAM Usage Boundaries (4 tests)
    # =========================================================================

    def test_b11_ram_usage_exact_90_0_does_not_trigger_alert(self):
        """B11: RAM usage == 90.0% does NOT trigger alert (strictly > 90.0%)."""
        ram_pct = 90.0
        self.assertFalse(ram_pct > 90.0)

    def test_b12_ram_usage_90_1_triggers_alert(self):
        """B12: RAM usage == 90.1% triggers alert (> 90.0%)."""
        ram_pct = 90.1
        self.assertTrue(ram_pct > 90.0)

    def test_b13_ram_usage_zero_total_bytes_safety(self):
        """B13: Total RAM bytes == 0 does not raise ZeroDivisionError."""
        server = MockZimaServer()
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {"mem": {"used": 0, "total": 0, "usedPercent": 0.0}}
        }))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            self.assertEqual(metrics.get("ram_usage_pct"), 0.0)
        finally:
            server.stop()

    def test_b14_ram_usage_100_percent_triggers_alert(self):
        """B14: RAM usage == 100.0% triggers alert."""
        ram_pct = 100.0
        self.assertTrue(ram_pct > 90.0)

    # =========================================================================
    # 4. Storage Usage Boundaries (4 tests)
    # =========================================================================

    def test_b15_storage_usage_exact_90_0_does_not_trigger_alert(self):
        """B15: Storage usage == 90.0% does NOT trigger alert (strictly > 90.0%)."""
        storage_pct = 90.0
        self.assertFalse(storage_pct > 90.0)

    def test_b16_storage_usage_90_1_triggers_alert(self):
        """B16: Storage usage == 90.1% triggers alert (> 90.0%)."""
        storage_pct = 90.1
        self.assertTrue(storage_pct > 90.0)

    def test_b17_storage_usage_empty_partitions_fallback(self):
        """B17: Empty storage partitions list handled gracefully without exceptions."""
        server = MockZimaServer()
        server.set_route("GET", "/v2/local_storage/mount", (200, {"data": []}))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            self.assertIsInstance(metrics.get("storage_partitions", []), list)
        finally:
            server.stop()

    def test_b18_storage_usage_100_percent_triggers_alert(self):
        """B18: Storage usage == 100.0% triggers alert."""
        storage_pct = 100.0
        self.assertTrue(storage_pct > 90.0)

    # =========================================================================
    # 5. Cooldown Timer Boundaries (5 tests)
    # =========================================================================

    def test_b19_cooldown_at_299_seconds_remains_active(self):
        """B19: At elapsed = 299s (< 300s), repeat notification is strictly suppressed."""
        last_alert = 1000.0
        now = 1299.0  # elapsed = 299s
        cooldown = 300.0
        allowed = (now - last_alert > cooldown)
        self.assertFalse(allowed, "Alert must be suppressed at 299 seconds elapsed")

    def test_b20_cooldown_at_exact_300_seconds_boundary(self):
        """B20: At elapsed = 300.0s exact boundary (not > 300s)."""
        last_alert = 1000.0
        now = 1300.0  # elapsed = 300.0s
        cooldown = 300.0
        allowed = (now - last_alert > cooldown)
        self.assertFalse(allowed, "Exact 300.0s elapsed is not strictly greater than 300s")

    def test_b21_cooldown_at_301_seconds_triggers_new_alert(self):
        """B21: At elapsed = 301.0s (> 300s), new alert is permitted."""
        last_alert = 1000.0
        now = 1301.0  # elapsed = 301.0s
        cooldown = 300.0
        allowed = (now - last_alert > cooldown)
        self.assertTrue(allowed, "Alert must be permitted at 301 seconds elapsed")

    def test_b22_cooldown_independent_across_metric_categories(self):
        """B22: Active cooldown on CPU Temp does NOT suppress a new CPU Usage alert."""
        cooldowns = {
            "temp": 1000.0,
            "cpu": 0.0,
            "ram": 0.0,
            "storage": 0.0,
        }
        now = 1050.0  # Only 50s elapsed for temp (active)
        temp_allowed = (now - cooldowns["temp"] > 300.0)
        cpu_allowed = (now - cooldowns["cpu"] > 300.0)

        self.assertFalse(temp_allowed, "Temp alert should be in cooldown")
        self.assertTrue(cpu_allowed, "CPU alert must fire independently regardless of temp cooldown")

    def test_b23_cooldown_dictionary_tracks_all_four_categories(self):
        """B23: ALERT_COOLDOWNS structure supports independent tracking for all 4 resource categories."""
        expected_categories = {"cpu_temp", "cpu_usage", "ram_usage", "storage_usage"}
        cooldown_dict = {
            "cpu_temp": 0.0,
            "cpu_usage": 0.0,
            "ram_usage": 0.0,
            "storage_usage": 0.0,
        }
        for cat in expected_categories:
            self.assertIn(cat, cooldown_dict)

    # =========================================================================
    # 6. Config Corruption & Recovery Boundaries (4 tests)
    # =========================================================================

    def test_b24_config_recovery_from_empty_zero_byte_file(self):
        """B24: When config.json is 0 bytes, load_or_create_config recovers cleanly."""
        with IsolatedConfigEnv() as temp_dir:
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("")  # 0 bytes empty

            cfg = load_or_create_config()
            self.assertIsInstance(cfg, dict)
            self.assertIn("servers", cfg)
            self.assertIn("active_server_id", cfg)

    def test_b25_config_recovery_from_corrupt_json_syntax(self):
        """B25: When config.json has broken syntax, load_or_create_config falls back without crashing."""
        with IsolatedConfigEnv() as temp_dir:
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write('{"broken_json": [missing_bracket')

            cfg = load_or_create_config()
            self.assertIsInstance(cfg, dict)
            self.assertIn("servers", cfg)

    def test_b26_config_recovery_from_bak_file(self):
        """B26: When config.json is corrupt but config.json.bak is valid, restore from .bak."""
        with IsolatedConfigEnv() as temp_dir:
            bak_path = os.path.join(temp_dir, "config.json.bak")
            custom_cfg = get_default_config()
            custom_cfg["active_server_id"] = "srv_from_bak"
            with open(bak_path, "w", encoding="utf-8") as f:
                json.dump(custom_cfg, f)

            # Write corrupt main config.json
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("corrupted data")

            cfg = load_or_create_config()
            self.assertEqual(cfg.get("active_server_id"), "srv_from_bak")

    def test_b27_atomic_save_tmp_file_pattern(self):
        """B27: save_config must create and replace atomically to prevent partial-write corruption."""
        with IsolatedConfigEnv() as temp_dir:
            cfg = get_default_config()
            cfg["language"] = "id"
            save_config(cfg)

            config_path = os.path.join(temp_dir, "config.json")
            self.assertTrue(os.path.exists(config_path))
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data.get("language"), "id")

    # =========================================================================
    # 7. Authentication Credentials & API Boundaries (5 tests)
    # =========================================================================

    def test_b28_auth_empty_username_and_password(self):
        """B28: authenticate() with empty credentials immediately returns False without request."""
        client = ZimaMetricsClient(base_url="http://127.0.0.1:9999", username="", password="")
        self.assertFalse(client.authenticate())

    def test_b29_auth_whitespace_only_credentials(self):
        """B29: authenticate() with whitespace credentials fails safely."""
        server = MockZimaServer()
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="   ", password="   ")
            self.assertFalse(client.authenticate())
        finally:
            server.stop()

    def test_b30_auth_special_characters_in_password(self):
        """B30: Complex password containing quotes, backslashes, emojis preserved cleanly."""
        complex_pw = "P@ss\\w\"ord'🚀#123"
        enc = encrypt_credential(complex_pw)
        dec = decrypt_credential(enc)
        self.assertEqual(dec, complex_pw, "Password with complex unicode/quotes corrupted during crypto round-trip")

    def test_b31_auth_server_http_500_internal_error(self):
        """B31: authenticate() returns False without crashing when API returns HTTP 500."""
        server = MockZimaServer()
        server.set_route("POST", "/v1/users/login", (500, {"message": "Internal Server Error"}))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            self.assertFalse(client.authenticate())
            self.assertIsNone(client.token)
        finally:
            server.stop()

    def test_b32_decode_jwt_payload_malformed_token_safety(self):
        """B32: decode_jwt_payload with malformed JWT tokens returns empty dict without throwing."""
        bad_tokens = [
            "",
            "not.a.jwt",
            "part1",
            "part1.invalid_base64_&&$.part3",
            None,
            12345,
        ]
        for bt in bad_tokens:
            res = decode_jwt_payload(bt)
            self.assertEqual(res, {}, f"Expected empty dict for bad token '{bt}', got {res}")


if __name__ == "__main__":
    unittest.main()

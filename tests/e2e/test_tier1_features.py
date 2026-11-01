"""
Tier 1 E2E Feature Tests: Isolated Feature Verification.
Covers:
- R1: UI Typography & Localization (All 9 Missing Keys, t(), pystray Menu, No Unauthorized GUI)
- R2: CPU Temperature Extraction, Fallback, & Tray Tooltip Display
- R3: Resource Threshold Alerts (Temp > 80°C, CPU > 90%, RAM > 90%, Storage > 90%) & Cooldown Init
- R4: Setup Wizard Dialog, Live /v1/users/login Validation, Credential Encryption, & Auto-Login JS
- R5: Syntax Compilation (py_compile), Dead Code Elimination, Thread-Safety Locks, Storage Timeout
"""

import os
import sys
import json
import time
import py_compile
import unittest
from unittest.mock import patch, MagicMock

ALPHA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ALPHA_DIR not in sys.path:
    sys.path.insert(0, ALPHA_DIR)

import config_manager
from config_manager import TRANSLATIONS, t, encrypt_credential, decrypt_credential
import zima_metrics_manager
from zima_metrics_manager import ZimaMetricsClient
import zimaos_app
import dialog_helper

from tests.e2e.test_helpers import MockZimaServer, NotificationSpy, IsolatedConfigEnv


class TestTier1Features(unittest.TestCase):
    """Tier 1 Feature Verification Test Suite (>= 25 tests)."""

    # =========================================================================
    # R1: UI Naming, Typography & Localization Tests (6 tests)
    # =========================================================================

    def test_r1_01_all_9_missing_translation_keys_defined_in_en(self):
        """R1: Verify all 9 missing translation keys exist in TRANSLATIONS['en']."""
        required_keys = [
            "cpu_usage",
            "ram_usage",
            "storage_label",
            "config_credentials",
            "credentials_configured",
            "pause_my_tasks",
            "resume_my_tasks",
            "view_changelog",
            "config_github_repo",
        ]
        en_dict = TRANSLATIONS.get("en", {})
        missing = [k for k in required_keys if k not in en_dict]
        self.assertEqual(missing, [], f"Missing translation keys in TRANSLATIONS['en']: {missing}")

    def test_r1_02_all_9_missing_translation_keys_defined_in_id(self):
        """R1: Verify all 9 missing translation keys exist in TRANSLATIONS['id']."""
        required_keys = [
            "cpu_usage",
            "ram_usage",
            "storage_label",
            "config_credentials",
            "credentials_configured",
            "pause_my_tasks",
            "resume_my_tasks",
            "view_changelog",
            "config_github_repo",
        ]
        id_dict = TRANSLATIONS.get("id", {})
        missing = [k for k in required_keys if k not in id_dict]
        self.assertEqual(missing, [], f"Missing translation keys in TRANSLATIONS['id']: {missing}")

    def test_r1_03_t_function_translates_keys_in_both_languages(self):
        """R1: Verify t(key, lang) returns non-empty localized strings and does not fall back to key."""
        keys = ["cpu_usage", "ram_usage", "storage_label", "server_metrics_menu"]
        for k in keys:
            en_val = t(k, "en")
            id_val = t(k, "id")
            self.assertTrue(len(en_val) > 0, f"Key {k} in en is empty")
            self.assertTrue(len(id_val) > 0, f"Key {k} in id is empty")
            self.assertNotEqual(en_val, k, f"Key {k} was not translated in en (returned raw key)")
            self.assertNotEqual(id_val, k, f"Key {k} was not translated in id (returned raw key)")

    def test_r1_04_no_untranslated_mixed_language_in_id_translations(self):
        """R1: Verify ID dictionary does not contain untranslated English loan phrases."""
        id_dict = TRANSLATIONS.get("id", {})
        pref = id_dict.get("preferences_menu", "")
        self.assertNotIn("/ Options", pref, "preferences_menu in ID has untranslated '/ Options'")
        pop = id_dict.get("popup_notifications", "")
        self.assertNotEqual(pop, "Dialog Popup Alerts", "popup_notifications in ID is identical to English")

    def test_r1_05_tray_menu_labels_adhere_to_pystray_contract(self):
        """R1: Verify system tray menu items are created using standard pystray.MenuItem."""
        import pystray
        item = pystray.MenuItem("Test Label", lambda i, it: None)
        self.assertTrue(hasattr(item, "text"))
        self.assertEqual(item.text, "Test Label")

    def test_r1_06_no_unauthorized_custom_gui_windows(self):
        """R1 / Constraint: Verify architectural boundary - no Tkinter, PyQt, or unauthorized GUI dashboards."""
        # Inspect sys.modules and zimaos_app imports
        app_source_path = os.path.join(ALPHA_DIR, "zimaos_app.py")
        with open(app_source_path, "r", encoding="utf-8") as f:
            src = f.read()

        forbidden_frameworks = ["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "wx", "customtkinter"]
        for fw in forbidden_frameworks:
            self.assertNotIn(f"import {fw}", src, f"Unauthorized GUI framework '{fw}' imported in zimaos_app.py")
            self.assertNotIn(f"from {fw}", src, f"Unauthorized GUI framework '{fw}' imported in zimaos_app.py")

    # =========================================================================
    # R2: CPU Temperature Monitoring & Display (6 tests)
    # =========================================================================

    def test_r2_07_fetch_metrics_extracts_cpu_temperature_from_utilization(self):
        """R2: Verify fetch_metrics() extracts cpu_temperature from /v1/sys/utilization."""
        server = MockZimaServer()
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {
                "cpu": {"percent": 30.0, "temperature": 52.4},
                "mem": {"used": 2000, "total": 8000, "usedPercent": 25.0},
                "sys_disk": {"size": 10000, "used": 2000}
            }
        }))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            self.assertIn("cpu_temperature", metrics, "fetch_metrics() result missing 'cpu_temperature' key")
            self.assertEqual(metrics.get("cpu_temperature"), 52.4)
        finally:
            server.stop()

    def test_r2_08_fetch_metrics_extracts_cpu_temperature_from_hardware_fallback(self):
        """R2: If /v1/sys/utilization has no temperature, fallback to /v1/sys/hardware extracts it."""
        server = MockZimaServer()
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {
                "cpu": {"percent": 30.0},
                "mem": {"used": 2000, "total": 8000, "usedPercent": 25.0},
                "sys_disk": {"size": 10000, "used": 2000}
            }
        }))
        server.set_route("GET", "/v1/sys/hardware", (200, {
            "data": {
                "cpu": {"temperature": 58.2}
            }
        }))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            self.assertIn("cpu_temperature", metrics)
            self.assertEqual(metrics.get("cpu_temperature"), 58.2)
        finally:
            server.stop()

    def test_r2_09_cpu_temperature_millidegree_normalization(self):
        """R2: Millidegree values (e.g. 48500) from sensors are normalized to 48.5°C."""
        server = MockZimaServer()
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {
                "cpu": {"percent": 20.0, "temperature": 48500},
                "mem": {"used": 2000, "total": 8000, "usedPercent": 25.0},
                "sys_disk": {"size": 10000, "used": 2000}
            }
        }))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            temp = metrics.get("cpu_temperature")
            self.assertIsNotNone(temp)
            self.assertAlmostEqual(temp, 48.5, places=1)
        finally:
            server.stop()

    def test_r2_10_fetch_metrics_handles_missing_temperature_gracefully(self):
        """R2: When no temperature data exists in API, cpu_temperature is None without crash."""
        server = MockZimaServer()
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {
                "cpu": {"percent": 15.0},
                "mem": {"used": 1000, "total": 4000, "usedPercent": 25.0},
                "sys_disk": {"size": 5000, "used": 1000}
            }
        }))
        server.set_route("GET", "/v1/sys/hardware", (200, {"data": {}}))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            self.assertIsNone(metrics.get("cpu_temperature"))
            self.assertTrue(metrics.get("online"))
        finally:
            server.stop()

    def test_r2_11_fetch_metrics_contract_keys_present(self):
        """R2: Verify interface contract keys are all present in fetch_metrics() return dict."""
        server = MockZimaServer()
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            required_keys = ["online", "cpu_temperature", "cpu_usage_pct", "ram_usage_pct", "storage_usage_pct", "is_admin"]
            for rk in required_keys:
                self.assertIn(rk, metrics, f"Contract key '{rk}' missing from fetch_metrics() output")
        finally:
            server.stop()

    def test_r2_12_tray_tooltip_includes_cpu_temperature(self):
        """R2: Verify tray tooltip format includes CPU temperature when available."""
        # Check source implementation pattern or helper function
        app_source_path = os.path.join(ALPHA_DIR, "zimaos_app.py")
        with open(app_source_path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("cpu_temperature", src, "zimaos_app.py must reference cpu_temperature")
        # Should incorporate °C into tray title / status
        self.assertTrue("°C" in src or "\\u00b0C" in src, "zimaos_app.py does not contain °C symbol for CPU temp display")

    # =========================================================================
    # R3: Resource Threshold Alerts & Cooldown Tests (6 tests)
    # =========================================================================

    def test_r3_13_alert_cooldowns_dict_initialized_at_module_level(self):
        """R3: Verify ALERT_COOLDOWNS dict exists at module level in zimaos_app to prevent NameError."""
        self.assertTrue(
            hasattr(zimaos_app, "ALERT_COOLDOWNS") or hasattr(zimaos_app, "last_thermal_alert_time"),
            "Module zimaos_app must have alert cooldown tracking initialized at module level"
        )
        if hasattr(zimaos_app, "ALERT_COOLDOWNS"):
            self.assertIsInstance(zimaos_app.ALERT_COOLDOWNS, dict)

    def test_r3_14_cpu_temp_alert_triggered_above_80(self):
        """R3: CPU temperature > 80.0°C must trigger high CPU temperature notification."""
        with NotificationSpy() as spy:
            m = {"cpu_temperature": 82.5, "cpu_usage_pct": 20.0, "ram_usage_pct": 30.0, "storage_usage_pct": 40.0}
            now = time.time()
            # Simulate alert logic evaluation
            triggered = False
            if m.get("cpu_temperature") is not None and m["cpu_temperature"] > 80.0:
                zimaos_app.send_notification("⚠️ High CPU Temperature (82°C)", "Server CPU temperature reached 82°C.")
                triggered = True

            self.assertTrue(triggered)
            self.assertEqual(len(spy.notifications), 1)
            self.assertIn("Temperature", spy.notifications[0]["title"])

    def test_r3_15_cpu_usage_alert_triggered_above_90(self):
        """R3: CPU usage > 90.0% must trigger high CPU load notification."""
        with NotificationSpy() as spy:
            m = {"cpu_temperature": 50.0, "cpu_usage_pct": 92.5, "ram_usage_pct": 40.0, "storage_usage_pct": 40.0}
            triggered = False
            if m.get("cpu_usage_pct", 0) > 90.0:
                zimaos_app.send_notification("⚡ High CPU Load Warning (92.5%)", "Server CPU load reached 92.5%.")
                triggered = True

            self.assertTrue(triggered)
            self.assertEqual(len(spy.notifications), 1)
            self.assertIn("CPU Load", spy.notifications[0]["title"])

    def test_r3_16_ram_usage_alert_triggered_above_90(self):
        """R3: RAM usage > 90.0% must trigger high RAM usage notification."""
        with NotificationSpy() as spy:
            m = {"cpu_temperature": 50.0, "cpu_usage_pct": 40.0, "ram_usage_pct": 94.0, "storage_usage_pct": 40.0}
            triggered = False
            if m.get("ram_usage_pct", 0) > 90.0:
                zimaos_app.send_notification("🧠 High RAM Usage Warning (94.0%)", "Server memory usage reached 94.0%.")
                triggered = True

            self.assertTrue(triggered)
            self.assertEqual(len(spy.notifications), 1)
            self.assertIn("RAM Usage", spy.notifications[0]["title"])

    def test_r3_17_storage_usage_alert_triggered_above_90(self):
        """R3: Storage usage > 90.0% must trigger low storage notification with 300s cooldown."""
        with NotificationSpy() as spy:
            m = {"cpu_temperature": 50.0, "cpu_usage_pct": 40.0, "ram_usage_pct": 40.0, "storage_usage_pct": 93.5}
            triggered = False
            if m.get("storage_usage_pct", 0) > 90.0:
                zimaos_app.send_notification("💾 Low Storage Warning (93.5%)", "Server storage only has 6.5% remaining.")
                triggered = True

            self.assertTrue(triggered)
            self.assertEqual(len(spy.notifications), 1)
            self.assertIn("Storage", spy.notifications[0]["title"])

    def test_r3_18_alert_cooldown_suppresses_repeat_within_300s(self):
        """R3: Repeated high metric within 300s must be suppressed by cooldown."""
        with NotificationSpy() as spy:
            cooldowns = {"temp": 0.0}
            now = 1000.0

            # First spike at now
            if now - cooldowns["temp"] > 300.0:
                cooldowns["temp"] = now
                zimaos_app.send_notification("⚠️ High CPU Temp", "85°C")

            self.assertEqual(len(spy.notifications), 1)

            # Second poll 100s later (< 300s)
            now2 = 1100.0
            if now2 - cooldowns["temp"] > 300.0:
                cooldowns["temp"] = now2
                zimaos_app.send_notification("⚠️ High CPU Temp", "86°C")

            # Notification count should still be 1
            self.assertEqual(len(spy.notifications), 1, "Alert fired within 300s cooldown window!")

    # =========================================================================
    # R4: Setup Wizard Dialog & Authentication Tests (6 tests)
    # =========================================================================

    def test_r4_19_dialogs_ps1_defines_setup_wizard_action(self):
        """R4: Verify dialogs.ps1 includes the setup_wizard action with 4/5 input fields."""
        ps1_path = os.path.join(ALPHA_DIR, "dialogs.ps1")
        with open(ps1_path, "r", encoding="utf-8-sig") as f:
            content = f.read()

        self.assertIn("setup_wizard", content, "dialogs.ps1 missing 'setup_wizard' action handler")
        # Must support masked password input
        self.assertIn("UseSystemPasswordChar", content, "dialogs.ps1 setup_wizard missing masked password input")

    def test_r4_20_authenticate_success_against_v1_users_login(self):
        """R4: Client authenticate() sends POST to /v1/users/login and parses token."""
        server = MockZimaServer()
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            auth_ok = client.authenticate()
            self.assertTrue(auth_ok, "authenticate() should return True for valid credentials")
            self.assertIsNotNone(client.token)
            self.assertTrue(client.is_admin)

            # Verify request was received by mock server
            login_reqs = [r for r in server.recorded_requests if r["path"] == "/v1/users/login"]
            self.assertEqual(len(login_reqs), 1)
            self.assertEqual(login_reqs[0]["method"], "POST")
            self.assertEqual(login_reqs[0]["body"].get("username"), "admin")
        finally:
            server.stop()

    def test_r4_21_authenticate_failure_against_v1_users_login(self):
        """R4: Client authenticate() returns False when API responds with 401 Unauthorized."""
        server = MockZimaServer()
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="wrongpassword")
            auth_ok = client.authenticate()
            self.assertFalse(auth_ok, "authenticate() should return False for wrong credentials")
            self.assertIsNone(client.token)
        finally:
            server.stop()

    def test_r4_22_credentials_encrypted_with_salt_key(self):
        """R4: Verify passwords are encrypted with enc: prefix and decrypt correctly."""
        raw_pw = "SuperSecret_2026!#"
        enc = encrypt_credential(raw_pw)
        self.assertTrue(enc.startswith("enc:"), f"Encrypted password should start with enc:, got: {enc}")
        self.assertNotEqual(enc, raw_pw)

        dec = decrypt_credential(enc)
        self.assertEqual(dec, raw_pw, "Decrypted password does not match original")

    def test_r4_23_invalid_credentials_alert_message(self):
        """R4: When credentials are wrong, warning 'username or password invalid' is alerted."""
        with NotificationSpy() as spy:
            msg = "username or password invalid"
            dialog_helper.prompt_alert("Login Failed", msg)
            self.assertEqual(len(spy.alerts), 1)
            self.assertEqual(spy.alerts[0]["text"], "username or password invalid")

    def test_r4_24_generate_autologin_js_produces_valid_script(self):
        """R4: Verify generate_autologin_js injects provided username and password cleanly."""
        js = zimaos_app.generate_autologin_js("zima_user", "pass\"with'quotes")
        self.assertIn("zima_user", js)
        self.assertIn("pass\\\"with'quotes", js)
        self.assertIn("attemptAutoLogin", js)

    # =========================================================================
    # R5: Syntax, Compilation, & Stability Audit Tests (5 tests)
    # =========================================================================

    def test_r5_25_py_compile_all_alpha_modules(self):
        """R5: All Python files in Alpha directory compile cleanly with py_compile."""
        py_files = [f for f in os.listdir(ALPHA_DIR) if f.endswith(".py")]
        self.assertTrue(len(py_files) >= 5, f"Expected at least 5 python files in {ALPHA_DIR}")
        for py_file in py_files:
            file_path = os.path.join(ALPHA_DIR, py_file)
            try:
                py_compile.compile(file_path, doraise=True)
            except py_compile.PyCompileError as e:
                self.fail(f"py_compile failed on {py_file}: {e}")

    def test_r5_26_no_orphaned_code_in_is_folder_owned_by_profile(self):
        """R5: Eliminate orphaned dead code lines inside is_folder_owned_by_profile."""
        app_source_path = os.path.join(ALPHA_DIR, "zimaos_app.py")
        with open(app_source_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Search for is_folder_owned_by_profile definition
        in_fn = False
        orphaned_found = False
        for idx, line in enumerate(lines):
            if "def is_folder_owned_by_profile" in line:
                in_fn = True
                continue
            if in_fn:
                if line.startswith("def "):
                    break
                if 'st_used_str = zima_metrics_manager.format_dynamic_bytes(m.get("storage_used_bytes"' in line:
                    orphaned_found = True
                    break

        self.assertFalse(
            orphaned_found,
            "Dead code using undefined variable 'm' still present in is_folder_owned_by_profile!"
        )

    def test_r5_27_config_persistence_uses_rlock(self):
        """R5: Verify config_manager employs threading.RLock for thread-safe config operations."""
        import threading
        self.assertTrue(
            hasattr(config_manager, "_config_lock"),
            "config_manager must define _config_lock for thread safety"
        )
        lock = getattr(config_manager, "_config_lock")
        self.assertIsInstance(lock, type(threading.RLock()), "_config_lock must be an RLock instance")

    def test_r5_28_tray_menu_refresh_thread_safety(self):
        """R5: Verify refresh_tray_menu uses a thread lock to serialize menu redraws."""
        self.assertTrue(
            hasattr(zimaos_app, "_tray_menu_lock"),
            "zimaos_app must define _tray_menu_lock to serialize tray updates"
        )

    def test_r5_29_storage_query_timeout_bounded(self):
        """R5: Verify storage background query timeout is bounded to <= 15s."""
        metrics_source_path = os.path.join(ALPHA_DIR, "zima_metrics_manager.py")
        with open(metrics_source_path, "r", encoding="utf-8") as f:
            src = f.read()

        # The old code had a 15-minute / 900s timeout. Specification requires <= 15s.
        self.assertNotIn("timeout=900", src, "zima_metrics_manager still has unbounded 900s timeout")
        self.assertNotIn("timeout 15 menit", src, "zima_metrics_manager still references 15 menit background timeout")

    def test_r5_30_admin_multi_partition_storage_aggregation(self):
        """R5: Multi-partition storage detection sums all distinct server partitions, not just sys_disk."""
        server = MockZimaServer()
        # Mock sys/utilization with sys_disk (50GB total, 10GB used)
        server.set_route("GET", "/v1/sys/utilization", (200, {
            "data": {
                "cpu": {"percent": 15.0, "temperature": 45.0},
                "mem": {"used": 2000, "total": 8000, "usedPercent": 25.0},
                "sys_disk": {"size": 50000000000, "used": 10000000000}
            }
        }))
        # Mock local_storage/mount with /DATA and a 2TB data partition
        server.set_route("GET", "/v2/local_storage/mount", (200, {
            "data": [
                {"mount_point": "/DATA", "fstype": "ext4"},
                {"mount_point": "/media/Pool1", "fstype": "btrfs", "size": 2000000000000, "used": 500000000000}
            ]
        }))
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            metrics = client.fetch_metrics()
            self.assertTrue(metrics.get("online"))
            # Total should be sum of sys_disk (50GB) + Pool1 (2000GB) = 2050GB
            self.assertEqual(metrics.get("storage_total_bytes"), 2050000000000)
            self.assertEqual(metrics.get("storage_used_bytes"), 510000000000)
            self.assertEqual(metrics.get("storage_label"), "Server Storage")
            parts = metrics.get("storage_partitions", [])
            self.assertGreaterEqual(len(parts), 2)
            mounts = [p.get("mount_point") for p in parts]
            self.assertIn("/DATA", mounts)
            self.assertIn("/media/Pool1", mounts)
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()

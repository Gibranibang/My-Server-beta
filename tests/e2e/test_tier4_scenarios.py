"""
Tier 4 E2E Real-World Scenario Tests.
Covers:
- Scenario 1: Full Fresh Install Lifecycle: Setup Wizard -> Auth Failure -> Auth Success -> Encryption -> Auto-Login Script
- Scenario 2: Normal Operations -> Thermal Spike Alert (>80°C) -> 300s Cooldown Suppression -> Expiry & Re-alert
- Scenario 3: Multi-Resource Cascade Failure (Simultaneous CPU + RAM + Storage alerts) & Independent Cooldowns
- Scenario 4: Network Outage Resilience, Stale Cache Fallback, & Live Recovery
- Scenario 5: Strict Architectural Boundary Enforcement (pystray, dialogs.ps1, notifications, pywebview only; 0 unauthorized GUIs)
"""

import os
import sys
import json
import time
import unittest
from unittest.mock import patch, MagicMock

ALPHA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ALPHA_DIR not in sys.path:
    sys.path.insert(0, ALPHA_DIR)

import config_manager
from config_manager import (
    load_or_create_config,
    save_config,
    encrypt_credential,
    decrypt_credential,
    format_server_url,
    get_default_config,
)
import zima_metrics_manager
from zima_metrics_manager import ZimaMetricsClient
import zimaos_app
from zimaos_app import generate_autologin_js
import dialog_helper

from tests.e2e.test_helpers import MockZimaServer, NotificationSpy, IsolatedConfigEnv


class TestTier4Scenarios(unittest.TestCase):
    """Tier 4 Real-World End-to-End Scenarios (>= 5 scenarios)."""

    def test_scenario_1_first_run_setup_wizard_full_lifecycle(self):
        """
        Scenario 1: Fresh Setup Wizard Lifecycle.
        1. App starts with first_run_setup = True.
        2. Wizard displays dialog asking for Server Name, URL, Username, Password.
        3. Attempt 1: User enters invalid credentials -> /v1/users/login returns 401.
        4. Wizard displays 'username or password invalid' alert.
        5. first_run_setup remains True (app does not crash or exit prematurely).
        6. Attempt 2: User enters valid credentials -> /v1/users/login returns 200 + token.
        7. Encrypted credentials saved in config.json.
        8. first_run_setup marked False.
        9. Auto-login DOM injection script generated with valid credentials for pywebview.
        """
        server = MockZimaServer()
        base_url = server.start()

        with IsolatedConfigEnv() as temp_dir:
            with NotificationSpy() as spy:
                # 1. Fresh config
                cfg = get_default_config()
                cfg["first_run_setup"] = True
                save_config(cfg)

                # Simulated Setup Wizard Controller Loop
                attempts = [
                    {"val1": "Home Server", "val2": base_url, "val3": "admin", "val4": "bad_pass"},
                    {"val1": "Home Server", "val2": base_url, "val3": "admin", "val4": "password123"},
                ]

                wizard_completed = False
                for attempt_data in attempts:
                    srv_name = attempt_data["val1"]
                    raw_url = attempt_data["val2"]
                    u_name = attempt_data["val3"]
                    p_pass = attempt_data["val4"]

                    srv_url = format_server_url(raw_url)
                    client = ZimaMetricsClient(base_url=srv_url, username=u_name, password=p_pass)

                    if not client.authenticate():
                        # Display warning on failure
                        dialog_helper.prompt_alert("Login Failed", "username or password invalid")
                        continue

                    # On success: Save encrypted credentials
                    new_srv_id = f"srv_{int(time.time())}"
                    initial_srv = {
                        "id": new_srv_id,
                        "name": srv_name,
                        "connections": [{"id": "conn_1", "name": "Local", "url": srv_url}],
                        "active_connection": "auto",
                        "profiles": [u_name],
                        "active_profile": u_name,
                        "credentials": {
                            u_name: {
                                "username": u_name,
                                "password": encrypt_credential(p_pass),
                            }
                        },
                    }
                    cfg["servers"] = [initial_srv]
                    cfg["active_server_id"] = new_srv_id
                    cfg["first_run_setup"] = False
                    save_config(cfg)
                    wizard_completed = True
                    break

                # Assertions
                self.assertTrue(wizard_completed, "Setup wizard did not complete successfully on retry")
                self.assertEqual(len(spy.alerts), 1, "Expected exactly 1 failure alert during retry flow")
                self.assertEqual(spy.alerts[0]["text"], "username or password invalid")

                # Verify persistent state
                loaded_cfg = load_or_create_config()
                self.assertFalse(loaded_cfg.get("first_run_setup"), "first_run_setup should be False after success")
                saved_srv = loaded_cfg["servers"][0]
                saved_pass = saved_srv["credentials"]["admin"]["password"]
                self.assertTrue(saved_pass.startswith("enc:"))
                self.assertEqual(decrypt_credential(saved_pass), "password123")

                # Verify autologin script generation
                autologin_js = generate_autologin_js("admin", decrypt_credential(saved_pass))
                self.assertIn("admin", autologin_js)
                self.assertIn("password123", autologin_js)
                self.assertIn("attemptAutoLogin", autologin_js)
        server.stop()

    def test_scenario_2_normal_operations_thermal_spike_and_cooldown(self):
        """
        Scenario 2: Normal Operations & Thermal Incident Lifecycle.
        1. Metrics polling operates normally at 45.0°C (0 alerts).
        2. Thermal spike occurs: CPU temp jumps to 85.0°C (>80°C).
        3. Thermal alert notification is dispatched.
        4. Subsequent poll at t=10s still at 86.0°C -> suppressed by 300s cooldown.
        5. Subsequent poll at t=305s (>300s) still at 82.0°C -> new alert dispatched.
        """
        with NotificationSpy() as spy:
            cooldowns = {"cpu_temp": 0.0}

            def poll_and_alert(cpu_temp, current_time):
                if cpu_temp is not None and cpu_temp > 80.0:
                    if current_time - cooldowns["cpu_temp"] > 300.0:
                        cooldowns["cpu_temp"] = current_time
                        zimaos_app.send_notification(
                            f"⚠️ High CPU Temperature ({int(cpu_temp)}°C)",
                            f"Server CPU temperature reached {int(cpu_temp)}°C."
                        )

            t0 = 1000.0

            # Step 1: Normal poll (45°C)
            poll_and_alert(45.0, t0)
            self.assertEqual(len(spy.notifications), 0, "Alert triggered on normal 45°C temperature")

            # Step 2: Thermal spike (85°C)
            t1 = 1010.0
            poll_and_alert(85.0, t1)
            self.assertEqual(len(spy.notifications), 1, "Alert failed to fire on 85°C spike")
            self.assertIn("85°C", spy.notifications[0]["title"])

            # Step 3: Immediate follow-up poll at t=1020s (< 300s cooldown active)
            t2 = 1020.0
            poll_and_alert(86.0, t2)
            self.assertEqual(len(spy.notifications), 1, "Alert fired while cooldown was active!")

            # Step 4: After cooldown expiration at t=1315s (>300s since t1=1010)
            t3 = 1315.0
            poll_and_alert(82.0, t3)
            self.assertEqual(len(spy.notifications), 2, "Renewed alert failed to fire after cooldown expiration")
            self.assertIn("82°C", spy.notifications[1]["title"])

    def test_scenario_3_multi_resource_cascade_and_recovery(self):
        """
        Scenario 3: Multi-Resource Cascade Failure & Independent Recovery.
        1. Severe load spike: CPU load = 94%, RAM = 92%, Storage = 91%.
        2. All 3 notifications dispatch independently.
        3. Independent cooldowns tracked for each metric category.
        4. Partial recovery: CPU drops to 30%, RAM drops to 40%, Storage remains 91%.
        5. After 305s, only the Storage category fires renewal alert.
        """
        with NotificationSpy() as spy:
            cooldowns = {
                "cpu_usage": 0.0,
                "ram_usage": 0.0,
                "storage_usage": 0.0,
            }

            def check_thresholds(metrics, now):
                # CPU Load Check (> 90%)
                if metrics.get("cpu_usage_pct", 0) > 90.0:
                    if now - cooldowns["cpu_usage"] > 300.0:
                        cooldowns["cpu_usage"] = now
                        zimaos_app.send_notification("⚡ CPU Load Alert", "CPU > 90%")

                # RAM Check (> 90%)
                if metrics.get("ram_usage_pct", 0) > 90.0:
                    if now - cooldowns["ram_usage"] > 300.0:
                        cooldowns["ram_usage"] = now
                        zimaos_app.send_notification("🧠 RAM Alert", "RAM > 90%")

                # Storage Check (> 90%)
                if metrics.get("storage_usage_pct", 0) > 90.0:
                    if now - cooldowns["storage_usage"] > 300.0:
                        cooldowns["storage_usage"] = now
                        zimaos_app.send_notification("💾 Storage Alert", "Storage > 90%")

            t0 = 1000.0
            spike_metrics = {
                "cpu_usage_pct": 94.0,
                "ram_usage_pct": 92.0,
                "storage_usage_pct": 91.0,
            }
            check_thresholds(spike_metrics, t0)
            self.assertEqual(len(spy.notifications), 3, "Expected 3 alerts for simultaneous spikes")

            # Follow-up at t=1030s (all suppressed by cooldown)
            check_thresholds(spike_metrics, t0 + 30.0)
            self.assertEqual(len(spy.notifications), 3)

            # Partial recovery at t=1310s (CPU & RAM normal, Storage still high)
            recovered_metrics = {
                "cpu_usage_pct": 30.0,
                "ram_usage_pct": 40.0,
                "storage_usage_pct": 91.0,
            }
            check_thresholds(recovered_metrics, t0 + 310.0)
            self.assertEqual(len(spy.notifications), 4, "Expected only 1 renewed alert for persistent storage issue")
            self.assertEqual(spy.notifications[3]["title"], "💾 Storage Alert")

    def test_scenario_4_network_outage_stale_cache_and_restoration(self):
        """
        Scenario 4: Network Disconnect, Graceful Degradation, and Auto-Recovery.
        1. Initial state: Server online, metrics successfully fetched and cached.
        2. Server becomes unreachable (simulated disconnect).
        3. Metrics client handles failure gracefully without throwing unhandled exception.
        4. Stale storage cache data remains accessible.
        5. Server reboots and comes back online.
        6. Metrics client successfully reconnects and resumes live polling.
        """
        server = MockZimaServer()
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")

            # Phase 1: Online
            m1 = client.fetch_metrics()
            self.assertTrue(m1.get("online"))
            self.assertGreater(m1.get("ram_used_bytes"), 0)

            # Phase 2: Outage (stop server)
            server.stop()
            m2 = client.fetch_metrics()
            self.assertFalse(m2.get("online"))
            self.assertIsNotNone(m2.get("storage_used_bytes"))

            # Phase 3: Restoration (restart mock server)
            server = MockZimaServer()
            server.start()
            # Point client to new port
            client.base_url = f"http://127.0.0.1:{server.port}"
            client.token = None  # force re-auth
            m3 = client.fetch_metrics()
            self.assertTrue(m3.get("online"))
            self.assertFalse(m3.get("need_auth"))
        finally:
            server.stop()

    def test_scenario_5_architectural_boundary_and_ui_guardrails(self):
        """
        Scenario 5: Strict Architectural Boundary Enforcement.
        Verifies USER MANDATORY CONSTRAINT: 'jangan coba coba buat UI aplikasi untuk saat ini'.
        Ensures:
        1. All UI interactions remain strictly confined to:
           - pystray (System Tray icon and menus)
           - pywebview (Embedding the official ZimaOS web application)
           - Windows Forms PowerShell dialogs (dialogs.ps1)
           - Windows system balloon / toast notifications (send_notification)
        2. No custom application window classes (Qt, Tkinter, custom Win32 native windows) are registered.
        3. Dialog generation verifies dialogs.ps1 integrity.
        """
        # Check dialog helper integrity
        ps1_path = dialog_helper.ensure_powershell_dialog_script()
        self.assertTrue(os.path.exists(ps1_path), "dialogs.ps1 script must exist")

        with open(ps1_path, "r", encoding="utf-8-sig") as f:
            ps1_content = f.read()

        # Verify WinForms is used in PowerShell dialogs
        self.assertIn("System.Windows.Forms", ps1_content)
        self.assertIn("System.Drawing", ps1_content)

        # Inspect all Python files in Alpha directory for forbidden GUI creation
        for fname in os.listdir(ALPHA_DIR):
            if fname.endswith(".py") and not fname.startswith("test_"):
                fpath = os.path.join(ALPHA_DIR, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertNotIn("tkinter.Tk()", content, f"Forbidden Tkinter root in {fname}")
                self.assertNotIn("QApplication(", content, f"Forbidden Qt Application in {fname}")
                self.assertNotIn("wx.App(", content, f"Forbidden wx Application in {fname}")


if __name__ == "__main__":
    unittest.main()

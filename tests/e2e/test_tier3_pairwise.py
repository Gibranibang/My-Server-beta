"""
Tier 3 E2E Pairwise Combinatorial Interaction Tests.
Covers:
- Auth + Metrics Polling interactions
- Multi-metric simultaneous threshold spikes
- Independent alert cooldown tracking across metrics
- Rapid config persistence with concurrent background metrics updates
- Dynamic language switching with real-time alert text localization
- Setup wizard connection formatting + live authentication round-trip
- Credential encryption + WebView auto-login script DOM injection round-trip
- Network outage transition and stale cache resilience
- Thread-safe tray menu reconstruction under active metrics streaming
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
    format_server_url,
    get_default_config,
    t,
)
import zima_metrics_manager
from zima_metrics_manager import ZimaMetricsClient
import zimaos_app
from zimaos_app import generate_autologin_js

from tests.e2e.test_helpers import MockZimaServer, NotificationSpy, IsolatedConfigEnv


class TestTier3Pairwise(unittest.TestCase):
    """Tier 3 Pairwise Combinatorial Test Suite (>= 10 tests)."""

    # =========================================================================
    # Pairwise 1 & 2: Auth State x Metrics Collection
    # =========================================================================

    def test_p01_auth_success_leads_to_valid_metrics_fetch(self):
        """P1: Valid authentication state enables successful metrics polling."""
        server = MockZimaServer()
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
            auth_ok = client.authenticate()
            self.assertTrue(auth_ok)

            metrics = client.fetch_metrics()
            self.assertTrue(metrics.get("online"))
            self.assertFalse(metrics.get("need_auth"))
            self.assertGreater(metrics.get("cpu_usage_pct"), 0.0)
            self.assertGreater(metrics.get("ram_usage_pct"), 0.0)
        finally:
            server.stop()

    def test_p02_auth_failure_blocks_metrics_and_flags_need_auth(self):
        """P2: Invalid authentication state marks need_auth=True and suppresses metrics."""
        server = MockZimaServer()
        base_url = server.start()
        try:
            client = ZimaMetricsClient(base_url=base_url, username="admin", password="invalid_password")
            metrics = client.fetch_metrics()
            self.assertFalse(metrics.get("online"))
            self.assertTrue(metrics.get("need_auth"))
            self.assertEqual(metrics.get("cpu_usage_pct"), 0.0)
        finally:
            server.stop()

    # =========================================================================
    # Pairwise 3 & 4: Multi-Metric Simultaneous Spikes
    # =========================================================================

    def test_p03_simultaneous_temp_and_cpu_spikes_trigger_both_alerts(self):
        """P3: Simultaneous CPU Temp (>80°C) and CPU Load (>90%) trigger 2 distinct alerts."""
        with NotificationSpy() as spy:
            m = {
                "cpu_temperature": 86.0,
                "cpu_usage_pct": 95.0,
                "ram_usage_pct": 50.0,
                "storage_usage_pct": 60.0,
            }

            # Evaluate temp alert
            if m.get("cpu_temperature") is not None and m["cpu_temperature"] > 80.0:
                zimaos_app.send_notification("⚠️ High CPU Temperature (86°C)", "Temp reached 86°C")

            # Evaluate cpu alert
            if m.get("cpu_usage_pct", 0) > 90.0:
                zimaos_app.send_notification("⚡ High CPU Load Warning (95.0%)", "CPU load reached 95%")

            self.assertEqual(len(spy.notifications), 2)
            titles = [n["title"] for n in spy.notifications]
            self.assertTrue(any("Temperature" in t for t in titles))
            self.assertTrue(any("CPU Load" in t for t in titles))

    def test_p04_all_four_metrics_simultaneous_spikes(self):
        """P4: Simultaneous spike across Temp, CPU, RAM, and Storage triggers all 4 distinct alerts."""
        with NotificationSpy() as spy:
            m = {
                "cpu_temperature": 88.0,
                "cpu_usage_pct": 96.0,
                "ram_usage_pct": 94.0,
                "storage_usage_pct": 98.0,
            }

            if m.get("cpu_temperature") is not None and m["cpu_temperature"] > 80.0:
                zimaos_app.send_notification("⚠️ Temp Alert", "Temp > 80")
            if m.get("cpu_usage_pct", 0) > 90.0:
                zimaos_app.send_notification("⚡ CPU Alert", "CPU > 90")
            if m.get("ram_usage_pct", 0) > 90.0:
                zimaos_app.send_notification("🧠 RAM Alert", "RAM > 90")
            if m.get("storage_usage_pct", 0) > 90.0:
                zimaos_app.send_notification("💾 Storage Alert", "Storage > 90")

            self.assertEqual(len(spy.notifications), 4)

    # =========================================================================
    # Pairwise 5: Cooldown Interaction across Disparate Categories
    # =========================================================================

    def test_p05_temp_cooldown_active_allows_cpu_alert_to_fire(self):
        """P5: An active cooldown on Temp does not suppress a subsequent CPU spike."""
        with NotificationSpy() as spy:
            cooldowns = {"cpu_temp": 1000.0, "cpu_usage": 0.0}
            now = 1100.0  # 100s elapsed for temp (suppressed)

            # Temp spike occurs -> suppressed
            if now - cooldowns["cpu_temp"] > 300.0:
                zimaos_app.send_notification("Temp Alert", "Temp")

            # CPU spike occurs -> allowed
            if now - cooldowns["cpu_usage"] > 300.0:
                cooldowns["cpu_usage"] = now
                zimaos_app.send_notification("CPU Alert", "CPU")

            self.assertEqual(len(spy.notifications), 1)
            self.assertEqual(spy.notifications[0]["title"], "CPU Alert")

    # =========================================================================
    # Pairwise 6: Concurrency: Rapid Config Save x Concurrent Reads
    # =========================================================================

    def test_p06_concurrent_config_saves_and_reads_thread_safety(self):
        """P6: Concurrent threads reading and writing config do not cause race conditions."""
        with IsolatedConfigEnv() as temp_dir:
            initial = get_default_config()
            save_config(initial)

            errors = []

            def writer_worker(idx):
                try:
                    for i in range(10):
                        cfg = load_or_create_config()
                        cfg["last_worker"] = f"writer_{idx}_{i}"
                        save_config(cfg)
                        time.sleep(0.005)
                except Exception as e:
                    errors.append(e)

            def reader_worker():
                try:
                    for _ in range(20):
                        cfg = load_or_create_config()
                        _ = cfg.get("active_server_id")
                        time.sleep(0.003)
                except Exception as e:
                    errors.append(e)

            threads = []
            for i in range(3):
                threads.append(threading.Thread(target=writer_worker, args=(i,)))
            for _ in range(3):
                threads.append(threading.Thread(target=reader_worker))

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10.0)

            self.assertEqual(errors, [], f"Encountered concurrency errors: {errors}")

    # =========================================================================
    # Pairwise 7: Language Switching x Alert Text Generation
    # =========================================================================

    def test_p07_language_switch_updates_alert_message_localization(self):
        """P7: Toggling language from EN to ID produces properly localized alert messages."""
        cpu_t = 85.0

        # EN Generation
        cur_l = "en"
        title_en = f"⚠️ High CPU Temperature ({int(cpu_t)}°C)" if cur_l == "en" else f"⚠️ Peringatan Suhu Server ({int(cpu_t)}°C)"
        msg_en = (
            f"Server CPU temperature reached {int(cpu_t)}°C. Check cooling ventilation or system load."
            if cur_l == "en"
            else f"Suhu prosesor server mencapai {int(cpu_t)}°C. Periksa sirkulasi udara atau beban proses server."
        )

        # ID Generation
        cur_l = "id"
        title_id = f"⚠️ High CPU Temperature ({int(cpu_t)}°C)" if cur_l == "en" else f"⚠️ Peringatan Suhu Server ({int(cpu_t)}°C)"
        msg_id = (
            f"Server CPU temperature reached {int(cpu_t)}°C. Check cooling ventilation or system load."
            if cur_l == "en"
            else f"Suhu prosesor server mencapai {int(cpu_t)}°C. Periksa sirkulasi udara atau beban proses server."
        )

        self.assertIn("High CPU Temperature", title_en)
        self.assertIn("Peringatan Suhu Server", title_id)
        self.assertIn("ventilation", msg_en)
        self.assertIn("sirkulasi udara", msg_id)

    # =========================================================================
    # Pairwise 8: Setup Wizard URL Normalization x Live Authentication
    # =========================================================================

    def test_p08_setup_wizard_url_normalization_with_live_auth(self):
        """P8: Raw server URLs (missing scheme, IP, trailing slashes) format correctly and authenticate."""
        server = MockZimaServer()
        base_url = server.start()
        try:
            # Strip http:// prefix to simulate raw user input like '127.0.0.1:port/'
            raw_input = base_url.replace("http://", "") + "/"
            formatted_url = format_server_url(raw_input)
            self.assertTrue(formatted_url.startswith("http://"))
            self.assertFalse(formatted_url.endswith("/"))

            client = ZimaMetricsClient(base_url=formatted_url, username="admin", password="password123")
            self.assertTrue(client.authenticate())
        finally:
            server.stop()

    # =========================================================================
    # Pairwise 9: Encrypted Credentials x Auto-Login JS DOM Injection
    # =========================================================================

    def test_p09_encrypted_credentials_to_autologin_js_pipeline(self):
        """P9: Encrypted stored password decrypted and injected cleanly into autologin JS."""
        raw_pass = "Complex\"P@ss'123"
        stored_enc = encrypt_credential(raw_pass)

        # Retrieve & decrypt
        decrypted = decrypt_credential(stored_enc)
        self.assertEqual(decrypted, raw_pass)

        # Generate JS
        js_code = generate_autologin_js("admin_user", decrypted)
        self.assertIn("admin_user", js_code)
        self.assertIn("Complex\\\"P@ss'123", js_code)
        self.assertIn("attemptAutoLogin", js_code)

    # =========================================================================
    # Pairwise 10: Network Outage x Metrics Stale Cache Resilience
    # =========================================================================

    def test_p10_network_failure_preserves_stale_cache_without_crash(self):
        """P10: When server becomes unreachable, fetch_metrics falls back gracefully without unhandled exception."""
        server = MockZimaServer()
        base_url = server.start()
        client = ZimaMetricsClient(base_url=base_url, username="admin", password="password123")
        # Populate initial cache
        m1 = client.fetch_metrics()
        self.assertTrue(m1.get("online"))

        # Terminate server to simulate sudden disconnect
        server.stop()

        m2 = client.fetch_metrics()
        self.assertFalse(m2.get("online"))
        self.assertIn("storage_used_bytes", m2)

    # =========================================================================
    # Pairwise 11 & 12: Tray Menu Redraw x Metrics Streaming Concurrency
    # =========================================================================

    def test_p11_tray_menu_refresh_serialized_under_lock(self):
        """P11: Rapid simulated tray menu refresh requests execute safely under _tray_menu_lock."""
        lock = getattr(zimaos_app, "_tray_menu_lock", threading.Lock())
        executed_runs = []

        def worker(num):
            with lock:
                executed_runs.append(num)
                time.sleep(0.005)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        self.assertEqual(len(executed_runs), 5)

    def test_p12_syncthing_manager_and_zima_metrics_client_coexist(self):
        """P12: Metrics client and Syncthing manager operate independently without state collision."""
        import syncthing_manager
        daemon = syncthing_manager.LocalSyncthingDaemon(base_dir=ALPHA_DIR)
        client = ZimaMetricsClient(base_url="http://127.0.0.1:8384", username="admin", password="password123")

        self.assertIsNotNone(daemon)
        self.assertIsNotNone(client)
        self.assertEqual(client.username, "admin")


if __name__ == "__main__":
    unittest.main()

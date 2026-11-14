import ctypes
import http.server
import json
import logging
import os
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch


def _install_linux_win_stubs():
    """Install minimal Windows stubs when running unit tests on Linux."""
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

    if "winreg" not in sys.modules:
        winreg_stub = types.ModuleType("winreg")
        winreg_stub.HKEY_CURRENT_USER = 0x80000001
        winreg_stub.KEY_READ = 0x20019
        winreg_stub.KEY_WRITE = 0x20006
        winreg_stub.REG_SZ = 1

        def _noop(*_args, **_kwargs):
            raise FileNotFoundError("stub winreg")

        winreg_stub.OpenKey = _noop
        winreg_stub.CreateKey = _noop
        winreg_stub.QueryValueEx = _noop
        winreg_stub.SetValueEx = _noop
        winreg_stub.CloseKey = lambda *_args, **_kwargs: None
        sys.modules["winreg"] = winreg_stub


_install_linux_win_stubs()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config_manager  # noqa: E402
import myserver_core_service as core  # noqa: E402


class _OkHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format, *args):
        return


class _FakeZimaClientSuccess:
    last_init_kwargs = None

    def __init__(self, **kwargs):
        _FakeZimaClientSuccess.last_init_kwargs = dict(kwargs)
        self.base_url = kwargs.get("base_url") or "http://10.0.0.5:80"
        self.username = kwargs.get("username", "")
        self.password = kwargs.get("password", "")
        self.token = "tok_wizard_123"
        self.is_admin = True

    def authenticate(self):
        return True

    def fetch_zerotier_network_info(self):
        return {
            "network_id": "8056c2e21c000001",
            "remote_ipv4": "10.147.20.42",
            "status": "OK",
        }


class _FakeZimaClientBadAuth(_FakeZimaClientSuccess):
    def authenticate(self):
        self.token = None
        return False


class _FakeZimaClientUnreachable(_FakeZimaClientSuccess):
    def authenticate(self):
        raise ConnectionError("Connection refused to ZimaOS host")


class _CapturingLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(self.format(record))


class WizardEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None

        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), core.CoreApiHandler
        )
        self.port = self.server.server_port
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.server_thread.start()

        self.log_handler = _CapturingLogHandler()
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        self._attached_logger = root_logger

    def tearDown(self):
        self._attached_logger.removeHandler(self.log_handler)
        self.server.shutdown()
        self.server.server_close()
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()

    def _request_json(self, method, path, payload=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(data))
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    return resp.status, json.loads(raw)
                except Exception:
                    return resp.status, {"_raw": raw}
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8", errors="replace")
            try:
                return err.code, json.loads(raw)
            except Exception:
                return err.code, {"_raw": raw}

    def _read_disk_config(self):
        cfg_path = os.path.join(self.tmp_dir.name, "config.json")
        with open(cfg_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write_disk_config(self, cfg):
        config_manager.save_config(cfg)

    def test_load_settings_first_run_setup_and_save_settings_guards(self):
        cfg = config_manager.get_default_config()
        cfg["first_run_setup"] = True
        self._write_disk_config(cfg)

        status, loaded = self._request_json("POST", "/api/load_settings", {})
        self.assertEqual(status, 200)
        self.assertIn("firstRunSetup", loaded)
        self.assertIs(loaded["firstRunSetup"], True)

        # Cannot set firstRunSetup=False while no valid configured server exists
        status, saved = self._request_json(
            "POST",
            "/api/save_settings",
            {"settings": {"firstRunSetup": False}},
        )
        self.assertEqual(status, 200)
        self.assertIs(saved.get("success"), True)

        status, after_blocked = self._request_json("POST", "/api/load_settings", {})
        self.assertEqual(status, 200)
        self.assertIs(after_blocked.get("firstRunSetup"), True)

        # Once a valid server exists, firstRunSetup=False can be saved and reopened
        cfg = config_manager.load_or_create_config()
        cfg["servers"][0]["name"] = "My Home NAS"
        cfg["servers"][0]["connections"] = [
            {"id": "conn_lan", "name": "LAN", "url": "http://192.168.1.50:80"}
        ]
        cfg["servers"][0]["credentials"] = {
            "Admin": {
                "username": "admin",
                "password": config_manager.encrypt_credential("Secret!1"),
            }
        }
        self._write_disk_config(cfg)

        status, _ = self._request_json(
            "POST",
            "/api/save_settings",
            {"settings": {"firstRunSetup": False}},
        )
        self.assertEqual(status, 200)
        status, after_done = self._request_json("POST", "/api/load_settings", {})
        self.assertEqual(status, 200)
        self.assertIs(after_done.get("firstRunSetup"), False)

        # Manual reopen writes first_run_setup=True to disk
        status, _ = self._request_json(
            "POST",
            "/api/save_settings",
            {"settings": {"firstRunSetup": True}},
        )
        self.assertEqual(status, 200)
        self.assertIs(self._read_disk_config().get("first_run_setup"), True)

    def test_wizard_verify_zimaos_success_and_errors_without_password_leak(self):
        secret_pw = "UltraSecretZimaPass!987"

        # Validation error for missing required fields -> 400
        status, body = self._request_json(
            "POST",
            "/api/wizard/verify_zimaos",
            {"url": "", "username": "admin", "password": ""},
        )
        self.assertEqual(status, 400)
        self.assertIs(body.get("success"), False)

        with patch.object(core, "ZimaMetricsClient", _FakeZimaClientSuccess):
            status, body = self._request_json(
                "POST",
                "/api/wizard/verify_zimaos",
                {
                    "url": "10.0.0.5:80",
                    "username": "admin",
                    "password": secret_pw,
                },
            )
        self.assertEqual(status, 200)
        self.assertIs(body.get("success"), True)
        self.assertEqual(body.get("username"), "admin")
        self.assertEqual(body.get("resolvedUrl"), "http://10.0.0.5:80")
        self.assertEqual(body.get("zerotierNetworkId"), "8056c2e21c000001")
        self.assertEqual(body.get("zerotierIp"), "10.147.20.42")
        self.assertEqual(body.get("ztStatus"), "OK")
        self.assertNotIn(secret_pw, json.dumps(body))

        # Auth failure -> 401
        with patch.object(core, "ZimaMetricsClient", _FakeZimaClientBadAuth):
            status, body = self._request_json(
                "POST",
                "/api/wizard/verify_zimaos",
                {
                    "url": "http://10.0.0.5:80",
                    "username": "admin",
                    "password": secret_pw,
                },
            )
        self.assertEqual(status, 401)
        self.assertIs(body.get("success"), False)
        self.assertNotIn(secret_pw, json.dumps(body))

        # Unreachable host -> 503
        with patch.object(core, "ZimaMetricsClient", _FakeZimaClientUnreachable):
            status, body = self._request_json(
                "POST",
                "/api/wizard/verify_zimaos",
                {
                    "url": "http://10.0.0.5:80",
                    "username": "admin",
                    "password": secret_pw,
                },
            )
        self.assertEqual(status, 503)
        self.assertIs(body.get("success"), False)
        self.assertNotIn(secret_pw, json.dumps(body))

        combined_logs = "\n".join(self.log_handler.messages)
        self.assertNotIn(secret_pw, combined_logs)

    def test_wizard_commit_server_reuses_srv_default_and_writes_nested_schema(self):
        cfg = config_manager.get_default_config()
        self._write_disk_config(cfg)
        secret_pw = "CommitSecretPass!42"

        payload = {
            "name": "Rumah Server",
            "localUrl": "192.168.1.50:80",
            "wanUrl": "https://nas.example.com",
            "zerotierNetworkId": "net1234567890",
            "zerotierVirtualIp": "10.147.17.5",
            "username": "admin",
            "password": secret_pw,
        }

        with patch.object(
            config_manager,
            "encrypt_credential",
            wraps=config_manager.encrypt_credential,
        ) as enc_spy:
            status, body = self._request_json(
                "POST", "/api/wizard/commit_server", payload
            )
        self.assertEqual(status, 200)
        self.assertIs(body.get("success"), True)
        self.assertEqual(body.get("serverId"), "srv_default")
        self.assertNotIn(secret_pw, json.dumps(body))
        self.assertGreaterEqual(enc_spy.call_count, 1)

        disk = self._read_disk_config()
        self.assertEqual(disk.get("active_server_id"), "srv_default")
        self.assertEqual(len(disk.get("servers", [])), 1)
        srv = disk["servers"][0]
        self.assertEqual(srv["id"], "srv_default")
        self.assertEqual(srv["name"], "Rumah Server")
        self.assertEqual(srv.get("zerotier_network_id"), "net1234567890")
        self.assertEqual(srv.get("remote_id"), "net1234567890")
        self.assertEqual(srv.get("zerotier_virtual_ip"), "10.147.17.5")
        self.assertEqual(srv.get("active_profile"), "Admin")
        self.assertIn("Admin", srv.get("profiles", []))

        conns = srv.get("connections", [])
        self.assertGreaterEqual(len(conns), 2)
        self.assertTrue(all("id" in c and "name" in c and "url" in c for c in conns))
        self.assertEqual(conns[0]["url"], "http://192.168.1.50:80")
        wan_conn = next((c for c in conns if c.get("id") == "conn_wan"), None)
        self.assertIsNotNone(wan_conn)
        self.assertEqual(wan_conn.get("type"), "domain")
        self.assertEqual(wan_conn.get("url"), "https://nas.example.com")

        stored_admin = srv["credentials"]["Admin"]
        self.assertEqual(stored_admin["username"], "admin")
        self.assertEqual(
            config_manager.decrypt_credential(stored_admin["password"]),
            secret_pw,
        )
        self.assertTrue(config_manager.has_valid_configured_server(disk))

        # Re-commit idempotently without creating duplicate srv_default
        payload2 = dict(payload)
        payload2["name"] = "Rumah Server Updated"
        payload2["wanUrl"] = ""
        status2, body2 = self._request_json(
            "POST", "/api/wizard/commit_server", payload2
        )
        self.assertEqual(status2, 200)
        self.assertEqual(body2.get("serverId"), "srv_default")
        disk2 = self._read_disk_config()
        self.assertEqual(len(disk2["servers"]), 1)
        self.assertEqual(disk2["servers"][0]["name"], "Rumah Server Updated")

        combined_logs = "\n".join(self.log_handler.messages)
        self.assertNotIn(secret_pw, combined_logs)

    def test_save_server_updates_credentials_retains_names_and_sets_active(self):
        cfg = config_manager.get_default_config()
        cfg["servers"] = [
            {
                "id": "srv_existing",
                "name": "Existing NAS",
                "connections": [{"id": "c1", "url": "http://10.0.0.2:80"}],
                "credentials": {
                    "Admin": {
                        "username": "old",
                        "password": config_manager.encrypt_credential("OldPass!1"),
                    }
                },
                "profiles": ["Admin"],
                "active_profile": "Admin",
            }
        ]
        cfg["active_server_id"] = "srv_existing"
        self._write_disk_config(cfg)

        status, body = self._request_json(
            "POST",
            "/api/save_server",
            {
                "id": "srv_existing",
                "name": "Renamed NAS",
                "url": "10.0.0.9:80",
                "username": "newadmin",
                "password": "UpdatedPass!77",
            },
        )
        self.assertEqual(status, 200)
        self.assertIs(body.get("success"), True)

        disk = self._read_disk_config()
        srv = next(s for s in disk["servers"] if s["id"] == "srv_existing")
        self.assertIn("name", srv["connections"][0])
        self.assertEqual(srv["connections"][0]["url"], "http://10.0.0.9:80")
        self.assertEqual(srv["credentials"]["Admin"]["username"], "newadmin")
        self.assertEqual(
            config_manager.decrypt_credential(srv["credentials"]["Admin"]["password"]),
            "UpdatedPass!77",
        )

        # Creating a new server sets active_server_id unless setActive is False
        status, body_new = self._request_json(
            "POST",
            "/api/save_server",
            {
                "name": "Second NAS",
                "url": "10.0.0.20:80",
                "username": "sec",
                "password": "SecPass!9",
            },
        )
        self.assertEqual(status, 200)
        self.assertIs(body_new.get("success"), True)
        disk_after = self._read_disk_config()
        new_id = body_new.get("server", {}).get("id") or body_new.get("serverId")
        self.assertTrue(new_id)
        self.assertEqual(disk_after.get("active_server_id"), new_id)

    def test_wizard_complete_gates_on_valid_server_and_is_idempotent(self):
        cfg = config_manager.get_default_config()
        cfg["first_run_setup"] = True
        self._write_disk_config(cfg)

        # Gate must block while no valid server exists
        status, body = self._request_json("POST", "/api/wizard/complete", {})
        self.assertEqual(status, 400)
        self.assertIs(body.get("success"), False)
        self.assertEqual(body.get("error"), "wizard_incomplete")
        self.assertIs(self._read_disk_config().get("first_run_setup"), True)

        # Commit valid server first
        status_c, _ = self._request_json(
            "POST",
            "/api/wizard/commit_server",
            {
                "name": "Prod NAS",
                "localUrl": "192.168.1.88:80",
                "username": "admin",
                "password": "ValidPassword!1",
            },
        )
        self.assertEqual(status_c, 200)

        # First complete succeeds
        status1, res1 = self._request_json("POST", "/api/wizard/complete", {})
        self.assertEqual(status1, 200)
        self.assertIs(res1.get("success"), True)
        self.assertIs(res1.get("firstRunSetup"), False)
        self.assertIs(self._read_disk_config().get("first_run_setup"), False)

        # Second complete is idempotent
        status2, res2 = self._request_json("POST", "/api/wizard/complete", {})
        self.assertEqual(status2, 200)
        self.assertIs(res2.get("success"), True)
        self.assertIs(res2.get("firstRunSetup"), False)

    def test_probe_url_and_call_core_api_wizard_slugs(self):
        probe_srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _OkHandler)
        probe_thread = threading.Thread(target=probe_srv.serve_forever, daemon=True)
        probe_thread.start()
        try:
            target_url = f"http://127.0.0.1:{probe_srv.server_port}"

            # Direct POST /api/probe_url
            status, body = self._request_json(
                "POST", "/api/probe_url", {"url": target_url}
            )
            self.assertEqual(status, 200)
            self.assertIs(body.get("reachable"), True)

            # Wrapped via /api/call_core_api
            status_ep, body_ep = self._request_json(
                "POST",
                "/api/call_core_api",
                {"endpoint": "probe_url", "url": target_url},
            )
            self.assertEqual(status_ep, 200)
            self.assertIs(body_ep.get("reachable"), True)
        finally:
            probe_srv.shutdown()
            probe_srv.server_close()

        # Wizard slugs via /api/call_core_api
        with patch.object(core, "ZimaMetricsClient", _FakeZimaClientSuccess):
            st_v, res_v = self._request_json(
                "POST",
                "/api/call_core_api",
                {
                    "endpoint": "wizard/verify_zimaos",
                    "url": "10.0.0.5:80",
                    "username": "admin",
                    "password": "Pw!1",
                },
            )
            self.assertEqual(st_v, 200)
            self.assertIs(res_v.get("success"), True)

        st_c, res_c = self._request_json(
            "POST",
            "/api/call_core_api",
            {
                "endpoint": "wizard/commit_server",
                "name": "Via Core API",
                "localUrl": "192.168.1.99:80",
                "username": "admin",
                "password": "Pw!1",
            },
        )
        self.assertEqual(st_c, 200)
        self.assertIs(res_c.get("success"), True)

        st_done, res_done = self._request_json(
            "POST",
            "/api/call_core_api",
            {"endpoint": "wizard/complete"},
        )
        self.assertEqual(st_done, 200)
        self.assertIs(res_done.get("firstRunSetup"), False)

    def test_syncthing_server_route_persists_and_reads_remote_ip_port_https(self):
        cfg = config_manager.get_default_config()
        cfg["servers"][0]["zerotier_virtual_ip"] = "10.147.20.77"
        cfg["servers"][0]["connections"] = [
            {"id": "conn_lan", "name": "LAN", "url": "http://192.168.1.50:80"}
        ]
        self._write_disk_config(cfg)

        # Fallback remote_ip from zerotier_virtual_ip and default remote_port/remote_https
        status, initial = self._request_json("POST", "/api/get_syncthing_config", {})
        self.assertEqual(status, 200)
        self.assertIs(initial.get("success"), True)
        srv_section = initial.get("server", {})
        self.assertEqual(srv_section.get("remote_ip"), "10.147.20.77")
        self.assertEqual(srv_section.get("remote_port"), "8384")
        self.assertIs(srv_section.get("remote_https"), False)

        # Persist explicit remote_ip, remote_port, remote_https
        status, saved = self._request_json(
            "POST",
            "/api/save_syncthing_server_route",
            {
                "remote_ip": "10.147.20.99",
                "remote_port": "8443",
                "remote_https": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertIs(saved.get("success"), True)

        status, updated = self._request_json("POST", "/api/get_syncthing_config", {})
        self.assertEqual(status, 200)
        srv_after = updated.get("server", {})
        self.assertEqual(srv_after.get("remote_ip"), "10.147.20.99")
        self.assertEqual(srv_after.get("remote_port"), "8443")
        self.assertIs(srv_after.get("remote_https"), True)

        disk = self._read_disk_config()
        b_app = disk["servers"][0].get("backup_app", {})
        self.assertEqual(b_app.get("remote_ip"), "10.147.20.99")
        self.assertEqual(b_app.get("remote_port"), "8443")
        self.assertIs(b_app.get("remote_https"), True)


if __name__ == "__main__":
    unittest.main()

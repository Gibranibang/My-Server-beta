import ctypes
import http.server
import json
import os
import sys
import tempfile
import threading
import types
import unittest
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
if REPO_ROOT not in sys.modules and REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config_manager  # noqa: E402
import smb_mount_manager  # noqa: E402


class _MockBackendApiState:
    def __init__(self):
        self.valid_users = {
            "staff_budi": {
                "password": "StaffSecret!9",
                "role": "staff",
                "allowed_disks": ["Media", "Shared"],
            },
            "admin_ops": {
                "password": "AdminOps!99",
                "role": "admin",
                "allowed_disks": [],
            },
        }
        self.active_tokens = {}
        self.expired_tokens = {"expired.jwt.30d"}
        self.token_seq = 0
        self.verify_calls = []
        self.disks_calls = []
        self.force_disks_status = None
        self.all_disks = [
            {"name": "Media", "relative_path": "Media", "is_accessible": True},
            {"name": "Shared", "relative_path": "Shared", "is_accessible": True},
            {"name": "Private", "relative_path": "Private", "is_accessible": False},
            {"name": "Root", "relative_path": "", "is_accessible": True},
        ]


def _start_mock_backend_server(state):
    class _Handler(http.server.BaseHTTPRequestHandler):
        def _read_json(self):
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _send(self, code, payload):
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            body = self._read_json()
            if self.path == "/api/v1/auth/verify":
                uname = str(body.get("username") or "").strip()
                pwd = str(body.get("password") or "")
                state.verify_calls.append({"username": uname, "password": pwd})
                rec = state.valid_users.get(uname)
                if not rec or rec["password"] != pwd:
                    self._send(401, {"detail": "Invalid username or password"})
                    return
                state.token_seq += 1
                tok = f"fresh.jwt.tok.{state.token_seq}"
                state.active_tokens[tok] = uname
                self._send(
                    200,
                    {
                        "success": True,
                        "access_token": tok,
                        "token_type": "bearer",
                        "user_id": 2,
                        "username": uname,
                        "role": rec["role"],
                        "allowed_disks": list(rec["allowed_disks"]),
                    },
                )
                return
            self._send(404, {"detail": "Not found"})

        def do_GET(self):
            if self.path == "/api/v1/storage/disks":
                auth_hdr = self.headers.get("Authorization", "")
                tok = auth_hdr[7:].strip() if auth_hdr.startswith("Bearer ") else ""
                state.disks_calls.append(tok)
                if state.force_disks_status is not None:
                    self._send(state.force_disks_status, {"detail": "Forced error"})
                    return
                if not tok or tok in state.expired_tokens or tok not in state.active_tokens:
                    self._send(401, {"detail": "Token expired or invalid"})
                    return
                uname = state.active_tokens[tok]
                rec = state.valid_users[uname]
                disks_out = []
                for d in state.all_disks:
                    item = dict(d)
                    if rec["role"] != "admin" and d["name"] not in rec["allowed_disks"]:
                        item["is_accessible"] = False
                    disks_out.append(item)
                self._send(200, {"disks": disks_out, "username": uname})
                return
            self._send(404, {"detail": "Not found"})

        def log_message(self, format, *args):
            return

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


class TestSmbSourceConfigAndMountManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None
        smb_mount_manager.clear_smb_share_cache()

        cfg = config_manager.get_default_config()
        cfg["servers"] = [
            {
                "id": "srv_1",
                "name": "HomeNAS",
                "connections": [{"id": "c_lan", "name": "LAN", "url": "http://192.168.55.50:80"}],
                "credentials": {
                    "Admin": {
                        "username": "zima_admin",
                        "password": config_manager.encrypt_credential("ZimaAdminPass!9"),
                    }
                },
                "profiles": ["Admin"],
                "active_profile": "Admin",
            }
        ]
        cfg["active_server_id"] = "srv_1"
        config_manager.save_config(cfg)

    def tearDown(self):
        smb_mount_manager.clear_smb_share_cache()
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()

    def test_01_dpapi_smb_source_isolation_from_zimaos_credentials(self):
        cfg = config_manager.load_or_create_config()
        srv = cfg["servers"][0]

        # Legacy server without smb_source / backend_smb_auth defaults cleanly to zimaos
        initial = config_manager.get_server_smb_source_config(srv)
        self.assertEqual(initial["source"], "zimaos")
        self.assertEqual(initial["username"], "")
        self.assertEqual(initial["password"], "")
        self.assertEqual(initial["access_token"], "")
        self.assertEqual(initial["allowed_disks"], [])
        self.assertFalse(initial["hasCredentials"])

        # Save backend source + encrypted password & access_token
        ok = config_manager.save_server_smb_source_config(
            cfg,
            "srv_1",
            "backend",
            username="staff_budi",
            password="StaffSecret!9",
            role="staff",
            allowed_disks=["Media", "Backup"],
            access_token="jwt.token.abc123",
        )
        self.assertTrue(ok)

        reloaded = config_manager.load_or_create_config()
        srv_after = reloaded["servers"][0]

        # ZimaOS credentials & active_profile MUST remain untouched
        self.assertEqual(srv_after["active_profile"], "Admin")
        zima_creds = config_manager.get_server_credentials(srv_after, "Admin")
        self.assertEqual(zima_creds["username"], "zima_admin")
        self.assertEqual(zima_creds["password"], "ZimaAdminPass!9")

        # Raw stored password and access_token must be encrypted (dpapi: or enc:)
        raw_auth = srv_after["backend_smb_auth"]
        self.assertTrue(
            raw_auth["password"].startswith(("dpapi:", "enc:")),
            f"Password must be encrypted: {raw_auth['password']}",
        )
        self.assertTrue(
            raw_auth["access_token"].startswith(("dpapi:", "enc:")),
            f"Access token must be encrypted: {raw_auth['access_token']}",
        )
        self.assertNotIn("StaffSecret!9", json.dumps(reloaded))
        self.assertNotIn("jwt.token.abc123", json.dumps(reloaded))

        # Decrypted getter returns full isolated values
        parsed = config_manager.get_server_smb_source_config(srv_after)
        self.assertEqual(parsed["source"], "backend")
        self.assertEqual(parsed["username"], "staff_budi")
        self.assertEqual(parsed["password"], "StaffSecret!9")
        self.assertEqual(parsed["access_token"], "jwt.token.abc123")
        self.assertEqual(parsed["role"], "staff")
        self.assertEqual(parsed["allowed_disks"], ["Media", "Backup"])
        self.assertTrue(parsed["hasCredentials"])

        # Refreshing access_token with password=None preserves encrypted password
        config_manager.save_server_smb_source_config(
            reloaded,
            "srv_1",
            "backend",
            access_token="jwt.token.refreshed",
        )
        parsed_refreshed = config_manager.get_server_smb_source_config(
            config_manager.load_or_create_config()["servers"][0]
        )
        self.assertEqual(parsed_refreshed["password"], "StaffSecret!9")
        self.assertEqual(parsed_refreshed["access_token"], "jwt.token.refreshed")

        # Changing username without new token clears stale access_token
        config_manager.save_server_smb_source_config(
            config_manager.load_or_create_config(),
            "srv_1",
            "backend",
            username="other_staff",
            password="OtherPass!1",
        )
        parsed_changed = config_manager.get_server_smb_source_config(
            config_manager.load_or_create_config()["servers"][0]
        )
        self.assertEqual(parsed_changed["username"], "other_staff")
        self.assertEqual(parsed_changed["access_token"], "")

        # Explicit clear when username="" and password=""
        config_manager.save_server_smb_source_config(
            config_manager.load_or_create_config(),
            "srv_1",
            "zimaos",
            username="",
            password="",
            access_token="",
        )
        parsed_cleared = config_manager.get_server_smb_source_config(
            config_manager.load_or_create_config()["servers"][0]
        )
        self.assertEqual(parsed_cleared["source"], "zimaos")
        self.assertFalse(parsed_cleared["hasCredentials"])
        self.assertEqual(parsed_cleared["access_token"], "")

    def test_02_normalize_backend_api_url_and_silent_401_reauth(self):
        norm = smb_mount_manager._normalize_backend_api_url
        self.assertEqual(norm("http://192.168.55.50:80"), "http://192.168.55.50:8080")
        self.assertEqual(norm("10.126.126.2"), "http://10.126.126.2:8080")
        self.assertEqual(
            norm("https://nas.example.com", fallback_host="10.126.126.2"),
            "http://10.126.126.2:8080",
        )
        self.assertEqual(norm("https://nas.example.com"), "http://nas.example.com:8080")
        self.assertEqual(norm("http://127.0.0.1:54321"), "http://127.0.0.1:54321")
        self.assertEqual(norm("http://[::1]:80"), "http://[::1]:8080")
        self.assertEqual(norm("", fallback_host="::1"), "http://[::1]:8080")
        self.assertEqual(norm(""), "")

        state = _MockBackendApiState()
        srv, backend_url = _start_mock_backend_server(state)
        try:
            refreshed = []

            # Case A: empty token -> verifies once and fetches accessible disks
            shares_a = smb_mount_manager.fetch_shares_from_backend_api(
                backend_url,
                username="staff_budi",
                password="StaffSecret!9",
                auth_token="",
                on_token_refreshed=lambda tok, payload: refreshed.append((tok, payload)),
            )
            self.assertEqual(shares_a, ["Media", "Shared"])
            self.assertEqual(len(state.verify_calls), 1)
            self.assertEqual(len(refreshed), 1)
            self.assertEqual(refreshed[0][0], "fresh.jwt.tok.1")

            # Case B: expired 30-day JWT -> 401 -> silent single re-auth -> retry succeeds
            state.verify_calls.clear()
            state.disks_calls.clear()
            refreshed.clear()
            shares_b = smb_mount_manager.fetch_shares_from_backend_api(
                backend_url,
                username="staff_budi",
                password="StaffSecret!9",
                auth_token="expired.jwt.30d",
                on_token_refreshed=lambda tok, payload: refreshed.append((tok, payload)),
            )
            self.assertEqual(shares_b, ["Media", "Shared"])
            self.assertEqual(len(state.verify_calls), 1)
            self.assertEqual(state.disks_calls, ["expired.jwt.30d", "fresh.jwt.tok.2"])
            self.assertEqual(len(refreshed), 1)
            self.assertEqual(refreshed[0][0], "fresh.jwt.tok.2")

            # Case C: persistent 401 after re-auth must NOT loop
            state.verify_calls.clear()
            state.disks_calls.clear()
            state.force_disks_status = 401
            shares_c = smb_mount_manager.fetch_shares_from_backend_api(
                backend_url,
                username="staff_budi",
                password="StaffSecret!9",
                auth_token="expired.jwt.30d",
            )
            self.assertEqual(shares_c, [])
            self.assertEqual(len(state.verify_calls), 1)
            self.assertEqual(len(state.disks_calls), 2)

            # Case D: non-401 error (500) must NOT retry auth/verify
            state.verify_calls.clear()
            state.disks_calls.clear()
            state.force_disks_status = 500
            shares_d = smb_mount_manager.fetch_shares_from_backend_api(
                backend_url,
                username="staff_budi",
                password="StaffSecret!9",
                auth_token="fresh.jwt.tok.2",
            )
            self.assertEqual(shares_d, [])
            self.assertEqual(len(state.verify_calls), 0)
            self.assertEqual(len(state.disks_calls), 1)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_03_cache_key_separation_and_mount_all_forwarding(self):
        state = _MockBackendApiState()
        srv, backend_url = _start_mock_backend_server(state)
        try:
            with patch.object(
                smb_mount_manager,
                "fetch_shares_from_zimaos_api",
                return_value=["ZimaShareA", "ZimaShareB"],
            ) as mock_zima:
                z_shares = smb_mount_manager.get_remote_smb_shares(
                    host="127.0.0.1",
                    username="staff_budi",
                    password="StaffSecret!9",
                    auth_token="zima_tok",
                    base_url="http://127.0.0.1:80",
                    smb_source="zimaos",
                )
                self.assertEqual(z_shares, ["ZimaShareA", "ZimaShareB"])
                self.assertEqual(mock_zima.call_count, 1)

                # Same host & username with smb_source="backend" must NOT reuse zimaos cache
                b_shares = smb_mount_manager.get_remote_smb_shares(
                    host="127.0.0.1",
                    username="staff_budi",
                    password="StaffSecret!9",
                    auth_token="",
                    base_url="http://127.0.0.1:80",
                    smb_source="backend",
                    backend_url=backend_url,
                )
                self.assertEqual(b_shares, ["Media", "Shared"])
                # Never called ZimaOS API in backend mode
                self.assertEqual(mock_zima.call_count, 1)

                # mount_all_smb_shares forwards smb_source, backend_url, on_token_refreshed
                cb = lambda tok, data: None
                with patch.object(
                    smb_mount_manager, "resolve_smb_host", return_value="127.0.0.1"
                ), patch.object(
                    smb_mount_manager, "get_remote_smb_shares", return_value=[]
                ) as mock_get_shares:
                    smb_mount_manager.mount_all_smb_shares(
                        host="127.0.0.1",
                        username="staff_budi",
                        password="StaffSecret!9",
                        auth_token="tok_x",
                        base_url="http://127.0.0.1:80",
                        smb_source="backend",
                        backend_url=backend_url,
                        on_token_refreshed=cb,
                    )
                    mock_get_shares.assert_called_once()
                    kwargs = mock_get_shares.call_args.kwargs
                    self.assertEqual(kwargs.get("smb_source"), "backend")
                    self.assertEqual(kwargs.get("backend_url"), backend_url)
                    self.assertIs(kwargs.get("on_token_refreshed"), cb)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

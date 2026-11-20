import ctypes
import http.server
import io
import json
import logging
import os
import sys
import tarfile
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
import zipfile
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
import smb_mount_manager  # noqa: E402


class _CapturingLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(self.format(record))


class _FakeChannel:
    def __init__(self, exit_status=0):
        self._exit_status = exit_status

    def recv_exit_status(self):
        return self._exit_status


class _FakeStream:
    def __init__(self, data=b"", exit_status=0):
        self._data = data
        self.channel = _FakeChannel(exit_status=exit_status)

    def read(self):
        return self._data


class _FakeSftp:
    def __init__(self, record):
        self.record = record

    def put(self, local_path, remote_path):
        self.record["sftp_puts"].append((local_path, remote_path))

    def close(self):
        return None


def _build_fake_paramiko(record):
    fake_mod = types.ModuleType("paramiko")

    class AuthenticationException(Exception):
        pass

    class AutoAddPolicy:
        pass

    class SSHClient:
        def set_missing_host_key_policy(self, _policy):
            return None

        def connect(self, host, port=22, username="", password="", **_kwargs):
            record["connect_calls"].append(
                {"host": host, "port": port, "username": username, "password": password}
            )

        def open_sftp(self):
            return _FakeSftp(record)

        def exec_command(self, cmd, timeout=None):
            record["exec_cmds"].append((cmd, timeout))
            return _FakeStream(b""), _FakeStream(b"Install OK\n", exit_status=0), _FakeStream(b"")

        def close(self):
            record["closed"] = True

    fake_mod.AuthenticationException = AuthenticationException
    fake_mod.AutoAddPolicy = AutoAddPolicy
    fake_mod.SSHClient = SSHClient
    return fake_mod


class _FakeHttpResponse:
    def __init__(self, payload_obj, status=200):
        self._raw = json.dumps(payload_obj).encode("utf-8")
        self.status = status

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _MockBackendApiState:
    def __init__(self):
        self.valid_users = {
            "user_1": {
                "password": "UserSecret!9",
                "role": "user",
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
        self.smb_mode = "zimaos"
        self.verify_calls = []
        self.disks_calls = []
        self.status_calls = []
        self.mode_calls = []
        self.force_disks_status = None
        self.force_verify_401 = False
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

        def _check_bearer(self):
            auth_hdr = self.headers.get("Authorization", "")
            tok = auth_hdr[7:].strip() if auth_hdr.startswith("Bearer ") else ""
            if not tok or tok in state.expired_tokens or tok not in state.active_tokens:
                return None, tok
            return state.active_tokens[tok], tok

        def do_POST(self):
            body = self._read_json()
            if self.path == "/api/v1/auth/verify":
                uname = str(body.get("username") or "").strip().lower()
                pwd = str(body.get("password") or "")
                state.verify_calls.append({"username": uname, "password": pwd})
                if state.force_verify_401:
                    self._send(401, {"detail": "Forced invalid credentials"})
                    return
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

            if self.path == "/api/v1/smb/mode":
                jwt_user, tok = self._check_bearer()
                if not jwt_user:
                    self._send(401, {"detail": "Token expired or invalid"})
                    return
                rec = state.valid_users[jwt_user]
                is_admin = rec["role"] in ("admin", "root")
                mode = str(body.get("mode") or "").strip().lower()
                req_user = str(body.get("username") or "").strip().lower()
                req_pass = body.get("password")
                state.mode_calls.append({"jwt_user": jwt_user, "token": tok, "body": dict(body)})

                if mode not in ("zimaos", "backend"):
                    self._send(400, {"detail": "Invalid mode"})
                    return

                # Strict 05-01 app/routers/smb.py enforcement
                if mode == "backend":
                    if not is_admin:
                        if not req_user or req_user != jwt_user or not req_pass or req_pass != rec["password"]:
                            self._send(403, {"detail": "Forbidden: invalid user credentials"})
                            return
                    elif req_user and req_user != jwt_user:
                        self._send(403, {"detail": "Username mismatch"})
                        return
                else:
                    if not is_admin:
                        if req_user and req_user != jwt_user:
                            self._send(403, {"detail": "Username mismatch"})
                            return
                        if req_pass and req_pass != rec["password"]:
                            self._send(403, {"detail": "Invalid password"})
                            return

                state.smb_mode = mode
                self._send(
                    200,
                    {
                        "mode": state.smb_mode,
                        "backend_smbd_running": state.smb_mode == "backend",
                        "zimaos_smbd_running": state.smb_mode == "zimaos",
                        "port_445_owner": state.smb_mode,
                        "shares": [],
                    },
                )
                return

            self._send(404, {"detail": "Not found"})

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"status": "ok", "version": "1.4.0"})
                return

            if self.path == "/api/v1/smb/status":
                jwt_user, tok = self._check_bearer()
                state.status_calls.append(tok)
                if not jwt_user:
                    self._send(401, {"detail": "Token expired or invalid"})
                    return
                self._send(
                    200,
                    {
                        "mode": state.smb_mode,
                        "backend_smbd_running": state.smb_mode == "backend",
                        "zimaos_smbd_running": state.smb_mode == "zimaos",
                        "port_445_owner": state.smb_mode,
                        "shares": [],
                    },
                )
                return

            if self.path == "/api/v1/storage/disks":
                jwt_user, tok = self._check_bearer()
                state.disks_calls.append(tok)
                if state.force_disks_status is not None:
                    self._send(state.force_disks_status, {"detail": "Forced error"})
                    return
                if not jwt_user:
                    self._send(401, {"detail": "Token expired or invalid"})
                    return
                rec = state.valid_users[jwt_user]
                disks_out = []
                for d in state.all_disks:
                    item = dict(d)
                    if rec["role"] != "admin" and d["name"] not in rec["allowed_disks"]:
                        item["is_accessible"] = False
                    disks_out.append(item)
                self._send(200, {"disks": disks_out, "username": jwt_user})
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

        initial = config_manager.get_server_smb_source_config(srv)
        self.assertEqual(initial["source"], "zimaos")
        self.assertEqual(initial["username"], "")
        self.assertEqual(initial["password"], "")
        self.assertEqual(initial["access_token"], "")
        self.assertEqual(initial["allowed_disks"], [])
        self.assertFalse(initial["hasCredentials"])

        ok = config_manager.save_server_smb_source_config(
            cfg,
            "srv_1",
            "backend",
            username="user_1",
            password="UserSecret!9",
            role="user",
            allowed_disks=["Media", "Backup"],
            access_token="jwt.token.abc123",
        )
        self.assertTrue(ok)

        reloaded = config_manager.load_or_create_config()
        srv_after = reloaded["servers"][0]

        self.assertEqual(srv_after["active_profile"], "Admin")
        zima_creds = config_manager.get_server_credentials(srv_after, "Admin")
        self.assertEqual(zima_creds["username"], "zima_admin")
        self.assertEqual(zima_creds["password"], "ZimaAdminPass!9")

        raw_auth = srv_after["backend_smb_auth"]
        self.assertTrue(
            raw_auth["password"].startswith(("dpapi:", "enc:")),
            f"Password must be encrypted: {raw_auth['password']}",
        )
        self.assertTrue(
            raw_auth["access_token"].startswith(("dpapi:", "enc:")),
            f"Access token must be encrypted: {raw_auth['access_token']}",
        )
        self.assertNotIn("UserSecret!9", json.dumps(reloaded))
        self.assertNotIn("jwt.token.abc123", json.dumps(reloaded))

        parsed = config_manager.get_server_smb_source_config(srv_after)
        self.assertEqual(parsed["source"], "backend")
        self.assertEqual(parsed["username"], "user_1")
        self.assertEqual(parsed["password"], "UserSecret!9")
        self.assertEqual(parsed["access_token"], "jwt.token.abc123")
        self.assertEqual(parsed["role"], "user")
        self.assertEqual(parsed["allowed_disks"], ["Media", "Backup"])
        self.assertTrue(parsed["hasCredentials"])

        # Legacy "staff" role persisted/passed in must normalize cleanly to "user"
        config_manager.save_server_smb_source_config(
            reloaded,
            "srv_1",
            "backend",
            role="staff",
        )
        parsed_legacy = config_manager.get_server_smb_source_config(
            config_manager.load_or_create_config()["servers"][0]
        )
        self.assertEqual(parsed_legacy["role"], "user")

        config_manager.save_server_smb_source_config(
            reloaded,
            "srv_1",
            "backend",
            access_token="jwt.token.refreshed",
        )
        parsed_refreshed = config_manager.get_server_smb_source_config(
            config_manager.load_or_create_config()["servers"][0]
        )
        self.assertEqual(parsed_refreshed["password"], "UserSecret!9")
        self.assertEqual(parsed_refreshed["access_token"], "jwt.token.refreshed")

        config_manager.save_server_smb_source_config(
            config_manager.load_or_create_config(),
            "srv_1",
            "backend",
            username="other_user",
            password="OtherPass!1",
        )
        parsed_changed = config_manager.get_server_smb_source_config(
            config_manager.load_or_create_config()["servers"][0]
        )
        self.assertEqual(parsed_changed["username"], "other_user")
        self.assertEqual(parsed_changed["access_token"], "")

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

            shares_a = smb_mount_manager.fetch_shares_from_backend_api(
                backend_url,
                username="user_1",
                password="UserSecret!9",
                auth_token="",
                on_token_refreshed=lambda tok, payload: refreshed.append((tok, payload)),
            )
            self.assertEqual(shares_a, ["Media", "Shared"])
            self.assertEqual(len(state.verify_calls), 1)
            self.assertEqual(len(refreshed), 1)
            self.assertEqual(refreshed[0][0], "fresh.jwt.tok.1")

            state.verify_calls.clear()
            state.disks_calls.clear()
            refreshed.clear()
            shares_b = smb_mount_manager.fetch_shares_from_backend_api(
                backend_url,
                username="user_1",
                password="UserSecret!9",
                auth_token="expired.jwt.30d",
                on_token_refreshed=lambda tok, payload: refreshed.append((tok, payload)),
            )
            self.assertEqual(shares_b, ["Media", "Shared"])
            self.assertEqual(len(state.verify_calls), 1)
            self.assertEqual(state.disks_calls, ["expired.jwt.30d", "fresh.jwt.tok.2"])
            self.assertEqual(len(refreshed), 1)
            self.assertEqual(refreshed[0][0], "fresh.jwt.tok.2")

            state.verify_calls.clear()
            state.disks_calls.clear()
            state.force_disks_status = 401
            shares_c = smb_mount_manager.fetch_shares_from_backend_api(
                backend_url,
                username="user_1",
                password="UserSecret!9",
                auth_token="expired.jwt.30d",
            )
            self.assertEqual(shares_c, [])
            self.assertEqual(len(state.verify_calls), 1)
            self.assertEqual(len(state.disks_calls), 2)

            state.verify_calls.clear()
            state.disks_calls.clear()
            state.force_disks_status = 500
            shares_d = smb_mount_manager.fetch_shares_from_backend_api(
                backend_url,
                username="user_1",
                password="UserSecret!9",
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
                    username="user_1",
                    password="UserSecret!9",
                    auth_token="zima_tok",
                    base_url="http://127.0.0.1:80",
                    smb_source="zimaos",
                )
                self.assertEqual(z_shares, ["ZimaShareA", "ZimaShareB"])
                self.assertEqual(mock_zima.call_count, 1)

                b_shares = smb_mount_manager.get_remote_smb_shares(
                    host="127.0.0.1",
                    username="user_1",
                    password="UserSecret!9",
                    auth_token="",
                    base_url="http://127.0.0.1:80",
                    smb_source="backend",
                    backend_url=backend_url,
                )
                self.assertEqual(b_shares, ["Media", "Shared"])
                self.assertEqual(mock_zima.call_count, 1)

                cb = lambda tok, data: None
                with patch.object(
                    smb_mount_manager, "resolve_smb_host", return_value="127.0.0.1"
                ), patch.object(
                    smb_mount_manager, "get_remote_smb_shares", return_value=[]
                ) as mock_get_shares:
                    smb_mount_manager.mount_all_smb_shares(
                        host="127.0.0.1",
                        username="user_1",
                        password="UserSecret!9",
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


class TestCoreServiceSmbSourceAndD07(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None
        smb_mount_manager.clear_smb_share_cache()

        self._orig_backend_info = dict(core._cached_backend_info)
        self._orig_url_cache = dict(core._backend_url_cache)
        core._backend_url_cache.clear()
        core._cached_backend_info["timestamp"] = 0
        core._cached_backend_info["server_id"] = ""
        core._cached_backend_info["data"] = {"online": False, "version": "", "latestVersion": "", "url": ""}

        cfg = config_manager.get_default_config()
        cfg["servers"] = [
            {
                "id": "srv_1",
                "name": "HomeNAS",
                "zerotier_virtual_ip": "10.147.20.9",
                "easytier_virtual_ip": "10.126.126.2",
                "connections": [
                    {"id": "c_lan", "name": "LAN", "url": "http://192.168.55.50:80"},
                    {"id": "c_wan", "name": "WAN", "url": "https://nas.example.com"},
                ],
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

        self.core_srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), core.CoreApiHandler)
        self.core_port = self.core_srv.server_port
        self.core_thread = threading.Thread(target=self.core_srv.serve_forever, daemon=True)
        self.core_thread.start()

        self.log_handler = _CapturingLogHandler()
        logging.getLogger().addHandler(self.log_handler)

    def tearDown(self):
        logging.getLogger().removeHandler(self.log_handler)
        self.core_srv.shutdown()
        self.core_srv.server_close()
        if hasattr(core, "_ACTIVE_BACKEND_DEPLOYS"):
            core._ACTIVE_BACKEND_DEPLOYS.clear()
        core._cached_backend_info.clear()
        core._cached_backend_info.update(self._orig_backend_info)
        core._backend_url_cache.clear()
        core._backend_url_cache.update(self._orig_url_cache)
        smb_mount_manager.clear_smb_share_cache()
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()

    def _req(self, method, path, payload=None):
        url = f"http://127.0.0.1:{self.core_port}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {}
        if data is not None:
            headers = {"Content-Type": "application/json", "Content-Length": str(len(data))}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode("utf-8"))

    def test_04_post_smb_source_backend_switch_and_secret_isolation(self):
        state = _MockBackendApiState()
        bsrv, backend_url = _start_mock_backend_server(state)
        try:
            with patch.object(core, "_get_active_server_backend_url", return_value=backend_url), \
                 patch.object(core, "get_active_resolved_route", return_value=("http://192.168.55.50:80", "LAN")), \
                 patch.object(core, "get_cached_metrics_client", side_effect=AssertionError("ZimaOS metrics client must not be touched in backend mode")), \
                 patch.object(smb_mount_manager, "unmount_all_smb_shares", return_value=1), \
                 patch.object(smb_mount_manager, "purge_smb_sessions") as mock_purge, \
                 patch.object(smb_mount_manager, "mount_all_smb_shares", return_value=(True, "Mounted")) as mock_mount, \
                 patch.object(core.time, "sleep", return_value=None):
                status, res = self._req(
                    "POST",
                    "/api/smb/source",
                    {
                        "action": "set",
                        "source": "backend",
                        "username": "user_1",
                        "password": "UserSecret!9",
                    },
                )

            self.assertEqual(status, 200)
            self.assertIs(res.get("success"), True)
            self.assertEqual(res.get("source"), "backend")
            self.assertEqual(res.get("username"), "user_1")
            self.assertEqual(res.get("role"), "user")
            self.assertEqual(res.get("allowedDisks"), ["Media", "Shared"])
            self.assertIs(res.get("hasCredentials"), True)
            self.assertNotIn("password", res)
            self.assertNotIn("access_token", res)
            self.assertNotIn("UserSecret!9", json.dumps(res))
            self.assertNotIn("fresh.jwt.tok", json.dumps(res))

            # Verify strict sequence of Backend calls & mount pipeline
            self.assertEqual(len(state.verify_calls), 1)
            self.assertEqual(state.mode_calls[0]["body"], {"mode": "backend", "username": "user_1", "password": "UserSecret!9"})
            self.assertGreaterEqual(len(state.disks_calls), 1)
            mock_purge.assert_called_once()
            purged_hosts = mock_purge.call_args[0][0]
            self.assertIn("10.126.126.2", purged_hosts)
            self.assertIn("10.147.20.9", purged_hosts)
            self.assertIn("192.168.55.50", purged_hosts)
            mock_mount.assert_called_once()
            mkw = mock_mount.call_args.kwargs
            self.assertEqual(mkw.get("smb_source"), "backend")
            self.assertEqual(mkw.get("backend_url"), backend_url)
            self.assertEqual(mkw.get("username"), "user_1")
            self.assertEqual(mkw.get("password"), "UserSecret!9")

            # Verify DPAPI/encrypted config & ZimaOS credentials untouched
            cfg_after = config_manager.load_or_create_config()
            srv_after = cfg_after["servers"][0]
            self.assertEqual(srv_after["active_profile"], "Admin")
            zima_creds = config_manager.get_server_credentials(srv_after, "Admin")
            self.assertEqual(zima_creds, {"username": "zima_admin", "password": "ZimaAdminPass!9"})
            raw_auth = srv_after["backend_smb_auth"]
            self.assertTrue(raw_auth["password"].startswith(("dpapi:", "enc:")))
            self.assertTrue(raw_auth["access_token"].startswith(("dpapi:", "enc:")))

            all_logs = "\n".join(self.log_handler.messages)
            self.assertNotIn("UserSecret!9", all_logs)
            self.assertNotIn("fresh.jwt.tok", all_logs)
        finally:
            bsrv.shutdown()
            bsrv.server_close()

    def test_05_401_jwt_refresh_invalid_login_and_user_admin_roundtrip(self):
        state = _MockBackendApiState()
        bsrv, backend_url = _start_mock_backend_server(state)
        try:
            # Seed expired 30-day JWT with stored user credentials
            cfg = config_manager.load_or_create_config()
            config_manager.save_server_smb_source_config(
                cfg,
                "srv_1",
                "backend",
                username="user_1",
                password="UserSecret!9",
                role="user",
                allowed_disks=["Media", "Shared"],
                access_token="expired.jwt.30d",
            )

            # 1. GET /api/smb/source triggers silent 401 JWT refresh & updates encrypted access_token
            with patch.object(core, "_get_active_server_backend_url", return_value=backend_url):
                st_get, res_get = self._req("GET", "/api/smb/source")
            self.assertEqual(st_get, 200)
            self.assertIs(res_get.get("success"), True)
            self.assertIs(res_get.get("needsAuth"), False)
            self.assertEqual(len(state.verify_calls), 1)
            self.assertEqual(state.verify_calls[0]["username"], "user_1")
            refreshed_cfg = config_manager.get_server_smb_source_config(
                config_manager.load_or_create_config()["servers"][0]
            )
            self.assertEqual(refreshed_cfg["access_token"], "fresh.jwt.tok.1")

            # 2. rebind_storage_pipeline with expired token silently refreshes via on_token_refreshed without touching ZimaOS metrics
            config_manager.save_server_smb_source_config(
                config_manager.load_or_create_config(),
                "srv_1",
                "backend",
                access_token="expired.jwt.30d",
            )
            state.verify_calls.clear()
            with patch.object(core, "_get_active_server_backend_url", return_value=backend_url), \
                 patch.object(core, "get_active_resolved_route", return_value=("http://192.168.55.50:80", "LAN")), \
                 patch.object(core, "get_cached_metrics_client", side_effect=AssertionError("Must not call metrics client")), \
                 patch.object(smb_mount_manager, "unmount_all_smb_shares", return_value=0), \
                 patch.object(smb_mount_manager, "purge_smb_sessions"), \
                 patch.object(smb_mount_manager, "resolve_smb_host", return_value="127.0.0.1"), \
                 patch.object(smb_mount_manager, "mount_smb_share", return_value=(True, "ok")), \
                 patch.object(smb_mount_manager, "get_available_drive_letter", return_value="Z:"), \
                 patch.object(core.time, "sleep", return_value=None):
                core.rebind_storage_pipeline("startup_auto")

            self.assertEqual(len(state.verify_calls), 1)
            self.assertEqual(state.verify_calls[0]["username"], "user_1")
            after_rebind_cfg = config_manager.get_server_smb_source_config(
                config_manager.load_or_create_config()["servers"][0]
            )
            self.assertEqual(after_rebind_cfg["access_token"], "fresh.jwt.tok.2")

            # 3. User round-trip switch back to zimaos sends stored username & password to /api/v1/smb/mode
            state.mode_calls.clear()
            with patch.object(core, "_get_active_server_backend_url", return_value=backend_url), \
                 patch.object(core, "get_active_resolved_route", return_value=("http://192.168.55.50:80", "LAN")), \
                 patch.object(core, "get_cached_metrics_client", return_value=types.SimpleNamespace(token="zima_tok_1", authenticate=lambda: None)), \
                 patch.object(core, "sync_server_zerotier_ip"), \
                 patch.object(smb_mount_manager, "unmount_all_smb_shares", return_value=1), \
                 patch.object(smb_mount_manager, "purge_smb_sessions"), \
                 patch.object(smb_mount_manager, "mount_all_smb_shares", return_value=(True, "Mounted")) as mock_z_mount, \
                 patch.object(core.time, "sleep", return_value=None):
                st_z, res_z = self._req("POST", "/api/smb/source", {"action": "set", "source": "zimaos"})
            self.assertEqual(st_z, 200)
            self.assertIs(res_z.get("success"), True)
            self.assertEqual(res_z.get("source"), "zimaos")
            self.assertEqual(state.smb_mode, "zimaos")
            self.assertEqual(
                state.mode_calls[-1]["body"],
                {"mode": "zimaos", "username": "user_1", "password": "UserSecret!9"},
            )
            self.assertEqual(mock_z_mount.call_args.kwargs.get("smb_source"), "zimaos")
            self.assertEqual(mock_z_mount.call_args.kwargs.get("username"), "zima_admin")

            # 4. Admin round-trip zimaos -> backend -> zimaos
            with patch.object(core, "_get_active_server_backend_url", return_value=backend_url), \
                 patch.object(core, "get_active_resolved_route", return_value=("http://192.168.55.50:80", "LAN")), \
                 patch.object(core, "get_cached_metrics_client", return_value=types.SimpleNamespace(token="zima_tok_1", authenticate=lambda: None)), \
                 patch.object(core, "sync_server_zerotier_ip"), \
                 patch.object(smb_mount_manager, "unmount_all_smb_shares", return_value=1), \
                 patch.object(smb_mount_manager, "purge_smb_sessions"), \
                 patch.object(smb_mount_manager, "mount_all_smb_shares", return_value=(True, "Mounted")), \
                 patch.object(core.time, "sleep", return_value=None):
                st_ab, res_ab = self._req(
                    "POST",
                    "/api/smb/source",
                    {"action": "set", "source": "backend", "username": "admin_ops", "password": "AdminOps!99"},
                )
                self.assertEqual(st_ab, 200)
                self.assertEqual(res_ab.get("source"), "backend")
                self.assertEqual(res_ab.get("role"), "admin")
                st_az, res_az = self._req("POST", "/api/smb/source", {"action": "set", "source": "zimaos"})
                self.assertEqual(st_az, 200)
                self.assertEqual(res_az.get("source"), "zimaos")

            # 5. Invalid login rejected 401 without mutating smb_source or ZimaOS creds & secret masked
            with patch.object(core, "_get_active_server_backend_url", return_value=backend_url):
                st_bad, res_bad = self._req(
                    "POST",
                    "/api/smb/source",
                    {"action": "set", "source": "backend", "username": "user_1", "password": "WrongSecret!00"},
                )
            self.assertEqual(st_bad, 401)
            self.assertIs(res_bad.get("success"), False)
            self.assertIs(res_bad.get("needsAuth"), True)
            self.assertNotIn("WrongSecret!00", "\n".join(self.log_handler.messages))
            self.assertEqual(
                config_manager.get_server_smb_source_config(
                    config_manager.load_or_create_config()["servers"][0]
                )["source"],
                "zimaos",
            )

            # 6. Double 401 (expired token + verify 401) sets needsAuth=True without falling back to zima_admin
            config_manager.save_server_smb_source_config(
                config_manager.load_or_create_config(),
                "srv_1",
                "zimaos",
                username="user_1",
                password="UserSecret!9",
                access_token="expired.jwt.30d",
            )
            state.verify_calls.clear()
            state.force_verify_401 = True
            with patch.object(core, "_get_active_server_backend_url", return_value=backend_url):
                st_d401, res_d401 = self._req("POST", "/api/smb/source", {"action": "set", "source": "backend"})
            self.assertEqual(st_d401, 401)
            self.assertIs(res_d401.get("success"), False)
            self.assertIs(res_d401.get("needsAuth"), True)
            self.assertTrue(all(vc["username"] != "zima_admin" for vc in state.verify_calls))
            state.force_verify_401 = False

            # 7. Backend offline during switch-back to zimaos succeeds gracefully with warning
            config_manager.save_server_smb_source_config(
                config_manager.load_or_create_config(),
                "srv_1",
                "backend",
            )
            with patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:1"), \
                 patch.object(core, "get_active_resolved_route", return_value=("http://192.168.55.50:80", "LAN")), \
                 patch.object(core, "get_cached_metrics_client", return_value=None), \
                 patch.object(smb_mount_manager, "unmount_all_smb_shares", return_value=0), \
                 patch.object(smb_mount_manager, "purge_smb_sessions"), \
                 patch.object(smb_mount_manager, "mount_all_smb_shares", return_value=(False, "offline")), \
                 patch.object(core.time, "sleep", return_value=None):
                st_off, res_off = self._req("POST", "/api/smb/source", {"action": "set", "source": "zimaos"})
            self.assertEqual(st_off, 200)
            self.assertIs(res_off.get("success"), True)
            self.assertEqual(res_off.get("source"), "zimaos")
        finally:
            bsrv.shutdown()
            bsrv.server_close()

    def test_06_live_drives_backend_mode_route_norm_open_web_and_call_core_api(self):
        # 1. /api/open_backend_file_manager + /api/call_core_api routing
        with patch.object(core, "_get_active_server_backend_url", return_value="http://10.126.126.2:8080"), \
             patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.4.0"}, 200)), \
             patch.object(core, "spawn_app_window", return_value=(True, "ok")) as mock_spawn:
            st_open, res_open = self._req("POST", "/api/open_backend_file_manager", {})
            self.assertEqual(st_open, 200)
            self.assertIs(res_open.get("success"), True)
            self.assertEqual(res_open.get("url"), "http://10.126.126.2:8080/")
            mock_spawn.assert_called_with("http://10.126.126.2:8080/", "HomeNAS Backend Files")

            st_ca_open, res_ca_open = self._req(
                "POST", "/api/call_core_api", {"endpoint": "open_backend_file_manager"}
            )
            self.assertEqual(st_ca_open, 200)
            self.assertEqual(res_ca_open.get("url"), "http://10.126.126.2:8080/")

        with patch.object(core, "_get_active_server_backend_url", return_value=None):
            st_off, res_off = self._req("POST", "/api/open_backend_file_manager", {})
            self.assertEqual(st_off, 400)
            self.assertIs(res_off.get("success"), False)

        with patch.object(core, "_get_active_server_backend_url", return_value=""):
            st_ca_get, res_ca_get = self._req(
                "POST", "/api/call_core_api", {"endpoint": "smb/source", "action": "get"}
            )
            self.assertEqual(st_ca_get, 200)
            self.assertEqual(res_ca_get.get("source"), "zimaos")

        # 2. rebind_storage_pipeline normalizes WAN domain active_u to P2P/LAN port 8080
        config_manager.save_server_smb_source_config(
            config_manager.load_or_create_config(),
            "srv_1",
            "backend",
            username="user_1",
            password="UserSecret!9",
            role="user",
            allowed_disks=["Media", "Shared"],
            access_token="tok_valid",
        )
        with patch.object(core, "get_active_resolved_route", return_value=("https://nas.example.com", "WAN")), \
             patch.object(core, "_get_active_server_backend_url", return_value="https://nas.example.com"), \
             patch.object(smb_mount_manager, "resolve_smb_host", return_value="10.126.126.2"), \
             patch.object(smb_mount_manager, "unmount_all_smb_shares", return_value=0), \
             patch.object(smb_mount_manager, "purge_smb_sessions") as mock_purge, \
             patch.object(smb_mount_manager, "clear_smb_share_cache") as mock_clear, \
             patch.object(smb_mount_manager, "mount_all_smb_shares", return_value=(True, "ok")) as mock_mount, \
             patch.object(core.time, "sleep", return_value=None):
            core.rebind_storage_pipeline("switch_source_backend")
        mock_clear.assert_called_once()
        mock_purge.assert_called_once()
        self.assertEqual(mock_mount.call_args.kwargs.get("backend_url"), "http://10.126.126.2:8080")

        # 3. _scan_live_drives_now in backend mode shows allowed_disks instead of ZimaOS-only cached_parts
        with core._state_lock:
            core._cached_state["storage_partitions"] = [
                {"name": "ZimaPrivatePool", "raw_name": "ZimaPrivatePool", "total_bytes": 1000, "used_bytes": 100}
            ]
        with patch.object(smb_mount_manager, "get_available_drive_letters", return_value=["Z:", "Y:", "X:"]):
            drives = core._scan_live_drives_now()
        drive_names = [d["name"] for d in drives]
        self.assertEqual(drive_names, ["Media", "Shared"])
        self.assertNotIn("ZimaPrivatePool", drive_names)

    def test_07_d07_auto_chain_ssh_rebuild_and_v130_boundary(self):
        with tempfile.TemporaryDirectory() as pkg_tmp:
            zip_path = os.path.join(pkg_tmp, "MyServer-Backend-ZimaOS.zip")
            tar_path = os.path.join(pkg_tmp, "MyServer-Backend-ZimaOS.tar.gz")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.4.0"\n')
            with tarfile.open(tar_path, "w:gz") as tf:
                info = tarfile.TarInfo("app/config.py")
                data = b'SERVER_VERSION = "1.4.0"\n'
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))

            # Case A: rebuild_required=True + has_ssh_creds=True -> auto-chains SSH install_zimaos.sh
            ssh_rec_a = {"connect_calls": [], "sftp_puts": [], "exec_cmds": []}
            fake_paramiko_a = _build_fake_paramiko(ssh_rec_a)
            poll_seq_a = [
                (True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-new"}, 200),
                (True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-ssh"}, 200),
            ]
            with patch.dict(sys.modules, {"paramiko": fake_paramiko_a}), \
                 patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]), \
                 patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
                 patch.object(core, "_get_bundled_backend_version", return_value="1.4.0"), \
                 patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, tar_path)), \
                 patch("urllib.request.urlopen", return_value=_FakeHttpResponse({"status": "success", "boot_id": "boot-old", "rebuild_required": True})), \
                 patch.object(core, "_backend_http_request", side_effect=poll_seq_a), \
                 patch("time.sleep", return_value=None):
                res_a = core.handle_remote_backend_action({"action": "update", "serverId": "srv_1"})
            self.assertIs(res_a.get("success"), True)
            self.assertTrue(any("install_zimaos.sh" in c[0] for c in ssh_rec_a["exec_cmds"]))
            self.assertEqual(len(ssh_rec_a["sftp_puts"]), 1)

            # Case B: v1.3.0 -> v1.4.0 boundary with rebuild_required=False and has_ssh_creds=True -> auto-chains SSH
            ssh_rec_b = {"connect_calls": [], "sftp_puts": [], "exec_cmds": []}
            fake_paramiko_b = _build_fake_paramiko(ssh_rec_b)
            poll_seq_b = [
                (True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-new"}, 200),
                (True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-ssh"}, 200),
            ]
            with patch.dict(sys.modules, {"paramiko": fake_paramiko_b}), \
                 patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]), \
                 patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
                 patch.object(core, "_get_bundled_backend_version", return_value="1.4.0"), \
                 patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, tar_path)), \
                 patch("urllib.request.urlopen", return_value=_FakeHttpResponse({"status": "success", "old_version": "1.3.0", "new_version": "1.4.0", "boot_id": "boot-old", "rebuild_required": False})), \
                 patch.object(core, "_backend_http_request", side_effect=poll_seq_b), \
                 patch("time.sleep", return_value=None):
                res_b = core.handle_remote_backend_action({"action": "update", "serverId": "srv_1"})
            self.assertIs(res_b.get("success"), True)
            self.assertTrue(any("install_zimaos.sh" in c[0] for c in ssh_rec_b["exec_cmds"]))

            # Case C: v1.3.0 -> v1.4.0 boundary via pre_ota_cached_ver when old_version omitted and has_ssh_creds=True
            ssh_rec_c = {"connect_calls": [], "sftp_puts": [], "exec_cmds": []}
            fake_paramiko_c = _build_fake_paramiko(ssh_rec_c)
            core._set_backend_health_cache("srv_1", True, "1.3.0", "1.4.0", "http://127.0.0.1:8080")
            poll_seq_c = [
                (True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-new"}, 200),
                (True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-ssh"}, 200),
            ]
            with patch.dict(sys.modules, {"paramiko": fake_paramiko_c}), \
                 patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]), \
                 patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
                 patch.object(core, "_get_bundled_backend_version", return_value="1.4.0"), \
                 patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, tar_path)), \
                 patch("urllib.request.urlopen", return_value=_FakeHttpResponse({"status": "success", "boot_id": "boot-old", "rebuild_required": False})), \
                 patch.object(core, "_backend_http_request", side_effect=poll_seq_c), \
                 patch("time.sleep", return_value=None):
                res_c = core.handle_remote_backend_action({"action": "update", "serverId": "srv_1"})
            self.assertIs(res_c.get("success"), True)
            self.assertTrue(any("install_zimaos.sh" in c[0] for c in ssh_rec_c["exec_cmds"]))

            # Case D: v1.3.0 -> v1.4.0 boundary when has_ssh_creds=False -> returns rebuildRecommended=True without SSH
            cfg_no_ssh = config_manager.load_or_create_config()
            cfg_no_ssh["servers"][0]["credentials"] = {}
            config_manager.save_config(cfg_no_ssh)
            ssh_rec_d = {"connect_calls": [], "sftp_puts": [], "exec_cmds": []}
            fake_paramiko_d = _build_fake_paramiko(ssh_rec_d)
            with patch.dict(sys.modules, {"paramiko": fake_paramiko_d}), \
                 patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]), \
                 patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
                 patch.object(core, "_get_bundled_backend_version", return_value="1.4.0"), \
                 patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, tar_path)), \
                 patch("urllib.request.urlopen", return_value=_FakeHttpResponse({"status": "success", "old_version": "1.3.0", "boot_id": "boot-old", "rebuild_required": False})), \
                 patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-new"}, 200)), \
                 patch("time.sleep", return_value=None):
                res_d = core.handle_remote_backend_action({"action": "update", "serverId": "srv_1"})
            self.assertIs(res_d.get("success"), True)
            self.assertIs(res_d.get("rebuildRecommended"), True)
            self.assertEqual(len(ssh_rec_d["connect_calls"]), 0)

    def test_08_cr07_backend_mode_empty_shares_never_falls_back_to_net_view(self):
        smb_mount_manager.clear_smb_share_cache()
        with patch.object(smb_mount_manager, "fetch_shares_from_backend_api", return_value=[]) as mock_be, \
             patch.object(smb_mount_manager.subprocess, "run", side_effect=AssertionError("net.exe view must NOT run in backend mode")):
            shares_first = smb_mount_manager.get_remote_smb_shares(
                host="10.126.126.2",
                username="user_zero",
                password="secret",
                smb_source="backend",
                backend_url="http://10.126.126.2:8080",
            )
            self.assertEqual(shares_first, [])
            self.assertEqual(mock_be.call_count, 1)

            # Empty list should also be cached without calling net.exe view or re-querying API immediately
            shares_cached = smb_mount_manager.get_remote_smb_shares(
                host="10.126.126.2",
                username="user_zero",
                password="secret",
                smb_source="backend",
                backend_url="http://10.126.126.2:8080",
            )
            self.assertEqual(shares_cached, [])
            self.assertEqual(mock_be.call_count, 1)

        # Verify ZimaOS mode still falls back to net.exe view when API returns []
        smb_mount_manager.clear_smb_share_cache()
        fake_net_view = types.SimpleNamespace(
            returncode=0,
            stdout="Share name   Type\n----\nZimaShare    Disk\nThe command completed successfully.\n",
            stderr="",
        )
        with patch.object(smb_mount_manager, "fetch_shares_from_zimaos_api", return_value=[]), \
             patch.object(smb_mount_manager.subprocess, "run", return_value=fake_net_view) as mock_sub:
            z_shares = smb_mount_manager.get_remote_smb_shares(
                host="192.168.55.50",
                username="zima_admin",
                password="pw",
                auth_token="tok",
                base_url="http://192.168.55.50:80",
                smb_source="zimaos",
            )
            self.assertEqual(z_shares, ["ZimaShare"])
            self.assertGreaterEqual(mock_sub.call_count, 1)

    def test_09_wr01_401_refresh_preserves_admin_allowed_disks(self):
        for admin_role in ("admin", "root"):
            cfg = config_manager.load_or_create_config()
            config_manager.save_server_smb_source_config(
                cfg,
                "srv_1",
                "backend",
                username="admin_ops",
                password="AdminOps!99",
                role=admin_role,
                allowed_disks=["DATA", "Media"],
                access_token="expired.admin.jwt",
            )

            ok = core._persist_refreshed_backend_token(
                "srv_1",
                "fresh.admin.jwt",
                {"role": admin_role, "allowed_disks": []},
            )
            self.assertTrue(ok)

            refreshed = config_manager.get_server_smb_source_config(
                config_manager.load_or_create_config()["servers"][0]
            )
            self.assertEqual(refreshed["access_token"], "fresh.admin.jwt")
            self.assertEqual(refreshed["role"], admin_role)
            self.assertEqual(refreshed["allowed_disks"], ["DATA", "Media"])

        # Non-admin user empty allowed_disks still updates normally
        config_manager.save_server_smb_source_config(
            config_manager.load_or_create_config(),
            "srv_1",
            "backend",
            username="user_1",
            password="UserSecret!9",
            role="user",
            allowed_disks=["Media"],
            access_token="expired.user.jwt",
        )
        core._persist_refreshed_backend_token(
            "srv_1",
            "fresh.user.jwt",
            {"role": "user", "allowed_disks": []},
        )
        user_refreshed = config_manager.get_server_smb_source_config(
            config_manager.load_or_create_config()["servers"][0]
        )
        self.assertEqual(user_refreshed["allowed_disks"], [])

    def test_10_wr02_scan_live_drives_now_recognizes_easytier_virtual_ip(self):
        cfg = config_manager.load_or_create_config()
        cfg["servers"].append(
            {
                "id": "srv_2",
                "name": "OtherNAS",
                "easytier_virtual_ip": "10.126.126.99",
                "connections": [{"id": "c_other", "name": "LAN", "url": "http://192.168.88.99:80"}],
            }
        )
        config_manager.save_config(cfg)

        drive_map = {
            "Z:": r"\\10.126.126.2\Media",
            "Y:": r"\\10.126.126.99\OtherShare",
        }

        class _FakeKernel32:
            def GetDriveTypeW(self, path_w):
                drv = path_w.rstrip("\\")
                return 4 if drv in drive_map else 1

        class _FakeMpr:
            def WNetGetConnectionW(self, drv, buf, _size_ref):
                unc = drive_map.get(drv)
                if unc:
                    buf.value = unc
                    return 0
                return 1201

        fake_windll = types.SimpleNamespace(kernel32=_FakeKernel32(), mpr=_FakeMpr())
        with core._state_lock:
            core._cached_state["is_online"] = True
            core._cached_state["storage_partitions"] = [
                {"name": "Media", "raw_name": "Media", "total_bytes": 1000, "used_bytes": 250}
            ]
        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core.ctypes, "windll", fake_windll, create=True), \
             patch.object(core, "get_active_resolved_route", return_value=("https://nas.example.com", "WAN")), \
             patch.object(core.zerotier_manager, "is_zerotier_ip", return_value=False):
            drives = core._scan_live_drives_now()

        names = [d["name"] for d in drives]
        self.assertIn("Media", names)
        self.assertNotIn("OtherShare", names)

    def test_11_wr03_dpapi_fallback_logs_warning_without_secret_leak(self):
        secret_val = "UltraSecretDPAPI!99"
        with patch.object(config_manager.sys, "platform", "win32"), \
             patch.object(config_manager, "_dpapi_protect", side_effect=OSError("CryptProtectData failed")), \
             patch.object(config_manager, "_dpapi_unprotect", side_effect=OSError("CryptUnprotectData failed")):
            enc = config_manager.encrypt_credential(secret_val)
            self.assertTrue(enc.startswith("enc:"))
            dec_bad = config_manager.decrypt_credential("dpapi:ZmFrZQ==")
            self.assertEqual(dec_bad, "dpapi:ZmFrZQ==")

        all_logs = "\n".join(self.log_handler.messages)
        self.assertIn("DPAPI_FALLBACK", all_logs)
        self.assertNotIn(secret_val, all_logs)

    def test_12_wr05_open_backend_file_manager_503_and_wr08_strict_health(self):
        # WR-05: /api/open_backend_file_manager probes /health and returns 503 when unreachable or unhealthy
        for bad_probe in ((False, {}, 502), (True, {"status": "degraded"}, 200), (False, {"detail": "not found"}, 404)):
            with patch.object(core, "_get_active_server_backend_url", return_value="http://10.126.126.2:8080"), \
                 patch.object(core, "_backend_http_request", return_value=bad_probe), \
                 patch.object(core, "spawn_app_window") as mock_spawn:
                st, res = self._req("POST", "/api/open_backend_file_manager", {})
            self.assertEqual(st, 503)
            self.assertIs(res.get("success"), False)
            self.assertIn("Backend tidak dapat dijangkau", res.get("error", ""))
            mock_spawn.assert_not_called()

        # WR-08: _handle_smb_source_request treats 404/500/503 or non-ok /health strictly as backendOnline=False
        for bad_health in ((False, {"detail": "Not Found"}, 404), (False, {"error": "Internal"}, 500), (True, {"status": "error"}, 200)):
            with patch.object(core, "_get_active_server_backend_url", return_value="http://10.126.126.2:8080"), \
                 patch.object(core, "_backend_http_request", return_value=bad_health):
                st_g, res_g = self._req("GET", "/api/smb/source")
            self.assertEqual(st_g, 200)
            self.assertIs(res_g.get("backendOnline"), False)

    def test_13_wr07_post_ota_ssh_failure_sets_ota_applied_and_uses_dynamic_candidates(self):
        with tempfile.TemporaryDirectory() as pkg_tmp:
            zip_path = os.path.join(pkg_tmp, "MyServer-Backend-ZimaOS.zip")
            tar_path = os.path.join(pkg_tmp, "MyServer-Backend-ZimaOS.tar.gz")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.4.0"\n')
            with tarfile.open(tar_path, "w:gz") as tf:
                info = tarfile.TarInfo("app/config.py")
                data = b'SERVER_VERSION = "1.4.0"\n'
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))

            # Part A: HTTP OTA succeeds, auto-chains SSH rebuild, SSH auth fails -> otaApplied & rebuildPendingSshAuth
            ssh_rec = {"connect_calls": [], "sftp_puts": [], "exec_cmds": []}
            fake_paramiko = _build_fake_paramiko(ssh_rec)

            def _raise_ssh_auth(*_a, **_kw):
                raise fake_paramiko.AuthenticationException("SSH auth failed")

            fake_paramiko.SSHClient.connect = _raise_ssh_auth

            with patch.dict(sys.modules, {"paramiko": fake_paramiko}), \
                 patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]), \
                 patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
                 patch.object(core, "_get_bundled_backend_version", return_value="1.4.0"), \
                 patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, tar_path)), \
                 patch("urllib.request.urlopen", return_value=_FakeHttpResponse({"status": "success", "boot_id": "boot-old", "rebuild_required": True})), \
                 patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-new"}, 200)), \
                 patch("time.sleep", return_value=None):
                res_fail = core.handle_remote_backend_action({"action": "update", "serverId": "srv_1"})

            self.assertIs(res_fail.get("success"), False)
            self.assertIs(res_fail.get("authFailed"), True)
            self.assertIs(res_fail.get("otaApplied"), True)
            self.assertIs(res_fail.get("rebuildPendingSshAuth"), True)
            self.assertIn("HTTP OTA sudah diterapkan", res_fail.get("message", ""))
            self.assertIn("HTTP OTA sudah diterapkan", res_fail.get("error", ""))

            # Part B: After SSH install_zimaos.sh, health check uses _get_backend_url_candidates (e.g. EasyTier IP)
            ssh_rec_ok = {"connect_calls": [], "sftp_puts": [], "exec_cmds": []}
            fake_paramiko_ok = _build_fake_paramiko(ssh_rec_ok)
            probed_urls = []

            def _health_side_effect(url, **_kwargs):
                probed_urls.append(url)
                if url.startswith("http://10.126.126.2:8080"):
                    return True, {"status": "ok", "version": "1.4.0"}, 200
                return False, {}, 0

            with patch.dict(sys.modules, {"paramiko": fake_paramiko_ok}), \
                 patch.object(core, "_get_backend_url_candidates", return_value=["http://10.126.126.2:8080", "http://192.168.55.50:8080"]), \
                 patch.object(core, "_get_bundled_backend_version", return_value="1.4.0"), \
                 patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, tar_path)), \
                 patch.object(core, "_backend_http_request", side_effect=_health_side_effect), \
                 patch("time.sleep", return_value=None):
                res_ssh_ok = core.handle_remote_backend_action(
                    {"action": "install", "source": "bundle", "serverId": "srv_1", "sshHost": "nas.example.com"}
                )

            self.assertIs(res_ssh_ok.get("success"), True)
            self.assertEqual(res_ssh_ok["backend"]["url"], "http://10.126.126.2:8080")
            self.assertIn("http://nas.example.com:8080/health", probed_urls)
            self.assertIn("http://10.126.126.2:8080/health", probed_urls)

    def test_14_cr03_desktop_ota_sends_bearer_jwt_form_creds_and_zimaos_token(self):
        with tempfile.TemporaryDirectory() as pkg_tmp:
            zip_path = os.path.join(pkg_tmp, "MyServer-Backend-ZimaOS.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("app/config.py", 'SERVER_VERSION = "1.4.0"\n')

            # Case A: Admin JWT in backend_smb_auth + ZimaMetricsClient zimaos_token
            config_manager.save_server_smb_source_config(
                config_manager.load_or_create_config(),
                "srv_1",
                "backend",
                username="admin_ops",
                password="AdminOps!99",
                role="admin",
                allowed_disks=["DATA"],
                access_token="admin.jwt.token.A",
            )
            captured_reqs = []

            def _fake_urlopen(req, timeout=20):
                captured_reqs.append(
                    {
                        "url": req.full_url,
                        "headers": {k.lower(): v for k, v in req.header_items()},
                        "data": req.data,
                    }
                )
                if req.full_url.endswith("/api/v1/auth/verify"):
                    return _FakeHttpResponse({"access_token": "refreshed.admin.jwt", "role": "admin"})
                return _FakeHttpResponse({"status": "success", "boot_id": "boot-new"})

            fake_mc = types.SimpleNamespace(token="zima_live_tok_99")
            with patch.object(core, "_active_metrics_client", fake_mc), \
                 patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]), \
                 patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
                 patch.object(core, "_get_bundled_backend_version", return_value="1.4.0"), \
                 patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, None)), \
                 patch("urllib.request.urlopen", side_effect=_fake_urlopen), \
                 patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-2"}, 200)), \
                 patch("time.sleep", return_value=None):
                res_a = core.handle_remote_backend_action({"action": "update", "serverId": "srv_1"})

            self.assertIs(res_a.get("success"), True)
            self.assertEqual(len(captured_reqs), 1)
            req_a = captured_reqs[0]
            self.assertTrue(req_a["url"].endswith("/api/v1/system/update"))
            self.assertEqual(req_a["headers"].get("authorization"), "Bearer admin.jwt.token.A")
            self.assertIn(b'name="username"\r\n\r\nadmin_ops\r\n', req_a["data"])
            self.assertIn(b'name="password"\r\n\r\nAdminOps!99\r\n', req_a["data"])
            self.assertIn(b'name="zimaos_token"\r\n\r\nzima_live_tok_99\r\n', req_a["data"])

            # Case B: Non-admin user token in backend_smb_auth must NOT be sent as OTA Bearer; uses ZimaOS creds & token
            config_manager.save_server_smb_source_config(
                config_manager.load_or_create_config(),
                "srv_1",
                "backend",
                username="user_1",
                password="UserSecret!9",
                role="user",
                allowed_disks=["Media"],
                access_token="user.jwt.must.not.send",
            )
            captured_reqs.clear()

            def _fake_urlopen_user(req, timeout=20):
                captured_reqs.append(
                    {
                        "url": req.full_url,
                        "headers": {k.lower(): v for k, v in req.header_items()},
                        "data": req.data,
                    }
                )
                if req.full_url.endswith("/api/v1/auth/verify"):
                    return _FakeHttpResponse({"access_token": "zima.admin.jwt.B", "role": "admin"})
                return _FakeHttpResponse({"status": "success", "boot_id": "boot-new"})

            with patch.object(core, "_active_metrics_client", fake_mc), \
                 patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]), \
                 patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
                 patch.object(core, "_get_bundled_backend_version", return_value="1.4.0"), \
                 patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, None)), \
                 patch("urllib.request.urlopen", side_effect=_fake_urlopen_user), \
                 patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-3"}, 200)), \
                 patch("time.sleep", return_value=None):
                res_b = core.handle_remote_backend_action({"action": "update", "serverId": "srv_1"})

            self.assertIs(res_b.get("success"), True)
            upd_req = [r for r in captured_reqs if r["url"].endswith("/api/v1/system/update")][0]
            self.assertNotEqual(upd_req["headers"].get("authorization"), "Bearer user.jwt.must.not.send")
            self.assertEqual(upd_req["headers"].get("authorization"), "Bearer zima.admin.jwt.B")
            self.assertIn(b'name="username"\r\n\r\nzima_admin\r\n', upd_req["data"])
            self.assertIn(b'name="password"\r\n\r\nZimaAdminPass!9\r\n', upd_req["data"])
            self.assertIn(b'name="zimaos_token"\r\n\r\nzima_live_tok_99\r\n', upd_req["data"])

            # Case C: Expired admin JWT triggers 401 -> refreshes via /api/v1/auth/verify and retries upload
            config_manager.save_server_smb_source_config(
                config_manager.load_or_create_config(),
                "srv_1",
                "backend",
                username="admin_ops",
                password="AdminOps!99",
                role="admin",
                allowed_disks=["DATA"],
                access_token="expired.admin.jwt",
            )
            captured_reqs.clear()

            def _fake_urlopen_401(req, timeout=20):
                hdrs = {k.lower(): v for k, v in req.header_items()}
                captured_reqs.append({"url": req.full_url, "headers": hdrs})
                if req.full_url.endswith("/api/v1/auth/verify"):
                    return _FakeHttpResponse({"access_token": "refreshed.admin.jwt.C", "role": "admin"})
                if hdrs.get("authorization") == "Bearer expired.admin.jwt":
                    raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
                return _FakeHttpResponse({"status": "success", "boot_id": "boot-new"})

            with patch.object(core, "_active_metrics_client", fake_mc), \
                 patch.object(core, "_get_backend_url_candidates", return_value=["http://127.0.0.1:8080"]), \
                 patch.object(core, "_get_active_server_backend_url", return_value="http://127.0.0.1:8080"), \
                 patch.object(core, "_get_bundled_backend_version", return_value="1.4.0"), \
                 patch.object(core, "_get_bundled_backend_packages", return_value=(zip_path, None)), \
                 patch("urllib.request.urlopen", side_effect=_fake_urlopen_401), \
                 patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.4.0", "boot_id": "boot-4"}, 200)), \
                 patch("time.sleep", return_value=None):
                res_c = core.handle_remote_backend_action({"action": "update", "serverId": "srv_1"})

            self.assertIs(res_c.get("success"), True)
            self.assertEqual(
                [r["headers"].get("authorization") for r in captured_reqs if r["url"].endswith("/api/v1/system/update")],
                ["Bearer expired.admin.jwt", "Bearer refreshed.admin.jwt.C"],
            )

    def test_10_auto_refresh_allowed_disks_on_get_smb_source_without_zimaos_toggle(self):
        state = _MockBackendApiState()
        state.smb_mode = "backend"
        state.active_tokens["tok_live_u1"] = "user_1"
        bsrv, backend_url = _start_mock_backend_server(state)
        try:
            cfg = config_manager.load_or_create_config()
            config_manager.save_server_smb_source_config(
                cfg,
                "srv_1",
                "backend",
                username="user_1",
                password="UserSecret!9",
                role="user",
                allowed_disks=["Media", "Shared"],
                access_token="tok_live_u1",
            )

            # Simulate Admin changing user_1's allowed_disks on Backend from ["Media", "Shared"] to ["Media"]
            state.valid_users["user_1"]["allowed_disks"] = ["Media"]

            with patch.object(core, "_get_active_server_backend_url", return_value=backend_url), \
                 patch.object(core, "rebind_storage_pipeline", return_value=[]) as mock_rebind, \
                 patch.object(smb_mount_manager, "get_available_drive_letters", return_value=["Z:", "Y:"]):
                st_get, res_get = self._req("GET", "/api/smb/source")

            self.assertEqual(st_get, 200)
            self.assertIs(res_get.get("success"), True)
            self.assertEqual(res_get.get("allowedDisks"), ["Media"])
            mock_rebind.assert_called_once_with("backend_acl_changed")
            self.assertEqual([d["name"] for d in res_get.get("drives", [])], ["Media"])

            updated_cfg = config_manager.get_server_smb_source_config(
                config_manager.load_or_create_config()["servers"][0]
            )
            self.assertEqual(updated_cfg["allowed_disks"], ["Media"])

            # Subsequent poll with unchanged allowed_disks must NOT trigger rebind again
            with patch.object(core, "_get_active_server_backend_url", return_value=backend_url), \
                 patch.object(core, "rebind_storage_pipeline", return_value=[]) as mock_rebind_2:
                st_get_2, res_get_2 = self._req("GET", "/api/smb/source")
            self.assertEqual(st_get_2, 200)
            self.assertEqual(res_get_2.get("allowedDisks"), ["Media"])
            mock_rebind_2.assert_not_called()
        finally:
            bsrv.shutdown()
            bsrv.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

import ctypes
import http.client
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
        winreg_stub.KEY_ALL_ACCESS = 0xF003F
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


class TestPhase12ShareCoreProxy(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None
        smb_mount_manager.clear_smb_share_cache()
        with smb_mount_manager._alias_1219_lock:
            smb_mount_manager._cached_1219_alias.clear()
        with smb_mount_manager._smb_host_cache_lock:
            smb_mount_manager._cached_resolved_smb_host.update(
                {"key": None, "target": "", "resolved": "", "ts": 0.0}
            )
        core._backend_url_cache.clear()
        with core._BACKEND_JWT_CACHE_LOCK:
            core._BACKEND_JWT_CACHE.clear()

        cfg = config_manager.get_default_config()
        cfg["servers"] = [
            {
                "id": "srv_1",
                "name": "HomeNAS",
                "active_connection": "c1",
                "connections": [{"id": "c1", "url": "http://192.0.2.10:8080", "label": "LAN"}],
                "zerotier_virtual_ip": "192.0.2.20",
                "easytier_virtual_ip": "192.0.2.30",
                "smb_source": "zimaos",
                "credentials": {
                    "Admin": {
                        "username": "alice",
                        "password": config_manager.encrypt_credential("AliceSecret!9"),
                    }
                },
                "profiles": ["Admin"],
                "active_profile": "Admin",
            },
            {
                "id": "srv_backend",
                "name": "BackendNAS",
                "active_connection": "c1",
                "connections": [{"id": "c1", "url": "http://192.0.2.50:8085", "label": "LAN"}],
                "smb_source": "backend",
                "backend_smb_auth": {
                    "username": "bob",
                    "password": config_manager.encrypt_credential("BobBackend!7"),
                },
                "credentials": {
                    "Admin": {
                        "username": "stale_zima_user",
                        "password": config_manager.encrypt_credential("StaleZima!9"),
                    }
                },
                "profiles": ["Admin"],
                "active_profile": "Admin",
            },
        ]
        cfg["active_server_id"] = "srv_1"
        config_manager.save_config(cfg)

        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), core.CoreApiHandler
        )
        self.port = self.server.server_port
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        with core._BACKEND_JWT_CACHE_LOCK:
            core._BACKEND_JWT_CACHE.clear()
        with smb_mount_manager._alias_1219_lock:
            smb_mount_manager._cached_1219_alias.clear()
        core._backend_url_cache.clear()
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()

    def _raw_http(self, method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            req_headers = dict(headers or {})
            body = None
            if payload is not None:
                body = json.dumps(payload).encode("utf-8")
                req_headers.setdefault("Content-Type", "application/json")
                req_headers["Content-Length"] = str(len(body))
            conn.request(method, path, body=body, headers=req_headers)
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8", errors="replace")
            resp_headers = {k.lower(): v for k, v in resp.getheaders()}
            try:
                parsed = json.loads(raw) if raw else None
            except Exception:
                parsed = {"_raw": raw}
            return resp.status, resp_headers, parsed
        finally:
            conn.close()

    def test_auth_token_required_on_all_five_account_share_routes(self):
        """SECH-01: Missing or invalid X-MyServer-Core-Token returns 401 fail-closed on all /api/shares/accounts/*."""
        routes = [
            ("/api/shares/accounts/candidates", {"server_id": "srv_1"}),
            ("/api/shares/accounts/list", {"server_id": "srv_1", "target_path": "Disk1/Docs"}),
            ("/api/shares/accounts/grant", {"server_id": "srv_1", "target_path": "Disk1/Docs", "grantee_username": "bob", "role": "editor"}),
            ("/api/shares/accounts/update", {"server_id": "srv_1", "grant_id": 1, "role": "viewer"}),
            ("/api/shares/accounts/revoke", {"server_id": "srv_1", "grant_id": 1}),
        ]
        for ep, payload in routes:
            st_no, _, body_no = self._raw_http("POST", ep, payload=payload)
            self.assertEqual(st_no, 401, f"Missing token on {ep} must return 401")
            self.assertIs(body_no.get("success"), False)

            st_bad, _, body_bad = self._raw_http(
                "POST", ep, payload=payload, headers={"X-MyServer-Core-Token": "bad-token"}
            )
            self.assertEqual(st_bad, 401, f"Bad token on {ep} must return 401")
            self.assertIs(body_bad.get("success"), False)

    def test_share_create_validates_role_max_upload_mb_and_strips_public_base_url(self):
        """/api/shares/create validates role (viewer/editor), max_upload_mb (1..102400), and strips public_base_url."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}
        sent_bodies = []

        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_alice", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/shares") and method == "POST":
                sent_bodies.append(dict(json_body or {}))
                return True, {"success": True, "share": {"token": "t_ok", "share_url": "/s/t_ok"}}, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_fake_backend), \
             patch.object(core, "_write_windows_clipboard", return_value=True):
            # Valid editor + max_upload_mb=100 + boundary 1 and 102400
            for role_in, max_in, exp_role, exp_max in (
                ("editor", 100, "editor", 100),
                (None, 1, "viewer", 1),
                ("", 102400, "viewer", 102400),
                ("viewer", None, "viewer", None),
            ):
                st, _, body = self._raw_http(
                    "POST",
                    "/api/shares/create",
                    payload={
                        "path": "Disk1/Shared",
                        "server_id": "srv_1",
                        "role": role_in,
                        "max_upload_mb": max_in,
                        "public_base_url": "https://evil.example.com",
                        "copy_to_clipboard": False,
                    },
                    headers=auth_hdr,
                )
                self.assertEqual(st, 200, f"Expected 200 for role={role_in}, max={max_in}, got {body}")
                self.assertIs(body["success"], True)
                self.assertEqual(sent_bodies[-1]["role"], exp_role)
                self.assertEqual(sent_bodies[-1]["max_upload_mb"], exp_max)
                self.assertNotIn("public_base_url", sent_bodies[-1])

        # Reject invalid roles (including administrator) and invalid max_upload_mb without hitting backend
        with patch.object(core, "_backend_http_request", side_effect=AssertionError("Must not call Backend on invalid payload")):
            for bad_role in ("administrator", "admin", "owner", 123, True):
                st, _, body = self._raw_http(
                    "POST",
                    "/api/shares/create",
                    payload={"path": "Disk1/Shared", "server_id": "srv_1", "role": bad_role},
                    headers=auth_hdr,
                )
                self.assertEqual(st, 400)
                self.assertEqual(body.get("code"), "INVALID_ROLE")

            for bad_max in (0, -5, 102401, True, False, 1.5, "abc"):
                st, _, body = self._raw_http(
                    "POST",
                    "/api/shares/create",
                    payload={"path": "Disk1/Shared", "server_id": "srv_1", "role": "editor", "max_upload_mb": bad_max},
                    headers=auth_hdr,
                )
                self.assertEqual(st, 400, f"Expected 400 for max_upload_mb={bad_max!r}")
                self.assertEqual(body.get("code"), "INVALID_MAX_UPLOAD_MB")

    def test_quick_share_locked_to_viewer_even_if_caller_injects_editor(self):
        """/api/shares/quick always sends role='viewer' and ignores any client role/max_upload_mb."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}
        sent_bodies = []

        target = {
            "canonical_rel": "Disk1/Docs",
            "basename": "Docs",
            "is_dir": True,
            "server_id": "srv_1",
            "server_name": "HomeNAS",
            "disk_name": "Disk1",
            "share_name": "Disk1",
            "is_admin": True,
            "backend_url": "http://192.0.2.10:8080",
            "smb_source": "zimaos",
        }

        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_alice", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/shares") and method == "POST":
                sent_bodies.append(dict(json_body or {}))
                return True, {"share": {"token": "q1", "share_url": "/s/q1"}}, 200
            return False, {}, 404

        with patch.object(core, "_resolve_smb_share_target", return_value=(True, target)), \
             patch.object(core, "_backend_http_request", side_effect=_fake_backend), \
             patch.object(core, "_write_windows_clipboard", return_value=True), \
             patch.object(core, "_show_windows_toast", return_value=True):
            st, _, body = self._raw_http(
                "POST",
                "/api/shares/quick",
                payload={"path": r"Z:\Docs", "role": "editor", "max_upload_mb": 500},
                headers=auth_hdr,
            )
        self.assertEqual(st, 200)
        self.assertTrue(body.get("success"))
        self.assertEqual(len(sent_bodies), 1)
        self.assertEqual(sent_bodies[0], {
            "path": "Disk1/Docs",
            "expires_in_hours": None,
            "password": None,
            "role": "viewer",
        })

    def test_account_share_routes_proxy_and_validate_inputs(self):
        """/api/shares/accounts/* proxies candidates, list, grant, update, revoke and rejects bad grant_id / FOREIGN_NAS."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}
        calls = []

        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            calls.append((method, url, json_body))
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_alice", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/share-accounts") and method == "GET":
                return True, {"accounts": [{"id": 2, "username": "bob"}]}, 200
            if "/api/v1/storage/account-shares?target_path=" in url and method == "GET":
                return True, {"shares": [{"id": 10, "grantee_username": "bob", "role": "editor"}], "caller_role": "owner"}, 200
            if url.endswith("/api/v1/storage/account-shares") and method == "POST":
                return True, {"share": {"id": 11, "grantee_username": json_body["grantee_username"], "role": json_body["role"]}}, 201
            if url.endswith("/api/v1/storage/account-shares/11") and method == "PATCH":
                return True, {"share": {"id": 11, "grantee_username": "bob", "role": json_body["role"]}}, 200
            if url.endswith("/api/v1/storage/account-shares/11") and method == "DELETE":
                return True, {"success": True}, 200
            return False, {"detail": "Not found"}, 404

        with patch.object(core, "_backend_http_request", side_effect=_fake_backend):
            st1, _, b1 = self._raw_http("POST", "/api/shares/accounts/candidates", payload={"server_id": "srv_1"}, headers=auth_hdr)
            self.assertEqual(st1, 200)
            self.assertEqual(b1["accounts"], [{"id": 2, "username": "bob"}])

            st2, _, b2 = self._raw_http("POST", "/api/shares/accounts/list", payload={"server_id": "srv_1", "target_path": "Disk1/Project A"}, headers=auth_hdr)
            self.assertEqual(st2, 200)
            self.assertEqual(b2["caller_role"], "owner")
            self.assertEqual(len(b2["shares"]), 1)

            st3, _, b3 = self._raw_http(
                "POST",
                "/api/shares/accounts/grant",
                payload={"server_id": "srv_1", "target_path": "Disk1/Project A", "grantee_username": "bob", "role": "administrator"},
                headers=auth_hdr,
            )
            self.assertEqual(st3, 200)
            self.assertEqual(b3["share"]["role"], "administrator")

            st4, _, b4 = self._raw_http(
                "POST",
                "/api/shares/accounts/update",
                payload={"server_id": "srv_1", "grant_id": 11, "role": "viewer"},
                headers=auth_hdr,
            )
            self.assertEqual(st4, 200)
            self.assertEqual(b4["share"]["role"], "viewer")

            st5, _, b5 = self._raw_http(
                "POST",
                "/api/shares/accounts/revoke",
                payload={"server_id": "srv_1", "grant_id": 11},
                headers=auth_hdr,
            )
            self.assertEqual(st5, 200)
            self.assertEqual(b5["grant_id"], 11)

        # Validation failures must never hit Backend
        with patch.object(core, "_backend_http_request", side_effect=AssertionError("Must not call Backend on validation error")):
            for bad_gid in ("../1", True, 0, -3, 1.5, "abc", None):
                st_u, _, bu = self._raw_http(
                    "POST", "/api/shares/accounts/update", payload={"server_id": "srv_1", "grant_id": bad_gid, "role": "viewer"}, headers=auth_hdr
                )
                self.assertEqual(st_u, 400)
                self.assertEqual(bu.get("code"), "INVALID_GRANT_ID")

                st_r, _, br = self._raw_http(
                    "POST", "/api/shares/accounts/revoke", payload={"server_id": "srv_1", "grant_id": bad_gid}, headers=auth_hdr
                )
                self.assertEqual(st_r, 400)
                self.assertEqual(br.get("code"), "INVALID_GRANT_ID")

            for ep, pl in (
                ("/api/shares/accounts/candidates", {"server_id": "unknown_srv"}),
                ("/api/shares/accounts/list", {"server_id": "unknown_srv", "target_path": "Disk1/A"}),
                ("/api/shares/accounts/grant", {"server_id": "unknown_srv", "target_path": "Disk1/A", "grantee_username": "bob", "role": "viewer"}),
                ("/api/shares/accounts/update", {"server_id": "unknown_srv", "grant_id": 1, "role": "viewer"}),
                ("/api/shares/accounts/revoke", {"server_id": "unknown_srv", "grant_id": 1}),
            ):
                st_f, _, bf = self._raw_http("POST", ep, payload=pl, headers=auth_hdr)
                self.assertEqual(st_f, 400)
                self.assertEqual(bf.get("code"), "FOREIGN_NAS")

    def test_account_share_sech03_isolation_and_error_mapping(self):
        """SECH-03: smb_source=='backend' uses backend_smb_auth only (never ZimaOS creds), and maps 403/404/401/502."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}
        auth_usernames = []

        def _fake_backend_isolation(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/login") or url.endswith("/api/v1/auth/verify"):
                auth_usernames.append((url, (json_body or {}).get("username")))
                return True, {"access_token": "tok_bob", "role": "user"}, 200
            if url.endswith("/api/v1/storage/share-accounts"):
                return True, {"accounts": [{"id": 1, "username": "alice"}]}, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_fake_backend_isolation):
            st, _, body = self._raw_http(
                "POST", "/api/shares/accounts/candidates", payload={"server_id": "srv_backend"}, headers=auth_hdr
            )
        self.assertEqual(st, 200)
        self.assertEqual(body["accounts"], [{"id": 1, "username": "alice"}])
        self.assertTrue(any(u == "bob" for _, u in auth_usernames))
        self.assertFalse(any(u == "stale_zima_user" for _, u in auth_usernames))

        # Backend HTTP error mapping: 403, 404, 401, 500->502
        for backend_st, exp_st, exp_code in (
            (403, 403, "FORBIDDEN_PATH"),
            (404, 404, "NOT_FOUND"),
            (401, 401, "UNAUTHENTICATED_SESSION"),
            (500, 502, "BACKEND_OFFLINE"),
            (0, 502, "BACKEND_OFFLINE"),
        ):
            def _err_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1, _st=backend_st):
                if url.endswith("/api/v1/auth/verify"):
                    return True, {"access_token": "tok_alice", "role": "admin"}, 200
                return False, {"detail": "backend error"}, _st

            with patch.object(core, "_backend_http_request", side_effect=_err_backend):
                st_e, _, body_e = self._raw_http(
                    "POST",
                    "/api/shares/accounts/list",
                    payload={"server_id": "srv_1", "target_path": "Disk1/Docs"},
                    headers=auth_hdr,
                )
            self.assertEqual(st_e, exp_st)
            self.assertEqual(body_e.get("code"), exp_code)


if __name__ == "__main__":
    unittest.main()

import ctypes
import http.client
import http.server
import io
import json
import os
import re
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch


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


class TestPhase10SecurityHardening(unittest.TestCase):
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
                "active_connection": "c1",
                "connections": [{"id": "c1", "url": "http://127.0.0.1:80", "label": "LAN"}],
                "credentials": {
                    "Admin": {
                        "username": "admin_ops",
                        "password": config_manager.encrypt_credential("AdminSecret!9"),
                    }
                },
                "profiles": ["Admin"],
                "active_profile": "Admin",
            }
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

    def test_01_core_token_auth_enforced_with_ping_exempt(self):
        """SECH-01: GET /api/ping is exempt; all other GET/POST routes require X-MyServer-Core-Token or Bearer token."""
        # 1. GET /api/ping succeeds without token
        st_ping, _, body_ping = self._raw_http("GET", "/api/ping")
        self.assertEqual(st_ping, 200)
        self.assertEqual(body_ping.get("status"), "ok")

        # 2. Missing or wrong token returns 401 on GET and POST
        for method, path, payload in (
            ("GET", "/api/get_log_directory", None),
            ("GET", "/api/state", None),
            ("POST", "/api/load_settings", {}),
            ("POST", "/api/quit_app", {}),
        ):
            st_no, _, body_no = self._raw_http(method, path, payload=payload)
            self.assertEqual(st_no, 401, f"{method} {path} should fail closed without token")
            self.assertIs(body_no.get("success"), False)

            st_bad, _, body_bad = self._raw_http(
                method,
                path,
                payload=payload,
                headers={"X-MyServer-Core-Token": "invalid-wrong-token"},
            )
            self.assertEqual(st_bad, 401, f"{method} {path} should reject wrong token")
            self.assertIs(body_bad.get("success"), False)

        # 3. Valid X-MyServer-Core-Token succeeds
        token = core.get_core_auth_token()
        self.assertTrue(len(token) >= 24)
        auth_hdr = {"X-MyServer-Core-Token": token}

        st_log, _, _ = self._raw_http("GET", "/api/get_log_directory", headers=auth_hdr)
        self.assertEqual(st_log, 200)

        st_state, _, _ = self._raw_http("GET", "/api/state", headers=auth_hdr)
        self.assertEqual(st_state, 200)

        st_load, _, body_load = self._raw_http("POST", "/api/load_settings", payload={}, headers=auth_hdr)
        self.assertEqual(st_load, 200)
        self.assertIsInstance(body_load, dict)

        with patch.object(core, "shutdown_background_daemons") as mock_sd, \
             patch.object(core.os, "_exit") as mock_exit:
            st_quit, _, body_quit = self._raw_http("POST", "/api/quit_app", payload={}, headers=auth_hdr)
            # Wait briefly for _delayed_exit thread so mocks remain active during its execution
            for _ in range(25):
                if mock_exit.called:
                    break
                threading.Event().wait(0.02)
        self.assertEqual(st_quit, 200)
        self.assertIs(body_quit.get("success"), True)
        mock_sd.assert_called()
        mock_exit.assert_called_once_with(0)

        # 4. Valid Authorization: Bearer <token> also succeeds
        bearer_hdr = {"Authorization": f"Bearer {token}"}
        st_bearer_get, _, _ = self._raw_http("GET", "/api/get_log_directory", headers=bearer_hdr)
        self.assertEqual(st_bearer_get, 200)
        st_bearer_post, _, _ = self._raw_http("POST", "/api/load_settings", payload={}, headers=bearer_hdr)
        self.assertEqual(st_bearer_post, 200)

        # 5. _init_core_auth_token honors MYSERVER_CORE_TOKEN env var and falls back to CSPRNG
        with patch.dict(os.environ, {"MYSERVER_CORE_TOKEN": "env-test-token-123"}, clear=False):
            self.assertEqual(core._init_core_auth_token(), "env-test-token-123")
        with patch.dict(os.environ, {"MYSERVER_CORE_TOKEN": ""}, clear=False):
            generated = core._init_core_auth_token()
            self.assertTrue(len(generated) >= 32)
            self.assertNotEqual(generated, "env-test-token-123")

    def test_02_strict_tauri_cors_and_options_preflight(self):
        """SECH-01: Allow only Tauri WebView origins (and explicit MYSERVER_DEV_CORS=1); reject untrusted origins."""
        token = core.get_core_auth_token()

        for trusted_origin in ("http://tauri.localhost", "https://tauri.localhost", "tauri://localhost"):
            st_opt, hdrs_opt, _ = self._raw_http(
                "OPTIONS", "/api/load_settings", headers={"Origin": trusted_origin}
            )
            self.assertIn(st_opt, (200, 204))
            self.assertEqual(hdrs_opt.get("access-control-allow-origin"), trusted_origin)
            self.assertEqual(hdrs_opt.get("vary"), "Origin")
            self.assertIn("X-MyServer-Core-Token", hdrs_opt.get("access-control-allow-headers", ""))

            st_get, hdrs_get, _ = self._raw_http(
                "GET",
                "/api/get_log_directory",
                headers={"Origin": trusted_origin, "X-MyServer-Core-Token": token},
            )
            self.assertEqual(st_get, 200)
            self.assertEqual(hdrs_get.get("access-control-allow-origin"), trusted_origin)
            self.assertEqual(hdrs_get.get("vary"), "Origin")

        # Untrusted Origin: OPTIONS -> 403, GET/POST -> omit ACAO
        st_evil_opt, hdrs_evil_opt, _ = self._raw_http(
            "OPTIONS", "/api/load_settings", headers={"Origin": "https://evil.com"}
        )
        self.assertEqual(st_evil_opt, 403)
        self.assertIsNone(hdrs_evil_opt.get("access-control-allow-origin"))

        st_evil_post, hdrs_evil_post, _ = self._raw_http(
            "POST",
            "/api/load_settings",
            payload={},
            headers={"Origin": "https://evil.com", "X-MyServer-Core-Token": token},
        )
        self.assertEqual(st_evil_post, 200)
        self.assertIsNone(hdrs_evil_post.get("access-control-allow-origin"))

        # Absent Origin: omit ACAO (never *)
        st_no_orig, hdrs_no_orig, _ = self._raw_http(
            "GET", "/api/get_log_directory", headers={"X-MyServer-Core-Token": token}
        )
        self.assertEqual(st_no_orig, 200)
        self.assertIsNone(hdrs_no_orig.get("access-control-allow-origin"))

        # Dev origin only allowed when MYSERVER_DEV_CORS=1
        with patch.dict(os.environ, {"MYSERVER_DEV_CORS": "0"}, clear=False):
            st_dev_off, hdrs_dev_off, _ = self._raw_http(
                "OPTIONS", "/api/load_settings", headers={"Origin": "http://localhost:5173"}
            )
            self.assertEqual(st_dev_off, 403)
            self.assertIsNone(hdrs_dev_off.get("access-control-allow-origin"))

        with patch.dict(os.environ, {"MYSERVER_DEV_CORS": "1"}, clear=False):
            st_dev_on, hdrs_dev_on, _ = self._raw_http(
                "OPTIONS", "/api/load_settings", headers={"Origin": "http://localhost:5173"}
            )
            self.assertIn(st_dev_on, (200, 204))
            self.assertEqual(hdrs_dev_on.get("access-control-allow-origin"), "http://localhost:5173")

    def test_03_updater_url_allowlist_and_redirect_validation(self):
        """SECH-01: Updater rejects non-HTTPS/non-Gibranibang/html_url/unsafe-redirect targets and allows CDN redirects."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}

        bad_urls = [
            "http://github.com/Gibranibang/My-Server-beta/releases/download/v4.6.9/MyServer-Setup.exe",
            "file:///C:/Windows/Temp/evil.exe",
            "https://evil.com/evil.exe",
            "https://github.com/attacker/repo/releases/download/v1/a.exe",
            "https://github.com/Gibranibang/My-Server-beta/releases/tag/v4.6.9",
            "https://user:pass@github.com/Gibranibang/My-Server-beta/releases/download/v4.6.9/MyServer-Setup.exe",
        ]
        with patch.object(core, "_download_stream_bounded") as mock_dl:
            for bad_url in bad_urls:
                st, _, body = self._raw_http(
                    "POST",
                    "/api/download_and_install_update",
                    payload={"downloadUrl": bad_url},
                    headers=auth_hdr,
                )
                self.assertEqual(st, 400, f"Expected 400 for {bad_url}, got {st}: {body}")
                self.assertIs(body.get("success"), False)
            mock_dl.assert_not_called()

        # Valid official GitHub release URL reaches _download_stream_bounded with url_validator & no NameError on repo_slug
        valid_url = "https://github.com/Gibranibang/My-Server-beta/releases/download/v4.6.9/MyServer-Setup.zip"

        def _fake_dl(_url, dest_path, **_kw):
            with open(dest_path, "wb") as fh:
                fh.write(b"PK" + b"\x00" * 2046)
            return 2048

        with patch.dict(os.environ, {"TEMP": self.tmp_dir.name}, clear=False), \
             patch.object(core, "_download_stream_bounded", side_effect=_fake_dl) as mock_dl, \
             patch.object(core, "apply_zip_update", return_value={"success": True}):
            st_ok, _, body_ok = self._raw_http(
                "POST",
                "/api/download_and_install_update",
                payload={"downloadUrl": valid_url},
                headers=auth_hdr,
            )
        self.assertEqual(st_ok, 200)
        self.assertIs(body_ok.get("success"), True, body_ok)
        mock_dl.assert_called_once()
        validator_arg = mock_dl.call_args.kwargs.get("url_validator")
        self.assertTrue(callable(validator_arg))
        self.assertEqual(
            validator_arg(
                "https://objects.githubusercontent.com/github-production-release-asset-2e65be/MyServer-Setup.zip",
                is_redirect=True,
            ),
            "https://objects.githubusercontent.com/github-production-release-asset-2e65be/MyServer-Setup.zip",
        )

        # Redirect handler inside _download_stream_bounded: allows official CDN 302, blocks evil/loopback 302
        validator = lambda u, is_redirect=False: core.validate_official_update_download_url(
            u, allowed_repo="Gibranibang/My-Server-beta", is_redirect=is_redirect
        )
        redir_handler = core._ValidatedRedirectHandler(validator)
        base_req = urllib.request.Request(valid_url)

        allowed_redir_req = redir_handler.redirect_request(
            base_req,
            io.BytesIO(b""),
            302,
            "Found",
            {},
            "https://objects.githubusercontent.com/github-production-release-asset-2e65be/MyServer-Setup.zip",
        )
        self.assertIsNotNone(allowed_redir_req)
        self.assertTrue(allowed_redir_req.full_url.startswith("https://objects.githubusercontent.com/"))

        for bad_redir in (
            "http://127.0.0.1/evil.exe",
            "https://evil.com/evil.exe",
            "file:///C:/Windows/calc.exe",
            "https://169.254.169.254/latest/meta-data/",
        ):
            with self.assertRaises(ValueError):
                redir_handler.redirect_request(
                    base_req, io.BytesIO(b""), 302, "Found", {}, bad_redir
                )

        # End-to-end _download_stream_bounded opener invocation verifying redirect validator is invoked
        class _FakeOpener:
            def __init__(self, handler):
                self.handler = handler

            def open(self, req, timeout=None):
                self.handler.redirect_request(
                    req,
                    io.BytesIO(b""),
                    302,
                    "Found",
                    {},
                    "http://127.0.0.1/evil.exe",
                )
                raise AssertionError("Should have raised ValueError before returning response")

        dest_path = os.path.join(self.tmp_dir.name, "out.zip")
        with patch.object(
            core.urllib.request,
            "build_opener",
            side_effect=lambda h: _FakeOpener(h),
        ):
            with self.assertRaises(ValueError):
                core._download_stream_bounded(valid_url, dest_path, url_validator=validator)
        self.assertFalse(os.path.exists(dest_path))

    def test_04_browser_url_validation_and_rust_invariants(self):
        """SECH-02: Core browser launcher rejects unsafe schemes; src-tauri/src/lib.rs uses ShellExecuteW + CSPRNG."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}

        with patch.object(core.webbrowser, "open") as mock_wb, \
             patch.object(core.os, "startfile", create=True) as mock_sf:
            for unsafe_url in (
                "file:///C:/Windows/calc.exe",
                "javascript:alert(1)",
                "ms-msdt:/id",
                r"\\evil\share\payload.exe",
                "https://evil.com/a\" & calc.exe",
            ):
                st, _, body = self._raw_http(
                    "POST",
                    "/api/open_external_browser",
                    payload={"url": unsafe_url},
                    headers=auth_hdr,
                )
                self.assertEqual(st, 400, f"Expected 400 for unsafe URL {unsafe_url!r}, got {st}")
                self.assertIs(body.get("success"), False)
            mock_wb.assert_not_called()
            mock_sf.assert_not_called()

            safe_url = "https://example.com/a?x=1&y=2"
            with patch.object(core.sys, "platform", "linux"):
                st_ok, _, body_ok = self._raw_http(
                    "POST",
                    "/api/open_external_browser",
                    payload={"url": safe_url},
                    headers=auth_hdr,
                )
            self.assertEqual(st_ok, 200)
            self.assertIs(body_ok.get("success"), True)
            mock_wb.assert_called_once_with(safe_url)

        # spawn_app_window also blocks unsafe schemes
        ok_spawn, msg_spawn = core.spawn_app_window("file:///C:/Windows/calc.exe", "Evil")
        self.assertFalse(ok_spawn)
        self.assertIn("http", msg_spawn.lower())

        # Static assertions on Phase 10-01 src-tauri/src/lib.rs
        lib_rs_path = os.path.join(REPO_ROOT, "src-tauri", "src", "lib.rs")
        with open(lib_rs_path, "r", encoding="utf-8") as fh:
            lib_src = fh.read()
        self.assertIn("ShellExecuteW", lib_src)
        self.assertIn("BCryptGenRandom", lib_src)
        self.assertIn('unsafe extern "system"', lib_src)
        self.assertIn("validate_external_browser_url", lib_src)
        self.assertIn("MYSERVER_CORE_TOKEN", lib_src)
        self.assertIn("X-MyServer-Core-Token", lib_src)
        self.assertIsNone(re.search(r'Command::new\(\s*"cmd"\s*\)', lib_src))
        self.assertNotIn("raw_arg", lib_src)

    def test_05_non_admin_smb_source_compat_and_vms_admin_jwt_preference(self):
        """SECH-03: Non-admin Desktop user mounts Backend SMB when mode==backend; /api/v1/vms prefers admin creds."""
        smb_state = {"mode": "backend", "mode_posts": [], "disks_auths": [], "vms_auths": []}

        class _MockBackendHandler(http.server.BaseHTTPRequestHandler):
            def _send(self, code, payload):
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                if self.path == "/api/v1/auth/verify":
                    uname = str(body.get("username") or "").strip().lower()
                    if uname == "admin_ops":
                        self._send(
                            200,
                            {
                                "success": True,
                                "access_token": "jwt.admin.token",
                                "username": "admin_ops",
                                "role": "admin",
                                "allowed_disks": [],
                            },
                        )
                        return
                    self._send(
                        200,
                        {
                            "success": True,
                            "access_token": "jwt.user.token",
                            "username": "user_1",
                            "role": "user",
                            "allowed_disks": ["Media"],
                        },
                    )
                    return

                if self.path == "/api/v1/smb/mode":
                    auth = self.headers.get("Authorization", "")
                    smb_state["mode_posts"].append(auth)
                    if auth != "Bearer jwt.admin.token":
                        self._send(403, {"detail": "Hanya administrator yang diizinkan mengubah mode SMB."})
                        return
                    smb_state["mode"] = body.get("mode", "backend")
                    self._send(200, {"mode": smb_state["mode"]})
                    return

                self._send(404, {"detail": "Not found"})

            def do_GET(self):
                auth = self.headers.get("Authorization", "")
                if self.path == "/api/v1/smb/status":
                    self._send(200, {"mode": smb_state["mode"]})
                    return
                if self.path == "/api/v1/storage/disks":
                    smb_state["disks_auths"].append(auth)
                    self._send(
                        200,
                        {
                            "disks": [
                                {"name": "Media", "relative_path": "Media", "is_accessible": True},
                                {"name": "Private", "relative_path": "Private", "is_accessible": False},
                            ]
                        },
                    )
                    return
                self._send(404, {"detail": "Not found"})

            def log_message(self, format, *args):
                return

        bsrv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _MockBackendHandler)
        bt = threading.Thread(target=bsrv.serve_forever, daemon=True)
        bt.start()
        backend_url = f"http://127.0.0.1:{bsrv.server_port}"
        try:
            with patch.object(core, "_get_active_server_backend_url", return_value=backend_url), \
                 patch.object(core, "get_active_resolved_route", return_value=("http://127.0.0.1:80", "LAN")), \
                 patch.object(smb_mount_manager, "unmount_all_smb_shares", return_value=0), \
                 patch.object(smb_mount_manager, "purge_smb_sessions"), \
                 patch.object(core, "rebind_storage_pipeline"), \
                 patch.object(core, "_scan_live_drives_now", return_value=[]), \
                 patch.object(core.time, "sleep", return_value=None):
                # 1. Inline-credentials non-admin user succeeds when Backend mode is already "backend"
                st_inline, res_inline = core._handle_smb_source_request(
                    {
                        "action": "set",
                        "source": "backend",
                        "username": "user_1",
                        "password": "UserSecret!9",
                    }
                )
                self.assertEqual(st_inline, 200, res_inline)
                self.assertIs(res_inline.get("success"), True)
                self.assertEqual(res_inline.get("allowedDisks"), ["Media"])
                self.assertEqual(smb_state["mode_posts"], [])

                # 2. Stored-credentials non-admin user also succeeds when Backend mode is already "backend"
                st_stored, res_stored = core._handle_smb_source_request(
                    {"action": "set", "source": "backend"}
                )
                self.assertEqual(st_stored, 200, res_stored)
                self.assertIs(res_stored.get("success"), True)
                self.assertEqual(smb_state["mode_posts"], [])

                # 3. When Backend mode is "zimaos", non-admin user cleanly gets 403
                smb_state["mode"] = "zimaos"
                st_403, res_403 = core._handle_smb_source_request(
                    {"action": "set", "source": "backend"}
                )
                self.assertEqual(st_403, 403, res_403)
                self.assertIs(res_403.get("success"), False)
                self.assertEqual(len(smb_state["mode_posts"]), 1)

            # 4. _resolve_backend_bearer_token_for_url prefers admin creds for /api/v1/vms
            cfg_now = config_manager.load_or_create_config()
            config_manager.save_server_smb_source_config(
                cfg_now,
                "srv_1",
                source="backend",
                username="user_1",
                password="UserSecret!9",
                role="user",
                allowed_disks=["Media"],
                access_token="jwt.user.token",
            )
            with patch.object(
                core,
                "_verify_backend_account",
                return_value=(200, {"access_token": "jwt.admin.token", "role": "admin"}),
            ) as mock_verify:
                vms_tok = core._resolve_backend_bearer_token_for_url(f"{backend_url}/api/v1/vms")
            self.assertEqual(vms_tok, "jwt.admin.token")
            mock_verify.assert_called_once_with(backend_url, "admin_ops", "AdminSecret!9")

            # Verify non-admin smb_cfg access_token was NOT overwritten by admin token
            smb_cfg_after = config_manager.get_server_smb_source_config(
                config_manager.load_or_create_config()["servers"][0]
            )
            self.assertEqual(smb_cfg_after["access_token"], "jwt.user.token")
            self.assertEqual(smb_cfg_after["username"], "user_1")
        finally:
            bsrv.shutdown()
            bsrv.server_close()

    def test_06_start_server_writes_and_cleans_up_core_token(self):
        """SECH-01: start_server() writes core.token next to core.port with 0600 perms and removes both in finally."""
        token_seen = {}
        expected_token_path = os.path.join(self.tmp_dir.name, "MyServer", "core.token")
        expected_port_path = os.path.join(self.tmp_dir.name, "MyServer", "core.port")

        class _FakeServer:
            def serve_forever(self):
                token_seen["port_exists"] = os.path.isfile(expected_port_path)
                token_seen["token_exists"] = os.path.isfile(expected_token_path)
                with open(expected_token_path, "r", encoding="utf-8") as fh:
                    token_seen["token_value"] = fh.read()
                if os.name != "nt":
                    token_seen["mode"] = os.stat(expected_token_path).st_mode & 0o777
                raise KeyboardInterrupt()

            def server_close(self):
                token_seen["closed"] = True

        with patch.dict(os.environ, {"LOCALAPPDATA": self.tmp_dir.name}, clear=False), \
             patch.object(core, "__file__", os.path.join(self.tmp_dir.name, "myserver_core_service.py")), \
             patch.object(core, "ReusableThreadingHTTPServer", return_value=_FakeServer()), \
             patch.object(core.threading, "Thread", return_value=MagicMock()), \
             patch.object(core, "shutdown_background_daemons"):
            core.start_server(port=48199, parent_pid=0)

        self.assertTrue(token_seen.get("port_exists"))
        self.assertTrue(token_seen.get("token_exists"))
        self.assertEqual(token_seen.get("token_value"), core.get_core_auth_token())
        if os.name != "nt":
            self.assertEqual(token_seen.get("mode"), 0o600)
        self.assertTrue(token_seen.get("closed"))
        self.assertFalse(os.path.exists(expected_port_path))
        self.assertFalse(os.path.exists(expected_token_path))


if __name__ == "__main__":
    unittest.main()

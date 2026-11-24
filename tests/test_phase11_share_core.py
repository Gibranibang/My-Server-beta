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


class TestPhase11ShareTracer(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None
        smb_mount_manager.clear_smb_share_cache()
        core._backend_url_cache.clear()
        with core._BACKEND_JWT_CACHE_LOCK:
            core._BACKEND_JWT_CACHE.clear()

        cfg = config_manager.get_default_config()
        cfg["servers"] = [
            {
                "id": "srv_1",
                "name": "HomeNAS",
                "active_connection": "c1",
                "connections": [{"id": "c1", "url": "http://192.168.1.10:8080", "label": "LAN"}],
                "zerotier_virtual_ip": "10.147.20.10",
                "easytier_virtual_ip": "10.144.144.10",
                "smb_source": "zimaos",
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

    def test_tracer_auth_enforced_on_resolve_and_create(self):
        """Missing or invalid X-MyServer-Core-Token returns 401 fail-closed."""
        for path, payload in (
            ("/api/shares/resolve", {"path": r"Z:\Movies\clip.mp4"}),
            ("/api/shares/create", {"path": r"Z:\Movies\clip.mp4"}),
        ):
            st_no, _, body_no = self._raw_http("POST", path, payload=payload)
            self.assertEqual(st_no, 401)
            self.assertIs(body_no.get("success"), False)

            st_bad, _, body_bad = self._raw_http(
                "POST",
                path,
                payload=payload,
                headers={"X-MyServer-Core-Token": "wrong-token"},
            )
            self.assertEqual(st_bad, 401)
            self.assertIs(body_bad.get("success"), False)

    def test_tracer_local_drive_rejected_without_subprocess(self):
        """resolve_local_path_to_smb_unc rejects local drives without calling subprocess."""
        with patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(2250, "")), \
             patch.object(smb_mount_manager.subprocess, "run", side_effect=AssertionError("subprocess forbidden")):
            ok, err = smb_mount_manager.resolve_local_path_to_smb_unc(r"C:\Users\Admin\file.txt")
        self.assertFalse(ok)
        self.assertEqual(err, "LOCAL_DRIVE")

    def test_tracer_resolve_unpack_and_create_lan_fallback(self):
        """End-to-end tracer: 2-tuple unpack, POST /api/shares/resolve, and POST /api/shares/create LAN fallback."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}

        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "jwt_zimaos_1", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/disks"):
                return True, {
                    "disks": [{"name": "Disk1", "relative_path": "Disk1", "mount_point": "/app/storage/Disk1", "is_accessible": True}],
                    "is_admin": True,
                }, 200
            if url.endswith("/api/v1/storage/shares") and method == "POST":
                return True, {
                    "success": True,
                    "share": {
                        "token": "tok123",
                        "share_url": "/s/tok123",
                        "target_path": json_body.get("path"),
                    },
                }, 200
            return False, {"detail": f"unhandled {url}"}, 404

        with patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(0, r"\\192.168.1.10\Disk1")), \
             patch.object(core, "_backend_http_request", side_effect=_fake_backend), \
             patch.object(core, "_write_windows_clipboard", return_value=True):
            # 1. Direct 2-tuple unpacking check
            ok, target = core._resolve_smb_share_target(r"Z:\Movies\clip.mp4")
            self.assertTrue(ok)
            self.assertEqual(target["canonical_rel"], "Disk1/Movies/clip.mp4")
            self.assertTrue(target["is_admin"])

            bad_ok, bad_err = core._resolve_smb_share_target("")
            self.assertFalse(bad_ok)
            self.assertEqual(bad_err["code"], "INVALID_PATH")

            # 2. HTTP POST /api/shares/resolve
            st_res, _, body_res = self._raw_http(
                "POST",
                "/api/shares/resolve",
                payload={"path": r"Z:\Movies\clip.mp4"},
                headers=auth_hdr,
            )
            self.assertEqual(st_res, 200)
            self.assertIs(body_res.get("ok"), True)
            self.assertEqual(body_res["target"]["canonical_rel"], "Disk1/Movies/clip.mp4")
            self.assertEqual(body_res["target"]["basename"], "clip.mp4")

            # 3. HTTP POST /api/shares/create converts relative /s/tok123 -> absolute LAN URL
            st_cr, _, body_cr = self._raw_http(
                "POST",
                "/api/shares/create",
                payload={"path": r"Z:\Movies\clip.mp4"},
                headers=auth_hdr,
            )
            self.assertEqual(st_cr, 200)
            self.assertIs(body_cr.get("success"), True)
            self.assertEqual(body_cr.get("share_url"), "http://192.168.1.10:8080/s/tok123")
            self.assertIs(body_cr.get("is_lan_fallback"), True)
            self.assertIs(body_cr.get("clipboard_copied"), True)

    def test_tracer_backend_smb_source_never_uses_zimaos_creds(self):
        """SECH-03: When smb_source == 'backend', missing backend_smb_auth never falls back to ZimaOS admin creds."""
        cfg = config_manager.load_or_create_config()
        cfg["servers"][0]["smb_source"] = "backend"
        config_manager.save_config(cfg)

        with patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(0, r"\\192.168.1.10\Disk1")), \
             patch.object(config_manager, "get_server_credentials", side_effect=AssertionError("ZimaOS creds forbidden")), \
             patch.object(core, "_backend_http_request", side_effect=AssertionError("Network call forbidden without backend_smb_auth")):
            ok, err = core._resolve_smb_share_target(r"Z:\Movies\clip.mp4")

        self.assertFalse(ok)
        self.assertEqual(err["code"], "UNAUTHENTICATED_SESSION")


if __name__ == "__main__":
    unittest.main()

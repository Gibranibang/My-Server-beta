import concurrent.futures
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


class _BaseShareCoreTestCase(unittest.TestCase):
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


class TestPhase11ShareTracer(_BaseShareCoreTestCase):
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
            ok, target = core._resolve_smb_share_target(r"Z:\Movies\clip.mp4")
            self.assertTrue(ok)
            self.assertEqual(target["canonical_rel"], "Disk1/Movies/clip.mp4")
            self.assertTrue(target["is_admin"])

            bad_ok, bad_err = core._resolve_smb_share_target("")
            self.assertFalse(bad_ok)
            self.assertEqual(bad_err["code"], "INVALID_PATH")

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


class TestShareResolver(_BaseShareCoreTestCase):
    def test_invalid_paths_and_traversal_rejected_without_os_calls(self):
        """Empty, whitespace, None, NUL bytes, and .. traversal return INVALID_PATH without Win32 or Backend calls."""
        bad_inputs = [
            "",
            "   ",
            None,
            "Z:\\Movies\\bad\x00.txt",
            r"Z:\Movies\..\secret.txt",
            r"\\192.168.1.10\Disk1\..\etc\passwd",
            r"\\192.168.1.10",
            "relative/path/without/drive.txt",
            "é:\\foo",
        ]
        with patch.object(smb_mount_manager, "_get_wnet_remote_unc", side_effect=AssertionError("Win32 should not run")), \
             patch.object(core, "_backend_http_request", side_effect=AssertionError("Backend should not run")):
            for bad in bad_inputs:
                ok, err = core._resolve_smb_share_target(bad)
                self.assertFalse(ok, f"Expected INVALID_PATH for {bad!r}")
                self.assertEqual(err["code"], "INVALID_PATH", f"Wrong code for {bad!r}: {err}")

    def test_trailing_quote_and_extended_unc_normalization(self):
        """Explorer trailing quote (Z:\") and \\\\?\\UNC\\ prefix normalize cleanly."""
        with patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(0, r"\\192.168.1.10\Disk1")):
            ok_q, info_q = smb_mount_manager.resolve_local_path_to_smb_unc('Z:\\"')
        self.assertTrue(ok_q)
        self.assertEqual(info_q["unc_host"], "192.168.1.10")
        self.assertEqual(info_q["share_name"], "Disk1")
        self.assertEqual(info_q["sub_parts"], [])

        ok_u, info_u = smb_mount_manager.resolve_local_path_to_smb_unc(r"\\?\UNC\192.168.1.10\Disk1\Docs\a.pdf")
        self.assertTrue(ok_u)
        self.assertEqual(info_u["unc_host"], "192.168.1.10")
        self.assertEqual(info_u["share_name"], "Disk1")
        self.assertEqual(info_u["sub_parts"], ["Docs", "a.pdf"])

    def test_local_drives_rejected_immediately(self):
        """C:\\ and D:\\ non-network drives return LOCAL_DRIVE."""
        with patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(2250, "")):
            for p in (r"C:\Users\file.txt", r"D:\data"):
                ok, err = core._resolve_smb_share_target(p)
                self.assertFalse(ok)
                self.assertEqual(err["code"], "LOCAL_DRIVE")

    def test_foreign_nas_rejected(self):
        """Unconfigured UNC host returns FOREIGN_NAS."""
        ok, err = core._resolve_smb_share_target(r"\\192.168.99.99\Public\file.txt")
        self.assertFalse(ok)
        self.assertEqual(err["code"], "FOREIGN_NAS")

    def test_exact_segment_boundary_disk1_vs_disk10(self):
        """Disk1 never collides with Disk10 when matching share_name to Backend disks."""
        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_admin", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/disks"):
                return True, {
                    "disks": [
                        {"name": "Disk10", "relative_path": "Disk10", "mount_point": "/app/storage/Disk10", "is_accessible": True},
                        {"name": "Disk1", "relative_path": "Disk1", "mount_point": "/app/storage/Disk1", "is_accessible": True},
                    ],
                    "is_admin": True,
                }, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_fake_backend):
            ok1, res1 = core._resolve_smb_share_target(r"\\192.168.1.10\Disk1\file.txt")
            ok10, res10 = core._resolve_smb_share_target(r"\\192.168.1.10\Disk10\file.txt")
        self.assertTrue(ok1)
        self.assertEqual(res1["canonical_rel"], "Disk1/file.txt")
        self.assertEqual(res1["disk_name"], "Disk1")
        self.assertTrue(ok10)
        self.assertEqual(res10["canonical_rel"], "Disk10/file.txt")
        self.assertEqual(res10["disk_name"], "Disk10")

        # Only Disk10 mounted -> Disk1 MUST NOT match Disk10
        def _only_disk10(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_admin", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/disks"):
                return True, {
                    "disks": [{"name": "Disk10", "relative_path": "Disk10", "mount_point": "/app/storage/Disk10", "is_accessible": True}],
                    "is_admin": True,
                }, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_only_disk10):
            ok_miss, err_miss = core._resolve_smb_share_target(r"\\192.168.1.10\Disk1\file.txt")
        self.assertFalse(ok_miss)
        self.assertEqual(err_miss["code"], "SHARE_NOT_MOUNTED_IN_BACKEND")

    def test_active_server_first_and_error_1219_alias(self):
        """Active server is checked first; Error-1219 alias and remaining config servers also match."""
        cfg = config_manager.load_or_create_config()
        cfg["servers"].append(
            {
                "id": "srv_2",
                "name": "OfficeNAS",
                "active_connection": "c2",
                "connections": [{"id": "c2", "url": "http://192.168.2.20:8080", "label": "LAN"}],
                "smb_source": "zimaos",
                "credentials": {
                    "Admin": {
                        "username": "office_admin",
                        "password": config_manager.encrypt_credential("OfficeSecret!9"),
                    }
                },
                "profiles": ["Admin"],
                "active_profile": "Admin",
            }
        )
        config_manager.save_config(cfg)

        with smb_mount_manager._alias_1219_lock:
            smb_mount_manager._cached_1219_alias["192.168.1.10"] = "homenas-1219.local"

        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_ok", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/disks"):
                return True, {
                    "disks": [{"name": "Data", "relative_path": "Data", "mount_point": "/app/storage/Data", "is_accessible": True}],
                    "is_admin": True,
                }, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_fake_backend):
            ok_alias, res_alias = core._resolve_smb_share_target(r"\\homenas-1219.local\Data\notes.txt")
            ok_srv2, res_srv2 = core._resolve_smb_share_target(r"\\192.168.2.20\Data\report.pdf")

        self.assertTrue(ok_alias)
        self.assertEqual(res_alias["server_id"], "srv_1")
        self.assertTrue(ok_srv2)
        self.assertEqual(res_srv2["server_id"], "srv_2")

    def test_backend_smb_isolation_and_zimaos_401_refresh(self):
        """smb_source='backend' isolates strictly; smb_source='zimaos' refreshes JWT on 401."""
        cfg = config_manager.load_or_create_config()
        cfg["servers"][0]["smb_source"] = "backend"
        config_manager.save_server_smb_source_config(
            cfg, "srv_1", source="backend", username="staff1", password="StaffPass1!", role="user", allowed_disks=["Disk1"], access_token="expired_tok"
        )
        cfg = config_manager.load_or_create_config()
        cfg["servers"][0]["smb_source"] = "backend"
        config_manager.save_config(cfg)

        # If backend auth fails with 401 -> UNAUTHENTICATED_SESSION, never reads ZimaOS creds
        def _backend_401(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                self.assertEqual(json_body["username"], "staff1")
                return False, {"detail": "Invalid credentials"}, 401
            return False, {"detail": "Expired"}, 401

        with patch.object(config_manager, "get_server_credentials", side_effect=AssertionError("Must not read ZimaOS creds")), \
             patch.object(core, "_backend_http_request", side_effect=_backend_401):
            ok_b, err_b = core._resolve_smb_share_target(r"\\192.168.1.10\Disk1\a.txt")
        self.assertFalse(ok_b)
        self.assertEqual(err_b["code"], "UNAUTHENTICATED_SESSION")

        # Now switch to zimaos without backend_smb_auth, seed stale cached JWT and verify 401 refresh
        cfg["servers"][0]["smb_source"] = "zimaos"
        cfg["servers"][0].pop("backend_smb_auth", None)
        config_manager.save_config(cfg)
        with core._BACKEND_JWT_CACHE_LOCK:
            core._BACKEND_JWT_CACHE[("srv_1", "http://192.168.1.10:8080", "zimaos_share", "admin_ops")] = {"token": "stale_jwt", "fail_until": 0.0}

        calls = []

        def _zima_refresh(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            calls.append((url, (headers or {}).get("Authorization")))
            if url.endswith("/api/v1/storage/disks"):
                if (headers or {}).get("Authorization") == "Bearer stale_jwt":
                    return False, {"detail": "Token expired"}, 401
                return True, {
                    "disks": [{"name": "Disk1", "relative_path": "Disk1", "mount_point": "/app/storage/Disk1", "is_accessible": True}],
                    "is_admin": True,
                }, 200
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "fresh_jwt", "role": "admin"}, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_zima_refresh):
            ok_z, res_z = core._resolve_smb_share_target(r"\\192.168.1.10\Disk1\a.txt")
        self.assertTrue(ok_z)
        self.assertEqual(res_z["canonical_rel"], "Disk1/a.txt")
        self.assertEqual(res_z["smb_source"], "zimaos")

    def test_zimaos_mode_ignores_stale_backend_smb_auth(self):
        """CR-02: Switching back to smb_source='zimaos' ignores leftover backend_smb_auth credentials/token."""
        cfg = config_manager.load_or_create_config()
        config_manager.save_server_smb_source_config(
            cfg,
            "srv_1",
            source="backend",
            username="stale_staff",
            password="StaffPass1!",
            role="user",
            allowed_disks=["Disk1"],
            access_token="stale_backend_tok",
        )
        cfg = config_manager.load_or_create_config()
        config_manager.save_server_smb_source_config(cfg, "srv_1", source="zimaos")

        seen_auth_users = []
        seen_bearer_tokens = []

        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                seen_auth_users.append((json_body or {}).get("username"))
                return True, {"access_token": "zimaos_admin_jwt", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/disks"):
                seen_bearer_tokens.append((headers or {}).get("Authorization"))
                return True, {
                    "disks": [{"name": "Disk1", "relative_path": "Disk1", "mount_point": "/app/storage/Disk1", "is_accessible": True}],
                    "is_admin": True,
                }, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_fake_backend):
            ok, res = core._resolve_smb_share_target(r"\\192.168.1.10\Disk1\a.txt")

        self.assertTrue(ok)
        self.assertEqual(res["smb_source"], "zimaos")
        self.assertEqual(seen_auth_users, ["admin_ops"])
        self.assertEqual(seen_bearer_tokens, ["Bearer zimaos_admin_jwt"])
        self.assertNotIn("stale_staff", seen_auth_users)
        self.assertNotIn("Bearer stale_backend_tok", seen_bearer_tokens)

    def test_zimaos_jwt_cache_key_isolates_active_profile_username(self):
        """CR-03: Switching active_profile from Admin to non-admin misses Admin JWT in _BACKEND_JWT_CACHE."""
        cfg = config_manager.load_or_create_config()
        cfg["servers"][0]["credentials"]["Guest"] = {
            "username": "guest_user",
            "password": config_manager.encrypt_credential("GuestSecret!1"),
        }
        cfg["servers"][0]["profiles"] = ["Admin", "Guest"]
        cfg["servers"][0]["active_profile"] = "Admin"
        config_manager.save_config(cfg)

        seen_calls = []

        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                uname = (json_body or {}).get("username")
                seen_calls.append(("verify", uname))
                tok = "jwt_admin" if uname == "admin_ops" else "jwt_guest"
                role = "admin" if uname == "admin_ops" else "user"
                return True, {"access_token": tok, "role": role}, 200
            if url.endswith("/api/v1/storage/disks"):
                auth = (headers or {}).get("Authorization")
                seen_calls.append(("disks", auth))
                is_adm = auth == "Bearer jwt_admin"
                return True, {
                    "disks": [{"name": "Disk1", "relative_path": "Disk1", "mount_point": "/app/storage/Disk1", "is_accessible": True}],
                    "is_admin": is_adm,
                }, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_fake_backend):
            ok_adm, res_adm = core._resolve_smb_share_target(r"\\192.168.1.10\Disk1\a.txt")
            self.assertTrue(ok_adm)
            self.assertTrue(res_adm["is_admin"])

            # Switch active_profile to Guest
            cfg2 = config_manager.load_or_create_config()
            cfg2["servers"][0]["active_profile"] = "Guest"
            config_manager.save_config(cfg2)

            ok_gst, res_gst = core._resolve_smb_share_target(r"\\192.168.1.10\Disk1\a.txt")
            self.assertTrue(ok_gst)
            self.assertFalse(res_gst["is_admin"])

        self.assertEqual(
            seen_calls,
            [
                ("verify", "admin_ops"),
                ("disks", "Bearer jwt_admin"),
                ("verify", "guest_user"),
                ("disks", "Bearer jwt_guest"),
            ],
        )

    def test_non_admin_missing_disk_probe_and_offline_errors(self):
        """Empty disks + non-admin browse 403 -> FORBIDDEN_PATH, 404 -> SHARE_NOT_MOUNTED_IN_BACKEND; 503/0 -> BACKEND_OFFLINE."""
        def _probe_403(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_user", "role": "user"}, 200
            if url.endswith("/api/v1/storage/disks"):
                return True, {"disks": [], "is_admin": False}, 200
            if "/api/v1/storage/browse" in url:
                return False, {"detail": "Forbidden"}, 403
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_probe_403):
            ok_403, err_403 = core._resolve_smb_share_target(r"\\192.168.1.10\PrivateDisk\secret.txt")
        self.assertFalse(ok_403)
        self.assertEqual(err_403["code"], "FORBIDDEN_PATH")

        def _probe_404(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_user", "role": "user"}, 200
            if url.endswith("/api/v1/storage/disks"):
                return True, {"disks": [], "is_admin": False}, 200
            if "/api/v1/storage/browse" in url:
                return False, {"detail": "Not found"}, 404
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_probe_404):
            ok_404, err_404 = core._resolve_smb_share_target(r"\\192.168.1.10\UsbShare\file.txt")
        self.assertFalse(ok_404)
        self.assertEqual(err_404["code"], "SHARE_NOT_MOUNTED_IN_BACKEND")

        # is_accessible=False -> FORBIDDEN_PATH
        def _inaccessible_disk(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_user", "role": "user"}, 200
            if url.endswith("/api/v1/storage/disks"):
                return True, {
                    "disks": [{"name": "Secret", "relative_path": "Secret", "mount_point": "/app/storage/Secret", "is_accessible": False}],
                    "is_admin": False,
                }, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_inaccessible_disk):
            ok_inacc, err_inacc = core._resolve_smb_share_target(r"\\192.168.1.10\Secret\doc.txt")
        self.assertFalse(ok_inacc)
        self.assertEqual(err_inacc["code"], "FORBIDDEN_PATH")

        # 503 / 0 -> BACKEND_OFFLINE
        def _offline_503(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_ok", "role": "admin"}, 200
            return False, {"error": "down"}, 503

        with patch.object(core, "_backend_http_request", side_effect=_offline_503):
            ok_off, err_off = core._resolve_smb_share_target(r"\\192.168.1.10\Disk1\a.txt")
        self.assertFalse(ok_off)
        self.assertEqual(err_off["code"], "BACKEND_OFFLINE")

        # No reachable backend URL -> SERVER_OFFLINE
        with patch.object(core, "_resolve_share_backend_url", return_value=""):
            ok_srv_off, err_srv_off = core._resolve_smb_share_target(r"\\192.168.1.10\Disk1\a.txt")
        self.assertFalse(ok_srv_off)
        self.assertEqual(err_srv_off["code"], "SERVER_OFFLINE")


class TestShareCoreEndpoints(_BaseShareCoreTestCase):
    def test_all_six_share_routes_enforce_core_token(self):
        """All 6 /api/shares/* endpoints return 401 without valid X-MyServer-Core-Token."""
        routes = [
            ("/api/shares/resolve", {"path": r"Z:\a.txt"}),
            ("/api/shares/list", {}),
            ("/api/shares/create", {"path": r"Z:\a.txt"}),
            ("/api/shares/revoke", {"token": "abc123"}),
            ("/api/shares/settings", {"public_base_url": ""}),
            ("/api/shares/copy_clipboard", {"text": "https://example.com"}),
        ]
        for path, payload in routes:
            st_no, _, body_no = self._raw_http("POST", path, payload=payload)
            self.assertEqual(st_no, 401, f"{path} without token must return 401")
            self.assertIs(body_no.get("success"), False)

            st_bad, _, body_bad = self._raw_http(
                "POST",
                path,
                payload=payload,
                headers={"X-MyServer-Core-Token": "bad-token"},
            )
            self.assertEqual(st_bad, 401, f"{path} with bad token must return 401")
            self.assertIs(body_bad.get("success"), False)

    def test_resolve_idempotent_and_list_preserves_order_and_enriches_url(self):
        """Repeated /api/shares/resolve is idempotent; /api/shares/list preserves Backend order and builds resolved_url."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}

        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_admin", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/disks"):
                return True, {
                    "disks": [{"name": "Disk1", "relative_path": "Disk1", "mount_point": "/app/storage/Disk1", "is_accessible": True}],
                    "is_admin": True,
                }, 200
            if "/api/v1/storage/shares" in url and method == "GET":
                return True, {
                    "shares": [
                        {"token": "newer_tok", "target_path": "Disk1/Movies/clip.mp4", "share_url": "/s/newer_tok"},
                        {"token": "other_tok", "target_path": "Disk1/Docs/readme.md", "share_url": "https://nas.example.com/s/other_tok"},
                        {"token": "older_tok", "target_path": "Disk1/Movies/clip.mp4", "share_url": "/s/older_tok"},
                    ],
                    "public_base_url": "",
                    "is_admin": True,
                    "username": "admin_ops",
                }, 200
            return False, {}, 404

        with patch.object(smb_mount_manager, "_get_wnet_remote_unc", return_value=(0, r"\\192.168.1.10\Disk1")), \
             patch.object(core, "_backend_http_request", side_effect=_fake_backend):
            _, _, r1 = self._raw_http("POST", "/api/shares/resolve", payload={"path": r"Z:\Movies\clip.mp4"}, headers=auth_hdr)
            _, _, r2 = self._raw_http("POST", "/api/shares/resolve", payload={"path": r"Z:\Movies\clip.mp4"}, headers=auth_hdr)
            self.assertEqual(r1, r2)
            self.assertEqual(r1["target"]["canonical_rel"], "Disk1/Movies/clip.mp4")

            st_all, _, body_all = self._raw_http("POST", "/api/shares/list", payload={}, headers=auth_hdr)
            self.assertEqual(st_all, 200)
            self.assertTrue(body_all["success"])
            self.assertEqual([s["token"] for s in body_all["shares"]], ["newer_tok", "other_tok", "older_tok"])
            self.assertEqual(body_all["shares"][0]["resolved_url"], "http://192.168.1.10:8080/s/newer_tok")
            self.assertIs(body_all["shares"][0]["is_lan_fallback"], True)
            self.assertEqual(body_all["shares"][1]["resolved_url"], "https://nas.example.com/s/other_tok")
            self.assertIs(body_all["shares"][1]["is_lan_fallback"], False)

            st_filt, _, body_filt = self._raw_http(
                "POST",
                "/api/shares/list",
                payload={"target_path": "Disk1/Movies/clip.mp4"},
                headers=auth_hdr,
            )
            self.assertEqual(st_filt, 200)
            self.assertEqual([s["token"] for s in body_filt["shares"]], ["newer_tok", "older_tok"])

    def test_create_ignores_client_public_base_url_and_clipboard_flag(self):
        """/api/shares/create strips public_base_url from client payload, validates expiry, and honors copy_to_clipboard."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}
        sent_bodies = []

        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_admin", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/shares") and method == "POST":
                sent_bodies.append(dict(json_body or {}))
                return True, {"success": True, "share": {"token": "t_ok", "share_url": "/s/t_ok"}}, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_fake_backend), \
             patch.object(core, "_write_windows_clipboard", return_value=True) as mock_clip:
            st, _, body = self._raw_http(
                "POST",
                "/api/shares/create",
                payload={
                    "path": "Disk1/Movies/clip.mp4",
                    "server_id": "srv_1",
                    "public_base_url": "https://evil.example.com",
                    "expires_in_hours": 24,
                    "password": "secret",
                    "copy_to_clipboard": False,
                },
                headers=auth_hdr,
            )
        self.assertEqual(st, 200)
        self.assertIs(body["success"], True)
        self.assertIs(body["clipboard_copied"], False)
        mock_clip.assert_not_called()
        self.assertEqual(len(sent_bodies), 1)
        self.assertNotIn("public_base_url", sent_bodies[0])
        self.assertEqual(sent_bodies[0]["expires_in_hours"], 24)
        self.assertEqual(sent_bodies[0]["password"], "secret")

        # Invalid expiry rejected with 400 without touching clipboard
        with patch.object(core, "_write_windows_clipboard", return_value=True) as mock_clip2:
            st_bad, _, body_bad = self._raw_http(
                "POST",
                "/api/shares/create",
                payload={"path": "Disk1/Movies/clip.mp4", "server_id": "srv_1", "expires_in_hours": 99999},
                headers=auth_hdr,
            )
        self.assertEqual(st_bad, 400)
        self.assertIs(body_bad["success"], False)
        mock_clip2.assert_not_called()

    def test_revoke_token_regex_and_already_revoked(self):
        """/api/shares/revoke rejects malformed tokens (400) and handles 404 already-revoked gracefully."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}

        with patch.object(core, "_backend_http_request", side_effect=AssertionError("Must not call Backend on invalid token")):
            for bad_tok in ("", "   ", "../admin", "tok with space", "a/b", "tok?x=1"):
                st_bad, _, body_bad = self._raw_http(
                    "POST",
                    "/api/shares/revoke",
                    payload={"token": bad_tok},
                    headers=auth_hdr,
                )
                self.assertEqual(st_bad, 400, f"Token {bad_tok!r} must be rejected with 400")
                self.assertEqual(body_bad.get("code"), "INVALID_TOKEN")

        def _fake_revoke(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_admin", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/shares/valid_tok-1") and method == "DELETE":
                return True, {"success": True, "token": "valid_tok-1", "status": "revoked"}, 200
            if url.endswith("/api/v1/storage/shares/already_gone") and method == "DELETE":
                return False, {"detail": "Share not found"}, 404
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_fake_revoke):
            st_ok, _, body_ok = self._raw_http(
                "POST", "/api/shares/revoke", payload={"token": "valid_tok-1"}, headers=auth_hdr
            )
            self.assertEqual(st_ok, 200)
            self.assertIs(body_ok["success"], True)

            st_gone, _, body_gone = self._raw_http(
                "POST", "/api/shares/revoke", payload={"token": "already_gone"}, headers=auth_hdr
            )
            self.assertEqual(st_gone, 200)
            self.assertIs(body_gone["success"], False)
            self.assertIs(body_gone["already_revoked"], True)

    def test_settings_propagates_403_and_accepts_https_or_blank(self):
        """/api/shares/settings validates URL scheme, accepts blank/https for admin, and propagates 403 for non-admin."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}

        st_inv, _, _ = self._raw_http(
            "POST",
            "/api/shares/settings",
            payload={"public_base_url": "ftp://invalid.example.com"},
            headers=auth_hdr,
        )
        self.assertEqual(st_inv, 400)

        def _non_admin_put(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_user", "role": "user"}, 200
            if url.endswith("/api/v1/storage/shares/settings") and method == "PUT":
                return False, {"detail": "Hanya administrator yang diizinkan mengubah Public Base URL."}, 403
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_non_admin_put):
            st_403, _, body_403 = self._raw_http(
                "POST",
                "/api/shares/settings",
                payload={"public_base_url": "https://share.example.com"},
                headers=auth_hdr,
            )
        self.assertEqual(st_403, 403)
        self.assertIs(body_403["success"], False)

        def _admin_put(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_admin", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/shares/settings") and method == "PUT":
                return True, {"success": True, "public_base_url": json_body.get("public_base_url", "")}, 200
            return False, {}, 404

        with patch.object(core, "_backend_http_request", side_effect=_admin_put):
            st_ok, _, body_ok = self._raw_http(
                "POST",
                "/api/shares/settings",
                payload={"public_base_url": "https://share.example.com/"},
                headers=auth_hdr,
            )
            self.assertEqual(st_ok, 200)
            self.assertEqual(body_ok["public_base_url"], "https://share.example.com")

            st_clr, _, body_clr = self._raw_http(
                "POST",
                "/api/shares/settings",
                payload={"public_base_url": ""},
                headers=auth_hdr,
            )
            self.assertEqual(st_clr, 200)
            self.assertEqual(body_clr["public_base_url"], "")

    def test_copy_clipboard_endpoint(self):
        """/api/shares/copy_clipboard delegates to _write_windows_clipboard."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}
        with patch.object(core, "_write_windows_clipboard", return_value=True) as mock_clip:
            st, _, body = self._raw_http(
                "POST",
                "/api/shares/copy_clipboard",
                payload={"text": "https://share.example.com/s/tok1"},
                headers=auth_hdr,
            )
        self.assertEqual(st, 200)
        self.assertIs(body["success"], True)
        mock_clip.assert_called_once_with("https://share.example.com/s/tok1")

    def test_concurrent_resolve_thread_safety(self):
        """Concurrent POST /api/shares/resolve requests execute thread-safely under ThreadingHTTPServer."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}

        def _fake_backend(url, method="GET", json_body=None, headers=None, timeout=5.0, retries=1):
            if url.endswith("/api/v1/auth/verify"):
                return True, {"access_token": "tok_concurrent", "role": "admin"}, 200
            if url.endswith("/api/v1/storage/disks"):
                return True, {
                    "disks": [{"name": "Disk1", "relative_path": "Disk1", "mount_point": "/app/storage/Disk1", "is_accessible": True}],
                    "is_admin": True,
                }, 200
            return False, {}, 404

        def _worker(idx):
            st, _, body = self._raw_http(
                "POST",
                "/api/shares/resolve",
                payload={"path": rf"\\192.168.1.10\Disk1\Folder\file_{idx}.txt"},
                headers=auth_hdr,
            )
            return st, body

        with patch.object(core, "_backend_http_request", side_effect=_fake_backend):
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(_worker, range(16)))

        for idx, (st, body) in enumerate(results):
            self.assertEqual(st, 200)
            self.assertIs(body.get("ok"), True)
            self.assertEqual(body["target"]["canonical_rel"], f"Disk1/Folder/file_{idx}.txt")

    def test_unknown_explicit_server_id_fails_closed_with_foreign_nas(self):
        """WR-01: Explicit unknown server_id fails closed with FOREIGN_NAS instead of falling back to active server."""
        token = core.get_core_auth_token()
        auth_hdr = {"X-MyServer-Core-Token": token}
        endpoints = [
            ("/api/shares/create", {"path": "Disk1/a.txt", "server_id": "deleted_srv"}),
            ("/api/shares/list", {"server_id": "deleted_srv"}),
            ("/api/shares/revoke", {"token": "tok_123", "server_id": "deleted_srv"}),
            ("/api/shares/settings", {"public_base_url": "https://nas.example.com", "server_id": "deleted_srv"}),
        ]
        with patch.object(core, "_backend_http_request", side_effect=AssertionError("Must not hit active server backend")):
            for ep, payload in endpoints:
                st, _, body = self._raw_http("POST", ep, payload=payload, headers=auth_hdr)
                self.assertEqual(st, 400, f"{ep} must return 400 for unknown server_id")
                self.assertIs(body.get("success"), False)
                self.assertEqual(body.get("code"), "FOREIGN_NAS")


if __name__ == "__main__":
    unittest.main()

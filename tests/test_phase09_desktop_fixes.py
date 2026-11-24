"""
Phase 09 Desktop Core & InstaBox regression tests (FIXV-01, FIXV-02, FIXV-04, FIXV-05):
- FIXV-01: /api/vms/save never diff-deletes omitted server VMs & preserves non-tombstoned VMs
- FIXV-02: instabox_manager Retry-After parsing, uniform 'error' keys, lastActive, cfg['vms'] support;
           myserver_core_service do_POST local import re elimination, log_warning, <30m threshold
- FIXV-04: autoCheckUpdate load/save round-trip, top-level tempfile, REG_RUN_KEY/AUTORUN_KEY_NAME
- FIXV-05: /api/v1/events/ in _PROTECTED_CONTROL_PREFIXES, SSE 401 refresh, SSE server-switch reconnect
"""

import ast
import ctypes
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest.mock import MagicMock, patch


def _install_linux_win_stubs():
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
        ctypes.WinDLL = lambda *a, **k: _DummyDll()

    if "winreg" not in sys.modules:
        winreg_stub = types.ModuleType("winreg")
        winreg_stub.HKEY_CURRENT_USER = 0x80000001
        winreg_stub.HKEY_LOCAL_MACHINE = 0x80000002
        winreg_stub.KEY_READ = 0x20019
        winreg_stub.KEY_WRITE = 0x20006
        winreg_stub.KEY_ALL_ACCESS = 0xF003F
        winreg_stub.REG_SZ = 1
        winreg_stub.OpenKey = lambda *_a, **_kw: (_ for _ in ()).throw(FileNotFoundError())
        winreg_stub.QueryValueEx = lambda *_a, **_kw: ("", 1)
        winreg_stub.CreateKey = lambda *_a, **_kw: None
        winreg_stub.SetValueEx = lambda *_a, **_kw: None
        winreg_stub.CloseKey = lambda *_a, **_kw: None
        sys.modules["winreg"] = winreg_stub


_install_linux_win_stubs()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config_manager  # noqa: E402
import instabox_manager as ib  # noqa: E402
import myserver_core_service as core  # noqa: E402
import smb_mount_manager as smb  # noqa: E402


class _StopSseLoop(BaseException):
    pass


class TestPhase09StaticAndCoreRuntime(unittest.TestCase):
    def test_01_do_post_has_no_local_import_re_and_no_log_warn(self):
        src_path = os.path.join(REPO_ROOT, "myserver_core_service.py")
        with open(src_path, "r", encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CoreApiHandler")
        do_post = next(f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name == "do_POST")

        re_imports = []
        for node in ast.walk(do_post):
            if isinstance(node, ast.Import) and any(a.name == "re" for a in node.names):
                re_imports.append(node.lineno)
            elif isinstance(node, ast.ImportFrom) and node.module == "re":
                re_imports.append(node.lineno)

        self.assertEqual(re_imports, [], f"Local import re found in do_POST at lines: {re_imports}")
        self.assertNotIn("log_warn(", src)
        self.assertNotIn("max(30, max_run_mins - 5)", src)
        self.assertTrue(hasattr(core, "tempfile"))

    def test_02_cleanup_temp_update_artifacts_runs_without_name_error(self):
        with tempfile.TemporaryDirectory() as td:
            old_file = os.path.join(td, "myserver_upd_old.bat")
            with open(old_file, "w", encoding="utf-8") as fh:
                fh.write("@echo off\n")
            stale_ts = time.time() - 120
            os.utime(old_file, (stale_ts, stale_ts))
            with patch.dict(os.environ, {"TEMP": td}):
                core.cleanup_temp_update_artifacts()
            self.assertFalse(os.path.exists(old_file))

    def test_03_apply_zip_update_uses_reg_run_key_and_autorun_key_name(self):
        with tempfile.TemporaryDirectory() as td:
            zip_path = os.path.join(td, "update.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("MyServer-Beta.exe", b"MZ-FAKE-EXE")

            captured_bats = []

            def fake_popen(args, **_kwargs):
                bat_path = args[2] if isinstance(args, list) and len(args) > 2 else ""
                if bat_path and os.path.isfile(bat_path):
                    with open(bat_path, "r", encoding="utf-8") as bf:
                        captured_bats.append(bf.read())
                return MagicMock()

            with patch.dict(os.environ, {"TEMP": td}), \
                 patch.object(core.dialog_helper, "prompt_confirm", return_value=True), \
                 patch.object(core, "is_autorun_enabled", return_value=True), \
                 patch.object(core, "get_gui_executable_path", return_value=""), \
                 patch.object(core.config_manager, "get_base_dir", return_value=td), \
                 patch.object(core, "shutdown_background_daemons"), \
                 patch.object(core.os, "_exit"), \
                 patch.object(core.threading, "Thread", return_value=MagicMock()), \
                 patch.object(core.subprocess, "Popen", side_effect=fake_popen):
                res = core.apply_zip_update(zip_path)

            self.assertTrue(res.get("success"), res)
            self.assertTrue(captured_bats)
            bat_text = captured_bats[0]
            self.assertIn(core.REG_RUN_KEY, bat_text)
            self.assertIn(core.AUTORUN_KEY_NAME, bat_text)
            self.assertNotIn("{REG_KEY}", bat_text)
            self.assertNotIn("{APP_NAME}", bat_text)


class TestPhase09InstaBoxFixes(unittest.TestCase):
    def test_01_parse_retry_after_seconds_variants(self):
        self.assertEqual(ib._parse_retry_after_seconds(120), 120)
        self.assertEqual(ib._parse_retry_after_seconds(95.9), 95)
        self.assertEqual(ib._parse_retry_after_seconds("120"), 120)
        self.assertEqual(ib._parse_retry_after_seconds(" 45.2 "), 45)
        self.assertEqual(ib._parse_retry_after_seconds(None), 300)
        self.assertEqual(ib._parse_retry_after_seconds(""), 300)
        self.assertEqual(ib._parse_retry_after_seconds("not-a-date"), 300)
        self.assertEqual(ib._parse_retry_after_seconds(True), 300)

        future_dt = datetime.now(timezone.utc) + timedelta(seconds=180)
        parsed_http_date = ib._parse_retry_after_seconds(format_datetime(future_dt))
        self.assertGreaterEqual(parsed_http_date, 175)
        self.assertLessEqual(parsed_http_date, 185)

    def test_02_update_and_delete_vm_operate_on_cfg_vms_and_instabox_vms(self):
        cfg = {
            "vms": [
                {"id": "vm_main", "name": "Main VM", "status": "sleeping", "lastActive": "Sleeping"}
            ],
            "instabox_vms": [
                {"id": "vm_legacy", "name": "Legacy VM", "status": "sleeping"}
            ],
        }
        with patch.object(ib.InstaBoxManager, "_get_config", return_value=cfg), \
             patch.object(ib.InstaBoxManager, "_save_config", return_value=True) as save_mock:
            updated = ib.InstaBoxManager.update_vm(
                "vm_main", {"status": "running", "lastActive": "Just now"}
            )
            self.assertIsNotNone(updated)
            self.assertEqual(cfg["vms"][0]["status"], "running")
            self.assertEqual(cfg["vms"][0]["lastActive"], "Just now")
            self.assertTrue(ib.InstaBoxManager.delete_vm("vm_main"))
            self.assertEqual(cfg["vms"], [])
            self.assertEqual(len(cfg["instabox_vms"]), 1)
            self.assertEqual(save_mock.call_count, 2)

    def test_03_resume_pause_error_keys_last_active_and_409_retry_after(self):
        vm_no_creds = {"id": "vm_nocred", "name": "NoCred", "apiKey": "", "machineId": ""}
        with patch.object(ib.InstaBoxManager, "get_vm", return_value=vm_no_creds):
            r_err = ib.InstaBoxManager.resume_vm("vm_nocred")
            p_err = ib.InstaBoxManager.pause_vm("vm_nocred")
        self.assertIn("error", r_err)
        self.assertIn("error", p_err)
        self.assertTrue(ib._is_error_response(r_err))
        self.assertTrue(ib._is_error_response(p_err))

        vm_ok = {"id": "vm_1", "name": "Box", "apiKey": "ibk_1", "machineId": "m_1", "status": "running"}
        with patch.object(ib.InstaBoxManager, "get_vm", return_value=vm_ok), \
             patch.object(
                 ib.InstaBoxManager,
                 "_api_request",
                 return_value={"error": "cooldown", "code": 409, "retryAfterSeconds": None},
             ), \
             patch.object(ib.InstaBoxManager, "update_vm") as upd_mock:
            res_409 = ib.InstaBoxManager.resume_vm("vm_1")
        self.assertEqual(res_409["code"], 409)
        self.assertEqual(res_409["retryAfterSeconds"], 300)
        upd_mock.assert_called_once()

        with patch.object(ib.InstaBoxManager, "get_vm", return_value=vm_ok), \
             patch.object(ib.InstaBoxManager, "_api_request", return_value={"status": "ok"}), \
             patch.object(ib.InstaBoxManager, "update_vm") as upd_pause:
            res_pause = ib.InstaBoxManager.pause_vm("vm_1")
        self.assertEqual(res_pause["status"], "ok")
        upd_pause.assert_called_once_with("vm_1", {"status": "sleeping", "lastActive": "Sleeping"})

        with patch.object(ib.InstaBoxManager, "get_vm", return_value=vm_ok), \
             patch.object(
                 ib.InstaBoxManager,
                 "_api_request",
                 return_value={"machine": {"id": "m_1", "state": "suspended"}},
             ), \
             patch.object(ib.InstaBoxManager, "update_vm") as upd_sync:
            res_sync = ib.InstaBoxManager.sync_vm_status("vm_1")
        self.assertEqual(res_sync["status"], "ok")
        self.assertEqual(upd_sync.call_args[0][1]["lastActive"], "Sleeping")


class TestPhase09CoreHttpEndpoints(unittest.TestCase):
    def setUp(self):
        core._recent_vm_mutations.clear()
        core._deleted_vms_tombstone.clear()
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

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()
        core._recent_vm_mutations.clear()
        core._deleted_vms_tombstone.clear()

    def _post_json(self, path, payload):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Content-Length": str(len(data))},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_01_vms_save_never_diff_deletes_and_preserves_omitted_vms(self):
        cfg = config_manager.get_default_config()
        cfg["servers"] = [{"id": "srv_1", "name": "NAS", "connections": [{"id": "c1", "url": "http://192.168.1.50:80"}]}]
        cfg["active_server_id"] = "srv_1"
        cfg["vms"] = [
            {"id": "vm_existing_srv", "name": "Existing Server VM", "scope": "server", "serverId": "srv_1", "status": "sleeping"},
            {"id": "vm_existing_loc", "name": "Existing Local VM", "scope": "local", "status": "sleeping"},
        ]
        config_manager.save_config(cfg)

        calls = []

        def fake_backend_req(url, method="GET", json_body=None, timeout=5.0, retries=0):
            calls.append((method, url, json_body))
            return True, {"ok": True}, 200

        new_vm = {"id": "vm_new_srv", "name": "New Server VM", "scope": "server", "serverId": "srv_1", "status": "sleeping"}
        with patch.object(core, "_get_active_server_backend_url", return_value="http://192.168.1.50:8080"), \
             patch.object(core, "_backend_http_request", side_effect=fake_backend_req):
            status, body = self._post_json("/api/vms/save", {"vms": [new_vm]})

        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        methods = [c[0] for c in calls]
        self.assertNotIn("DELETE", methods)
        self.assertNotIn("GET", methods)
        self.assertEqual(methods, ["POST"])
        self.assertEqual(calls[0][1], "http://192.168.1.50:8080/api/v1/vms")

        saved_cfg = config_manager.load_or_create_config()
        saved_ids = [v["id"] for v in saved_cfg.get("vms", [])]
        self.assertEqual(saved_ids, ["vm_existing_srv", "vm_existing_loc", "vm_new_srv"])

    def test_02_auto_check_update_roundtrip_load_and_get_settings(self):
        cfg = config_manager.get_default_config()
        config_manager.save_config(cfg)

        st_l0, d_l0 = self._post_json("/api/load_settings", {})
        self.assertEqual(st_l0, 200)
        self.assertIs(d_l0.get("autoCheckUpdate"), True)

        st_s1, _ = self._post_json("/api/save_settings", {"settings": {"autoCheckUpdate": False}})
        self.assertEqual(st_s1, 200)

        st_g1, d_g1 = self._post_json("/api/get_settings", {})
        self.assertEqual(st_g1, 200)
        self.assertIs(d_g1.get("autoCheckUpdate"), False)

        st_s2, _ = self._post_json("/api/save_settings", {"settings": {"autoCheckUpdate": True}})
        self.assertEqual(st_s2, 200)

        st_l2, d_l2 = self._post_json("/api/load_settings", {})
        self.assertEqual(st_l2, 200)
        self.assertIs(d_l2.get("autoCheckUpdate"), True)


class TestPhase09SseAuthAndReconnect(unittest.TestCase):
    def setUp(self):
        with core._BACKEND_JWT_CACHE_LOCK:
            core._BACKEND_JWT_CACHE.clear()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None

    def tearDown(self):
        with core._BACKEND_JWT_CACHE_LOCK:
            core._BACKEND_JWT_CACHE.clear()
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()

    def test_01_events_prefix_protected_and_resolves_bearer_token(self):
        self.assertIn("/api/v1/events/", core._PROTECTED_CONTROL_PREFIXES)
        cfg = config_manager.get_default_config()
        cfg["active_server_id"] = "srv_sse"
        cfg["servers"] = [
            {
                "id": "srv_sse",
                "name": "SSE Server",
                "connections": [{"id": "c1", "url": "http://127.0.0.1:8080"}],
                "profiles": ["Admin"],
                "active_profile": "Admin",
                "credentials": {
                    "Admin": {"username": "admin", "password": config_manager.encrypt_credential("pw")}
                },
            }
        ]
        config_manager.save_config(cfg)

        with patch.object(core, "_verify_backend_account", return_value=(200, {"access_token": "jwt_sse_tok"})):
            tok = core._resolve_backend_bearer_token_for_url("http://127.0.0.1:8080/api/v1/events/stream")
        self.assertEqual(tok, "jwt_sse_tok")

    def test_02_sse_listener_refreshes_on_401_and_reconnects_on_server_switch(self):
        state = {"active": "srv_a"}

        def fake_load_cfg():
            if state["active"] == "srv_a":
                return {
                    "active_server_id": "srv_a",
                    "servers": [{"id": "srv_a", "connections": [{"id": "c1", "url": "http://10.0.0.1:80"}]}],
                }
            return {
                "active_server_id": "srv_b",
                "servers": [{"id": "srv_b", "connections": [{"id": "c2", "url": "http://10.0.0.2:80"}]}],
            }

        def fake_active_srv(cfg):
            aid = cfg.get("active_server_id")
            return next((s for s in cfg.get("servers", []) if s.get("id") == aid), None)

        def fake_backend_url(cfg):
            return "http://10.0.0.1:8080" if cfg.get("active_server_id") == "srv_a" else "http://10.0.0.2:8080"

        resolve_calls = []

        def fake_resolve(url, force_refresh=False):
            resolve_calls.append((url, force_refresh))
            if "10.0.0.1" in url:
                return "fresh_tok_a" if force_refresh else "stale_tok_a"
            return "tok_b"

        class _FakeResp:
            def __init__(self, lines, on_yield=None):
                self._lines = lines
                self._on_yield = on_yield

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def __iter__(self):
                for idx, item in enumerate(self._lines):
                    if self._on_yield:
                        self._on_yield(idx)
                    yield item

        open_urls = []

        def fake_urlopen(req, timeout=45.0):
            url = req.full_url
            auth = req.get_header("Authorization")
            open_urls.append((url, auth))
            if "10.0.0.1" in url and auth == "Bearer stale_tok_a":
                raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, io.BytesIO(b""))
            if "10.0.0.1" in url and auth == "Bearer fresh_tok_a":
                def switch_on_second(idx):
                    if idx == 1:
                        state["active"] = "srv_b"
                return _FakeResp([b"event: smb_synced\n", b": keepalive\n"], on_yield=switch_on_second)
            if "10.0.0.2" in url:
                raise _StopSseLoop()
            raise _StopSseLoop()

        with patch.object(core.config_manager, "load_or_create_config", side_effect=fake_load_cfg), \
             patch.object(core.config_manager, "get_active_server", side_effect=fake_active_srv), \
             patch.object(core, "_get_active_server_backend_url", side_effect=fake_backend_url), \
             patch.object(core, "_resolve_backend_bearer_token_for_url", side_effect=fake_resolve), \
             patch.object(core.urllib.request, "urlopen", side_effect=fake_urlopen), \
             patch.object(smb, "clear_smb_share_cache") as clear_smb_mock, \
             patch.object(core.time, "sleep"):
            with self.assertRaises(_StopSseLoop):
                core._backend_sse_listener_loop()

        self.assertEqual(
            resolve_calls,
            [
                ("http://10.0.0.1:8080/api/v1/events/stream", False),
                ("http://10.0.0.1:8080/api/v1/events/stream", True),
                ("http://10.0.0.2:8080/api/v1/events/stream", False),
            ],
        )
        self.assertEqual(
            open_urls,
            [
                ("http://10.0.0.1:8080/api/v1/events/stream", "Bearer stale_tok_a"),
                ("http://10.0.0.1:8080/api/v1/events/stream", "Bearer fresh_tok_a"),
                ("http://10.0.0.2:8080/api/v1/events/stream", "Bearer tok_b"),
            ],
        )
        clear_smb_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()

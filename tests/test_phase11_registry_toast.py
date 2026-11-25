import copy
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


class _FakeWinRegHive:
    """In-memory HKCU winreg simulator supporting CreateKey/OpenKey/QueryValueEx/SetValueEx/DeleteKey/CloseKey."""

    HKEY_CURRENT_USER = 0x80000001
    KEY_READ = 0x20019
    KEY_WRITE = 0x20006
    KEY_ALL_ACCESS = 0xF003F
    REG_SZ = 1

    def __init__(self):
        self.keys = {}
        self.raise_on_create = None
        self.raise_on_delete = None

    class _Handle:
        def __init__(self, subkey):
            self.subkey = subkey

    def _norm(self, subkey):
        return str(subkey or "").strip("\\")

    def CreateKey(self, hkey, subkey):
        if hkey != self.HKEY_CURRENT_USER:
            raise OSError("Unsupported hive")
        if self.raise_on_create is not None:
            raise self.raise_on_create
        norm = self._norm(subkey)
        self.keys.setdefault(norm, {})
        return self._Handle(norm)

    def OpenKey(self, hkey, subkey, _reserved=0, _access=0):
        if hkey != self.HKEY_CURRENT_USER:
            raise FileNotFoundError(subkey)
        norm = self._norm(subkey)
        if norm not in self.keys:
            raise FileNotFoundError(norm)
        return self._Handle(norm)

    def SetValueEx(self, handle, value_name, _reserved, reg_type, value):
        if handle.subkey not in self.keys:
            raise FileNotFoundError(handle.subkey)
        self.keys[handle.subkey][str(value_name or "")] = (reg_type, str(value))

    def QueryValueEx(self, handle, value_name):
        norm = handle.subkey
        if norm not in self.keys:
            raise FileNotFoundError(norm)
        vname = str(value_name or "")
        if vname not in self.keys[norm]:
            raise FileNotFoundError(vname)
        return self.keys[norm][vname][1], self.keys[norm][vname][0]

    def DeleteKey(self, hkey, subkey):
        if hkey != self.HKEY_CURRENT_USER:
            raise FileNotFoundError(subkey)
        if self.raise_on_delete is not None:
            raise self.raise_on_delete
        norm = self._norm(subkey)
        if norm not in self.keys:
            raise FileNotFoundError(norm)
        prefix = norm + "\\"
        if any(k.startswith(prefix) for k in self.keys):
            raise OSError("Subkeys exist")
        del self.keys[norm]

    def CloseKey(self, _handle):
        return None


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
        hive = _FakeWinRegHive()
        winreg_stub = types.ModuleType("winreg")
        winreg_stub.HKEY_CURRENT_USER = hive.HKEY_CURRENT_USER
        winreg_stub.KEY_READ = hive.KEY_READ
        winreg_stub.KEY_WRITE = hive.KEY_WRITE
        winreg_stub.KEY_ALL_ACCESS = hive.KEY_ALL_ACCESS
        winreg_stub.REG_SZ = hive.REG_SZ
        winreg_stub.OpenKey = hive.OpenKey
        winreg_stub.CreateKey = hive.CreateKey
        winreg_stub.QueryValueEx = hive.QueryValueEx
        winreg_stub.SetValueEx = hive.SetValueEx
        winreg_stub.DeleteKey = hive.DeleteKey
        winreg_stub.CloseKey = hive.CloseKey
        sys.modules["winreg"] = winreg_stub


_install_linux_win_stubs()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config_manager  # noqa: E402
import myserver_core_service as core  # noqa: E402
import smb_mount_manager  # noqa: E402


class _BaseRegistryToastTestCase(unittest.TestCase):
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
        cfg["language"] = "en"
        cfg["servers"] = [
            {
                "id": "srv_1",
                "name": "HomeNAS",
                "active_connection": "c1",
                "connections": [{"id": "c1", "url": "http://192.168.1.10:8080", "label": "LAN"}],
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


class TestQuickShareAndToast(_BaseRegistryToastTestCase):
    def test_quick_share_requires_core_token(self):
        st_no, _, body_no = self._raw_http(
            "POST", "/api/shares/quick", payload={"path": r"Z:\Docs\plan.pdf"}
        )
        self.assertEqual(st_no, 401)
        self.assertIs(body_no.get("success"), False)

        st_bad, _, body_bad = self._raw_http(
            "POST",
            "/api/shares/quick",
            payload={"path": r"Z:\Docs\plan.pdf"},
            headers={"X-MyServer-Core-Token": "wrong-token"},
        )
        self.assertEqual(st_bad, 401)
        self.assertIs(body_bad.get("success"), False)

    def test_quick_share_ok_public_en_and_id(self):
        target = {
            "canonical_rel": "Storage/Docs/plan.pdf",
            "basename": "plan.pdf",
            "is_dir": False,
            "server_id": "srv_1",
            "server_name": "HomeNAS",
            "disk_name": "Storage",
            "share_name": "Storage",
            "is_admin": True,
            "backend_url": "http://192.168.1.10:8080",
            "smb_source": "zimaos",
        }
        share_obj = {
            "token": "pubTok123",
            "share_url": "https://files.example.com/s/pubTok123",
            "target_path": "Storage/Docs/plan.pdf",
        }

        for lang, exp_title, exp_body in (
            ("en", "Share link copied to clipboard", "plan.pdf · Unlimited · No password"),
            ("id", "Tautan berbagi disalin ke clipboard", "plan.pdf · Tanpa batas · Tanpa sandi"),
        ):
            cfg = config_manager.load_or_create_config()
            cfg["language"] = lang
            config_manager.save_config(cfg)

            with patch.object(core, "_resolve_smb_share_target", return_value=(True, target)), \
                 patch.object(core, "_backend_share_request", return_value=(200, {"share": share_obj}, "jwt")) as mock_req, \
                 patch.object(core, "_write_windows_clipboard", return_value=True) as mock_clip, \
                 patch.object(core, "_show_windows_toast", return_value=True) as mock_toast:
                st, _, data = self._raw_http(
                    "POST",
                    "/api/shares/quick",
                    payload={"path": r"Z:\Docs\plan.pdf"},
                    headers={"X-MyServer-Core-Token": core._CORE_AUTH_TOKEN},
                )
            self.assertEqual(st, 200)
            self.assertTrue(data["success"])
            self.assertTrue(data["ok"])
            self.assertEqual(data["code"], "OK_PUBLIC")
            self.assertEqual(data["share_url"], "https://files.example.com/s/pubTok123")
            self.assertFalse(data["is_lan_fallback"])
            self.assertTrue(data["clipboard_copied"])
            self.assertEqual(data["toast_title"], exp_title)
            self.assertEqual(data["toast_body"], exp_body)

            mock_req.assert_called_once()
            _, req_kwargs = mock_req.call_args
            self.assertEqual(
                req_kwargs["json_body"],
                {"path": "Storage/Docs/plan.pdf", "expires_in_hours": None, "password": None, "role": "viewer"},
            )
            mock_clip.assert_called_once_with("https://files.example.com/s/pubTok123")
            mock_toast.assert_called_once_with(exp_title, exp_body, level="info")

    def test_quick_share_ok_lan_fallback_en_and_id(self):
        target = {
            "canonical_rel": "Storage/Photos",
            "basename": "Photos",
            "is_dir": True,
            "server_id": "srv_1",
            "server_name": "HomeNAS",
            "disk_name": "Storage",
            "share_name": "Storage",
            "is_admin": False,
            "backend_url": "http://192.168.1.10:8080",
            "smb_source": "zimaos",
        }
        share_obj = {
            "token": "lanTok99",
            "share_url": "/s/lanTok99",
            "target_path": "Storage/Photos",
        }

        for lang, exp_title, exp_body in (
            ("en", "Share link copied to clipboard", "Photos · Local LAN URL only (Public Base URL not set)"),
            ("id", "Tautan berbagi disalin ke clipboard", "Photos · Tautan LAN lokal saja (Public Base URL belum diatur)"),
        ):
            cfg = config_manager.load_or_create_config()
            cfg["language"] = lang
            config_manager.save_config(cfg)

            with patch.object(core, "_resolve_smb_share_target", return_value=(True, target)), \
                 patch.object(core, "_backend_share_request", return_value=(200, {"share": share_obj}, "jwt")), \
                 patch.object(core, "_write_windows_clipboard", return_value=True) as mock_clip, \
                 patch.object(core, "_show_windows_toast", return_value=True) as mock_toast:
                st, _, data = self._raw_http(
                    "POST",
                    "/api/shares/quick",
                    payload={"path": r"Z:\Photos"},
                    headers={"X-MyServer-Core-Token": core._CORE_AUTH_TOKEN},
                )
            self.assertEqual(st, 200)
            self.assertTrue(data["success"])
            self.assertEqual(data["code"], "OK_LAN_FALLBACK")
            self.assertTrue(data["is_lan_fallback"])
            self.assertEqual(data["share_url"], "http://192.168.1.10:8080/s/lanTok99")
            mock_clip.assert_called_once_with("http://192.168.1.10:8080/s/lanTok99")
            mock_toast.assert_called_once_with(exp_title, exp_body, level="info")

    def test_quick_share_preserves_clipboard_and_emits_localized_error_toasts(self):
        resolve_err_cases = [
            ("LOCAL_DRIVE", "en", "Cannot Share This Item", "Only files or folders on a MyServer SMB drive can be shared. Move the item to a MyServer drive first."),
            ("LOCAL_DRIVE", "id", "Tidak Dapat Membagikan Item Ini", "Hanya file atau folder pada drive SMB MyServer yang dapat dibagikan. Pindahkan item ke drive MyServer terlebih dahulu."),
            ("FOREIGN_NAS", "en", "Cannot Share This Item", "Only files or folders on a MyServer SMB drive can be shared. Move the item to a MyServer drive first."),
            ("FOREIGN_NAS", "id", "Tidak Dapat Membagikan Item Ini", "Hanya file atau folder pada drive SMB MyServer yang dapat dibagikan. Pindahkan item ke drive MyServer terlebih dahulu."),
            ("SHARE_NOT_MOUNTED_IN_BACKEND", "en", "Storage Share Not Accessible by Backend", "This ZimaOS share is not mounted under /app/storage in MyServer Backend. Add the volume in ZimaOS Docker Settings."),
            ("SHARE_NOT_MOUNTED_IN_BACKEND", "id", "Partisi Tidak Terpasang di Backend", "Share ZimaOS ini belum ter-mount ke /app/storage di MyServer Backend. Tambahkan volume melalui Settings Docker ZimaOS."),
            ("SERVER_OFFLINE", "en", "MyServer Backend Unreachable", "Cannot create share link while server or Backend is offline. Check connection in MyServer Companion."),
            ("SERVER_OFFLINE", "id", "MyServer Backend Tidak Terjangkau", "Tidak dapat membuat tautan saat server atau Backend offline. Periksa koneksi di MyServer Companion."),
        ]
        for code, lang, exp_title, exp_body in resolve_err_cases:
            cfg = config_manager.load_or_create_config()
            cfg["language"] = lang
            config_manager.save_config(cfg)
            with patch.object(core, "_resolve_smb_share_target", return_value=(False, {"code": code, "message": "err"})), \
                 patch.object(core, "_write_windows_clipboard") as mock_clip, \
                 patch.object(core, "_show_windows_toast", return_value=True) as mock_toast:
                st, _, data = self._raw_http(
                    "POST",
                    "/api/shares/quick",
                    payload={"path": r"C:\local.txt"},
                    headers={"X-MyServer-Core-Token": core._CORE_AUTH_TOKEN},
                )
            self.assertEqual(st, 200)
            self.assertFalse(data["success"])
            self.assertFalse(data["ok"])
            self.assertEqual(data["code"], code)
            mock_clip.assert_not_called()
            mock_toast.assert_called_once_with(exp_title, exp_body, level="error")

        target = {
            "canonical_rel": "Storage/Docs/a.pdf",
            "basename": "a.pdf",
            "is_dir": False,
            "server_id": "srv_1",
            "server_name": "HomeNAS",
            "disk_name": "Storage",
            "share_name": "Storage",
            "is_admin": False,
            "backend_url": "http://192.168.1.10:8080",
            "smb_source": "backend",
        }
        backend_err_cases = [
            (0, "BACKEND_OFFLINE", "en", "MyServer Backend Unreachable", "Cannot create share link while server or Backend is offline. Check connection in MyServer Companion."),
            (503, "BACKEND_OFFLINE", "id", "MyServer Backend Tidak Terjangkau", "Tidak dapat membuat tautan saat server atau Backend offline. Periksa koneksi di MyServer Companion."),
            (401, "UNAUTHENTICATED_SESSION", "en", "Backend Login Required", "Open MyServer Companion → Storage & Files to sign in to your Backend account before sharing."),
            (401, "UNAUTHENTICATED_SESSION", "id", "Login Akun Backend Diperlukan", "Buka MyServer Companion → Penyimpanan & Berkas untuk masuk ke akun Backend sebelum berbagi."),
            (403, "FORBIDDEN_PATH", "en", "Sharing Permission Denied", "Your Backend account does not have permission to share this storage partition. Contact your administrator."),
            (403, "FORBIDDEN_PATH", "id", "Izin Berbagi Ditolak", "Akun Backend Anda tidak memiliki izin untuk membagikan partisi ini. Hubungi administrator server."),
        ]
        for http_st, exp_code, lang, exp_title, exp_body in backend_err_cases:
            cfg = config_manager.load_or_create_config()
            cfg["language"] = lang
            config_manager.save_config(cfg)
            with patch.object(core, "_resolve_smb_share_target", return_value=(True, target)), \
                 patch.object(core, "_backend_share_request", return_value=(http_st, {"detail": "err"}, "jwt")), \
                 patch.object(core, "_write_windows_clipboard") as mock_clip, \
                 patch.object(core, "_show_windows_toast", return_value=True) as mock_toast:
                st, _, data = self._raw_http(
                    "POST",
                    "/api/shares/quick",
                    payload={"path": r"Z:\Docs\a.pdf"},
                    headers={"X-MyServer-Core-Token": core._CORE_AUTH_TOKEN},
                )
            self.assertEqual(st, 200)
            self.assertFalse(data["success"])
            self.assertEqual(data["code"], exp_code)
            mock_clip.assert_not_called()
            mock_toast.assert_called_once_with(exp_title, exp_body, level="error")

    def test_show_windows_toast_prevents_powershell_injection(self):
        malicious = '$(calc.exe); " & <toast>.pdf'
        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core, "_ensure_toast_aumid_registered", return_value=True), \
             patch.object(core.subprocess, "Popen") as mock_popen:
            ok = core._show_windows_toast("Share link copied to clipboard", malicious, level="info")

        self.assertTrue(ok)
        mock_popen.assert_called_once()
        cmd_args, kwargs = mock_popen.call_args
        cmd_list = cmd_args[0]
        self.assertEqual(cmd_list[-1], core._WINRT_TOAST_PS_SCRIPT)
        self.assertIn("[System.Security.SecurityElement]::Escape", core._WINRT_TOAST_PS_SCRIPT)
        self.assertNotIn("$(calc.exe)", " ".join(cmd_list))
        self.assertNotIn("<toast>.pdf", " ".join(cmd_list))
        self.assertEqual(kwargs["env"]["MYSERVER_TOAST_BODY"], malicious)
        self.assertEqual(kwargs["env"]["MYSERVER_TOAST_AUMID"], core._TOAST_AUMID)
        self.assertEqual(kwargs["env"]["MYSERVER_TOAST_LEVEL"], "info")
        self.assertEqual(kwargs["creationflags"], 0x08000000)

    def test_clipboard_timeout_kills_powershell_and_toast_prefers_system32_exe(self):
        # IN-02: _write_windows_clipboard kills timed-out PowerShell child
        class _HangingProc:
            def __init__(self):
                self.killed = False
                self.returncode = -1
                self.calls = 0

            def communicate(self, input=None, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    raise core.subprocess.TimeoutExpired(cmd="powershell.exe", timeout=timeout or 4.0)
                return b"", b""

            def kill(self):
                self.killed = True

        hanging = _HangingProc()
        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core.subprocess, "Popen", return_value=hanging):
            self.assertFalse(core._write_windows_clipboard("https://example.com"))
        self.assertTrue(hanging.killed)

        # IN-02: _show_windows_toast prefers System32 powershell.exe when file exists
        fake_root = os.path.join(self.tmp_dir.name, "WinRoot")
        ps_path = os.path.join(fake_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        os.makedirs(os.path.dirname(ps_path), exist_ok=True)
        with open(ps_path, "wb") as f:
            f.write(b"MZ")

        with patch.dict(core.os.environ, {"SystemRoot": fake_root}), \
             patch.object(core.sys, "platform", "win32"), \
             patch.object(core, "_ensure_toast_aumid_registered", return_value=True), \
             patch.object(core.subprocess, "Popen") as mock_popen:
            self.assertTrue(core._show_windows_toast("Title", "Body", level="info"))
        self.assertEqual(mock_popen.call_args[0][0][0], ps_path)

    def test_resolve_notify_on_error_hook(self):
        cfg = config_manager.load_or_create_config()
        cfg["language"] = "en"
        config_manager.save_config(cfg)

        with patch.object(core, "_show_windows_toast", return_value=True) as mock_toast:
            st1, _, d1 = self._raw_http(
                "POST",
                "/api/shares/resolve",
                payload={"path": r"C:\local.txt", "notify_on_error": True},
                headers={"X-MyServer-Core-Token": core._CORE_AUTH_TOKEN},
            )
        self.assertEqual(st1, 200)
        self.assertFalse(d1["ok"])
        self.assertEqual(d1["code"], "LOCAL_DRIVE")
        mock_toast.assert_called_once_with(
            "Cannot Share This Item",
            "Only files or folders on a MyServer SMB drive can be shared. Move the item to a MyServer drive first.",
            level="error",
        )

        with patch.object(core, "_show_windows_toast", return_value=True) as mock_toast_off:
            st2, _, d2 = self._raw_http(
                "POST",
                "/api/shares/resolve",
                payload={"path": r"C:\local.txt", "notify_on_error": False},
                headers={"X-MyServer-Core-Token": core._CORE_AUTH_TOKEN},
            )
        self.assertEqual(st2, 200)
        self.assertFalse(d2["ok"])
        mock_toast_off.assert_not_called()


class TestExplorerRegistryAndInstaller(_BaseRegistryToastTestCase):
    def _make_winreg_module(self, hive):
        mod = types.ModuleType("winreg")
        mod.HKEY_CURRENT_USER = hive.HKEY_CURRENT_USER
        mod.KEY_READ = hive.KEY_READ
        mod.KEY_WRITE = hive.KEY_WRITE
        mod.KEY_ALL_ACCESS = hive.KEY_ALL_ACCESS
        mod.REG_SZ = hive.REG_SZ
        mod.OpenKey = hive.OpenKey
        mod.CreateKey = hive.CreateKey
        mod.QueryValueEx = hive.QueryValueEx
        mod.SetValueEx = hive.SetValueEx
        mod.DeleteKey = hive.DeleteKey
        mod.CloseKey = hive.CloseKey
        return mod

    def test_registry_enable_disable_idempotency_and_aumid(self):
        hive = _FakeWinRegHive()
        wreg_mod = self._make_winreg_module(hive)
        app_dir = os.path.join(self.tmp_dir.name, "app")
        os.makedirs(app_dir, exist_ok=True)
        exe_path = os.path.join(app_dir, "MyServer-Beta.exe")
        ico_path = os.path.join(app_dir, "app_icon.ico")
        with open(exe_path, "wb") as f:
            f.write(b"MZ")
        with open(ico_path, "wb") as f:
            f.write(b"ICO")

        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core, "winreg", wreg_mod), \
             patch.object(core, "get_gui_executable_path", return_value=exe_path):
            self.assertFalse(core.is_explorer_context_menu_enabled())

            ok1, err1 = core.set_explorer_context_menu_enabled(True)
            self.assertTrue(ok1, err1)
            self.assertEqual(err1, "")
            self.assertTrue(core.is_explorer_context_menu_enabled())
            snapshot = copy.deepcopy(hive.keys)

            # Double enable overwrites cleanly with identical values
            ok2, err2 = core.set_explorer_context_menu_enabled(True)
            self.assertTrue(ok2, err2)
            self.assertEqual(hive.keys, snapshot)

            expected = [
                (r"Software\Classes\*\shell\MyServerShare", "Share via MyServer", "--share", "%1"),
                (r"Software\Classes\*\shell\MyServerQuickShare", "Quick Share via MyServer", "--quick-share", "%1"),
                (r"Software\Classes\Directory\shell\MyServerShare", "Share via MyServer", "--share", "%1"),
                (r"Software\Classes\Directory\shell\MyServerQuickShare", "Quick Share via MyServer", "--quick-share", "%1"),
                (r"Software\Classes\*\shell\MyServerHttpCopy", "Copy via MyServer", "--explorer-copy", "%1"),
                (r"Software\Classes\Directory\shell\MyServerHttpCopy", "Copy via MyServer", "--explorer-copy", "%1"),
                (r"Software\Classes\Directory\shell\MyServerHttpPaste", "Paste via MyServer", "--explorer-paste", "%1"),
                (r"Software\Classes\Directory\Background\shell\MyServerHttpPaste", "Paste via MyServer", "--explorer-paste", "%V"),
            ]
            for subkey, display_name, flag, arg_placeholder in expected:
                self.assertEqual(hive.keys[subkey][""][1], display_name)
                self.assertEqual(hive.keys[subkey]["Icon"][1], ico_path)
                self.assertEqual(hive.keys[subkey]["MultiSelectModel"][1], "Single")
                self.assertEqual(
                    hive.keys[rf"{subkey}\command"][""][1],
                    f'"{exe_path}" {flag} "{arg_placeholder}"',
                )

            aumid_key = r"Software\Classes\AppUserModelId\com.algithaproject.myserver.companion.beta"
            self.assertEqual(hive.keys[aumid_key]["DisplayName"][1], "MyServer")
            self.assertEqual(hive.keys[aumid_key]["IconUri"][1], ico_path)

            # Double disable is idempotent even when keys are already absent
            ok3, err3 = core.set_explorer_context_menu_enabled(False)
            self.assertTrue(ok3, err3)
            self.assertFalse(core.is_explorer_context_menu_enabled())
            for subkey, _, _, _ in expected:
                self.assertNotIn(subkey, hive.keys)
                self.assertNotIn(rf"{subkey}\command", hive.keys)

            ok4, err4 = core.set_explorer_context_menu_enabled(False)
            self.assertTrue(ok4, err4)
            self.assertFalse(core.is_explorer_context_menu_enabled())

    def test_registry_icon_fallback_and_failure_handling(self):
        hive = _FakeWinRegHive()
        wreg_mod = self._make_winreg_module(hive)
        exe_only = os.path.join(self.tmp_dir.name, "no_ico_dir", "MyServer-Beta.exe")

        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core, "winreg", wreg_mod), \
             patch.object(core, "get_gui_executable_path", return_value=""):
            ok_no_exe, err_no_exe = core.set_explorer_context_menu_enabled(True)
            self.assertFalse(ok_no_exe)
            self.assertIn("GUI executable", err_no_exe)

        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core, "winreg", wreg_mod), \
             patch.object(core, "get_gui_executable_path", return_value=exe_only):
            ok_fb, err_fb = core.set_explorer_context_menu_enabled(True)
            self.assertTrue(ok_fb, err_fb)
            self.assertEqual(
                hive.keys[r"Software\Classes\*\shell\MyServerShare"]["Icon"][1],
                f"{exe_only},0",
            )

        hive.raise_on_create = PermissionError("Access is denied")
        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core, "winreg", wreg_mod), \
             patch.object(core, "get_gui_executable_path", return_value=exe_only):
            ok_perm, err_perm = core.set_explorer_context_menu_enabled(True)
            self.assertFalse(ok_perm)
            self.assertIn("Access is denied", err_perm)

        # WR-04: disable propagates non-ENOENT OSErrors (e.g. winerror 145 / 5), ignores winerror 2
        hive.raise_on_create = None
        err_145 = OSError("The directory is not empty")
        err_145.winerror = 145
        hive.raise_on_delete = err_145
        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core, "winreg", wreg_mod):
            ok_145, msg_145 = core.set_explorer_context_menu_enabled(False)
            self.assertFalse(ok_145)
            self.assertIn("not empty", msg_145)

        err_2 = OSError("The system cannot find the file specified")
        err_2.winerror = 2
        hive.raise_on_delete = err_2
        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core, "winreg", wreg_mod):
            ok_2, msg_2 = core.set_explorer_context_menu_enabled(False)
            self.assertTrue(ok_2, msg_2)
            self.assertEqual(msg_2, "")

    def test_http_explorer_context_menu_and_load_settings(self):
        hive = _FakeWinRegHive()
        wreg_mod = self._make_winreg_module(hive)
        app_dir = os.path.join(self.tmp_dir.name, "http_app")
        os.makedirs(app_dir, exist_ok=True)
        exe_path = os.path.join(app_dir, "MyServer-Beta.exe")
        with open(exe_path, "wb") as f:
            f.write(b"MZ")

        st_unauth, _, body_unauth = self._raw_http(
            "POST",
            "/api/settings/explorer_context_menu",
            payload={"enabled": True},
        )
        self.assertEqual(st_unauth, 401)
        self.assertIs(body_unauth.get("success"), False)

        auth_hdr = {"X-MyServer-Core-Token": core._CORE_AUTH_TOKEN}

        with patch.object(core.sys, "platform", "win32"), \
             patch.object(core, "winreg", wreg_mod), \
             patch.object(core, "get_gui_executable_path", return_value=exe_path):
            st_get0, _, load_get0 = self._raw_http("GET", "/api/load_settings", headers=auth_hdr)
            self.assertEqual(st_get0, 200)
            self.assertIs(load_get0.get("explorerContextMenuEnabled"), False)

            st_en, _, body_en = self._raw_http(
                "POST",
                "/api/settings/explorer_context_menu",
                payload={"enabled": True},
                headers=auth_hdr,
            )
            self.assertEqual(st_en, 200)
            self.assertTrue(body_en["success"])
            self.assertTrue(body_en["enabled"])

            st_get1, _, load_get1 = self._raw_http("GET", "/api/load_settings", headers=auth_hdr)
            self.assertEqual(st_get1, 200)
            self.assertIs(load_get1.get("explorerContextMenuEnabled"), True)

            st_post1, _, load_post1 = self._raw_http(
                "POST", "/api/load_settings", payload={}, headers=auth_hdr
            )
            self.assertEqual(st_post1, 200)
            self.assertIs(load_post1.get("explorerContextMenuEnabled"), True)

            st_dis, _, body_dis = self._raw_http(
                "POST",
                "/api/settings/explorer_context_menu",
                payload={"enabled": False},
                headers=auth_hdr,
            )
            self.assertEqual(st_dis, 200)
            self.assertTrue(body_dis["success"])
            self.assertFalse(body_dis["enabled"])

            st_get2, _, load_get2 = self._raw_http("GET", "/api/load_settings", headers=auth_hdr)
            self.assertEqual(st_get2, 200)
            self.assertIs(load_get2.get("explorerContextMenuEnabled"), False)

    def test_installer_iss_contains_explorer_verbs_and_matches_generator(self):
        import build_installer_package

        iss_path = os.path.join(REPO_ROOT, "installer.iss")
        with open(iss_path, "r", encoding="utf-8") as f:
            iss_text = f.read()

        self.assertEqual(
            iss_text,
            build_installer_package.render_installer_iss(
                build_installer_package.VERSION, build_installer_package.APP_NAME
            ),
        )
        self.assertIn('Name: "explorercontextmenu"', iss_text)
        self.assertIn("[Registry]", iss_text)
        for subkey in (
            r"Software\Classes\*\shell\MyServerShare",
            r"Software\Classes\*\shell\MyServerQuickShare",
            r"Software\Classes\Directory\shell\MyServerShare",
            r"Software\Classes\Directory\shell\MyServerQuickShare",
            r"Software\Classes\*\shell\MyServerHttpCopy",
            r"Software\Classes\Directory\shell\MyServerHttpCopy",
            r"Software\Classes\Directory\shell\MyServerHttpPaste",
            r"Software\Classes\Directory\Background\shell\MyServerHttpPaste",
        ):
            self.assertIn(f'Root: HKCU; Subkey: "{subkey}"', iss_text)
            self.assertIn(f'Root: HKCU; Subkey: "{subkey}\\command"', iss_text)
        self.assertIn('ValueName: "MultiSelectModel"; ValueData: "Single"', iss_text)
        self.assertIn("Flags: uninsdeletekey", iss_text)
        self.assertIn(
            r'Root: HKCU; Subkey: "Software\Classes\AppUserModelId\com.algithaproject.myserver.companion.beta"',
            iss_text,
        )
        self.assertIn('--share ""%1""', iss_text)
        self.assertIn('--quick-share ""%1""', iss_text)
        self.assertIn('--explorer-copy ""%1""', iss_text)
        self.assertIn('--explorer-paste ""%1""', iss_text)
        self.assertIn('--explorer-paste ""%V""', iss_text)


if __name__ == "__main__":
    unittest.main()

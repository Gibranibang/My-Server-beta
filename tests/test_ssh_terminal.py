import ctypes
import http.server
import json
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


class SshTerminalEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None

        cfg = config_manager.load_or_create_config()
        cfg["active_server_id"] = "srv_stimi"
        cfg["servers"] = [
            {
                "id": "srv_stimi",
                "name": "STIMI-Server",
                "active_connection": "c1",
                "connections": [{"id": "c1", "name": "LAN", "url": "http://192.168.10.50:80"}],
                "active_profile": "Admin",
                "profiles": ["Admin"],
                "credentials": {"Admin": {"username": "MyServerDesktopAdmin"}},
            }
        ]
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
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()

    def _post_ssh(self, payload):
        url = f"http://127.0.0.1:{self.port}/api/server/ssh_terminal"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(data)),
                "X-MyServer-Core-Token": core.get_core_auth_token(),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_explicit_ssh_user_overrides_profile_and_persists_per_server(self):
        with patch.object(core.subprocess, "Popen") as popen_mock:
            status, res = self._post_ssh({
                "serverId": "srv_stimi",
                "host": "192.168.10.50",
                "user": "algitha",
                "port": 22,
                "saveSshUser": True,
            })
        self.assertEqual(status, 200)
        self.assertTrue(res["success"])
        self.assertEqual(res["user"], "algitha")
        self.assertEqual(res["command"], "ssh algitha@192.168.10.50")
        popen_mock.assert_called_once()
        ps_cmd = popen_mock.call_args[0][0]
        self.assertIn("ssh algitha@192.168.10.50", ps_cmd[-1])

        config_manager._config_cache = None
        cfg = config_manager.load_or_create_config()
        self.assertEqual(cfg["servers"][0].get("ssh_user"), "algitha")

        # Subsequent call without explicit user prefers persisted ssh_user over profile username
        with patch.object(core.subprocess, "Popen") as popen_mock2:
            status2, res2 = self._post_ssh({
                "serverId": "srv_stimi",
                "host": "192.168.10.50",
                "port": 2222,
            })
        self.assertEqual(status2, 200)
        self.assertEqual(res2["user"], "algitha")
        self.assertEqual(res2["port"], 2222)
        self.assertEqual(res2["command"], "ssh -p 2222 algitha@192.168.10.50")
        popen_mock2.assert_called_once()

    def test_rejects_shell_injection_and_invalid_ports(self):
        with patch.object(core.subprocess, "Popen") as popen_mock:
            for bad_payload in [
                {"host": "192.168.10.50", "user": "root; calc.exe"},
                {"host": "192.168.10.50 && whoami", "user": "algitha"},
                {"host": "192.168.10.50", "user": "algitha", "port": "bad"},
                {"host": "192.168.10.50", "user": "algitha", "port": 70000},
            ]:
                status, res = self._post_ssh(bad_payload)
                self.assertEqual(status, 400, f"Expected 400 for {bad_payload}, got {status}: {res}")
                self.assertFalse(res.get("success", True))
        popen_mock.assert_not_called()

    def test_server_details_exposes_ssh_user(self):
        cfg = config_manager.load_or_create_config()
        cfg["servers"][0]["ssh_user"] = "zimaadmin"
        config_manager.save_config(cfg)

        details = core.get_server_details_data(cfg=cfg)
        self.assertEqual(details.get("sshUser"), "zimaadmin")
        self.assertEqual(details["servers"][0].get("sshUser"), "zimaadmin")


if __name__ == "__main__":
    unittest.main()

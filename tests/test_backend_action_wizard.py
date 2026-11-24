import ctypes
import http.server
import json
import logging
import os
import shlex
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
        if self.record.get("sftp_fail"):
            raise IOError("Simulated SFTP failure")
        self.record["sftp_puts"].append((local_path, remote_path))

    def close(self):
        return None


def _build_fake_paramiko(record, connect_hook=None):
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
                {
                    "host": host,
                    "port": port,
                    "username": username,
                    "password": password,
                }
            )
            if connect_hook is not None:
                connect_hook(host, port, username, password)
            if record.get("raise_auth_exc"):
                raise AuthenticationException("Authentication failed.")

        def open_sftp(self):
            return _FakeSftp(record)

        def exec_command(self, cmd, timeout=None):
            record["exec_cmds"].append(cmd)
            if "wc -c" in cmd:
                return (
                    _FakeStream(b""),
                    _FakeStream(b"2048\n", exit_status=0),
                    _FakeStream(b""),
                )
            if "install_zimaos.sh" in cmd and record.get("sudo_auth_fail"):
                return (
                    _FakeStream(b""),
                    _FakeStream(b"", exit_status=1),
                    _FakeStream(b"sudo: 1 incorrect password attempt\n"),
                )
            return (
                _FakeStream(b""),
                _FakeStream(b"Install OK\n", exit_status=0),
                _FakeStream(b""),
            )

        def close(self):
            record["closed"] = True

    fake_mod.AuthenticationException = AuthenticationException
    fake_mod.AutoAddPolicy = AutoAddPolicy
    fake_mod.SSHClient = SSHClient
    return fake_mod


class _CapturingLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(self.format(record))


class BackendActionWizardTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir_patch = patch.object(
            config_manager, "get_base_dir", return_value=self.tmp_dir.name
        )
        self.base_dir_patch.start()
        config_manager._config_cache = None

        cfg = config_manager.get_default_config()
        cfg["servers"] = [
            {
                "id": "srv_target",
                "name": "Target NAS",
                "connections": [
                    {"id": "conn_lan", "name": "LAN", "url": "http://192.168.1.50:80"}
                ],
                "credentials": {
                    "Admin": {
                        "username": "admin",
                        "password": config_manager.encrypt_credential("AdminPass!1"),
                    }
                },
                "profiles": ["Admin"],
                "active_profile": "Admin",
            }
        ]
        cfg["active_server_id"] = "srv_target"
        config_manager.save_config(cfg)

        self.log_handler = _CapturingLogHandler()
        logging.getLogger().addHandler(self.log_handler)

    def tearDown(self):
        logging.getLogger().removeHandler(self.log_handler)
        if hasattr(core, "_ACTIVE_BACKEND_DEPLOYS"):
            core._ACTIVE_BACKEND_DEPLOYS.clear()
        config_manager._config_cache = None
        self.base_dir_patch.stop()
        self.tmp_dir.cleanup()

    def test_source_github_bypasses_local_ota_and_sftp_and_validates_slug(self):
        bundle_zip = os.path.join(self.tmp_dir.name, "backend_ota.zip")
        bundle_tar = os.path.join(self.tmp_dir.name, "backend.tar.gz")
        with open(bundle_zip, "wb") as f:
            f.write(b"PK\x03\x04dummy")
        with open(bundle_tar, "wb") as f:
            f.write(b"\x1f\x8bdummy")

        cfg = config_manager.load_or_create_config()
        cfg["github_repo"] = "custom-org/custom-repo"
        config_manager.save_config(cfg)

        ssh_record = {"connect_calls": [], "sftp_puts": [], "exec_cmds": []}
        fake_paramiko = _build_fake_paramiko(ssh_record)

        def _fake_http(url, method="GET", timeout=2.0, retries=0):
            if url.endswith("/health"):
                return True, {"status": "ok", "version": "1.2.7"}, 200
            raise AssertionError(f"Unexpected HTTP call: {url}")

        with patch.dict(sys.modules, {"paramiko": fake_paramiko}), \
             patch.object(core, "_get_bundled_backend_packages", return_value=(bundle_zip, bundle_tar)), \
             patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"), \
             patch.object(core, "_backend_http_request", side_effect=_fake_http), \
             patch.object(core.urllib.request, "urlopen", side_effect=AssertionError("HTTP OTA urlopen must be bypassed when source=github")), \
             patch.object(core.time, "sleep", return_value=None):
            res = core.handle_remote_backend_action(
                {"action": "update", "source": "github", "serverId": "srv_target"}
            )

        self.assertIs(res.get("success"), True)
        self.assertEqual(len(ssh_record["sftp_puts"]), 0)
        expected_url = "https://github.com/custom-org/custom-repo/releases/latest/download/MyServer-Backend-ZimaOS.tar.gz"
        curl_cmds = [c for c in ssh_record["exec_cmds"] if "curl " in c]
        self.assertEqual(len(curl_cmds), 1)
        self.assertIn(shlex.quote(expected_url), curl_cmds[0])

        # Invalid github_repo slug rejected
        cfg["github_repo"] = "../evil/traversal"
        config_manager.save_config(cfg)
        with patch.dict(sys.modules, {"paramiko": fake_paramiko}):
            bad = core.handle_remote_backend_action(
                {"action": "install", "source": "github", "serverId": "srv_target"}
            )
        self.assertIs(bad.get("success"), False)
        self.assertIs(bad.get("validationError"), True)
        self.assertEqual(bad.get("stage"), "validation")

    def test_source_bundle_requires_local_bundle_and_disables_github_fallback(self):
        ssh_record = {"connect_calls": [], "sftp_puts": [], "exec_cmds": [], "sftp_fail": True}
        fake_paramiko = _build_fake_paramiko(ssh_record)

        # Missing bundle returns validationError before SSH
        with patch.dict(sys.modules, {"paramiko": fake_paramiko}), \
             patch.object(core, "_get_bundled_backend_packages", return_value=(None, None)), \
             patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"):
            res = core.handle_remote_backend_action(
                {"action": "install", "source": "bundle", "serverId": "srv_target"}
            )
        self.assertIs(res.get("success"), False)
        self.assertIs(res.get("validationError"), True)
        self.assertEqual(res.get("stage"), "validation")
        self.assertEqual(len(ssh_record["connect_calls"]), 0)

        # Present bundle whose SFTP upload fails must NOT curl GitHub
        bundle_tar = os.path.join(self.tmp_dir.name, "backend.tar.gz")
        with open(bundle_tar, "wb") as f:
            f.write(b"\x1f\x8bdummy")
        with patch.dict(sys.modules, {"paramiko": fake_paramiko}), \
             patch.object(core, "_get_bundled_backend_packages", return_value=(None, bundle_tar)), \
             patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"):
            res_sftp = core.handle_remote_backend_action(
                {"action": "install", "source": "bundle", "serverId": "srv_target"}
            )
        self.assertIs(res_sftp.get("success"), False)
        self.assertFalse(any("curl " in c for c in ssh_record["exec_cmds"]))

    def test_ssh_overrides_port_validation_shlex_quoting_and_zero_password_leak(self):
        ssh_record = {"connect_calls": [], "sftp_puts": [], "exec_cmds": []}
        fake_paramiko = _build_fake_paramiko(ssh_record)

        for bad_port in (0, -5, 65536, "not_int", True):
            with patch.dict(sys.modules, {"paramiko": fake_paramiko}):
                res_bad = core.handle_remote_backend_action(
                    {
                        "action": "install",
                        "source": "github",
                        "serverId": "srv_target",
                        "sshPort": bad_port,
                    }
                )
            self.assertIs(res_bad.get("success"), False)
            self.assertIs(res_bad.get("validationError"), True)
            self.assertEqual(res_bad.get("stage"), "validation")

        secret_ssh_pw = "Ssh'Secret$!99"
        injected_user = "my;admin$(id)"
        with patch.dict(sys.modules, {"paramiko": fake_paramiko}), \
             patch.object(core, "_get_bundled_backend_packages", return_value=(None, None)), \
             patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"), \
             patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.2.7"}, 200)), \
             patch.object(core.time, "sleep", return_value=None):
            res_ok = core.handle_remote_backend_action(
                {
                    "action": "install",
                    "source": "github",
                    "serverId": "srv_target",
                    "sshHost": "192.168.77.88",
                    "sshPort": 2222,
                    "sshUser": injected_user,
                    "sshPassword": secret_ssh_pw,
                }
            )

        self.assertIs(res_ok.get("success"), True)
        self.assertEqual(len(ssh_record["connect_calls"]), 1)
        c0 = ssh_record["connect_calls"][0]
        self.assertEqual(c0["host"], "192.168.77.88")
        self.assertEqual(c0["port"], 2222)
        self.assertEqual(c0["username"], injected_user)
        self.assertEqual(c0["password"], secret_ssh_pw)

        all_cmds = "\n".join(ssh_record["exec_cmds"])
        self.assertNotIn("$(id)", all_cmds)
        self.assertIn(shlex.quote(secret_ssh_pw), all_cmds)

        # Password must never appear in response payload or logs
        self.assertNotIn(secret_ssh_pw, json.dumps(res_ok))
        self.assertNotIn(secret_ssh_pw, "\n".join(self.log_handler.messages))

    def test_ssh_auth_failure_and_sudo_denied_return_structured_auth_failed(self):
        # Case A: paramiko.AuthenticationException on SSH connect
        rec_a = {"connect_calls": [], "sftp_puts": [], "exec_cmds": [], "raise_auth_exc": True}
        fake_a = _build_fake_paramiko(rec_a)
        secret_pw = "WrongSshPw!123"
        with patch.dict(sys.modules, {"paramiko": fake_a}), \
             patch.object(core, "_get_bundled_backend_packages", return_value=(None, None)), \
             patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"):
            res_a = core.handle_remote_backend_action(
                {
                    "action": "install",
                    "source": "github",
                    "serverId": "srv_target",
                    "sshHost": "10.0.0.5",
                    "sshPassword": secret_pw,
                }
            )
        self.assertIs(res_a.get("success"), False)
        self.assertIs(res_a.get("authFailed"), True)
        self.assertEqual(res_a.get("stage"), "ssh_auth")
        self.assertNotIn(secret_pw, json.dumps(res_a))

        # Case B: sudo -S stderr denial
        rec_b = {"connect_calls": [], "sftp_puts": [], "exec_cmds": [], "sudo_auth_fail": True}
        fake_b = _build_fake_paramiko(rec_b)
        with patch.dict(sys.modules, {"paramiko": fake_b}), \
             patch.object(core, "_get_bundled_backend_packages", return_value=(None, None)), \
             patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"), \
             patch.object(core, "_backend_http_request", return_value=(False, None, 0)), \
             patch.object(core.time, "sleep", return_value=None):
            res_b = core.handle_remote_backend_action(
                {
                    "action": "install",
                    "source": "github",
                    "serverId": "srv_target",
                    "sshHost": "10.0.0.5",
                    "sshPassword": secret_pw,
                }
            )
        self.assertIs(res_b.get("success"), False)
        self.assertIs(res_b.get("authFailed"), True)
        self.assertEqual(res_b.get("stage"), "ssh_auth")
        self.assertNotIn(secret_pw, json.dumps(res_b))

    def test_per_server_deploy_lock_returns_busy_and_releases_on_completion(self):
        entered = threading.Event()
        release = threading.Event()

        def _blocking_connect(*_args, **_kwargs):
            entered.set()
            release.wait(timeout=5)
            raise RuntimeError("abort first run to verify finally release")

        rec = {"connect_calls": [], "sftp_puts": [], "exec_cmds": []}
        fake_paramiko = _build_fake_paramiko(rec, connect_hook=_blocking_connect)
        results = {}

        def _worker():
            results["first"] = core.handle_remote_backend_action(
                {"action": "install", "source": "github", "serverId": "srv_target", "sshHost": "10.0.0.5"}
            )

        with patch.dict(sys.modules, {"paramiko": fake_paramiko}), \
             patch.object(core, "_get_bundled_backend_packages", return_value=(None, None)), \
             patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"):
            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            self.assertTrue(entered.wait(timeout=3))

            busy_res = core.handle_remote_backend_action(
                {"action": "install", "source": "github", "serverId": "srv_target", "sshHost": "10.0.0.5"}
            )
            self.assertIs(busy_res.get("success"), False)
            self.assertIs(busy_res.get("busy"), True)
            self.assertEqual(busy_res.get("stage"), "locked")

            release.set()
            t.join(timeout=3)

        # Lock must be released in finally even when Thread 1 errored
        rec2 = {"connect_calls": [], "sftp_puts": [], "exec_cmds": []}
        fake_ok = _build_fake_paramiko(rec2)
        with patch.dict(sys.modules, {"paramiko": fake_ok}), \
             patch.object(core, "_get_bundled_backend_packages", return_value=(None, None)), \
             patch.object(core, "_get_bundled_backend_version", return_value="1.2.7"), \
             patch.object(core, "_backend_http_request", return_value=(True, {"status": "ok", "version": "1.2.7"}, 200)), \
             patch.object(core.time, "sleep", return_value=None):
            third_res = core.handle_remote_backend_action(
                {"action": "install", "source": "github", "serverId": "srv_target", "sshHost": "10.0.0.5"}
            )
        self.assertIs(third_res.get("success"), True)

    def test_http_backend_action_status_code_mapping(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), core.CoreApiHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            def _post_action():
                url = f"http://127.0.0.1:{srv.server_port}/api/server/backend_action"
                data = json.dumps({"action": "install"}).encode("utf-8")
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
                except urllib.error.HTTPError as err:
                    return err.code, json.loads(err.read().decode("utf-8"))

            cases = [
                ({"success": True, "status": "ok"}, 200),
                ({"success": False, "busy": True, "stage": "locked"}, 409),
                ({"success": False, "authFailed": True, "stage": "ssh_auth"}, 401),
                ({"success": False, "validationError": True, "stage": "validation"}, 400),
                ({"success": False, "status": "error", "message": "boom"}, 500),
            ]
            for payload, expected_code in cases:
                with patch.object(core, "handle_remote_backend_action", return_value=payload):
                    code, body = _post_action()
                self.assertEqual(code, expected_code)
                self.assertEqual(body, payload)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()

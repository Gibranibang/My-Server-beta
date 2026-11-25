import ctypes
import hashlib
import http.server
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
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
BACKEND_ROOT = os.path.abspath(os.path.join(REPO_ROOT, "..", "..", "MyServer Backend by algitha"))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import smb_mount_manager  # noqa: E402
import explorer_tab_reader  # noqa: E402
import http_transfer_manager  # noqa: E402
from http_transfer_manager import HttpTransferManager, _safe_local_join  # noqa: E402


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(262144):
            h.update(chunk)
    return h.hexdigest()


class TestSmbTargetedRefresh(unittest.TestCase):
    def test_notify_local_folder_updated_calls_shcne_updatedir_only(self):
        calls = []

        class _FakeShell32:
            def SHChangeNotify(self, event_id, flags, item1, item2):
                calls.append((event_id, flags, getattr(item1, "value", item1), item2))

        fake_windll = types.SimpleNamespace(shell32=_FakeShell32())
        with patch.object(sys, "platform", "win32"), patch.object(ctypes, "windll", fake_windll, create=True):
            ok = smb_mount_manager.notify_local_folder_updated("/tmp/test_folder")

        self.assertTrue(ok)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], smb_mount_manager.SHCNE_UPDATEDIR)
        self.assertEqual(calls[0][0], 0x00001000)
        self.assertEqual(calls[0][1], smb_mount_manager.SHCNF_PATHW)
        self.assertNotEqual(calls[0][0], 0x08000000)

    def test_notify_local_folder_updated_returns_false_on_non_windows(self):
        with patch.object(sys, "platform", "linux"):
            self.assertFalse(smb_mount_manager.notify_local_folder_updated("/tmp/test_folder"))
        self.assertFalse(smb_mount_manager.notify_local_folder_updated(""))


class TestExplorerTabReader(unittest.TestCase):
    def setUp(self):
        with explorer_tab_reader._IN_FLIGHT_LOCK:
            explorer_tab_reader._in_flight_com_threads = 0

    def tearDown(self):
        with explorer_tab_reader._IN_FLIGHT_LOCK:
            explorer_tab_reader._in_flight_com_threads = 0

    def test_non_windows_returns_non_windows_error(self):
        with patch.object(sys, "platform", "linux"):
            res = explorer_tab_reader.read_active_explorer_tab(1234, 5678)
        self.assertFalse(res["ok"])
        self.assertFalse(res["timed_out"])
        self.assertEqual(res["error"], "NON_WINDOWS")

    def test_timeout_and_com_busy_limit(self):
        release_event = threading.Event()

        def _hung_worker(fg_hwnd, top_tab_hwnd, timeout_ms, result_box, done_event, on_finish):
            def _bg():
                release_event.wait(2.0)
                on_finish()
                done_event.set()

            threading.Thread(target=_bg, daemon=True).start()

        try:
            with patch.object(sys, "platform", "win32"), patch.object(
                explorer_tab_reader, "_spawn_sta_com_worker", side_effect=_hung_worker
            ):
                for _ in range(3):
                    r = explorer_tab_reader.read_active_explorer_tab(100, 200, timeout_ms=30)
                    self.assertFalse(r["ok"])
                    self.assertTrue(r["timed_out"])
                    self.assertEqual(r["error"], "TIMEOUT")

                busy_res = explorer_tab_reader.read_active_explorer_tab(100, 200, timeout_ms=30)
                self.assertFalse(busy_res["ok"])
                self.assertFalse(busy_res["timed_out"])
                self.assertEqual(busy_res["error"], "COM_BUSY")
        finally:
            release_event.set()

    def test_win11_short_circuit_skips_inactive_tab_document(self):
        class _BadTab:
            FullName = r"C:\Windows\explorer.exe"
            HWND = 100

            @property
            def Document(self):
                raise AssertionError("Inactive tab .Document must NOT be accessed!")

        class _Item:
            def __init__(self, p):
                self.Path = p

        class _ActiveTab:
            FullName = r"C:\Windows\explorer.exe"
            HWND = 100
            Document = types.SimpleNamespace(
                Folder=types.SimpleNamespace(Self=types.SimpleNamespace(Path=r"C:\Users\alice\Docs")),
                SelectedItems=lambda: [_Item(r"C:\Users\alice\Docs\a.txt")],
            )

        bad_tab = _BadTab()
        active_tab = _ActiveTab()
        tab_map = {id(bad_tab): 101, id(active_tab): 102}

        res = explorer_tab_reader._extract_active_tab_from_shell_windows(
            [bad_tab, active_tab],
            fg_hwnd=100,
            top_tab_hwnd=102,
            get_tab_hwnd_fn=lambda w: tab_map[id(w)],
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["tab_hwnd"], 102)
        self.assertEqual(res["folder_path"], r"C:\Users\alice\Docs")
        self.assertEqual(res["selected_items"], [r"C:\Users\alice\Docs\a.txt"])


class TestHttpTransferCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_root = tempfile.TemporaryDirectory()
        cls.storage_dir = os.path.join(cls.tmp_root.name, "storage")
        cls.data_dir = os.path.join(cls.tmp_root.name, "data")
        cls.temp_dir = os.path.join(cls.tmp_root.name, "temp_chunks")
        cls.db_path = os.path.join(cls.data_dir, "myserver_test.db")
        os.makedirs(cls.storage_dir, exist_ok=True)
        os.makedirs(cls.data_dir, exist_ok=True)
        os.makedirs(cls.temp_dir, exist_ok=True)

        spec = importlib.util.spec_from_file_location(
            "myserver_backend_dev_server_p13",
            os.path.join(BACKEND_ROOT, "dev_server.py"),
        )
        cls.dev_server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.dev_server)

        cls.dev_server.DATA_DIR = cls.data_dir
        cls.dev_server.STORAGE_DIR = cls.storage_dir
        cls.dev_server.TEMP_DIR = cls.temp_dir
        cls.dev_server.DB_PATH = cls.db_path
        cls.dev_server.init_db(cls.db_path)

        cls.admin_rec = cls.dev_server.create_or_update_user(
            "admin", "AdminPass!1", role="admin", db_path=cls.db_path
        )
        cls.alice_rec = cls.dev_server.create_or_update_user(
            "alice", "AlicePass!1", role="user", db_path=cls.db_path
        )
        cls.bob_rec = cls.dev_server.create_or_update_user(
            "bob", "BobPass!1", role="user", db_path=cls.db_path
        )

        cls.admin_token = cls.dev_server.create_access_token("admin", int(cls.admin_rec["id"]), role="admin")
        cls.alice_token = cls.dev_server.create_access_token("alice", int(cls.alice_rec["id"]), role="user")
        cls.bob_token = cls.dev_server.create_access_token("bob", int(cls.bob_rec["id"]), role="user")

        # Create DiskA with Proj and SharedViewer
        os.makedirs(os.path.join(cls.storage_dir, "DiskA", "Proj"), exist_ok=True)
        os.makedirs(os.path.join(cls.storage_dir, "DiskA", "ViewerDir"), exist_ok=True)
        os.makedirs(os.path.join(cls.storage_dir, "DiskA", "AdminWork"), exist_ok=True)

        with open(os.path.join(cls.storage_dir, "DiskA", "Proj", "catatan 03 — coba.txt"), "wb") as f:
            f.write("Halo Unicode Phase 13 — OK!".encode("utf-8"))

        # Grant alice editor on DiskA/Proj and bob viewer on DiskA/ViewerDir + DiskA/Proj
        cls.dev_server.upsert_internal_share(
            int(cls.admin_rec["id"]), "admin", "DiskA/Proj", True, int(cls.alice_rec["id"]), "alice", role="editor", db_path=cls.db_path
        )
        cls.dev_server.upsert_internal_share(
            int(cls.admin_rec["id"]), "admin", "DiskA/Proj", True, int(cls.bob_rec["id"]), "bob", role="viewer", db_path=cls.db_path
        )
        cls.dev_server.upsert_internal_share(
            int(cls.admin_rec["id"]), "admin", "DiskA/ViewerDir", True, int(cls.bob_rec["id"]), "bob", role="viewer", db_path=cls.db_path
        )

        cls.httpd = cls.dev_server.ThreadedHTTPServer(("127.0.0.1", 0), cls.dev_server.NativeBackupHandler)
        cls.port = cls.httpd.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.srv_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.srv_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp_root.cleanup()

    def _make_manager(self, token: str, notified_dirs=None, resolve_fn=None) -> HttpTransferManager:
        notified = notified_dirs if notified_dirs is not None else []
        return HttpTransferManager(
            resolve_smb_target_fn=resolve_fn,
            get_backend_session_fn=lambda sid="": ("srv_1", "TestNAS", self.base_url, token),
            notify_local_dir_fn=lambda d: (notified.append(d) or True),
        )

    def test_upload_nested_folder_chunked_and_editor_created_path(self):
        mgr = self._make_manager(self.admin_token)
        with tempfile.TemporaryDirectory() as local_src:
            root_folder = os.path.join(local_src, "BundleA")
            empty_sub = os.path.join(root_folder, "EmptySub")
            os.makedirs(empty_sub, exist_ok=True)
            small_path = os.path.join(root_folder, "small.txt")
            big_path = os.path.join(root_folder, "big.bin")
            small_bytes = b"hello small file"
            big_bytes = os.urandom(1200 * 1024)  # 1.2 MB > 512 KB
            with open(small_path, "wb") as f:
                f.write(small_bytes)
            with open(big_path, "wb") as f:
                f.write(big_bytes)

            mgr.set_clipboard_local([root_folder])
            res = mgr.dispatch_paste(dest_rel="DiskA/AdminWork", server_id="srv_1")
            self.assertTrue(res["success"])
            status = mgr.wait_for_job(res["job_id"], timeout=30.0)
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["completed_files"], 2)

            srv_empty = os.path.join(self.storage_dir, "DiskA", "AdminWork", "BundleA", "EmptySub")
            srv_small = os.path.join(self.storage_dir, "DiskA", "AdminWork", "BundleA", "small.txt")
            srv_big = os.path.join(self.storage_dir, "DiskA", "AdminWork", "BundleA", "big.bin")
            self.assertTrue(os.path.isdir(srv_empty))
            self.assertEqual(_sha256_file(srv_small), _sha256_bytes(small_bytes))
            self.assertEqual(_sha256_file(srv_big), _sha256_bytes(big_bytes))

        # Test editor role follows created_path on colliding folder
        alice_mgr = self._make_manager(self.alice_token)
        os.makedirs(os.path.join(self.storage_dir, "DiskA", "Proj", "EditorDir"), exist_ok=True)
        with tempfile.TemporaryDirectory() as alice_src:
            ed_dir = os.path.join(alice_src, "EditorDir")
            os.makedirs(ed_dir, exist_ok=True)
            with open(os.path.join(ed_dir, "note.txt"), "wb") as f:
                f.write(b"editor safe")
            alice_mgr.set_clipboard_local([ed_dir])
            r2 = alice_mgr.dispatch_paste(dest_rel="DiskA/Proj", server_id="srv_1")
            jid2 = r2["job_id"]
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and alice_mgr.get_status(jid2)["status"] != "awaiting_conflict":
                time.sleep(0.02)
            if alice_mgr.get_status(jid2)["status"] == "awaiting_conflict":
                alice_mgr.resolve_conflict(jid2, "overwrite")
            st2 = alice_mgr.wait_for_job(jid2, timeout=20.0)
            self.assertEqual(st2["status"], "completed")
            self.assertTrue(os.path.isfile(os.path.join(self.storage_dir, "DiskA", "Proj", "EditorDir (1)", "note.txt")))

    def test_download_unicode_and_shared_root_fallback_probe(self):
        notified = []
        bob_mgr = self._make_manager(self.bob_token, notified_dirs=notified)

        # Case 1: is_dir=True on Shared with Me root (parent DiskA is 403 for bob)
        with tempfile.TemporaryDirectory() as local_dest1:
            bob_mgr.set_clipboard_server(
                "srv_1",
                "TestNAS",
                [{"rel_path": "DiskA/Proj", "name": "Proj", "is_dir": True}],
            )
            r1 = bob_mgr.dispatch_paste(dest_path=local_dest1)
            st1 = bob_mgr.wait_for_job(r1["job_id"], timeout=20.0)
            self.assertEqual(st1["status"], "completed")
            dl_file1 = os.path.join(local_dest1, "Proj", "catatan 03 — coba.txt")
            self.assertTrue(os.path.isfile(dl_file1))
            self.assertEqual(
                _sha256_file(dl_file1),
                _sha256_file(os.path.join(self.storage_dir, "DiskA", "Proj", "catatan 03 — coba.txt")),
            )
            self.assertIn(os.path.realpath(local_dest1), [os.path.realpath(x) for x in notified])

        # Case 2: is_dir=None fallback probe directly to /browse-files?path=DiskA/Proj
        with tempfile.TemporaryDirectory() as local_dest2:
            bob_mgr.set_clipboard_server(
                "srv_1",
                "TestNAS",
                [{"rel_path": "DiskA/Proj", "name": "Proj", "is_dir": None}],
            )
            r2 = bob_mgr.dispatch_paste(dest_path=local_dest2)
            st2 = bob_mgr.wait_for_job(r2["job_id"], timeout=20.0)
            self.assertEqual(st2["status"], "completed")
            self.assertTrue(os.path.isfile(os.path.join(local_dest2, "Proj", "catatan 03 — coba.txt")))

    def test_traversal_guard_rejects_dotdot(self):
        with tempfile.TemporaryDirectory() as dest_dir:
            with self.assertRaises(ValueError):
                _safe_local_join(dest_dir, "..", "evil.txt")
            with self.assertRaises(ValueError):
                _safe_local_join(dest_dir, "../evil.txt")

        mgr = self._make_manager(self.admin_token)
        with tempfile.TemporaryDirectory() as dest_dir:
            mgr.set_clipboard_server(
                "srv_1",
                "TestNAS",
                [{"rel_path": "../evil.txt", "name": "../evil.txt", "is_dir": False}],
            )
            r = mgr.dispatch_paste(dest_path=dest_dir)
            st = mgr.wait_for_job(r["job_id"], timeout=10.0)
            self.assertEqual(st["status"], "failed")
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(dest_dir), "evil.txt")))

    def test_conflict_resolution_overwrite_rename_skip_and_apply_to_all(self):
        mgr = self._make_manager(self.admin_token)
        with open(os.path.join(self.storage_dir, "DiskA", "AdminWork", "c1.txt"), "wb") as f:
            f.write(b"server-c1")
        with open(os.path.join(self.storage_dir, "DiskA", "AdminWork", "c2.txt"), "wb") as f:
            f.write(b"server-c2")

        with tempfile.TemporaryDirectory() as local_dest:
            with open(os.path.join(local_dest, "c1.txt"), "wb") as f:
                f.write(b"local-old-1")
            with open(os.path.join(local_dest, "c2.txt"), "wb") as f:
                f.write(b"local-old-2")

            mgr.set_clipboard_server(
                "srv_1",
                "TestNAS",
                [
                    {"rel_path": "DiskA/AdminWork/c1.txt", "name": "c1.txt", "is_dir": False},
                    {"rel_path": "DiskA/AdminWork/c2.txt", "name": "c2.txt", "is_dir": False},
                ],
            )
            res = mgr.dispatch_paste(dest_path=local_dest)
            jid = res["job_id"]

            # Wait for first conflict
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                st = mgr.get_status(jid)
                if st["status"] == "awaiting_conflict":
                    break
                time.sleep(0.02)
            self.assertEqual(mgr.get_status(jid)["status"], "awaiting_conflict")
            mgr.resolve_conflict(jid, "rename", apply_to_all=True)

            final_st = mgr.wait_for_job(jid, timeout=15.0)
            self.assertEqual(final_st["status"], "completed")
            self.assertTrue(os.path.isfile(os.path.join(local_dest, "c1 (1).txt")))
            self.assertTrue(os.path.isfile(os.path.join(local_dest, "c2 (1).txt")))

            # Verify skip + overwrite
            mgr.set_clipboard_server(
                "srv_1",
                "TestNAS",
                [{"rel_path": "DiskA/AdminWork/c1.txt", "name": "c1.txt", "is_dir": False}],
            )
            r_skip = mgr.dispatch_paste(dest_path=local_dest)
            jid_skip = r_skip["job_id"]
            while mgr.get_status(jid_skip)["status"] != "awaiting_conflict":
                time.sleep(0.02)
            mgr.resolve_conflict(jid_skip, "skip", apply_to_all=False)
            st_skip = mgr.wait_for_job(jid_skip, timeout=10.0)
            self.assertEqual(st_skip["skipped_files"], 1)

            mgr.set_clipboard_server(
                "srv_1",
                "TestNAS",
                [{"rel_path": "DiskA/AdminWork/c1.txt", "name": "c1.txt", "is_dir": False}],
            )
            r_ow = mgr.dispatch_paste(dest_path=local_dest)
            jid_ow = r_ow["job_id"]
            while mgr.get_status(jid_ow)["status"] != "awaiting_conflict":
                time.sleep(0.02)
            mgr.resolve_conflict(jid_ow, "overwrite", apply_to_all=False)
            mgr.wait_for_job(jid_ow, timeout=10.0)
            with open(os.path.join(local_dest, "c1.txt"), "rb") as f:
                self.assertEqual(f.read(), b"server-c1")

    def test_pause_resume_and_cancel_cleans_part_files(self):
        big_srv = os.path.join(self.storage_dir, "DiskA", "AdminWork", "stream_cancel.bin")
        with open(big_srv, "wb") as f:
            f.write(os.urandom(900 * 1024))

        mgr = self._make_manager(self.admin_token)
        with tempfile.TemporaryDirectory() as local_dest:
            mgr.set_clipboard_server(
                "srv_1",
                "TestNAS",
                [{"rel_path": "DiskA/AdminWork/stream_cancel.bin", "name": "stream_cancel.bin", "is_dir": False}],
            )
            r = mgr.dispatch_paste(dest_path=local_dest)
            jid = r["job_id"]
            mgr.pause_job(jid)
            self.assertIn(mgr.get_status(jid)["status"], ("paused", "completed"))
            mgr.resume_job(jid)
            mgr.cancel_job(jid)
            st = mgr.wait_for_job(jid, timeout=10.0)
            self.assertEqual(st["status"], "cancelled")
            leftovers = [fn for fn in os.listdir(local_dest) if ".myserver-part." in fn]
            self.assertEqual(leftovers, [])

    def test_hybrid_dispatcher_server_copy_quick_picker_and_viewer_browse(self):
        with open(os.path.join(self.storage_dir, "DiskA", "AdminWork", "copy_me.txt"), "wb") as f:
            f.write(b"server-copy-payload")

        def _fake_resolve(raw_p):
            if str(raw_p).startswith("Z:\\"):
                return (True, {"server_id": "srv_1", "server_name": "TestNAS", "canonical_rel": "DiskA/AdminWork"})
            return (False, {"code": "LOCAL_DRIVE"})

        mgr = self._make_manager(self.admin_token, resolve_fn=_fake_resolve)
        # Z:\ -> Z:\ copy
        mgr.set_clipboard_server("srv_1", "TestNAS", [{"rel_path": "DiskA/AdminWork/copy_me.txt", "is_dir": False}])
        r_copy = mgr.dispatch_paste(dest_path=r"Z:\AdminWork")
        self.assertEqual(r_copy["direction"], "server_copy")
        jid_copy = r_copy["job_id"]
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and mgr.get_status(jid_copy)["status"] != "awaiting_conflict":
            time.sleep(0.02)
        if mgr.get_status(jid_copy)["status"] == "awaiting_conflict":
            mgr.resolve_conflict(jid_copy, "rename")
        st_copy = mgr.wait_for_job(jid_copy, timeout=10.0)
        self.assertEqual(st_copy["status"], "completed")

        # Local -> non-SMB opens Quick Picker without os.path.exists on SMB
        with tempfile.TemporaryDirectory() as src_dir:
            fp = os.path.join(src_dir, "local.txt")
            with open(fp, "wb") as f:
                f.write(b"x")
            mgr.set_clipboard_local([fp])
            r_qp = mgr.dispatch_paste(dest_path=r"C:\Users\alice\Desktop")
            self.assertEqual(r_qp["ui_action"], "open_transfer_window")
            self.assertEqual(r_qp["mode"], "quick_picker")

        # Viewer browse_directory returns writable=False
        bob_mgr = self._make_manager(self.bob_token)
        b_res = bob_mgr.browse_directory(path="DiskA/ViewerDir", source="shared")
        self.assertTrue(b_res["ok"])
        self.assertEqual(b_res["effective_role"], "viewer")
        self.assertFalse(b_res["writable"])


class TestCoreApiTransferIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import config_manager
        import myserver_core_service as core

        cls.config_manager = config_manager
        cls.core = core
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.base_dir_patch = patch.object(config_manager, "get_base_dir", return_value=cls.tmp_dir.name)
        cls.base_dir_patch.start()
        config_manager._config_cache = None
        cfg = config_manager.get_default_config()
        cfg["language"] = "en"
        cfg["servers"] = [
            {
                "id": "srv_1",
                "name": "TestNAS",
                "host": "192.168.1.50",
                "username": "admin_zima",
                "smb_source": "backend",
                "backend_smb_auth": {"username": "alice", "password": "secret", "access_token": "tok_alice"},
            }
        ]
        cfg["active_server_id"] = "srv_1"
        config_manager.save_config(cfg)

        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), core.CoreApiHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.base_dir_patch.stop()
        cls.config_manager._config_cache = None
        cls.tmp_dir.cleanup()

    def setUp(self):
        self.core._transfer_manager.clear_clipboard()

    def _raw_http(self, method, path, payload=None, headers=None):
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5.0)
        hdrs = dict(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=body, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        conn.close()
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"raw": raw}
        return resp.status, data

    def test_requires_core_auth_token_on_all_transfer_endpoints(self):
        for ep in (
            "/api/transfer/copy",
            "/api/transfer/paste",
            "/api/transfer/status",
            "/api/transfer/browse",
            "/api/transfer/resolve_conflict",
            "/api/transfer/pause",
            "/api/transfer/resume",
            "/api/transfer/cancel",
            "/api/transfer/clear",
            "/api/transfer/clipboard/get",
            "/api/transfer/clipboard/clear",
            "/api/settings/explorer_hotkey",
        ):
            st, data = self._raw_http("POST", ep, payload={})
            self.assertEqual(st, 401, f"Expected 401 without token for POST {ep}")
            self.assertIs(data.get("success"), False)

        for ep in ("/api/transfer/status", "/api/transfer/clipboard/get"):
            st, _ = self._raw_http("GET", ep)
            self.assertEqual(st, 401, f"Expected 401 without token for GET {ep}")

    def test_unified_copy_paste_status_controls_and_hotkey_setting(self):
        auth = {"X-MyServer-Core-Token": self.core._CORE_AUTH_TOKEN}

        # 1. Companion copy preserves is_dir and appears on POST + GET /api/transfer/clipboard/get
        with patch.object(self.core, "_show_windows_toast", return_value=True):
            st, res = self._raw_http(
                "POST",
                "/api/transfer/copy",
                payload={
                    "source": "companion",
                    "server_id": "srv_1",
                    "items": [
                        {"relative_path": "DiskA/Folder1", "name": "Folder1", "is_dir": True, "size": 0},
                        {"relative_path": "DiskA/doc.txt", "name": "doc.txt", "is_dir": False, "size": 12},
                    ],
                },
                headers=auth,
            )
        self.assertEqual(st, 200)
        self.assertTrue(res["success"])
        self.assertEqual(res["clipboard"]["kind"], "server")
        self.assertIs(res["clipboard"]["items"][0]["is_dir"], True)

        st_p, clip_p = self._raw_http("POST", "/api/transfer/clipboard/get", payload={}, headers=auth)
        st_g, clip_g = self._raw_http("GET", "/api/transfer/clipboard/get", headers=auth)
        self.assertEqual(st_p, 200)
        self.assertEqual(st_g, 200)
        self.assertEqual(clip_p["kind"], "server")
        self.assertEqual(clip_g["kind"], "server")
        self.assertEqual(len(clip_g["items"]), 2)

        # 2. Hotkey copy timeout & empty selection & local path
        with patch.object(
            self.core.explorer_tab_reader,
            "read_active_explorer_tab",
            return_value={"ok": False, "timed_out": True, "error": "TIMEOUT"},
        ), patch.object(self.core, "_show_windows_toast", return_value=True):
            st_to, res_to = self._raw_http(
                "POST",
                "/api/transfer/copy",
                payload={"source": "hotkey", "fg_hwnd": 11, "top_tab_hwnd": 22},
                headers=auth,
            )
        self.assertEqual(st_to, 200)
        self.assertFalse(res_to["success"])
        self.assertEqual(res_to["code"], "EXPLORER_TIMEOUT")

        with patch.object(
            self.core.explorer_tab_reader,
            "read_active_explorer_tab",
            return_value={"ok": True, "timed_out": False, "folder_path": r"C:\Local", "selected_items": []},
        ), patch.object(self.core, "_show_windows_toast", return_value=True):
            st_emp, res_emp = self._raw_http(
                "POST",
                "/api/transfer/copy",
                payload={"source": "hotkey", "fg_hwnd": 11, "top_tab_hwnd": 22},
                headers=auth,
            )
        self.assertEqual(st_emp, 200)
        self.assertEqual(res_emp["code"], "EMPTY_SELECTION")

        # 3. Context menu local copy + Hotkey paste timeout -> quick_picker
        with patch.object(self.core, "_show_windows_toast", return_value=True):
            st_cm, res_cm = self._raw_http(
                "POST",
                "/api/transfer/copy",
                payload={"source": "context_menu", "paths": [r"C:\Users\alice\local_doc.txt"]},
                headers=auth,
            )
        self.assertEqual(st_cm, 200)
        self.assertTrue(res_cm["success"])
        self.assertEqual(res_cm["clipboard"]["kind"], "local")

        with patch.object(
            self.core.explorer_tab_reader,
            "read_active_explorer_tab",
            return_value={"ok": False, "timed_out": True, "error": "TIMEOUT"},
        ):
            st_hp, res_hp = self._raw_http(
                "POST",
                "/api/transfer/paste",
                payload={"source": "hotkey", "fg_hwnd": 11, "top_tab_hwnd": 22},
                headers=auth,
            )
        self.assertEqual(st_hp, 200)
        self.assertEqual(res_hp["ui_action"], "open_transfer_window")
        self.assertEqual(res_hp["mode"], "quick_picker")

        # 4. Context menu & Quick Picker paste delegate to _transfer_manager.dispatch_paste
        with patch.object(
            self.core._transfer_manager,
            "dispatch_paste",
            return_value={"success": True, "ui_action": "open_transfer_window", "mode": "progress", "job_id": "xfer_1"},
        ) as mock_disp:
            st_cmp, res_cmp = self._raw_http(
                "POST",
                "/api/transfer/paste",
                payload={"source": "context_menu", "dest_path": r"Z:\Work"},
                headers=auth,
            )
            self.assertEqual(st_cmp, 200)
            self.assertEqual(res_cmp["job_id"], "xfer_1")
            mock_disp.assert_called_with(dest_path=r"Z:\Work")

            st_qp, res_qp = self._raw_http(
                "POST",
                "/api/transfer/paste",
                payload={"source": "quick_picker", "serverId": "srv_1", "destRel": "DiskA/Target"},
                headers=auth,
            )
            self.assertEqual(st_qp, 200)
            self.assertEqual(res_qp["job_id"], "xfer_1")
            mock_disp.assert_called_with(server_id="srv_1", dest_rel="DiskA/Target")

        # 5. Status (POST & GET), browse, conflict, pause/resume/cancel/clear, clipboard/clear
        st_sp, body_sp = self._raw_http("POST", "/api/transfer/status", payload={}, headers=auth)
        st_sg, body_sg = self._raw_http("GET", "/api/transfer/status", headers=auth)
        self.assertEqual(st_sp, 200)
        self.assertEqual(st_sg, 200)
        self.assertTrue(body_sp["success"])
        self.assertTrue(body_sg["success"])

        with patch.object(
            self.core._transfer_manager,
            "browse_directory",
            return_value={"ok": True, "server_id": "srv_1", "server_name": "TestNAS", "source": "disks", "path": "DiskA/Sub", "effective_role": "editor", "writable": True, "items": []},
        ):
            st_br, body_br = self._raw_http(
                "POST",
                "/api/transfer/browse",
                payload={"serverId": "srv_1", "path": "DiskA/Sub", "source": "disks"},
                headers=auth,
            )
        self.assertEqual(st_br, 200)
        self.assertTrue(body_br["success"])
        self.assertEqual(body_br["current_path"], "DiskA/Sub")
        self.assertEqual(body_br["parent_path"], "DiskA")

        for ep, payload in (
            ("/api/transfer/resolve_conflict", {"job_id": "missing", "action": "rename", "apply_to_all": True}),
            ("/api/transfer/pause", {"job_id": "missing"}),
            ("/api/transfer/resume", {"job_id": "missing"}),
            ("/api/transfer/cancel", {"job_id": "missing"}),
            ("/api/transfer/clear", {}),
            ("/api/transfer/clipboard/clear", {}),
        ):
            st_c, _ = self._raw_http("POST", ep, payload=payload, headers=auth)
            self.assertEqual(st_c, 200)

        # 6. Explorer hotkey setting persists & appears in /api/load_settings
        st_hk, body_hk = self._raw_http(
            "POST",
            "/api/settings/explorer_hotkey",
            payload={"enabled": False},
            headers=auth,
        )
        self.assertEqual(st_hk, 200)
        self.assertFalse(body_hk["enabled"])
        _, ls = self._raw_http("GET", "/api/load_settings", headers=auth)
        self.assertIs(ls.get("explorerHotkeyEnabled"), False)
        self._raw_http("POST", "/api/settings/explorer_hotkey", payload={"enabled": True}, headers=auth)

    def test_sse_desktop_clipboard_copy_verifies_active_user(self):
        cfg = self.config_manager.load_or_create_config()
        srv = self.config_manager.get_active_server(cfg)

        envelope_other = json.dumps({
            "type": "desktop_clipboard_copy",
            "ts": 1700000000,
            "data": {
                "username": "mallory",
                "items": [{"rel_path": "DiskA/secret.txt", "name": "secret.txt", "is_dir": False}],
            },
        })
        with patch.object(self.core, "_show_windows_toast", return_value=True) as mock_toast:
            accepted_other = self.core._process_backend_sse_event("desktop_clipboard_copy", envelope_other, srv, cfg)
        self.assertFalse(accepted_other)
        self.assertEqual(self.core._transfer_manager.get_clipboard()["mode"], "")
        mock_toast.assert_not_called()

        envelope_alice = json.dumps({
            "type": "desktop_clipboard_copy",
            "ts": 1700000001,
            "data": {
                "username": "alice",
                "items": [{"rel_path": "DiskA/report.pdf", "name": "report.pdf", "is_dir": False, "size": 42}],
            },
        })
        with patch.object(self.core, "_show_windows_toast", return_value=True) as mock_toast:
            accepted_alice = self.core._process_backend_sse_event("desktop_clipboard_copy", envelope_alice, srv, cfg)
        self.assertTrue(accepted_alice)
        clip = self.core._transfer_manager.get_clipboard()
        self.assertEqual(clip["mode"], "server")
        self.assertEqual(clip["source_origin"], "web_explorer")
        self.assertEqual(clip["items"][0]["rel_path"], "DiskA/report.pdf")
        mock_toast.assert_called_once()


if __name__ == "__main__":
    unittest.main()

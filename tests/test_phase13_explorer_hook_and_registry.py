import json
import os
import re
import unittest

from tests.test_phase11_tauri_contract import (
    CAPABILITIES_PATH,
    CARGO_TOML_PATH,
    LIB_RS_PATH,
    REPO_ROOT,
    _check_rust_delimiters,
    _extract_block,
)

EXPLORER_HOOK_RS_PATH = os.path.join(REPO_ROOT, "src-tauri", "src", "explorer_hook.rs")


class TestExplorerHookAndTauriTransferContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(EXPLORER_HOOK_RS_PATH, "r", encoding="utf-8") as fh:
            cls.hook_rs = fh.read()
        with open(LIB_RS_PATH, "r", encoding="utf-8") as fh:
            cls.lib_rs = fh.read()
        with open(CAPABILITIES_PATH, "r", encoding="utf-8") as fh:
            cls.cap = json.loads(fh.read())
        with open(CARGO_TOML_PATH, "r", encoding="utf-8") as fh:
            cls.cargo_toml = fh.read()

    def test_01_rust_delimiters_balanced_across_hook_and_lib(self):
        ok_hook, msg_hook = _check_rust_delimiters(self.hook_rs)
        self.assertTrue(ok_hook, f"explorer_hook.rs delimiter check failed: {msg_hook}")
        ok_lib, msg_lib = _check_rust_delimiters(self.lib_rs)
        self.assertTrue(ok_lib, f"lib.rs delimiter check failed: {msg_lib}")

        for fn_anchor in (
            "fn parse_explorer_cli_action(",
            "fn open_or_focus_transfer_window(",
            "async fn handle_explorer_transfer_cli_action(",
            "fn start_explorer_hook_worker(",
            "async fn open_transfer_window(",
            "fn close_transfer_window(",
            "fn get_transfer_window_state(",
            "fn set_explorer_hotkey_enabled(",
        ):
            block = _extract_block(self.lib_rs, fn_anchor)
            ok_fn, msg_fn = _check_rust_delimiters(block)
            self.assertTrue(ok_fn, f"{fn_anchor} unbalanced: {msg_fn}")

    def test_02_explorer_hook_win32_wh_keyboard_ll_and_no_blocking_io(self):
        for required in (
            "WH_KEYBOARD_LL",
            "WM_KEYDOWN",
            "WM_SYSKEYDOWN",
            "CabinetWClass",
            "ExploreWClass",
            "ShellTabWindowClass",
            "CallNextHookEx",
            "HOOK_ENABLED",
            "PostThreadMessageW",
            "try_send",
        ):
            self.assertIn(required, self.hook_rs)

        # Must never use global OS hotkey APIs
        self.assertNotIn("RegisterHotKey", self.hook_rs)
        self.assertNotIn("tauri_plugin_global_shortcut", self.hook_rs)

        # Callback low_level_keyboard_proc must remain pure Win32 + non-blocking try_send
        cb_block = _extract_block(self.hook_rs, "unsafe extern \"system\" fn low_level_keyboard_proc(")
        self.assertIn("CallNextHookEx", cb_block)
        self.assertIn("try_send", cb_block)
        for forbidden in ("TcpStream", "call_core_api", "CoInitialize", "http://", "https://", "reqwest"):
            self.assertNotIn(forbidden, cb_block)

    def test_03_lib_rs_transfer_window_and_unified_core_bridge(self):
        self.assertIn("mod explorer_hook;", self.lib_rs)
        self.assertIn(".manage(TransferWindowState::default())", self.lib_rs)

        for required in (
            "TransferWindowState",
            "parse_explorer_cli_action",
            "open_or_focus_transfer_window",
            "transfer/copy",
            "transfer/paste",
            "myserver:transfer-event",
            "explorer_hotkey_enabled",
        ):
            self.assertIn(required, self.lib_rs)

        # setup() reads explorer_hotkey_enabled from cfg_opt and applies it before starting hook worker
        setup_block = _extract_block(self.lib_rs, ".setup(|app| {")
        cfg_pos = setup_block.find("explorer_hotkey_enabled")
        set_pos = setup_block.find("explorer_hook::set_explorer_hotkey_enabled(")
        start_pos = setup_block.find("start_explorer_hook_worker(")
        self.assertNotEqual(cfg_pos, -1)
        self.assertNotEqual(set_pos, -1)
        self.assertNotEqual(start_pos, -1)
        self.assertLess(cfg_pos, set_pos)
        self.assertLess(set_pos, start_pos)

        # CloseRequested isolates transfer-window before api.prevent_close()
        close_block = _extract_block(self.lib_rs, "tauri::WindowEvent::CloseRequested { api, .. } => {")
        guard_pos = close_block.find('window.label() == "transfer-window"')
        prevent_pos = close_block.find("api.prevent_close()")
        self.assertNotEqual(guard_pos, -1)
        self.assertGreater(prevent_pos, guard_pos)
        transfer_guard = _extract_block(close_block, 'if window.label() == "transfer-window"')
        self.assertIn("TransferWindowState", transfer_guard)
        self.assertIn("return;", transfer_guard)
        self.assertNotIn("api.prevent_close()", transfer_guard)
        self.assertNotIn("myserver:reset-home", transfer_guard)

        # Tauri IPC commands & parameter signatures
        self.assertIn(
            "async fn open_transfer_window(app: AppHandle, state: serde_json::Value) -> Result<(), String>",
            self.lib_rs,
        )
        self.assertIn(
            "fn set_explorer_hotkey_enabled(enabled: bool) -> Result<bool, String>",
            self.lib_rs,
        )

        handler_match = re.search(
            r"tauri::generate_handler!\[(.*?)\]", self.lib_rs, re.DOTALL
        )
        self.assertIsNotNone(handler_match)
        handler_body = handler_match.group(1)
        for cmd in (
            "open_transfer_window",
            "close_transfer_window",
            "get_transfer_window_state",
            "set_explorer_hotkey_enabled",
        ):
            self.assertIn(cmd, handler_body)

    def test_04_rust_unit_tests_cover_explorer_cli_parser(self):
        tests_idx = self.lib_rs.find("#[cfg(test)]\nmod tests")
        if tests_idx == -1:
            tests_idx = self.lib_rs.find("#[cfg(test)]\r\nmod tests")
        self.assertNotEqual(tests_idx, -1)
        tests_src = self.lib_rs[tests_idx:]
        self.assertIn("parse_explorer_cli_action", tests_src)
        self.assertIn("--explorer-copy", tests_src)
        self.assertIn("--explorer-paste", tests_src)

    def test_05_cargo_toml_and_capabilities_lock(self):
        self.assertEqual(
            self.cap.get("windows"),
            ["main", "share-window", "transfer-window"],
        )
        self.assertEqual(self.cap.get("permissions"), ["core:default"])

        deps_section = self.cargo_toml.split("[dependencies]", 1)[1]
        dep_names = sorted(
            line.split("=", 1)[0].strip()
            for line in deps_section.splitlines()
            if "=" in line and not line.strip().startswith("#")
        )
        self.assertEqual(
            dep_names,
            [
                "log",
                "serde",
                "serde_json",
                "tauri",
                "tauri-plugin-log",
                "tauri-plugin-single-instance",
            ],
        )


class TestPhase13RegistryAndTabReaderContract(unittest.TestCase):
    def test_01_installer_iss_byte_sync_and_http_copy_paste_verbs(self):
        import build_installer_package

        iss_path = os.path.join(REPO_ROOT, "installer.iss")
        with open(iss_path, "r", encoding="utf-8") as fh:
            iss_text = fh.read()
        expected = build_installer_package.render_installer_iss(
            build_installer_package.VERSION, build_installer_package.APP_NAME
        )
        self.assertEqual(iss_text, expected)
        for required in (
            r"Software\Classes\*\shell\MyServerHttpCopy",
            r"Software\Classes\Directory\shell\MyServerHttpCopy",
            r"Software\Classes\Directory\shell\MyServerHttpPaste",
            r"Software\Classes\Directory\Background\shell\MyServerHttpPaste",
            '--explorer-copy ""%1""',
            '--explorer-paste ""%1""',
            '--explorer-paste ""%V""',
        ):
            self.assertIn(required, iss_text)

    def test_02_core_hkcu_targets_include_background_paste_percent_v(self):
        import myserver_core_service as core

        targets = {row[0]: row for row in core._EXPLORER_CTX_SHELL_TARGETS}
        self.assertEqual(len(targets), 8)
        bg_key = r"Software\Classes\Directory\Background\shell\MyServerHttpPaste"
        self.assertIn(bg_key, targets)
        self.assertEqual(targets[bg_key], (bg_key, "Paste via MyServer", "--explorer-paste", "%V"))

    def test_03_explorer_tab_reader_short_circuit_contract(self):
        import explorer_tab_reader

        class _InactiveTab:
            FullName = r"C:\Windows\explorer.exe"
            HWND = 100

            @property
            def Document(self):
                raise AssertionError("Inactive tab .Document must never be accessed")

        class _ActiveTab:
            FullName = r"C:\Windows\explorer.exe"
            HWND = 100
            LocationURL = "file:///Z:/Shared"

            class _Folder:
                class _Self:
                    Path = r"Z:\Shared"

                Self = _Self()

            class _Doc:
                Folder = None

                def SelectedItems(self):
                    return [type("_Item", (), {"Path": r"Z:\Shared\file.txt"})()]

            def __init__(self):
                self._doc = self._Doc()
                self._doc.Folder = self._Folder()

            @property
            def Document(self):
                return self._doc

        res = explorer_tab_reader._extract_active_tab_from_shell_windows(
            [_InactiveTab(), _ActiveTab()],
            fg_hwnd=100,
            top_tab_hwnd=2002,
            get_tab_hwnd_fn=lambda w: 1001 if isinstance(w, _InactiveTab) else 2002,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["folder_path"], r"Z:\Shared")
        self.assertEqual(res["selected_items"], [r"Z:\Shared\file.txt"])


if __name__ == "__main__":
    unittest.main()

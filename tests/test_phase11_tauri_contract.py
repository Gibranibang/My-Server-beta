import json
import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAPABILITIES_PATH = os.path.join(REPO_ROOT, "src-tauri", "capabilities", "default.json")
LIB_RS_PATH = os.path.join(REPO_ROOT, "src-tauri", "src", "lib.rs")
CARGO_TOML_PATH = os.path.join(REPO_ROOT, "src-tauri", "Cargo.toml")


def _check_rust_delimiters(source: str) -> tuple[bool, str]:
    """Verify balanced (), [], {} in Rust source ignoring comments, strings, raw strings, and char literals."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    i = 0
    n = len(source)
    line = 1

    while i < n:
        ch = source[i]
        if ch == "\n":
            line += 1
            i += 1
            continue

        # Line comment
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            nl = source.find("\n", i + 2)
            i = n if nl == -1 else nl
            continue

        # Block comment (supports Rust nested block comments)
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            depth = 1
            i += 2
            while i < n and depth > 0:
                if source[i] == "\n":
                    line += 1
                elif source[i] == "/" and i + 1 < n and source[i + 1] == "*":
                    depth += 1
                    i += 2
                    continue
                elif source[i] == "*" and i + 1 < n and source[i + 1] == "/":
                    depth -= 1
                    i += 2
                    continue
                i += 1
            if depth != 0:
                return False, f"Unclosed block comment near line {line}"
            continue

        # Raw string literal: r"..." or r#"..."# (and b"...", br#"..."#)
        if ch in ("r", "b") and i + 1 < n:
            j = i + 1
            if ch == "b" and j < n and source[j] == "r":
                j += 1
            if (ch == "r" or (ch == "b" and source[i + 1] == "r")) and j < n:
                hashes = 0
                while j < n and source[j] == "#":
                    hashes += 1
                    j += 1
                if j < n and source[j] == '"':
                    end_marker = '"' + ("#" * hashes)
                    j += 1
                    end_idx = source.find(end_marker, j)
                    if end_idx == -1:
                        return False, f"Unclosed raw string near line {line}"
                    line += source[j:end_idx].count("\n")
                    i = end_idx + len(end_marker)
                    continue

        # Normal string literal
        if ch == '"':
            i += 1
            while i < n:
                if source[i] == "\n":
                    line += 1
                elif source[i] == "\\":
                    i += 2
                    continue
                elif source[i] == '"':
                    i += 1
                    break
                i += 1
            else:
                return False, f"Unclosed string literal near line {line}"
            continue

        # Character literal vs lifetime ('a / '_ / 'static)
        if ch == "'":
            if i + 1 < n and source[i + 1] == "\\":
                i += 3  # skip ', \, and escaped char
                while i < n and source[i] != "'" and source[i] != "\n":
                    i += 1
                if i < n and source[i] == "'":
                    i += 1
                continue
            if i + 2 < n and source[i + 2] == "'" and source[i + 1] != "'":
                i += 3
                continue
            # Lifetime token; advance past quote only
            i += 1
            continue

        if ch in pairs:
            stack.append((ch, line))
        elif ch in closing:
            if not stack or stack[-1][0] != closing[ch]:
                expected = stack[-1][0] if stack else "<empty>"
                return False, f"Mismatched closing '{ch}' at line {line} (top={expected})"
            stack.pop()
        i += 1

    if stack:
        unclosed = ", ".join(f"'{c}'@L{ln}" for c, ln in stack[-5:])
        return False, f"Unclosed delimiters: {unclosed}"
    return True, "balanced"


def _extract_block(source: str, anchor: str) -> str:
    """Extract brace-delimited block starting at trailing '{' of anchor or first '{' after anchor."""
    idx = source.find(anchor)
    if idx == -1:
        raise AssertionError(f"Anchor not found: {anchor}")
    if anchor.endswith("{"):
        brace_start = idx + len(anchor) - 1
    else:
        brace_start = source.find("{", idx)
    if brace_start == -1:
        raise AssertionError(f"Opening brace not found after: {anchor}")

    depth = 0
    i = brace_start
    n = len(source)
    while i < n:
        ch = source[i]
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            nl = source.find("\n", i + 2)
            i = n if nl == -1 else nl
            continue
        if ch == '"':
            i += 1
            while i < n:
                if source[i] == "\\":
                    i += 2
                    continue
                if source[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if ch == "'":
            if i + 1 < n and source[i + 1] == "\\":
                i += 3
                while i < n and source[i] != "'" and source[i] != "\n":
                    i += 1
                if i < n and source[i] == "'":
                    i += 1
                continue
            if i + 2 < n and source[i + 2] == "'" and source[i + 1] != "'":
                i += 3
                continue
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[idx : i + 1]
        i += 1
    raise AssertionError(f"Unclosed block for anchor: {anchor}")


class TestRustAndCapabilitiesContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CAPABILITIES_PATH, "r", encoding="utf-8") as fh:
            cls.cap_raw = fh.read()
        cls.cap = json.loads(cls.cap_raw)
        with open(LIB_RS_PATH, "r", encoding="utf-8") as fh:
            cls.lib_rs = fh.read()
        with open(CARGO_TOML_PATH, "r", encoding="utf-8") as fh:
            cls.cargo_toml = fh.read()

    def test_01_capabilities_allowlists_main_and_share_window(self):
        self.assertEqual(self.cap.get("identifier"), "default")
        self.assertEqual(self.cap.get("windows"), ["main", "share-window", "transfer-window"])
        self.assertEqual(self.cap.get("permissions"), ["core:default"])

    def test_02_lib_rs_delimiters_and_syntax_sanity(self):
        ok, msg = _check_rust_delimiters(self.lib_rs)
        self.assertTrue(ok, f"Rust delimiter check failed: {msg}")
        for fn_anchor in (
            "fn sanitize_cli_share_path(",
            "fn parse_share_cli_action(",
            "fn open_or_focus_share_window(",
            "async fn wait_for_core_service_ready(",
            "async fn handle_share_cli_action(",
            "async fn open_share_window(",
            "fn close_share_window(",
            "fn get_share_window_target(",
            "pub fn run()",
        ):
            block = _extract_block(self.lib_rs, fn_anchor)
            ok_fn, msg_fn = _check_rust_delimiters(block)
            self.assertTrue(ok_fn, f"{fn_anchor} unbalanced: {msg_fn}")

    def test_03_share_window_unlocked_non_modal_attributes_and_no_recenter(self):
        fn_block = _extract_block(self.lib_rs, "fn open_or_focus_share_window(")
        self.assertIn('WebviewUrl::App("index.html?window=share".into())', fn_block)
        self.assertIn('.title("Share via MyServer")', fn_block)
        self.assertIn(".inner_size(400.0, 560.0)", fn_block)
        self.assertIn(".resizable(false)", fn_block)
        self.assertIn(".decorations(false)", fn_block)
        self.assertIn(".transparent(true)", fn_block)
        self.assertIn(".shadow(false)", fn_block)
        self.assertIn(".always_on_top(false)", fn_block)

        # Must never lock wizard mode or touch WizardWindowState / main window
        self.assertNotIn("set_wizard_mode", fn_block)
        self.assertNotIn("WizardWindowState", fn_block)
        self.assertNotIn('get_webview_window("main")', fn_block)

        # Existing window branch must emit myserver:share-target via serde_json::to_string and NOT call .center()
        existing_branch = _extract_block(fn_block, 'if let Some(wv) = app.get_webview_window("share-window")')
        self.assertIn("serde_json::to_string", existing_branch)
        self.assertIn("myserver:share-target", existing_branch)
        self.assertIn("wv.unminimize()", existing_branch)
        self.assertIn("wv.show()", existing_branch)
        self.assertIn("wv.set_focus()", existing_branch)
        self.assertNotIn(".center()", existing_branch)

        # New window branch centers once on initial creation
        self.assertIn(".center()", fn_block)

        # CR-01: ShareWindowState mutex must be scoped and dropped before get_webview_window / WebviewWindowBuilder
        lock_block = _extract_block(fn_block, "{\n        let state = app.state::<ShareWindowState>();")
        self.assertIn("*guard = Some(target_json.clone());", lock_block)
        lock_end = fn_block.find(lock_block) + len(lock_block)
        get_wv_pos = fn_block.find('app.get_webview_window("share-window")')
        builder_pos = fn_block.find("WebviewWindowBuilder::new(")
        self.assertLess(lock_end, get_wv_pos)
        self.assertLess(lock_end, builder_pos)
        self.assertIn("*guard = None;", fn_block)

    def test_04_close_requested_isolates_share_window_before_prevent_close(self):
        close_block = _extract_block(self.lib_rs, "tauri::WindowEvent::CloseRequested { api, .. } => {")
        guard_pos = close_block.find('window.label() == "share-window"')
        prevent_pos = close_block.find("api.prevent_close()")
        reset_pos = close_block.find("myserver:reset-home")
        hide_pos = close_block.find("window.hide()")

        self.assertNotEqual(guard_pos, -1, "Missing share-window label guard in CloseRequested")
        self.assertGreater(prevent_pos, guard_pos)
        self.assertGreater(reset_pos, guard_pos)
        self.assertGreater(hide_pos, guard_pos)

        share_guard_block = _extract_block(close_block, 'if window.label() == "share-window"')
        self.assertIn("ShareWindowState", share_guard_block)
        self.assertIn("return;", share_guard_block)
        self.assertNotIn("api.prevent_close()", share_guard_block)
        self.assertNotIn("myserver:reset-home", share_guard_block)
        self.assertNotIn("window.hide()", share_guard_block)

    def test_05_drag_drop_gated_to_main_and_not_wizard_with_serde_json(self):
        drop_block = _extract_block(self.lib_rs, "tauri::WindowEvent::DragDrop(drop_event) =>")
        label_pos = drop_block.find('window.label() != "main"')
        wizard_pos = drop_block.find("WizardWindowState")
        eval_pos = drop_block.find("wv.eval(")

        self.assertNotEqual(label_pos, -1)
        self.assertNotEqual(wizard_pos, -1)
        self.assertNotEqual(eval_pos, -1)
        self.assertLess(label_pos, eval_pos)
        self.assertLess(wizard_pos, eval_pos)

        self.assertIn("tauri::DragDropEvent::Enter", drop_block)
        self.assertIn("tauri::DragDropEvent::Drop", drop_block)
        self.assertIn("tauri::DragDropEvent::Leave", drop_block)
        self.assertIn("serde_json::to_string", drop_block)
        self.assertIn("myserver:drag-drop", drop_block)

    def test_06_single_instance_and_setup_cli_route_via_call_core_api_without_showing_main(self):
        si_idx = self.lib_rs.find("tauri_plugin_single_instance::init(")
        self.assertNotEqual(si_idx, -1)
        si_section = self.lib_rs[si_idx : si_idx + 900]
        parse_pos = si_section.find("parse_share_cli_action(&args)")
        restore_pos = si_section.find("restore_or_present_window")
        self.assertNotEqual(parse_pos, -1)
        self.assertNotEqual(restore_pos, -1)
        self.assertLess(parse_pos, restore_pos)
        self.assertIn("handle_share_cli_action(app_handle, action, true)", si_section)
        self.assertIn("return;", si_section[:restore_pos])

        # Cold-start setup suppresses should_auto_open when cli_share_action is present
        self.assertIn("should_auto_open && cli_share_action.is_none()", self.lib_rs)
        self.assertIn("handle_share_cli_action(app_handle, action, true)", self.lib_rs)

        # CLI action forwarding routes strictly through call_core_api (attaches X-MyServer-Core-Token)
        cli_block = _extract_block(self.lib_rs, "async fn handle_share_cli_action(")
        self.assertIn("wait_for_core_service_ready(15000).await", cli_block)
        self.assertIn('call_core_api(\n                "shares/resolve".to_string()', cli_block)
        self.assertIn('call_core_api(\n                "shares/quick".to_string()', cli_block)
        self.assertIn("open_or_focus_share_window", cli_block)
        self.assertNotIn("restore_or_present_window", cli_block)
        self.assertNotIn("127.0.0.1:48123", cli_block)

        # wait_for_core_service_ready polls GET /api/ping on 127.0.0.1:48123
        wait_block = _extract_block(self.lib_rs, "async fn wait_for_core_service_ready(")
        self.assertIn("GET /api/ping HTTP/1.1", wait_block)
        self.assertIn("TcpStream::connect_timeout", wait_block)

    def test_07_managed_state_and_ipc_handlers_registered(self):
        self.assertIn(".manage(ShareWindowState::default())", self.lib_rs)
        handler_match = re.search(
            r"tauri::generate_handler!\[(.*?)\]", self.lib_rs, re.DOTALL
        )
        self.assertIsNotNone(handler_match)
        handler_body = handler_match.group(1)
        for cmd in (
            "open_share_window",
            "close_share_window",
            "get_share_window_target",
        ):
            self.assertIn(cmd, handler_body)

    def test_08_rust_unit_tests_present_for_cli_parser(self):
        tests_idx = self.lib_rs.find("#[cfg(test)]\nmod tests")
        if tests_idx == -1:
            tests_idx = self.lib_rs.find("#[cfg(test)]\r\nmod tests")
        self.assertNotEqual(tests_idx, -1)
        tests_src = self.lib_rs[tests_idx:]
        self.assertIn("parse_share_cli_action", tests_src)
        self.assertIn("--share", tests_src)
        self.assertIn("--quick-share", tests_src)
        self.assertIn('Z:\\"', tests_src)

    def test_09_cargo_toml_adds_zero_new_crates(self):
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


if __name__ == "__main__":
    unittest.main()

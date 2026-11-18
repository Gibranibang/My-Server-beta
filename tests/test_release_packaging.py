import ast
import hashlib
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

try:
    import test_backend_detection
except ImportError:
    from tests import test_backend_detection

BETA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestReleasePackaging(unittest.TestCase):
    def test_version_info_and_manifest_match_app_version(self):
        import generate_version_info

        expected_ver = generate_version_info.detect_app_version()
        v_quad = ".".join(str(x) for x in generate_version_info.parse_version_tuple(expected_ver))

        vi_path = os.path.join(BETA_DIR, "file_version_info.txt")
        self.assertTrue(os.path.isfile(vi_path))
        vi_text = _read_text(vi_path)
        self.assertIn("StringStruct('CompanyName', 'Project Algitha')", vi_text)
        self.assertIn("StringStruct('OriginalFilename', 'myserver-core.exe')", vi_text)
        self.assertIn(f"StringStruct('FileVersion', '{v_quad}')", vi_text)

        manifest_path = os.path.join(BETA_DIR, "app.manifest")
        self.assertTrue(os.path.isfile(manifest_path))
        xml_text = _read_text(manifest_path)
        root = ET.fromstring(xml_text)
        self.assertIsNotNone(root)
        self.assertIn(f'version="{v_quad}"', xml_text)
        self.assertIn('level="asInvoker"', xml_text)
        self.assertIn("PerMonitorV2", xml_text)

    def test_pyinstaller_spec_uses_onedir_and_pe_metadata(self):
        spec_path = os.path.join(BETA_DIR, "myserver-core.spec")
        text = _read_text(spec_path)
        tree = ast.parse(text, filename=spec_path)
        calls = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertIn("EXE", calls)
        self.assertIn("COLLECT", calls)
        self.assertIn("exclude_binaries=True", text)
        self.assertIn("upx=False", text)
        self.assertIn("file_version_info.txt", text)
        self.assertIn("app.manifest", text)
        self.assertIn("app_icon.ico", text)
        self.assertIn("api-ms-win-", text)

    def test_installer_iss_is_in_sync_and_industry_standard(self):
        import build_installer_package

        iss_text = _read_text(os.path.join(BETA_DIR, "installer.iss"))
        self.assertEqual(
            iss_text,
            build_installer_package.render_installer_iss(
                build_installer_package.VERSION, build_installer_package.APP_NAME
            ),
        )
        self.assertIn("CloseApplications=yes", iss_text)
        self.assertIn("CloseApplicationsFilter=*.exe,*.dll,*.sys", iss_text)
        self.assertIn("#ifdef SIGN_TOOL", iss_text)
        self.assertIn("SignedUninstaller=yes", iss_text)
        self.assertIn(r'Type: files; Name: "{app}\bin\myserver-core.exe"', iss_text)
        self.assertIn(r'Type: filesandordirs; Name: "{app}\bin\easytier"', iss_text)
        self.assertIn("procedure TryGracefulAppShutdown();", iss_text)
        init_setup_block = iss_text.split("function InitializeSetup(): Boolean;")[1].split("end;")[0]
        self.assertNotIn("taskkill", init_setup_block)
        self.assertNotIn("StopRunningAppProcesses", init_setup_block)

    def test_staging_eliminates_duplicates_and_legacy_selfsigned_hacks(self):
        import build_installer_package

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "dist", "myserver-core", "_internal"), exist_ok=True)
            with open(os.path.join(tmp, "dist", "myserver-core", "myserver-core.exe"), "wb") as f:
                f.write(b"core")
            with open(os.path.join(tmp, "dist", "myserver-core", "_internal", "python312.dll"), "wb") as f:
                f.write(b"py")

            et_src = os.path.join(tmp, "resources", "deps", "easytier", "win32", "x64")
            os.makedirs(et_src, exist_ok=True)
            for fn in build_installer_package.EASYTIER_FILES:
                with open(os.path.join(et_src, fn), "wb") as f:
                    f.write(fn.encode())

            staging = os.path.join(tmp, "staging")
            os.makedirs(staging, exist_ok=True)

            mode, path = build_installer_package.find_core_artifact(tmp)
            self.assertEqual(mode, "onedir")
            build_installer_package.stage_core_artifact(mode, path, staging)
            et_count = build_installer_package.stage_easytier_binaries(tmp, staging)

            self.assertEqual(et_count, len(build_installer_package.EASYTIER_FILES))
            self.assertTrue(os.path.isfile(os.path.join(staging, "myserver-core.exe")))
            self.assertTrue(os.path.isfile(os.path.join(staging, "_internal", "python312.dll")))
            self.assertFalse(os.path.exists(os.path.join(staging, "bin", "myserver-core.exe")))
            self.assertFalse(os.path.exists(os.path.join(staging, "bin", "easytier")))
            self.assertTrue(
                os.path.isfile(os.path.join(staging, "resources", "deps", "easytier", "win32", "x64", "WinDivert64.sys"))
            )

            script_text = _read_text(os.path.join(BETA_DIR, "build_installer_package.py"))
            self.assertNotIn("Algitha_Project_Security_Certificate.cer", script_text)
            self.assertNotIn("1_Buka_Blokir_Windows_Unblock.bat", script_text)
            self.assertNotIn("sign_app.ps1", script_text)

    def test_write_sha256_sums_records_valid_digests(self):
        import build_installer_package

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "dist"), exist_ok=True)
            os.makedirs(os.path.join(tmp, "resources"), exist_ok=True)
            setup_path = os.path.join(tmp, "dist", "MyServer-Setup.exe")
            zip_path = os.path.join(tmp, "dist", "MyServer-v9.9.9-Beta.zip")
            manifest_path = os.path.join(tmp, "resources", "backend_manifest.json")
            with open(setup_path, "wb") as f:
                f.write(b"setup-payload")
            with open(zip_path, "wb") as f:
                f.write(b"zip-payload")
            with open(manifest_path, "wb") as f:
                f.write(b'{"version":"1.2.8"}')

            out_path, lines = build_installer_package.write_sha256_sums(tmp, "9.9.9")
            self.assertTrue(os.path.isfile(out_path))
            self.assertEqual(len(lines), 3)
            expected_setup_hash = hashlib.sha256(b"setup-payload").hexdigest()
            self.assertIn(f"{expected_setup_hash}  MyServer-Setup.exe", lines)

    def test_shutdown_background_daemons_stops_easytier_and_syncthing(self):
        test_backend_detection._install_linux_win_stubs()
        import myserver_core_service

        mock_et = mock.MagicMock()
        mock_st = mock.MagicMock()
        sample_cfg = {"local_syncthing": {"port": "8385", "api_key": "st-key-123"}}
        with (
            mock.patch.object(myserver_core_service.easytier_manager, "get_easytier_manager", return_value=mock_et),
            mock.patch.object(myserver_core_service, "_local_st_daemon", mock_st),
            mock.patch.object(myserver_core_service.config_manager, "load_or_create_config", return_value=sample_cfg),
        ):
            myserver_core_service.shutdown_background_daemons()

        mock_et.stop.assert_called_once()
        mock_st.stop.assert_called_once_with(custom_port="8385", api_key="st-key-123")

    def test_cargo_and_ci_workflow_integrity(self):
        cargo_text = _read_text(os.path.join(BETA_DIR, "src-tauri", "Cargo.toml"))
        self.assertIn('license = "MIT"', cargo_text)
        self.assertIn('repository = "https://github.com/Gibranibang/My-Server-beta"', cargo_text)

        wf_text = _read_text(os.path.join(BETA_DIR, ".github", "workflows", "build-release.yml"))
        self.assertIn("azure/artifact-signing-action@v2", wf_text)
        self.assertIn("dist\\myserver-core\\myserver-core.exe", wf_text)
        self.assertIn("SHA256SUMS.txt", wf_text)
        # Ensure EasyTier download only targets canonical resources\deps\easytier path
        dl_section = wf_text.split("Download Syncthing and EasyTier Windows binaries")[1].split("Detect Windows Code Signing")[0]
        self.assertNotIn("bin\\easytier", dl_section)


if __name__ == "__main__":
    unittest.main()

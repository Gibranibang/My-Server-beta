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
        self.assertIn("resources\\deps\\zerotier\\ZeroTier One.msi", dl_section)
        self.assertIn("0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1", dl_section)
        self.assertIn("dist\\staging_payload\\resources\\deps\\zerotier\\ZeroTier One.msi", wf_text)

    def test_is_valid_msi_file_validates_ole_cfbf_magic_and_size(self):
        import build_installer_package

        with tempfile.TemporaryDirectory() as tmp:
            missing_path = os.path.join(tmp, "missing.msi")
            self.assertFalse(build_installer_package.is_valid_msi_file(missing_path))

            valid_msi = os.path.join(tmp, "ZeroTier One.msi")
            with open(valid_msi, "wb") as f:
                f.write(build_installer_package.OLE_CFBF_MAGIC + (b"\x00" * 128))
            self.assertTrue(build_installer_package.is_valid_msi_file(valid_msi, min_bytes=64))
            self.assertFalse(build_installer_package.is_valid_msi_file(valid_msi, min_bytes=1024))

            bad_html = os.path.join(tmp, "error.msi")
            with open(bad_html, "wb") as f:
                f.write(b"<html>404 Not Found</html>" + (b" " * 128))
            self.assertFalse(build_installer_package.is_valid_msi_file(bad_html, min_bytes=64))

    def test_stage_zerotier_installer_uses_local_cache_or_downloads_with_validation(self):
        import build_installer_package

        with tempfile.TemporaryDirectory() as tmp:
            base_dir = os.path.join(tmp, "base")
            staging_dir = os.path.join(tmp, "staging")
            os.makedirs(base_dir, exist_ok=True)
            os.makedirs(staging_dir, exist_ok=True)

            # 1. Offline without local cache raises FileNotFoundError when allow_download=False
            with self.assertRaises(FileNotFoundError):
                build_installer_package.stage_zerotier_installer(
                    base_dir, staging_dir, allow_download=False, min_bytes=64
                )

            # 2. Corrupt download (non-OLE header) is rejected and .part is cleaned up
            bad_resp = mock.MagicMock()
            bad_resp.read.side_effect = [b"<!DOCTYPE html>Bad Gateway", b""]
            bad_resp.__enter__.return_value = bad_resp
            bad_resp.__exit__.return_value = False
            with mock.patch("urllib.request.urlopen", return_value=bad_resp):
                with self.assertRaises(RuntimeError):
                    build_installer_package.stage_zerotier_installer(
                        base_dir, staging_dir, allow_download=True, min_bytes=16
                    )
            local_msi = os.path.join(base_dir, "resources", "deps", "zerotier", "ZeroTier One.msi")
            self.assertFalse(os.path.exists(local_msi))
            self.assertFalse(os.path.exists(local_msi + ".part"))

            # 3. Valid download caches to base_dir and copies to staging_dir
            valid_payload = build_installer_package.OLE_CFBF_MAGIC + (b"\x5a" * 256)
            good_resp = mock.MagicMock()
            good_resp.read.side_effect = [valid_payload, b""]
            good_resp.__enter__.return_value = good_resp
            good_resp.__exit__.return_value = False
            with mock.patch("urllib.request.urlopen", return_value=good_resp) as m_open:
                staged_path = build_installer_package.stage_zerotier_installer(
                    base_dir, staging_dir, allow_download=True, min_bytes=64
                )
                self.assertEqual(m_open.call_count, 1)
            self.assertTrue(os.path.isfile(local_msi))
            self.assertTrue(os.path.isfile(staged_path))
            self.assertEqual(
                staged_path,
                os.path.join(staging_dir, "resources", "deps", "zerotier", "ZeroTier One.msi"),
            )

            # 4. Subsequent call uses local cache without hitting network
            staging_dir_2 = os.path.join(tmp, "staging2")
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("Network should not be called")):
                staged_path_2 = build_installer_package.stage_zerotier_installer(
                    base_dir, staging_dir_2, allow_download=True, min_bytes=64
                )
            self.assertTrue(os.path.isfile(staged_path_2))

    def test_installer_iss_bundles_zerotier_msi_and_keeps_version_4_6_1(self):
        import build_installer_package

        self.assertEqual(build_installer_package.VERSION, "4.9.6")
        iss_text = _read_text(os.path.join(BETA_DIR, "installer.iss"))
        self.assertIn('#define MyAppVersion "4.9.6"', iss_text)
        self.assertIn(
            r'Source: "dist\staging_payload\resources\deps\zerotier\ZeroTier One.msi"; DestDir: "{app}\resources\deps\zerotier"; Flags: ignoreversion',
            iss_text,
        )
        self.assertIn(
            r'Filename: "msiexec.exe"; Parameters: "/i ""{app}\resources\deps\zerotier\ZeroTier One.msi"" /qn /norestart"; StatusMsg: "Installing ZeroTier One service..."; Flags: runhidden waituntilterminated; Check: NeedsZeroTierInstall',
            iss_text,
        )
        self.assertIn(
            r'Filename: "{sys}\sc.exe"; Parameters: "config ZeroTierOneService start= auto"; Flags: runhidden waituntilterminated',
            iss_text,
        )
        self.assertIn(
            r'Filename: "{sys}\sc.exe"; Parameters: "start ZeroTierOneService"; Flags: runhidden waituntilterminated',
            iss_text,
        )
        self.assertIn("function NeedsZeroTierInstall(): Boolean;", iss_text)
        self.assertIn(r"SYSTEM\CurrentControlSet\Services\ZeroTierOneService", iss_text)
        self.assertIn(r"{commonappdata}\ZeroTier\One\zerotier-one_x64.exe", iss_text)

    def test_zerotier_manager_prefers_bundled_msi_over_network_download(self):
        import build_installer_package
        import zerotier_manager

        with tempfile.TemporaryDirectory() as tmp:
            bundled_dir = os.path.join(tmp, "resources", "deps", "zerotier")
            os.makedirs(bundled_dir, exist_ok=True)
            bundled_msi = os.path.join(bundled_dir, "ZeroTier One.msi")
            with open(bundled_msi, "wb") as f:
                f.write(build_installer_package.OLE_CFBF_MAGIC + (b"\x00" * 128))

            with mock.patch("os.getcwd", return_value=tmp):
                detected = zerotier_manager.get_bundled_zerotier_msi_path()
                self.assertEqual(os.path.abspath(detected), os.path.abspath(bundled_msi))

            mock_proc = mock.MagicMock(returncode=0, stdout="", stderr="")
            mock_client = mock.MagicMock()
            mock_client.is_service_running.return_value = (True, {"online": True})
            with (
                mock.patch.object(zerotier_manager, "get_bundled_zerotier_msi_path", return_value=bundled_msi),
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("Should not download when bundled")),
                mock.patch("subprocess.run", return_value=mock_proc) as m_run,
                mock.patch.object(zerotier_manager, "ZeroTierClient", return_value=mock_client),
                mock.patch("time.sleep"),
            ):
                ok, msg = zerotier_manager.install_zerotier_silently()
                self.assertTrue(ok)
                self.assertIn("ZeroTier One", msg)
                self.assertTrue(os.path.isfile(bundled_msi))
                ps_command = m_run.call_args[0][0][-1]
                self.assertIn(bundled_msi, ps_command)


if __name__ == "__main__":
    unittest.main()


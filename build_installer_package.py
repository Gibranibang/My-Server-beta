# -*- coding: utf-8 -*-
"""
MyServer Beta Automated Package & Installer Builder.

Menghasilkan:
1. Staging payload distribusi (--onedir Core Service + Tauri Shell + dependensi kanonik)
2. Paket arsip ZIP portabel: MyServer-v<VERSION>-Beta.zip
3. Skrip & installer resmi Inno Setup 6 (MyServer-v<VERSION>-Beta-Setup.exe & MyServer-Setup.exe)
4. Daftar checksum SHA256SUMS.txt untuk verifikasi integritas distribusi
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

BASE_BETA = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_BETA, "dist")
STAGING_DIR = os.path.join(DIST_DIR, "staging_payload")
VERSION = "4.5.14"
APP_NAME = "My-Server by algitha BETA"

EASYTIER_FILES = (
    "easytier-core.exe",
    "easytier-cli.exe",
    "wintun.dll",
    "Packet.dll",
    "WinDivert64.sys",
)

BACKEND_RESOURCE_FILES = (
    "backend_manifest.json",
    "MyServer-Backend-ZimaOS.zip",
    "MyServer-Backend-ZimaOS.tar.gz",
)


def _find_iscc():
    """Menemukan lokasi kompiler Inno Setup 6 (ISCC.exe)."""
    env_path = os.environ.get("ISCC_PATH", "").strip()
    if env_path and os.path.exists(env_path):
        return env_path
    which_path = shutil.which("ISCC.exe") or shutil.which("iscc")
    if which_path:
        return which_path
    for cand in (
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ):
        if os.path.exists(cand):
            return cand
    return os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe")


def find_tauri_binary(base_dir=BASE_BETA):
    """Memilih biner Tauri Shell terbaru yang tersedia."""
    candidates = [
        os.path.join(base_dir, "src-tauri", "target", "release", "MyServer-Beta.exe"),
        os.path.join(base_dir, "sandbox", "tauri_shell", "src-tauri", "target", "release", "MyServer-Beta.exe"),
    ]
    existing = [p for p in candidates if os.path.exists(p)]
    if existing:
        return max(existing, key=os.path.getmtime)
    return candidates[0]


def find_core_artifact(base_dir=BASE_BETA):
    """
    Memprioritaskan hasil PyInstaller --onedir (dist/myserver-core/myserver-core.exe),
    dengan fallback ke --onefile hanya jika direktori --onedir tidak tersedia.
    """
    onedir_dir = os.path.join(base_dir, "dist", "myserver-core")
    onedir_exe = os.path.join(onedir_dir, "myserver-core.exe")
    if os.path.isdir(onedir_dir) and os.path.exists(onedir_exe):
        return "onedir", onedir_dir

    onefile_cands = [
        os.path.join(base_dir, "dist", "myserver-core.exe"),
        os.path.join(base_dir, "sandbox", "dist", "myserver-core.exe"),
        os.path.join(os.path.dirname(base_dir), "dist", "myserver-core.exe"),
    ]
    existing = [c for c in onefile_cands if os.path.exists(c)]
    if existing:
        return "onefile", max(existing, key=os.path.getmtime)
    return "onedir", onedir_dir


def stage_core_artifact(mode, core_path, staging_dir):
    """Menyalin Core Service ke root staging tanpa duplikasi biner di bin/."""
    if mode == "onedir":
        exe_path = os.path.join(core_path, "myserver-core.exe")
        if not os.path.exists(exe_path):
            raise FileNotFoundError(f"Biner Core Service (--onedir) tidak ditemukan: {exe_path}")
        shutil.copytree(core_path, staging_dir, dirs_exist_ok=True)
        return exe_path

    if not os.path.exists(core_path):
        raise FileNotFoundError(f"Biner Core Service tidak ditemukan: {core_path}")
    dst_exe = os.path.join(staging_dir, "myserver-core.exe")
    shutil.copy2(core_path, dst_exe)
    return dst_exe


def stage_easytier_binaries(base_dir, staging_dir):
    """
    Menyalin biner EasyTier satu kali secara kanonik ke resources/deps/easytier/win32/x64/.
    Menghindari duplikasi file driver WinDivert64.sys / DLL ke folder bin/easytier/.
    """
    canonical_src = os.path.join(base_dir, "resources", "deps", "easytier", "win32", "x64")
    legacy_src = os.path.join(base_dir, "bin", "easytier")
    src_dir = canonical_src if os.path.isdir(canonical_src) else legacy_src
    if not os.path.isdir(src_dir):
        return 0

    dst_dir = os.path.join(staging_dir, "resources", "deps", "easytier", "win32", "x64")
    os.makedirs(dst_dir, exist_ok=True)
    copied = 0
    for f_name in sorted(os.listdir(src_dir)):
        s_file = os.path.join(src_dir, f_name)
        if os.path.isfile(s_file) and (f_name in EASYTIER_FILES or os.path.isdir(canonical_src)):
            shutil.copy2(s_file, os.path.join(dst_dir, f_name))
            copied += 1
    return copied


def stage_backend_resources(base_dir, staging_dir):
    """Menyalin manifest dan arsip instalasi backend ZimaOS ke staging resources/."""
    src_res_root = os.path.join(base_dir, "resources")
    dst_res_root = os.path.join(staging_dir, "resources")
    if not os.path.isdir(src_res_root):
        return

    os.makedirs(dst_res_root, exist_ok=True)
    for f_name in BACKEND_RESOURCE_FILES:
        s_file = os.path.join(src_res_root, f_name)
        if os.path.isfile(s_file):
            shutil.copy2(s_file, os.path.join(dst_res_root, f_name))
            print(f"    [v] Backend resource staged: resources/{f_name}")
        else:
            print(f"    [!] Peringatan: resources/{f_name} tidak ditemukan!")

    for f_name in sorted(os.listdir(src_res_root)):
        if (
            f_name.startswith("MyServer-Backend-")
            and (f_name.endswith(".zip") or f_name.endswith(".tar.gz"))
            and f_name not in BACKEND_RESOURCE_FILES
        ):
            s_file = os.path.join(src_res_root, f_name)
            if os.path.isfile(s_file):
                shutil.copy2(s_file, os.path.join(dst_res_root, f_name))
                print(f"    [v] Extra backend package staged: resources/{f_name}")


def build_default_config(base_dir=BASE_BETA):
    """Membentuk templat config.json bersih untuk pengguna baru."""
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    try:
        import config_manager
        return config_manager.get_default_config()
    except Exception:
        return {
            "active_server_id": "srv_default",
            "servers": [{
                "id": "srv_default",
                "name": "Server Utama",
                "connections": [{"id": "conn_default", "name": "Lokal", "url": "http://zimaos.local"}],
                "active_connection": "auto",
                "profiles": ["Admin"],
                "active_profile": "Admin",
                "credentials": {},
                "backup_app": {"lan_mode": "inherit", "lan_ip": "", "lan_port": "8384", "wan_url": "", "api_key": ""},
                "wake_on_lan": {"mac_address": "", "broadcast_ip": "255.255.255.255", "port": 9},
            }],
            "local_syncthing": {"enabled": True, "port": "8384", "api_key": "", "auto_start": True},
            "web_apps": [],
            "first_run_setup": True,
            "language": "en",
            "notifications_enabled": True,
            "open_dashboard_on_launch": False,
        }


def render_installer_iss(version=VERSION, app_name=APP_NAME):
    """Menghasilkan skrip Inno Setup 6 standar industri untuk MyServer Beta."""
    return f"""; Script generated by Algitha Project Desktop
; Inno Setup 6 Script for MyServer Desktop (Beta)
; Industry Standard Windows Setup Engine

#define MyAppName "{app_name}"
#define MyAppVersion "{version}"
#define MyAppPublisher "Algitha Project"
#define MyAppURL "https://github.com/Gibranibang/My-Server-beta"
#define MyAppExeName "MyServer-Beta.exe"

[Setup]
; AppId resmi MyServer Beta (hanya 1 kurung kurawal penutup agar tepat mencocokkan registry key)
AppId={{{{5D8C7A3B-8C4E-4B1C-9A5F-2D3E6F7A8B9C}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
AppUpdatesURL={{#MyAppURL}}
DefaultDirName={{code:GetInstallDir}}
DefaultGroupName={{#MyAppName}}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=MyServer-v{version}-Beta-Setup
SetupIconFile=app_icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
UsePreviousAppDir=yes
UsePreviousPrivileges=no
DirExistsWarning=no
DisableProgramGroupPage=auto
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.sys
RestartApplications=no
UninstallDisplayIcon={{app}}\\{{#MyAppExeName}}
UninstallDisplayName={{#MyAppName}}
#ifdef SIGN_TOOL
SignTool=mysign
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"

[Files]
Source: "app_icon.ico"; DestDir: "{{app}}"; Flags: ignoreversion
; Salin semua biner dan dependensi runtime hasil kompilasi
Source: "dist\\staging_payload\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config.json,config.json.bak"
; Lindungi config.json agar tidak pernah tertimpa saat update / reinstall
Source: "dist\\staging_payload\\config.json"; DestDir: "{{app}}"; Flags: onlyifdoesntexist uninsneveruninstall

[InstallDelete]
Type: files; Name: "{{userstartup}}\\MyServer*.lnk"
Type: files; Name: "{{userstartup}}\\My-Server*.lnk"
; Bersihkan duplikasi biner lama dari versi pra-onedir agar tidak tersisa file usang
Type: files; Name: "{{app}}\\bin\\myserver-core.exe"
Type: filesandordirs; Name: "{{app}}\\bin\\easytier"

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; IconFilename: "{{app}}\\app_icon.ico"
Name: "{{group}}\\{{cm:UninstallProgram,{{#MyAppName}}}}"; Filename: "{{uninstallexe}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; IconFilename: "{{app}}\\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#MyAppName}}}}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
var
  IsUpgradeMode: Boolean;
  DetectedPath: String;

function GetExistingAppDir(): String;
var
  S: String;
begin
  Result := '';
  // 1. Cek registry HKCU (instalasi per-user saat ini)
  if RegQueryStringValue(HKCU, 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{{5D8C7A3B-8C4E-4B1C-9A5F-2D3E6F7A8B9C}}_is1', 'Inno Setup: App Path', S) and (S <> '') then
    Result := S
  else if RegQueryStringValue(HKCU, 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{{5D8C7A3B-8C4E-4B1C-9A5F-2D3E6F7A8B9C}}_is1', 'InstallLocation', S) and (S <> '') then
    Result := S
  // 2. Cek registry HKLM (jika pernah dipasang untuk semua pengguna)
  else if RegQueryStringValue(HKLM, 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{{5D8C7A3B-8C4E-4B1C-9A5F-2D3E6F7A8B9C}}_is1', 'Inno Setup: App Path', S) and (S <> '') then
    Result := S
  else if RegQueryStringValue(HKLM, 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{{5D8C7A3B-8C4E-4B1C-9A5F-2D3E6F7A8B9C}}_is1', 'InstallLocation', S) and (S <> '') then
    Result := S;
end;

function GetInstallDir(Param: String): String;
begin
  if DetectedPath <> '' then
    Result := DetectedPath
  else
    Result := ExpandConstant('{{autopf}}\\{{#MyAppName}}');
end;

procedure TryGracefulAppShutdown();
var
  Http: Variant;
begin
  try
    Http := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    Http.SetTimeouts(500, 500, 1000, 1000);
    Http.Open('POST', 'http://127.0.0.1:48123/api/quit_app', False);
    Http.SetRequestHeader('Content-Type', 'application/json');
    Http.Send('{{}}');
    Sleep(1200);
  except
    // Core Service sedang tidak berjalan atau belum siap; lanjut ke langkah berikutnya
  end;
end;

procedure StopRunningAppProcesses();
var
  ResultCode: Integer;
begin
  TryGracefulAppShutdown();
  Exec(
    AddBackslash(ExpandConstant('{{sys}}')) + 'taskkill.exe',
    '/F /IM MyServer-Beta.exe /IM MyServer.exe /IM myserver-core.exe /IM syncthing.exe /IM easytier-core.exe /IM easytier-cli.exe',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Sleep(1000);
end;

function InitializeSetup(): Boolean;
begin
  DetectedPath := GetExistingAppDir();
  IsUpgradeMode := (DetectedPath <> '');
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningAppProcesses();
  Result := '';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  // Saat mode update, lewati halaman pemilihan folder agar tetap di folder instalasi yang sudah ada
  if IsUpgradeMode and (PageID = wpSelectDir) then
    Result := True
  else
    Result := False;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if IsUpgradeMode and (CurPageID = wpReady) then
  begin
    WizardForm.NextButton.Caption := '&Update';
  end;
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningAppProcesses();
  Result := True;
end;
"""


def create_portable_zip(staging_dir, zip_target):
    """Mengemas isi staging_payload ke ZIP portabel di bawah root folder MyServer-Beta/."""
    with zipfile.ZipFile(zip_target, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(staging_dir):
            for file_name in sorted(files):
                full_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(full_path, staging_dir)
                archive_name = os.path.join("MyServer-Beta", rel_path)
                z.write(full_path, archive_name)
    return zip_target


def compute_sha256(file_path):
    """Menghitung digest SHA-256 hex lowercase sebuah berkas."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def write_sha256_sums(base_dir=BASE_BETA, version=VERSION):
    """Menulis dist/SHA256SUMS.txt untuk semua artefak rilis yang ada."""
    dist_dir = os.path.join(base_dir, "dist")
    res_dir = os.path.join(base_dir, "resources")
    candidates = [
        os.path.join(dist_dir, f"MyServer-v{version}-Beta.zip"),
        os.path.join(dist_dir, f"MyServer-v{version}-Beta-Setup.exe"),
        os.path.join(dist_dir, "MyServer-Setup.exe"),
        os.path.join(res_dir, "backend_manifest.json"),
        os.path.join(res_dir, "MyServer-Backend-ZimaOS.zip"),
        os.path.join(res_dir, "MyServer-Backend-ZimaOS.tar.gz"),
    ]
    lines = []
    for path in candidates:
        if os.path.isfile(path):
            digest = compute_sha256(path)
            lines.append(f"{digest}  {os.path.basename(path)}")

    os.makedirs(dist_dir, exist_ok=True)
    out_path = os.path.join(dist_dir, "SHA256SUMS.txt")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    return out_path, lines


def compile_installer(iscc_path, iss_script, base_dir=BASE_BETA, version=VERSION):
    """Menjalankan ISCC.exe (dengan SignTool CI bila dikonfigurasi) untuk menghasilkan installer."""
    cmd = [iscc_path]
    signtool_spec = os.environ.get("MYSERVER_ISCC_SIGNTOOL", "").strip()
    if signtool_spec:
        cmd.extend(["/DSIGN_TOOL", f"/Smysign={signtool_spec}"])
    cmd.append(iss_script)

    res = subprocess.run(cmd, cwd=base_dir, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ISCC Compiler Error:\n{res.stderr}\n{res.stdout}")

    dist_dir = os.path.join(base_dir, "dist")
    setup_output = os.path.join(dist_dir, f"MyServer-v{version}-Beta-Setup.exe")
    if not os.path.exists(setup_output):
        raise FileNotFoundError(f"ISCC selesai tapi berkas installer tidak ditemukan: {setup_output}")

    setup_generic = os.path.join(dist_dir, "MyServer-Setup.exe")
    shutil.copy2(setup_output, setup_generic)
    return setup_output, setup_generic


def main(argv=None):
    parser = argparse.ArgumentParser(description="MyServer Beta Package & Installer Builder")
    parser.add_argument("--generate-iss-only", action="store_true", help="Hanya perbarui installer.iss")
    parser.add_argument("--skip-iscc", action="store_true", help="Lewati kompilasi ISCC Inno Setup")
    parser.add_argument("--checksums-only", action="store_true", help="Hanya buat/perbarui dist/SHA256SUMS.txt")
    args = parser.parse_args(argv)

    iss_script = os.path.join(BASE_BETA, "installer.iss")

    if args.generate_iss_only:
        with open(iss_script, "w", encoding="utf-8") as f:
            f.write(render_installer_iss(VERSION, APP_NAME))
        print(f"[v] Skrip Inno Setup diperbarui: {iss_script}")
        return 0

    if args.checksums_only:
        sum_path, sum_lines = write_sha256_sums(BASE_BETA, VERSION)
        print(f"[v] SHA256SUMS.txt ditulis ({len(sum_lines)} entri): {sum_path}")
        return 0

    iscc_path = _find_iscc()
    src_tauri_exe = find_tauri_binary(BASE_BETA)
    core_mode, src_core_path = find_core_artifact(BASE_BETA)

    print(f"=== [MyServer v{VERSION} Beta Installer & Package Builder] ===")
    print(f"[*] Menggunakan biner Companion: {src_tauri_exe}")
    print(f"[*] Menggunakan Core Service ({core_mode}): {src_core_path}")

    print("\n[1] Memeriksa biner terkompilasi...")
    if not os.path.exists(src_tauri_exe):
        print(f"  [X] ERROR: Biner Tauri tidak ditemukan: {src_tauri_exe}")
        return 1
    print(f"  [v] Tauri Shell: {src_tauri_exe} ({os.path.getsize(src_tauri_exe):,} bytes)")

    print("\n[2] Menyiapkan staging payload distribusi...")
    if os.path.exists(STAGING_DIR):
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
    os.makedirs(STAGING_DIR, exist_ok=True)
    os.makedirs(os.path.join(STAGING_DIR, "bin"), exist_ok=True)

    shutil.copy2(src_tauri_exe, os.path.join(STAGING_DIR, "MyServer-Beta.exe"))
    try:
        staged_core_exe = stage_core_artifact(core_mode, src_core_path, STAGING_DIR)
        print(f"  [v] Core Service staged ({core_mode}): {staged_core_exe}")
    except FileNotFoundError as exc:
        print(f"  [X] ERROR: {exc}")
        return 1

    et_count = stage_easytier_binaries(BASE_BETA, STAGING_DIR)
    print(f"  [v] EasyTier dependencies staged (kanonik tunggal): {et_count} berkas")

    stage_backend_resources(BASE_BETA, STAGING_DIR)

    st_exe_src = os.path.join(BASE_BETA, "bin", "syncthing.exe")
    if not os.path.exists(st_exe_src):
        st_exe_src = os.environ.get("MYSERVER_SYNCTHING_PATH", "") or shutil.which("syncthing.exe") or ""
    if st_exe_src and os.path.exists(st_exe_src):
        shutil.copy2(st_exe_src, os.path.join(STAGING_DIR, "bin", "syncthing.exe"))
        print(f"  [v] Syncthing Engine: {st_exe_src} ({os.path.getsize(st_exe_src):,} bytes)")
    else:
        print(f"  [!] PERINGATAN: syncthing.exe tidak ditemukan di {st_exe_src}")

    for asset_name in ("app_icon.ico", "dialogs.ps1", "LICENSE", "CHANGELOG.md", "CHANGELOG.txt"):
        src_asset = os.path.join(BASE_BETA, asset_name)
        if os.path.exists(src_asset):
            shutil.copy2(src_asset, os.path.join(STAGING_DIR, asset_name))

    clean_cfg = build_default_config(BASE_BETA)
    with open(os.path.join(STAGING_DIR, "config.json"), "w", encoding="utf-8") as f:
        json.dump(clean_cfg, f, indent=2)

    print(f"  [v] Staging payload siap: {len(os.listdir(STAGING_DIR))} item di root staging")

    zip_filename = f"MyServer-v{VERSION}-Beta.zip"
    zip_target = os.path.join(DIST_DIR, zip_filename)
    print(f"\n[3] Mengemas berkas arsip portabel ZIP ({zip_filename})...")
    create_portable_zip(STAGING_DIR, zip_target)
    print(f"  [v] ZIP Portabel siap: {zip_target} ({os.path.getsize(zip_target):,} bytes)")

    sw_dist = os.environ.get("MYSERVER_EXTRA_DIST_DIR", "").strip()
    if sw_dist and os.path.isdir(os.path.dirname(sw_dist)):
        os.makedirs(sw_dist, exist_ok=True)
        shutil.copy2(zip_target, os.path.join(sw_dist, zip_filename))

    print("\n[4] Memperbarui skrip & mengompilasi Installer Standar Windows (Inno Setup 6)...")
    with open(iss_script, "w", encoding="utf-8") as f:
        f.write(render_installer_iss(VERSION, APP_NAME))
    print(f"  [v] Skrip Inno Setup diperbarui: {iss_script}")

    if not args.skip_iscc:
        try:
            setup_output, setup_generic = compile_installer(iscc_path, iss_script, BASE_BETA, VERSION)
            if sw_dist and os.path.isdir(sw_dist):
                shutil.copy2(setup_output, os.path.join(sw_dist, os.path.basename(setup_output)))
                shutil.copy2(setup_output, os.path.join(sw_dist, "MyServer-Setup.exe"))
            print("  [v] SUKSES! Installer Inno Setup 6 siap:")
            print(f"      - {setup_output} ({os.path.getsize(setup_output):,} bytes)")
            print(f"      - {setup_generic}")
        except Exception as exc:
            print(f"  [X] {exc}")
            return 1

    sum_path, sum_lines = write_sha256_sums(BASE_BETA, VERSION)
    print(f"\n[5] Checksum integritas dibuat ({len(sum_lines)} entri): {sum_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

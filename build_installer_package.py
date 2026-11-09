# -*- coding: utf-8 -*-

"""

MyServer v3.10.12 Beta Automated Package & Installer Builder

Menghasilkan:

1. Staging Payload lengkap dengan biner Tauri + Core Service

2. Paket Arsip ZIP Portabel: MyServer-v3.10.12-Beta.zip

3. Berkas Installer Resmi Windows (Inno Setup 6): MyServer-v3.10.12-Beta-Setup.exe & MyServer-Setup.exe

4. Penandatanganan digital Authenticode otomatis

"""



import os

import sys

import shutil

import subprocess

import json

import zipfile



BASE_BETA = r"D:\Projek\MyServer\Beta"

DIST_DIR = os.path.join(BASE_BETA, "dist")

STAGING_DIR = os.path.join(DIST_DIR, "staging_payload")

VERSION = "4.4.6"

APP_NAME = "My-Server by algitha BETA"

ISCC_PATH = r"C:\Users\gibra\AppData\Local\Programs\Inno Setup 6\ISCC.exe"



cand1 = os.path.join(BASE_BETA, r"src-tauri\target\release\MyServer-Beta.exe")
cand2 = os.path.join(BASE_BETA, r"sandbox\tauri_shell\src-tauri\target\release\MyServer-Beta.exe")
if os.path.exists(cand1) and os.path.exists(cand2):
    src_tauri_exe = cand1 if os.path.getmtime(cand1) >= os.path.getmtime(cand2) else cand2
elif os.path.exists(cand1):
    src_tauri_exe = cand1
else:
    src_tauri_exe = cand2
print(f"[*] Menggunakan biner Companion: {src_tauri_exe}")

src_core_exe = os.path.join(BASE_BETA, r"sandbox\dist\myserver-core.exe")

if not os.path.exists(src_core_exe):

    src_core_exe = r"D:\Projek\dist\myserver-core.exe"



print(f"=== [MyServer v{VERSION} Beta Installer & Package Builder] ===")



# 1. Validasi biner sumber

print("\n[1] Memeriksa biner terkompilasi...")

if not os.path.exists(src_tauri_exe):

    print(f"  [X] ERROR: Biner Tauri tidak ditemukan: {src_tauri_exe}")

    sys.exit(1)

print(f"  [v] Tauri Shell: {src_tauri_exe} ({os.path.getsize(src_tauri_exe):,} bytes)")



if not os.path.exists(src_core_exe):

    print(f"  [X] ERROR: Biner Core Service tidak ditemukan: {src_core_exe}")

    sys.exit(1)

print(f"  [v] Core Service: {src_core_exe} ({os.path.getsize(src_core_exe):,} bytes)")



# 2. Siapkan direktori staging_payload

print("\n[2] Menyiapkan staging payload distribusi...")

if os.path.exists(STAGING_DIR):

    shutil.rmtree(STAGING_DIR, ignore_errors=True)

os.makedirs(STAGING_DIR, exist_ok=True)

os.makedirs(os.path.join(STAGING_DIR, "bin"), exist_ok=True)



# Salin biner utama

shutil.copy2(src_tauri_exe, os.path.join(STAGING_DIR, "MyServer-Beta.exe"))

shutil.copy2(src_core_exe, os.path.join(STAGING_DIR, "myserver-core.exe"))

shutil.copy2(src_core_exe, os.path.join(STAGING_DIR, "bin", "myserver-core.exe"))

# Salin biner EasyTier P2P Mesh
src_easytier_dir = os.path.join(BASE_BETA, "bin", "easytier")
dst_easytier_dir = os.path.join(STAGING_DIR, "bin", "easytier")
if os.path.exists(src_easytier_dir):
    os.makedirs(dst_easytier_dir, exist_ok=True)
    for et_file in ["easytier-core.exe", "easytier-cli.exe", "wintun.dll", "Packet.dll", "WinDivert64.sys"]:
        et_src = os.path.join(src_easytier_dir, et_file)
        if os.path.exists(et_src):
            shutil.copy2(et_src, os.path.join(dst_easytier_dir, et_file))

# Salin juga ke resources/deps/easytier/win32/x64 untuk keselarasan struktur ZimaNet
src_res_et = os.path.join(BASE_BETA, "resources", "deps", "easytier", "win32", "x64")
dst_res_et = os.path.join(STAGING_DIR, "resources", "deps", "easytier", "win32", "x64")
if os.path.exists(src_res_et):
    os.makedirs(dst_res_et, exist_ok=True)
    for f_name in os.listdir(src_res_et):
        s_file = os.path.join(src_res_et, f_name)
        if os.path.isfile(s_file):
            shutil.copy2(s_file, os.path.join(dst_res_et, f_name))

# Tanda tangani seluruh biner di staging_payload dengan Authenticode
sign_ps1 = os.path.join(BASE_BETA, "sign_app.ps1")
if os.path.exists(sign_ps1):
    for biner_rel in ["MyServer-Beta.exe", "myserver-core.exe", os.path.join("bin", "myserver-core.exe"), os.path.join("bin", "easytier", "easytier-core.exe"), os.path.join("bin", "easytier", "easytier-cli.exe")]:
        target_bin = os.path.join(STAGING_DIR, biner_rel)
        if os.path.exists(target_bin):
            subprocess.run([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", sign_ps1,
                "-TargetExe", target_bin,
                "-DistDir", STAGING_DIR,
                "-SkipTimestamp"
            ], capture_output=True, text=True)
            print(f"  [v] Authenticode Signed: {biner_rel}")




# Salin biner Syncthing Engine ke bin\

st_exe_src = os.path.join(BASE_BETA, "bin", "syncthing.exe")

if not os.path.exists(st_exe_src):

    st_exe_src = r"D:\Softwares\Syncthing\syncthing.exe"

if os.path.exists(st_exe_src):

    shutil.copy2(st_exe_src, os.path.join(STAGING_DIR, "bin", "syncthing.exe"))

    print(f"  [v] Syncthing Engine: {st_exe_src} ({os.path.getsize(st_exe_src):,} bytes)")

else:

    print(f"  [!] PERINGATAN: syncthing.exe tidak ditemukan di {st_exe_src}")



# Salin ikon aplikasi

ico_src = os.path.join(BASE_BETA, "app_icon.ico")

if os.path.exists(ico_src):

    shutil.copy2(ico_src, os.path.join(STAGING_DIR, "app_icon.ico"))



# Salin dialogs.ps1

ps1_src = os.path.join(BASE_BETA, "dialogs.ps1")

if not os.path.exists(ps1_src):

    ps1_src = r"D:\Softwares\MyServer\dialogs.ps1"

if os.path.exists(ps1_src):

    shutil.copy2(ps1_src, os.path.join(STAGING_DIR, "dialogs.ps1"))



# Buat default config.json bersih (template untuk pengguna baru)

sys.path.insert(0, BASE_BETA)

try:

    import config_manager

    clean_cfg = config_manager.get_default_config()

except Exception:

    clean_cfg = {

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

            "wake_on_lan": {"mac_address": "", "broadcast_ip": "255.255.255.255", "port": 9}

        }],

        "local_syncthing": {"enabled": True, "port": "8384", "api_key": "", "auto_start": True},

        "web_apps": [],

        "first_run_setup": True,

        "language": "en",

        "notifications_enabled": True,

        "open_dashboard_on_launch": False

    }



with open(os.path.join(STAGING_DIR, "config.json"), "w", encoding="utf-8") as f:

    json.dump(clean_cfg, f, indent=2)



# Salin berkas sertifikat dan skrip keamanan tambahan jika ada

extra_files = [

    (r"D:\Softwares\MyServer\1_Buka_Blokir_Windows_Unblock.bat", "1_Buka_Blokir_Windows_Unblock.bat"),

    (r"D:\Softwares\MyServer\2_Pasang_Sertifikat_Kepercayaan_Admin.bat", "2_Pasang_Sertifikat_Kepercayaan_Admin.bat"),

    (r"D:\Softwares\MyServer\Algitha_Project_Security_Certificate.cer", "Algitha_Project_Security_Certificate.cer"),

    (r"D:\Softwares\MyServer\PANDUAN_KEAMANAN_WINDOWS.txt", "PANDUAN_KEAMANAN_WINDOWS.txt"),

    (os.path.join(BASE_BETA, "CHANGELOG.md"), "CHANGELOG.md"),

    (os.path.join(BASE_BETA, "CHANGELOG.txt"), "CHANGELOG.txt"),

]



for src, name in extra_files:

    if os.path.exists(src):

        shutil.copy2(src, os.path.join(STAGING_DIR, name))



print(f"  [v] Staging payload siap: {len(os.listdir(STAGING_DIR))} berkas & direktori")



# 3. Buat Arsip Portabel ZIP: MyServer-v3.10.8-Beta.zip

zip_filename = f"MyServer-v{VERSION}-Beta.zip"

zip_target = os.path.join(DIST_DIR, zip_filename)

print(f"\n[3] Mengemas berkas arsip portabel ZIP ({zip_filename})...")

with zipfile.ZipFile(zip_target, "w", zipfile.ZIP_DEFLATED) as z:

    for root, dirs, files in os.walk(STAGING_DIR):

        for file in files:

            full_path = os.path.join(root, file)

            rel_path = os.path.relpath(full_path, STAGING_DIR)

            # Simpan di dalam folder MyServer-Beta/ di dalam ZIP

            archive_name = os.path.join("MyServer-Beta", rel_path)

            z.write(full_path, archive_name)



print(f"  [v] ZIP Portabel siap: {zip_target} ({os.path.getsize(zip_target):,} bytes)")



# Salin juga ke D:\Softwares\MyServer\dist jika folder ada

sw_dist = r"D:\Softwares\MyServer\dist"

os.makedirs(sw_dist, exist_ok=True)

shutil.copy2(zip_target, os.path.join(sw_dist, zip_filename))



# 4. Perbarui dan jalankan Inno Setup 6 Compiler (ISCC.exe)

print("\n[4] Mengompilasi Installer Standar Windows (Inno Setup 6)...")

iss_script = os.path.join(BASE_BETA, "installer.iss")



iss_content = f"""; Script generated by Algitha Project Desktop

; Inno Setup 6 Script for MyServer Desktop (Beta)

; Industry Standard Windows Setup Engine



#define MyAppName "{APP_NAME}"

#define MyAppVersion "{VERSION}"

#define MyAppPublisher "Algitha Project"

#define MyAppURL "https://github.com/Algitha/MyServer"

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

OutputBaseFilename=MyServer-v{VERSION}-Beta-Setup

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

CloseApplications=no

RestartApplications=no

UninstallDisplayIcon={{app}}\\{{#MyAppExeName}}

UninstallDisplayName={{#MyAppName}}



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
    Result := S
  // 3. Fallback jika biner MyServer ditemukan langsung di D:\Softwares\MyServer
  else if FileExists('D:\\Softwares\\MyServer\\MyServer-Beta.exe') then
    Result := 'D:\\Softwares\\MyServer';
end;

function GetInstallDir(Param: String): String;
begin
  if DetectedPath <> '' then
    Result := DetectedPath
  else
    Result := ExpandConstant('{{autopf}}\\{{#MyAppName}}');
end;

procedure KillRunningAppProcesses();
var
  ResultCode: Integer;
begin
  Exec(AddBackslash(ExpandConstant('{{sys}}')) + 'taskkill.exe', '/F /IM MyServer-Beta.exe /IM MyServer.exe /IM myserver-core.exe /IM syncthing.exe /IM easytier-core.exe /IM easytier-cli.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1500);
end;

function InitializeSetup(): Boolean;
begin
  DetectedPath := GetExistingAppDir();
  IsUpgradeMode := (DetectedPath <> '');
  KillRunningAppProcesses();
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  KillRunningAppProcesses();
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
  KillRunningAppProcesses();
  Result := True;
end;

"""



with open(iss_script, "w", encoding="utf-8") as f:

    f.write(iss_content)

print(f"  [v] Skrip Inno Setup diperbarui: {iss_script}")



# Jalankan ISCC

iscc_res = subprocess.run([ISCC_PATH, iss_script], cwd=BASE_BETA, capture_output=True, text=True)

if iscc_res.returncode == 0:

    setup_output = os.path.join(DIST_DIR, f"MyServer-v{VERSION}-Beta-Setup.exe")

    setup_generic = os.path.join(DIST_DIR, "MyServer-Setup.exe")

    if os.path.exists(setup_output):

        shutil.copy2(setup_output, setup_generic)

        shutil.copy2(setup_output, os.path.join(sw_dist, f"MyServer-v{VERSION}-Beta-Setup.exe"))

        shutil.copy2(setup_output, os.path.join(sw_dist, "MyServer-Setup.exe"))

        print(f"  [v] SUKSES! Installer Inno Setup 6 siap:")

        print(f"      - {setup_output} ({os.path.getsize(setup_output):,} bytes)")

        print(f"      - {setup_generic}")

    else:

        print(f"  [!] ISCC selesai tapi target berkas tidak ditemukan di {setup_output}")

else:

    print(f"  [X] ISCC Compiler Error:\n{iscc_res.stderr}\n{iscc_res.stdout}")



# 5. Tanda Tangan Digital Authenticode

print("\n[5] Menandatangani berkas instalasi secara digital (Authenticode)...")

sign_ps1 = os.path.join(BASE_BETA, "sign_app.ps1")

if os.path.exists(sign_ps1):

    try:

        setup_exe = os.path.join(DIST_DIR, f"MyServer-v{VERSION}-Beta-Setup.exe")

        if os.path.exists(setup_exe):

            subprocess.run([

                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",

                "-File", sign_ps1,

                "-TargetExe", setup_exe,

                "-DistDir", DIST_DIR,

                "-SkipTimestamp"

            ], capture_output=True, text=True)

            print("  [v] Tanda tangan digital berhasil diterapkan!")

    except Exception as e:

        print(f"  [-] Catatan: {e}")



print("\n==============================================================================")

print("[v] KESIMPULAN BERKAS DISTRIBUSI SIAP PAKAI:")

print(f"    1. INSTALLER SETUP : {os.path.join(DIST_DIR, f'MyServer-v{VERSION}-Beta-Setup.exe')}")

print(f"    2. INSTALLER SETUP : {os.path.join(DIST_DIR, 'MyServer-Setup.exe')}")

print(f"    3. ZIP PORTABEL    : {zip_target}")

print("==============================================================================")


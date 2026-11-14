#!/usr/bin/env python3
"""
MyServer Unified Version Synchronizer
Usage: py -3 sync_version.py <version> [channel]
Example: py -3 sync_version.py 3.10.23 Beta
"""

import sys
import re
import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def sync_version(version_str, channel="Beta"):
    clean_ver = version_str.strip().lstrip('v')
    print(f"[*] Menyelaraskan versi MyServer ke: v{clean_ver} ({channel})")

    # 1. myserver_core_service.py (Main & Sandbox)
    for rel_path in ["myserver_core_service.py", os.path.join("sandbox", "myserver_core_service.py")]:
        full_p = os.path.join(ROOT_DIR, rel_path)
        if os.path.exists(full_p):
            with open(full_p, "r", encoding="utf-8") as f:
                c = f.read()
            
            # Ensure APP_VERSION_NUMBER and APP_FULL_VERSION are declared at the top
            if 'APP_VERSION_NUMBER =' not in c:
                c = re.sub(
                    r'(CORE_VERSION\s*=\s*["\'][^"\']+["\'])',
                    f'APP_VERSION_NUMBER = "{clean_ver}"\nCORE_VERSION = f"{{APP_VERSION_NUMBER}}-beta"\nAPP_FULL_VERSION = f"MyServer v{{APP_VERSION_NUMBER}} [{channel}]"',
                    c,
                    count=1
                )
            else:
                c = re.sub(r'APP_VERSION_NUMBER\s*=\s*["\'][^"\']+["\']', f'APP_VERSION_NUMBER = "{clean_ver}"', c)
                c = re.sub(r'CORE_VERSION\s*=\s*["\'][^"\']+["\']', f'CORE_VERSION = f"{{APP_VERSION_NUMBER}}-beta"', c)
                c = re.sub(r'APP_FULL_VERSION\s*=\s*["\'][^"\']+["\']', f'APP_FULL_VERSION = f"MyServer v{{APP_VERSION_NUMBER}} [{channel}]"', c)
            
            # Replace hardcoded versions in getServerDetails, check_update, etc.
            c = re.sub(r'"appVersion":\s*["\'][0-9\.]+["\']', '"appVersion": APP_VERSION_NUMBER', c)
            c = re.sub(r'"fullVersion":\s*["\']MyServer v[0-9\.]+ \[[^\]]+\]["\']', '"fullVersion": APP_FULL_VERSION', c)
            c = re.sub(r'self\._send_json\(\{"upToDate":\s*True,\s*"version":\s*["\'][0-9\.]+["\']\}\)', 'self._send_json({"upToDate": True, "version": APP_VERSION_NUMBER})', c)
            
            with open(full_p, "w", encoding="utf-8") as f:
                f.write(c)
            print(f"  [v] {rel_path} tersinkronisasi.")

    # 2. version.ts
    ver_ts = os.path.join(ROOT_DIR, "MyServer Desktop Companion UI", "src", "companion", "version.ts")
    if os.path.exists(ver_ts):
        with open(ver_ts, "w", encoding="utf-8") as f:
            f.write(f'export const APP_VERSION = "{clean_ver}"\nexport const APP_CHANNEL = "{channel}"\n')
        print(f"  [v] version.ts tersinkronisasi ({clean_ver}, {channel}).")


    # 2b. package.json
    pkg_json = os.path.join(ROOT_DIR, "MyServer Desktop Companion UI", "package.json")
    if os.path.exists(pkg_json):
        with open(pkg_json, "r", encoding="utf-8") as f:
            c = f.read()
        c = re.sub(r'"version":\s*"[0-9\.]+"', f'"version": "{clean_ver}"', c, count=1)
        with open(pkg_json, "w", encoding="utf-8") as f:
            f.write(c)
        print(f"  [v] package.json tersinkronisasi ({clean_ver}).")

    # 3b. Cargo.lock
    cargo_lock = os.path.join(ROOT_DIR, "src-tauri", "Cargo.lock")
    if os.path.exists(cargo_lock):
        with open(cargo_lock, "r", encoding="utf-8") as f:
            c = f.read()
        c = re.sub(r'(name = "app"\r?\nversion = )"[0-9\.]+"', rf'\g<1>"{clean_ver}"', c, count=1)
        with open(cargo_lock, "w", encoding="utf-8") as f:
            f.write(c)
        print(f"  [v] src-tauri/Cargo.lock tersinkronisasi ({clean_ver}).")

    # 3. Cargo.toml
    for c_rel in [os.path.join("src-tauri", "Cargo.toml"), os.path.join("sandbox", "tauri_shell", "src-tauri", "Cargo.toml")]:
        cargo_p = os.path.join(ROOT_DIR, c_rel)
        if os.path.exists(cargo_p):
            with open(cargo_p, "r", encoding="utf-8") as f:
                c = f.read()
            c = re.sub(r'version\s*=\s*"[0-9\.]+"', f'version = "{clean_ver}"', c, count=1)
            with open(cargo_p, "w", encoding="utf-8") as f:
                f.write(c)
            print(f"  [v] {c_rel} tersinkronisasi.")

    # 4. tauri.conf.json
    for t_rel in [os.path.join("src-tauri", "tauri.conf.json"), os.path.join("sandbox", "tauri_shell", "src-tauri", "tauri.conf.json")]:
        tauri_p = os.path.join(ROOT_DIR, t_rel)
        if os.path.exists(tauri_p):
            with open(tauri_p, "r", encoding="utf-8") as f:
                c = f.read()
            c = re.sub(r'"version":\s*"[0-9\.]+"', f'"version": "{clean_ver}"', c, count=1)
            with open(tauri_p, "w", encoding="utf-8") as f:
                f.write(c)
            print(f"  [v] {t_rel} tersinkronisasi.")

    # 5. build_installer_package.py
    bld_p = os.path.join(ROOT_DIR, "build_installer_package.py")
    if os.path.exists(bld_p):
        with open(bld_p, "r", encoding="utf-8") as f:
            c = f.read()
        c = re.sub(r'VERSION\s*=\s*"[0-9\.]+"', f'VERSION = "{clean_ver}"', c, count=1)
        with open(bld_p, "w", encoding="utf-8") as f:
            f.write(c)
        print(f"  [v] build_installer_package.py tersinkronisasi.")

    # 6. installer.iss
    iss_p = os.path.join(ROOT_DIR, "installer.iss")
    if os.path.exists(iss_p):
        with open(iss_p, "r", encoding="utf-8") as f:
            c = f.read()
        c = re.sub(r'#define MyAppVersion\s*"[0-9\.]+"', f'#define MyAppVersion "{clean_ver}"', c)
        c = re.sub(r'OutputBaseFilename=MyServer-v[0-9\.]+-Beta-Setup', f'OutputBaseFilename=MyServer-v{clean_ver}-Beta-Setup', c)
        with open(iss_p, "w", encoding="utf-8") as f:
            f.write(c)
        print(f"  [v] installer.iss tersinkronisasi.")

    # 7. changelog_manager.py
    chg_p = os.path.join(ROOT_DIR, "changelog_manager.py")
    if os.path.exists(chg_p):
        with open(chg_p, "r", encoding="utf-8") as f:
            c = f.read()
        if f'"version": "{clean_ver}"' not in c:
            new_entry = f'''    {{
        "version": "{clean_ver}",
        "channel": "{channel}",
        "date": "2026-10-30",
        "highlights": [
            "Dekopel total arsitektur loading skeleton: Telemetri Monitoring (TrayDock) vs Menu Utama (HomeView) berjalan mandiri & paralel berbasis Data-Ready Trigger nyata.",
            "Perbaikan hilangnya animated skeleton pada cold-start (TrayDock scanning wave aktif sejak milidetik pertama).",
            "Penyelarasan tipografi font chip rute (WAN) dengan chip akun (Marcom) secara konsisten.",
            "Sinkronisasi nomor versi tunggal (Single Source of Truth) di seluruh lapisan sistem MyServer."
        ]
    }},
'''
            c = c.replace('CHANGELOG_HISTORY = [\n', f'CHANGELOG_HISTORY = [\n{new_entry}')
            with open(chg_p, "w", encoding="utf-8") as f:
                f.write(c)
        print(f"  [v] changelog_manager.py tersinkronisasi.")

    print("\n[v] SEMUA BERKAS RESMI TELAH TERHUBUNG KE SINGLE SOURCE OF TRUTH VERSI!")

if __name__ == "__main__":
    v = sys.argv[1] if len(sys.argv) > 1 else "3.10.23"
    c = sys.argv[2] if len(sys.argv) > 2 else "Beta"
    sync_version(v, c)

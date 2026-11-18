# -*- coding: utf-8 -*-
"""
Generator metadata Windows PE Version Information (file_version_info.txt)
dan sinkronisasi versi app.manifest untuk myserver-core.exe.
"""

import os
import re
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def detect_app_version(default="4.6.0"):
    """Membaca APP_VERSION_NUMBER dari myserver_core_service.py secara statis."""
    core_path = os.path.join(ROOT_DIR, "myserver_core_service.py")
    if os.path.exists(core_path):
        try:
            with open(core_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(4096)
            m = re.search(r'APP_VERSION_NUMBER\s*=\s*["\']([^"\']+)["\']', content)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
    return default


def parse_version_tuple(version_str):
    """Mengonversi string versi semver menjadi tuple 4 integer untuk Windows PE."""
    clean = str(version_str or "").strip().lstrip("vV")
    parts = [int(p) for p in re.split(r"[^0-9]+", clean) if p.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def build_version_info_content(version_str, channel="Beta"):
    """Membentuk konten resource VSVersionInfo untuk PyInstaller myserver-core.spec."""
    v_tuple = parse_version_tuple(version_str)
    v_quad = ".".join(str(x) for x in v_tuple)
    v_short = ".".join(str(x) for x in v_tuple[:3])

    return (
        "# UTF-8\n"
        f"# Windows PE Version Information Resource File for MyServer Core Service ({channel})\n"
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={v_tuple},\n"
        f"    prodvers={v_tuple},\n"
        "    mask=0x3f,\n"
        "    flags=0x0,\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo(\n"
        "      [\n"
        "        StringTable(\n"
        "          '040904b0',\n"
        "          [\n"
        "            StringStruct('CompanyName', 'Project Algitha'),\n"
        f"            StringStruct('FileDescription', 'MyServer Core Service ({channel})'),\n"
        f"            StringStruct('FileVersion', '{v_quad}'),\n"
        "            StringStruct('InternalName', 'myserver-core'),\n"
        "            StringStruct('LegalCopyright', 'Copyright (C) 2026 Project Algitha. All rights reserved.'),\n"
        "            StringStruct('OriginalFilename', 'myserver-core.exe'),\n"
        "            StringStruct('ProductName', 'MyServer Desktop'),\n"
        f"            StringStruct('ProductVersion', '{v_short}'),\n"
        "            StringStruct('Comments', 'MyServer Companion Background Core Service - Project Algitha')\n"
        "          ]\n"
        "        )\n"
        "      ]\n"
        "    ),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n"
    )


def update_manifest_version(version_str, manifest_path=None):
    """Menyelaraskan atribut version pada assemblyIdentity di app.manifest."""
    target = manifest_path or os.path.join(ROOT_DIR, "app.manifest")
    if not os.path.exists(target):
        return False
    v_quad = ".".join(str(x) for x in parse_version_tuple(version_str))
    with open(target, "r", encoding="utf-8") as f:
        text = f.read()
    updated = re.sub(
        r'(<assemblyIdentity\b[^>]*\bversion=")[^"]*(")',
        rf"\g<1>{v_quad}\g<2>",
        text,
        count=1,
    )
    if updated != text:
        with open(target, "w", encoding="utf-8") as f:
            f.write(updated)
    return True


def generate_version_info(version_str=None, channel="Beta", output_path=None, manifest_path=None):
    """Menulis file_version_info.txt dan memperbarui app.manifest."""
    resolved_ver = (version_str or detect_app_version()).strip().lstrip("vV")
    target = output_path or os.path.join(ROOT_DIR, "file_version_info.txt")
    content = build_version_info_content(resolved_ver, channel=channel)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    update_manifest_version(resolved_ver, manifest_path=manifest_path)
    return target


if __name__ == "__main__":
    arg_ver = sys.argv[1] if len(sys.argv) > 1 else None
    arg_chan = sys.argv[2] if len(sys.argv) > 2 else "Beta"
    out = generate_version_info(arg_ver, arg_chan)
    print(f"[v] file_version_info.txt generated: {out} (v{arg_ver or detect_app_version()} {arg_chan})")

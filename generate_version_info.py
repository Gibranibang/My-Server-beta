# -*- coding: utf-8 -*-
"""
Helper script to generate PyInstaller Windows PE Version Information (file_version_info.txt).
Menyematkan metadata resmi Windows (Company, Description, Copyright, Version)
untuk mengurangi false positive antivirus (SmartScreen / Windows Defender).
"""

import sys
import os

try:
    import zimaos_app
    app_version = getattr(zimaos_app, "APP_VERSION", "3.8.0")
    app_channel = getattr(zimaos_app, "APP_CHANNEL", "Beta")
except Exception:
    app_version = "3.8.0"
    app_channel = "Beta"

# Parse version tuple
parts = [int(p) for p in app_version.split(".") if p.isdigit()]
while len(parts) < 4:
    parts.append(0)
version_tuple = tuple(parts[:4])
version_str = ".".join(str(p) for p in version_tuple)

content = f"""# UTF-8
# Windows PE Version Information Resource File for MyServer Desktop ({app_channel})
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904b0',
          [
            StringStruct('CompanyName', 'Project Algitha'),
            StringStruct('FileDescription', 'MyServer Desktop Client ({app_channel})'),
            StringStruct('FileVersion', '{version_str}'),
            StringStruct('InternalName', 'MyServer-{app_channel}'),
            StringStruct('LegalCopyright', 'Copyright (C) 2026 Project Algitha. All rights reserved.'),
            StringStruct('OriginalFilename', 'MyServer-{app_channel}.exe'),
            StringStruct('ProductName', 'MyServer Desktop'),
            StringStruct('ProductVersion', '{app_version}'),
            StringStruct('Comments', 'MyServer Client by Algitha - Native ZimaOS Client')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "file_version_info.txt")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"[v] Berkas versi PE Windows berhasil dibuat: {output_path} (v{app_version})")

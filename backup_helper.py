"""
Targeted Pre-Modification Backup Helper untuk MyServer Desktop
Aturan Wajib Project Owner:
Hanya mencadangkan (backup) berkas yang MEMANG AKAN DIUBAH / DIMODIFIKASI pada sesi tersebut.
Dilarang membackup berkas yang tidak disentuh demi efisiensi memori dan ruang penyimpanan.

Format direktori: <Kanal>/backup/YYYY-MM-DD_HH-mm/

Penggunaan CLI:
    python backup_helper.py <file1> [file2] [file3] ... [--session NAMA_SESI]
Contoh:
    python backup_helper.py zimaos_app.py
"""

import os
import shutil
import sys
from datetime import datetime


def create_targeted_backup(target_files=None, channel_dir=None, session_name=None):
    if not channel_dir:
        channel_dir = os.path.dirname(os.path.abspath(__file__))

    channel_name = os.path.basename(channel_dir)
    backup_base = os.path.join(channel_dir, "backup")
    os.makedirs(backup_base, exist_ok=True)

    if not session_name:
        session_name = datetime.now().strftime("%Y-%m-%d_%H-%M")

    target_backup_dir = os.path.join(backup_base, session_name)
    os.makedirs(target_backup_dir, exist_ok=True)

    if not target_files:
        print("[!] PERINGATAN: Tidak ada berkas target yang ditentukan.")
        print("    Berdasarkan mandat Project Owner: HANYA berkas yang akan diubah/dimodifikasi yang dicadangkan.")
        print("    Gunakan: python backup_helper.py <berkas_yang_akan_diubah_1> [berkas_2] ...")
        return None

    copied_count = 0
    total_bytes = 0
    copied_files_info = []

    for file_path in target_files:
        if os.path.isabs(file_path):
            src_file = os.path.normpath(file_path)
        else:
            cand1 = os.path.normpath(os.path.join(os.getcwd(), file_path))
            cand2 = os.path.normpath(os.path.join(channel_dir, file_path))
            if os.path.isfile(cand1):
                src_file = cand1
            elif os.path.isfile(cand2):
                src_file = cand2
            else:
                src_file = cand1

        if not os.path.isfile(src_file):
            print(f"[-] Berkas tidak ditemukan (dilewati): {file_path}")
            continue

        try:
            rel_path = os.path.relpath(src_file, channel_dir)
            if rel_path.startswith(".."):
                rel_path = os.path.basename(src_file)
        except ValueError:
            rel_path = os.path.basename(src_file)

        dest_file = os.path.join(target_backup_dir, rel_path)
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)

        shutil.copy2(src_file, dest_file)
        file_size = os.path.getsize(src_file)
        copied_count += 1
        total_bytes += file_size
        copied_files_info.append((rel_path, file_size))

    if copied_count > 0:
        size_kb = round(total_bytes / 1024, 2)
        print(f"[v] Targeted Pre-Modification Backup Berhasil!")
        print(f"    Kanal       : {channel_name}")
        print(f"    Sesi        : {session_name}")
        print(f"    Lokasi      : {target_backup_dir}")
        print(f"    Total Berkas: {copied_count} file ({size_kb} KB)")
        print("    Daftar Berkas yang Dicadangkan:")
        for r_path, f_sz in copied_files_info:
            print(f"      - {r_path} ({round(f_sz / 1024, 2)} KB)")
        return target_backup_dir
    else:
        print("[!] Tidak ada berkas valid yang berhasil dicadangkan.")
        return None


if __name__ == "__main__":
    args = sys.argv[1:]
    target_files = []
    session = None

    i = 0
    while i < len(args):
        if args[i] == "--session" and i + 1 < len(args):
            session = args[i + 1]
            i += 2
        elif args[i] == "--all":
            print("[!] Mode --all tidak disarankan. Mandat Project Owner mengharuskan targeted backup berkas yang dimodifikasi saja.")
            i += 1
        else:
            target_files.append(args[i])
            i += 1

    if not target_files:
        print("=== TARGETED PRE-MODIFICATION BACKUP HELPER ===")
        print("Aturan Mandat Project Owner:")
        print("Hanya cadangkan berkas yang AKAN dimodifikasi untuk efisiensi penyimpanan dan memori.")
        print("\nPenggunaan:")
        print("    python backup_helper.py <file1> [file2] [file3] ... [--session NAMA_SESI]")
        print("\nContoh:")
        print("    python backup_helper.py zimaos_app.py")
        sys.exit(1)

    create_targeted_backup(target_files=target_files, session_name=session)

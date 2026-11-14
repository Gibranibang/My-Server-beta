"""
Wake on LAN (WoL) Manager for MyServer Desktop (v3.6.9 Alpha)
Modul pengontrol transmisi Magic Packet (UDP Broadcast), validasi & deteksi MAC Address via ARP.
"""

import os
import re
import socket
import subprocess
import sys
import time


def validate_mac_address(mac_address):
    """
    Memeriksa apakah string merupakan format MAC Address yang valid.
    Menerima format dengan pemisah (00:11:22:33:44:55 / 00-11-22-33-44-55) maupun raw 12 karakter hex.
    """
    if not mac_address or not isinstance(mac_address, str):
        return False
    clean = re.sub(r'[^0-9A-Fa-f]', '', mac_address)
    return len(clean) == 12


def normalize_mac_address(mac_address, delimiter=":"):
    """
    Menstandarkan format MAC Address menjadi format uppercase berpemisah (default ':').
    Contoh output: '52:17:52:E9:6E:06'
    """
    if not mac_address or not isinstance(mac_address, str):
        raise ValueError("MAC Address kosong atau bukan string.")
    clean = re.sub(r'[^0-9A-Fa-f]', '', mac_address).upper()
    if len(clean) != 12:
        raise ValueError(f"Format MAC Address tidak valid: '{mac_address}' (harus 12 karakter heksadesimal).")
    return delimiter.join(clean[i:i+2] for i in range(0, 12, 2))


def build_magic_packet(mac_address):
    """
    Menyusun paket data Magic Packet standar AMD/Wake-on-LAN (102 byte).
    Terdiri dari 6 byte 0xFF diikuti oleh MAC Address tujuan yang diulang sebanyak 16 kali.
    """
    clean = re.sub(r'[^0-9A-Fa-f]', '', mac_address)
    if len(clean) != 12:
        raise ValueError(f"Format MAC Address tidak valid: '{mac_address}' (harus 12 karakter heksadesimal).")

    mac_bytes = bytes.fromhex(clean)
    magic_packet = (b'\xff' * 6) + (mac_bytes * 16)
    if len(magic_packet) != 102:
        raise ValueError("Ukuran Magic Packet tidak sesuai (harus tepat 102 byte).")
    return magic_packet


def send_magic_packet(mac_address, broadcast_ip="255.255.255.255", port=9, repeat=3):
    """
    Mengirim Magic Packet melalui socket UDP Broadcast ke jaringan lokal.
    Menggunakan transmisi burst (default 3x) untuk memastikan paket tidak tereduksi oleh switch/router.
    """
    try:
        clean_broadcast = str(broadcast_ip).strip() or "255.255.255.255"
        try:
            port_num = int(port) if port else 9
        except (ValueError, TypeError):
            port_num = 9

        packet = build_magic_packet(mac_address)
        norm_mac = normalize_mac_address(mac_address)

        sent_count = 0
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for i in range(max(1, int(repeat))):
                sock.sendto(packet, (clean_broadcast, port_num))
                sent_count += 1
                if i < repeat - 1:
                    time.sleep(0.05)

        return True, f"Berhasil mengirim {sent_count}x Magic Packet ke {norm_mac} via {clean_broadcast}:{port_num}"
    except Exception as e:
        return False, str(e)


def detect_mac_from_arp(target_host_or_ip):
    """
    Mendeteksi MAC address perangkat secara otomatis dari tabel ARP Windows.
    Menerima host, domain lokal, atau IP address langsung.
    """
    if not target_host_or_ip:
        return None

    clean_target = str(target_host_or_ip).replace("http://", "").replace("https://", "").split(":")[0].strip()
    resolved_ip = clean_target

    # Jika target berupa hostname/domain lokal, coba resolve IP-nya
    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', clean_target):
        try:
            resolved_ip = socket.gethostbyname(clean_target)
        except Exception:
            resolved_ip = clean_target

    creationflags = 0x08000000 if sys.platform == "win32" else 0
    try:
        # Jalankan arp -a
        cmd = ["arp", "-a"]
        if resolved_ip and re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', resolved_ip):
            cmd.append(resolved_ip)

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            timeout=3.0,
        )
        if res.stdout:
            lines = res.stdout.splitlines()
            for line in lines:
                if resolved_ip in line or clean_target in line:
                    match = re.search(
                        r'([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})',
                        line
                    )
                    if match:
                        found_mac = match.group(1).replace("-", ":").upper()
                        # Jangan ambil broadcast/multicast MAC seperti FF-FF-FF-FF-FF-FF
                        if found_mac != "FF:FF:FF:FF:FF:FF" and not found_mac.startswith("01:00:5E"):
                            return found_mac
    except Exception:
        pass

    return None


def get_wol_guidance_text(language="id"):
    """
    Mengembalikan teks penjelasan dan panduan persyaratan teknis fitur Wake on LAN.
    """
    if language == "id":
        return {
            "title": "Panduan & Persyaratan Fitur Wake on LAN (WoL)",
            "summary": (
                "Fitur Wake on LAN memungkinkan Anda menyalakan atau membangunkan server dari kondisi mati (S5), "
                "tidur (sleep), atau suspend dari jarak jauh melalui jaringan lokal menggunakan Magic Packet."
            ),
            "requirements": [
                "1. Kabel LAN Fisik (Ethernet): Server wajib terhubung menggunakan kabel LAN ke router/switch (WoL tidak bekerja via Wi-Fi biasa).",
                "2. Pengaturan BIOS / UEFI Motherboard: Opsi 'Wake on LAN', 'Power On By PCI-E', atau 'PCIe PME Event' harus dalam posisi AKTIF (Enabled).",
                "3. Sumber Daya Listrik: Kabel power server tetap terhubung ke listrik agar kartu jaringan (NIC) tetap menerima standby power (biasanya lampu port LAN berkedip saat server mati).",
                "4. Satu Jaringan Lokal: Laptop pengirim dan server harus berada di jaringan/subnet lokal yang sama agar Magic Packet broadcast dapat sampai.",
                "5. Pengaturan OS (Linux/ZimaOS): Pastikan driver jaringan mengizinkan wake paket (misal: 'ethtool -s eth0 wol g')."
            ],
            "note": "Catatan: Jika server Anda belum mendukung WoL di tingkat BIOS/hardware, Anda tetap dapat menyimpan konfigurasi ini untuk digunakan saat server sudah siap.",
        }
    else:
        return {
            "title": "Wake on LAN (WoL) Setup Guide & Requirements",
            "summary": (
                "Wake on LAN allows you to remotely power on or wake your server from off (S5), sleep, "
                "or suspend state over your local network using Magic Packets."
            ),
            "requirements": [
                "1. Physical Ethernet Cable: Server must be connected via LAN cable to router/switch (WoL standard does not work over regular Wi-Fi).",
                "2. BIOS / UEFI Settings: 'Wake on LAN', 'Power On By PCI-E', or 'PCIe PME Event' must be ENABLED in your motherboard BIOS/UEFI.",
                "3. Standby Power: Server power supply must stay plugged in so the network card receives standby power (LAN LED blinks while powered off).",
                "4. Same Local Network: Sending laptop and server must be on the same local subnet for UDP broadcast delivery.",
                "5. OS Settings (Linux/ZimaOS): Ensure network interface permits wake packets (e.g. 'ethtool -s eth0 wol g')."
            ],
            "note": "Note: If your server hardware does not currently support WoL in BIOS, you can still save this configuration in advance for when it is ready.",
        }

### ==============================================================================
### MODULE: Changelog Manager & Auto-Sync
### Features:
### 1. Centralized Version & Release Notes Database
### 2. Auto-Generation of CHANGELOG.txt and CHANGELOG.md
### 3. Integrated Build-Time & Runtime Changelog Extraction
### ==============================================================================

import os
import sys
from datetime import datetime

CHANGELOG_HISTORY = [
    {
        "version": "4.5.5",
        "channel": "Beta",
        "date": "2026-11-10",
        "title": "Optimistic Inline Soft-Delete VM, Eliminasi Latensi Probing Antrean Soket, dan Pembaruan Atomik Automasi VM",
        "notes": [
            "Optimistic Inline Card Degradation: Penghapusan VM kini menutup dialog seketika (0ms) dengan status visual inline 'Menghapus...' tanpa memblokir layar pengguna, serta mempertahankan tombstone 30 detik untuk meredam respons polling tertunda.",
            "Eliminasi Latensi Probing Soket: Menambahkan cache rute backend 25 detik pada Core Service sehingga operasi penghapusan VM berlangsung sub-detik (<1s) tanpa kemacetan antrean IPC Tauri 60 detik.",
            "Pembaruan Pengaturan VM Atomik: Menambahkan endpoint atomik /api/vms/update (PUT /api/v1/vms/{id}) untuk saklar Always-On 24/7, Auto-On, dan Auto-Restart sehingga pengaturan tersimpan permanen dan tidak membal kembali akibat polling berkala.",
            "Sinkronisasi Nilai Boolean & Array Jadwal: Menyelaraskan konversi camelCase dan snake_case antara Desktop dan ZimaOS Backend v1.2.3 sehingga nilai false dan daftar hari dihormati secara presisi."
        ],
        "features": [
            "Optimistic Inline Soft-Delete VM (Non-Blocking UX)",
            "Cache Rute Backend Sub-Detik (Bebas Antrean Soket)",
            "Endpoint Atomik /api/vms/update (PUT /api/v1/vms/{id})",
            "Harmonisasi Nilai Boolean Automasi (Always-On, Auto-On, Auto-Restart)"
        ]
    },
    {
        "version": "4.5.4",
        "channel": "Beta",
        "date": "2026-11-10",
        "title": "Perbaikan Hapus VM Multi-Perangkat (Zero Zombie VM), Dedicated Delete API, dan Sinkronisasi Real-Time",
        "notes": [
            "Dedicated API Hapus VM Server: Menambahkan endpoint resmi /api/vms/delete pada Core Service dan pemanggilan langsung HTTP DELETE ke Backend ZimaOS saat pengguna mengonfirmasi penghapusan di VM Manager.",
            "Eliminasi Zombie VM Resurrection Loop: Menghapus loop pembangkitan VM usang dari cache lokal, menjadikan database Backend ZimaOS sebagai sumber kebenaran mutlak (authoritative source of truth).",
            "Pemisahan Polling Telemetri dari Penyimpanan: Memisahkan pembaruan berkala CPU/RAM/runtime agar tidak memicu auto-save ke server yang berpotensi me-rePOST VM yang telah dihapus oleh perangkat lain.",
            "Sinkronisasi Multi-Perangkat Otomatis: Menambahkan auto-sync polling setiap 10 detik dan listener fokus jendela (window focus) untuk sinkronisasi seketika antar-perangkat pendamping."
        ],
        "features": [
            "Dedicated Delete API /api/vms/delete ke Backend ZimaOS",
            "Pemusnahan Zombie VM Resurrection Loop",
            "Isolasi Background Telemetry dari Auto-Save Server",
            "Auto-Sync Multi-Device Real-Time (10s & Window Focus)"
        ]
    },
    {
        "version": "4.5.3",
        "channel": "Beta",
        "date": "2026-11-10",
        "title": "1-Klik Remote Install & Update OTA Backend ZimaOS, Eliminasi Socket WinError 10054, dan Sinkronisasi Telemetri & Runtime Murni InstaBox",
        "notes": [
            "1-Klik Pasang & Perbarui OTA MyServer Backend ke ZimaOS: Menambahkan tombol dinamis pada antarmuka ServerView untuk memasang (fresh install) atau memperbarui (update OTA) backend ZimaOS ke versi 1.2.2 langsung dari desktop tanpa terminal manual.",
            "Eliminasi Tuntas Socket WinError 10054 (Reset by Peer): Mengimplementasikan header eksplisit Connection: close dan mekanisme auto-retry 1x pada seluruh transmisi HTTP ke backend ZimaOS, menjamin transmisi REST API bebas kegagalan soket terputus.",
            "Penyingkiran Timer Inflasi Runtime & Pembersihan Telemetri Fiktif: Menghapus timer interval increment fiktif di sisi frontend, membaca nilai runtime murni dari API InstaBox, serta membersihkan cache telemetri palsu (2.3% CPU / 0.7 GB RAM) sehingga status mesin berstatus tidur menampilkan strip (-) secara jujur.",
            "Sinkronisasi Status Port & Host SSH MicroVM Resmi: Memperbaiki format host SSH agar selalu menampilkan alamat resmi ssh.instabox.sh:2222 secara konsisten dan meniadakan tampilan host kosong."
        ],
        "features": [
            "1-Klik Remote Install & Update OTA MyServer Backend v1.2.2",
            "Eliminasi Socket WinError 10054 via Connection: Close & Auto-Retry",
            "Sinkronisasi Runtime Murni Cloud InstaBox (Hapus Timer Fiktif)",
            "Pembersihan Cache Telemetri Statis & Format Host SSH Resmi"
        ]
    },
    {
        "version": "4.5.2",
        "channel": "Beta",
        "date": "2026-11-10",
        "title": "Pengalihan Otomatis Rute WAN SSH via Remote P2P, Resolusi Backend API WAN, Persistensi Otomasi 24/7 & Sinkronisasi InstaBox",
        "notes": [
            "Pengalihan Otomatis Rute Terminal SSH via Remote P2P saat Rute WAN Aktif: Terminal SSH ZimaOS secara cerdas mendeteksi rute WAN dan secara otomatis mengalihkan target koneksi ke Virtual IP Remote P2P (EasyTier / ZeroTier) di mana port 22 terbuka, persis seperti mekanisme akses Web App dan mount SMB.",
            "Resolusi Cerdas REST API Backend ZimaOS pada Jaringan Eksternal (WAN): Memperbaiki kegagalan koneksi REST API backend (port 8080) saat pengguna berada di luar jaringan rumah dengan mengalihkan endpoint backend ke Remote P2P IP secara dinamis, sehingga daftar VM sisi server tidak lagi menghilang.",
            "Penyelarasan Schema Pydantic Backend ZimaOS (v1.2.1) & Persistensi Otomasi 24/7: Menyelaraskan field schema Pydantic untuk menerima format camelCase dari desktop (keepAliveEnabled, apiKey, machineId, runtimeMinutes) serta membongkar struktur nested autoRestart dan autoOn, menjamin otomasi tersimpan di SQLite server dan tersinkronisasi 100% antar-perangkat.",
            "Sinkronisasi Status Riil VM InstaBox (Case-Insensitive) & Durasi Timer Uptime: Memperbaiki pengecekan status microVM menjadi case-insensitive (running / active), membaca durasi runtime riil dari API InstaBox (currentRunSeconds / uptimeSeconds), serta memperbaiki interval loop scheduler server berbasis timestamp riil untuk mencegah inflasi waktu runtime."
        ],
        "features": [
            "Pengalihan Otomatis Rute Terminal SSH via Remote P2P saat Rute WAN Aktif",
            "Resolusi Cerdas REST API Backend ZimaOS pada Jaringan Eksternal (WAN)",
            "Penyelarasan Schema Pydantic Backend ZimaOS (v1.2.1) & Persistensi Otomasi 24/7",
            "Sinkronisasi Status Riil VM InstaBox (Case-Insensitive) & Durasi Timer Uptime"
        ]
    },
    {
        "version": "3.12.0",
        "channel": "Beta",
        "date": "2026-11-01",
        "title": "GitHub Integration, Resilient Installer Auto-Close, Accordion UI Overhaul, & Diagnostic Log Tools",
        "notes": [
            "GitHub Releases API Update Checker: Menghubungkan pemeriksaan versi otomatis aplikasi ke repositori resmi GitHub (Gibranibang/My-Server-beta) secara real-time dengan semantic versioning comparison.",
            "Perbaikan Ekstraksi & Eksekusi Update ZIP: Menyempurnakan apply_zip_update() untuk memprioritaskan biner utama MyServer-Beta.exe, mengeliminasi konflik penguncian syncthing.exe, dan memproteksi konfigurasi pengguna (Pasal 2).",
            "Auto-Close Installer Inno Setup: Mengintegrasikan skrip Pascal KillRunningProcesses untuk menutup seluruh proses latar belakang (MyServer-Beta.exe, myserver-core.exe, syncthing.exe) saat installer dijalankan, menghapus tuntas error file lock 'DeleteFile failed'.",
            "Overhaul Sub-Menu Options (Accordion Style): Merestrukturisasi antarmuka Options menjadi 4 seksi akordeon interaktif (Sistem & Startup, Bahasa & Keamanan, Integrasi Storage & Jaringan, Diagnostik & Log), serta mengeliminasi toggle obsolete.",
            "Hero Header & Ikon Resmi MyServer: Memperbesar dan menengahkan ikon resmi MyServer (favicon.png 64px) di bagian paling atas sub-menu Options, diikuti identitas versi dan tombol pembaruan.",
            "Pengembalian Fitur Copy Log & Save Log: Menghadirkan kembali tombol Salin Log ke Clipboard sistem dengan notifikasi instan serta dialog penyimpanan berkas SaveFileDialog native Windows untuk diagnostik mandiri."
        ],
        "features": [
            "GitHub Releases API Update Checker: Menghubungkan pemeriksaan versi otomatis aplikasi ke repositori resmi GitHub (Gibranibang/My-Server-beta) secara real-time dengan semantic versioning comparison.",
            "Perbaikan Ekstraksi & Eksekusi Update ZIP: Menyempurnakan apply_zip_update() untuk memprioritaskan biner utama MyServer-Beta.exe, mengeliminasi konflik penguncian syncthing.exe, dan memproteksi konfigurasi pengguna (Pasal 2).",
            "Auto-Close Installer Inno Setup: Mengintegrasikan skrip Pascal KillRunningProcesses untuk menutup seluruh proses latar belakang (MyServer-Beta.exe, myserver-core.exe, syncthing.exe) saat installer dijalankan, menghapus tuntas error file lock 'DeleteFile failed'.",
            "Overhaul Sub-Menu Options (Accordion Style): Merestrukturisasi antarmuka Options menjadi 4 seksi akordeon interaktif (Sistem & Startup, Bahasa & Keamanan, Integrasi Storage & Jaringan, Diagnostik & Log), serta mengeliminasi toggle obsolete.",
            "Hero Header & Ikon Resmi MyServer: Memperbesar dan menengahkan ikon resmi MyServer (favicon.png 64px) di bagian paling atas sub-menu Options, diikuti identitas versi dan tombol pembaruan.",
            "Pengembalian Fitur Copy Log & Save Log: Menghadirkan kembali tombol Salin Log ke Clipboard sistem dengan notifikasi instan serta dialog penyimpanan berkas SaveFileDialog native Windows untuk diagnostik mandiri."
        ]
    },
    {
        "version": "3.11.5",
        "channel": "Beta",
        "date": "2026-11-01",
        "title": "SMB Drive Card & Chip Interactive Explorer Click Fix",
        "notes": [
            "Aktivasi Event Click Chip Open Explorer: Mengintegrasikan prop onClick langsung pada komponen Chip 'Open Explorer', mengaktifkan rendering tag button interaktif dengan efek hover dan transisi tekan.",
            "Dukungan onClick pada Komponen Card (ui.tsx): Memperluas komponen Card untuk menerima prop onClick dan meneruskannya ke kontainer div DOM utama.",
            "Visual Toast Feedback: Menambahkan notifikasi visual instan 'Opening Windows File Explorer to SMB disk...' saat partisi drive dipilih.",
            "Dual-Engine Explorer Launcher: Menambahkan mekanisme fallback subprocess Popen(explorer.exe) pada smb_mount_manager jika os.startfile terhambat oleh shell desktop."
        ],
        "features": [
            "Aktivasi Event Click Chip Open Explorer: Mengintegrasikan prop onClick langsung pada komponen Chip 'Open Explorer', mengaktifkan rendering tag button interaktif dengan efek hover dan transisi tekan.",
            "Dukungan onClick pada Komponen Card (ui.tsx): Memperluas komponen Card untuk menerima prop onClick dan meneruskannya ke kontainer div DOM utama.",
            "Visual Toast Feedback: Menambahkan notifikasi visual instan 'Opening Windows File Explorer to SMB disk...' saat partisi drive dipilih.",
            "Dual-Engine Explorer Launcher: Menambahkan mekanisme fallback subprocess Popen(explorer.exe) pada smb_mount_manager jika os.startfile terhambat oleh shell desktop."
        ]
    },
    {
        "version": "3.11.4",
        "channel": "Beta",
        "date": "2026-11-01",
        "title": "Clean Standalone Binary Pipeline, Zero-UPX Heuristic Elimination, & Authenticode Code Signing",
        "notes": [
            "Eliminasi Total Kompresi UPX (upx=False): Rekonstruksi berkas spesifikasi kompilasi PyInstaller untuk mematikan kompresi UPX packer, mengeliminasi false positive alarm heuristik Windows Defender (Trojan:Win32/Bearfoos.A!ml).",
            "Sematkan Metadata Windows PE & Manifest Asli: Mengintegrasikan core_version_info.txt (Project Algitha - MyServer Core Service v3.11.4.0) dan app.manifest ke dalam biner PE resmi.",
            "Penandatanganan Digital Authenticode Menyeluruh: Menandatangani secara digital seluruh biner executable internal (myserver-core.exe dan MyServer-Beta.exe) dengan sertifikat Algitha Project Desktop sebelum dipaketkan.",
            "Kemandirian Penuh (Self-Contained Standalone): Menjamin aplikasi 100% mandiri tanpa ketergantungan pada runtime Python eksternal di komputer pengguna/klien."
        ],
        "features": [
            "Eliminasi Total Kompresi UPX (upx=False): Rekonstruksi berkas spesifikasi kompilasi PyInstaller untuk mematikan kompresi UPX packer, mengeliminasi false positive alarm heuristik Windows Defender (Trojan:Win32/Bearfoos.A!ml).",
            "Sematkan Metadata Windows PE & Manifest Asli: Mengintegrasikan core_version_info.txt (Project Algitha - MyServer Core Service v3.11.4.0) dan app.manifest ke dalam biner PE resmi.",
            "Penandatanganan Digital Authenticode Menyeluruh: Menandatangani secara digital seluruh biner executable internal (myserver-core.exe dan MyServer-Beta.exe) dengan sertifikat Algitha Project Desktop sebelum dipaketkan.",
            "Kemandirian Penuh (Self-Contained Standalone): Menjamin aplikasi 100% mandiri tanpa ketergantungan pada runtime Python eksternal di komputer pengguna/klien."
        ]
    },
    {
        "version": "3.11.3",
        "channel": "Beta",
        "date": "2026-11-01",
        "title": "Backup Sync Throughput 3-Row Server-Rack LED Dot Meter & Zero-Shift Persistent Dock",
        "notes": [
            "Backup Sync Throughput 3-Row LED Dot Meter: Menggantikan solid gradient progress bar pada sub-menu Backup & Sync dengan dot matrix SVG 42 kolom x 3 baris (126 LED dots) dengan radius 2.1px dan pitch 6x6px yang identik dengan monitoring dock dan storage meter.",
            "Dynamic Directional Glow & Tone Mapping: Warna LED dots menyesuaikan arah transfer secara presisi (fill-success/hijau untuk download, fill-info/biru untuk upload, dan fill-line/abu-abu netral saat idle).",
            "Zero Cumulative Layout Shift (CLS = 0): Kontainer dock throughput dipertahankan tetap rendered secara persisten saat idle, mengeliminasi layout jump 18px saat sinkronisasi dimulai atau selesai."
        ],
        "features": [
            "Backup Sync Throughput 3-Row LED Dot Meter: Menggantikan solid gradient progress bar pada sub-menu Backup & Sync dengan dot matrix SVG 42 kolom x 3 baris (126 LED dots) dengan radius 2.1px dan pitch 6x6px yang identik dengan monitoring dock dan storage meter.",
            "Dynamic Directional Glow & Tone Mapping: Warna LED dots menyesuaikan arah transfer secara presisi (fill-success/hijau untuk download, fill-info/biru untuk upload, dan fill-line/abu-abu netral saat idle).",
            "Zero Cumulative Layout Shift (CLS = 0): Kontainer dock throughput dipertahankan tetap rendered secara persisten saat idle, mengeliminasi layout jump 18px saat sinkronisasi dimulai atau selesai."
        ]
    },
    {
        "version": "3.11.2",
        "channel": "Beta",
        "date": "2026-11-01",
        "title": "Storage Usage Server-Rack LED Dot Meter & 3-Tier Auto-Layout Anti-Overflow Guard",
        "notes": [
            "Storage Usage Server-Rack LED Dot Meter: Menggantikan bar solid konvensional pada sub-menu Storage & Files dengan 25 titik vektor SVG berkoordinat matematis (viewBox 250x8), di mana 1 titik merepresentasikan 4% kapasitas disk secara simetris.",
            "Dynamic Tone Mapping: Pemetaan warna titik dinamis berdasarkan ambang batas kapasitas (<70% hijau ramah, 70%-85% oranye peringatan, >85% merah kritis, serta abu-abu saat offline/unmounted).",
            "3-Tier Auto-Layout Architecture: Merestrukturisasi kartu drive menjadi 3 tingkat terisolasi: Tier 1 (Header: Ikon, Drive Letter, Truncated Drive Name, dan Protected Action Chip), Tier 2 (LED Dot Meter), dan Tier 3 (Footer: Rincian Kapasitas Bebas/Total dan Persentase Penggunaan).",
            "Zero Text Overflow Guard: Proteksi auto-layout flexbox dengan isolasi shrink-0 pada tombol Open Explorer dan Drive Letter, serta truncate elipsis pada nama partisi panjang, mencegah teks menabrak atau meluap dari batas kartu.",
            "Vertical Balance & UI Equilibrium: Menyelaraskan jarak vertikal elemen dan memberikan feedback visual kapasitas instan (Mono percentage) bagi pengalaman pengguna yang optimal."
        ],
        "features": [
            "Storage Usage Server-Rack LED Dot Meter: Menggantikan bar solid konvensional pada sub-menu Storage & Files dengan 25 titik vektor SVG berkoordinat matematis (viewBox 250x8), di mana 1 titik merepresentasikan 4% kapasitas disk secara simetris.",
            "Dynamic Tone Mapping: Pemetaan warna titik dinamis berdasarkan ambang batas kapasitas (<70% hijau ramah, 70%-85% oranye peringatan, >85% merah kritis, serta abu-abu saat offline/unmounted).",
            "3-Tier Auto-Layout Architecture: Merestrukturisasi kartu drive menjadi 3 tingkat terisolasi: Tier 1 (Header: Ikon, Drive Letter, Truncated Drive Name, dan Protected Action Chip), Tier 2 (LED Dot Meter), dan Tier 3 (Footer: Rincian Kapasitas Bebas/Total dan Persentase Penggunaan).",
            "Zero Text Overflow Guard: Proteksi auto-layout flexbox dengan isolasi shrink-0 pada tombol Open Explorer dan Drive Letter, serta truncate elipsis pada nama partisi panjang, mencegah teks menabrak atau meluap dari batas kartu.",
            "Vertical Balance & UI Equilibrium: Menyelaraskan jarak vertikal elemen dan memberikan feedback visual kapasitas instan (Mono percentage) bagi pengalaman pengguna yang optimal."
        ]
    },
    {
        "version": "3.11.1",
        "channel": "Beta",
        "date": "2026-11-01",
        "title": "Vectorized Zero-Drift Telemetry Dot Matrix & Docker App Credential Boundary Guard",
        "notes": [
            "Vectorized Zero-Drift Telemetry Dot Matrix: Mengganti 18 elemen <span> CSS Grid dengan satu elemen SVG vektor murni berkoordinat matematis (viewBox 36x18). Mengunci aspek rasio 1:1 circular LED matrix dan mengeliminasi distorsi pil lonjong pada Windows Display Scaling (125%-175%).",
            "Multi-DPI Subpixel Precision: Mengeliminasi celah belang antar-kolom akibat pembulatan subpixel snapping DirectWrite/Blink pada monitor laptop resolusi tinggi.",
            "Skeleton Meter Harmonization: Menyelaraskan status loading telemetri ke geometri SVG yang sama persis, menghasilkan Zero Layout Shift (CLS = 0) saat transisi data masuk.",
            "Docker App Credential Boundary Guard: Mencegah injeksi otomatis username dan password root ZimaOS ke form login aplikasi pihak ketiga (Nextcloud, qBittorrent, Transmission, Jellyfin, Portainer, dll.).",
            "Triple-Layer Security Guard: Validasi ketat pada Layer 1 (Python Origin & Port Check), Layer 2 (JavaScript DOM CasaOS Signature Guard), dan Layer 3 (API Intent) memastikan kredensial OS HANYA diinput ke halaman resmi ZimaOS Dashboard.",
            "Zero Credential Leakage: Menjamin keamanan kredensial akun induk dan mencegah pemblokiran akun akibat salah password berulang pada aplikasi Docker."
        ],
        "features": [
            "Vectorized Zero-Drift Telemetry Dot Matrix: Mengganti 18 elemen <span> CSS Grid dengan satu elemen SVG vektor murni berkoordinat matematis (viewBox 36x18). Mengunci aspek rasio 1:1 circular LED matrix dan mengeliminasi distorsi pil lonjong pada Windows Display Scaling (125%-175%).",
            "Multi-DPI Subpixel Precision: Mengeliminasi celah belang antar-kolom akibat pembulatan subpixel snapping DirectWrite/Blink pada monitor laptop resolusi tinggi.",
            "Skeleton Meter Harmonization: Menyelaraskan status loading telemetri ke geometri SVG yang sama persis, menghasilkan Zero Layout Shift (CLS = 0) saat transisi data masuk.",
            "Docker App Credential Boundary Guard: Mencegah injeksi otomatis username dan password root ZimaOS ke form login aplikasi pihak ketiga (Nextcloud, qBittorrent, Transmission, Jellyfin, Portainer, dll.).",
            "Triple-Layer Security Guard: Validasi ketat pada Layer 1 (Python Origin & Port Check), Layer 2 (JavaScript DOM CasaOS Signature Guard), dan Layer 3 (API Intent) memastikan kredensial OS HANYA diinput ke halaman resmi ZimaOS Dashboard.",
            "Zero Credential Leakage: Menjamin keamanan kredensial akun induk dan mencegah pemblokiran akun akibat salah password berulang pada aplikasi Docker."
        ]
    },
    {
        "version": "3.11.0",
        "channel": "Beta",
        "date": "2026-10-30",
        "title": "Smart Multi-Server Backup Target Selector, Zero-Bias BEP Protocol Verification & Smart Identity Inheritance Architecture",
        "notes": [
            "Smart Multi-Server Backup Target Selector: Pengguna kini dapat memilih server target (Primary-Server / Secondary-Server) secara langsung di modal Tambah Jalur Backup Baru tanpa perlu beralih server global atau mengganggu koneksi SMB aktif.",
            "Independent Task Routing: Pembuatan task backup langsung memetakan kredensial, Device ID, dan rute efektif server tujuan terpilih secara terisolasi.",
            "Smart Identity Inheritance Architecture: MyServer secara cerdas mewarisi dan mengamankan sertifikat digital (cert.pem & key.pem) dari instalasi lama ke direktori internal MyServer, menjamin 0% re-pairing dan mencegah laptop dibaca sebagai device baru.",
            "Zero-Bias Native Protocol Verification: Terbukti secara empiris melalui pengujian koneksi TLSv1.3 langsung bahwa kode Python MyServer dapat berkomunikasi dengan Syncthing di sisi server (BEP Magic 0x2EA7D90B & Protobuf Hello) saat Syncthing laptop dimatikan.",
            "Target Server Visual Badging: Setiap kartu jalur backup pada daftar task kini menampilkan label badge server tujuan (🎯 Primary-Server / 🎯 Secondary-Server) dengan visual penanda server aktif.",
            "Single-Command Multi-File Version Synchronizer: Utilitas terpusat sync_version.py untuk sinkronisasi versi atomik lintas seluruh ekosistem berkas MyServer."
        ],
        "features": [
            "Smart Multi-Server Backup Target Selector: Pengguna kini dapat memilih server target (Primary-Server / Secondary-Server) secara langsung di modal Tambah Jalur Backup Baru tanpa perlu beralih server global atau mengganggu koneksi SMB aktif.",
            "Independent Task Routing: Pembuatan task backup langsung memetakan kredensial, Device ID, dan rute efektif server tujuan terpilih secara terisolasi.",
            "Smart Identity Inheritance Architecture: MyServer secara cerdas mewarisi dan mengamankan sertifikat digital (cert.pem & key.pem) dari instalasi lama ke direktori internal MyServer, menjamin 0% re-pairing dan mencegah laptop dibaca sebagai device baru.",
            "Zero-Bias Native Protocol Verification: Terbukti secara empiris melalui pengujian koneksi TLSv1.3 langsung bahwa kode Python MyServer dapat berkomunikasi dengan Syncthing di sisi server (BEP Magic 0x2EA7D90B & Protobuf Hello) saat Syncthing laptop dimatikan.",
            "Target Server Visual Badging: Setiap kartu jalur backup pada daftar task kini menampilkan label badge server tujuan (🎯 Primary-Server / 🎯 Secondary-Server) dengan visual penanda server aktif.",
            "Single-Command Multi-File Version Synchronizer: Utilitas terpusat sync_version.py untuk sinkronisasi versi atomik lintas seluruh ekosistem berkas MyServer."
        ]
    },
    {
        "version": "3.10.21",
        "channel": "Beta",
        "date": "2026-10-29",
        "title": "Server NET Telemetry, Syncthing Throughput Monitor, Global Loading Overlay & Font Harmonization",
        "notes": [
            "Server-Side Network Telemetry: Monitor NET di dock kini menampilkan kecepatan upload & download riil server ZimaOS dari endpoint sys_net (bukan adapter laptop).",
            "Dedicated Syncthing Speed: Monitor kecepatan sinkronisasi backup murni membaca throughput Syncthing tanpa pernah bocor ke kecepatan internet laptop.",
            "Global Loading Transition Overlay: Transisi visual loading halus saat pergantian rute, server, atau akun dengan auto-refresh in-place tanpa mental ke beranda.",
            "Eliminasi Total False Claim Online (Manual LAN): Isolasi ketat kandidat koneksi saat rute manual LAN dipilih di luar jaringan lokal.",
            "Hover DISK Akun Aktif: Menampilkan jumlah disk dan kapasitas total partisi SMB yang dapat diakses oleh profil pengguna aktif.",
            "Pencegahan Crash Submenu Backup: Memperbaiki shadowing fungsi translasi pada daftar tugas sehingga bebas dari TypeError.",
            "Harmonisasi Tipografi & CSS Inheritance: Seluruh modal baru, input, dan form controls kini konsisten mewarisi Plus Jakarta Sans dan JetBrains Mono.",
            "Pembersihan Total Hardcoded Power Control: Standardisasi seluruh checklist WoL, badge status kesiapan, dan konfirmasi daya ke i18n."
        ],
        "features": [
            "Server-Side Network Telemetry: Monitor NET di dock kini menampilkan kecepatan upload & download riil server ZimaOS dari endpoint sys_net (bukan adapter laptop).",
            "Dedicated Syncthing Speed: Monitor kecepatan sinkronisasi backup murni membaca throughput Syncthing tanpa pernah bocor ke kecepatan internet laptop.",
            "Global Loading Transition Overlay: Transisi visual loading halus saat pergantian rute, server, atau akun dengan auto-refresh in-place tanpa mental ke beranda.",
            "Eliminasi Total False Claim Online (Manual LAN): Isolasi ketat kandidat koneksi saat rute manual LAN dipilih di luar jaringan lokal.",
            "Hover DISK Akun Aktif: Menampilkan jumlah disk dan kapasitas total partisi SMB yang dapat diakses oleh profil pengguna aktif.",
            "Pencegahan Crash Submenu Backup: Memperbaiki shadowing fungsi translasi pada daftar tugas sehingga bebas dari TypeError.",
            "Harmonisasi Tipografi & CSS Inheritance: Seluruh modal baru, input, dan form controls kini konsisten mewarisi Plus Jakarta Sans dan JetBrains Mono.",
            "Pembersihan Total Hardcoded Power Control: Standardisasi seluruh checklist WoL, badge status kesiapan, dan konfirmasi daya ke i18n."
        ]
    },

    {
        "version": "3.10.20",
        "channel": "Beta",
        "date": "2026-10-29",
        "title": "Harmonisasi Modal React Modern, Telemetri Suhu & Wattage Real-Time, dan Redesain Pill Rute Cepat Minimalis",
        "notes": [
            "Redesain Pill Footer HomeView: Tampilan nama rute ringkas (LAN, Remote, WAN) dengan ikon spesifik (LAN/Ethernet, Remote Wifi, WAN Globe) bebas distraksi.",
            "Quick Route Switcher Pop-up: Modal ganti cepat rute dengan status aktif, latensi ms, opsi otomatis failover, dan masked URL/IP dengan tombol toggle unmask.",
            "Harmonisasi Dialog WinForms ke React: Penggantian seluruh popup skrip PowerShell Windows Forms klasik ke Modal React mengambang terpadu di dalam antarmuka companion.",
            "Hover Telemetri Mendalam: Pengukuran suhu CPU (°C), konsumsi daya (Watt), pembagian RAM GB/GB riil, serta jumlah dan kapasitas partisi disk.",
            "Label DISK Anti-Patah Baris: Penyelarasan label MEM menjadi DISK dengan whitespace-nowrap.",
            "Pembersihan Dwibahasa Penuh: 100% bebas hardcode pada seluruh kartu (kartu Opsi), chip, notifikasi, dan form."
        ],
        "features": [
            "Redesain Pill Footer HomeView: Tampilan nama rute ringkas (LAN, Remote, WAN) dengan ikon spesifik (LAN/Ethernet, Remote Wifi, WAN Globe) bebas distraksi.",
            "Quick Route Switcher Pop-up: Modal ganti cepat rute dengan status aktif, latensi ms, opsi otomatis failover, dan masked URL/IP dengan tombol toggle unmask.",
            "Harmonisasi Dialog WinForms ke React: Penggantian seluruh popup skrip PowerShell Windows Forms klasik ke Modal React mengambang terpadu di dalam antarmuka companion.",
            "Hover Telemetri Mendalam: Pengukuran suhu CPU (°C), konsumsi daya (Watt), pembagian RAM GB/GB riil, serta jumlah dan kapasitas partisi disk.",
            "Label DISK Anti-Patah Baris: Penyelarasan label MEM menjadi DISK dengan whitespace-nowrap.",
            "Pembersihan Dwibahasa Penuh: 100% bebas hardcode pada seluruh kartu (kartu Opsi), chip, notifikasi, dan form."
        ]
    },
    {
        "version": "3.10.19",
        "channel": "Beta",
        "date": "2026-10-29",
        "title": "Eliminasi Total False Claim Online, Validasi Nyata Origin Server, dan Dual-Route Dynamic SMB Storage",
        "features": [
            "Strict Origin Validation: Mengeliminasi false online claim akibat CDN/Cloudflare (error 520-530 dan tunnel disconnect langsung dinyatakan Offline).",
            "Eliminasi Latensi Palsu: Menghilangkan hardcode pingMs 2ms dan menyajikan latensi pengukuran empiris nyata.",
            "Dual-Route Dynamic SMB Storage: Penyelarasan rute mounting disk secara alami (LAN -> SMB LAN, ZeroTier -> SMB ZeroTier) dengan fallback cerdas tanpa freeze.",
            "Pembersihan Hardcode SMB: Menghapus aturan kaku lama yang memaksakan rute domain wajib dialihkan ke ZeroTier.",
            "Transparansi Status ZeroTier: Membedakan status layanan klien laptop dengan status konektivitas peer server fisik."
        ]
    },
    {
        "version": "3.10.18",
        "channel": "Beta",
        "date": "2026-10-29",
        "title": "Perbaikan Menyeluruh Auto Failover Multi-Jalur & Integrasi Rute Dinamis ZeroTier P2P",
        "features": [
            "Integrasi Penuh Rute Dinamis ZeroTier (Tier 3): Menyintesis zerotier_virtual_ip ke evaluasi Auto Failover dan antarmuka pilihan rute.",
            "Probing Jaringan Hybrid Adaptif: Harmonisasi deteksi online dengan TCP socket cepat dan HTTP probe toleran Cloudflare/Reverse Proxy.",
            "Eliminasi Standar Ganda Status Online: Menghilangkan inkonsistensi status online antara rute manual vs rute otomatis.",
            "Smart Offline Fallback (Anti-Banting ke LAN): Mencegah sistem terkunci ke IP LAN 192.168.x.x saat pengguna berada di luar jaringan rumah.",
            "Timeout Adaptif Jaringan WAN: Menaikkan toleransi latensi probe domain hingga 4.5 detik pada jaringan remote/seluler."
        ]
    },
    {
        "version": "3.10.17",
        "channel": "Beta",
        "date": "2026-10-28",
        "title": "Comprehensive 100% Bilingual English & Indonesian Localization Across All Views",
        "features": [
            "Penuntasan total translasi dwibahasa di seluruh antarmuka (Companion, Home, Files, Backup, Apps, Power, Server).",
            "Header dinamis di seluruh sub-view melalui getViewHeader() menghilangkan string bahasa Indonesia statis.",
            "Eliminasi total teks bahasa Indonesia pada hover tooltip kartu menu utama di HomeView.",
            "Lokalisasi penuh tombol aksi, status drive, tile P2P, form drawer, checklist BIOS, dan modal konfirmasi.",
            "Penguatan rantai Graceful Fallback Chain 4-lapis pada kamus i18n untuk stabilitas rendering mutlak."
        ]
    },
    {
        "version": "3.10.16",
        "channel": "Beta",
        "date": "2026-10-28 07:15",
        "notes": [
            "Penuntasan Bahasa Inggris Menyeluruh (English Default & ID): Mengembangkan kamus i18n untuk seluruh elemen antarmuka, judul menu, hover tooltip, metrik trafik, dan dialog dengan prinsip Graceful Fallback Chain.",
            "Status DPAPI 100% Dinamis: Mengintegrasikan fungsi probe runtime nyata pada Windows CryptProtectData in-memory sehingga indikator status DPAPI mencerminkan kondisi riil sistem operasi Windows.",
            "Eliminasi Total 71 Temuan Hardcode: Menghapus asumsi akun kaku ('Admin'), fallback MAC palsu ('AA:BB:CC:DD:EE:FF'), huruf drive dan partisi statis ('Z' dan 'DATA'), serta menetralkan contoh IP dan Network ID pada komentar/dialog."
        ],
    },
    {
        "version": "3.10.15",
        "channel": "Beta",
        "date": "2026-10-28 06:15",
        "notes": [
            "Fungsi Ganti Bahasa Dwibahasa di Options: Menambahkan opsi preferensi bahasa antarmuka (English Default & Bahasa Indonesia) baik melalui segmented button pada kartu Options maupun toggle instan pada chip status footer.",
            "Fitur Pembaruan Aplikasi Melalui ZIP: Mengintegrasikan fitur pembaruan mandiri offline dari berkas arsip ZIP dengan validasi integritas biner, isolasi karantina temp, dan skrip updater batch independen yang aman.",
            "Sinkronisasi Versi Dinamis Terpusat: Menghilangkan seluruh nilai versi hardcoded di komponen antarmuka, menyelaraskan seluruh tampilan Mini Tray dan Options agar selalu sinkron secara dinamis 100% mengikuti metadata versi aplikasi."
        ],
    },
    {
        "version": "3.10.14",
        "channel": "Beta",
        "date": "2026-10-28 05:30",
        "notes": [
            "Opsi Preferensi Klik File Manager di Pengaturan: Menambahkan kartu pengaturan interaktif pada Options untuk memilih target klik kartu File Manager di beranda (File Explorer Windows vs ZimaOS File Manager).",
            "Tombol Sub-Menu Penyimpanan Dinamis & Adaptif: Tombol peluncur pada menu Penyimpanan & Berkas otomatis menyajikan alternatif aplikasi yang belum dipilih sebagai aksi default tanpa teks terpotong.",
            "Minimalisir Tombol Titik Tiga pada Kartu Beranda: Mengganti tombol sub-menu teks pada kartu File Manager dengan ikon titik 3 (MoreVertical) yang elegan dan ringkas tanpa menimpa teks judul.",
            "Pembersihan UI Kartu Akun: Menghapus badge verifikasi akun yang redundan agar kartu profil akun lapang dan teks deskripsi hak akses dapat dibaca secara leluasa tanpa terhimpit."
        ],
    },
    {
        "version": "3.10.13",
        "channel": "Beta",
        "date": "2026-10-27 22:30",
        "notes": [
            "URL Web App Dinamis via Remote IP: Kontainer aplikasi ZimaOS di menu Apps otomatis diarahkan ke Remote IP (ZeroTier) saat server diakses melalui rute Domain publik, menembus batasan port-forwarding router secara native tanpa hardcode.",
            "Rekayasa Alur File Manager: Tombol File Manager di menu utama Mini Tray kini langsung membuka Windows File Explorer ke disk SMB terpasang untuk akses cepat berkas.",
            "Tombol Menu File Manager Baru: Menambahkan tombol navigasi [Menu →] di kartu File Manager pada menu utama untuk membuka antarmuka lengkap manajemen disk & storage.",
            "Opsi Ganda Peluncur Berkas: Menyediakan tombol terpisah di menu File Manager untuk membuka File Explorer (Windows SMB) dan ZimaOS File Manager (Web Files), serta opsi preferensi aksi klik cepat.",
            "Deskripsi Hak Akses Dinamis (Nol Hardcode): Menggantikan teks statis dengan deskripsi peran real dari API resmi ZimaOS (/v1/users/current), membedakan izin Administrator vs Pengguna Standar secara presisi.",
            "Opsi Switch Auto Buka Mini Tray: Pengguna dapat memilih apakah jendela mini tray otomatis terbuka di layar saat startup Windows atau tetap berjalan senyap di system tray."
        ],
    },
    {
        "version": "3.10.12",
        "channel": "Beta",
        "date": "2026-10-27 00:15",
        "notes": [
            "Penyegaran Real-Time File Manager: Menu Penyimpanan & Berkas kini memicu penyegaran drive seketika saat dibuka (on-mount) dan polling berkala (3 detik) saat aktif, mengeliminasi delay pembaruan data partisi storage.",
            "Sinkronisasi Cache & Switch Server Instan: Cache memori drive SMB langsung diinvalidasi saat peralihan server atau profil akun, mencegah tampilan disk server lama tertinggal di UI.",
            "Filter Kepemilikan Network Drive Dinamis: Pemindaian drive Windows memfilter kepemilikan host UNC secara dinamis berbasis identitas server aktif (koneksi, domain, IP virtual ZeroTier), mengisolasi disk antar-server secara presisi tanpa hardcode.",
            "Dynamic Host Footer File Manager: Menampilkan hostname/IP rute aktif server secara dinamis pada footer kartu penyimpanan, menggantikan nilai statis \\\\127.0.0.1.",
            "Batas Waktu Autentikasi Adaptif (Admin Telemetri Jarak Jauh): Mengoptimalkan batas waktu autentikasi ZimaOS secara dinamis (10.0 detik untuk rute Domain/WAN publik, 5.0 detik untuk LAN privat), mengatasi masalah telemetri 0% pada akun Admin root di koneksi internet/WAN bertopologi latensi tinggi.",
            "Penyempurnaan Penanganan Array Kosong Drive: Memperbaiki logika sinkronisasi UI saat transisi unmount agar drive yang dilepas langsung bersih dari layar secara akurat."
        ],
    },
    {
        "version": "3.10.11",
        "channel": "Beta",
        "date": "2026-10-26 23:15",
        "notes": [
            "Auto-Discovery & Sinkronisasi ZeroTier Virtual IP per Server: Setiap server kini secara mandiri dan dinamis menemukan IP virtual ZeroTier masing-masing dari REST API ZimaOS (/v2/zimaos/zt/info) tanpa intervensi manual.",
            "Mounting Otomatis Disk SMB Server Ber-Rute Domain: Saat beralih ke server di luar jaringan LAN (rute domain/WAN publik), pipeline SMB secara cerdas mengalihkan resolusi ke ZeroTier Virtual IP server tersebut dengan verifikasi respons port 445 dan fallback aman.",
            "Pemilihan Jaringan ZeroTier Akurat di UI: Kartu status ZeroTier pada pengaturan server menampilkan status dan detail jaringan yang secara presisi cocok dengan Remote ID server aktif, bukan elemen acak dari daemon lokal.",
            "Resolusi Subnet ZeroTier Dinamis (Zero Hardcoded): Menggantikan seluruh filter subnet statis dengan pemindaian rute terkelola adapter ZeroTier aktif langsung dari daemon sistem.",
            "Validasi Partisi Network Drive Terintegrasi: Menyertakan ZeroTier Virtual IP server aktif ke dalam identitas server resmi agar drive SMB yang terpasang via IP ZeroTier langsung tampil di daftar Disk UI."
        ],
    },
    {
        "version": "3.10.10",
        "channel": "Beta",
        "date": "2026-10-26 22:00",
        "notes": [
            "Perbaikan Total Auto-Run Windows Boot: Menghubungkan autorun registry (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\MyServerCompanion) tepat ke biner GUI utama (MyServer-Beta.exe) bukan backend headless, dilengkapi Startup Registry Self-Healing dan Orphan Boot Guard.",
            "Pemulihan & Penguatan Auto-Mount SMB Pasca-Boot: Mengaktifkan inisialisasi is_online yang akurat dan pemicu startup_auto dengan mekanisme retry adaptif saat jaringan Wi-Fi/LAN/ZeroTier siap, serta mode non-destruktif yang mempertahankan drive yang sudah sehat.",
            "Perbaikan Status Multi-Server (Anti-Offline Palsu): Memperbaiki isolasi cache rute berdasarkan server_id dan active_conn, memisahkan status Online keterjangkauan jaringan dari autentikasi API telemetri, serta toleransi 3 siklus kegagalan berturut-turut.",
            "Akselerasi Ekstrem Mounting SMB: Mengeliminasi pemindaian berulang dan pemblokiran WNet/net.exe pada domain publik WAN/Cloudflare di purge_smb_sessions, membatasi reverse DNS hanya untuk IPv4 privat (0.3s), dan memanfaatkan kembali token autentikasi aktif.",
            "Pembersihan Kode Debug Trace Shell: Menghapus seluruh penulisan jejak debug hardcoded (setup_trace.log) di engine Rust Tauri shell untuk performa startup yang bersih dan patuh standar."
        ],
    },
    {
        "version": "3.10.9",
        "channel": "Beta",
        "date": "2026-10-26 00:45",
        "notes": [
            "Overhaul SMB Engine Mengadopsi Arsitektur Zima Client v2.3.5: Registrasi otomatis kredensial ke Windows Credential Vault (cmdkey.exe), penghapusan passwordless net.exe fallback yang memicu hang 2-4 menit, pembersihan drive Red-X (ERROR_CONNECTION_UNAVAIL / 1201), auto-recovery Error 1219, dan notifikasi instan SHChangeNotify ke File Explorer.",
            "Eliminasi SMB Polling Overhead: Menggunakan kapasitas partisi langsung dari REST API /v2/local_storage/mount tanpa membanjiri network drive SMB dengan GetDiskFreeSpaceExW setiap 2 detik.",
            "Tata Letak Kartu Jalur Backup (BackupView): Memindahkan badge target server ke sisi kiri barisan ikon aksi bawah sehingga judul jalur backup tampil utuh dan proporsional.",
            "Reset Otomatis ke Menu Awal (HomeView): Menutup Mini Tray (tombol X atau klik ikon tray) dan membukanya kembali selalu mengembalikan tampilan ke menu awal.",
            "Pemulihan Auto-Login Dashboard WebView: Mengaktifkan kembali isolasi sesi WebView2 per-profil (WEBVIEW2_USER_DATA_FOLDER & storage_path) serta injeksi token JWT & auto-fill kredensial akun aktif.",
            "Persistensi Permanen MAC Address Wake-on-LAN (WoL): Menyimpan dan memuat MAC address langsung dari config.json tanpa tereset ke nilai default.",
            "Latar Putih Menyatu dengan Sudut Melengkung Seragam (rounded-2xl): Menyatukan latar belakang antara kartu monitoring dan kartu utama dengan corner radius yang konsisten di keempat sudut."
        ],
    },
    {
        "version": "3.10.2",
        "channel": "Beta",
        "date": "2026-10-24 22:35",
        "notes": [
            "Pemulihan Pipeline Atomik Storage SMB (rebind_storage_pipeline): Unmount bersih seluruh drive remote lama dan pembersihan sesi kredensial Windows (NET USE /DELETE & WNetCancelConnection2W) otomatis saat pergantian akun aktif, mencegah tumpukan drive letter dan error 1219.",
            "Koreksi Deteksi Share REST API ZimaOS: Memperbaiki penanganan respons list array pada endpoint /v2_1/files/share dan verifikasi hak akses case-insensitive multi-field untuk akun Admin (algitha) dan user standar.",
            "Pemulihan Live Telemetri Monitoring: Mengintegrasikan ZimaMetricsClient.fetch_metrics() secara real-time pada background thread daemon, memulihkan indikator CPU, RAM, dan HDD yang sebelumnya tertahan di 0%.",
            "Peluncur Jendela Web App Mandiri (Tauri WebviewWindow): Mengimplementasikan pembuka jendela native 1150x750 untuk aplikasi web ZimaOS dan dashboard dengan akselerasi perangkat keras.",
            "Peluncur Browser Eksternal Andal: Mengaktifkan aksi 'Browser Luar' via Windows native ShellExecute (os.startfile / start) untuk peramban default sistem."
        ],
    },
    {
        "version": "3.10.1",
        "channel": "Beta",
        "date": "2026-10-24 21:55",
        "notes": [
            "Jembatan IPC Native Rust (std::net::TcpStream): Menghapus ketergantungan pada WebView2 loopback fetch() yang diblokir oleh Chromium Private Network Access (PNA), digantikan dengan call_core_api berlatensi < 0.5ms tanpa ketergantungan crate eksternal.",
            "Penghapusan Total Mock Hardcoded Fallback: Menghilangkan seluruh nilai statis (127.0.0.1, Server Utama, dll.) di api.real.ts, memulihkan resolusi Promise Proxy RPC tanpa hanging pada .then.",
            "Pemulihan Seluruh Tombol Aksi & Navigasi: Menghubungkan kembali aksi tombol Tambah Server, Ubah, Hapus, Tambah Rute, Hubungkan Remote ID ZeroTier, Pasang Semua Disk Server, dan Deteksi MAC WoL.",
            "Integrasi Dialog Native Windows Forms: Seluruh dialog konfigurasi (dialogs.ps1) beroperasi dengan TopMost = true di latar depan.",
            "Optimalisasi Ukuran Biner: Ukuran binary MyServer-Beta.exe menyusut dari 13.6 MB menjadi 9.37 MB berkat eliminasi transitive dependencies Rust."
        ],
    },
    {
        "version": "3.10.0",
        "channel": "Beta",
        "date": "2026-10-24 19:30",
        "notes": [
            "Arsitektur Baru Tauri v2 Native Shell: Menggantikan engine WinForms pywebview dengan Tauri v2 berbasis DirectComposition hardware-accelerated per-pixel alpha transparency.",
            "Transparansi Sempurna 100% (True Wallpaper See-Through): Celah 16px antara Dock dan Flyout sepenuhnya tembus pandang ke wallpaper desktop native Windows tanpa kotak abu-abu gelap #202020 WinForms.",
            "Tombol Minimalkan Native Windows (_): Meminimalkan jendela secara native ke Windows Taskbar, hadir di Alt+Tab dan Win+Tab tanpa bug ShowWindow(SW_HIDE).",
            "Zero UI Redesign: Seluruh desain React 19 + Tailwind CSS + Lucide icons tetap 100% identik dengan rancangan Figma.",
            "Headless Companion Core Service: Backend Python berjalan sebagai companion service headless independen melalui IPC loopback port dinamis."
        ],
    },
    {
        "version": "3.9.4",
        "channel": "Beta",
        "date": "2026-10-24 11:45",
        "notes": [
            "Paket 1: Dinamisasi Menu Web Apps & Kontainer ZimaOS (AppsView): Mengeliminasi kontainer fiktif statis (Nextcloud/Plex/Jellyfin/AdGuard mockup) dan menggantikannya 100% dengan daftar dinamis dari config.json.",
            "Formulir Inline Tambah Web App Baru: Menyediakan form terintegrasi di dalam flyout Mini Tray untuk menyimpan nama aplikasi dan tautan URL/port secara langsung.",
            "Manajemen Hapus Web App Terintegrasi: Pengguna dapat menghapus tautan web app langsung dari kartu antarmuka Mini Tray dengan sinkronisasi otomatis ke menu klik kanan baki sistem.",
            "Integrasi Dinamis ZimaOS AppStore: Tombol pintasan AppStore membuka URL AppStore ZimaOS secara murni dinamis berbasis rute server aktif tanpa hardcoded IP."
        ],
    },
    {
        "version": "3.9.2",
        "channel": "Beta",
        "date": "2026-10-24 11:15",
        "notes": [
            "Integrasi Penuh Antarmuka Figma Make Companion UI: Seluruh 6 tampilan utama (Home Bento Hub, Files & Storage, Backup & Syncthing, Apps & Containers, Settings, dan Emergency Power Dock) aktif secara penuh.",
            "Menu Baru Pusat Kendali Jaringan & Akun (ServerView): Menghubungkan klik kartu 'Server Name' ke menu navigasi rute jaringan (LAN Fisik, ZeroTier P2P, Domain/WAN), penukaran profil akun aktif, dan status multi-server.",
            "Aksi Nyata Seluruh Tombol Mini Tray: Menggantikan seluruh tombol mock toast menjadi aksi native Windows (buka Web Files, luncurkan PeerDrop, buka drive Explorer, buka console server, buka log Notepad, dan persistensi MAC WoL ke config.json).",
            "Transparansi Kapsul Melayang Murni (Floating Aesthetic): Mengubah kanvas menjadi transparent sehingga dua kapsul melayang dengan bayangan halus tanpa kotak hitam di tepinya.",
        ],
    },
    {
        "version": "3.9.1",
        "channel": "Beta",
        "date": "2026-10-24 09:45",
        "notes": [
            "Refactoring Arsitektur Mini Tray Popover Sesuai Standar Industri Zima Client: Mengadopsi mekanisme native focus loss (WinForms Deactivate / Electron Blur), mengeliminasi total pemantau klik mouse agresif (GetAsyncKeyState) yang sebelumnya memicu penutupan prematur secara keliru.",
            "Kalibrasi Posisi Berlabuh Presisi (.NET Screen.PrimaryScreen.WorkingArea): Memastikan jendela Mini Tray selalu berlabuh sempurna di pojok kanan bawah tepat di atas taskbar Windows pada layar 1080p dengan skala DPI 150% tanpa terpotong atau terlempar ke luar batas layar.",
            "Koreksi Parsing Partisi SMB UNC: Memperbaiki ekstraksi nama partisi share dari jalur UNC jaringan Windows sehingga nama share (seperti Shared_Disk) tampil presisi pada tombol akses cepat.",
            "Stabilitas Interaksi Pengguna: Menjamin antarmuka Mini Tray tetap tenang dan stabil di layar hingga pengguna secara sadar menutup via tombol X, toggle ikon tray, mengklik opsi aksi, atau beralih fokus ke aplikasi lain.",
        ],
    },
    {
        "version": "3.9.0",
        "channel": "Beta",
        "date": "2026-10-24 07:15",
        "notes": [
            "Arsitektur Antarmuka Baru: Mini Tray Flyout Popover (Windows 11 Fluent UI): Menghadirkan jendela popover modern frameless di pojok kanan bawah layar saat ikon baki sistem (System Tray) diklik, merefleksikan standar antarmuka kelas dunia seperti Microsoft OneDrive dan Docker Desktop.",
            "Kalkulasi Posisi Presisi Native Win32 (SPI_GETWORKAREA): Menjamin jendela Mini Tray selalu berlabuh sempurna di pojok kanan bawah tepat di atas taskbar Windows di semua resolusi layar (1080p, 1440p, 4K) dan skala DPI (100%, 125%, 150%).",
            "Mekanisme Auto-Dismiss Cerdas: Jendela Mini Tray otomatis tertutup secara halus saat pengguna mengklik area luar (desktop atau aplikasi lain).",
            "Monitoring Kecepatan Jaringan Real-Time (Pure Win32 iphlpapi): Menampilkan indikator kecepatan unduh/unggah langsung (kB/s) dan rute aktif secara dinamis tanpa library pihak ketiga.",
            "Pintasan Cepat Akses Partisi SMB Utama: Menampilkan nama partisi aktif (misal 'Open Shared_Disk' pada Drive Z:) yang langsung membuka Windows Explorer dengan 1-klik.",
            "Integrasi Telemetri Perangkat Keras Live: Menampilkan utilisasi CPU, RAM, Disk Storage, dan latensi jaringan real-time dari mesin telemetri ZimaOS.",
            "Dual-Interaction System Tray: Klik kiri menampilkan Mini Tray Flyout modern; klik kanan tetap mempertahankan menu kontekstual baki sistem.",
        ],
    },
    {
        "version": "3.8.8",
        "channel": "Beta",
        "date": "2026-10-24 05:30",
        "notes": [
            "Perbaikan Font & Tampilan Simbol Garis Miring ('/') pada Menu Baki Sistem: Mengganti karakter ampersand ('&') yang sebelumnya disembunyikan oleh Windows Win32 Menu Accelerator menjadi garis miring (' / ') eksplisit pada seluruh tombol menu (seperti '📂 Penyimpanan / Berkas', '🌐 Jaringan / Status', '👥 Akun / Server', dan '🌐 Web Apps / Bookmarks').",
            "Eliminasi Duplikasi Ikon Pengaturan (Gear): Menghilangkan penambahan ikon manual ganda pada item menu baki sistem sehingga ikon '⚙️' hanya tampil tepat satu kali pada '⚙️ Pengaturan / Preferensi'.",
        ],
    },
    {
        "version": "3.8.7",
        "channel": "Beta",
        "date": "2026-10-24 05:20",
        "notes": [
            "Perbaikan Arsitektur Backup & Restore Data (Atomic Python Restore): Menghapus total ketergantungan pada skrip batch taskkill /T yang sebelumnya membunuh proses restore sendiri. Pemulihan config.json kini dijalankan secara atomik langsung di Python dengan verifikasi integritas JSON, proteksi cadangan otomatis (.bak), dan peluncuran ulang aplikasi secara mandiri (Windows Detached Process).",
            "Penyaringan Berkas Cadangan Bersih (Zero Browser Bloat): Memperbaiki proses backup data agar menyaring dan mengecualikan direktori cache WebView2 (EBWebView) dan berkas sementara, menjadikan arsip cadangan ringan, bersih, dan 100% kompatibel saat dipulihkan.",
            "Peningkatan Resolusi Tampilan Native (PerMonitorV2 Manifest & VisualStyles): Menyematkan manifest aplikasi resmi Windows (app.manifest) berstandar industri dengan deklarasi PerMonitorV2 High-DPI, serta mengaktifkan EnableVisualStyles() dan SetProcessDpiAwarenessContext(-4) pada seluruh jendela dialog PowerShell Windows Forms agar seluruh teks, tombol, dan bingkai tampil tajam (razor-sharp).",
            "Elevasi Pengaturan Aplikasi ke Menu Utama Baki Sistem: Memindahkan submenu 'Pengaturan Aplikasi' (Preferences) langsung ke menu utama baki sistem untuk akses 1-klik yang intuitif dan cepat.",
            "Indikator Status Server Real-Time pada 'Open MyServer': Menambahkan badge status konektivitas '(ON)' atau '(OFF)' secara dinamis di samping label menu pembuka server berdasarkan status jaringan aktif.",
        ],
    },
    {
        "version": "3.8.6",
        "channel": "Beta",
        "date": "2026-10-24 02:50",
        "notes": [
            "Dukungan Penuh Partisi SMB dengan Nama Berspasi (Multi-Word Share Parsing): Memperbaiki regex parsing pada net.exe view dan net.exe use sehingga seluruh partisi fisik/share folder server termasuk yang memiliki karakter spasi (seperti 'Toshiba 1TB') terdeteksi utuh secara dinamis dan dipasang sempurna tanpa ada yang terlewat.",
            "Eliminasi Total Deadlock Pergantian Akun pada Rute yang Sama: Menjadikan pembersihan sesi WebView2 berjalan asinkron (non-blocking) dan memprioritaskan sinkronisasi storage SMB di awal pergantian akun. Proses unmount seluruh drive lama, deep purge sesi Windows, dan remount drive akun baru kini tuntas seketika (<0.6 detik) pada rute dan IP yang sama tanpa galat Windows 1219.",
            "Proteksi Pelepasan Drive Kuat (Win32 WNetCancelConnection2W Fallback): Memperkuat unmount_smb_share dengan fallback API resmi Windows WNetCancelConnection2W dengan bForce=True jika net.exe use terhalang oleh file handle yang tertahan di Windows Explorer.",
            "Pembersihan Sesi SMB Dinamis & Presisi: Menggunakan regex UNC presisi pada purge_smb_sessions sehingga share folder berspasi maupun huruf drive terkait terlepas tuntas dari tabel koneksi Windows saat pergantian akun/server/rute.",
        ],
    },
    {
        "version": "3.8.5",
        "channel": "Beta",
        "date": "2026-10-24 02:30",
        "notes": [
            "Deep Purge Sesi SMB & Unmount-Remount Bersih saat Ganti Akun (Anti-Error 1219): Mengeliminasi total Windows Error 1219 saat berganti akun dengan membersihkan seluruh koneksi network, sesi IPC$ terautentikasi, dan memanggil WNetCancelConnection2W Win32 API sebelum drive akun baru dipasang.",
            "Prioritas Mutlak Rute Aktif Pengguna pada Resolusi SMB Host: Jika pengguna memilih rute ZimaOS/ZeroTier IP (172.25.0.1) atau LAN IP (192.168.1.11), resolusi SMB wajib mengikat langsung ke host rute pilihan tersebut selama port 445 merespons, meniadakan pembajakan rute oleh IP lain di daftar koneksi.",
            "Sinkronisasi Real-Time Hak Akses Disk SMB (Multi-User Dynamic Refresh): Menu penyimpanan dan pipeline mounting kini otomatis mendeteksi share disk sesuai hak akses akun aktif (Admin melihat 5 disk, user biasa melihat 2 disk), serta memulihkan daftar disk secara utuh saat berganti kembali ke Admin.",
            "Peningkatan Resolusi Tampilan Native & Anti-Buram (Per-Monitor V2 DPI Awareness): Mengaktifkan API resmi Windows Per-Monitor V2 DPI Awareness (DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) saat startup, meniadakan efek buram/pecah akibat bitmap stretching Windows pada skala 125%/150%/200%.",
            "Pencatatan Log Komprehensif Seluruh Aktivitas & Eliminasi Spamming: Mencatat secara eksplisit setiap awal dan akhir aksi perpindahan akun profil ([Profile Switch]), rute ([Route Switch]), dan server ([Server Switch]) ke myserver.log, serta meniadakan log spamming pada hover menu baki sistem.",
        ],
    },
    {
        "version": "3.8.4",
        "channel": "Beta",
        "date": "2026-10-24 01:45",
        "notes": [
            "Perbaikan Arsitektur SMB Host Resolver (Prioritas Ketat 3-Tier): Mengeliminasi insiden resolusi SMB ke IP Remote ZeroTier saat pengguna berada pada jaringan lokal (LAN). IP LAN fisik (Tier 1) kini selalu diprioritaskan untuk rute lokal, sedangkan ZeroTier IP (Tier 2/3) hanya digunakan jika rute aktif adalah Domain FQDN/WAN atau LAN offline.",
            "Restorasi Penuh Modul Logging Terpusat (myserver.log): Mengimplementasikan fungsi top-level log_info(), log_error(), log_warning(), log_debug(), dan hook unhandled exception global. Seluruh aktivitas startup, perpindahan rute, pergantian server/profil, dan eksekusi SMB kini tercatat secara real-time dengan auto-flush berkas.",
            "Pipeline Mounting SMB Standar Industri Zima Client: Mengadopsi mekanisme otentikasi dua tahap Zima Client (pre-auth sesi IPC$ dengan kredensial aktif diikuti pemetaan drive dengan fallback sintaks alternatif).",
            "Feedback Transparan & Eliminasi Silent Failure: Menambahkan dialog notifikasi kegagalan/keberhasilan (prompt_alert) secara interaktif saat pemasangan disk SMB manual, serta pencatatan galat sistem yang detail ke myserver.log.",
        ],
    },
    {
        "version": "3.8.3",
        "channel": "Beta",
        "date": "2026-10-24 01:00",
        "notes": [
            "Perbaikan Crash NameError get_cached_zima_client: Mengimplementasikan fungsi get_cached_zima_client() untuk memastikan build_smb_storage_menu dan rebind_storage_pipeline berjalan tanpa unhandled exception.",
            "Peningkatan Presisi Deteksi Otomatis Remote ID: Handler auto-detect kini dilengkapi TLS 1.2, payload login v1 (name: $usr), ekstraksi multi-struktur token JWT, fallback bertingkat (ZimaOS REST API -> Konfigurasi Zima Client lokal -> Daemon ZeroTier port 9993), serta notifikasi diagnostik galat yang transparan.",
            "Pembersihan Contoh Placeholder IP (Zero-Hardcoding Strict): Mengeliminasi seluruh pencatatan IP privat riil pengguna pada label formulir wizard dan komentar kode; seluruh placeholder kini menggunakan format netral (10.x.x.x) dengan nilai awal kosong murni.",
        ],
    },
    {
        "version": "3.8.0",
        "channel": "Beta",
        "date": "2026-10-23 21:00",
        "notes": [
            "Upgrade Enkripsi Kredensial ke Windows DPAPI: Menggantikan enkripsi XOR statis dengan Windows Data Protection API (CryptProtectData/CryptUnprotectData) dengan idempotency check dan unwrapping rekursif.",
            "Validasi SSL/TLS Adaptif & Strict WAN: Menerapkan validasi sertifikat SSL ketat untuk domain publik (FQDN/HTTPS) dan unverified context adaptif untuk IP privat lokal/ZeroTier, menutup celah MitM.",
            "Mesin ZeroTier Remote Access Native & Silent Auto-Installer: Integrasi mandiri dengan API lokal ZeroTier One (port 9993), Remote ID dinamis, dan pemasangan otomatis senyap berkas resmi ZeroTier One.msi jika belum terpasang.",
            "Multi-Disk SMB Dinamis (Zero Hardcoding): Auto-mount seluruh share folder disk server secara runtime via net view, alokasi dinamis huruf drive kosong dari Z: ke D: via Win32 API, dan pembukaan UNC root Explorer.",
            "Auto-Failover Storage & Event-Driven Rebinding: Otomatis melepaskan dan memasang ulang drive SMB saat perpindahan jalur (LAN/Remote), ganti server, ganti akun (anti-Error 1219), serta pelepasan bersih saat aplikasi ditutup.",
            "Siklus Hidup Otomatis (Auto-Connect & Auto-Mount on Startup): MyServer langsung menghubungkan Remote ID ZeroTier dan memasang seluruh drive penyimpanan begitu aplikasi dibuka.",
            "Redesain Menu Baki Sistem (Modern 4-Kategori): Menata 15+ tombol menjadi 4 kategori terstruktur: Dashboard, Penyimpanan & Berkas, Jaringan & Status, dan Manajemen Server & Akun.",
            "Sistem Logging Diagnostik Terpusat (logger_manager.py): Pencatatan otomatis terpusat di folder aplikasi (<Folder_Aplikasi>/logs/myserver.log) atau folder kustom dengan auto-rotation 5 MB dan tombol buka Notepad instan.",
            "Windows Smart Setup Installer (MyServer-Setup.exe): Biner instalasi mandiri dengan pemilihan folder bebas, Fresh Install, Repair/Reinstall, dan Seamless Auto-Update tanpa mereset data lama.",
            "Mitigasi Rate Limiter 'Too Many Requests': Pembatasan skrip injeksi auto-login maksimal 2x dan penghentian interval loop guna mencegah pemblokiran login ZimaOS.",
        ],
    },
    {
        "version": "3.7.1",
        "channel": "Stable",
        "date": "2026-09-25 05:36",
        "notes": [
            "Mitigasi False Positive Antivirus (SmartScreen & Windows Defender): Menyematkan metadata resmi Windows PE (VS_VERSION_INFO) mencakup Company Name, File Description, Version, dan Copyright ke dalam biner executable untuk menaikkan trust score di mata mesin pemindai antivirus.",
            "Tanda Tangan Digital Biner Otomatis (Authenticode Code Signing): Mengintegrasikan penandatanganan digital bersertifikat resmi Algitha Project ke dalam proses build untuk MyServer-Stable.exe dan skrip PowerShell dengan timestamping RFC3161.",
            "Paket Helper Kepercayaan & Unblock MOTW: Menyertakan skrip otomatis '1_Buka_Blokir_Windows_Unblock.bat' untuk menghapus atribut unduhan Mark of the Web (ZoneId=3) dan '2_Pasang_Sertifikat_Kepercayaan_Admin.bat' untuk mendaftarkan sertifikat penerbit terpercaya ke Windows Certificate Store.",
            "Eliminasi Kompresi UPX (--noupx): Mematikan pengemasan UPX packer secara eksplisit pada PyInstaller dan berkas spesifikasi build guna meniadakan deteksi heuristik AI (!ml) trojan yang keliru.",
            "Dokumentasi Panduan Keamanan Pengguna: Menyematkan berkas 'PANDUAN_KEAMANAN_WINDOWS.txt' di dalam paket rilis ZIP yang memuat instruksi penanganan mudah bagi perangkat pengguna akhir.",
        ],
    },
    {
        "version": "3.7.0",
        "channel": "Stable",
        "date": "2026-09-24 22:40",
        "notes": [
            "Promosi Rilis Stabil Generasi Baru v3.7.0: Menggabungkan seluruh penyempurnaan, stabilitas, dan fitur matang dari siklus rilis Beta v3.6.0 hingga v3.6.2 ke kanal produksi utama.",
            "Sistem Prioritas Rute Otomatis 3-Tier: Hierarki koneksi ketat: 1. LAN Fisik lokal (192.168.x.x, 172.16-31.x.x), 2. Domain Publik (HTTPS/DDNS/FQDN), 3. IP Khusus Fallback (Zima direct 10.0.5.x, ZeroTier 172.25.x.x, Tailscale, VPN virtual adapter). Mengeliminasi rute macet atau salah sasaran saat berada di luar rumah.",
            "Deteksi Cerdas Adapter Virtual Sistem: Pemetaan antarmuka virtual/VPN (ZeroTier One, Tailscale, TAP/TUN, Docker) serta indikator visual ([LAN], [Domain], [Khusus/Zima]) pada submenu Baki Sistem (System Tray).",
            "Seamless Dashboard Refresh saat Pergantian Server atau Akun ZimaOS: Berpindah server atau profil akun langsung memuat antarmuka baru secara instan pada jendela aktif tanpa perlu menutup window atau me-restart aplikasi.",
            "Opsi Fleksibel Startup Window: Pengaturan open_dashboard_on_launch (default: false / senyap di tray) dengan menu toggle pada preferensi, meminimalkan gangguan visual saat booting Windows.",
            "Fitur Terintegrasi Wake on LAN (WoL): Pengiriman UDP Magic Packet terverifikasi (burst 3 paket), pencarian MAC address otomatis via ARP Windows, dan dialog panduan prasyarat hardware.",
            "Manajemen Perangkat Syncthing Dinamis & Pop-up Pairing Real-Time: Pengelolaan koneksi perangkat P2P, dialog konfirmasi interaktif izin/tolak perangkat masuk secara live, dan penyalinan Device ID instan.",
            "Multi-Server Dynamic Credentials: Kredensial mandiri per-server (case-insensitive & fallback), timeout autentikasi 12.0s, dan toleransi enkripsi JWT token ECDSA ES256 ZimaOS.",
            "Identitas Visual Kanal Stable: Penandaan antarmuka dan tray icon resmi Hijau (#059669) untuk rilis produksi teruji.",
        ],
    },
    {
        "version": "3.6.2",
        "channel": "Beta",
        "date": "2026-09-24 22:30",
        "notes": [
            "Klasifikasi Subnet ZeroTier & Virtual Adapter (172.25.x.x): Menyelesaikan kendala IP ZimaOS/ZeroTier (misal subnet 172.25.x.x) yang sebelumnya keliru diklasifikasikan sebagai IP LAN Kelas B (172.16-31.x.x). Kini 172.25.x.x, Tailscale (100.64-127.x.x), adapter virtual sistem, serta Zima direct (10.0.5.x) secara tegas dikategorikan sebagai Tier 3 (IP Khusus / Fallback).",
            "Deteksi Cerdas Adapter Virtual Sistem: Menambahkan pemetaan dinamis interface virtual/VPN sistem (ZeroTier One, Tailscale, TAP/TUN, Docker) sehingga rute Domain Publik (Tier 2) selalu diprioritaskan saat pengguna berada di luar rumah meskipun tunnel ZeroTier dan network drive sedang aktif.",
            "Label Tier Visual pada Menu Jalur Baki Sistem: Menambahkan indikator visual status jalur ([LAN], [Domain], [Khusus/Zima]) pada submenu Baki Sistem (System Tray) untuk transparansi hierarki rute koneksi server.",
        ],
    },
    {
        "version": "3.6.1",
        "channel": "Beta",
        "date": "2026-09-24 22:15",
        "notes": [
            "Sistem Prioritas Rute Otomatis 3-Tier: Menetapkan hierarki rute yang ketat: 1. IP Lokal LAN (192.168.x.x, 172.16-31.x.x), 2. Domain Publik (FQDN/DDNS/HTTPS), 3. IP Khusus ZimaOS/Direct Link (10.0.5.x, zimaos.local). Mengatasi rute salah jatuh ke IP Zima saat di luar rumah.",
            "Peningkatan Resiliensi check_server_ping: Menambahkan SSL Context (CERT_NONE) untuk domain HTTPS publik serta mengenali respon kode HTTP 200, 301, 302, 307, 308, 401 (Auth ZimaOS), 403, 404 sebagai indikator server online.",
            "Seamless Dashboard Refresh saat Ganti Server: Berpindah server kini langsung memuat URL server baru secara instan pada jendela dashboard aktif tanpa perlu menutup window atau me-restart aplikasi.",
            "Seamless Dashboard Refresh saat Ganti Akun Zima: Berpindah profil akun kini membersihkan token sesi lama dan langsung login otomatis ke akun baru secara instan tanpa menutup jendela dashboard.",
            "Opsi Fleksibel Startup Window: Menambahkan konfigurasi open_dashboard_on_launch (default: false / senyap di tray) dengan menu toggle pada Pengaturan & Preferensi, sehingga jendela dashboard hanya muncul saat ditekan atau sesuai preferensi pengguna.",
        ],
    },
    {
        "version": "3.6.0",
        "channel": "Beta",
        "date": "2026-09-24 18:45",
        "notes": [
            "Promosi Rilis Stabil Beta v3.6.0: Menggabungkan seluruh penyempurnaan dan fitur matang dari siklus pengembangan v3.6.1 hingga v3.6.10 Alpha.",
            "Multi-Server Dynamic Credentials: Kredensial dinamis per-server & toleran (case-insensitive & fallback), mendukung lingkungan multi-server terisolasi.",
            "Timeout 12s & Failover Rute Autentikasi ZimaOS: Verifikasi kredensial andal & token ECDSA ES256 tanpa false positive login failed pada jaringan latensi tinggi.",
            "Fitur Wake on LAN (WoL) Terintegrasi: Pengiriman UDP Magic Packet terverifikasi, pencarian MAC address via ARP, dan panduan hardware interaktif.",
            "Manajemen Perangkat Syncthing Dinamis & Pop-up Pairing Real-Time: Pengelolaan koneksi perangkat P2P, izin/tolak perangkat masuk secara live, dan penyalinan Device ID.",
            "Dynamic Routing & Auto-Probing Syncthing Mandiri: Failover otomatis antara LAN IP dan WAN Domain independen dari Web UI ZimaOS.",
            "Identitas Visual Kanal Beta: Penandaan antarmuka dan tray icon Biru (#2563EB) untuk kanal pengujian stabil pengguna.",
        ],
    },
    {
        "version": "3.6.10",
        "channel": "Alpha",
        "date": "2026-09-24 10:00",
        "notes": [
            "Manajemen Kredensial Multi-Server Dinamis & Mandiri: Sistem kredensial kini sepenuhnya terisolasi per-server dan per-profil dengan get_server_credentials & save_server_credentials yang toleran (case-insensitive & fallback), menyelesaikan kegagalan login saat berpindah ke Secondary-Server.",
            "Peningkatan Timeout Autentikasi ZimaOS (12.0s): Memperpanjang batas waktu verifikasi kredensial dan kalkulasi JWT token ECDSA ES256 ZimaOS dari 5.0s menjadi 12.0s, mengeliminasi false positive 'Login Failed' pada server dengan latensi enkripsi ~6.2s.",
            "Failover Rute Otomatis pada Autentikasi Metrik & Status: Autentikasi ZimaOS kini secara cerdas menguji base_url dan seluruh daftar jalur server_connections (LAN IP maupun Domain WAN) sampai menemukan rute yang dapat dihubungi.",
            "Dekopling Validasi Kredensial dari URL Webview Aktif: Dialog konfigurasi kredensial kini mengarahkan validasi secara spesifik ke server target, mencegah validasi kredensial server kantor terlempar ke URL server utama.",
            "Wizard Tambah Server 4-Field Interaktif: Penambahan server baru kini langsung menyertakan input Username dan Password dengan verifikasi koneksi live dan opsi instan beralih ke server baru.",
            "Submenu Manajemen Kredensial Cepat di Baki Sistem: Menambahkan menu '🔑 Kredensial Server' pada system tray untuk memudahkan konfigurasi akun login setiap server secara mandiri tanpa harus mengganti server aktif terlebih dahulu.",
        ],
    },
    {
        "version": "3.6.9",
        "channel": "Alpha",
        "date": "2026-09-23 21:55",
        "notes": [
            "Fitur Wake on LAN (WoL) Terintegrasi: Menambahkan kapabilitas menghidupkan server dari kondisi mati/standby melalui pengiriman UDP broadcast Magic Packet (burst 3 paket).",
            "Dialog Konfigurasi Wake on LAN Interaktif & Edukatif: Dilengkapi panduan lengkap prasyarat hardware (kabel LAN fisik RJ45, aktivasi Wake on LAN di BIOS/UEFI, daya siaga listrik +5VSB, dan jaringan lokal/subnet yang sama).",
            "Deteksi MAC Address Otomatis via ARP: Tombol pencarian otomatis untuk mendeteksi alamat fisik (MAC Address) kartu jaringan server dari tabel ARP Windows secara instan.",
            "Tombol Uji Kirim Paket Langsung: Pengguna dapat langsung menguji pengiriman Magic Packet dari dalam dialog konfigurasi dengan pesan konfirmasi status interaktif.",
            "Aksesibilitas Menu Tray Offline & Online: Menu Wake on LAN tersedia langsung pada menu tray saat server berstatus offline serta di bawah submenu Kontrol Daya Server saat online.",
        ],
    },
    {
        "version": "3.6.8",
        "channel": "Alpha",
        "date": "2026-09-23 15:35",
        "notes": [
            "Manajemen Perangkat Syncthing Dinamis: Menambahkan fitur penambahan perangkat Syncthing terhubung (Laptop ke Server, Laptop ke Laptop rekan kantor/P2P, dan Mutual Pairing 2-Arah).",
            "Dialog Pop-up Real-Time Izin/Tolak Koneksi: Sistem secara otonom memantau permintaan perangkat masuk dan menampilkan dialog pop-up konfirmasi interaktif ([✔ Izinkan & Hubungkan] atau [✖ Tolak Permintaan]).",
            "Tampilan & Penyalinan Device ID Mandiri: Dialog untuk melihat dan menyalin Device ID Laptop dan Server dengan 1-klik ke clipboard untuk kemudahan bertukar ID antar-perangkat.",
            "Menu Kontrol & Pemutusan Perangkat di System Tray: Memungkinkan jeda, lanjutkan, peninjauan permintaan masuk, serta pemutusan/penghapusan perangkat Syncthing langsung dari baki sistem.",
        ],
    },
    {
        "version": "3.6.7",
        "channel": "Alpha",
        "date": "2026-09-23 11:45",
        "notes": [
            "Resolusi IP & Domain Syncthing Dinamis & Mandiri: Memisahkan ketergantungan resolusi rute Syncthing dari IP/status Web UI ZimaOS, memungkinkan Syncthing beroperasi pada IP atau domain tersendiri secara otonom.",
            "Auto-Probing & Dynamic Failover Syncthing: Mendeteksi ketersediaan layanan Syncthing secara langsung melalui endpoint health (/rest/noauth/health dan /rest/system/ping), otomatis beralih antara LAN dan WAN Domain berdasarkan ketersediaan jaringan real-time.",
            "Mode Pemilihan Rute Fleksibel: Menambahkan opsi pemilihan mode rute (Otomatis/Dinamis, Selalu Gunakan LAN, Selalu Gunakan WAN/Domain) pada dialog konfigurasi.",
            "Caching Rute Non-Blocking: Mengoptimalkan performa menu baki sistem dan antarmuka dengan cache status rute responsif tanpa lag.",
        ],
    },
    {
        "version": "3.6.6",
        "channel": "Alpha",
        "date": "2026-09-23 11:15",
        "notes": [
            "Pemindaian Network Drive Dinamis (A: hingga Z:): Memindai seluruh partisi drive remote Windows di setiap perangkat tanpa batas huruf drive.",
            "Filter Validasi Kepemilikan via API ZimaOS: Memfilter drive jaringan secara ketat menggunakan API ZimaOS (/v2/users/samba/user) untuk memastikan drive tersebut benar milik server ZimaOS dan diizinkan untuk akun pengguna aktif, menolak drive dari aplikasi, server, atau NAS lain.",
            "Pembacaan Ukuran Disk Akurat Akun Non-Admin: Memastikan telemetri ukuran disk granular (...GB) dan total kapasitas terbaca sempurna pada akun pengguna biasa dengan arsitektur dual-layer (API ZimaOS dan Windows live metrics).",
            "Resolusi Identitas Multi-Host Server: Mengagregasi hostname, seluruh rute koneksi server, nama NetBIOS resmi ZimaOS, dan IP perangkat untuk validasi koneksi remote UNC yang andal.",
        ],
    },
    {
        "version": "3.6.5",
        "channel": "Alpha",
        "date": "2026-09-22 21:40",
        "notes": [
            "Perbaikan Monitor Kecepatan Upload & Download (0B): Menyimpan status metrik transfer secara persisten lintas instance SyncthingClient dan background worker, mengatasi bug kecepatan macet di 0 B/s.",
            "Tampilan Kecepatan Lengkap di Hover Tray: Menampilkan kecepatan transfer aktif pada tooltip hover (upload, download, dan 2-arah) secara real-time.",
            "Indikator Kecepatan Submenu Server & Laptop: Memastikan submenu sinkronisasi menampilkan kecepatan transfer aktual.",
            "Fallback Agregasi Koneksi: Menghitung total akumulasi dari seluruh koneksi aktif bila data total daemon kosong.",
        ],
    },
    {
        "version": "3.6.4",
        "channel": "Alpha",
        "date": "2026-09-22 21:15",
        "notes": [
            "Eliminasi Duplikasi Umbrella /DATA: Menghapus /DATA dari submenu partisi dan total kapasitas saat partisi individual tersedia, mencegah duplikasi kapasitas ganda (dari 5.6 TB kembali normal ke ~3.3 TB).",
            "Perbaikan Deteksi Disk SATA Internal (Toshiba 1TB): Menghilangkan pembatasan `if not new_map` pada query /v1/sys/hardware agar disk SATA selalu terindeks.",
            "Parsing Petunjuk Kapasitas Drive: Mendeteksi ukuran drive secara cerdas dari label volume (misal: 'Toshiba 1TB' -> 1 TB).",
            "Rekonsiliasi Ruang Disk Terpakai: Mengalokasikan selisih sys_used ke disk tanpa data pemakaian sehingga setiap partisi dan total server terukur akurat.",
        ],
    },
    {
        "version": "3.6.3",
        "channel": "Alpha",
        "date": "2026-09-22 21:00",
        "notes": [
            "Penggantian Dinamis Partisi via Network Drive: Partisi yang terhubung di Network Drive Windows secara otomatis menggantikan partisi yang belum berukuran/belum lengkap dari API ZimaOS.",
            "Eliminasi Device Kernel Mentah (sdc, sdd, sde): Memblokir kemunculan nama block device mentah Linux dari menu tray partisi.",
            "Korelasi Device Block & Volume: Memetakan dev source (/dev/sdd, /dev/sdb) ke partisi volume sebenarnya (Disk_Aldhy, Toshiba 1TB) untuk ukuran akurat.",
            "Multi-Bus Storage Stats Parsing: Mendeteksi sys_sata, sys_pci, sys_nvme, dan sys_usb secara komprehensif dari /v2/local_storage/storage/stats.",
            "Fallback Query Disk Info: Mengambil info detail kapasitas partisi disk langsung dari /v2/local_storage/disk/info jika partisi berstatus 0 B.",
        ],
    },
    {
        "version": "3.6.2",
        "channel": "Alpha",
        "date": "2026-09-22 20:30",
        "notes": [
            "Perbaikan Bug Partisi Storage: Eliminasi tuntas mount point sistem (/mnt/overlay, /etc, /tmp, /var) dan layer Docker overlay2.",
            "Deduplikasi Kanonikal Partisi: Mencegah duplikasi 3x lipat pada partisi fisik dan network drive Windows.",
            "Normalisasi Kapasitas Drive Fisik: Menampilkan kapasitas riil drive USB/SATA tanpa tertimpa model hardware atau berstatus 0 B (Aktif).",
            "Validasi Ketat Network Drive: Mencegah pencocokan salah antara host jaringan lokal dan target remote server.",
        ],
    },
    {
        "version": "3.6.1",
        "channel": "Alpha",
        "date": "2026-09-22 16:45",
        "notes": [
            "Peningkatan Pemantauan Storage Admin: Deteksi instan multi-partisi server (bukan hanya network drive).",
            "Agregasi Total Storage Akurat: Menghitung akumulasi seluruh partisi server pada label utama baki sistem.",
            "Sinkronisasi kuota dan kapasitas partisi /DATA langsung dari data sys_disk ZimaOS OpenAPI.",
            "Optimasi query endpoint storage cepat (/v2/local_storage/storage) tanpa memblokir thread latar belakang.",
        ],
    },
    {
        "version": "3.6.0",
        "channel": "Alpha",
        "date": "2026-09-21 22:40",
        "notes": [
            "Pemantauan Suhu CPU Server Real-Time (°C) & Peringatan Termal Otomatis.",
            "Peringatan Kesehatan Server (S.M.A.R.T Disk Failure & Storage Critical Alert).",
            "Penyempurnaan Bahasa Menu Monitoring Baki Sistem ('Performa & Daya Server').",
            "Pengecekan & Pemasangan Pembaruan Online GitHub Releases API serta integrasi update ZIP.",
            "Konfigurasi Repositori GitHub untuk Integrasi Pembaruan Mandiri.",
            "Restorasi arsitektur runtime Watchdog Worker & Multi-Server Switch yang stabil.",
        ],
    },
    {
        "version": "3.5.4",
        "channel": "Alpha",
        "date": "2026-09-20 11:35",
        "notes": [
            "Setup Wizard Terpadu 4-Langkah (Server & Rute, Remote Backup, Local Syncthing, Akun).",
            "Verifikasi kredensial akun langsung ke API ZimaOS pada saat setup akun pertama.",
            "Penghapusan tombol manual 'Save Auto-Login Credentials' (akun terverifikasi otomatis sejak awal).",
            "Failover dinamis Windows Network Drive: membaca drive Zima Client / SMB lokal jika API ZimaOS timeout.",
            "Keamanan Restore Data: Auto-wipe password lama saat restore ZIP untuk mencegah spam login & pesan 'Too Many Requests'.",
            "Perbaikan monitoring partisi ZimaOS untuk Admin (sys_disk 3.6TB & mount point aktif) dan Non-Admin (filter izin Samba).",
            "Koreksi HTTP Method kontrol daya server (Reboot & Shutdown) ke method PUT sesuai spesifikasi ZimaOS.",
            "Penerapan Client Session Reuse untuk mencegah login berulang tiap 5 detik dan mengurangi beban CPU/jaringan.",
            "Sistem Auto-Changelog terpusat dan Auto-Backup source code ke direktori /bin pada skrip build bat.",
        ],
    },
    {
        "version": "3.5.3",
        "channel": "Alpha",
        "date": "2026-09-19 20:15",
        "notes": [
            "Dynamic API Role Verification untuk akun Admin sekunder (non-UID 1).",
            "Perhitungan telemetri RAPL CPU Wattage real-time.",
            "Stale Cache Fallback untuk mencegah kekosongan data saat server spin-up.",
        ],
    },
    {
        "version": "3.5.2",
        "channel": "Alpha",
        "date": "2026-09-19 15:32",
        "notes": [
            "Arsitektur Dual-Route Syncthing: Jalur LAN (Port 8384) + WAN Subdomain Publik.",
            "Auto-Switch cerdas mengikuti status jaringan (LAN lokal vs Domain publik).",
            "Dialog konfigurasi interaktif Dual-Route di dialogs.ps1.",
            "Dukungan protokol HTTPS aman untuk subdomain reverse proxy (port 443).",
        ],
    },
]


def generate_changelog_text():
    """Menghasilkan teks format CHANGELOG.txt."""
    lines = []
    for entry in CHANGELOG_HISTORY:
        lines.append("===================================================")
        lines.append(f"[v{entry['version']} - {entry['channel']}] - {entry['date']}")
        lines.append("Catatan:")
        for idx, note in enumerate(entry.get("notes", entry.get("features", [])), 1):
            lines.append(f"{idx}. {note}")
        lines.append("===================================================\n")
    return "\n".join(lines).strip() + "\n"


def generate_changelog_markdown():
    """Menghasilkan teks format CHANGELOG.md."""
    lines = ["# Changelog MyServer Desktop\n"]
    for entry in CHANGELOG_HISTORY:
        lines.append(f"## [v{entry['version']} - {entry['channel']}] - {entry['date']}\n")
        for note in entry.get("notes", entry.get("features", [])):
            lines.append(f"- {note}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def sync_changelog_files(base_dir=None):
    """Menyinkronkan database changelog ke berkas fisik CHANGELOG.txt dan CHANGELOG.md."""
    if not base_dir:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    txt_path = os.path.join(base_dir, "CHANGELOG.txt")
    md_path = os.path.join(base_dir, "CHANGELOG.md")

    txt_content = generate_changelog_text()
    md_content = generate_changelog_markdown()

    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt_content)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        return True
    except Exception as e:
        print(f"[!] Gagal menyinkronkan changelog: {e}")
        return False


def backup_source_code(base_dir=None):
    """Membuat arsip zip cadangan source code ke direktori bin/."""
    if not base_dir:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    bin_dir = os.path.join(base_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    try:
        import zimaos_app
        ver = getattr(zimaos_app, "APP_VERSION", "3.7.0")
        chan = getattr(zimaos_app, "APP_CHANNEL", "Stable")
    except Exception:
        ver = "3.7.0"
        chan = "Stable"

    zip_filename = f"source_v{ver}_{chan}.zip"
    zip_path = os.path.join(bin_dir, zip_filename)

    import zipfile
    extensions_to_include = {".py", ".ps1", ".ico", ".bat", ".md", ".txt", ".json"}
    files_to_skip = {"config.json"}

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(base_dir):
                rel_root = os.path.relpath(root, base_dir)
                if any(part in ["build", "dist", "__pycache__", ".git", "bin", "archive"] for part in rel_root.split(os.sep)):
                    continue
                for file in files:
                    if file in files_to_skip:
                        continue
                    ext = os.path.splitext(file)[1].lower()
                    if ext in extensions_to_include:
                        abs_f = os.path.join(root, file)
                        rel_f = os.path.relpath(abs_f, base_dir)
                        zipf.write(abs_f, rel_f)
        print(f"[v] Backup source code berhasil disimpan ke: {zip_path}")
        return True
    except Exception as e:
        print(f"[!] Gagal membuat backup source code: {e}")
        return False


if __name__ == "__main__":
    if "--backup" in sys.argv:
        backup_source_code()
    if sync_changelog_files():
        print("[v] CHANGELOG.txt & CHANGELOG.md berhasil disinkronkan secara otomatis!")
    else:
        sys.exit(1)



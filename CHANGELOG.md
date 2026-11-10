# Changelog MyServer Desktop

## [v4.5.2 - Beta] - 2026-11-10

- Pengalihan Otomatis Rute Terminal SSH via Remote P2P saat Rute WAN Aktif:
  - Terminal SSH ZimaOS secara cerdas mendeteksi rute WAN dan secara otomatis mengalihkan target koneksi ke Virtual IP Remote P2P (EasyTier / ZeroTier) di mana port 22 terbuka, persis seperti mekanisme akses Web App dan mount SMB.
- Resolusi Cerdas REST API Backend ZimaOS pada Jaringan Eksternal (WAN):
  - Memperbaiki kegagalan koneksi REST API backend (port 8080) saat pengguna berada di luar jaringan rumah (misalnya kantor) dengan mengalihkan endpoint backend ke Remote P2P IP secara dinamis, sehingga daftar VM sisi server tidak lagi menghilang.
- Penyelarasan Schema Pydantic Backend ZimaOS (v1.2.1) & Persistensi Otomasi 24/7:
  - Menyelaraskan field schema Pydantic (VmCreateRequest dan VmUpdateRequest) untuk menerima format camelCase dari desktop (keepAliveEnabled, apiKey, machineId, runtimeMinutes) serta membongkar struktur nested autoRestart dan autoOn.
  - Memastikan fitur Always-On dan otomasi penjadwalan benar-benar tersimpan ke database SQLite server ZimaOS dan tersinkronisasi 100% antar-perangkat.
- Sinkronisasi Status Riil VM InstaBox (Case-Insensitive) & Durasi Timer Uptime:
  - Memperbaiki pengecekan status microVM menjadi case-insensitive (running / active), mengatasi kendala tampilan status Tidur (amber) padahal VM sedang berjalan (Running) di instabox.sh.
  - Membaca durasi runtime riil (currentRunSeconds / uptimeSeconds / runDurationSeconds) dari API InstaBox, sehingga progress timer kartu VM menampilkan menit riil sesuai pusat cloud dan bukan ter-reset ke 1 menit.
  - Memperbaiki interval loop scheduler server berbasis timestamp riil untuk mencegah inflasi waktu runtime per siklus 20 detik.

## [v4.5.1 - Beta] - 2026-11-10

- Perbaikan Sinkronisasi VM Multi-Device:
  - Mengimplementasikan query dinamis ke backend ZimaOS saat endpoint POST /api/vms/load dipanggil, sehingga VM yang disimpan di Server langsung muncul di Perangkat B dan seluruh perangkat klien yang terhubung (mengatasi kendala 'No Virtual Machines Added').
  - Sinkronisasi pintar otomatis pada VmManagerView saat inisialisasi, pergantian server aktif, maupun penerimaan sinyal event myserver:refresh.
  - Penambahan ref pelindung penulisan agar state lokal tidak menimpa data konfigurasi sebelum proses sinkronisasi remote tuntas.
- Resolusi Akun Dinamis Terminal SSH ZimaOS (Anti-Hardcoding):
  - Mengganti string statis 'root' dengan resolusi dinamis akun Linux pengguna dari profil server yang sedang aktif (misalnya 'algitha' atau 'stimi').
  - Mengatasi penolakan autentikasi 'Permission denied' pada terminal SSH PowerShell dan memastikan perintah salin SSH akurat 100%.

## [v4.5.0 - Beta] - 2026-11-10

- Pengelompokan & Penyimpanan VM Multi-Target (Server vs Lokal):
  - Opsi penyimpanan dan automasi VM pada modal Tambah VM: Server (<Nama Server Aktif>) vs Lokal (Perangkat Ini).
  - VM kelompok Server tersimpan di database SQLite ZimaOS (MyServer Backend by algitha v1.2.0) dan disinkronisasi ke seluruh perangkat yang terhubung ke server tersebut.
  - Daemon latar belakang 24/7 di ZimaOS mengeksekusi automasi Always-On, Smart Reset 8 jam tanpa cooldown, Auto-On, dan Auto-Restart mandiri meskipun laptop pengguna mati.
- Migrasi 1-Klik VM Terhubung (Server <-> Lokal):
  - Tombol migrasi cepat di dalam menu Edit VM untuk memindahkan VM beserta konfigurasi SSH dan jadwal automasi antara Server dan Lokal secara atomik dalam 1 klik tanpa perlu mengisi ulang form.
- Akses Cepat Terminal SSH ke Server ZimaOS:
  - Tombol penuh berdesain hijau selaras dengan tombol referensi Copy SSH Command tepat di bawah baris tombol Tambah, Ubah, Hapus pada menu Server & Network (ServerView.tsx).
  - Menyalin perintah SSH (ssh root@<host>) ke clipboard dan meluncurkan terminal interaktif secara otomatis.
- Pemfilteran Dinamis & Pengelompokan Kondisional Pintar:
  - Menampilkan daftar VM sesuai server ZimaOS yang aktif ditambah VM Lokal.
  - Header pemisah kelompok (SERVER: <NAMA SERVER> dan LOKAL · PERANGKAT INI) hanya muncul apabila kedua kelompok memiliki VM. Jika server terhubung tidak memiliki VM, header kelompok otomatis disembunyikan secara bersih.
- Perbaikan Bug Animasi CRT Mode Offline (Isolasi Ketat):
  - Menghapus lapisan animasi CRT (glitch, scanlines, hum, vignette, tracking band) khusus pada kartu File Manager (FILES_OFFLINE_SVG) dan VM Manager (VM_OFFLINE_SVG) mode offline. Seluruh kartu mode online dan kartu offline lainnya tetap 100% utuh dan identik.
- Optimalisasi Modal UX & Struktur Scrollbar:
  - Tombol hapus di header modal telah dieliminasi sehingga hanya tersisa satu tombol hapus di bagian bawah menu edit.
  - Struktur scrollbar disederhanakan menjadi satu scrollbar tunggal yang rapi tanpa slider ganda.

## [v4.4.7 - Beta] - 2026-11-09

- Perbaikan Menyeluruh Fitur "Tetap Nyala" (Always-On) & "Auto-Restart" + Daemon Latar Belakang 24/7:
  - Memperbaiki bug ReferenceError (`vmsRef is not defined`) dan *stale closure* pada `VmManagerView.tsx` yang sebelumnya membuat penjadwal otomatis berhenti berfungsi.
  - Mengaktifkan tombol "Tetap Nyala" pada VM InstaBox yang sedang tidur kini langsung membangunkan VM seketika (*instant wake*).
  - Menambahkan thread daemon latar belakang 24/7 (`vm_power_scheduler_loop`) di `myserver_core_service.py` agar fitur Always-On, Auto-On, dan Auto-Restart tetap berjalan meskipun jendela UI ditutup ke System Tray.
- Fitur Baru Tombol & Penjadwal "Auto-On" (Nyala Otomatis) dengan Tata Letak Grid Aksi 3x2 Simetris:
  - Menambahkan tombol `Auto-On` pada Grid Aksi 3x2 (`Layar Virtual | SFTP`, `Auto-On | Auto-Restart`, `Bangunkan/Tidurkan | Tetap Nyala`).
  - Mendukung 2 mode penjadwalan: Mode Jam Tertentu (`HH:MM` beserta pilihan hari aktif) dan Mode Jeda Setelah Mati (`X` detik/menit/jam setelah VM mati atau tertidur).
- Tombol Hapus VM & Modal Konfirmasi Penghapusan:
  - Menambahkan tombol Hapus VM (`Trash2`) di samping tombol Edit (`Pencil`) pada baris header setiap kartu VM, dilengkapi popup modal konfirmasi penghapusan dwibahasa (`ID/ENG`).
  - Memastikan seluruh kartu VM selalu berstatus tertutup rapi (*minimized*) secara default saat menu dibuka.
- Pilihan Target Pembukaan Layar Virtual & Isolasi Sesi Login Multi-Akun InstaBox:
  - Menambahkan opsi pembukaan Layar Virtual melalui **Jendela MyServer (Sesi Terisolasi)** atau **Browser Bawaan**, dilengkapi kotak centang pengingat pilihan per-VM.
  - Setiap VM memiliki direktori profil WebView2 terpisah (`data/vms/<vm_id>/webview_profile`) sehingga pengguna dapat login ke banyak akun InstaBox berbeda secara bersamaan tanpa saling ter-logout.
- Resolusi Ikon Otomatis (Auto-Favicon) untuk Custom Web Apps:
  - Aplikasi web kustom di menu `Apps` kini otomatis mengambil dan menampilkan ikon situs (*favicon*) dari URL aplikasi terkait dengan fallback berlapis ke ikon vektor standar.
- Perbaikan Persistensi Preferensi Mode Light/Dark Lintas Reboot:
  - Memperbaiki endpoint `/api/load_settings` di `myserver_core_service.py` dan sinkronisasi tema di `api.real.ts` serta `store.tsx` agar pilihan Light Mode atau Dark Mode tersimpan permanen di `config.json` dan tidak ter-reset saat laptop dinyalakan ulang.


## [v4.4.6 - Beta] - 2026-11-09

- Fitur Khusus "Tetap Nyala" (Always-On) Khusus InstaBox Cloud:
  - Mengirimkan anti-sleep heartbeat berkala tiap 15 menit ke API InstaBox agar mesin tidak tertidur otomatis karena idle.
  - Keterkaitan cerdas dengan Auto-Restart: mengeksekusi siklus Smart Reset (pause 2 detik lalu bangunkan kembali) sebelum continuous runtime mencapai 8 jam, mencegah mesin terkena penalti cooldown 20 menit dari cloud.
  - Proteksi penuh logika VM Umum: Auto-Restart untuk VM Manual SSH tetap murni memanggil handleTogglePower tanpa intervensi.
- Tombol Edit VM Per-Provider & Filter Modal Otomatis:
  - Menambahkan tombol Edit (ikon pensil) di baris header setiap kartu VM.
  - Modal form edit otomatis terkunci sesuai provider VM (tab switcher disembunyikan): form InstaBox untuk VM InstaBox, dan form Manual SSH untuk VM Manual SSH.
- Sinkronisasi Status Riil Cloud:
  - Memperbaiki normalisasi status API sehingga saat mesin tertidur otomatis dari pusat cloud, pill status di MyServer langsung beralih ke "Sleep" / "Tidur" (kuning/amber), bukan tertahan di "Active".
- Perbaikan UI/UX, Animasi Accordion & Nol Emoji:
  - Seluruh kartu informasi VM berstatus tertutup rapi (collapsed/minimized) secara default saat halaman dimuat.
  - Animasi buka-tutup kartu menggunakan CSS Grid transition halus dan rotasi chevron 180 derajat.
  - Standardisasi seluruh ikon tombol aksi ke ukuran 16x16px (`size-4 shrink-0`) sehingga tidak lagi tertekan/menciut oleh flexbox.
  - Penyelarasan bahasa simetris (ID/ENG) pada kamus i18n dan pembersihan total teks dummy `expires in 7d`.

## [v4.4.5 - Beta] - 2026-11-09

- Perbaikan Endpoint Daya InstaBox Cloud:
  - Mengoreksi routing API pause InstaBox menjadi `POST /v1/machines/{id}/suspend` yang valid sesuai spesifikasi OpenAPI InstaBox.
  - Memperbaiki scoping shadow variable UnboundLocalError pada do_POST di myserver_core_service.py.
  - Memulihkan fungsionalitas tombol Tidurkan VM dan Bangunkan VM secara real-time.
- Perbaikan kontras tombol aksi pada tema terang (Light Mode) menggunakan varian subtle dengan garis tepi presisi.

## [v4.4.4 - Beta] - 2026-11-08

- Redesain Kartu VM Manager Sesuai Standar UI Resmi & LED Dot Matrix Bar:
  - Mengadopsi style dot matrix LED SVG 42 kolom x 3 baris dari File Manager (`FilesView.tsx`) untuk visualisasi progres batas waktu 8 jam InstaBox secara proporsional dan dinamis (hijau <70%, kuning 70-85%, merah >85%).
  - Mempertahankan 100% tata letak shell menu luar VM Manager dari v4.4.3 Beta tanpa perubahan, hanya meredesain bagian dalam kartu informasi VM.
  - Menghilangkan seluruh hardcoded telemetri fiktif; CPU, RAM, dan Disk kini hanya menampilkan nilai riil atau tanda strip (`—`) jika data belum tersedia/offline.
  - Membersihkan seluruh data privasi dari repositori: inisialisasi state murni kosong (Empty State) dan modal form selalu bersih dari hardcoded token.
- Fitur Jadwal Auto-Restart Seluruh VM & Reset Limit 8 Jam InstaBox:
  - Tombol aksi seragam dan bersih: `Jadwal Auto-Restart` pada semua kartu VM.
  - Penjadwalan fleksibel berdasarkan interval (detik, menit, jam) atau jam tertentu (HH:MM).
  - Khusus InstaBox: Integrasi siklus resmi (Pause -> 5 detik -> Resume) untuk mereset timer batas waktu 8 jam kembali ke 0 tanpa terkena penalti cooldown 20 menit, dilengkapi tombol aksi langsung `Reset Limit 8 Jam Sekarang`.
  - Untuk VM Linux/VPS manual: Mengeksekusi restart sistem (`sudo reboot`) via terminal/SSH.
- Sinkronisasi Versi Atomik v4.4.4 Beta pada seluruh stack biner, frontend, backend, installer, dan manifest.

## [v4.4.3 - Beta] - 2026-11-08

- Perombakan Total UI/UX VM Manager:
  - Merapikan tata letak header menu: judul kategori `VIRTUAL MACHINE` di sisi kiri dan tombol `+ Tambah VM` di sisi kanan dengan jarak proporsional tanpa terpotong.
  - Menghapus banner mock toggle `1 VM Connected (Card Mode) + Tampilkan 2 VM (Accordion)` sehingga tampilan sepenuhnya otomatis reaktif (1 VM = Card Mode, 2+ VM = Accordion Mode).
  - Mengganti tombol aksi hardcoded Antigravity menjadi aksi universal: Salin / Hubungkan Perintah SSH Terminal, Buka Layanan Web (opsional), dan kontrol daya Sleep/Wake.
  - Menghapus seluruh hardcoded spesifikasi hardware fiktif. Seluruh data koneksi VM (Host, Port, Token, User, Expiry) berasal murni dari input pengguna dan tersimpan persisten.
- Sinkronisasi Versi Atomik v4.4.3 Beta pada seluruh stack biner, frontend, backend, installer, dan manifest.

## [v4.4.2 - Beta] - 2026-11-08

- Integrasi Aset Kartu Baru: Mengintegrasikan 4 file SVG terbaru dari Figma (`File Manager Card.svg`, `File Manager Card (offline).svg`, `VM Manager Card.svg`, dan `VM Manager Card (offline).svg`) tanpa merubah bentuk, font, atau warna desain asli.
- Restorasi Penuh Animasi Retro CRT: Memulihkan efek visual scanline, tube warmth vignette, CRT jitter glitch, dan horizontal tracking band pada semua slot kartu.
- Restorasi Tombol "..." File Manager: Memfungsikan kembali tombol 3 titik pada kartu File Manager untuk membuka sub-menu Storage & Files, sementara klik pada bodi kartu tetap membuka File Explorer native.
- Penyelarasan Frame Auto Layout 1:1 Figma: Mengunci dimensi Auto Layout kartu 284x236 (padding horizontal 16px, vertikal 8px) serta menyelaraskan frame footer status dan header flyout shell (Node 83:292 & 134-17822) dengan clearance aman ~21px.
- Sinkronisasi Versi Atomik v4.4.2 Beta pada seluruh biner, frontend, backend, installer, dan tauri manifest.

## [v4.4.1 - Beta] - 2026-11-08

- Perbaikan Tuntas Grid Kontainer Kartu & Eliminasi Total Horizontal Scroll:
  - Mengembalikan struktur tata letak murni 1:1 sesuai versi v4.3.2 Beta (`w-[252px] h-[228px]`) tanpa pembungkus ekstra yang menyempitkan lebar kontainer.
  - Mematikan total scrollbar horizontal (`overflow-x-hidden`) dan menyembunyikan scrollbar OS (`scrollbar-none`) agar kartu tidak terdorong ke kiri dan tidak memunculkan bilah scroll tebal yang memotong elemen kartu.
  - Navigasi kartu ke bawah (downward scrolling) kini berjalan mulus melalui mouse wheel atau trackpad gesture untuk mengakses kartu ke-5 VM Manager tanpa layout shift.
- Penyematan Rangkaian Efek CRT Retro Elektronik pada Kartu VM Manager:
  - Menerapkan CRT electronics suite lengkap (`crt-glitch-content`, `crt-layer-scanlines`, `crt-hum-wrapper`, `crt-layer-vignette`, dan `crt-tracking-band`) pada kartu VM Manager online dan offline.
  - Menambahkan konfigurasi timing seed organik `[data-crt-slot="vm"]` pada `crt-cards.css` sehingga kartu VM Manager memiliki animasi hover glitch jitter, tube warmth, tracking band flash, dan scanline hum yang serasi dengan 4 kartu lainnya.
- Sinkronisasi Versi Atomik v4.4.1 Beta pada seluruh biner, frontend, backend, installer, dan tauri.

## [v4.4.0 - Beta] - 2026-11-08

- Integrasi Sub-sistem Virtual Machine (VM Manager) & Antigravity Remote:
  - Menambahkan kartu menu ke-5 'VM Manager' pada Home View dengan navigasi scroll vertikal mulus (tanpa layout shift pada header atau footer).
  - Tampilan dinamis 1:1 sesuai desain SVG asli pengguna (`VM Manager Card.svg` & `VM Manager Card (offline).svg`).
  - Tampilan adaptif cerdas: Mode Kartu Tunggal (Single Card) jika terhubung 1 VM, dan Mode Accordion jika terhubung 2 atau lebih VM.
  - Fitur lengkap: Spesifikasi hardware (CPU, RAM, NVMe), pelacak batas waktu nyala continuous (maksimal 8 jam), indikator idle auto-sleep (30 menit), peluncur pre-flight otomatis ("Buka Antigravity Remote" dengan wake otomatis sebelum akses webapp), toggle kontrol daya tidur/bangun VM, dan shortcut terminal SSH.
  - Dialog modal konfirmasi penghapusan VM dengan proteksi peringatan risiko serta dialog formulir tambah/edit VM yang terintegrasi penuh.
  - Konsistensi penuh lintas tema Dark/Light, koneksi Online/Offline, dan bahasa ID/EN.
- Integrasi Backend Core Service & InstaBox Manager (`instabox_manager.py`):
  - Modul independen REST API v1 (`https://api.instabox.sh/v1`) dengan penanganan idempotency key, token otorisasi Bearer, sinkronisasi status mesin, kontrol status tidur/bangun, serta Smart Anti-Cooldown Guard (pencegahan cooldown wajib melalui reset runtime).
  - Endpoint backend baru: `/api/instabox/vms`, `/api/instabox/status`, `/api/instabox/wake`, `/api/instabox/pause`, `/api/instabox/preflight_launch`, `/api/instabox/smart_reset`.
- Perbaikan Mutlak Biner Font Doto Lokal:
  - Mengarahkan deklarasi `@font-face` di `index.css` langsung ke TrueType biner valid `Doto-Black.ttf` dengan `font-display: block`, mengeliminasi galat decode font gzipped lokal dan memastikan seluruh tampilan LCD footer dan badge dock tampil dengan font dot-matrix asli tanpa fallback serif.
- Bump Versi Atomik v4.4.0 Beta: Menyelaraskan seluruh konstanta versi pada UI frontend, Core Service backend, metadata biner PE Windows, Inno Setup installer, dan Cargo manifest untuk deteksi instan oleh GitHub Auto-Update Checker.

## [v4.3.2 - Beta] - 2026-11-08

- Penyelarasan Presisi Chip Footer Mode OFFLINE (1:1 Acuan footer.relative (offline).svg):
  - Mengubah styling tombol rute jaringan (LAN/WAN) dan tombol akun pengguna (Account/User) saat server offline agar selaras 100% dengan desain footer.relative (offline).svg.
  - Ikon globe dan ikon pengguna kini mengadopsi warna charcoal gelap #2D2D2D, teks rute dan nama akun menggunakan abu-abu lembut #CCCCCC, serta chevron dropdown menggunakan #CBCBCA.
  - Menggantikan bayangan biru pada chip akun saat offline dengan bayangan halus beraksen kemerahan 0px 4px 6px 0px rgba(130,0,22,0.15), inset 4px 4px 8px 0px rgba(130,0,22,0.30), dan bayangan chip rute 0px 4px 6px 0px rgba(130,0,22,0.20), inset 4px 4px 8px 0px rgba(130,0,22,0.30).
  - Seluruh dimensi, padding, font size, border radius, dan interaktivitas tetap 100% konsisten (zero layout shift).
- Bump Versi Atomik v4.3.2 Beta: Menyelaraskan seluruh konstanta versi pada UI frontend, Core Service backend, metadata biner PE Windows, Inno Setup installer, dan Cargo manifest untuk deteksi instan oleh GitHub Auto-Update Checker.

## [v4.3.1 - Beta] - 2026-11-08

- Perbaikan Cepat (Hotfix) Runtime ReferenceError NoticeMarquee: Menambahkan parameter `isOnline` pada deklarasi parameter fungsi `NoticeMarquee` dan saat pemanggilannya di `FooterStatus` (`FlyoutShell.tsx`), mengeliminasi tuntas galat fatal "Failed to Load View: isOnline is not defined" pada tampilan beranda.
- Bump Versi Atomik v4.3.1 Beta: Menyelaraskan seluruh konstanta versi pada UI frontend, Core Service backend, metadata biner PE Windows, Inno Setup installer, dan Cargo manifest untuk deteksi instan oleh GitHub Auto-Update Checker.

## [v4.3.0 - Beta] - 2026-11-08

- Penuntasan Definitif Akses Terkunci (Access Denied) In-App Updater: Mengonfigurasi hak akses Inno Setup menjadi elevated (`PrivilegesRequired=admin` dan `PrivilegesRequiredOverridesAllowed=commandline`) serta menambahkan flag `runasoriginaluser` pada eksekusi aplikasi paska-instalasi. Dengan elevasi ini, installer memiliki hak penuh untuk mematikan daemon background elevated EasyTier (`easytier-core.exe` & `easytier-cli.exe`), menuntaskan galat `DeleteFile failed; code 5. Access is denied` saat update berlangsung.
- Penguatan Backend Pre-Installer Termination: Menambahkan penutupan paksa proses EasyTier via `taskkill` dan jeda `time.sleep(1.5)` pada handler backend `/api/download_and_install_update` sebelum installer dijalankan, memastikan seluruh open file handle kernel terlepas sempurna.
- Tampilan UI Mode OFFLINE Murni (1:1 Acuan v4.2.7 Beta):
  - Mengadopsi 4 kartu CRT standby elegan berbasis SVG terbaru pengguna (`Backup Card (offline).svg`, `File Manager Card (offline).svg`, `Apps Card (offline).svg`, dan `Options card (offline).svg`) dengan tampilan CRT monitor standby gelap (`#121212`).
  - Penyelarasan Logo CRT: Kata "Server" pada bezel monitor bertransformasi menjadi dot-matrix merah `#E60004` (glow `#FF001E`), 100% selaras dengan status "Offline" pada kartu server bawah.
  - Kartu Server Bawah (`FooterStatus`): Mengadopsi glow merah `#FF001E`, nama server font dots abu-abu `#2D2D2D`, status koneksi "Offline" merah `#E60004`, dan lonceng notifikasi abu-abu `#2E2E2E` (Idle).
  - Mini Tray Dock Telemetri: Unit telemetri kiri menampilkan readout strip standby (`–`) dan titik LED unlit dalam font dots abu-abu `#2E2E2E`.
  - Flyout Background Grid Merah: Mengintegrasikan tekstur latar belakang grid merah halus khusus mode offline untuk Dark Mode dan Light Mode.
- Penyelarasan Menyeluruh Seluruh Font Hijau Menjadi Merah saat Offline (Zero Layout Shift):
  - Mengimplementasikan CSS semantic token remapping otomatis `[data-server-status="offline"]` di `index.css`, meremap `--color-brand` dan `--color-success` ke `#E60004`.
  - Seluruh font teks, badge, checkmark, dan aksen hijau pada seluruh menu (Server & Network, Settings & Preferences, Server Power Control, Backup & Sync, Web Apps, dan Storage & Files) otomatis bertransformasi menjadi merah `#E60004` saat server offline, tanpa mengubah margin, padding, ukuran font, maupun dimensi layout 1 pixel pun.
- Bump Versi Atomik v4.3.0 Beta: Menyelaraskan seluruh konstanta versi pada UI frontend, Core Service backend, metadata biner PE Windows, Inno Setup installer, dan Cargo manifest untuk deteksi instan oleh GitHub Auto-Update Checker.

## [v4.2.7 - Beta] - 2026-11-07

- Perbaikan Penguncian Packet.dll pada In-App Update: Menambahkan penghentian bersih proses background `easytier-core.exe` dan `easytier-cli.exe` pada backend sebelum installer dieksekusi, serta pada prosedur `KillRunningAppProcesses()` di Inno Setup, menuntaskan galat `DeleteFile failed; code 5. Access is denied` saat update di perangkat klien.
- Perbaikan & Dukungan Pembaruan via ZIP Portabel: Menambahkan graceful shutdown daemon EasyTier dan perintah taskkill pada skrip batch `myserver_upd_*.bat` di `apply_zip_update()`, memastikan berkas paket ZIP resmi yang diunduh dari GitHub dapat diterapkan sempurna tanpa terhambat file lock.
- Penyelarasan Layout Chip Modal Power Subsystem: Mengoptimalkan tata letak baris chip `FooterStatus` di `FlyoutShell.tsx` saat notice pill dinonaktifkan sehingga mengisi lebar penuh kartu dengan margin seimbang, serta memadatkan teks chip pada `PowerView.tsx` (`9 / UDP`, `Broadcast`, `Need LAN`/`Perlu LAN`) sehingga bebas dari terpotongnya tepi kanan chip.
- Penghapusan Toggle Legacy Auto-connect ZeroTier: Menghapus baris pengaturan `autoZeroTier` dari jendela Pengaturan demi keselarasan murni arsitektur dual-engine remote (Auto, EasyTier, ZeroTier).
- Penyelarasan Tombol Change Log Folder: Menyelaraskan teks tombol menjadi `Change Folder...` / `Ubah Folder...` dengan penahan truncate simetris sehingga teks muat rapi di dalam pill tombol berdampingan dengan tombol `Copy Log`.
- Kamus Bilingual Lengkap Aksi Remote: Melengkapi terjemahan tombol Hubungkan/Putuskan (`Connect`/`Disconnect`), subtitle status peer node, serta modal Ubah Remote ID EasyTier dan ZeroTier secara kontekstual.
- Jarak Header Kartu Remote & Indikator Titik Blooming: Menambahkan gap dan ruang fleksibel pada header kartu remote di Server & Network, serta menyederhanakan indikator statusnya menjadi bulatan blooming `StatusDot` yang bersih dan elegan (tanpa mengubah indikator dock putih di bagian bawah).
- Bump Versi Atomik v4.2.7 Beta: Menyelaraskan seluruh konstanta versi pada UI frontend, Core Service backend, metadata biner PE Windows, Inno Setup installer, dan Cargo manifest untuk deteksi instan oleh GitHub Auto-Update Checker.

## [v4.2.6 - Beta] - 2026-11-07

- Restorasi Ikon Pensil Edit Remote/Network ID: Memperbaiki render tombol edit pensil pada kartu EasyTier dan ZeroTier di menu Server & Network. Sebelumnya pembungkusan komponen `<Button>` dengan padding horizontal default (`px-3`) menyebabkan ikon pensil (`Edit2`) terhimpit menjadi bintik mikro (~2px); kini digantikan dengan tombol circular semantik (`rounded-full h-7 w-7`) dengan rendering SVG stroke tegas yang tampil tajam dan presisi pada mode Dark maupun Light.
- Sinkronisasi Versi Atomik v4.2.6 Beta: Menyelaraskan seluruh konstanta versi pada UI frontend, Core Service backend, metadata biner PE Windows, Inno Setup installer, dan Cargo manifest untuk deteksi instan oleh GitHub Auto-Update Checker.

## [v4.2.6 - Beta] - 2026-11-07

- Perbaikan Layout & Overflow Tombol Remote ID (Pencil Button): Memperbaiki tombol aksi pensil Edit Remote ID dan Edit Network ID di `ServerView.tsx` menjadi circular button presisi (`h-7 w-7 rounded-full bg-surface-muted hover:bg-line text-ink`), menghilangkan tuntas masalah tombol edit yang meluber keluar dari batas kartu (*card overflow*) baik pada kartu EasyTier maupun ZeroTier.
- Penyelarasan UX Tombol Remote Seragam: Menyelaraskan struktur tata letak tombol aksi kartu ZeroTier agar identik dengan EasyTier (tombol aksi utama Putuskan/Hubungkan yang fleksibel dan tombol pensil terpisah di samping kanan dalam kartu).
- Verifikasi Integritas Failover & Multi-Remote: Memastikan kestabilan switch dinamis antara EasyTier dan ZeroTier untuk mounting drive SMB File Explorer serta navigasi aplikasi Web Apps pada rute WAN.
- Bump Versi Atomik v4.2.6 Beta: Menyelaraskan seluruh konstanta versi pada UI frontend, Core Service backend, metadata biner PE Windows, Inno Setup installer, dan Cargo manifest untuk deteksi instan oleh GitHub Auto-Update Checker.

## [v4.2.5 - Beta] - 2026-11-07

- Perbaikan Klasifikasi Tipe Rute Remote (Eliminasi Salah Deteksi LAN): Memperbaiki helper `classifyRoute` di `HomeView.tsx` agar memprioritaskan deteksi rute Remote P2P (`EasyTier` dan `ZeroTier`, subnet `10.126.126.x`, `172.24.x`, `172.25.x`) sebelum evaluasi subnet LAN, menghilangkan tuntas bug di mana rute EasyTier sebelumnya salah dilabeli sebagai `LAN (EasyTier Remote (P2P))` dengan ikon network.
- Auto-Failover Tangguh EasyTier -> ZeroTier: Memperbaiki logika deteksi kesehatan EasyTier di `config_manager.py` dan `easytier_manager.py`. Sistem kini memverifikasi apakah server peer EasyTier benar-benar terhubung dan responsif. Jika EasyTier daemon berjalan namun server peer tidak merespons (misal server belum online di EasyTier mesh atau relay terblokir), mode Auto secara cerdas dan otomatis langsung mengalihkan rute remote ke ZeroTier (`172.24.0.1` / `172.25.0.1`).
- Resolusi Dinamis SMB WAN Multi-Kandidat: Memperbarui `smb_mount_manager.py` agar mengumpulkan seluruh kandidat IP remote (EasyTier & ZeroTier) dan menguji port 445 SMB. Ketika EasyTier tidak merespons, pemasangan share drive SMB pada rute WAN otomatis langsung beralih ke IP ZeroTier yang sehat, memastikan seluruh drive disk Windows File Explorer berhasil terpasang sempurna tanpa error.
- Web Apps WAN Failover Otomatis: Tautan aplikasi Docker/Compose pada rute WAN kini secara otomatis diarahkan ke IP remote yang benar-benar aktif dan dapat dijangkau (ZeroTier saat EasyTier tidak merespons).
- Bump Versi Atomik v4.2.5 Beta: Menyelaraskan seluruh konstanta versi pada UI frontend, Core Service backend, metadata biner PE Windows, Inno Setup installer, dan Cargo manifest untuk deteksi instan oleh GitHub Auto-Update Checker.

## [v4.2.4 - Beta] - 2026-11-07

- Penyelarasan Penuh Standar Zima Client v2.3.5 untuk EasyTier Mesh: Menyesuaikan parameter identitas jaringan EasyTier agar sama persis dengan backend ZimaOS (menggunakan 16-karakter Remote ID murni sebagai network_name dan network_secret, serta menambahkan daftar relay resmi IceWhale tcp/udp://139.162.29.247:11010, 103.29.68.33:11010, dan 172.239.28.141:11010).
- Eliminasi Freeze / Timeout RPC Telemetri: Menambahkan short-circuit guard sebelum pemanggilan easytier-cli.exe dan cache status lokal 1.2 detik sehingga seluruh request API telemetri merespons seketika dalam < 50ms tanpa ada request yang menggantung atau melempar os error 10060.
- Resolusi Wintun Virtual Adapter Otomatis: Memastikan adapter TUN kernel Windows et_* berhasil tercipta melalui elevasi proses mandiri ShellExecuteW RunAs, menampilkan virtual IPv4 10.126.126.2 secara akurat di antarmuka (Laptop IP).
- SMB & Web Apps WAN Failover Dinamis: Akses share drive SMB (\\10.126.126.1) dan Web Apps Docker/Compose pada rute WAN otomatis terhubung langsung ke IP remote EasyTier saat aktif tanpa terintervensi ZeroTier.
- Bump Versi Atomik v4.2.4 Beta: Seluruh metadata biner, package installer Inno Setup, metadata PE, dan konfigurasi rilis diperbarui ke versi v4.2.4 Beta untuk deteksi pembaruan instan via Auto-Update Checker.

## [v4.2.3 - Beta] - 2026-11-07

- Arsitektur Elevasi Daemon Mandiri (Zero WebView2 Panic): Menghilangkan pemaksaan requireAdministrator pada shell UI Tauri (MyServer-Beta.exe) untuk mencegah galat fatal WebView2 HRESULT 0x80070578 ('Invalid window handle'). Elevasi hak administrator kini didelegasikan secara mandiri dan aman khusus ke biner background easytier-core.exe via Win32 ShellExecuteW RunAs, sehingga Wintun virtual network adapter berhasil terpasang sempurna tanpa mengorbankan stabilitas antarmuka pengguna.
- Kartu Akses Remote Tunggal Dinamis (Single Remote Card UI): Menata ulang tampilan Server & Network sehingga hanya menampilkan tepat 1 kartu akses remote tunggal yang bertransformasi dinamis mengikuti mode yang dipilih (EasyTier atau ZeroTier), didukung oleh selector tab pill (Auto, EasyTier, ZeroTier).
- Penyelarasan Simetris Tombol Aksi Remote: Tombol Hubungkan/Putuskan dan tombol pensil Edit Remote ID diselaraskan secara simetris dengan pembatasan overflow ketat (zero overflow keluar kartu) baik pada EasyTier maupun ZeroTier.
- Eliminasi Masalah Laptop IP Kosong & Failover Murni: Memperbaiki deteksi status RPC daemon via port 15888 sehingga Laptop IP (10.126.126.2) dan Server IP (10.126.126.1) selalu terisi dan tidak pernah lagi menampilkan strip (-). Mounting SMB dan Web Apps pada mode WAN otomatis dialihkan secara mulus ke subnet 10.126.126.1 tanpa terintervensi ZeroTier ketika EasyTier aktif.
- Bump Versi Atomik v4.2.3 Beta: Seluruh artefak proyek diperbarui ke versi v4.2.3 Beta untuk memastikan Auto-Update Checker langsung menyajikan versi terbaru kepada seluruh pengguna.

## [v4.2.2 - Beta] - 2026-11-07

- Perbaikan Driver Wintun Virtual Adapter (Hak Akses Administrator / UAC): Menyematkan manifest eksekusi administratif (requireAdministrator) pada biner aplikasi (MyServer-Beta.exe dan myserver-core.exe) mengikuti standar Zima Client v2.3.5. Menghilangkan galat rust tun error Failed to create adapter dan Access is denied (0x80070005) saat inisialisasi EasyTier P2P mesh di Windows.
- Standardisasi Subnet ZimaNet EasyTier (10.126.126.0/24): Mengganti flag DHCP (-d true) dengan alokasi IP virtual eksplisit 10.126.126.2/24, menambahkan flag --lazy-p2p, dan menetapkan default server peer IP di 10.126.126.1. Menghilangkan masalah Laptop IP kosong/strip (-).
- Mounting SMB WAN Dinamis EasyTier/ZeroTier: Memperbaiki deteksi rute failover sehingga saat mode EasyTier aktif, mounting SMB File Explorer diarahkan ke subnet 10.126.126.1 tanpa fallback keliru ke IP ZeroTier.
- Routing Dinamis Web Apps di Rute WAN: Menghubungkan alamat port aplikasi Docker/Compose pada rute WAN langsung ke IP remote aktif (EasyTier atau ZeroTier) secara dinamis, sementara link dashboard ZimaOS tetap mempertahankan domain WAN publik.
- Bump Versi Atomik v4.2.2 Beta: Memperbarui seluruh konstanta versi aplikasi, UI frontend, backend Core Service, installer Inno Setup, metadata PE, dan rilis GitHub agar Auto-Update Checker dapat langsung mendeteksi dan menginstal rilis perbaikan ini.

## [v4.2.1 - Beta] - 2026-11-07

- Perbaikan Layout Tombol Remote ID: Memperbaiki flex flow dan padding kartu EasyTier sehingga tombol edit Remote ID menyatu rapi di dalam batas kartu tanpa meluber keluar (zero overflow).
- Penyelarasan UX Tombol EasyTier & ZeroTier: Memisahkan tombol Hubungkan/Putuskan dengan tombol edit pensil pada ZeroTier secara simetris mengikuti tata letak EasyTier.
- Dual Remote Engine Auto-Failover & Selector Manual: Menyediakan sistem failover otomatis khusus dua mode remote (EasyTier <-> ZeroTier) serta kontrol manual (Auto, EasyTier, ZeroTier) agar pengguna dapat mematikan salah satunya.
- Kartu Rute Remote Dinamis Tunggal (Single Card): Menyederhanakan daftar rute jaringan sehingga hanya memunculkan 1 kartu rute remote dinamis yang berubah mulus mengikuti mode remote yang sedang aktif.
- Visual Kartu Auto Failover Solid: Memperbaiki fill kartu Auto Failover rute dengan warna background solid kartu (bg-surface) dan stroke hijau tegas saat aktif di mode Dark dan Light.
- Mounting SMB WAN Dinamis: Mengarahkan koneksi share SMB di rute WAN/Domain ke IP remote yang sedang aktif secara dinamis antara EasyTier dan ZeroTier.
- Akses Web Apps WAN Dinamis: Membangun URL aplikasi web Docker/Compose pada rute WAN menggunakan IP remote aktif, dengan pengecualian link dashboard ZimaOS tetap mengarah ke domain WAN asli.
- Masking URL Seragam '••••': Menyelaraskan seluruh URL yang disembunyikan pada popover menu switch rute menjadi tepat 4 titik '••••' murni tanpa awalan http://.

## [v4.2.0 - Beta] - 2026-11-07

- Integrasi EasyTier P2P Mesh sebagai Remote Engine Utama: Mengadopsi arsitektur embedded background daemon Zima Client v2.3.5 (easytier-core.exe & wintun.dll) untuk akses remote peer-to-peer tanpa batasan firewall, tanpa instalasi driver pihak ketiga di awal, dan mendukung multi-protokol (UDP, TCP, WebSocket Secure port 443).
- Orkestrasi Failover Cerdas (Dual-Engine Remote): Menjadikan ZeroTier sebagai engine cadangan otomatis (auto-failover) saat EasyTier terputus atau saat server tujuan menggunakan ZeroTier network ID. Pengguna baru tidak lagi diwajibkan menginstal ZeroTier saat pertama kali menggunakan aplikasi.
- Background Worker Auto-Update & Notifikasi Tray: Menambahkan worker background loop di Core Service yang memeriksa update GitHub setiap 45 menit, serta memicu notifikasi balon resmi Windows di pojok kanan bawah layar saat update rilis terdeteksi ketika jendela sedang tertutup.
- Sinkronisasi Versi Atomik v4.2.0 Beta: Menyelaraskan seluruh konstanta versi pada UI frontend, Core Service backend, metadata biner PE Windows, Inno Setup installer, dan Cargo manifest.

## [v4.1.1 - Beta] - 2026-11-06

- Perbaikan Form Web App (RPC Argument Swap Fix): Memperbaiki bug pada jembatan antarmuka Tauri RPC (api.real.ts) dan endpoint core service (/api/add_web_app) di mana nama aplikasi sebelumnya menimpa alamat URL (url: args[0]). Sekarang nama aplikasi dan URL tersimpan murni sesuai kolom input pengguna secara presisi 1:1 tanpa tertukar maupun terabaikan.
- Sinkronisasi Versi Atomik v4.1.1 Beta: Menyelaraskan seluruh konstanta versi pada UI frontend, Core Service backend, metadata biner PE Windows, Inno Setup installer, dan Cargo manifest.

## [v4.1.0 - Beta] - 2026-11-06

- Tombol Centang Auto Cek Update (Native UI): Menambahkan baris preferensi pemeriksaan pembaruan otomatis di menu Pengaturan (Hero Header & Accordion Sistem & Startup) dengan gaya visual asli MyServer (`text-micro`, `font-semibold`, `text-ink`, `rounded-control`, `bg-brand` #7BC504). Saat diaktifkan, companion melakukan pemeriksaan pembaruan secara hening di latar belakang saat startup (3.5 detik) dan menampilkan notifikasi halus di Notification Center jika versi baru tersedia.
- Pembersihan Otomatis Berkas Pembaruan di %TEMP%: Menambahkan mekanisme pembersihan otomatis aman (Zero Data Risk - Pasal 2) pada startup daemon myserver-core yang secara spesifik membersihkan berkas sisa artefak pembaruan (`MyServer_Update_*`, `myserver_upd_*.bat`, `myserver_ext_*`) dengan usia > 60 detik tanpa pernah menyentuh data atau berkas pribadi pengguna di direktori mana pun.
- Standardisasi Bahasa Bilingual (Eliminasi Inkonsistensi EN / ID):
  - Menu Apps (Services & Containers): Menghubungkan header seksi ("SERVICES & CONTAINERS"), tombol penambahan ("+ Add App"), tombol buka aplikasi ("Open"), serta tooltip dan menu opsi ke kamus i18n sehingga konsisten berbahasa Inggris saat bahasa Inggris dipilih.
  - Menu Backup & Sync: Menyelaraskan teks tombol pemindaian ("Rescan All"), header daftar jalur ("Backup Paths"), tombol penambahan ("+ Add Path"), badge status ("2-Way (Sync)"), dan teks wizard pembuatan jalur ke kamus i18n bilingual.
- Sinkronisasi Versi Atomik v4.1.0 Beta: Menyelaraskan seluruh konstanta versi pada frontend, backend headless, metadata PE Windows, Inno Setup installer, dan Tauri shell.

## [v4.0.12 - Beta] - 2026-11-06

- Overhaul Marquee Notifikasi Footer: Memperbaiki animasi ticker marquee pada pill notifikasi bawah, teks bergerak halus masuk dari sisi kanan luar kontainer (translateX 25px) meluncur ke kiri (-100%) dengan durasi proporsional (~30-32px/s) tanpa terpotong di tengah layar, dan mengeliminasi bug snap-back kemunculan teks ke-3 dengan fill-mode forwards.
- Status Badge Counter Notifikasi Kosong: Menampilkan tanda strip ("-") yang clean pada LCD pill notifikasi saat jumlah riwayat notifikasi 0 (menggantikan teks "Aman" / "Idle" yang membingungkan).
- Perbaikan Tombol Tutup Modal Notifikasi (Mojibake Fix): Mengganti karakter simbol rusak dengan ikon native Lucide <X /> yang tajam dan presisi.
- Guard Universal Notifikasi Cold-Start: Mencegah spam notifikasi kemunculan milestone syncthing lama (25%, 50%, 90%, 100%) dan handshake koneksi awal secara retroaktif saat aplikasi baru dinyalakan/booting.
- Persistensi Riwayat Notifikasi (localStorage): Menyimpan riwayat notifikasi di local storage (myserver_notice_history) sehingga aksi "Bersihkan" menghapus tuntas riwayat secara permanen dan mereset counter ke "-".
- Kerapian Header Menu Apps: Menghapus badge pill jumlah kontainer (20) di sebelah teks "LAYANAN & KONTAINER" pada AppsView.tsx sehingga judul tidak lagi mengalami text-truncation ("LAYANAN & KONTA...").
- Desinkronisasi Seed Organik Kartu CRT: Menambahkan variabel seed CSS slot dinamis pada 4 kartu utama (Backup, File Manager, Apps, Options) untuk mendesinkronisasi frekuensi AC hum line, tube warmth flicker, dan glitch jitter, menghasilkan visual retro yang natural tanpa merubah bentuk, padding, maupun dimensi kartu (122x110px).
- Sinkronisasi Versi Atomik v4.0.12: Memperbarui seluruh konstanta versi aplikasi (version.ts, core service, biner PE metadata, Inno Setup, dan Tauri manifest).

## [v4.0.11 - Beta] - 2026-11-06

- Penyelarasan Skeleton Loading Footer Card Home View: Merekonstruksi kartu status server bagian bawah pada kondisi cold-start loading agar selaras 100% dengan skeleton card lainnya (menggunakan container `border border-line bg-surface`, bayangan `shadow-card`, dan placeholder `bg-surface-sunken animate-pulse`). Mengeliminasi background putih/krem `#F6F6F6` yang bertabrakan dengan dark mode, serta menghapus elemen statis (LCD teks 'Offline' dan tombol notifikasi aktif) selama fase loading.

## [v4.0.10 - Beta] - 2026-11-06

- Rekonstruksi Tombol Daya & Footer Subsistem Daya (Figma 1:1): Mengganti tombol Reboot dan Shutdown dengan pill ramping h-[26px] px-2 text-[10.5px] anti-overflow (mengeliminasi teks terpotong pada Bahasa Indonesia), serta menstandarisasi Footer Subsistem Daya dengan TrayChip resmi Figma dan showNoticePill={false} (pb-[10px] mt-[9.19px]) mengadopsi kerapian menu Apps (Gambar 2).
- Penyelarasan Skala Card WoL & Checklist Mengadopsi v3.12.1 Beta: Mengoptimalkan field input MAC (h-[30px] text-[10.5px]), tombol Deteksi via ARP (h-[22px] px-2 text-[9.5px]), tombol Kirim Magic Packet (h-[30px] text-[11px] font-semibold), dan checklist hardware (size-3.5 icons, text-[11px] labels, text-[9.5px] descriptions) agar pas elegan dalam satu tampilan tanpa scroll berlebih.
- Diferensiasi Warna Telemetri Layar Monitoring NET (Gambar 5): Menambahkan palet warna Biru Elektrik (#38BDF8) pada LED dot matrix 6x3 dan font readout Doto saat Speed Up (Upload) aktif atau dominan, membedakannya secara tegas dan instan dari Speed Down (Download) yang berwarna Hijau Retro (#7BC504), dengan tetap mempertahankan 100% dimensi casing metalik dan estetika skeuomorfik.

## [v4.0.6 - Beta] - 2026-11-05

- Restorasi Menyeluruh Animasi CRT Suite (1:1 v4.0.0 Standard): Memulihkan seluruh efek elektronik CRT retro pada 4 kartu utama (Backup, File Manager, Apps, Options) mencakup Fine Scanlines Mesh, 60Hz Ground AC Hum Bar, Tube Warmth Flicker, dan V-Sync Tracking Line Flash.
- Eliminasi Screen Tearing File Manager Card: Memperbaiki nesting DOM pada FILES_SVG dengan memindahkan background monitor hitam (#1B1B1B) ke luar grup .crt-glitch-content, mengeliminasi robeknya layar saat di-hover sehingga hanya piksel matriks hijau yang bergetar secara presisi.
- Rekonstruksi V-Sync Tracking Band Flash: Mengembalikan elemen .crt-tracking-band ke spesifikasi asli (garis fosfor hijau #86efac 3px dengan opacity awal 0), memulihkan animasi kilatan tracking horizontal saat kartu di-hover.
- Isolasi Namespace Defs SVG (Zero ID Collision): Mengalokasikan ID defs unik per kartu (crt-scanlines-backup/files/apps/options, crt-vignette, crt-hum-grad) untuk mencegah tabrakan ID pada DOM HTML dan memastikan koordinat gradien akurat 100%.
- Transform-Box Fill-Box & Elevasi Natural: Menambahkan transform-box: fill-box pada kelompok glitch SVG dan mengembalikan bayangan skeuomorfik natural v4.0.0 (drop-shadow 10px 20px rgba(0,0,0,0.40)) saat hover.
- Sinkronisasi Versi Atomik v4.0.6: Memperbarui seluruh konstanta versi aplikasi (version.ts, core service, biner PE metadata, Inno Setup, dan Tauri manifest).

## [v3.12.0 - Beta] - 2026-11-01

- GitHub Releases API Update Checker: Menghubungkan pemeriksaan versi otomatis aplikasi ke repositori resmi GitHub (Gibranibang/My-Server-beta) secara real-time dengan semantic versioning comparison.
- Perbaikan Ekstraksi & Eksekusi Update ZIP: Menyempurnakan apply_zip_update() untuk memprioritaskan biner utama MyServer-Beta.exe, mengeliminasi konflik penguncian syncthing.exe, dan memproteksi konfigurasi pengguna (Pasal 2).
- Auto-Close Installer Inno Setup: Mengintegrasikan skrip Pascal KillRunningProcesses untuk menutup seluruh proses latar belakang (MyServer-Beta.exe, myserver-core.exe, syncthing.exe) saat installer dijalankan, menghapus tuntas error file lock 'DeleteFile failed'.
- Overhaul Sub-Menu Options (Accordion Style): Merestrukturisasi antarmuka Options menjadi 4 seksi akordeon interaktif (Sistem & Startup, Bahasa & Keamanan, Integrasi Storage & Jaringan, Diagnostik & Log), serta mengeliminasi toggle obsolete.
- Hero Header & Ikon Resmi MyServer: Memperbesar dan menengahkan ikon resmi MyServer (favicon.png 64px) di bagian paling atas sub-menu Options, diikuti identitas versi dan tombol pembaruan.
- Pengembalian Fitur Copy Log & Save Log: Menghadirkan kembali tombol Salin Log ke Clipboard sistem dengan notifikasi instan serta dialog penyimpanan berkas SaveFileDialog native Windows untuk diagnostik mandiri.

## [v3.11.5 - Beta] - 2026-11-01

- Aktivasi Event Click Chip Open Explorer: Mengintegrasikan prop onClick langsung pada komponen Chip 'Open Explorer', mengaktifkan rendering tag button interaktif dengan efek hover dan transisi tekan.
- Dukungan onClick pada Komponen Card (ui.tsx): Memperluas komponen Card untuk menerima prop onClick dan meneruskannya ke kontainer div DOM utama.
- Visual Toast Feedback: Menambahkan notifikasi visual instan 'Opening Windows File Explorer to SMB disk...' saat partisi drive dipilih.
- Dual-Engine Explorer Launcher: Menambahkan mekanisme fallback subprocess Popen(explorer.exe) pada smb_mount_manager jika os.startfile terhambat oleh shell desktop.

## [v3.11.4 - Beta] - 2026-11-01

- Eliminasi Total Kompresi UPX (upx=False): Rekonstruksi berkas spesifikasi kompilasi PyInstaller untuk mematikan kompresi UPX packer, mengeliminasi false positive alarm heuristik Windows Defender (Trojan:Win32/Bearfoos.A!ml).
- Sematkan Metadata Windows PE & Manifest Asli: Mengintegrasikan core_version_info.txt (Project Algitha - MyServer Core Service v3.11.4.0) dan app.manifest ke dalam biner PE resmi.
- Penandatanganan Digital Authenticode Menyeluruh: Menandatangani secara digital seluruh biner executable internal (myserver-core.exe dan MyServer-Beta.exe) dengan sertifikat Algitha Project Desktop sebelum dipaketkan.
- Kemandirian Penuh (Self-Contained Standalone): Menjamin aplikasi 100% mandiri tanpa ketergantungan pada runtime Python eksternal di komputer pengguna/klien.

## [v3.11.3 - Beta] - 2026-11-01

- Backup Sync Throughput 3-Row LED Dot Meter: Menggantikan solid gradient progress bar pada sub-menu Backup & Sync dengan dot matrix SVG 42 kolom x 3 baris (126 LED dots) dengan radius 2.1px dan pitch 6x6px yang identik dengan monitoring dock dan storage meter.
- Dynamic Directional Glow & Tone Mapping: Warna LED dots menyesuaikan arah transfer secara presisi (fill-success/hijau untuk download, fill-info/biru untuk upload, dan fill-line/abu-abu netral saat idle).
- Zero Cumulative Layout Shift (CLS = 0): Kontainer dock throughput dipertahankan tetap rendered secara persisten saat idle, mengeliminasi layout jump 18px saat sinkronisasi dimulai atau selesai.

## [v3.11.2 - Beta] - 2026-11-01

- Storage Usage Server-Rack LED Dot Meter: Menggantikan bar solid konvensional pada sub-menu Storage & Files dengan 25 titik vektor SVG berkoordinat matematis (viewBox 250x8), di mana 1 titik merepresentasikan 4% kapasitas disk secara simetris.
- Dynamic Tone Mapping: Pemetaan warna titik dinamis berdasarkan ambang batas kapasitas (<70% hijau ramah, 70%-85% oranye peringatan, >85% merah kritis, serta abu-abu saat offline/unmounted).
- 3-Tier Auto-Layout Architecture: Merestrukturisasi kartu drive menjadi 3 tingkat terisolasi: Tier 1 (Header: Ikon, Drive Letter, Truncated Drive Name, dan Protected Action Chip), Tier 2 (LED Dot Meter), dan Tier 3 (Footer: Rincian Kapasitas Bebas/Total dan Persentase Penggunaan).
- Zero Text Overflow Guard: Proteksi auto-layout flexbox dengan isolasi shrink-0 pada tombol Open Explorer dan Drive Letter, serta truncate elipsis pada nama partisi panjang, mencegah teks menabrak atau meluap dari batas kartu.
- Vertical Balance & UI Equilibrium: Menyelaraskan jarak vertikal elemen dan memberikan feedback visual kapasitas instan (Mono percentage) bagi pengalaman pengguna yang optimal.

## [v3.11.1 - Beta] - 2026-11-01

- Vectorized Zero-Drift Telemetry Dot Matrix: Mengganti 18 elemen <span> CSS Grid dengan satu elemen SVG vektor murni berkoordinat matematis (viewBox 36x18). Mengunci aspek rasio 1:1 circular LED matrix dan mengeliminasi distorsi pil lonjong pada Windows Display Scaling (125%-175%).
- Multi-DPI Subpixel Precision: Mengeliminasi celah belang antar-kolom akibat pembulatan subpixel snapping DirectWrite/Blink pada monitor laptop resolusi tinggi.
- Skeleton Meter Harmonization: Menyelaraskan status loading telemetri ke geometri SVG yang sama persis, menghasilkan Zero Layout Shift (CLS = 0) saat transisi data masuk.
- Docker App Credential Boundary Guard: Mencegah injeksi otomatis username dan password root ZimaOS ke form login aplikasi pihak ketiga (Nextcloud, qBittorrent, Transmission, Jellyfin, Portainer, dll.).
- Triple-Layer Security Guard: Validasi ketat pada Layer 1 (Python Origin & Port Check), Layer 2 (JavaScript DOM CasaOS Signature Guard), dan Layer 3 (API Intent) memastikan kredensial OS HANYA diinput ke halaman resmi ZimaOS Dashboard.
- Zero Credential Leakage: Menjamin keamanan kredensial akun induk dan mencegah pemblokiran akun akibat salah password berulang pada aplikasi Docker.

## [v3.11.0 - Beta] - 2026-10-30

- Smart Multi-Server Backup Target Selector: Pengguna kini dapat memilih server target (Primary-Server / Secondary-Server) secara langsung di modal Tambah Jalur Backup Baru tanpa perlu beralih server global atau mengganggu koneksi SMB aktif.
- Independent Task Routing: Pembuatan task backup langsung memetakan kredensial, Device ID, dan rute efektif server tujuan terpilih secara terisolasi.
- Smart Identity Inheritance Architecture: MyServer secara cerdas mewarisi dan mengamankan sertifikat digital (cert.pem & key.pem) dari instalasi lama ke direktori internal MyServer, menjamin 0% re-pairing dan mencegah laptop dibaca sebagai device baru.
- Zero-Bias Native Protocol Verification: Terbukti secara empiris melalui pengujian koneksi TLSv1.3 langsung bahwa kode Python MyServer dapat berkomunikasi dengan Syncthing di sisi server (BEP Magic 0x2EA7D90B & Protobuf Hello) saat Syncthing laptop dimatikan.
- Target Server Visual Badging: Setiap kartu jalur backup pada daftar task kini menampilkan label badge server tujuan (🎯 Primary-Server / 🎯 Secondary-Server) dengan visual penanda server aktif.
- Single-Command Multi-File Version Synchronizer: Utilitas terpusat sync_version.py untuk sinkronisasi versi atomik lintas seluruh ekosistem berkas MyServer.

## [v3.10.21 - Beta] - 2026-10-29

- Server-Side Network Telemetry: Monitor NET di dock kini menampilkan kecepatan upload & download riil server ZimaOS dari endpoint sys_net (bukan adapter laptop).
- Dedicated Syncthing Speed: Monitor kecepatan sinkronisasi backup murni membaca throughput Syncthing tanpa pernah bocor ke kecepatan internet laptop.
- Global Loading Transition Overlay: Transisi visual loading halus saat pergantian rute, server, atau akun dengan auto-refresh in-place tanpa mental ke beranda.
- Eliminasi Total False Claim Online (Manual LAN): Isolasi ketat kandidat koneksi saat rute manual LAN dipilih di luar jaringan lokal.
- Hover DISK Akun Aktif: Menampilkan jumlah disk dan kapasitas total partisi SMB yang dapat diakses oleh profil pengguna aktif.
- Pencegahan Crash Submenu Backup: Memperbaiki shadowing fungsi translasi pada daftar tugas sehingga bebas dari TypeError.
- Harmonisasi Tipografi & CSS Inheritance: Seluruh modal baru, input, dan form controls kini konsisten mewarisi Plus Jakarta Sans dan JetBrains Mono.
- Pembersihan Total Hardcoded Power Control: Standardisasi seluruh checklist WoL, badge status kesiapan, dan konfirmasi daya ke i18n.

## [v3.10.20 - Beta] - 2026-10-29

- Redesain Pill Footer HomeView: Tampilan nama rute ringkas (LAN, Remote, WAN) dengan ikon spesifik (LAN/Ethernet, Remote Wifi, WAN Globe) bebas distraksi.
- Quick Route Switcher Pop-up: Modal ganti cepat rute dengan status aktif, latensi ms, opsi otomatis failover, dan masked URL/IP dengan tombol toggle unmask.
- Harmonisasi Dialog WinForms ke React: Penggantian seluruh popup skrip PowerShell Windows Forms klasik ke Modal React mengambang terpadu di dalam antarmuka companion.
- Hover Telemetri Mendalam: Pengukuran suhu CPU (°C), konsumsi daya (Watt), pembagian RAM GB/GB riil, serta jumlah dan kapasitas partisi disk.
- Label DISK Anti-Patah Baris: Penyelarasan label MEM menjadi DISK dengan whitespace-nowrap.
- Pembersihan Dwibahasa Penuh: 100% bebas hardcode pada seluruh kartu (kartu Opsi), chip, notifikasi, dan form.

## [v3.10.19 - Beta] - 2026-10-29

- Strict Origin Validation: Mengeliminasi false online claim akibat CDN/Cloudflare (error 520-530 dan tunnel disconnect langsung dinyatakan Offline).
- Eliminasi Latensi Palsu: Menghilangkan hardcode pingMs 2ms dan menyajikan latensi pengukuran empiris nyata.
- Dual-Route Dynamic SMB Storage: Penyelarasan rute mounting disk secara alami (LAN -> SMB LAN, ZeroTier -> SMB ZeroTier) dengan fallback cerdas tanpa freeze.
- Pembersihan Hardcode SMB: Menghapus aturan kaku lama yang memaksakan rute domain wajib dialihkan ke ZeroTier.
- Transparansi Status ZeroTier: Membedakan status layanan klien laptop dengan status konektivitas peer server fisik.

## [v3.10.18 - Beta] - 2026-10-29

- Integrasi Penuh Rute Dinamis ZeroTier (Tier 3): Menyintesis zerotier_virtual_ip ke evaluasi Auto Failover dan antarmuka pilihan rute.
- Probing Jaringan Hybrid Adaptif: Harmonisasi deteksi online dengan TCP socket cepat dan HTTP probe toleran Cloudflare/Reverse Proxy.
- Eliminasi Standar Ganda Status Online: Menghilangkan inkonsistensi status online antara rute manual vs rute otomatis.
- Smart Offline Fallback (Anti-Banting ke LAN): Mencegah sistem terkunci ke IP LAN 192.168.x.x saat pengguna berada di luar jaringan rumah.
- Timeout Adaptif Jaringan WAN: Menaikkan toleransi latensi probe domain hingga 4.5 detik pada jaringan remote/seluler.

## [v3.10.17 - Beta] - 2026-10-28

- Penuntasan total translasi dwibahasa di seluruh antarmuka (Companion, Home, Files, Backup, Apps, Power, Server).
- Header dinamis di seluruh sub-view melalui getViewHeader() menghilangkan string bahasa Indonesia statis.
- Eliminasi total teks bahasa Indonesia pada hover tooltip kartu menu utama di HomeView.
- Lokalisasi penuh tombol aksi, status drive, tile P2P, form drawer, checklist BIOS, dan modal konfirmasi.
- Penguatan rantai Graceful Fallback Chain 4-lapis pada kamus i18n untuk stabilitas rendering mutlak.

## [v3.10.16 - Beta] - 2026-10-28 07:15

- Penuntasan Bahasa Inggris Menyeluruh (English Default & ID): Mengembangkan kamus i18n untuk seluruh elemen antarmuka, judul menu, hover tooltip, metrik trafik, dan dialog dengan prinsip Graceful Fallback Chain.
- Status DPAPI 100% Dinamis: Mengintegrasikan fungsi probe runtime nyata pada Windows CryptProtectData in-memory sehingga indikator status DPAPI mencerminkan kondisi riil sistem operasi Windows.
- Eliminasi Total 71 Temuan Hardcode: Menghapus asumsi akun kaku ('Admin'), fallback MAC palsu ('AA:BB:CC:DD:EE:FF'), huruf drive dan partisi statis ('Z' dan 'DATA'), serta menetralkan contoh IP dan Network ID pada komentar/dialog.

## [v3.10.15 - Beta] - 2026-10-28 06:15

- Fungsi Ganti Bahasa Dwibahasa di Options: Menambahkan opsi preferensi bahasa antarmuka (English Default & Bahasa Indonesia) baik melalui segmented button pada kartu Options maupun toggle instan pada chip status footer.
- Fitur Pembaruan Aplikasi Melalui ZIP: Mengintegrasikan fitur pembaruan mandiri offline dari berkas arsip ZIP dengan validasi integritas biner, isolasi karantina temp, dan skrip updater batch independen yang aman.
- Sinkronisasi Versi Dinamis Terpusat: Menghilangkan seluruh nilai versi hardcoded di komponen antarmuka, menyelaraskan seluruh tampilan Mini Tray dan Options agar selalu sinkron secara dinamis 100% mengikuti metadata versi aplikasi.

## [v3.10.14 - Beta] - 2026-10-28 05:30

- Opsi Preferensi Klik File Manager di Pengaturan: Menambahkan kartu pengaturan interaktif pada Options untuk memilih target klik kartu File Manager di beranda (File Explorer Windows vs ZimaOS File Manager).
- Tombol Sub-Menu Penyimpanan Dinamis & Adaptif: Tombol peluncur pada menu Penyimpanan & Berkas otomatis menyajikan alternatif aplikasi yang belum dipilih sebagai aksi default tanpa teks terpotong.
- Minimalisir Tombol Titik Tiga pada Kartu Beranda: Mengganti tombol sub-menu teks pada kartu File Manager dengan ikon titik 3 (MoreVertical) yang elegan dan ringkas tanpa menimpa teks judul.
- Pembersihan UI Kartu Akun: Menghapus badge verifikasi akun yang redundan agar kartu profil akun lapang dan teks deskripsi hak akses dapat dibaca secara leluasa tanpa terhimpit.

## [v3.10.13 - Beta] - 2026-10-27 22:30

- URL Web App Dinamis via Remote IP: Kontainer aplikasi ZimaOS di menu Apps otomatis diarahkan ke Remote IP (ZeroTier) saat server diakses melalui rute Domain publik, menembus batasan port-forwarding router secara native tanpa hardcode.
- Rekayasa Alur File Manager: Tombol File Manager di menu utama Mini Tray kini langsung membuka Windows File Explorer ke disk SMB terpasang untuk akses cepat berkas.
- Tombol Menu File Manager Baru: Menambahkan tombol navigasi [Menu →] di kartu File Manager pada menu utama untuk membuka antarmuka lengkap manajemen disk & storage.
- Opsi Ganda Peluncur Berkas: Menyediakan tombol terpisah di menu File Manager untuk membuka File Explorer (Windows SMB) dan ZimaOS File Manager (Web Files), serta opsi preferensi aksi klik cepat.
- Deskripsi Hak Akses Dinamis (Nol Hardcode): Menggantikan teks statis dengan deskripsi peran real dari API resmi ZimaOS (/v1/users/current), membedakan izin Administrator vs Pengguna Standar secara presisi.
- Opsi Switch Auto Buka Mini Tray: Pengguna dapat memilih apakah jendela mini tray otomatis terbuka di layar saat startup Windows atau tetap berjalan senyap di system tray.

## [v3.10.12 - Beta] - 2026-10-27 00:15

- Penyegaran Real-Time File Manager: Menu Penyimpanan & Berkas kini memicu penyegaran drive seketika saat dibuka (on-mount) dan polling berkala (3 detik) saat aktif, mengeliminasi delay pembaruan data partisi storage.
- Sinkronisasi Cache & Switch Server Instan: Cache memori drive SMB langsung diinvalidasi saat peralihan server atau profil akun, mencegah tampilan disk server lama tertinggal di UI.
- Filter Kepemilikan Network Drive Dinamis: Pemindaian drive Windows memfilter kepemilikan host UNC secara dinamis berbasis identitas server aktif (koneksi, domain, IP virtual ZeroTier), mengisolasi disk antar-server secara presisi tanpa hardcode.
- Dynamic Host Footer File Manager: Menampilkan hostname/IP rute aktif server secara dinamis pada footer kartu penyimpanan, menggantikan nilai statis \\127.0.0.1.
- Batas Waktu Autentikasi Adaptif (Admin Telemetri Jarak Jauh): Mengoptimalkan batas waktu autentikasi ZimaOS secara dinamis (10.0 detik untuk rute Domain/WAN publik, 5.0 detik untuk LAN privat), mengatasi masalah telemetri 0% pada akun Admin root di koneksi internet/WAN bertopologi latensi tinggi.
- Penyempurnaan Penanganan Array Kosong Drive: Memperbaiki logika sinkronisasi UI saat transisi unmount agar drive yang dilepas langsung bersih dari layar secara akurat.

## [v3.10.11 - Beta] - 2026-10-26 23:15

- Auto-Discovery & Sinkronisasi ZeroTier Virtual IP per Server: Setiap server kini secara mandiri dan dinamis menemukan IP virtual ZeroTier masing-masing dari REST API ZimaOS (/v2/zimaos/zt/info) tanpa intervensi manual.
- Mounting Otomatis Disk SMB Server Ber-Rute Domain: Saat beralih ke server di luar jaringan LAN (rute domain/WAN publik), pipeline SMB secara cerdas mengalihkan resolusi ke ZeroTier Virtual IP server tersebut dengan verifikasi respons port 445 dan fallback aman.
- Pemilihan Jaringan ZeroTier Akurat di UI: Kartu status ZeroTier pada pengaturan server menampilkan status dan detail jaringan yang secara presisi cocok dengan Remote ID server aktif, bukan elemen acak dari daemon lokal.
- Resolusi Subnet ZeroTier Dinamis (Zero Hardcoded): Menggantikan seluruh filter subnet statis dengan pemindaian rute terkelola adapter ZeroTier aktif langsung dari daemon sistem.
- Validasi Partisi Network Drive Terintegrasi: Menyertakan ZeroTier Virtual IP server aktif ke dalam identitas server resmi agar drive SMB yang terpasang via IP ZeroTier langsung tampil di daftar Disk UI.

## [v3.10.10 - Beta] - 2026-10-26 22:00

- Perbaikan Total Auto-Run Windows Boot: Menghubungkan autorun registry (HKCU\Software\Microsoft\Windows\CurrentVersion\Run\MyServerCompanion) tepat ke biner GUI utama (MyServer-Beta.exe) bukan backend headless, dilengkapi Startup Registry Self-Healing dan Orphan Boot Guard.
- Pemulihan & Penguatan Auto-Mount SMB Pasca-Boot: Mengaktifkan inisialisasi is_online yang akurat dan pemicu startup_auto dengan mekanisme retry adaptif saat jaringan Wi-Fi/LAN/ZeroTier siap, serta mode non-destruktif yang mempertahankan drive yang sudah sehat.
- Perbaikan Status Multi-Server (Anti-Offline Palsu): Memperbaiki isolasi cache rute berdasarkan server_id dan active_conn, memisahkan status Online keterjangkauan jaringan dari autentikasi API telemetri, serta toleransi 3 siklus kegagalan berturut-turut.
- Akselerasi Ekstrem Mounting SMB: Mengeliminasi pemindaian berulang dan pemblokiran WNet/net.exe pada domain publik WAN/Cloudflare di purge_smb_sessions, membatasi reverse DNS hanya untuk IPv4 privat (0.3s), dan memanfaatkan kembali token autentikasi aktif.
- Pembersihan Kode Debug Trace Shell: Menghapus seluruh penulisan jejak debug hardcoded (setup_trace.log) di engine Rust Tauri shell untuk performa startup yang bersih dan patuh standar.

## [v3.10.9 - Beta] - 2026-10-26 00:45

- Overhaul SMB Engine Mengadopsi Arsitektur Zima Client v2.3.5: Registrasi otomatis kredensial ke Windows Credential Vault (cmdkey.exe), penghapusan passwordless net.exe fallback yang memicu hang 2-4 menit, pembersihan drive Red-X (ERROR_CONNECTION_UNAVAIL / 1201), auto-recovery Error 1219, dan notifikasi instan SHChangeNotify ke File Explorer.
- Eliminasi SMB Polling Overhead: Menggunakan kapasitas partisi langsung dari REST API /v2/local_storage/mount tanpa membanjiri network drive SMB dengan GetDiskFreeSpaceExW setiap 2 detik.
- Tata Letak Kartu Jalur Backup (BackupView): Memindahkan badge target server ke sisi kiri barisan ikon aksi bawah sehingga judul jalur backup tampil utuh dan proporsional.
- Reset Otomatis ke Menu Awal (HomeView): Menutup Mini Tray (tombol X atau klik ikon tray) dan membukanya kembali selalu mengembalikan tampilan ke menu awal.
- Pemulihan Auto-Login Dashboard WebView: Mengaktifkan kembali isolasi sesi WebView2 per-profil (WEBVIEW2_USER_DATA_FOLDER & storage_path) serta injeksi token JWT & auto-fill kredensial akun aktif.
- Persistensi Permanen MAC Address Wake-on-LAN (WoL): Menyimpan dan memuat MAC address langsung dari config.json tanpa tereset ke nilai default.
- Latar Putih Menyatu dengan Sudut Melengkung Seragam (rounded-2xl): Menyatukan latar belakang antara kartu monitoring dan kartu utama dengan corner radius yang konsisten di keempat sudut.

## [v3.10.2 - Beta] - 2026-10-24 22:35

- Pemulihan Pipeline Atomik Storage SMB (rebind_storage_pipeline): Unmount bersih seluruh drive remote lama dan pembersihan sesi kredensial Windows (NET USE /DELETE & WNetCancelConnection2W) otomatis saat pergantian akun aktif, mencegah tumpukan drive letter dan error 1219.
- Koreksi Deteksi Share REST API ZimaOS: Memperbaiki penanganan respons list array pada endpoint /v2_1/files/share dan verifikasi hak akses case-insensitive multi-field untuk akun Admin (algitha) dan user standar.
- Pemulihan Live Telemetri Monitoring: Mengintegrasikan ZimaMetricsClient.fetch_metrics() secara real-time pada background thread daemon, memulihkan indikator CPU, RAM, dan HDD yang sebelumnya tertahan di 0%.
- Peluncur Jendela Web App Mandiri (Tauri WebviewWindow): Mengimplementasikan pembuka jendela native 1150x750 untuk aplikasi web ZimaOS dan dashboard dengan akselerasi perangkat keras.
- Peluncur Browser Eksternal Andal: Mengaktifkan aksi 'Browser Luar' via Windows native ShellExecute (os.startfile / start) untuk peramban default sistem.

## [v3.10.1 - Beta] - 2026-10-24 21:55

- Jembatan IPC Native Rust (std::net::TcpStream): Menghapus ketergantungan pada WebView2 loopback fetch() yang diblokir oleh Chromium Private Network Access (PNA), digantikan dengan call_core_api berlatensi < 0.5ms tanpa ketergantungan crate eksternal.
- Penghapusan Total Mock Hardcoded Fallback: Menghilangkan seluruh nilai statis (127.0.0.1, Server Utama, dll.) di api.real.ts, memulihkan resolusi Promise Proxy RPC tanpa hanging pada .then.
- Pemulihan Seluruh Tombol Aksi & Navigasi: Menghubungkan kembali aksi tombol Tambah Server, Ubah, Hapus, Tambah Rute, Hubungkan Remote ID ZeroTier, Pasang Semua Disk Server, dan Deteksi MAC WoL.
- Integrasi Dialog Native Windows Forms: Seluruh dialog konfigurasi (dialogs.ps1) beroperasi dengan TopMost = true di latar depan.
- Optimalisasi Ukuran Biner: Ukuran binary MyServer-Beta.exe menyusut dari 13.6 MB menjadi 9.37 MB berkat eliminasi transitive dependencies Rust.

## [v3.10.0 - Beta] - 2026-10-24 19:30

- Arsitektur Baru Tauri v2 Native Shell: Menggantikan engine WinForms pywebview dengan Tauri v2 berbasis DirectComposition hardware-accelerated per-pixel alpha transparency.
- Transparansi Sempurna 100% (True Wallpaper See-Through): Celah 16px antara Dock dan Flyout sepenuhnya tembus pandang ke wallpaper desktop native Windows tanpa kotak abu-abu gelap #202020 WinForms.
- Tombol Minimalkan Native Windows (_): Meminimalkan jendela secara native ke Windows Taskbar, hadir di Alt+Tab dan Win+Tab tanpa bug ShowWindow(SW_HIDE).
- Zero UI Redesign: Seluruh desain React 19 + Tailwind CSS + Lucide icons tetap 100% identik dengan rancangan Figma.
- Headless Companion Core Service: Backend Python berjalan sebagai companion service headless independen melalui IPC loopback port dinamis.

## [v3.9.4 - Beta] - 2026-10-24 11:45

- Paket 1: Dinamisasi Menu Web Apps & Kontainer ZimaOS (AppsView): Mengeliminasi kontainer fiktif statis (Nextcloud/Plex/Jellyfin/AdGuard mockup) dan menggantikannya 100% dengan daftar dinamis dari config.json.
- Formulir Inline Tambah Web App Baru: Menyediakan form terintegrasi di dalam flyout Mini Tray untuk menyimpan nama aplikasi dan tautan URL/port secara langsung.
- Manajemen Hapus Web App Terintegrasi: Pengguna dapat menghapus tautan web app langsung dari kartu antarmuka Mini Tray dengan sinkronisasi otomatis ke menu klik kanan baki sistem.
- Integrasi Dinamis ZimaOS AppStore: Tombol pintasan AppStore membuka URL AppStore ZimaOS secara murni dinamis berbasis rute server aktif tanpa hardcoded IP.

## [v3.9.2 - Beta] - 2026-10-24 11:15

- Integrasi Penuh Antarmuka Figma Make Companion UI: Seluruh 6 tampilan utama (Home Bento Hub, Files & Storage, Backup & Syncthing, Apps & Containers, Settings, dan Emergency Power Dock) aktif secara penuh.
- Menu Baru Pusat Kendali Jaringan & Akun (ServerView): Menghubungkan klik kartu 'Server Name' ke menu navigasi rute jaringan (LAN Fisik, ZeroTier P2P, Domain/WAN), penukaran profil akun aktif, dan status multi-server.
- Aksi Nyata Seluruh Tombol Mini Tray: Menggantikan seluruh tombol mock toast menjadi aksi native Windows (buka Web Files, luncurkan PeerDrop, buka drive Explorer, buka console server, buka log Notepad, dan persistensi MAC WoL ke config.json).
- Transparansi Kapsul Melayang Murni (Floating Aesthetic): Mengubah kanvas menjadi transparent sehingga dua kapsul melayang dengan bayangan halus tanpa kotak hitam di tepinya.

## [v3.9.1 - Beta] - 2026-10-24 09:45

- Refactoring Arsitektur Mini Tray Popover Sesuai Standar Industri Zima Client: Mengadopsi mekanisme native focus loss (WinForms Deactivate / Electron Blur), mengeliminasi total pemantau klik mouse agresif (GetAsyncKeyState) yang sebelumnya memicu penutupan prematur secara keliru.
- Kalibrasi Posisi Berlabuh Presisi (.NET Screen.PrimaryScreen.WorkingArea): Memastikan jendela Mini Tray selalu berlabuh sempurna di pojok kanan bawah tepat di atas taskbar Windows pada layar 1080p dengan skala DPI 150% tanpa terpotong atau terlempar ke luar batas layar.
- Koreksi Parsing Partisi SMB UNC: Memperbaiki ekstraksi nama partisi share dari jalur UNC jaringan Windows sehingga nama share (seperti Shared_Disk) tampil presisi pada tombol akses cepat.
- Stabilitas Interaksi Pengguna: Menjamin antarmuka Mini Tray tetap tenang dan stabil di layar hingga pengguna secara sadar menutup via tombol X, toggle ikon tray, mengklik opsi aksi, atau beralih fokus ke aplikasi lain.

## [v3.9.0 - Beta] - 2026-10-24 07:15

- Arsitektur Antarmuka Baru: Mini Tray Flyout Popover (Windows 11 Fluent UI): Menghadirkan jendela popover modern frameless di pojok kanan bawah layar saat ikon baki sistem (System Tray) diklik, merefleksikan standar antarmuka kelas dunia seperti Microsoft OneDrive dan Docker Desktop.
- Kalkulasi Posisi Presisi Native Win32 (SPI_GETWORKAREA): Menjamin jendela Mini Tray selalu berlabuh sempurna di pojok kanan bawah tepat di atas taskbar Windows di semua resolusi layar (1080p, 1440p, 4K) dan skala DPI (100%, 125%, 150%).
- Mekanisme Auto-Dismiss Cerdas: Jendela Mini Tray otomatis tertutup secara halus saat pengguna mengklik area luar (desktop atau aplikasi lain).
- Monitoring Kecepatan Jaringan Real-Time (Pure Win32 iphlpapi): Menampilkan indikator kecepatan unduh/unggah langsung (kB/s) dan rute aktif secara dinamis tanpa library pihak ketiga.
- Pintasan Cepat Akses Partisi SMB Utama: Menampilkan nama partisi aktif (misal 'Open Shared_Disk' pada Drive Z:) yang langsung membuka Windows Explorer dengan 1-klik.
- Integrasi Telemetri Perangkat Keras Live: Menampilkan utilisasi CPU, RAM, Disk Storage, dan latensi jaringan real-time dari mesin telemetri ZimaOS.
- Dual-Interaction System Tray: Klik kiri menampilkan Mini Tray Flyout modern; klik kanan tetap mempertahankan menu kontekstual baki sistem.

## [v3.8.8 - Beta] - 2026-10-24 05:30

- Perbaikan Font & Tampilan Simbol Garis Miring ('/') pada Menu Baki Sistem: Mengganti karakter ampersand ('&') yang sebelumnya disembunyikan oleh Windows Win32 Menu Accelerator menjadi garis miring (' / ') eksplisit pada seluruh tombol menu (seperti '📂 Penyimpanan / Berkas', '🌐 Jaringan / Status', '👥 Akun / Server', dan '🌐 Web Apps / Bookmarks').
- Eliminasi Duplikasi Ikon Pengaturan (Gear): Menghilangkan penambahan ikon manual ganda pada item menu baki sistem sehingga ikon '⚙️' hanya tampil tepat satu kali pada '⚙️ Pengaturan / Preferensi'.

## [v3.8.7 - Beta] - 2026-10-24 05:20

- Perbaikan Arsitektur Backup & Restore Data (Atomic Python Restore): Menghapus total ketergantungan pada skrip batch taskkill /T yang sebelumnya membunuh proses restore sendiri. Pemulihan config.json kini dijalankan secara atomik langsung di Python dengan verifikasi integritas JSON, proteksi cadangan otomatis (.bak), dan peluncuran ulang aplikasi secara mandiri (Windows Detached Process).
- Penyaringan Berkas Cadangan Bersih (Zero Browser Bloat): Memperbaiki proses backup data agar menyaring dan mengecualikan direktori cache WebView2 (EBWebView) dan berkas sementara, menjadikan arsip cadangan ringan, bersih, dan 100% kompatibel saat dipulihkan.
- Peningkatan Resolusi Tampilan Native (PerMonitorV2 Manifest & VisualStyles): Menyematkan manifest aplikasi resmi Windows (app.manifest) berstandar industri dengan deklarasi PerMonitorV2 High-DPI, serta mengaktifkan EnableVisualStyles() dan SetProcessDpiAwarenessContext(-4) pada seluruh jendela dialog PowerShell Windows Forms agar seluruh teks, tombol, dan bingkai tampil tajam (razor-sharp).
- Elevasi Pengaturan Aplikasi ke Menu Utama Baki Sistem: Memindahkan submenu 'Pengaturan Aplikasi' (Preferences) langsung ke menu utama baki sistem untuk akses 1-klik yang intuitif dan cepat.
- Indikator Status Server Real-Time pada 'Open MyServer': Menambahkan badge status konektivitas '(ON)' atau '(OFF)' secara dinamis di samping label menu pembuka server berdasarkan status jaringan aktif.

## [v3.8.6 - Beta] - 2026-10-24 02:50

- Dukungan Penuh Partisi SMB dengan Nama Berspasi (Multi-Word Share Parsing): Memperbaiki regex parsing pada net.exe view dan net.exe use sehingga seluruh partisi fisik/share folder server termasuk yang memiliki karakter spasi (seperti 'Toshiba 1TB') terdeteksi utuh secara dinamis dan dipasang sempurna tanpa ada yang terlewat.
- Eliminasi Total Deadlock Pergantian Akun pada Rute yang Sama: Menjadikan pembersihan sesi WebView2 berjalan asinkron (non-blocking) dan memprioritaskan sinkronisasi storage SMB di awal pergantian akun. Proses unmount seluruh drive lama, deep purge sesi Windows, dan remount drive akun baru kini tuntas seketika (<0.6 detik) pada rute dan IP yang sama tanpa galat Windows 1219.
- Proteksi Pelepasan Drive Kuat (Win32 WNetCancelConnection2W Fallback): Memperkuat unmount_smb_share dengan fallback API resmi Windows WNetCancelConnection2W dengan bForce=True jika net.exe use terhalang oleh file handle yang tertahan di Windows Explorer.
- Pembersihan Sesi SMB Dinamis & Presisi: Menggunakan regex UNC presisi pada purge_smb_sessions sehingga share folder berspasi maupun huruf drive terkait terlepas tuntas dari tabel koneksi Windows saat pergantian akun/server/rute.

## [v3.8.5 - Beta] - 2026-10-24 02:30

- Deep Purge Sesi SMB & Unmount-Remount Bersih saat Ganti Akun (Anti-Error 1219): Mengeliminasi total Windows Error 1219 saat berganti akun dengan membersihkan seluruh koneksi network, sesi IPC$ terautentikasi, dan memanggil WNetCancelConnection2W Win32 API sebelum drive akun baru dipasang.
- Prioritas Mutlak Rute Aktif Pengguna pada Resolusi SMB Host: Jika pengguna memilih rute ZimaOS/ZeroTier IP (172.25.0.1) atau LAN IP (192.168.1.11), resolusi SMB wajib mengikat langsung ke host rute pilihan tersebut selama port 445 merespons, meniadakan pembajakan rute oleh IP lain di daftar koneksi.
- Sinkronisasi Real-Time Hak Akses Disk SMB (Multi-User Dynamic Refresh): Menu penyimpanan dan pipeline mounting kini otomatis mendeteksi share disk sesuai hak akses akun aktif (Admin melihat 5 disk, user biasa melihat 2 disk), serta memulihkan daftar disk secara utuh saat berganti kembali ke Admin.
- Peningkatan Resolusi Tampilan Native & Anti-Buram (Per-Monitor V2 DPI Awareness): Mengaktifkan API resmi Windows Per-Monitor V2 DPI Awareness (DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) saat startup, meniadakan efek buram/pecah akibat bitmap stretching Windows pada skala 125%/150%/200%.
- Pencatatan Log Komprehensif Seluruh Aktivitas & Eliminasi Spamming: Mencatat secara eksplisit setiap awal dan akhir aksi perpindahan akun profil ([Profile Switch]), rute ([Route Switch]), dan server ([Server Switch]) ke myserver.log, serta meniadakan log spamming pada hover menu baki sistem.

## [v3.8.4 - Beta] - 2026-10-24 01:45

- Perbaikan Arsitektur SMB Host Resolver (Prioritas Ketat 3-Tier): Mengeliminasi insiden resolusi SMB ke IP Remote ZeroTier saat pengguna berada pada jaringan lokal (LAN). IP LAN fisik (Tier 1) kini selalu diprioritaskan untuk rute lokal, sedangkan ZeroTier IP (Tier 2/3) hanya digunakan jika rute aktif adalah Domain FQDN/WAN atau LAN offline.
- Restorasi Penuh Modul Logging Terpusat (myserver.log): Mengimplementasikan fungsi top-level log_info(), log_error(), log_warning(), log_debug(), dan hook unhandled exception global. Seluruh aktivitas startup, perpindahan rute, pergantian server/profil, dan eksekusi SMB kini tercatat secara real-time dengan auto-flush berkas.
- Pipeline Mounting SMB Standar Industri Zima Client: Mengadopsi mekanisme otentikasi dua tahap Zima Client (pre-auth sesi IPC$ dengan kredensial aktif diikuti pemetaan drive dengan fallback sintaks alternatif).
- Feedback Transparan & Eliminasi Silent Failure: Menambahkan dialog notifikasi kegagalan/keberhasilan (prompt_alert) secara interaktif saat pemasangan disk SMB manual, serta pencatatan galat sistem yang detail ke myserver.log.

## [v3.8.3 - Beta] - 2026-10-24 01:00

- Perbaikan Crash NameError get_cached_zima_client: Mengimplementasikan fungsi get_cached_zima_client() untuk memastikan build_smb_storage_menu dan rebind_storage_pipeline berjalan tanpa unhandled exception.
- Peningkatan Presisi Deteksi Otomatis Remote ID: Handler auto-detect kini dilengkapi TLS 1.2, payload login v1 (name: $usr), ekstraksi multi-struktur token JWT, fallback bertingkat (ZimaOS REST API -> Konfigurasi Zima Client lokal -> Daemon ZeroTier port 9993), serta notifikasi diagnostik galat yang transparan.
- Pembersihan Contoh Placeholder IP (Zero-Hardcoding Strict): Mengeliminasi seluruh pencatatan IP privat riil pengguna pada label formulir wizard dan komentar kode; seluruh placeholder kini menggunakan format netral (10.x.x.x) dengan nilai awal kosong murni.

## [v3.8.0 - Beta] - 2026-10-23 21:00

- Upgrade Enkripsi Kredensial ke Windows DPAPI: Menggantikan enkripsi XOR statis dengan Windows Data Protection API (CryptProtectData/CryptUnprotectData) dengan idempotency check dan unwrapping rekursif.
- Validasi SSL/TLS Adaptif & Strict WAN: Menerapkan validasi sertifikat SSL ketat untuk domain publik (FQDN/HTTPS) dan unverified context adaptif untuk IP privat lokal/ZeroTier, menutup celah MitM.
- Mesin ZeroTier Remote Access Native & Silent Auto-Installer: Integrasi mandiri dengan API lokal ZeroTier One (port 9993), Remote ID dinamis, dan pemasangan otomatis senyap berkas resmi ZeroTier One.msi jika belum terpasang.
- Multi-Disk SMB Dinamis (Zero Hardcoding): Auto-mount seluruh share folder disk server secara runtime via net view, alokasi dinamis huruf drive kosong dari Z: ke D: via Win32 API, dan pembukaan UNC root Explorer.
- Auto-Failover Storage & Event-Driven Rebinding: Otomatis melepaskan dan memasang ulang drive SMB saat perpindahan jalur (LAN/Remote), ganti server, ganti akun (anti-Error 1219), serta pelepasan bersih saat aplikasi ditutup.
- Siklus Hidup Otomatis (Auto-Connect & Auto-Mount on Startup): MyServer langsung menghubungkan Remote ID ZeroTier dan memasang seluruh drive penyimpanan begitu aplikasi dibuka.
- Redesain Menu Baki Sistem (Modern 4-Kategori): Menata 15+ tombol menjadi 4 kategori terstruktur: Dashboard, Penyimpanan & Berkas, Jaringan & Status, dan Manajemen Server & Akun.
- Sistem Logging Diagnostik Terpusat (logger_manager.py): Pencatatan otomatis terpusat di folder aplikasi (<Folder_Aplikasi>/logs/myserver.log) atau folder kustom dengan auto-rotation 5 MB dan tombol buka Notepad instan.
- Windows Smart Setup Installer (MyServer-Setup.exe): Biner instalasi mandiri dengan pemilihan folder bebas, Fresh Install, Repair/Reinstall, dan Seamless Auto-Update tanpa mereset data lama.
- Mitigasi Rate Limiter 'Too Many Requests': Pembatasan skrip injeksi auto-login maksimal 2x dan penghentian interval loop guna mencegah pemblokiran login ZimaOS.

## [v3.7.1 - Stable] - 2026-09-25 05:36

- Mitigasi False Positive Antivirus (SmartScreen & Windows Defender): Menyematkan metadata resmi Windows PE (VS_VERSION_INFO) mencakup Company Name, File Description, Version, dan Copyright ke dalam biner executable untuk menaikkan trust score di mata mesin pemindai antivirus.
- Tanda Tangan Digital Biner Otomatis (Authenticode Code Signing): Mengintegrasikan penandatanganan digital bersertifikat resmi Algitha Project ke dalam proses build untuk MyServer-Stable.exe dan skrip PowerShell dengan timestamping RFC3161.
- Paket Helper Kepercayaan & Unblock MOTW: Menyertakan skrip otomatis '1_Buka_Blokir_Windows_Unblock.bat' untuk menghapus atribut unduhan Mark of the Web (ZoneId=3) dan '2_Pasang_Sertifikat_Kepercayaan_Admin.bat' untuk mendaftarkan sertifikat penerbit terpercaya ke Windows Certificate Store.
- Eliminasi Kompresi UPX (--noupx): Mematikan pengemasan UPX packer secara eksplisit pada PyInstaller dan berkas spesifikasi build guna meniadakan deteksi heuristik AI (!ml) trojan yang keliru.
- Dokumentasi Panduan Keamanan Pengguna: Menyematkan berkas 'PANDUAN_KEAMANAN_WINDOWS.txt' di dalam paket rilis ZIP yang memuat instruksi penanganan mudah bagi perangkat pengguna akhir.

## [v3.7.0 - Stable] - 2026-09-24 22:40

- Promosi Rilis Stabil Generasi Baru v3.7.0: Menggabungkan seluruh penyempurnaan, stabilitas, dan fitur matang dari siklus rilis Beta v3.6.0 hingga v3.6.2 ke kanal produksi utama.
- Sistem Prioritas Rute Otomatis 3-Tier: Hierarki koneksi ketat: 1. LAN Fisik lokal (192.168.x.x, 172.16-31.x.x), 2. Domain Publik (HTTPS/DDNS/FQDN), 3. IP Khusus Fallback (Zima direct 10.0.5.x, ZeroTier 172.25.x.x, Tailscale, VPN virtual adapter). Mengeliminasi rute macet atau salah sasaran saat berada di luar rumah.
- Deteksi Cerdas Adapter Virtual Sistem: Pemetaan antarmuka virtual/VPN (ZeroTier One, Tailscale, TAP/TUN, Docker) serta indikator visual ([LAN], [Domain], [Khusus/Zima]) pada submenu Baki Sistem (System Tray).
- Seamless Dashboard Refresh saat Pergantian Server atau Akun ZimaOS: Berpindah server atau profil akun langsung memuat antarmuka baru secara instan pada jendela aktif tanpa perlu menutup window atau me-restart aplikasi.
- Opsi Fleksibel Startup Window: Pengaturan open_dashboard_on_launch (default: false / senyap di tray) dengan menu toggle pada preferensi, meminimalkan gangguan visual saat booting Windows.
- Fitur Terintegrasi Wake on LAN (WoL): Pengiriman UDP Magic Packet terverifikasi (burst 3 paket), pencarian MAC address otomatis via ARP Windows, dan dialog panduan prasyarat hardware.
- Manajemen Perangkat Syncthing Dinamis & Pop-up Pairing Real-Time: Pengelolaan koneksi perangkat P2P, dialog konfirmasi interaktif izin/tolak perangkat masuk secara live, dan penyalinan Device ID instan.
- Multi-Server Dynamic Credentials: Kredensial mandiri per-server (case-insensitive & fallback), timeout autentikasi 12.0s, dan toleransi enkripsi JWT token ECDSA ES256 ZimaOS.
- Identitas Visual Kanal Stable: Penandaan antarmuka dan tray icon resmi Hijau (#059669) untuk rilis produksi teruji.

## [v3.6.2 - Beta] - 2026-09-24 22:30

- Klasifikasi Subnet ZeroTier & Virtual Adapter (172.25.x.x): Menyelesaikan kendala IP ZimaOS/ZeroTier (misal subnet 172.25.x.x) yang sebelumnya keliru diklasifikasikan sebagai IP LAN Kelas B (172.16-31.x.x). Kini 172.25.x.x, Tailscale (100.64-127.x.x), adapter virtual sistem, serta Zima direct (10.0.5.x) secara tegas dikategorikan sebagai Tier 3 (IP Khusus / Fallback).
- Deteksi Cerdas Adapter Virtual Sistem: Menambahkan pemetaan dinamis interface virtual/VPN sistem (ZeroTier One, Tailscale, TAP/TUN, Docker) sehingga rute Domain Publik (Tier 2) selalu diprioritaskan saat pengguna berada di luar rumah meskipun tunnel ZeroTier dan network drive sedang aktif.
- Label Tier Visual pada Menu Jalur Baki Sistem: Menambahkan indikator visual status jalur ([LAN], [Domain], [Khusus/Zima]) pada submenu Baki Sistem (System Tray) untuk transparansi hierarki rute koneksi server.

## [v3.6.1 - Beta] - 2026-09-24 22:15

- Sistem Prioritas Rute Otomatis 3-Tier: Menetapkan hierarki rute yang ketat: 1. IP Lokal LAN (192.168.x.x, 172.16-31.x.x), 2. Domain Publik (FQDN/DDNS/HTTPS), 3. IP Khusus ZimaOS/Direct Link (10.0.5.x, zimaos.local). Mengatasi rute salah jatuh ke IP Zima saat di luar rumah.
- Peningkatan Resiliensi check_server_ping: Menambahkan SSL Context (CERT_NONE) untuk domain HTTPS publik serta mengenali respon kode HTTP 200, 301, 302, 307, 308, 401 (Auth ZimaOS), 403, 404 sebagai indikator server online.
- Seamless Dashboard Refresh saat Ganti Server: Berpindah server kini langsung memuat URL server baru secara instan pada jendela dashboard aktif tanpa perlu menutup window atau me-restart aplikasi.
- Seamless Dashboard Refresh saat Ganti Akun Zima: Berpindah profil akun kini membersihkan token sesi lama dan langsung login otomatis ke akun baru secara instan tanpa menutup jendela dashboard.
- Opsi Fleksibel Startup Window: Menambahkan konfigurasi open_dashboard_on_launch (default: false / senyap di tray) dengan menu toggle pada Pengaturan & Preferensi, sehingga jendela dashboard hanya muncul saat ditekan atau sesuai preferensi pengguna.

## [v3.6.0 - Beta] - 2026-09-24 18:45

- Promosi Rilis Stabil Beta v3.6.0: Menggabungkan seluruh penyempurnaan dan fitur matang dari siklus pengembangan v3.6.1 hingga v3.6.10 Alpha.
- Multi-Server Dynamic Credentials: Kredensial dinamis per-server & toleran (case-insensitive & fallback), mendukung lingkungan multi-server terisolasi.
- Timeout 12s & Failover Rute Autentikasi ZimaOS: Verifikasi kredensial andal & token ECDSA ES256 tanpa false positive login failed pada jaringan latensi tinggi.
- Fitur Wake on LAN (WoL) Terintegrasi: Pengiriman UDP Magic Packet terverifikasi, pencarian MAC address via ARP, dan panduan hardware interaktif.
- Manajemen Perangkat Syncthing Dinamis & Pop-up Pairing Real-Time: Pengelolaan koneksi perangkat P2P, izin/tolak perangkat masuk secara live, dan penyalinan Device ID.
- Dynamic Routing & Auto-Probing Syncthing Mandiri: Failover otomatis antara LAN IP dan WAN Domain independen dari Web UI ZimaOS.
- Identitas Visual Kanal Beta: Penandaan antarmuka dan tray icon Biru (#2563EB) untuk kanal pengujian stabil pengguna.

## [v3.6.10 - Alpha] - 2026-09-24 10:00

- Manajemen Kredensial Multi-Server Dinamis & Mandiri: Sistem kredensial kini sepenuhnya terisolasi per-server dan per-profil dengan get_server_credentials & save_server_credentials yang toleran (case-insensitive & fallback), menyelesaikan kegagalan login saat berpindah ke Secondary-Server.
- Peningkatan Timeout Autentikasi ZimaOS (12.0s): Memperpanjang batas waktu verifikasi kredensial dan kalkulasi JWT token ECDSA ES256 ZimaOS dari 5.0s menjadi 12.0s, mengeliminasi false positive 'Login Failed' pada server dengan latensi enkripsi ~6.2s.
- Failover Rute Otomatis pada Autentikasi Metrik & Status: Autentikasi ZimaOS kini secara cerdas menguji base_url dan seluruh daftar jalur server_connections (LAN IP maupun Domain WAN) sampai menemukan rute yang dapat dihubungi.
- Dekopling Validasi Kredensial dari URL Webview Aktif: Dialog konfigurasi kredensial kini mengarahkan validasi secara spesifik ke server target, mencegah validasi kredensial server kantor terlempar ke URL server utama.
- Wizard Tambah Server 4-Field Interaktif: Penambahan server baru kini langsung menyertakan input Username dan Password dengan verifikasi koneksi live dan opsi instan beralih ke server baru.
- Submenu Manajemen Kredensial Cepat di Baki Sistem: Menambahkan menu '🔑 Kredensial Server' pada system tray untuk memudahkan konfigurasi akun login setiap server secara mandiri tanpa harus mengganti server aktif terlebih dahulu.

## [v3.6.9 - Alpha] - 2026-09-23 21:55

- Fitur Wake on LAN (WoL) Terintegrasi: Menambahkan kapabilitas menghidupkan server dari kondisi mati/standby melalui pengiriman UDP broadcast Magic Packet (burst 3 paket).
- Dialog Konfigurasi Wake on LAN Interaktif & Edukatif: Dilengkapi panduan lengkap prasyarat hardware (kabel LAN fisik RJ45, aktivasi Wake on LAN di BIOS/UEFI, daya siaga listrik +5VSB, dan jaringan lokal/subnet yang sama).
- Deteksi MAC Address Otomatis via ARP: Tombol pencarian otomatis untuk mendeteksi alamat fisik (MAC Address) kartu jaringan server dari tabel ARP Windows secara instan.
- Tombol Uji Kirim Paket Langsung: Pengguna dapat langsung menguji pengiriman Magic Packet dari dalam dialog konfigurasi dengan pesan konfirmasi status interaktif.
- Aksesibilitas Menu Tray Offline & Online: Menu Wake on LAN tersedia langsung pada menu tray saat server berstatus offline serta di bawah submenu Kontrol Daya Server saat online.

## [v3.6.8 - Alpha] - 2026-09-23 15:35

- Manajemen Perangkat Syncthing Dinamis: Menambahkan fitur penambahan perangkat Syncthing terhubung (Laptop ke Server, Laptop ke Laptop rekan kantor/P2P, dan Mutual Pairing 2-Arah).
- Dialog Pop-up Real-Time Izin/Tolak Koneksi: Sistem secara otonom memantau permintaan perangkat masuk dan menampilkan dialog pop-up konfirmasi interaktif ([✔ Izinkan & Hubungkan] atau [✖ Tolak Permintaan]).
- Tampilan & Penyalinan Device ID Mandiri: Dialog untuk melihat dan menyalin Device ID Laptop dan Server dengan 1-klik ke clipboard untuk kemudahan bertukar ID antar-perangkat.
- Menu Kontrol & Pemutusan Perangkat di System Tray: Memungkinkan jeda, lanjutkan, peninjauan permintaan masuk, serta pemutusan/penghapusan perangkat Syncthing langsung dari baki sistem.

## [v3.6.7 - Alpha] - 2026-09-23 11:45

- Resolusi IP & Domain Syncthing Dinamis & Mandiri: Memisahkan ketergantungan resolusi rute Syncthing dari IP/status Web UI ZimaOS, memungkinkan Syncthing beroperasi pada IP atau domain tersendiri secara otonom.
- Auto-Probing & Dynamic Failover Syncthing: Mendeteksi ketersediaan layanan Syncthing secara langsung melalui endpoint health (/rest/noauth/health dan /rest/system/ping), otomatis beralih antara LAN dan WAN Domain berdasarkan ketersediaan jaringan real-time.
- Mode Pemilihan Rute Fleksibel: Menambahkan opsi pemilihan mode rute (Otomatis/Dinamis, Selalu Gunakan LAN, Selalu Gunakan WAN/Domain) pada dialog konfigurasi.
- Caching Rute Non-Blocking: Mengoptimalkan performa menu baki sistem dan antarmuka dengan cache status rute responsif tanpa lag.

## [v3.6.6 - Alpha] - 2026-09-23 11:15

- Pemindaian Network Drive Dinamis (A: hingga Z:): Memindai seluruh partisi drive remote Windows di setiap perangkat tanpa batas huruf drive.
- Filter Validasi Kepemilikan via API ZimaOS: Memfilter drive jaringan secara ketat menggunakan API ZimaOS (/v2/users/samba/user) untuk memastikan drive tersebut benar milik server ZimaOS dan diizinkan untuk akun pengguna aktif, menolak drive dari aplikasi, server, atau NAS lain.
- Pembacaan Ukuran Disk Akurat Akun Non-Admin: Memastikan telemetri ukuran disk granular (...GB) dan total kapasitas terbaca sempurna pada akun pengguna biasa dengan arsitektur dual-layer (API ZimaOS dan Windows live metrics).
- Resolusi Identitas Multi-Host Server: Mengagregasi hostname, seluruh rute koneksi server, nama NetBIOS resmi ZimaOS, dan IP perangkat untuk validasi koneksi remote UNC yang andal.

## [v3.6.5 - Alpha] - 2026-09-22 21:40

- Perbaikan Monitor Kecepatan Upload & Download (0B): Menyimpan status metrik transfer secara persisten lintas instance SyncthingClient dan background worker, mengatasi bug kecepatan macet di 0 B/s.
- Tampilan Kecepatan Lengkap di Hover Tray: Menampilkan kecepatan transfer aktif pada tooltip hover (upload, download, dan 2-arah) secara real-time.
- Indikator Kecepatan Submenu Server & Laptop: Memastikan submenu sinkronisasi menampilkan kecepatan transfer aktual.
- Fallback Agregasi Koneksi: Menghitung total akumulasi dari seluruh koneksi aktif bila data total daemon kosong.

## [v3.6.4 - Alpha] - 2026-09-22 21:15

- Eliminasi Duplikasi Umbrella /DATA: Menghapus /DATA dari submenu partisi dan total kapasitas saat partisi individual tersedia, mencegah duplikasi kapasitas ganda (dari 5.6 TB kembali normal ke ~3.3 TB).
- Perbaikan Deteksi Disk SATA Internal (Toshiba 1TB): Menghilangkan pembatasan `if not new_map` pada query /v1/sys/hardware agar disk SATA selalu terindeks.
- Parsing Petunjuk Kapasitas Drive: Mendeteksi ukuran drive secara cerdas dari label volume (misal: 'Toshiba 1TB' -> 1 TB).
- Rekonsiliasi Ruang Disk Terpakai: Mengalokasikan selisih sys_used ke disk tanpa data pemakaian sehingga setiap partisi dan total server terukur akurat.

## [v3.6.3 - Alpha] - 2026-09-22 21:00

- Penggantian Dinamis Partisi via Network Drive: Partisi yang terhubung di Network Drive Windows secara otomatis menggantikan partisi yang belum berukuran/belum lengkap dari API ZimaOS.
- Eliminasi Device Kernel Mentah (sdc, sdd, sde): Memblokir kemunculan nama block device mentah Linux dari menu tray partisi.
- Korelasi Device Block & Volume: Memetakan dev source (/dev/sdd, /dev/sdb) ke partisi volume sebenarnya (Disk_Aldhy, Toshiba 1TB) untuk ukuran akurat.
- Multi-Bus Storage Stats Parsing: Mendeteksi sys_sata, sys_pci, sys_nvme, dan sys_usb secara komprehensif dari /v2/local_storage/storage/stats.
- Fallback Query Disk Info: Mengambil info detail kapasitas partisi disk langsung dari /v2/local_storage/disk/info jika partisi berstatus 0 B.

## [v3.6.2 - Alpha] - 2026-09-22 20:30

- Perbaikan Bug Partisi Storage: Eliminasi tuntas mount point sistem (/mnt/overlay, /etc, /tmp, /var) dan layer Docker overlay2.
- Deduplikasi Kanonikal Partisi: Mencegah duplikasi 3x lipat pada partisi fisik dan network drive Windows.
- Normalisasi Kapasitas Drive Fisik: Menampilkan kapasitas riil drive USB/SATA tanpa tertimpa model hardware atau berstatus 0 B (Aktif).
- Validasi Ketat Network Drive: Mencegah pencocokan salah antara host jaringan lokal dan target remote server.

## [v3.6.1 - Alpha] - 2026-09-22 16:45

- Peningkatan Pemantauan Storage Admin: Deteksi instan multi-partisi server (bukan hanya network drive).
- Agregasi Total Storage Akurat: Menghitung akumulasi seluruh partisi server pada label utama baki sistem.
- Sinkronisasi kuota dan kapasitas partisi /DATA langsung dari data sys_disk ZimaOS OpenAPI.
- Optimasi query endpoint storage cepat (/v2/local_storage/storage) tanpa memblokir thread latar belakang.

## [v3.6.0 - Alpha] - 2026-09-21 22:40

- Pemantauan Suhu CPU Server Real-Time (°C) & Peringatan Termal Otomatis.
- Peringatan Kesehatan Server (S.M.A.R.T Disk Failure & Storage Critical Alert).
- Penyempurnaan Bahasa Menu Monitoring Baki Sistem ('Performa & Daya Server').
- Pengecekan & Pemasangan Pembaruan Online GitHub Releases API serta integrasi update ZIP.
- Konfigurasi Repositori GitHub untuk Integrasi Pembaruan Mandiri.
- Restorasi arsitektur runtime Watchdog Worker & Multi-Server Switch yang stabil.

## [v3.5.4 - Alpha] - 2026-09-20 11:35

- Setup Wizard Terpadu 4-Langkah (Server & Rute, Remote Backup, Local Syncthing, Akun).
- Verifikasi kredensial akun langsung ke API ZimaOS pada saat setup akun pertama.
- Penghapusan tombol manual 'Save Auto-Login Credentials' (akun terverifikasi otomatis sejak awal).
- Failover dinamis Windows Network Drive: membaca drive Zima Client / SMB lokal jika API ZimaOS timeout.
- Keamanan Restore Data: Auto-wipe password lama saat restore ZIP untuk mencegah spam login & pesan 'Too Many Requests'.
- Perbaikan monitoring partisi ZimaOS untuk Admin (sys_disk 3.6TB & mount point aktif) dan Non-Admin (filter izin Samba).
- Koreksi HTTP Method kontrol daya server (Reboot & Shutdown) ke method PUT sesuai spesifikasi ZimaOS.
- Penerapan Client Session Reuse untuk mencegah login berulang tiap 5 detik dan mengurangi beban CPU/jaringan.
- Sistem Auto-Changelog terpusat dan Auto-Backup source code ke direktori /bin pada skrip build bat.

## [v3.5.3 - Alpha] - 2026-09-19 20:15

- Dynamic API Role Verification untuk akun Admin sekunder (non-UID 1).
- Perhitungan telemetri RAPL CPU Wattage real-time.
- Stale Cache Fallback untuk mencegah kekosongan data saat server spin-up.

## [v3.5.2 - Alpha] - 2026-09-19 15:32

- Arsitektur Dual-Route Syncthing: Jalur LAN (Port 8384) + WAN Subdomain Publik.
- Auto-Switch cerdas mengikuti status jaringan (LAN lokal vs Domain publik).
- Dialog konfigurasi interaktif Dual-Route di dialogs.ps1.
- Dukungan protokol HTTPS aman untuk subdomain reverse proxy (port 443).

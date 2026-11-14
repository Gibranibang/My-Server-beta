# MyServer Desktop Companion (Beta)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%20x64-0078D6.svg)](https://microsoft.com/windows)
[![Version](https://img.shields.io/badge/Version-3.12.0%20Beta-emerald.svg)](CHANGELOG.md)
[![Architecture](https://img.shields.io/badge/Stack-Tauri%20%7C%20React%20%7C%20Python-orange.svg)](#architecture)

**MyServer Desktop Companion** adalah aplikasi desktop modern Windows yang bertindak sebagai orchestrator dan pemantau server rumah (*home server* / ZimaOS / Linux). Aplikasi ini mengintegrasikan sinkronisasi berkas otomatis berkecepatan tinggi, pemasangan partisi drive penyimpanan jaringan SMB (*Samba*), jaringan mesh virtual ZeroTier, serta telemetri server bergaya matriks LED rak server.

---

## Fitur Utama

* **Server-Rack LED Matrix Telemetry:**
  Indikator throughput real-time dan kapasitas storage berbentuk kisi matriks 3-baris LED vektor SVG berpitch presisi tanpa pergeseran tata letak (*Zero Layout Shift*).
* **Automated Continuous Syncthing Backup:**
  Mesin sinkronisasi dua arah otomatis yang menjaga direktori kerja Anda selalu ter-backup ke server rumah secara instan.
* **Samba SMB Storage Auto-Mounting:**
  Mendeteksi dan memasang partisi disk jaringan (`Drive Z:`, `Drive Y:`) secara otomatis saat Windows boot dengan integrasi tombol pintas ke Windows File Explorer.
* **ZeroTier SDN Mesh Integration:**
  Konektivitas rute multi-jalur (LAN Fisik $\leftrightarrow$ ZeroTier Remote) yang berpindah secara cerdas saat Anda berada di luar jaringan rumah.
* **Organized Accordion Settings & Diagnostics:**
  Sub-menu Options berformat akordeon modern (Sistem & Startup, Bahasa & Keamanan Vault, Integrasi Storage & Jaringan, Diagnostik & Log) lengkap dengan fitur salin log ke clipboard dan dialog penyimpanan log native Windows.
* **Real-time GitHub Releases Update Checker:**
  Pengecekan versi rilis terbaru langsung dari GitHub Releases API dengan perbandingan versi semantik (*semver*).
* **Hardware-Level Security:**
  Penyimpanan kredensial dan token rahasia terlindungi enkripsi perangkat keras Windows DPAPI (*Data Protection API*).

---

## Arsitektur Sistem

```
┌───────────────────────────────────────────────────────────────┐
│                 MyServer Desktop Companion                   │
├───────────────────────────────┬───────────────────────────────┤
│         FRONTEND UI           │        BACKEND SERVICE        │
│ • React 18 + Vite             │ • Headless Daemon Python      │
│ • Tailwind CSS + Lucide Icons │ • Windows DPAPI Vault         │
│ • Tauri Native Windows Shell  │ • SMB Mounter (WNet/Net.exe)  │
│ • Server-Rack SVG Component   │ • Local Syncthing Engine      │
└───────────────────────────────┴───────────────────────────────┘
```

---

## Lisensi & Atribusi Pihak Ketiga

Aplikasi ini dilisensikan di bawah [**MIT License**](LICENSE).

Aplikasi ini memanfaatkan dan berkomunikasi dengan beberapa perangkat lunak pihak ketiga:
* **Syncthing** (© The Syncthing Authors) — Berlisensi di bawah [Mozilla Public License 2.0 (MPL-2.0)](https://www.mozilla.org/en-US/MPL/2.0/).
* **ZeroTier One** (© ZeroTier, Inc.) — Berlisensi di bawah [Business Source License 1.1 (BSL 1.1)](https://www.zerotier.com).
* **Tauri Framework** (© The Tauri Programme in the Commons Conservancy) — Berlisensi di bawah Apache 2.0 / MIT.
* **Lucide Icons** (© Lucide Contributors) — Berlisensi di bawah ISC License.

Rincian lengkap atribusi pihak ketiga dapat dilihat pada berkas [**`THIRD_PARTY_LICENSES.md`**](THIRD_PARTY_LICENSES.md).

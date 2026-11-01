# Script Penandatanganan Digital (Authenticode Code Signing) Otomatis
# Digunakan untuk MyServer Desktop (Stable) agar terverifikasi di Windows
param(
    [string]$TargetExe = "dist\MyServer-Stable\MyServer-Stable.exe",
    [string]$DistDir = "dist\MyServer-Stable",
    [switch]$SkipTimestamp = $true
)

$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "[Code Signing] Menyiapkan Tanda Tangan Digital Authenticode untuk MyServer (Stable)..." -ForegroundColor Cyan
Write-Host "=============================================================================="

$certSubject = "CN=Algitha Project Desktop, O=Algitha Project"
$certFriendlyName = "Algitha Project Desktop Signing Certificate"

# 1. Cari sertifikat yang sudah ada di CurrentUser\My
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue | 
        Where-Object { $_.Subject -like "*CN=Algitha Project Desktop*" } | 
        Select-Object -First 1

if (-not $cert) {
    Write-Host "[*] Membuat sertifikat Code Signing baru untuk Algitha Project..." -ForegroundColor Yellow
    $cert = New-SelfSignedCertificate -Type CodeSigningCert `
        -Subject $certSubject `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears(5) `
        -FriendlyName $certFriendlyName
    Write-Host "[v] Sertifikat berhasil dibuat dengan Thumbprint: $($cert.Thumbprint)" -ForegroundColor Green
} else {
    Write-Host "[v] Menggunakan sertifikat Code Signing yang sudah ada: $($cert.Thumbprint)" -ForegroundColor Green
}

# 2. Ekspor sertifikat publik .cer ke folder distribusi
if (Test-Path $DistDir) {
    $cerPath = Join-Path $DistDir "Algitha_Project_Security_Certificate.cer"
    Write-Host "[*] Mengekspor sertifikat publik ke: $cerPath" -ForegroundColor Yellow
    Export-Certificate -Cert $cert -FilePath $cerPath -Force | Out-Null
    Write-Host "[v] Sertifikat publik berhasil diekspor." -ForegroundColor Green
}

# 3. Tanda tangani executable utama
if (Test-Path $TargetExe) {
    Write-Host "[*] Menandatangani berkas biner: $TargetExe" -ForegroundColor Yellow
    
    $signed = $false
    if (-not $SkipTimestamp -and -not $env:SKIP_TIMESTAMP) {
        $timestampServers = @(
            "http://timestamp.digicert.com",
            "http://timestamp.sectigo.com",
            "http://tsa.starfieldtech.com"
        )
        
        foreach ($ts in $timestampServers) {
            try {
                Write-Host "    Mencoba timestamp server: $ts ..."
                $res = Set-AuthenticodeSignature -FilePath $TargetExe -Certificate $cert -TimestampServer $ts -ErrorAction Stop
                if ($res.Status -eq "Valid") {
                    Write-Host "[v] Tanda tangan digital valid dengan timestamp!" -ForegroundColor Green
                    $signed = $true
                    break
                }
            } catch {
                Write-Host "    Gagal dengan $ts, beralih..." -ForegroundColor DarkGray
            }
        }
    }
    
    if (-not $signed) {
        Write-Host "    Menandatangani lokal Authenticode..." -ForegroundColor Yellow
        $res = Set-AuthenticodeSignature -FilePath $TargetExe -Certificate $cert -ErrorAction SilentlyContinue
    }
    
    $sig = Get-AuthenticodeSignature -FilePath $TargetExe
    $signer = if ($sig.SignerCertificate) { $sig.SignerCertificate.Subject } else { "N/A" }
    $validUntil = if ($sig.SignerCertificate) { $sig.SignerCertificate.NotAfter.ToString('yyyy-MM-dd') } else { "N/A" }
    Write-Host "==============================================================================" -ForegroundColor Cyan
    Write-Host "[HASIL TANDA TANGAN DIGITAL]:" -ForegroundColor Cyan
    Write-Host "  * Berkas    : $TargetExe"
    Write-Host "  * Status    : $($sig.Status)"
    Write-Host "  * Penerbit  : $signer"
    Write-Host "  * Berlaku s/d: $validUntil"
    Write-Host "==============================================================================" -ForegroundColor Cyan
} else {
    Write-Host "[!] Berkas $TargetExe tidak ditemukan untuk ditandatangani." -ForegroundColor Red
}

# 4. Tanda tangani juga dialogs.ps1 jika ada di folder dist
$ps1Files = Get-ChildItem -Path $DistDir -Filter "*.ps1" -Recurse -ErrorAction SilentlyContinue
foreach ($ps1 in $ps1Files) {
    Write-Host "[*] Menandatangani skrip PowerShell: $($ps1.FullName)" -ForegroundColor Yellow
    Set-AuthenticodeSignature -FilePath $ps1.FullName -Certificate $cert -ErrorAction SilentlyContinue | Out-Null
}

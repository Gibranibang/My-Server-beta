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

# SIG # Begin signature block
# MIIF0wYJKoZIhvcNAQcCoIIFxDCCBcACAQExCzAJBgUrDgMCGgUAMGkGCisGAQQB
# gjcCAQSgWzBZMDQGCisGAQQBgjcCAR4wJgIDAQAABBAfzDtgWUsITrck0sYpfvNR
# AgEAAgEAAgEAAgEAAgEAMCEwCQYFKw4DAhoFAAQUtwEBb+wAvlcwNkYnKMR+hyrK
# vl+gggNMMIIDSDCCAjCgAwIBAgIQVGb09oekxrxD1s9OIbn4JjANBgkqhkiG9w0B
# AQsFADA8MRgwFgYDVQQKDA9BbGdpdGhhIFByb2plY3QxIDAeBgNVBAMMF0FsZ2l0
# aGEgUHJvamVjdCBEZXNrdG9wMB4XDTI2MTAyMzEzMjcyNloXDTMxMTAyMzEzMzcy
# NlowPDEYMBYGA1UECgwPQWxnaXRoYSBQcm9qZWN0MSAwHgYDVQQDDBdBbGdpdGhh
# IFByb2plY3QgRGVza3RvcDCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEB
# AMVQAffSVbTv8scTOUdyHwp2PGagTHPTWt4wbI+a7T4LVOKNYWgl0HnHdSeH4vA/
# sWsIfYrPeJjD1KDh0RzHfxxYdysn8UcXUjNYnxuq2zBF9iIYUn/PyBPnePrXeooI
# X8SLcWMOKXnvGEWMNA5NkXHKEjtZCL6eQSKBXP3j5MaLavbSghPcJc5ptBhgnNgW
# Bx2B8YWuHKAFKStKLMyzZUy6qce29RYY9+Eye+rDcmSBZP+edqvozO/E/v2n7cpa
# MCRJ7jwJzefvQ1weBcFg4xFudbn+xULYBkDbf6kfM/t3p0H6KNtS0rE42sjehHeh
# z5kGB0x2Oraqw1lkSK8xv90CAwEAAaNGMEQwDgYDVR0PAQH/BAQDAgeAMBMGA1Ud
# JQQMMAoGCCsGAQUFBwMDMB0GA1UdDgQWBBR3ibhnNyDf4drS3xVzqsIqNZnE2DAN
# BgkqhkiG9w0BAQsFAAOCAQEAb7dNrEuPs7z2TO8VPH1jOgK3yAnQFEd59hy/XZOV
# rEfrsirTz6zghBwkSNLGzaKz8IWQPx9jtNGYgETS/dnkFnaEB9uqf1JNFFFe45G3
# /oD1wSXTtSWyWHTDOeSaQvfpwJ1r0hBVu+Ygb/fbDR6z3f0trt6Tu7dKkdMRC/DP
# /6SIo8DV0p6/hD2m9KGo8ns3/SIpJ44o8yAytKR4VE4PaEcFqesjmFH+8cPYHr8Z
# 9MU8tQ3W6O1u134hf/coNt93nsPkKdbKTGN27DbIAvzorzxyqmvGSBYnjNxJaoeC
# O+wVzL2ydrv2bsnwx48oNROU2tPqbSzvy/gS73KI4bBtUDGCAfEwggHtAgEBMFAw
# PDEYMBYGA1UECgwPQWxnaXRoYSBQcm9qZWN0MSAwHgYDVQQDDBdBbGdpdGhhIFBy
# b2plY3QgRGVza3RvcAIQVGb09oekxrxD1s9OIbn4JjAJBgUrDgMCGgUAoHgwGAYK
# KwYBBAGCNwIBDDEKMAigAoAAoQKAADAZBgkqhkiG9w0BCQMxDAYKKwYBBAGCNwIB
# BDAcBgorBgEEAYI3AgELMQ4wDAYKKwYBBAGCNwIBFTAjBgkqhkiG9w0BCQQxFgQU
# oq7SolJehW1aVwv3a48ofqPsaYIwDQYJKoZIhvcNAQEBBQAEggEAIEQs2T/hWUyP
# mHgvOY0/mQi7MhDdmY7SPYLiQ9+Kt2oV4k3p8noZukmXzYi22IsVNE8QGx/8u8Vo
# 1mpTSZQdmKMwBMMSI1O2MhglaROQrpuzcNXpHrhFPOVtnoZkdLKEpsq+a0HLWw2v
# XkXW8WIsl9bWZ4N86tT8nMorFwXwHf1K7iOxSXV1aL/Pm8c3bZ/dzQzTBXK4QOoS
# GISHCgC4T3/l3dhkc/OQrXzmA8A02nwug3ZQtfcHMjft4CtqV4MC+WOX7PqQKHxi
# l4uLdeGBUIml3g3RI8B77vpPSN+u6nkEnRdH7zaDxW50t5WC3QfCmq36vREdnqec
# MF5lQADxbA==
# SIG # End signature block

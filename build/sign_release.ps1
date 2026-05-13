param(
    [string]$DistDir = "dist\Voice-Comms-DCS",
    [string]$Installer = "build_output\Voice-Comms-DCS-Setup-0.4.0.exe",
    [string]$Manifest = "build_output\release_manifest.json",
    [string]$ModelManifest = "build_output\model_manifest.json",
    [string]$CertificateThumbprint = $env:VCDCS_SIGN_CERT_THUMBPRINT,
    [string]$TimestampServer = "http://timestamp.digicert.com",
    [switch]$SkipSigning,
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"

function Get-SignToolPath {
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $kits = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
        "$env:ProgramFiles\Windows Kits\10\bin"
    )
    foreach ($kit in $kits) {
        if (-not (Test-Path $kit)) { continue }
        $candidate = Get-ChildItem -Path $kit -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "x64" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) { return $candidate.FullName }
    }
    throw "signtool.exe not found. Install Windows SDK or add signtool to PATH."
}

function Sign-File {
    param([string]$Path)
    if ($SkipSigning) {
        Write-Host "Skipping signing: $Path"
        return
    }
    if (-not $CertificateThumbprint) {
        throw "Certificate thumbprint missing. Set VCDCS_SIGN_CERT_THUMBPRINT or pass -CertificateThumbprint."
    }
    $signtool = Get-SignToolPath
    Write-Host "Signing $Path"
    & $signtool sign /fd SHA256 /td SHA256 /tr $TimestampServer /sha1 $CertificateThumbprint $Path
}

function Verify-File {
    param([string]$Path)
    $signtool = Get-SignToolPath
    Write-Host "Verifying $Path"
    & $signtool verify /pa /v $Path
}

$targets = @()
if (Test-Path $DistDir) {
    $targets += Get-ChildItem -Path $DistDir -Recurse -Include *.exe,*.dll | ForEach-Object { $_.FullName }
}
if (Test-Path $Installer) { $targets += (Resolve-Path $Installer).Path }

if (-not $targets) {
    Write-Warning "No EXE/DLL signing targets found. Build first."
}

foreach ($target in $targets) {
    if (-not $VerifyOnly) { Sign-File -Path $target }
    Verify-File -Path $target
}

python -m voice_comms_dcs.release_manifest --output $Manifest
python -m voice_comms_dcs.release_manifest --output $Manifest --verify
python -m voice_comms_dcs.model_manifest --output $ModelManifest
python -m voice_comms_dcs.model_manifest --output $ModelManifest --verify

Write-Host "Release signing/checksum pass complete."

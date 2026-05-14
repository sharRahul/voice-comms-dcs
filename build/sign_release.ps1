param(
    [string]$DistDir = "dist\Voice-Comms-DCS",
    [string]$Installer = "build_output\Voice-Comms-DCS-Setup-0.4.0.exe",
    [string]$Manifest = "build_output\release_manifest.json",
    [string]$ModelManifest = "build_output\model_manifest.json",
    [string]$CertificateThumbprint = $env:VCDCS_SIGN_CERT_THUMBPRINT,
    [string]$TimestampServer = "http://timestamp.digicert.com",
    [string]$ManifestSigningTool = "minisign",
    [string]$ManifestPrivateKey = $env:VCDCS_MANIFEST_MINISIGN_PRIVATE_KEY,
    [string]$ManifestPublicKey = $env:VCDCS_MANIFEST_MINISIGN_PUBLIC_KEY,
    [switch]$SkipSigning,
    [switch]$SkipManifestSigning,
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
        Write-Host "Skipping Authenticode signing: $Path"
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

function Invoke-ManifestSignature {
    param(
        [string]$Path,
        [switch]$Verify
    )

    if ($SkipManifestSigning) {
        Write-Host "Skipping detached manifest signature: $Path"
        return
    }

    if ($ManifestSigningTool -ne "minisign") {
        throw "Unsupported manifest signing tool '$ManifestSigningTool'. Supported value: minisign."
    }

    $tool = Get-Command minisign -ErrorAction SilentlyContinue
    if (-not $tool) {
        throw "minisign not found. Install minisign or pass -SkipManifestSigning for local development."
    }

    if ($Verify) {
        if (-not $ManifestPublicKey) {
            throw "Manifest public key missing. Set VCDCS_MANIFEST_MINISIGN_PUBLIC_KEY or pass -ManifestPublicKey."
        }
        Write-Host "Verifying detached manifest signature: $Path"
        & $tool.Source -Vm $Path -p $ManifestPublicKey
        return
    }

    if (-not $ManifestPrivateKey) {
        throw "Manifest private key missing. Set VCDCS_MANIFEST_MINISIGN_PRIVATE_KEY or pass -ManifestPrivateKey."
    }
    Write-Host "Signing manifest: $Path"
    & $tool.Source -Sm $Path -s $ManifestPrivateKey
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

if ($VerifyOnly) {
    Invoke-ManifestSignature -Path $Manifest -Verify
    Invoke-ManifestSignature -Path $ModelManifest -Verify
} else {
    Invoke-ManifestSignature -Path $Manifest
    Invoke-ManifestSignature -Path $ModelManifest
}

Write-Host "Release signing/checksum pass complete."

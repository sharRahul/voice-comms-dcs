param(
    [string]$SpecPath = "build\pyinstaller.spec",
    [string]$RequirementsPath = "requirements.txt",
    [string]$ConstraintsPath = "constraints.txt",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

Write-Host "== Voice-Comms-DCS build =="
Write-Host "Using spec: $SpecPath"
Write-Host "Using requirements: $RequirementsPath"
Write-Host "Using constraints: $ConstraintsPath"

if (-not (Test-Path $SpecPath)) {
    throw "PyInstaller spec not found: $SpecPath"
}

if (-not $SkipDependencyInstall) {
    if (-not (Test-Path $RequirementsPath)) {
        throw "Requirements file not found: $RequirementsPath"
    }
    if (-not (Test-Path $ConstraintsPath)) {
        throw "Constraints file not found: $ConstraintsPath. Build dependencies must be installed through the reproducible constraints path."
    }
    python -m pip install --upgrade pip
    python -m pip install -r $RequirementsPath -c $ConstraintsPath
    python -m pip install -e . --no-deps
}
else {
    Write-Host "Skipping dependency installation because -SkipDependencyInstall was provided."
}

if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}
if (Test-Path "build\pyinstaller") {
    Remove-Item -Recurse -Force "build\pyinstaller"
}

pyinstaller --noconfirm --clean $SpecPath
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$expectedExe = "dist\Voice-Comms-DCS\Voice-Comms-DCS.exe"
if (-not (Test-Path $expectedExe)) {
    throw "PyInstaller completed but output is missing: $expectedExe"
}

Write-Host "Build complete: $expectedExe"

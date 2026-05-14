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

pyinstaller --noconfirm --clean $SpecPath

Write-Host "Build complete: dist\Voice-Comms-DCS\Voice-Comms-DCS.exe"

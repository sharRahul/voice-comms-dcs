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
if (Test-Path $ConstraintsPath) {
    Write-Host "Using constraints: $ConstraintsPath"
}

if (-not (Test-Path $SpecPath)) {
    throw "PyInstaller spec not found: $SpecPath"
}

if (-not $SkipDependencyInstall) {
    if (-not (Test-Path $RequirementsPath)) {
        throw "Requirements file not found: $RequirementsPath"
    }
    python -m pip install --upgrade pip
    if (Test-Path $ConstraintsPath) {
        python -m pip install -r $RequirementsPath -c $ConstraintsPath
    }
    else {
        python -m pip install -r $RequirementsPath
    }
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

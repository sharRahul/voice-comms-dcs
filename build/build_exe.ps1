param(
    [string]$SpecPath = "build\pyinstaller.spec"
)

$ErrorActionPreference = "Stop"

Write-Host "== Voice-Comms-DCS build =="
Write-Host "Using spec: $SpecPath"

if (-not (Test-Path $SpecPath)) {
    throw "PyInstaller spec not found: $SpecPath"
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .

if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}

pyinstaller --noconfirm --clean $SpecPath

Write-Host "Build complete: dist\Voice-Comms-DCS\Voice-Comms-DCS.exe"

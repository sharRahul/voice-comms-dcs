param(
    [ValidateSet("tiny.en", "base.en", "small.en")]
    [string]$Model = "base.en",

    [string]$OutputDir = "models\whisper"
)

$ErrorActionPreference = "Stop"

$models = @{
    "tiny.en" = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
    "base.en" = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
    "small.en" = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$url = $models[$Model]
$fileName = "ggml-$Model.bin"
$outputPath = Join-Path $OutputDir $fileName

Write-Host "== Voice-Comms-DCS Whisper.cpp model setup =="
Write-Host "Model: $Model"
Write-Host "Output: $outputPath"

if (Test-Path $outputPath) {
    Write-Host "Model already exists. No download needed."
    exit 0
}

Write-Host "Downloading $url"
Invoke-WebRequest -Uri $url -OutFile $outputPath

Write-Host "Downloaded: $outputPath"
Write-Host "Recommended WebRTC launch argument: --whisper-model $outputPath"

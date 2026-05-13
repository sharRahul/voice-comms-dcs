param(
    [ValidateSet("minimum", "recommended", "quality")]
    [string]$Profile = "minimum",

    [ValidateSet("lessac-low", "ryan-low")]
    [string]$PiperVoice = "lessac-low",

    [switch]$SkipOllama,
    [switch]$SkipPiper,
    [switch]$SkipWhisper
)

$ErrorActionPreference = "Stop"

$ollamaModels = @{
    "minimum" = "qwen2.5:0.5b"
    "recommended" = "qwen2.5:1.5b"
    "quality" = "llama3.2:3b"
}

$piperVoices = @{
    "lessac-low" = @{
        "BaseUrl" = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low"
        "Model" = "en_US-lessac-low.onnx"
        "Json" = "en_US-lessac-low.onnx.json"
    }
    "ryan-low" = @{
        "BaseUrl" = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/low"
        "Model" = "en_US-ryan-low.onnx"
        "Json" = "en_US-ryan-low.onnx.json"
    }
}

Write-Host "== Voice-Comms-DCS local model setup =="
Write-Host "Profile: $Profile"
Write-Host "Piper voice: $PiperVoice"

if (-not $SkipOllama) {
    $ollamaModel = $ollamaModels[$Profile]
    Write-Host "\n== Ollama =="
    Write-Host "Installing/pulling $ollamaModel"
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Write-Warning "Ollama command not found. Install Ollama first, then run: ollama pull $ollamaModel"
    }
    else {
        ollama pull $ollamaModel
    }
}

if (-not $SkipPiper) {
    Write-Host "\n== Piper voice =="
    $voice = $piperVoices[$PiperVoice]
    $outputDir = "models\piper"
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

    $modelPath = Join-Path $outputDir $voice.Model
    $jsonPath = Join-Path $outputDir $voice.Json

    if (-not (Test-Path $modelPath)) {
        $modelUrl = "$($voice.BaseUrl)/$($voice.Model)"
        Write-Host "Downloading $modelUrl"
        Invoke-WebRequest -Uri $modelUrl -OutFile $modelPath
    }
    else {
        Write-Host "Piper model already exists: $modelPath"
    }

    if (-not (Test-Path $jsonPath)) {
        $jsonUrl = "$($voice.BaseUrl)/$($voice.Json)"
        Write-Host "Downloading $jsonUrl"
        Invoke-WebRequest -Uri $jsonUrl -OutFile $jsonPath
    }
    else {
        Write-Host "Piper metadata already exists: $jsonPath"
    }
}

if (-not $SkipWhisper) {
    Write-Host "\n== Whisper.cpp =="
    $whisperModel = if ($Profile -eq "minimum") { "tiny.en" } else { "base.en" }
    & "$PSScriptRoot\setup_whisper.ps1" -Model $whisperModel
}

Write-Host "\nSetup complete."
Write-Host "Minimum profile config: Ollama qwen2.5:0.5b, Piper en_US-lessac-low, Whisper tiny.en/base.en."
Write-Host "Recommended profile config: Ollama qwen2.5:1.5b, Piper en_US-lessac-low, Whisper base.en."

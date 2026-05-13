param(
    [ValidateSet("minimum", "recommended", "quality")]
    [string]$Profile = "minimum",

    [ValidateSet("en", "zh", "ko", "fr", "ru", "es")]
    [string[]]$Languages = @("en"),

    [ValidateSet("tiny", "base")]
    [string]$WhisperQuality = "base",

    [switch]$UseUi,
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

$ollamaModel = $ollamaModels[$Profile]
$languageArgs = $Languages -join " "

Write-Host "== Voice-Comms-DCS local model setup =="
Write-Host "Profile: $Profile"
Write-Host "Languages: $languageArgs"
Write-Host "Whisper quality: $WhisperQuality"
Write-Host "Ollama model: $ollamaModel"

$baseArgs = @(
    "--languages"
) + $Languages + @(
    "--ollama-model", $ollamaModel,
    "--whisper-quality", $WhisperQuality
)

if ($SkipOllama) { $baseArgs += "--skip-ollama" }
if ($SkipPiper) { $baseArgs += "--skip-piper" }
if ($SkipWhisper) { $baseArgs += "--skip-whisper" }

if ($UseUi) {
    python -m voice_comms_dcs.dependency_setup_ui @baseArgs
}
else {
    python -m voice_comms_dcs.setup_dependencies @baseArgs
}

Write-Host "\nSetup complete."
Write-Host "Minimum profile: qwen2.5:0.5b + selected Piper voices + Whisper $WhisperQuality."
Write-Host "Recommended profile: qwen2.5:1.5b + selected Piper voices + Whisper base."

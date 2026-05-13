from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PiperVoiceSpec:
    language: str
    label: str
    model_path: str
    config_path: str
    model_url: str
    config_url: str
    source: str
    license_note: str = "See upstream MODEL_CARD or repository license."


@dataclass(frozen=True)
class WhisperModelSpec:
    key: str
    model_path: str
    url: str
    multilingual: bool


SUPPORTED_LANGUAGES = {
    "en": "English",
    "zh": "中文 / Chinese",
    "ko": "한국어 / Korean",
    "fr": "Français / French",
    "ru": "Русский / Russian",
    "es": "Español / Spanish",
}

# Whisper.cpp language codes. Use multilingual models for all non-English languages.
WHISPER_LANGUAGE_CODES = {
    "en": "en",
    "zh": "zh",
    "ko": "ko",
    "fr": "fr",
    "ru": "ru",
    "es": "es",
}

WHISPER_MODELS = {
    "tiny.en": WhisperModelSpec(
        key="tiny.en",
        model_path="models/whisper/ggml-tiny.en.bin",
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin",
        multilingual=False,
    ),
    "base.en": WhisperModelSpec(
        key="base.en",
        model_path="models/whisper/ggml-base.en.bin",
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin",
        multilingual=False,
    ),
    "tiny": WhisperModelSpec(
        key="tiny",
        model_path="models/whisper/ggml-tiny.bin",
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
        multilingual=True,
    ),
    "base": WhisperModelSpec(
        key="base",
        model_path="models/whisper/ggml-base.bin",
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
        multilingual=True,
    ),
}

# Piper voice URLs use /resolve/main/ so the downloader receives the actual file.
PIPER_VOICES: dict[str, PiperVoiceSpec] = {
    "en": PiperVoiceSpec(
        language="en",
        label="English - Lessac low",
        model_path="models/piper/en_US-lessac-low.onnx",
        config_path="models/piper/en_US-lessac-low.onnx.json",
        model_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx",
        config_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx.json",
        source="rhasspy/piper-voices",
    ),
    "zh": PiperVoiceSpec(
        language="zh",
        label="Chinese - Huayan x_low",
        model_path="models/piper/zh_CN-huayan-x_low.onnx",
        config_path="models/piper/zh_CN-huayan-x_low.onnx.json",
        model_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/x_low/zh_CN-huayan-x_low.onnx",
        config_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/x_low/zh_CN-huayan-x_low.onnx.json",
        source="rhasspy/piper-voices",
    ),
    "ko": PiperVoiceSpec(
        language="ko",
        label="Korean - KSS Piper-compatible",
        model_path="models/piper/piper-kss-korean.onnx",
        config_path="models/piper/piper-kss-korean.onnx.json",
        model_url="https://huggingface.co/neurlang/piper-onnx-kss-korean/resolve/main/piper-kss-korean.onnx",
        config_url="https://huggingface.co/neurlang/piper-onnx-kss-korean/resolve/main/piper-kss-korean.onnx.json",
        source="neurlang/piper-onnx-kss-korean",
        license_note="Non-official Piper-compatible Korean voice; upstream lists CC-BY-NC-SA-4.0.",
    ),
    "fr": PiperVoiceSpec(
        language="fr",
        label="French - Siwis low",
        model_path="models/piper/fr_FR-siwis-low.onnx",
        config_path="models/piper/fr_FR-siwis-low.onnx.json",
        model_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/low/fr_FR-siwis-low.onnx",
        config_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/low/fr_FR-siwis-low.onnx.json",
        source="rhasspy/piper-voices",
    ),
    "ru": PiperVoiceSpec(
        language="ru",
        label="Russian - Ruslan medium",
        model_path="models/piper/ru_RU-ruslan-medium.onnx",
        config_path="models/piper/ru_RU-ruslan-medium.onnx.json",
        model_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx",
        config_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx.json",
        source="rhasspy/piper-voices",
    ),
    "es": PiperVoiceSpec(
        language="es",
        label="Spanish - MLS 9972 low",
        model_path="models/piper/es_ES-mls_9972-low.onnx",
        config_path="models/piper/es_ES-mls_9972-low.onnx.json",
        model_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/mls_9972/low/es_ES-mls_9972-low.onnx",
        config_url="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/mls_9972/low/es_ES-mls_9972-low.onnx.json",
        source="rhasspy/piper-voices",
    ),
}


def get_piper_voice(language: str) -> PiperVoiceSpec:
    return PIPER_VOICES.get(language, PIPER_VOICES["en"])


def get_whisper_model_key(language: str, quality: str = "base") -> str:
    if language == "en":
        return "base.en" if quality == "base" else "tiny.en"
    return "base" if quality == "base" else "tiny"


def get_whisper_language_code(language: str) -> str:
    return WHISPER_LANGUAGE_CODES.get(language, "en")

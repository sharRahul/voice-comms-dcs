from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

import requests

from .app import DispatchResult, VoiceCommsService
from .config import AppConfig, load_config
from .context_manager import AiMode, ContextManager, DynamicContext
from .dashboard_settings import personality_instruction
from .language_models import SUPPORTED_LANGUAGES
from .matcher import find_best_match


OLLAMA_UNAVAILABLE_RESPONSE = "Comms system offline, wingman unavailable. Commands still active."
DEFAULT_LLM_TIMEOUT_SECONDS = 8.0
DEFAULT_CONTEXT_LIMIT_TOKENS = 2048
TOKEN_ESTIMATE_MULTIPLIER = 1.3


class OllamaUnavailableError(RuntimeError):
    """Raised when the local Ollama service cannot answer within the runtime budget."""


class IntentType(str, Enum):
    COMMAND = "command"
    INFORMATIONAL = "informational"
    CONVERSATIONAL = "conversational"
    WARNING = "warning"


@dataclass(frozen=True)
class IntentDecision:
    intent: IntentType
    response_text: str
    command_id: str | None = None
    confidence: float = 0.0
    raw: dict[str, Any] | None = None


class LocalLlmClient:
    """Small Ollama-compatible local LLM client."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:0.5b",
        timeout_seconds: float | None = None,
    ) -> None:
        """Create a bounded local LLM client with environment-configurable timeout."""
        self.base_url = base_url.rstrip("/")
        self.model = model
        timeout_default = timeout_seconds if timeout_seconds is not None else DEFAULT_LLM_TIMEOUT_SECONDS
        self.timeout_seconds = _float_from_env("NIMBUS_LLM_TIMEOUT", timeout_default)

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Send chat messages to Ollama and parse a JSON object response."""
        payload = self._post_chat(
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2, "num_ctx": 1024},
            }
        )
        content = payload.get("message", {}).get("content", "{}")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM returned non-object JSON")
        return parsed

    def chat_text(self, messages: list[dict[str, str]], combat_mode: bool = False) -> str:
        """Send chat messages to Ollama and return the assistant text response."""
        options = {
            "temperature": 0.35 if not combat_mode else 0.1,
            "num_ctx": 1024,
            "num_predict": 24 if combat_mode else 80,
        }
        payload = self._post_chat(
            {"model": self.model, "messages": messages, "stream": False, "options": options}
        )
        return str(payload.get("message", {}).get("content", "")).strip()

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            parsed = response.json()
        except requests.exceptions.RequestException as exc:
            raise OllamaUnavailableError("Ollama did not respond within the runtime budget.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Ollama returned a non-object response")
        return parsed


class NimbusIntelligence:
    """Telemetry-aware multilingual intent switchboard for the conversational cockpit."""

    def __init__(
        self,
        config: AppConfig,
        context_manager: ContextManager | None = None,
        llm: LocalLlmClient | None = None,
        enable_llm: bool = True,
        personality: str = "professional",
    ) -> None:
        """Initialise Nimbus with deterministic command handling and optional local LLM support."""
        self.config = config
        self.context_manager = context_manager or ContextManager()
        self.llm = llm or LocalLlmClient(
            base_url=config.llm.base_url,
            model=config.llm.model,
            timeout_seconds=config.llm.timeout_seconds,
        )
        self.enable_llm = enable_llm
        self.command_service = VoiceCommsService(config)
        self.language = config.language.selected
        self.personality = personality

    @property
    def context_window_tokens(self) -> int:
        """Return a word-count based estimate of the in-memory conversation token load."""
        with self.context_manager._lock:
            return self._estimate_history_tokens_unlocked()

    def trim_history_if_needed(self) -> None:
        """Drop the oldest user/assistant turns when the conversation exceeds its token budget."""
        limit = _int_from_env("NIMBUS_CONTEXT_LIMIT", DEFAULT_CONTEXT_LIMIT_TOKENS)
        if limit <= 0:
            return
        with self.context_manager._lock:
            while self._estimate_history_tokens_unlocked() > limit and self.context_manager._turns:
                self.context_manager._turns.popleft()
                if self.context_manager._turns:
                    self.context_manager._turns.popleft()

    def set_language(self, language: str) -> None:
        """Set Nimbus's response language when it is one of the supported language codes."""
        if language in SUPPORTED_LANGUAGES:
            self.language = language

    def set_personality(self, personality: str) -> None:
        """Set the tactical response personality used in local LLM prompts."""
        self.personality = personality

    def close(self) -> None:
        """Release runtime resources held by the deterministic DCS command service."""
        self.command_service.close()

    def update_telemetry(self, telemetry: dict[str, Any]) -> DynamicContext:
        """Refresh the dynamic DCS telemetry context used by Nimbus responses."""
        return self.context_manager.update_telemetry(telemetry)

    def handle_pilot_text(self, text: str) -> tuple[IntentDecision, DispatchResult | None]:
        """Route pilot text through warnings, deterministic commands, telemetry, or the LLM."""
        self.trim_history_if_needed()
        context = self.context_manager.get_context()

        warning = self._priority_warning_decision(context)
        if warning:
            self.context_manager.add_turn("assistant", warning.response_text)
            self.trim_history_if_needed()
            return warning, None

        command_match = find_best_match(text, self.config.commands, self.config.min_confidence)
        if command_match:
            dispatch = self.command_service.handle_transcript(text)
            response = _combat_trim(_phrase(self.language, "copy"), context.mode)
            decision = IntentDecision(
                intent=IntentType.COMMAND,
                response_text=response,
                command_id=command_match.command.id,
                confidence=command_match.confidence,
            )
            self._remember_turn_pair(text, response)
            return decision, dispatch

        if _looks_like_telemetry_question(text):
            response = self._answer_telemetry_question(text, context)
            decision = IntentDecision(
                intent=IntentType.INFORMATIONAL,
                response_text=_combat_trim(response, context.mode),
                confidence=0.85,
            )
            self._remember_turn_pair(text, decision.response_text)
            return decision, None

        response = self._conversational_response(text, context)
        decision = IntentDecision(
            intent=IntentType.CONVERSATIONAL,
            response_text=_combat_trim(response, context.mode),
            confidence=0.65,
        )
        self._remember_turn_pair(text, decision.response_text)
        return decision, None

    def _estimate_history_tokens_unlocked(self) -> int:
        return sum(_estimate_tokens(turn.text) for turn in self.context_manager._turns)

    def _remember_turn_pair(self, user_text: str, assistant_text: str) -> None:
        self.context_manager.add_turn("user", user_text)
        self.context_manager.add_turn("assistant", assistant_text)
        self.trim_history_if_needed()

    def _priority_warning_decision(self, context: DynamicContext) -> IntentDecision | None:
        if context.warning and context.mode is AiMode.COMBAT:
            return IntentDecision(
                intent=IntentType.WARNING,
                response_text=_combat_trim(context.warning.message, context.mode),
                confidence=1.0,
            )
        return None

    def _answer_telemetry_question(self, text: str, context: DynamicContext) -> str:
        lower = text.lower()
        telemetry = context.telemetry
        lang = self.language
        if "fuel" in lower or "bingo" in lower:
            fuel = _get_number(telemetry, "internal", "fuel_total_kg")
            return _telemetry_phrase(lang, "fuel_unavailable") if fuel is None else _telemetry_phrase(lang, "fuel", fuel=fuel)
        if "altitude" in lower or "height" in lower:
            alt = _get_number(telemetry, "spatial", "altitude_asl_ft")
            agl = _get_number(telemetry, "spatial", "altitude_agl_ft")
            if alt is None:
                return _telemetry_phrase(lang, "altitude_unavailable")
            return _telemetry_phrase(lang, "altitude_agl", alt=alt, agl=agl) if agl is not None else _telemetry_phrase(lang, "altitude", alt=alt)
        if "speed" in lower or "airspeed" in lower:
            ias = _get_number(telemetry, "spatial", "ias_kt")
            tas = _get_number(telemetry, "spatial", "tas_kt")
            if ias is None:
                return _telemetry_phrase(lang, "speed_unavailable")
            return _telemetry_phrase(lang, "speed_tas", ias=ias, tas=tas) if tas is not None else _telemetry_phrase(lang, "speed", ias=ias)
        if "target" in lower or "bandit" in lower or "bogey" in lower:
            target = telemetry.get("tactical", {}).get("locked_target", {})
            if not isinstance(target, dict) or not target:
                return _telemetry_phrase(lang, "target_unavailable")
            return _telemetry_phrase(
                lang,
                "target",
                bearing=target.get("bearing_deg", "unknown"),
                range_nm=target.get("range_nm", "unknown"),
                velocity=target.get("velocity_kt", "unknown"),
            )
        return context.prompt_prefix or _telemetry_phrase(lang, "telemetry_unavailable")

    def _conversational_response(self, text: str, context: DynamicContext) -> str:
        if not self.enable_llm:
            return _phrase(self.language, "monitoring")

        self.trim_history_if_needed()
        messages = self.context_manager.build_llm_messages(text)
        messages[0]["content"] += "\n\n" + language_instruction(self.language)
        messages[0]["content"] += "\n" + personality_instruction(self.personality)
        try:
            response = self.llm.chat_text(messages, combat_mode=context.mode is AiMode.COMBAT)
        except OllamaUnavailableError:
            return OLLAMA_UNAVAILABLE_RESPONSE
        except Exception:
            return _phrase(self.language, "local_model_unavailable")
        return response or _phrase(self.language, "say_again")


def language_instruction(language: str) -> str:
    """Return the prompt instruction that keeps Nimbus responses in the selected language."""
    names = {
        "en": "English",
        "zh": "Chinese",
        "ko": "Korean",
        "fr": "French",
        "ru": "Russian",
        "es": "Spanish",
    }
    target = names.get(language, "English")
    return f"Always respond to the pilot in {target}. Keep tactical brevity and do not switch languages."


def _phrase(language: str, key: str) -> str:
    phrases = {
        "copy": {"en": "Copy.", "zh": "收到。", "ko": "확인.", "fr": "Reçu.", "ru": "Принято.", "es": "Copiado."},
        "monitoring": {
            "en": "I am with you. Telemetry is online.",
            "zh": "我在。遥测在线。",
            "ko": "함께합니다. 텔레메트리 정상.",
            "fr": "Je suis avec vous. Télémétrie active.",
            "ru": "Я с вами. Телеметрия активна.",
            "es": "Estoy contigo. Telemetría activa.",
        },
        "local_model_unavailable": {
            "en": "Local model unavailable. I am still monitoring telemetry.",
            "zh": "本地模型不可用。我仍在监控遥测。",
            "ko": "로컬 모델을 사용할 수 없습니다. 텔레메트리는 계속 감시합니다.",
            "fr": "Modèle local indisponible. Je surveille toujours la télémétrie.",
            "ru": "Локальная модель недоступна. Я продолжаю следить за телеметрией.",
            "es": "Modelo local no disponible. Sigo vigilando la telemetría.",
        },
        "say_again": {"en": "Say again.", "zh": "请重复。", "ko": "다시 말해 주세요.", "fr": "Répétez.", "ru": "Повторите.", "es": "Repita."},
    }
    return phrases[key].get(language, phrases[key]["en"])


def _telemetry_phrase(language: str, key: str, **values: Any) -> str:
    templates = {
        "en": {
            "fuel": "Fuel is {fuel:.0f} kilograms.",
            "fuel_unavailable": "Fuel telemetry unavailable.",
            "altitude": "Altitude {alt:.0f} feet ASL.",
            "altitude_agl": "Altitude {alt:.0f} feet ASL, {agl:.0f} AGL.",
            "altitude_unavailable": "Altitude telemetry unavailable.",
            "speed": "Airspeed {ias:.0f} knots indicated.",
            "speed_tas": "Airspeed {ias:.0f} knots indicated, {tas:.0f} true.",
            "speed_unavailable": "Airspeed telemetry unavailable.",
            "target": "Locked target bearing {bearing}, range {range_nm} miles, speed {velocity}.",
            "target_unavailable": "No locked target data.",
            "telemetry_unavailable": "Telemetry unavailable.",
        },
        "zh": {
            "fuel": "燃油 {fuel:.0f} 公斤。", "fuel_unavailable": "燃油遥测不可用。",
            "altitude": "高度 {alt:.0f} 英尺海拔。", "altitude_agl": "高度 {alt:.0f} 英尺海拔，{agl:.0f} 英尺离地。", "altitude_unavailable": "高度遥测不可用。",
            "speed": "指示空速 {ias:.0f} 节。", "speed_tas": "指示空速 {ias:.0f} 节，真空速 {tas:.0f} 节。", "speed_unavailable": "空速遥测不可用。",
            "target": "锁定目标方位 {bearing}，距离 {range_nm} 海里，速度 {velocity}。", "target_unavailable": "没有锁定目标数据。", "telemetry_unavailable": "遥测不可用。",
        },
        "ko": {
            "fuel": "연료 {fuel:.0f} 킬로그램.", "fuel_unavailable": "연료 텔레메트리 없음.",
            "altitude": "고도 {alt:.0f} 피트 ASL.", "altitude_agl": "고도 {alt:.0f} 피트 ASL, {agl:.0f} AGL.", "altitude_unavailable": "고도 텔레메트리 없음.",
            "speed": "지시대기속도 {ias:.0f} 노트.", "speed_tas": "지시대기속도 {ias:.0f} 노트, 진대기속도 {tas:.0f} 노트.", "speed_unavailable": "속도 텔레메트리 없음.",
            "target": "락온 목표 방위 {bearing}, 거리 {range_nm} 해리, 속도 {velocity}.", "target_unavailable": "락온 목표 데이터 없음.", "telemetry_unavailable": "텔레메트리 없음.",
        },
        "fr": {
            "fuel": "Carburant {fuel:.0f} kilogrammes.", "fuel_unavailable": "Télémétrie carburant indisponible.",
            "altitude": "Altitude {alt:.0f} pieds ASL.", "altitude_agl": "Altitude {alt:.0f} pieds ASL, {agl:.0f} AGL.", "altitude_unavailable": "Télémétrie altitude indisponible.",
            "speed": "Vitesse indiquée {ias:.0f} nœuds.", "speed_tas": "Vitesse indiquée {ias:.0f} nœuds, vraie {tas:.0f}.", "speed_unavailable": "Télémétrie vitesse indisponible.",
            "target": "Cible verrouillée cap {bearing}, distance {range_nm} nautiques, vitesse {velocity}.", "target_unavailable": "Aucune donnée de cible verrouillée.", "telemetry_unavailable": "Télémétrie indisponible.",
        },
        "ru": {
            "fuel": "Топливо {fuel:.0f} килограммов.", "fuel_unavailable": "Телеметрия топлива недоступна.",
            "altitude": "Высота {alt:.0f} футов ASL.", "altitude_agl": "Высота {alt:.0f} футов ASL, {agl:.0f} AGL.", "altitude_unavailable": "Телеметрия высоты недоступна.",
            "speed": "Приборная скорость {ias:.0f} узлов.", "speed_tas": "Приборная скорость {ias:.0f} узлов, истинная {tas:.0f}.", "speed_unavailable": "Телеметрия скорости недоступна.",
            "target": "Захваченная цель пеленг {bearing}, дальность {range_nm} миль, скорость {velocity}.", "target_unavailable": "Нет данных захваченной цели.", "telemetry_unavailable": "Телеметрия недоступна.",
        },
        "es": {
            "fuel": "Combustible {fuel:.0f} kilogramos.", "fuel_unavailable": "Telemetría de combustible no disponible.",
            "altitude": "Altitud {alt:.0f} pies ASL.", "altitude_agl": "Altitud {alt:.0f} pies ASL, {agl:.0f} AGL.", "altitude_unavailable": "Telemetría de altitud no disponible.",
            "speed": "Velocidad indicada {ias:.0f} nudos.", "speed_tas": "Velocidad indicada {ias:.0f} nudos, verdadera {tas:.0f}.", "speed_unavailable": "Telemetría de velocidad no disponible.",
            "target": "Objetivo fijado rumbo {bearing}, distancia {range_nm} millas, velocidad {velocity}.", "target_unavailable": "Sin datos de objetivo fijado.", "telemetry_unavailable": "Telemetría no disponible.",
        },
    }
    template = templates.get(language, templates["en"]).get(key, templates["en"].get(key, "Telemetry unavailable."))
    return template.format(**values)


def _looks_like_telemetry_question(text: str) -> bool:
    lower = text.lower()
    keywords = {"fuel", "bingo", "altitude", "height", "speed", "airspeed", "heading", "target", "bandit", "bogey", "rwr", "gear", "flaps"}
    question_words = {"what", "how", "where", "status", "tell", "report"}
    return any(word in lower for word in keywords) and ("?" in text or any(word in lower for word in question_words))


def _combat_trim(text: str, mode: AiMode) -> str:
    words = text.split()
    if mode is AiMode.COMBAT and len(words) > 10:
        return " ".join(words[:10])
    return text


def _get_number(data: dict[str, Any], *path: str) -> float | None:
    cursor: Any = data
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    try:
        if cursor is None:
            return None
        return float(cursor)
    except (TypeError, ValueError):
        return None


def _float_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _int_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _estimate_tokens(text: str) -> int:
    return int(len(text.split()) * TOKEN_ESTIMATE_MULTIPLIER)


def main(argv: list[str] | None = None) -> int:
    """Run a one-shot Nimbus intelligence check from the command line."""
    parser = argparse.ArgumentParser(description="Run a one-shot Nimbus intelligence test.")
    parser.add_argument("--config", default="config/commands.json")
    parser.add_argument("--text", required=True)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--personality", default="professional", choices=["professional", "conversational", "instructor", "rio"])
    args = parser.parse_args(argv)

    config = load_config(args.config)
    nimbus = NimbusIntelligence(config=config, enable_llm=not args.no_llm, personality=args.personality)
    decision, dispatch = nimbus.handle_pilot_text(args.text)
    print(json.dumps({"decision": decision.__dict__, "dispatch": dispatch.__dict__ if dispatch else None}, indent=2, default=str, ensure_ascii=False))
    nimbus.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

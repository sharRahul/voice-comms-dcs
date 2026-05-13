from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

import requests

from .app import DispatchResult, VoiceCommsService
from .config import AppConfig, load_config
from .context_manager import AiMode, ContextManager, DynamicContext
from .matcher import find_best_match


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
    """Small Ollama-compatible local LLM client.

    No cloud endpoints are used. The default endpoint is the local Ollama HTTP API.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:3b-instruct",
        timeout_seconds: float = 4.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 2048,
                },
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload.get("message", {}).get("content", "{}")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM returned non-object JSON")
        return parsed

    def chat_text(self, messages: list[dict[str, str]], combat_mode: bool = False) -> str:
        options = {
            "temperature": 0.35 if not combat_mode else 0.1,
            "num_ctx": 2048,
            "num_predict": 32 if combat_mode else 120,
        }
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": options,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("message", {}).get("content", "")).strip()


class NimbusIntelligence:
    """Telemetry-aware intent switchboard for the conversational cockpit.

    The switchboard uses deterministic command matching first for safety, then a local LLM for
    informational and conversational responses. It can run without Ollama by falling back to compact
    deterministic telemetry answers.
    """

    def __init__(
        self,
        config: AppConfig,
        context_manager: ContextManager | None = None,
        llm: LocalLlmClient | None = None,
        enable_llm: bool = True,
    ) -> None:
        self.config = config
        self.context_manager = context_manager or ContextManager()
        self.llm = llm or LocalLlmClient()
        self.enable_llm = enable_llm
        self.command_service = VoiceCommsService(config)

    def close(self) -> None:
        self.command_service.close()

    def update_telemetry(self, telemetry: dict[str, Any]) -> DynamicContext:
        return self.context_manager.update_telemetry(telemetry)

    def handle_pilot_text(self, text: str) -> tuple[IntentDecision, DispatchResult | None]:
        context = self.context_manager.get_context()

        warning = self._priority_warning_decision(context)
        if warning:
            self.context_manager.add_turn("assistant", warning.response_text)
            return warning, None

        command_match = find_best_match(text, self.config.commands, self.config.min_confidence)
        if command_match:
            dispatch = self.command_service.handle_transcript(text)
            response = _combat_trim("Copy.", context.mode)
            decision = IntentDecision(
                intent=IntentType.COMMAND,
                response_text=response,
                command_id=command_match.command.id,
                confidence=command_match.confidence,
            )
            self.context_manager.add_turn("user", text)
            self.context_manager.add_turn("assistant", response)
            return decision, dispatch

        if _looks_like_telemetry_question(text):
            response = self._answer_telemetry_question(text, context)
            decision = IntentDecision(
                intent=IntentType.INFORMATIONAL,
                response_text=_combat_trim(response, context.mode),
                confidence=0.85,
            )
            self.context_manager.add_turn("user", text)
            self.context_manager.add_turn("assistant", decision.response_text)
            return decision, None

        response = self._conversational_response(text, context)
        decision = IntentDecision(
            intent=IntentType.CONVERSATIONAL,
            response_text=_combat_trim(response, context.mode),
            confidence=0.65,
        )
        self.context_manager.add_turn("user", text)
        self.context_manager.add_turn("assistant", decision.response_text)
        return decision, None

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
        if "fuel" in lower or "bingo" in lower:
            fuel = _get_number(telemetry, "internal", "fuel_total_kg")
            if fuel is None:
                return "Fuel telemetry unavailable."
            return f"Fuel is {fuel:.0f} kilograms."
        if "altitude" in lower or "height" in lower:
            alt = _get_number(telemetry, "spatial", "altitude_asl_ft")
            agl = _get_number(telemetry, "spatial", "altitude_agl_ft")
            if alt is None:
                return "Altitude telemetry unavailable."
            if agl is not None:
                return f"Altitude {alt:.0f} feet ASL, {agl:.0f} AGL."
            return f"Altitude {alt:.0f} feet ASL."
        if "speed" in lower or "airspeed" in lower:
            ias = _get_number(telemetry, "spatial", "ias_kt")
            tas = _get_number(telemetry, "spatial", "tas_kt")
            if ias is None:
                return "Airspeed telemetry unavailable."
            if tas is not None:
                return f"Airspeed {ias:.0f} knots indicated, {tas:.0f} true."
            return f"Airspeed {ias:.0f} knots indicated."
        if "target" in lower or "bandit" in lower or "bogey" in lower:
            target = telemetry.get("tactical", {}).get("locked_target", {})
            if not isinstance(target, dict) or not target:
                return "No locked target data."
            bearing = target.get("bearing_deg", "unknown")
            range_nm = target.get("range_nm", "unknown")
            velocity = target.get("velocity_kt", "unknown")
            return f"Locked target bearing {bearing}, range {range_nm} miles, speed {velocity}."
        return context.prompt_prefix or "Telemetry unavailable."

    def _conversational_response(self, text: str, context: DynamicContext) -> str:
        if not self.enable_llm:
            return "I am with you. Telemetry is online."

        messages = self.context_manager.build_llm_messages(text)
        try:
            response = self.llm.chat_text(messages, combat_mode=context.mode is AiMode.COMBAT)
        except Exception:
            return "Local model unavailable. I am still monitoring telemetry."
        return response or "Say again."


def _looks_like_telemetry_question(text: str) -> bool:
    lower = text.lower()
    keywords = {
        "fuel",
        "bingo",
        "altitude",
        "height",
        "speed",
        "airspeed",
        "heading",
        "target",
        "bandit",
        "bogey",
        "rwr",
        "gear",
        "flaps",
    }
    question_words = {"what", "how", "where", "status", "tell", "report"}
    return any(word in lower for word in keywords) and (
        "?" in text or any(word in lower for word in question_words)
    )


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a one-shot Nimbus intelligence test.")
    parser.add_argument("--config", default="config/commands.json")
    parser.add_argument("--text", required=True)
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    nimbus = NimbusIntelligence(config=config, enable_llm=not args.no_llm)
    decision, dispatch = nimbus.handle_pilot_text(args.text)
    print(json.dumps({"decision": decision.__dict__, "dispatch": dispatch.__dict__ if dispatch else None}, indent=2, default=str))
    nimbus.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

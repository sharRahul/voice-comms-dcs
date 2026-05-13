from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .config import VoiceCommand

_WORD_RE = re.compile(r"[^a-z0-9 ]+")


@dataclass(frozen=True)
class MatchResult:
    command: VoiceCommand
    phrase: str
    confidence: float
    transcript: str


def normalise_text(text: str) -> str:
    """Normalise STT text so matching is predictable and config-friendly."""
    cleaned = _WORD_RE.sub(" ", text.lower())
    return " ".join(cleaned.split())


def _score(transcript: str, phrase: str) -> float:
    if not transcript or not phrase:
        return 0.0
    if transcript == phrase:
        return 1.0
    if phrase in transcript:
        # Favour commands embedded in longer STT output such as "please request tanker".
        return min(0.98, 0.88 + (len(phrase) / max(len(transcript), 1)) * 0.1)
    return SequenceMatcher(None, transcript, phrase).ratio()


def find_best_match(
    transcript: str,
    commands: tuple[VoiceCommand, ...],
    min_confidence: float,
) -> MatchResult | None:
    normalised = normalise_text(transcript)
    best: MatchResult | None = None

    for command in commands:
        for phrase in command.phrases:
            confidence = _score(normalised, phrase)
            if best is None or confidence > best.confidence:
                best = MatchResult(
                    command=command,
                    phrase=phrase,
                    confidence=confidence,
                    transcript=normalised,
                )

    if best is None or best.confidence < min_confidence:
        return None
    return best

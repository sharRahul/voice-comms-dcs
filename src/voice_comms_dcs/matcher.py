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


@dataclass(frozen=True)
class CompiledPhrase:
    command: VoiceCommand
    phrase: str
    tokens: frozenset[str]


@dataclass(frozen=True)
class CommandMatcher:
    commands: tuple[VoiceCommand, ...]
    phrases: tuple[CompiledPhrase, ...]
    exact: dict[str, CompiledPhrase]

    @classmethod
    def from_commands(cls, commands: tuple[VoiceCommand, ...]) -> "CommandMatcher":
        phrases: list[CompiledPhrase] = []
        exact: dict[str, CompiledPhrase] = {}
        for command in commands:
            for raw_phrase in command.phrases:
                phrase = normalise_text(raw_phrase)
                if not phrase:
                    continue
                compiled = CompiledPhrase(
                    command=command,
                    phrase=phrase,
                    tokens=frozenset(phrase.split()),
                )
                phrases.append(compiled)
                exact.setdefault(phrase, compiled)
        return cls(commands=commands, phrases=tuple(phrases), exact=exact)

    def find_best_match(self, transcript: str, min_confidence: float) -> MatchResult | None:
        normalised = normalise_text(transcript)
        if not normalised:
            return None

        exact = self.exact.get(normalised)
        if exact is not None:
            return MatchResult(
                command=exact.command,
                phrase=exact.phrase,
                confidence=1.0,
                transcript=normalised,
            )

        transcript_tokens = frozenset(normalised.split())
        best: MatchResult | None = None

        for compiled in self.phrases:
            confidence = _score_compiled(normalised, transcript_tokens, compiled)
            if confidence <= 0.0:
                continue
            if best is None or confidence > best.confidence:
                best = MatchResult(
                    command=compiled.command,
                    phrase=compiled.phrase,
                    confidence=confidence,
                    transcript=normalised,
                )

        if best is None or best.confidence < min_confidence:
            return None
        return best


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


def _score_compiled(
    transcript: str,
    transcript_tokens: frozenset[str],
    compiled: CompiledPhrase,
) -> float:
    phrase = compiled.phrase
    if phrase in transcript:
        return min(0.98, 0.88 + (len(phrase) / max(len(transcript), 1)) * 0.1)

    has_token_overlap = bool(transcript_tokens & compiled.tokens)
    length_ratio = min(len(transcript), len(phrase)) / max(len(transcript), len(phrase), 1)
    if not has_token_overlap and length_ratio < 0.72:
        return 0.0
    return SequenceMatcher(None, transcript, phrase).ratio()


def find_best_match(
    transcript: str,
    commands: tuple[VoiceCommand, ...],
    min_confidence: float,
) -> MatchResult | None:
    return CommandMatcher.from_commands(commands).find_best_match(transcript, min_confidence)

"""Stable models for local speech preparation and quality-control reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from ..policy import (
    DEFAULT_SEQUENCE_FALLBACK_MODE,
    SequenceFallbackMode,
    validate_sequence_fallback_mode,
)


@dataclass(frozen=True, slots=True)
class SpeechPreparationOptions:
    """Narrow, stable options for preparing SSMD for speech."""

    mode: Literal["off", "audit", "annotate"] = "off"
    language: str | None = None
    strict: bool = False
    sequence_fallback_mode: SequenceFallbackMode = DEFAULT_SEQUENCE_FALLBACK_MODE
    pronunciations: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in {"off", "audit", "annotate"}:
            raise ValueError("mode must be 'off', 'audit', or 'annotate'")
        validate_sequence_fallback_mode(self.sequence_fallback_mode)
        if self.language is not None and (
            not isinstance(self.language, str) or not self.language.strip()
        ):
            raise ValueError("language must be a non-empty string or None")
        if not isinstance(self.strict, bool):
            raise TypeError("strict must be a bool")
        if not isinstance(self.pronunciations, Mapping):
            raise TypeError("pronunciations must be a mapping of source terms to spoken forms")
        copied: dict[str, str] = {}
        for source, spoken in self.pronunciations.items():
            if (
                not isinstance(source, str)
                or not source.strip()
                or source != source.strip()
                or "\n" in source
                or "\r" in source
            ):
                raise ValueError(
                    "pronunciation keys must be non-empty single-line strings "
                    "without edge whitespace"
                )
            if not isinstance(spoken, str) or not spoken.strip():
                raise ValueError("pronunciation values must be non-empty strings")
            copied[source] = spoken
        object.__setattr__(self, "pronunciations", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class SpeechChange:
    """One exact normalization candidate and its write-back disposition."""

    source_start: int | None
    source_end: int | None
    source_text: str
    spoken_text: str
    language: str
    kind: str | None = None
    rule: str | None = None
    status: Literal["applied", "skipped"] = "applied"
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SpeechIssue:
    """One unresolved source-quality or safe-mapping issue."""

    code: str
    severity: Literal["info", "warning", "error"]
    source_start: int | None
    source_end: int | None
    text: str | None
    message: str
    codepoint: str | None = None
    unicode_name: str | None = None


@dataclass(frozen=True, slots=True)
class SpeechPreparationReport:
    """Deterministic, JSON-ready provenance for one speech preparation pass."""

    backend: str
    backend_version: str | None
    languages: tuple[str, ...]
    changes: tuple[SpeechChange, ...]
    issues: tuple[SpeechIssue, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report with stable field ordering."""
        return {
            "backend": self.backend,
            "backend_version": self.backend_version,
            "languages": list(self.languages),
            "changes": [asdict(change) for change in self.changes],
            "issues": [asdict(issue) for issue in self.issues],
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        """Serialize the report deterministically as UTF-8-friendly JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass(frozen=True, slots=True)
class SpeechPreparationResult:
    """SSMD output paired with its speech-preparation report."""

    ssmd: str
    report: SpeechPreparationReport

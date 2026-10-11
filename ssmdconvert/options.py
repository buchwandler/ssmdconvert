"""Immutable, validated option objects for the application-facing API."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from .linguistics import SpacyPolicy
from .policy import DEFAULT_SEQUENCE_FALLBACK_MODE, SequenceFallbackMode

if TYPE_CHECKING:
    from ttsready import PreparationProfile, SpeechOverride

SpeechMode = Literal["freeze", "preserve"]


def _freeze_json(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain NaN or Infinity")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} mapping keys must be strings")
            frozen[key] = _freeze_json(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, f"{path}[{index}]") for index, item in enumerate(value))
    raise TypeError(f"{path} must contain only JSON-compatible values")


def thaw_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a fresh mutable JSON mapping for existing metadata services."""

    def thaw(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {key: thaw(value) for key, value in item.items()}
        if isinstance(item, tuple):
            return [thaw(value) for value in item]
        return item

    return thaw(value)


def _freeze_metadata(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    frozen = _freeze_json(value, name)
    return frozen


def _optional_text(value: str | None, name: str, *, non_empty: bool = False) -> None:
    if value is not None and (not isinstance(value, str) or (non_empty and not value.strip())):
        qualifier = "non-empty " if non_empty else ""
        raise TypeError(f"{name} must be {qualifier}text or None")


def _sequence_mode(value: str, name: str = "sequence_fallback_mode") -> None:
    if value not in {"preserve", "spell"}:
        raise ValueError(f"{name} must be 'preserve' or 'spell'")


def _spacy_policy(value: str) -> None:
    if value not in {"off", "auto", "sm", "md", "lg", "trf"}:
        raise ValueError("spacy must be one of: off, auto, sm, md, lg, trf")


@dataclass(frozen=True, slots=True, kw_only=True)
class SpeechOptions:
    """Speech behavior for a book operation; defaults are local and deterministic."""

    mode: SpeechMode = "freeze"
    spacy: SpacyPolicy = "off"

    def __post_init__(self) -> None:
        if self.mode not in {"freeze", "preserve"}:
            raise ValueError("speech mode must be 'freeze' or 'preserve'")
        _spacy_policy(self.spacy)


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentConversionOptions:
    """Validated document conversion settings shared by Python callers and CLI."""

    language: str | None = None
    title: str | None = None
    author: str | None = None
    metadata_overrides: Mapping[str, Any] = field(default_factory=dict)
    sequence_fallback_mode: SequenceFallbackMode = DEFAULT_SEQUENCE_FALLBACK_MODE

    def __post_init__(self) -> None:
        _optional_text(self.language, "language", non_empty=True)
        _optional_text(self.title, "title")
        _optional_text(self.author, "author")
        _sequence_mode(self.sequence_fallback_mode)
        object.__setattr__(
            self,
            "metadata_overrides",
            _freeze_metadata(self.metadata_overrides, "metadata_overrides"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BookConversionOptions:
    """Validated EPUB selection, metadata, and optional speech-freeze settings."""

    chapters: str = "all"
    language: str | None = None
    metadata_overrides: Mapping[str, Any] = field(default_factory=dict)
    sequence_fallback_mode: SequenceFallbackMode = DEFAULT_SEQUENCE_FALLBACK_MODE
    speech: SpeechOptions = field(default_factory=SpeechOptions)

    def __post_init__(self) -> None:
        if not isinstance(self.chapters, str) or not self.chapters.strip():
            raise ValueError("chapters must be a non-empty selector string")
        _optional_text(self.language, "language", non_empty=True)
        _sequence_mode(self.sequence_fallback_mode)
        if not isinstance(self.speech, SpeechOptions):
            raise TypeError("speech must be a SpeechOptions instance")
        object.__setattr__(
            self,
            "metadata_overrides",
            _freeze_metadata(self.metadata_overrides, "metadata_overrides"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisOptions:
    """SSMD speech-preparation policy; analysis itself never writes source files."""

    chapters: str = "all"
    language: str | None = None
    fallback_language: str | None = None
    spacy: SpacyPolicy = "off"
    include_titles: bool = True
    sequence_fallback_mode: SequenceFallbackMode | None = None
    profile: PreparationProfile | None = None
    overrides: tuple[SpeechOverride, ...] = ()
    pronunciations: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.chapters, str) or not self.chapters.strip():
            raise ValueError("chapters must be a non-empty selector string")
        _optional_text(self.language, "language", non_empty=True)
        _optional_text(self.fallback_language, "fallback_language", non_empty=True)
        _spacy_policy(self.spacy)
        if not isinstance(self.include_titles, bool):
            raise TypeError("include_titles must be a bool")
        if self.sequence_fallback_mode is not None:
            _sequence_mode(self.sequence_fallback_mode)
        if not isinstance(self.overrides, tuple):
            raise TypeError("overrides must be a tuple of ttsready SpeechOverride values")
        if self.overrides:
            from ttsready import SpeechOverride

            if any(not isinstance(item, SpeechOverride) for item in self.overrides):
                raise TypeError("overrides must contain only ttsready SpeechOverride values")
        if self.profile is not None:
            from ttsready import PreparationProfile

            if not isinstance(self.profile, PreparationProfile):
                raise TypeError("profile must be a ttsready PreparationProfile or None")
        if not isinstance(self.pronunciations, Mapping):
            raise TypeError("pronunciations must be a mapping of words to spoken forms")
        normalized: dict[str, str] = {}
        for surface, spoken in self.pronunciations.items():
            if not isinstance(surface, str) or not surface.strip() or surface != surface.strip():
                raise ValueError(
                    "pronunciation keys must be non-empty strings without edge whitespace"
                )
            if not isinstance(spoken, str) or not spoken.strip():
                raise ValueError("pronunciation values must be non-empty strings")
            normalized[surface] = spoken
        object.__setattr__(self, "pronunciations", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True, kw_only=True)
class TextProjectionOptions:
    """Options for deterministic prepared-text projection and paragraph splitting."""

    max_paragraph_chars: int | None = 1000
    include_titles: bool = True

    def __post_init__(self) -> None:
        if self.max_paragraph_chars is not None and (
            isinstance(self.max_paragraph_chars, bool)
            or not isinstance(self.max_paragraph_chars, int)
            or self.max_paragraph_chars < 1
        ):
            raise ValueError("max_paragraph_chars must be at least 1 or None")
        if not isinstance(self.include_titles, bool):
            raise TypeError("include_titles must be a bool")

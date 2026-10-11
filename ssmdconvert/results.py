"""Typed, immutable outcomes for the application-facing API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, cast

from .models import Book

if TYPE_CHECKING:
    from .analysis.models import SsmdAnalysisIssue
    from .speech.models import SpeechFreezeSummary, SsmdMappedChange

SpeechOutcomeStatus = Literal["complete", "preserved"]


def _freeze_json(value: Any, path: str = "report") -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} object keys must be strings")
            frozen[key] = _freeze_json(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_json(item, f"{path}[{index}]") for index, item in enumerate(value))
    raise TypeError(f"{path} contains non-JSON value {type(value).__name__}")


def json_report_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return mutable JSON-ready data from an immutable report mapping."""

    def thaw(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {key: thaw(child) for key, child in item.items()}
        if isinstance(item, tuple):
            return [thaw(child) for child in item]
        return item

    return cast(dict[str, Any], thaw(value))


@dataclass(frozen=True, slots=True)
class SpeechOutcome:
    """Discriminated freeze/preserve outcome with a versioned JSON-ready report."""

    status: SpeechOutcomeStatus
    summary: SpeechFreezeSummary | None
    report: Mapping[str, object]
    analysis_id: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"complete", "preserved"}:
            raise ValueError("speech outcome status must be 'complete' or 'preserved'")
        if not isinstance(self.report, Mapping):
            raise TypeError("speech outcome report must be a mapping")
        frozen_report = _freeze_json(self.report)
        if frozen_report.get("format") != "ssmdconvert-speech-freeze-report":
            raise ValueError("speech outcome report has an unsupported format")
        if type(frozen_report.get("version")) is not int or frozen_report["version"] != 1:
            raise ValueError("speech outcome report has an unsupported version")
        if frozen_report.get("status") != self.status:
            raise ValueError("speech outcome status must match the report status")
        if self.status == "complete" and (
            self.summary is None or not getattr(self.summary, "complete", False)
        ):
            raise ValueError("a complete speech outcome requires a complete freeze summary")
        if self.status == "preserved" and self.summary is not None:
            raise ValueError("a preserved speech outcome cannot claim a freeze summary")
        if self.analysis_id is not None and not isinstance(self.analysis_id, str):
            raise TypeError("analysis_id must be a string or None")
        object.__setattr__(self, "report", frozen_report)

    def to_dict(self) -> dict[str, Any]:
        """Return a detached mutable mapping suitable for JSON serialization."""
        return json_report_dict(self.report)


@dataclass(frozen=True, slots=True)
class BookConversionResult:
    """Converted book content plus speech disposition and structured diagnostics."""

    book: Book
    speech: SpeechOutcome
    issues: tuple[SsmdAnalysisIssue, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.book, Book):
            raise TypeError("book must be a Book instance")
        if not isinstance(self.speech, SpeechOutcome):
            raise TypeError("speech must be a SpeechOutcome instance")
        if not isinstance(self.issues, tuple):
            raise TypeError("issues must be a tuple")


@dataclass(frozen=True, slots=True)
class SpeechFreezeResult:
    """Completed in-memory SSMD freeze with rendered sections and change evidence."""

    status: Literal["complete"]
    sections: Mapping[str, str]
    speech: SpeechOutcome
    changes: tuple[SsmdMappedChange, ...]
    issues: tuple[SsmdAnalysisIssue, ...]

    def __post_init__(self) -> None:
        if self.status != "complete" or self.speech.status != "complete":
            raise ValueError("a SpeechFreezeResult must represent a complete freeze")
        if not isinstance(self.sections, Mapping):
            raise TypeError("sections must be a mapping of section IDs to SSMD text")
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in self.sections.items()
        ):
            raise TypeError("sections must map string IDs to SSMD text")
        if not isinstance(self.changes, tuple) or not isinstance(self.issues, tuple):
            raise TypeError("changes and issues must be tuples")
        object.__setattr__(self, "sections", MappingProxyType(dict(self.sections)))


@dataclass(frozen=True, slots=True)
class SsmdChangeContext:
    """In-memory source/spoken context and SSMD mapping evidence for one change."""

    change: SsmdMappedChange
    language: str | None
    source_text: str
    spoken_text: str
    source_sentences: tuple[str, ...]
    spoken_sentences: tuple[str, ...]
    analysis_id: str | None


def report_mapping(value: Mapping[str, Any]) -> Mapping[str, object]:
    """Return a deeply immutable copy of a JSON-compatible report."""
    frozen = _freeze_json(value)
    if not isinstance(frozen, Mapping):
        raise TypeError("report must be a mapping")
    return frozen

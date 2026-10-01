"""Small source-neutral conversion models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .speech.models import SpeechPreparationReport


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Identity and media type for a converted source."""

    path: Path
    format: str
    media_type: str | None = None


@dataclass(slots=True)
class Section:
    """A normalized, ordered portion of a source document."""

    id: str
    markdown: str
    title: str | None = None
    level: int = 1
    source_ref: str | None = None


@dataclass(slots=True)
class Document:
    """Source-neutral document model passed between adapters and renderers."""

    source: SourceInfo
    sections: list[Section]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConversionResult:
    """Rendered SSMD with its normalized document and conversion warnings."""

    document: Document
    ssmd: str
    warnings: list[str] = field(default_factory=list)
    speech_report: SpeechPreparationReport | None = None


@dataclass(frozen=True, slots=True)
class BookChapter:
    """One source chapter represented as a standalone SSMD document."""

    id: str
    source_number: int
    title: str
    ssmd: str
    source_id: str | None = None
    href: str | None = None
    parent_id: str | None = None
    level: int = 1
    char_count: int | None = None
    diagnostics: tuple[Mapping[str, Any], ...] = ()
    bundle_path: str | None = None


@dataclass(frozen=True, slots=True)
class Book:
    """Chapter-aware representation of a source book."""

    source: SourceInfo
    metadata: Mapping[str, Any]
    chapters: tuple[BookChapter, ...]
    source_chapter_count: int | None = None
    source_name: str | None = None
    source_sha256: str | None = None
    speech_reports: Mapping[str, SpeechPreparationReport] = field(
        default_factory=dict,
        compare=False,
        repr=False,
    )


@dataclass(frozen=True, slots=True)
class BookInspectionChapter:
    """Inventory metadata for one source chapter."""

    id: str
    source_number: int
    title: str
    source_id: str | None = None
    href: str | None = None
    parent_id: str | None = None
    level: int = 1
    char_count: int | None = None
    diagnostics: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class BookInspection:
    """Source metadata and ordered chapter inventory for a book."""

    source: Path
    source_format: str
    metadata: Mapping[str, Any]
    chapters: tuple[BookInspectionChapter, ...]

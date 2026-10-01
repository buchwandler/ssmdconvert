"""Small source-neutral conversion models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Source format and provenance, with a path only when locally available."""

    format: str
    media_type: str | None = None
    path: Path | None = None
    name: str | None = None


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


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """Rendered SSMD and its normalized document."""

    document: Document
    ssmd: str


@dataclass(frozen=True, slots=True)
class BookChapter:
    """One source chapter represented as a standalone SSMD document."""

    id: str
    source_number: int
    title: str
    ssmd: str
    source_id: str | None = None
    href: str | None = None
    source_parent_id: str | None = None
    parent_id: str | None = None
    level: int = 1
    char_count: int | None = None
    diagnostics: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class Book:
    """Chapter-aware representation of a source book."""

    source: SourceInfo
    metadata: Mapping[str, Any]
    chapters: tuple[BookChapter, ...]
    source_sha256: str
    source_chapter_count: int | None = None


@dataclass(frozen=True, slots=True)
class BookInspectionChapter:
    """Inventory metadata for one source chapter."""

    id: str
    source_number: int
    title: str
    source_id: str | None = None
    href: str | None = None
    source_parent_id: str | None = None
    parent_id: str | None = None
    level: int = 1
    char_count: int | None = None
    diagnostics: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class BookInspection:
    """Source metadata and ordered chapter inventory for a book."""

    source: SourceInfo
    metadata: Mapping[str, Any]
    chapters: tuple[BookInspectionChapter, ...]

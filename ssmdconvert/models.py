"""Small source-neutral conversion models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceInfo:
    path: Path
    format: str
    media_type: str | None = None


@dataclass(slots=True)
class Section:
    id: str
    markdown: str
    title: str | None = None
    level: int = 1
    source_ref: str | None = None


@dataclass(slots=True)
class Document:
    source: SourceInfo
    sections: list[Section]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConversionResult:
    document: Document
    ssmd: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BookChapter:
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
    source: SourceInfo
    metadata: Mapping[str, Any]
    chapters: tuple[BookChapter, ...]
    source_chapter_count: int | None = None
    source_name: str | None = None
    source_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class BookInspectionChapter:
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
    source: Path
    source_format: str
    metadata: Mapping[str, Any]
    chapters: tuple[BookInspectionChapter, ...]

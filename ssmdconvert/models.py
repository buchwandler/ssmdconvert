"""Small source-neutral conversion models."""

from __future__ import annotations

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

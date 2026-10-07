"""SSMD-specific mapping models for source-neutral preparation changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ttsready import SpokenChange


@dataclass(frozen=True, slots=True)
class SsmdMappedChange:
    """A generic ttsready change enriched with SSMD source coordinates."""

    change: SpokenChange
    section_id: str
    section_index: int
    section_title: str | None
    paragraph_index: int
    is_title: bool
    clean_start: int | None
    clean_end: int | None
    raw_source_start: int | None
    raw_source_end: int | None
    mapping_status: Literal["exact", "synthetic", "protected", "unmappable"]
    materialization_status: Literal[
        "available",
        "already-authoritative",
        "not-materializable",
        "skipped",
        "applied",
    ]
    reason: str | None = None

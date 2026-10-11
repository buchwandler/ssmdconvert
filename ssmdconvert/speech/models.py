"""SSMD-specific mapping models for source-neutral preparation changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ttsready import SpokenChange

SpeechFreezeStatus = Literal["complete", "incomplete", "preserved"]
SpeechChangeDisposition = Literal["applied", "already-authoritative", "author-owned", "unresolved"]


@dataclass(frozen=True, slots=True)
class SpeechFreezeSummary:
    """Terminal counts for automatic text-changing speech decisions."""

    status: SpeechFreezeStatus
    changes_total: int
    applied: int
    already_authoritative: int
    author_owned: int
    unresolved: int

    @property
    def complete(self) -> bool:
        return (
            self.status == "complete"
            and self.unresolved == 0
            and self.changes_total == self.applied + self.already_authoritative + self.author_owned
        )


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
        "author-owned",
        "unresolved",
        "applied",
    ]
    reason: str | None = None

    @property
    def final_disposition(self) -> SpeechChangeDisposition:
        """Return the terminal or prospective outcome implied by this mapped change."""
        if self.materialization_status == "applied":
            return "applied"
        if self.materialization_status == "already-authoritative":
            return "already-authoritative"
        if self.materialization_status == "author-owned" or self.mapping_status == "protected":
            return "author-owned"
        if self.materialization_status == "available" and self.mapping_status == "exact":
            return "applied"
        return "unresolved"

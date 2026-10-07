"""SSMD-specific application models used by analysis and review workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ssmd import ParseStructureResult
from ttsready import PreparationResult

WorkspaceType = Literal["standalone", "zip", "directory"]
WorkspaceStatus = Literal["valid", "clean", "dirty"]
IssueSeverity = Literal["info", "warning", "error"]
IssueOrigin = Literal["ssmd", "ttsready", "mapping", "workspace", "projection"]


@dataclass(frozen=True, slots=True)
class LoadedSsmdSection:
    """One validated standalone SSMD chapter in source order."""

    id: str
    index: int
    title: str | None
    level: int
    ssmd: str
    source_number: int | None = None
    href: str | None = None
    parent_id: str | None = None
    source_ref: str | None = None
    chapter_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class LoadedSsmdSource:
    """Validated SSMD content plus application-level source/workspace identity."""

    path: Path
    kind: Literal["ssmd", "ssmdbook"]
    input_format: Literal["ssmd", "ssmdbook"]
    title: str | None
    metadata: Mapping[str, Any]
    sections: tuple[LoadedSsmdSection, ...]
    source_sha256: str
    content_fingerprint: str
    workspace_type: WorkspaceType
    workspace_status: WorkspaceStatus
    dirty_chapters: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SsmdTextContext:
    """Stable paragraph/title locator independent of file path and unit IDs."""

    id: str
    section_id: str
    section_index: int
    paragraph_index: int
    is_title: bool
    source_text: str
    clean_start: int | None
    clean_end: int | None
    unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SsmdUnitLocator:
    """SSMD clean-text coordinates for one generic ttsready unit."""

    unit_id: str
    section_id: str
    section_index: int
    paragraph_index: int
    run_index: int
    role: str
    is_title: bool
    clean_start: int | None
    clean_end: int | None


@dataclass(frozen=True, slots=True)
class SsmdAnalysisIssue:
    """Application-facing issue enriched with optional SSMD source coordinates."""

    code: str
    severity: IssueSeverity
    section_id: str | None
    paragraph_index: int | None
    clean_start: int | None
    clean_end: int | None
    raw_source_start: int | None
    raw_source_end: int | None
    message: str
    origin: IssueOrigin


@dataclass(frozen=True, slots=True)
class SsmdAnalysis:
    """In-memory analysis of exactly the selected SSMD sections."""

    source: LoadedSsmdSource
    sections: tuple[LoadedSsmdSection, ...]
    structures: Mapping[str, ParseStructureResult]
    unit_locators: Mapping[str, SsmdUnitLocator]
    contexts: tuple[SsmdTextContext, ...]
    preparation: PreparationResult
    issues: tuple[SsmdAnalysisIssue, ...]
    requested_language: str | None
    effective_languages: tuple[str, ...]
    stored_sequence_fallback: str | None
    effective_sequence_fallback: Literal["preserve", "spell"]


@dataclass(frozen=True, slots=True)
class SourceReport:
    path: str
    input_format: str
    title: str | None
    source_sha256: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class ConfigurationReport:
    metadata_language: str | None
    requested_language: str | None
    effective_languages: tuple[str, ...]
    selected_sections: tuple[str, ...]
    stored_sequence_fallback: str | None
    effective_sequence_fallback: str
    include_titles: bool
    max_paragraph_chars: int | None
    output_layout: str


@dataclass(frozen=True, slots=True)
class WorkspaceReport:
    type: WorkspaceType
    status: WorkspaceStatus
    dirty_chapters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticsReport:
    portable_metadata: Mapping[str, Any]
    generic_txt_warning: str


@dataclass(frozen=True, slots=True)
class ReproducibilityReport:
    source_sha256: str
    content_fingerprint: str
    prepared_output_sha256: str
    analysis_id: str | None
    tool_versions: Mapping[str, str]
    normalization_profile_sha256: str
    override_profile_sha256: str
    runtime_fingerprint: str


@dataclass(frozen=True, slots=True)
class SectionAnalysisStats:
    section_id: str
    index: int
    title: str | None
    level: int
    input_chars: int
    source_paragraphs: int
    prepared_units: int
    prepared_paragraphs: int
    changes: int
    output_chars: int
    chapter_sha256: str | None


@dataclass(frozen=True, slots=True)
class ProjectionStats:
    source_prepared_items: int
    split_source_items: int
    added_split_parts: int
    max_prepared_paragraph_chars: int
    output_chars: int
    output_lines: int
    output_files: int
    output_layout: str
    prepared_output_sha256: str


@dataclass(frozen=True, slots=True)
class SsmdAnalysisReport:
    source: SourceReport
    configuration: ConfigurationReport
    workspace: WorkspaceReport
    semantics: SemanticsReport
    reproducibility: ReproducibilityReport
    sections: tuple[SectionAnalysisStats, ...]
    preparation: PreparationResult
    mapped_changes: tuple[Any, ...]
    issues: tuple[SsmdAnalysisIssue, ...]
    projection: ProjectionStats
    contexts: tuple[SsmdTextContext, ...]
    analysis_id: str | None = None
    schema: str = "ssmdconvert.analysis-report.v1"


def select_sections(
    source: LoadedSsmdSource, chapters: str | None = "all"
) -> tuple[LoadedSsmdSection, ...]:
    """Select sections using source numbers while preserving loaded source order."""
    from ..chapter_selection import parse_chapter_selection

    available = tuple(
        section.source_number if section.source_number is not None else section.index
        for section in source.sections
    )
    selected = set(parse_chapter_selection(chapters, available_numbers=available))
    return tuple(
        section
        for section, number in zip(source.sections, available, strict=True)
        if number in selected
    )

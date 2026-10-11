"""Shared SSMD analysis-to-materialization orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..analysis.models import SsmdAnalysis, SsmdAnalysisIssue
from ..errors import MaterializationError
from .mapping import map_analysis_changes
from .materialize import materialize_substitutions
from .models import SpeechFreezeSummary, SsmdMappedChange


@dataclass(frozen=True, slots=True)
class AnalysisMaterialization:
    """Validated new SSMD text for selected sections and final change dispositions."""

    section_ssmd: Mapping[str, str]
    changes: tuple[SsmdMappedChange, ...]
    issues: tuple[SsmdAnalysisIssue, ...]
    summary: SpeechFreezeSummary


def summarize_changes(changes: tuple[SsmdMappedChange, ...]) -> SpeechFreezeSummary:
    applied = sum(change.final_disposition == "applied" for change in changes)
    already_authoritative = sum(
        change.final_disposition == "already-authoritative" for change in changes
    )
    author_owned = sum(change.final_disposition == "author-owned" for change in changes)
    unresolved = sum(change.final_disposition == "unresolved" for change in changes)
    complete = unresolved == 0 and len(changes) == applied + already_authoritative + author_owned
    return SpeechFreezeSummary(
        status="complete" if complete else "incomplete",
        changes_total=len(changes),
        applied=applied,
        already_authoritative=already_authoritative,
        author_owned=author_owned,
        unresolved=unresolved,
    )


def materialize_analysis(analysis: SsmdAnalysis) -> AnalysisMaterialization:
    """Freeze current ttsready changes as exact, idempotent SSMD ``sub`` annotations."""
    if any(issue.code == "analysis.language_unresolved" for issue in analysis.issues):
        raise MaterializationError(
            "cannot materialize SSMD speech changes while an effective language is unresolved"
        )
    if not analysis.coverage.complete:
        coverage = analysis.coverage
        raise MaterializationError(
            "cannot freeze speech semantics because narratable-text coverage is incomplete "
            f"({coverage.covered_contexts}/{coverage.narratable_contexts} contexts covered; "
            f"uncovered={len(coverage.uncovered_context_ids)}, "
            f"duplicates={len(coverage.duplicate_unit_ids)}, "
            f"orphaned={len(coverage.orphan_unit_ids)})"
        )
    mapped = map_analysis_changes(analysis)
    section_ssmd: dict[str, str] = {}
    final_changes: list[SsmdMappedChange] = []
    issues: list[SsmdAnalysisIssue] = []
    for section in analysis.sections:
        result = materialize_substitutions(
            section.ssmd,
            analysis.structures[section.id],
            (change for change in mapped if change.section_id == section.id),
        )
        section_ssmd[section.id] = result.ssmd
        final_changes.extend(result.changes)
        issues.extend(result.issues)
    completed_changes = tuple(final_changes)
    summary = summarize_changes(completed_changes)
    if not summary.complete:
        raise MaterializationError(
            "cannot complete speech freeze because automatic text changes remain unresolved "
            f"({summary.unresolved} unresolved of {summary.changes_total})"
        )
    return AnalysisMaterialization(
        section_ssmd=MappingProxyType(section_ssmd),
        changes=completed_changes,
        issues=tuple(issues),
        summary=summary,
    )

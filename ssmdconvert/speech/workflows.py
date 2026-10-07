"""Shared SSMD analysis-to-materialization orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..analysis.models import SsmdAnalysis, SsmdAnalysisIssue
from ..errors import MaterializationError
from .mapping import map_analysis_changes
from .materialize import materialize_substitutions
from .models import SsmdMappedChange


@dataclass(frozen=True, slots=True)
class AnalysisMaterialization:
    """Validated new SSMD text for selected sections and final change dispositions."""

    section_ssmd: Mapping[str, str]
    changes: tuple[SsmdMappedChange, ...]
    issues: tuple[SsmdAnalysisIssue, ...]


def materialize_analysis(analysis: SsmdAnalysis) -> AnalysisMaterialization:
    """Freeze current ttsready changes as exact, idempotent SSMD ``sub`` annotations."""
    if any(issue.code == "analysis.language_unresolved" for issue in analysis.issues):
        raise MaterializationError(
            "cannot materialize SSMD speech changes while an effective language is unresolved"
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
    return AnalysisMaterialization(
        section_ssmd=MappingProxyType(section_ssmd),
        changes=tuple(final_changes),
        issues=tuple(issues),
    )

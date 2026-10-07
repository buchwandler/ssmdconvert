"""Focused speech-audit view over the canonical SSMD analysis pipeline."""

from __future__ import annotations

from pathlib import Path

from ..analysis.models import LoadedSsmdSource, SsmdAnalysisReport
from ..analysis.prepare import analyze_ssmd_source
from ..analysis.projection import project_txt
from ..analysis.reporting import build_analysis_report


def audit_ssmd(
    source: str | Path | LoadedSsmdSource,
    *,
    chapters: str | None = "all",
    language: str | None = None,
    sequence_fallback_mode: str | None = None,
    include_titles: bool = True,
) -> SsmdAnalysisReport:
    """Run the same ttsready preparation and SSMD mapping used by ``report``."""
    analysis = analyze_ssmd_source(
        source,
        chapters=chapters,
        language=language,
        sequence_fallback_mode=sequence_fallback_mode,
        include_titles=include_titles,
    )
    projection = project_txt(analysis, include_titles=include_titles)
    return build_analysis_report(
        analysis,
        projection,
        include_titles=include_titles,
    )

"""Context-bearing failures for incomplete speech-freeze attempts."""

from __future__ import annotations

from dataclasses import replace

from ..analysis.models import SsmdAnalysis
from ..errors import MaterializationError
from .mapping import map_analysis_changes
from .models import SpeechFreezeSummary, SsmdMappedChange
from .workflows import summarize_changes


class SpeechFreezeFailure(MaterializationError):
    """A failed freeze retaining its analysis and reviewable incomplete dispositions."""

    def __init__(
        self,
        message: str,
        *,
        analysis: SsmdAnalysis,
        changes: tuple[SsmdMappedChange, ...],
        summary: SpeechFreezeSummary,
    ) -> None:
        super().__init__(message)
        self.analysis = analysis
        self.changes = changes
        self.summary = summary


def make_speech_freeze_failure(analysis: SsmdAnalysis, message: str) -> SpeechFreezeFailure:
    """Mark unwritten automatic changes unresolved and retain an incomplete summary."""
    try:
        mapped = map_analysis_changes(analysis)
    except Exception:
        mapped = ()
    changes = tuple(
        replace(change, materialization_status="unresolved", reason=message)
        if change.materialization_status == "available"
        else change
        for change in mapped
    )
    summary = replace(summarize_changes(changes), status="incomplete")
    return SpeechFreezeFailure(
        message,
        analysis=analysis,
        changes=changes,
        summary=summary,
    )

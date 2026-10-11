"""Versioned machine-readable reports for SSMD speech freezes."""

from __future__ import annotations

from typing import Any

from ..analysis.models import SsmdAnalysis
from .models import SpeechFreezeSummary, SsmdMappedChange
from .provenance import build_speech_provenance

_REPORT_FORMAT = "ssmdconvert-speech-freeze-report"
_REPORT_VERSION = 1


def build_speech_freeze_report(
    analysis: SsmdAnalysis,
    changes: tuple[SsmdMappedChange, ...],
    summary: SpeechFreezeSummary,
    *,
    failure: str | None = None,
) -> dict[str, Any]:
    """Return a stable JSON-compatible freeze report, including incomplete outcomes."""
    if summary.status not in {"complete", "incomplete"}:
        raise ValueError(f"unsupported freeze report status: {summary.status!r}")
    provenance = build_speech_provenance(analysis, status=summary.status)
    coverage = analysis.coverage
    report = {
        "format": _REPORT_FORMAT,
        "version": _REPORT_VERSION,
        "status": summary.status,
        "complete": summary.complete,
        "source_sha256": analysis.source.source_sha256,
        "provenance": provenance,
        "coverage": {
            "complete": coverage.complete,
            "narratable_contexts": coverage.narratable_contexts,
            "covered_contexts": coverage.covered_contexts,
            "uncovered_context_ids": list(coverage.uncovered_context_ids),
            "duplicate_unit_ids": list(coverage.duplicate_unit_ids),
            "orphan_unit_ids": list(coverage.orphan_unit_ids),
            "protected_units": coverage.protected_units,
            "excluded_title_contexts": coverage.excluded_title_contexts,
        },
        "summary": {
            "changes_total": summary.changes_total,
            "applied": summary.applied,
            "already_authoritative": summary.already_authoritative,
            "author_owned": summary.author_owned,
            "unresolved": summary.unresolved,
        },
        "changes": [_change_record(change) for change in changes],
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity,
                "section_id": issue.section_id,
                "paragraph_index": issue.paragraph_index,
                "message": issue.message,
            }
            for issue in analysis.issues
        ],
    }
    if failure is not None:
        report["failure"] = failure
    return report


def build_preserved_speech_report(source_sha256: str) -> dict[str, Any]:
    """Report structural-only conversion without claiming a completed freeze."""
    return {
        "format": _REPORT_FORMAT,
        "version": _REPORT_VERSION,
        "status": "preserved",
        "complete": False,
        "source_sha256": source_sha256,
        "provenance": {
            "status": "preserved",
            "owner": "ssmdconvert",
            "source_sha256": source_sha256,
        },
        "coverage": None,
        "summary": {
            "changes_total": 0,
            "applied": 0,
            "already_authoritative": 0,
            "author_owned": 0,
            "unresolved": 0,
        },
        "changes": [],
        "issues": [],
    }

def _change_record(change: SsmdMappedChange) -> dict[str, Any]:
    return {
        "id": change.change.id,
        "section_id": change.section_id,
        "section_index": change.section_index,
        "section_title": change.section_title,
        "paragraph_index": change.paragraph_index,
        "is_title": change.is_title,
        "source": change.change.source,
        "spoken": change.change.replacement,
        "kind": change.change.kind,
        "rule": change.change.rule,
        "language": change.change.language,
        "mapping_status": change.mapping_status,
        "materialization_status": change.materialization_status,
        "final_disposition": change.final_disposition,
        "location": {
            "clean_start": change.clean_start,
            "clean_end": change.clean_end,
            "raw_source_start": change.raw_source_start,
            "raw_source_end": change.raw_source_end,
        },
        "reason": change.reason,
    }

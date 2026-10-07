"""Verified SSMD substitution write-back for mapped ttsready changes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

from ssmd import ParseStructureResult, parse_structure

from ..analysis.models import SsmdAnalysisIssue
from ..errors import MappingError, MaterializationError
from ..render import validate_ssmd_document
from .escaping import format_sub_annotation
from .models import SsmdMappedChange


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    """New SSMD text, final change dispositions, and mapping diagnostics."""

    ssmd: str
    changes: tuple[SsmdMappedChange, ...]
    issues: tuple[SsmdAnalysisIssue, ...]


def _substitution_count(structure: ParseStructureResult) -> int:
    return sum("sub" in annotation.attrs for annotation in structure.annotations)


def _issue(
    change: SsmdMappedChange,
    message: str,
    *,
    severity: Literal["warning", "error"],
) -> SsmdAnalysisIssue:
    return SsmdAnalysisIssue(
        code="mapping.unsafe_materialization",
        severity=severity,
        section_id=change.section_id,
        paragraph_index=change.paragraph_index,
        clean_start=change.clean_start,
        clean_end=change.clean_end,
        raw_source_start=change.raw_source_start,
        raw_source_end=change.raw_source_end,
        message=message,
        origin="mapping",
    )


def materialize_substitutions(
    source: str,
    structure: ParseStructureResult,
    changes: Iterable[SsmdMappedChange],
    *,
    strict: bool = True,
) -> MaterializationResult:
    """Apply only exact, non-overlapping changes and prove the SSMD invariants."""
    ordered = tuple(changes)
    issues: list[SsmdAnalysisIssue] = []
    eligible: list[SsmdMappedChange] = []
    for change in ordered:
        if (
            change.mapping_status == "exact"
            and change.materialization_status == "available"
            and change.raw_source_start is not None
            and change.raw_source_end is not None
        ):
            eligible.append(change)
        elif change.mapping_status == "unmappable":
            message = change.reason or "Automatic change has no exact SSMD source mapping."
            issues.append(_issue(change, message, severity="error" if strict else "warning"))
            if strict:
                raise MaterializationError(
                    f"cannot safely materialize change {change.change.id}: {message}"
                )
        elif change.materialization_status == "available":
            raise MaterializationError(
                f"available change {change.change.id} is missing an exact raw source range"
            )

    by_start = sorted(
        eligible,
        key=lambda item: (item.raw_source_start or 0, item.raw_source_end or 0),
    )
    for previous, current in zip(by_start, by_start[1:], strict=False):
        assert previous.raw_source_end is not None and current.raw_source_start is not None
        if previous.raw_source_end > current.raw_source_start:
            raise MaterializationError(
                f"mapped SSMD substitutions overlap: {previous.change.id} and {current.change.id}"
            )

    result = source
    for change in sorted(
        eligible,
        key=lambda item: item.raw_source_start if item.raw_source_start is not None else -1,
        reverse=True,
    ):
        start = change.raw_source_start
        end = change.raw_source_end
        assert start is not None and end is not None
        if not (0 <= start < end <= len(result)):
            raise MappingError(f"raw SSMD source span is invalid for change {change.change.id}")
        if result[start:end] != change.change.source:
            raise MappingError(
                f"raw SSMD source changed before materialization of {change.change.id}"
            )
        try:
            annotation = format_sub_annotation(change.change.source, change.change.replacement)
        except ValueError as exc:
            raise MaterializationError(
                f"could not format SSMD substitution for {change.change.id}: {exc}"
            ) from exc
        result = result[:start] + annotation + result[end:]

    applied_ids = {change.change.id for change in eligible}
    final_changes = tuple(
        replace(change, materialization_status="applied")
        if change.change.id in applied_ids
        else change
        for change in ordered
    )
    if not eligible:
        return MaterializationResult(result, final_changes, tuple(issues))

    try:
        validate_ssmd_document(result)
        after = parse_structure(result, dialect="0.9", normalize=False)
    except Exception as exc:
        raise MaterializationError(f"materialized SSMD failed validation: {exc}") from exc
    if after.clean_text != structure.clean_text:
        raise MaterializationError("materialized substitutions changed visible SSMD text")
    inserted = _substitution_count(after) - _substitution_count(structure)
    if inserted != len(eligible):
        raise MaterializationError(
            "materialized substitutions did not create exactly one sub annotation per change"
        )
    return MaterializationResult(result, final_changes, tuple(issues))

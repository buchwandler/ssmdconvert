"""Fail-closed mapping from ttsready changes to parser-owned SSMD source spans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from ssmd import ParseStructureResult

from ..analysis.models import SsmdAnalysis, SsmdAnalysisIssue
from ..errors import MappingError
from .models import SsmdMappedChange


def source_range_for_clean_span(
    source: str,
    structure: ParseStructureResult,
    clean_start: int,
    clean_end: int,
    *,
    expected_text: str,
) -> tuple[int, int] | None:
    """Map one complete clean-text range only through a proven one-to-one leaf."""
    clean_text = structure.clean_text
    if not (0 <= clean_start < clean_end <= len(clean_text)):
        return None
    if clean_text[clean_start:clean_end] != expected_text:
        return None

    for span in structure.text_spans:
        if not (span.char_start <= clean_start and clean_end <= span.char_end):
            continue
        if not (
            0 <= span.char_start <= span.char_end <= len(clean_text)
            and 0 <= span.source_start <= span.source_end <= len(source)
        ):
            return None
        clean_leaf = clean_text[span.char_start : span.char_end]
        raw_leaf = source[span.source_start : span.source_end]
        if len(clean_leaf) != len(raw_leaf) or clean_leaf != raw_leaf:
            return None
        relative_start = clean_start - span.char_start
        relative_end = clean_end - span.char_start
        raw_start = span.source_start + relative_start
        raw_end = span.source_start + relative_end
        if source[raw_start:raw_end] != expected_text:
            return None
        return raw_start, raw_end
    return None


def _has_provider_semantics(attrs: Mapping[str, object]) -> bool:
    semantic_keys = {"as", "say-as", "ph", "phoneme", "phonemes", "pronunciation", "ipa"}
    if semantic_keys.intersection(attrs):
        return True
    return any(key.startswith(("tts-", "tts:", "provider-", "provider:")) for key in attrs)


def _annotation_disposition(
    structure: ParseStructureResult,
    clean_start: int,
    clean_end: int,
    replacement: str,
) -> tuple[bool, bool]:
    annotations = structure.effective_annotations or structure.annotations
    already_authoritative = False
    protected = False
    for annotation in annotations:
        if not (annotation.char_start < clean_end and clean_start < annotation.char_end):
            continue
        sub = annotation.attrs.get("sub")
        if (
            annotation.char_start == clean_start
            and annotation.char_end == clean_end
            and isinstance(sub, str)
            and sub == replacement
        ):
            already_authoritative = True
        if _has_provider_semantics(annotation.attrs):
            protected = True
    return already_authoritative, protected


def map_analysis_changes(analysis: SsmdAnalysis) -> tuple[SsmdMappedChange, ...]:
    """Enrich generic changes without modifying their IDs or provenance."""
    section_by_id = {section.id: section for section in analysis.sections}
    mapped: list[SsmdMappedChange] = []
    for change in analysis.preparation.changes:
        locator = analysis.unit_locators.get(change.unit_id)
        if locator is None:
            raise MappingError(f"No SSMD locator exists for ttsready unit {change.unit_id!r}")
        section = section_by_id.get(locator.section_id)
        if section is None:
            raise MappingError(f"Selected analysis is missing section {locator.section_id!r}")
        if locator.is_title or locator.clean_start is None or locator.clean_end is None:
            mapped.append(
                SsmdMappedChange(
                    change=change,
                    section_id=section.id,
                    section_index=section.index,
                    section_title=section.title,
                    paragraph_index=locator.paragraph_index,
                    is_title=locator.is_title,
                    clean_start=None,
                    clean_end=None,
                    raw_source_start=None,
                    raw_source_end=None,
                    mapping_status="synthetic",
                    materialization_status="not-materializable",
                    reason="Synthetic chapter title has no raw SSMD body range.",
                )
            )
            continue

        clean_start = locator.clean_start + change.source_start
        clean_end = locator.clean_start + change.source_end
        structure = analysis.structures[section.id]
        source_range = source_range_for_clean_span(
            section.ssmd,
            structure,
            clean_start,
            clean_end,
            expected_text=change.source,
        )
        already_authoritative, protected = _annotation_disposition(
            structure,
            clean_start,
            clean_end,
            change.replacement,
        )
        if source_range is None:
            mapped.append(
                SsmdMappedChange(
                    change=change,
                    section_id=section.id,
                    section_index=section.index,
                    section_title=section.title,
                    paragraph_index=locator.paragraph_index,
                    is_title=False,
                    clean_start=clean_start,
                    clean_end=clean_end,
                    raw_source_start=None,
                    raw_source_end=None,
                    mapping_status="unmappable",
                    materialization_status="not-materializable",
                    reason=(
                        "No parser-owned one-to-one text span proves the complete source slice."
                    ),
                )
            )
            continue

        raw_start, raw_end = source_range
        status: Literal["already-authoritative", "not-materializable", "available"]
        if already_authoritative:
            status = "already-authoritative"
            reason = "The same spoken form is already specified by an SSMD sub annotation."
        elif protected:
            status = "not-materializable"
            reason = "The source range has authoritative SSMD delivery semantics."
        else:
            status = "available"
            reason = None
        mapped.append(
            SsmdMappedChange(
                change=change,
                section_id=section.id,
                section_index=section.index,
                section_title=section.title,
                paragraph_index=locator.paragraph_index,
                is_title=False,
                clean_start=clean_start,
                clean_end=clean_end,
                raw_source_start=raw_start,
                raw_source_end=raw_end,
                mapping_status="protected" if protected else "exact",
                materialization_status=status,
                reason=reason,
            )
        )
    return tuple(mapped)


def mapping_issues(changes: tuple[SsmdMappedChange, ...]) -> tuple[SsmdAnalysisIssue, ...]:
    """Convert fail-closed mapping results into app-level diagnostics."""
    return tuple(
        SsmdAnalysisIssue(
            code="mapping.unmappable_change",
            severity="warning",
            section_id=change.section_id,
            paragraph_index=change.paragraph_index,
            clean_start=change.clean_start,
            clean_end=change.clean_end,
            raw_source_start=change.raw_source_start,
            raw_source_end=change.raw_source_end,
            message=change.reason or "The automatic change cannot be mapped to SSMD source.",
            origin="mapping",
        )
        for change in changes
        if change.mapping_status == "unmappable"
    )

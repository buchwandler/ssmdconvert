"""Application orchestration around ttsready's source-neutral preparation API."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import ttsready

from ..errors import AnalysisError
from ..linguistics import LinguisticModelSelection, LinguisticResourcePool, LinguisticsConfig
from ..policy import DEFAULT_SEQUENCE_FALLBACK_MODE, validate_sequence_fallback_mode
from ..progress import ProgressCallback, ProgressCallbackFailure, emit_progress
from .models import (
    LoadedSsmdSource,
    SsmdAnalysis,
    SsmdAnalysisIssue,
    SsmdUnitLocator,
    select_sections,
)
from .source import load_ssmd_source
from .units import UnitExtraction, extract_units


def _stored_sequence_fallback(
    analysis_input: UnitExtraction,
    source: LoadedSsmdSource,
    *,
    requested: str | None,
) -> tuple[str | None, Literal["preserve", "spell"], tuple[SsmdAnalysisIssue, ...]]:
    stored: list[str] = []
    for value in (source.metadata.get("sequence_fallback_mode"),):
        if isinstance(value, str) and value:
            stored.append(value)
    for structure in analysis_input.structures.values():
        value = structure.header.get("sequence_fallback_mode")
        if isinstance(value, str) and value:
            stored.append(value)

    distinct = tuple(dict.fromkeys(stored))
    stored_value = distinct[0] if len(distinct) == 1 else (distinct[0] if distinct else None)
    issues: list[SsmdAnalysisIssue] = []
    if len(distinct) > 1 and requested is None:
        issues.append(
            SsmdAnalysisIssue(
                code="analysis.sequence_fallback_conflict",
                severity="warning",
                section_id=None,
                paragraph_index=None,
                clean_start=None,
                clean_end=None,
                raw_source_start=None,
                raw_source_end=None,
                message=(
                    "Selected sections contain different stored sequence fallback modes; "
                    "the first stored mode is used."
                ),
                origin="ssmd",
            )
        )
    candidate = requested or stored_value or DEFAULT_SEQUENCE_FALLBACK_MODE
    try:
        effective = validate_sequence_fallback_mode(candidate)
    except ValueError as exc:
        issues.append(
            SsmdAnalysisIssue(
                code="analysis.sequence_fallback_invalid",
                severity="error",
                section_id=None,
                paragraph_index=None,
                clean_start=None,
                clean_end=None,
                raw_source_start=None,
                raw_source_end=None,
                message=f"Invalid stored sequence fallback mode {candidate!r}: {exc}",
                origin="ssmd",
            )
        )
        effective = DEFAULT_SEQUENCE_FALLBACK_MODE
    return stored_value, effective, tuple(issues)


def _pronunciation_overrides(
    pronunciations: Mapping[str, str],
) -> tuple[ttsready.SpeechOverride, ...]:
    result: list[ttsready.SpeechOverride] = []
    for surface, spoken in sorted(pronunciations.items()):
        if not isinstance(surface, str) or not surface.strip() or surface != surface.strip():
            raise ValueError("pronunciation keys must be non-empty strings without edge whitespace")
        if not isinstance(spoken, str) or not spoken.strip():
            raise ValueError("pronunciation values must be non-empty strings")
        result.append(
            ttsready.SpeechOverride(
                surface=surface,
                spoken=spoken,
                match="word",
                case_sensitive=True,
                provenance={"origin": "ssmdconvert", "source": "pronunciation-profile"},
            )
        )
    return tuple(result)


def _unit_locators(extraction: UnitExtraction) -> dict[str, SsmdUnitLocator]:
    locators: dict[str, SsmdUnitLocator] = {}
    for unit in extraction.units:
        metadata = unit.metadata
        section_id = metadata.get("section_id")
        section_index = metadata.get("section_index")
        paragraph_index = metadata.get("paragraph_index")
        run_index = metadata.get("run_index")
        role = metadata.get("role")
        if (
            not isinstance(section_id, str)
            or not isinstance(section_index, int)
            or not isinstance(paragraph_index, int)
            or not isinstance(run_index, int)
            or not isinstance(role, str)
        ):
            raise AnalysisError(f"analysis unit {unit.id!r} is missing its SSMD locator")
        clean_start = metadata.get("clean_start")
        clean_end = metadata.get("clean_end")
        locators[unit.id] = SsmdUnitLocator(
            unit_id=unit.id,
            section_id=section_id,
            section_index=section_index,
            paragraph_index=paragraph_index,
            run_index=run_index,
            role=role,
            is_title=metadata.get("is_title") is True,
            clean_start=clean_start if isinstance(clean_start, int) else None,
            clean_end=clean_end if isinstance(clean_end, int) else None,
        )
    return locators


def _resolve_linguistics(
    units: tuple[ttsready.TextUnit, ...],
    config: LinguisticsConfig,
    pool: LinguisticResourcePool,
    on_progress: ProgressCallback | None,
) -> dict[str, LinguisticModelSelection]:
    languages = tuple(dict.fromkeys(unit.language for unit in units))
    emit_progress(
        on_progress,
        "phase.started",
        "linguistics.resolve",
        completed=0,
        total=len(languages),
    )
    selections = {
        language: pool.resolve(language, config, on_progress=on_progress) for language in languages
    }
    fallbacks = {
        language: selection.fallback_reason
        for language, selection in selections.items()
        if selection.fallback_reason is not None
    }
    emit_progress(
        on_progress,
        "phase.completed",
        "linguistics.resolve",
        completed=len(languages),
        total=len(languages),
        details={
            "fallbacks": fallbacks,
            "models": {
                language: selection.cache_identity() for language, selection in selections.items()
            },
        },
    )
    return selections


def _enrich_linguistic_units(
    units: tuple[ttsready.TextUnit, ...],
    selections: Mapping[str, LinguisticModelSelection],
    pool: LinguisticResourcePool,
    on_progress: ProgressCallback | None,
    *,
    completed_offset: int = 0,
    progress_total: int | None = None,
) -> tuple[ttsready.TextUnit, ...]:
    total = progress_total if progress_total is not None else len(units)
    emit_progress(
        on_progress,
        "phase.started",
        "linguistics.enrichment",
        completed=completed_offset,
        total=total,
    )
    enriched: list[ttsready.TextUnit] = []
    for index, unit in enumerate(units):
        selection = selections[unit.language]
        if selection.provider == "spacy":
            emit_progress(
                on_progress,
                "unit.started",
                "linguistics.enrichment",
                completed=completed_offset + index,
                total=total,
                unit_id=unit.id,
                language=unit.language,
                provider=selection.provider,
                model=selection.model,
            )
            tokens = pool.analyze_text(unit.text, selection, on_progress=on_progress)
            unit = replace(unit, linguistic_tokens=tokens)
            emit_progress(
                on_progress,
                "unit.completed",
                "linguistics.enrichment",
                completed=completed_offset + index + 1,
                total=total,
                unit_id=unit.id,
                language=unit.language,
                provider=selection.provider,
                model=selection.model,
            )
        enriched.append(unit)
    emit_progress(
        on_progress,
        "phase.completed",
        "linguistics.enrichment",
        completed=completed_offset + len(units),
        total=total,
    )
    return tuple(enriched)


def _preparation_progress(
    callback: ProgressCallback | None,
    *,
    completed_offset: int = 0,
    progress_total: int | None = None,
) -> Callable[[Any], None] | None:
    if callback is None:
        return None

    def forward(event: Any) -> None:
        try:
            emit_progress(
                callback,
                event.kind,
                "speech.prepare",
                completed=completed_offset + event.completed,
                total=progress_total if progress_total is not None else event.total,
                unit_id=event.unit_id,
                language=event.language,
                details={"role": event.role},
            )
        except BaseException as exc:
            raise ProgressCallbackFailure(exc) from exc

    return forward


def analyze_ssmd_source(
    source: str | Path | LoadedSsmdSource,
    *,
    chapters: str | None = "all",
    language: str | None = None,
    fallback_language: str | None = None,
    sequence_fallback_mode: str | None = None,
    include_titles: bool = True,
    profile: ttsready.PreparationProfile | None = None,
    overrides: tuple[ttsready.SpeechOverride, ...] = (),
    pronunciations: Mapping[str, str] | None = None,
    unit_extraction: UnitExtraction | None = None,
    prepared_result: ttsready.PreparationResult | None = None,
    linguistics: LinguisticsConfig | None = None,
    on_progress: ProgressCallback | None = None,
) -> SsmdAnalysis:
    """Analyze the selected SSMD sections through public ttsready 0.2 APIs."""
    emit_progress(on_progress, "phase.started", "analysis")
    loaded = source if isinstance(source, LoadedSsmdSource) else load_ssmd_source(source)

    selected = select_sections(loaded, chapters)
    extracted = unit_extraction or extract_units(
        loaded,
        selected,
        language=language,
        fallback_language=fallback_language,
        include_titles=include_titles,
    )
    if tuple(extracted.structures) != tuple(section.id for section in selected):
        raise AnalysisError("pre-extracted SSMD units do not match the selected sections")
    selected_linguistics = linguistics or LinguisticsConfig()
    if not isinstance(selected_linguistics, LinguisticsConfig):
        raise TypeError("linguistics must be a LinguisticsConfig")
    stored_fallback, effective_fallback, fallback_issues = _stored_sequence_fallback(
        extracted,
        loaded,
        requested=sequence_fallback_mode,
    )
    active_profile = replace(
        profile or ttsready.PreparationProfile(),
        sequence_fallback_mode=effective_fallback,
    )
    all_overrides = (
        *extracted.overrides,
        *overrides,
        *_pronunciation_overrides(pronunciations or {}),
    )
    if prepared_result is None:
        pool = LinguisticResourcePool()
        selections = _resolve_linguistics(extracted.units, selected_linguistics, pool, on_progress)
        prepared_units = _enrich_linguistic_units(extracted.units, selections, pool, on_progress)
        emit_progress(
            on_progress,
            "phase.started",
            "speech.prepare",
            completed=0,
            total=len(prepared_units),
        )
        try:
            preparation = ttsready.prepare_units(
                prepared_units,
                overrides=all_overrides,
                profile=active_profile,
                strict=False,
                on_progress=_preparation_progress(on_progress, progress_total=len(prepared_units)),
            )
        except ProgressCallbackFailure as exc:
            raise exc.original from exc
        except Exception as exc:
            raise AnalysisError(
                f"ttsready could not prepare the selected SSMD text: {exc}"
            ) from exc
        emit_progress(
            on_progress,
            "phase.completed",
            "speech.prepare",
            completed=len(prepared_units),
            total=len(prepared_units),
        )
    else:
        expected_unit_ids = tuple(unit.id for unit in extracted.units)
        actual_unit_ids = tuple(unit.unit_id for unit in prepared_result.units)
        if expected_unit_ids != actual_unit_ids:
            raise AnalysisError("cached ttsready units do not match the selected SSMD units")
        if prepared_result.profile_fingerprint != ttsready.profile_fingerprint(active_profile):
            raise AnalysisError("cached ttsready profile fingerprint does not match the request")
        if prepared_result.override_fingerprint != ttsready.override_fingerprint(all_overrides):
            raise AnalysisError("cached ttsready override fingerprint does not match the request")
        if prepared_result.runtime_fingerprint != ttsready.runtime_fingerprint():
            raise AnalysisError(
                "cached ttsready runtime fingerprint does not match the current runtime"
            )
        preparation = prepared_result

    issues = [*extracted.issues, *fallback_issues]
    if loaded.workspace_status == "dirty":
        issues.append(
            SsmdAnalysisIssue(
                code="workspace.dirty",
                severity="warning",
                section_id=None,
                paragraph_index=None,
                clean_start=None,
                clean_end=None,
                raw_source_start=None,
                raw_source_end=None,
                message=(
                    f"Directory workspace has edited chapters: {', '.join(loaded.dirty_chapters)}"
                ),
                origin="workspace",
            )
        )
    unit_metadata = {unit.id: unit.metadata for unit in extracted.units}
    for issue in preparation.issues:
        metadata = unit_metadata.get(issue.unit_id, {})
        clean_base = metadata.get("clean_start")
        start = issue.source_start
        end = issue.source_end
        issues.append(
            SsmdAnalysisIssue(
                code=issue.code,
                severity=issue.severity,
                section_id=metadata.get("section_id"),
                paragraph_index=metadata.get("paragraph_index"),
                clean_start=(
                    clean_base + start
                    if isinstance(clean_base, int) and start is not None
                    else None
                ),
                clean_end=(
                    clean_base + end if isinstance(clean_base, int) and end is not None else None
                ),
                raw_source_start=None,
                raw_source_end=None,
                message=issue.message,
                origin="ttsready",
            )
        )

    unit_locators = _unit_locators(extracted)
    analysis = SsmdAnalysis(
        source=loaded,
        sections=selected,
        structures=extracted.structures,
        unit_locators=unit_locators,
        contexts=extracted.contexts,
        preparation=preparation,
        issues=tuple(issues),
        requested_language=language,
        effective_languages=extracted.effective_languages,
        stored_sequence_fallback=stored_fallback,
        effective_sequence_fallback=effective_fallback,
    )
    emit_progress(
        on_progress,
        "phase.completed",
        "analysis",
        completed=len(extracted.units),
        total=len(extracted.units),
    )
    return analysis

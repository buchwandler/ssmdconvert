"""Extract stable plain-text units and SSMD semantics for ttsready."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ssmd import AnnotationSpan, ParseStructureResult, parse_structure
from ttsready import (
    OverrideScope,
    ProtectedSpan,
    SpeechOverride,
    TextUnit,
)

from .fingerprints import canonical_json_bytes
from .models import (
    LoadedSsmdSection,
    LoadedSsmdSource,
    SsmdAnalysisIssue,
    SsmdTextContext,
)

_PARAGRAPH_SEPARATOR = re.compile(r"\n(?:[ \t]*\n)+")
_PROTECTED_ANNOTATION_KEYS = frozenset(
    {"as", "say-as", "ph", "phoneme", "phonemes", "pronunciation", "ipa", "speech-form"}
)


@dataclass(frozen=True, slots=True)
class UnitExtraction:
    """SSMD parser results and source-neutral inputs ready for ttsready."""

    units: tuple[TextUnit, ...]
    overrides: tuple[SpeechOverride, ...]
    contexts: tuple[SsmdTextContext, ...]
    structures: Mapping[str, ParseStructureResult]
    issues: tuple[SsmdAnalysisIssue, ...]
    effective_languages: tuple[str, ...]


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:20]
    return f"{prefix}:v1:{digest}"


def _metadata_language(metadata: Mapping[str, Any]) -> str | None:
    for key in ("language", "lang"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _annotation_language(annotation: AnnotationSpan) -> str | None:
    for key in ("lang", "language"):
        value = annotation.attrs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _annotations(structure: ParseStructureResult) -> tuple[AnnotationSpan, ...]:
    source = structure.effective_annotations or structure.annotations
    unique: dict[tuple[Any, ...], AnnotationSpan] = {}
    for annotation in source:
        identity = (
            annotation.char_start,
            annotation.char_end,
            annotation.kind,
            tuple(sorted((key, repr(value)) for key, value in annotation.attrs.items())),
        )
        unique[identity] = annotation
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end)))


def _language_for_interval(
    start: int,
    end: int,
    annotations: tuple[AnnotationSpan, ...],
    *,
    requested_language: str | None,
    section_language: str | None,
    source_language: str | None,
    fallback_language: str | None,
) -> str | None:
    if requested_language is not None:
        return requested_language
    scoped = [
        annotation
        for annotation in annotations
        if _annotation_language(annotation) is not None
        and annotation.char_start <= start
        and end <= annotation.char_end
    ]
    if scoped:
        innermost = min(scoped, key=lambda item: item.char_end - item.char_start)
        return _annotation_language(innermost)
    return section_language or source_language or fallback_language


def _runs_for_paragraph(
    start: int,
    end: int,
    annotations: tuple[AnnotationSpan, ...],
    *,
    requested_language: str | None,
    section_language: str | None,
    source_language: str | None,
    fallback_language: str | None,
) -> tuple[tuple[int, int, str | None], ...]:
    boundaries = {start, end}
    for annotation in annotations:
        if _annotation_language(annotation) is None:
            continue
        if annotation.char_start < end and start < annotation.char_end:
            boundaries.add(max(start, annotation.char_start))
            boundaries.add(min(end, annotation.char_end))
    ordered = sorted(boundaries)
    runs: list[tuple[int, int, str | None]] = []
    for run_start, run_end in zip(ordered, ordered[1:], strict=False):
        language = _language_for_interval(
            run_start,
            run_end,
            annotations,
            requested_language=requested_language,
            section_language=section_language,
            source_language=source_language,
            fallback_language=fallback_language,
        )
        if runs and runs[-1][1] == run_start and runs[-1][2] == language:
            previous = runs[-1]
            runs[-1] = (previous[0], run_end, language)
        else:
            runs.append((run_start, run_end, language))
    return tuple(runs)


def _is_provider_specific(attrs: Mapping[str, Any]) -> bool:
    return any(key.startswith(("tts-", "tts:", "provider-", "provider:")) for key in attrs)


def _is_protected(annotation: AnnotationSpan) -> bool:
    keys = set(annotation.attrs) - {"tag", "lang", "language", "sub"}
    return bool(keys & _PROTECTED_ANNOTATION_KEYS) or _is_provider_specific(annotation.attrs)


def _protected_spans(
    run_start: int,
    run_end: int,
    annotations: tuple[AnnotationSpan, ...],
) -> tuple[ProtectedSpan, ...]:
    candidates = sorted(
        (
            max(run_start, annotation.char_start) - run_start,
            min(run_end, annotation.char_end) - run_start,
        )
        for annotation in annotations
        if _is_protected(annotation)
        and annotation.char_start < run_end
        and run_start < annotation.char_end
    )
    merged: list[tuple[int, int]] = []
    for start, end in candidates:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(
        ProtectedSpan(start, end, reason="authoritative SSMD speech semantics")
        for start, end in merged
    )


def _parser_issues(
    section: LoadedSsmdSection, structure: ParseStructureResult
) -> list[SsmdAnalysisIssue]:
    issues = [
        SsmdAnalysisIssue(
            code=diagnostic.code,
            severity=diagnostic.severity,
            section_id=section.id,
            paragraph_index=None,
            clean_start=None,
            clean_end=None,
            raw_source_start=diagnostic.source_start,
            raw_source_end=diagnostic.source_end,
            message=diagnostic.message,
            origin="ssmd",
        )
        for diagnostic in structure.diagnostics
    ]
    issues.extend(
        SsmdAnalysisIssue(
            code="ssmd.parser_warning",
            severity="warning",
            section_id=section.id,
            paragraph_index=None,
            clean_start=None,
            clean_end=None,
            raw_source_start=None,
            raw_source_end=None,
            message=warning,
            origin="ssmd",
        )
        for warning in structure.warnings
    )
    return issues


def _paragraph_ranges(text: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for match in _PARAGRAPH_SEPARATOR.finditer(text):
        if text[cursor : match.start()].strip():
            ranges.append((cursor, match.start()))
        cursor = match.end()
    if text[cursor:].strip():
        ranges.append((cursor, len(text)))
    return tuple(ranges)


def _validate_language(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty language tag or None")
    return value.strip()


def extract_units(
    source: LoadedSsmdSource,
    sections: Iterable[LoadedSsmdSection] | None = None,
    *,
    language: str | None = None,
    fallback_language: str | None = None,
    include_titles: bool = True,
) -> UnitExtraction:
    """Extract visible-text units, contexts, overrides, and SSMD diagnostics.

    Unit text is an exact slice of parser clean text. No SSMD markup or Path
    values enter ttsready metadata.
    """
    requested_language = _validate_language(language, "language")
    fallback_language = _validate_language(fallback_language, "fallback_language")
    selected = tuple(source.sections if sections is None else sections)
    source_language = _metadata_language(source.metadata)
    units: list[TextUnit] = []
    overrides: list[SpeechOverride] = []
    contexts: list[SsmdTextContext] = []
    structures: dict[str, ParseStructureResult] = {}
    issues: list[SsmdAnalysisIssue] = []
    languages: list[str] = []

    for section in selected:
        structure = parse_structure(
            section.ssmd,
            dialect="0.9",
            normalize=False,
            resolve_defaults=True,
        )
        structures[section.id] = structure
        annotations = _annotations(structure)
        issues.extend(_parser_issues(section, structure))
        section_language = _metadata_language(structure.header)
        text_contexts: list[tuple[int, str, int | None, int | None, bool]] = []
        if include_titles and section.title:
            text_contexts.append((-1, section.title, None, None, True))
        text_contexts.extend(
            (paragraph_index, structure.clean_text[start:end], start, end, False)
            for paragraph_index, (start, end) in enumerate(
                _paragraph_ranges(structure.clean_text), start=1
            )
        )

        for paragraph_index, context_text, context_start, context_end, is_title in text_contexts:
            role = "title" if is_title else "prose"
            context_id = _stable_id(
                "ctx",
                {
                    "section_id": section.id,
                    "paragraph_index": paragraph_index,
                    "role": role,
                },
            )
            run_specs: tuple[tuple[int, int, str | None], ...]
            if is_title:
                run_specs = (
                    (
                        0,
                        len(context_text),
                        requested_language
                        or section_language
                        or source_language
                        or fallback_language,
                    ),
                )
            else:
                assert context_start is not None and context_end is not None
                run_specs = _runs_for_paragraph(
                    context_start,
                    context_end,
                    annotations,
                    requested_language=requested_language,
                    section_language=section_language,
                    source_language=source_language,
                    fallback_language=fallback_language,
                )

            context_unit_ids: list[str] = []
            for run_index, (run_start, run_end, effective_language) in enumerate(
                run_specs, start=1
            ):
                if is_title:
                    run_text = context_text[run_start:run_end]
                    absolute_start = absolute_end = None
                    local_annotations: tuple[AnnotationSpan, ...] = ()
                else:
                    assert context_start is not None
                    absolute_start = run_start
                    absolute_end = run_end
                    run_text = structure.clean_text[run_start:run_end]
                    local_annotations = annotations
                if not run_text:
                    continue
                if effective_language is None:
                    if run_text.strip():
                        issues.append(
                            SsmdAnalysisIssue(
                                code="analysis.language_unresolved",
                                severity="error",
                                section_id=section.id,
                                paragraph_index=paragraph_index,
                                clean_start=absolute_start,
                                clean_end=absolute_end,
                                raw_source_start=None,
                                raw_source_end=None,
                                message=(
                                    "No effective language is available for this text; "
                                    "supply --language or configure a fallback."
                                ),
                                origin="ssmd",
                            )
                        )
                    continue

                unit_id = _stable_id(
                    "unit",
                    {
                        "section_id": section.id,
                        "paragraph_index": paragraph_index,
                        "run_index": run_index,
                        "role": role,
                    },
                )
                protected = (
                    _protected_spans(run_start, run_end, local_annotations) if not is_title else ()
                )
                unit = TextUnit(
                    id=unit_id,
                    text=run_text,
                    language=effective_language,
                    role=role,
                    protected_spans=protected,
                    metadata={
                        "section_id": section.id,
                        "section_index": section.index,
                        "paragraph_index": paragraph_index,
                        "run_index": run_index,
                        "role": role,
                        "context_id": context_id,
                        "is_title": is_title,
                        "clean_start": absolute_start,
                        "clean_end": absolute_end,
                    },
                )
                units.append(unit)
                context_unit_ids.append(unit_id)
                if effective_language not in languages:
                    languages.append(effective_language)

                if is_title:
                    continue
                assert absolute_start is not None and absolute_end is not None
                for annotation in annotations:
                    spoken = annotation.attrs.get("sub")
                    if spoken is None or not (
                        annotation.char_start < absolute_end
                        and absolute_start < annotation.char_end
                    ):
                        continue
                    if (
                        not isinstance(spoken, str)
                        or annotation.char_start < absolute_start
                        or annotation.char_end > absolute_end
                    ):
                        if _is_protected(annotation):
                            continue
                        issues.append(
                            SsmdAnalysisIssue(
                                code="ssmd.sub_crosses_language_run",
                                severity="warning",
                                section_id=section.id,
                                paragraph_index=paragraph_index,
                                clean_start=max(absolute_start, annotation.char_start),
                                clean_end=min(absolute_end, annotation.char_end),
                                raw_source_start=annotation.source_start,
                                raw_source_end=annotation.source_end,
                                message=(
                                    "An SSMD sub annotation could not be represented as one "
                                    "language-scoped override."
                                ),
                                origin="ssmd",
                            )
                        )
                        continue
                    local_start = annotation.char_start - absolute_start
                    local_end = annotation.char_end - absolute_start
                    overrides.append(
                        SpeechOverride(
                            surface=run_text[local_start:local_end],
                            spoken=spoken,
                            match="literal",
                            scope=OverrideScope(
                                kind="occurrence",
                                unit_id=unit_id,
                                source_start=local_start,
                                source_end=local_end,
                            ),
                            provenance={"origin": "ssmd", "annotation": "sub"},
                        )
                    )

            contexts.append(
                SsmdTextContext(
                    id=context_id,
                    section_id=section.id,
                    section_index=section.index,
                    paragraph_index=paragraph_index,
                    is_title=is_title,
                    source_text=context_text,
                    clean_start=context_start,
                    clean_end=context_end,
                    unit_ids=tuple(context_unit_ids),
                )
            )

    return UnitExtraction(
        units=tuple(units),
        overrides=tuple(overrides),
        contexts=tuple(contexts),
        structures=structures,
        issues=tuple(issues),
        effective_languages=tuple(languages),
    )

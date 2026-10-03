"""SSMD-aware local speech audit and preparation orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

import spokenform
from ssmd import AnnotationSpan, ParseStructureResult, parse_structure

from ..render import validate_ssmd_document
from .audit import (
    TextSpan,
    audit_residual_characters,
    source_range_for_clean_span,
    text_spans,
)
from .escaping import format_sub_annotation
from .models import (
    SpeechChange,
    SpeechPreparationOptions,
    SpeechPreparationReport,
    SpeechPreparationResult,
)

_SPEECH_OVERRIDE_KEYS = frozenset({"sub", "as", "say-as", "ph", "phonemes"})
_BOUNDARY_CHARACTERS = frozenset("_")


@dataclass(frozen=True, slots=True)
class _Candidate:
    start: int
    end: int
    source_text: str
    spoken_text: str
    language: str
    kind: str | None
    rule: str | None
    skipped_reason: str | None = None


def _backend_version() -> str | None:
    try:
        return version("spokenform")
    except PackageNotFoundError:
        return getattr(spokenform, "__version__", None)


def _annotation_language(annotation: AnnotationSpan) -> str | None:
    language = annotation.attrs.get("lang") or annotation.attrs.get("language")
    return language if isinstance(language, str) else None


def _run_language(
    span: TextSpan,
    structure: ParseStructureResult,
    options: SpeechPreparationOptions,
) -> str | None:
    inline_languages = [
        annotation
        for annotation in structure.annotations
        if _annotation_language(annotation)
        and annotation.char_start <= span.char_start
        and span.char_end <= annotation.char_end
    ]
    if inline_languages:
        innermost = min(
            inline_languages,
            key=lambda annotation: annotation.char_end - annotation.char_start,
        )
        return _annotation_language(innermost)
    if options.language is not None:
        return options.language
    language = structure.header.get("language") or structure.header.get("lang")
    return language if isinstance(language, str) and language.strip() else None


def _is_authoritatively_protected(
    span: TextSpan,
    annotations: list[AnnotationSpan],
) -> bool:
    for annotation in annotations:
        if not _SPEECH_OVERRIDE_KEYS.intersection(annotation.attrs):
            continue
        if annotation.char_start < span.char_end and span.char_start < annotation.char_end:
            return True
    return False


def _speech_profile(
    language: str,
    pronunciations: Mapping[str, str],
) -> spokenform.SpeechProfile | None:
    if not pronunciations:
        return None
    entries = tuple(
        spokenform.GlossaryEntry(
            abbreviation=source,
            long_form=spoken,
            read_as="custom",
            spoken_form=spoken,
            case_sensitive=True,
        )
        for source, spoken in sorted(pronunciations.items())
    )
    return spokenform.SpeechProfile(
        name="ssmdconvert-project-pronunciations",
        language=language,
        glossary=entries,
    )


def _prepare_plain_run(
    text: str,
    language: str,
    sequence_fallback_mode: str,
    *,
    profile: spokenform.SpeechProfile | None,
    protected_spans: tuple[tuple[int, int], ...] = (),
    expand_structured: bool = True,
    expand_numbers: bool = True,
) -> spokenform.PreparedText:
    """Call spokenform with deterministic local settings on plain text only."""
    return spokenform.prepare(
        text,
        language=language,
        profile=profile,
        protected_spans=protected_spans,
        use_spacy=False,
        strict=False,
        symbol_mode="none",
        normalize_unicode=False,
        normalize_whitespace=False,
        strip_outer_whitespace=False,
        collapse_horizontal_whitespace=False,
        normalize_line_whitespace=False,
        collapse_blank_lines=False,
        generic_acronym_mode="known_only",
        sequence_fallback_mode=sequence_fallback_mode,
        expand_structured=expand_structured,
        expand_numbers=expand_numbers,
    )


def _is_word_character(character: str) -> bool:
    return character.isalnum() or character in _BOUNDARY_CHARACTERS


def _find_glossary_matches(
    text: str,
    pronunciations: Mapping[str, str],
) -> tuple[tuple[int, int, str, str], ...]:
    matches: list[tuple[int, int, str, str]] = []
    for surface, spoken in sorted(
        pronunciations.items(), key=lambda item: (-len(item[0]), item[0])
    ):
        cursor = 0
        while True:
            start = text.find(surface, cursor)
            if start < 0:
                break
            end = start + len(surface)
            left_boundary = start == 0 or not _is_word_character(text[start - 1])
            right_boundary = end == len(text) or not _is_word_character(text[end])
            if left_boundary and right_boundary:
                matches.append((start, end, surface, spoken))
            cursor = start + 1
    return tuple(sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]), item[2])))


def _glossary_candidates(
    text: str,
    language: str,
    profile: spokenform.SpeechProfile | None,
    matches: tuple[tuple[int, int, str, str], ...],
) -> tuple[tuple[_Candidate, ...], tuple[str, ...]]:
    candidates: list[_Candidate] = []
    warnings: list[str] = []
    if not matches:
        return (), ()

    for start, end, surface, expected_spoken in matches:
        prepared = _prepare_plain_run(
            surface,
            language,
            "preserve",
            profile=profile,
            expand_structured=False,
            expand_numbers=False,
        )
        warnings.extend(str(item) for item in prepared.warnings)
        exact = next(
            (
                replacement
                for replacement in prepared.source_replacements
                if replacement.source_start == 0
                and replacement.source_end == len(surface)
                and replacement.source == surface
                and replacement.replacement == expected_spoken
            ),
            None,
        )
        skipped_reason = None
        spoken_text = expected_spoken
        rule = "project-pronunciation"
        if exact is None:
            skipped_reason = "spokenform profile did not produce the exact glossary pronunciation"
        else:
            spoken_text = exact.replacement
            rule = exact.rule or rule
        candidates.append(
            _Candidate(
                start=start,
                end=end,
                source_text=surface,
                spoken_text=spoken_text,
                language=language,
                kind="glossary",
                rule=rule,
                skipped_reason=skipped_reason,
            )
        )
    return tuple(candidates), tuple(warnings)


def _generic_candidates(
    prepared: spokenform.PreparedText,
    language: str,
) -> tuple[_Candidate, ...]:
    candidates: list[_Candidate] = []
    expected_base_language = spokenform.base_language(language)
    for replacement in prepared.source_replacements:
        reported_language = replacement.language
        language_mismatch = (
            reported_language is not None
            and spokenform.base_language(reported_language) != expected_base_language
        )
        candidates.append(
            _Candidate(
                start=replacement.source_start,
                end=replacement.source_end,
                source_text=replacement.source,
                spoken_text=replacement.replacement,
                language=language,
                kind=replacement.kind,
                rule=replacement.rule,
                skipped_reason=(
                    "spokenform replacement language does not match its plain-text run"
                    if language_mismatch
                    else None
                ),
            )
        )
    return tuple(candidates)


def _ranges_overlap(left: _Candidate, right: _Candidate) -> bool:
    return left.start < right.end and right.start < left.end


def _resolve_candidates(
    generic: tuple[_Candidate, ...],
    glossary: tuple[_Candidate, ...],
) -> tuple[tuple[_Candidate, ...], tuple[tuple[_Candidate, str], ...]]:
    skipped: list[tuple[_Candidate, str]] = []
    remaining_generic: list[_Candidate] = []
    for candidate in generic:
        if any(_ranges_overlap(candidate, override) for override in glossary):
            skipped.append((candidate, "superseded by project pronunciation glossary"))
        else:
            remaining_generic.append(candidate)

    candidates = (*glossary, *remaining_generic)
    overlap_indexes: set[int] = set()
    for left_index, left in enumerate(candidates):
        for right_index in range(left_index + 1, len(candidates)):
            if _ranges_overlap(left, candidates[right_index]):
                overlap_indexes.add(left_index)
                overlap_indexes.add(right_index)
    accepted: list[_Candidate] = []
    for index, candidate in enumerate(candidates):
        if index in overlap_indexes:
            skipped.append((candidate, "overlaps another replacement candidate"))
        elif candidate.skipped_reason is not None:
            skipped.append((candidate, candidate.skipped_reason))
        else:
            accepted.append(candidate)
    return tuple(sorted(accepted, key=lambda item: (item.start, item.end))), tuple(skipped)


def _speech_change(
    candidate: _Candidate,
    source_range: tuple[int, int] | None,
    *,
    status: Literal["applied", "skipped"],
    reason: str | None,
) -> SpeechChange:
    return SpeechChange(
        source_start=source_range[0] if source_range is not None else None,
        source_end=source_range[1] if source_range is not None else None,
        source_text=candidate.source_text,
        spoken_text=candidate.spoken_text,
        language=candidate.language,
        kind=candidate.kind,
        rule=candidate.rule,
        status=status,
        reason=reason,
    )


def _count_substitutions(structure: ParseStructureResult) -> int:
    return sum("sub" in annotation.attrs for annotation in structure.annotations)


def _apply_source_edits(
    source: str,
    structure: ParseStructureResult,
    edits: list[tuple[int, int, _Candidate]],
) -> str:
    result = source
    for source_start, source_end, candidate in sorted(
        edits, key=lambda item: item[0], reverse=True
    ):
        original = source[source_start:source_end]
        if original != candidate.source_text:
            raise ValueError("Speech annotation source changed after candidate validation")
        annotation = format_sub_annotation(original, candidate.spoken_text)
        result = result[:source_start] + annotation + result[source_end:]

    validate_ssmd_document(result)
    result_structure = parse_structure(result, dialect="0.9", normalize=False)
    if result_structure.clean_text != structure.clean_text:
        raise ValueError("Speech annotations changed visible SSMD text")
    if _count_substitutions(result_structure) - _count_substitutions(structure) != len(edits):
        raise ValueError("Applied speech changes did not produce exactly one sub annotation each")
    return result


def prepare_ssmd_for_speech(
    source: str,
    *,
    options: SpeechPreparationOptions,
) -> SpeechPreparationResult:
    """Audit SSMD 0.9 or add safe, reviewable speech substitutions.

    Spokenform receives plain-text leaves only. Author speech annotations are
    protected, and candidate edits are applied only when public source spans
    prove that their source slice is exact.
    """
    if options.mode == "off":
        report = SpeechPreparationReport(
            backend="spokenform",
            backend_version=_backend_version(),
            languages=(),
            changes=(),
            issues=(),
            warnings=(),
        )
        return SpeechPreparationResult(ssmd=source, report=report)

    validate_ssmd_document(source)
    structure = parse_structure(source, dialect="0.9", normalize=False)
    spans = text_spans(source, structure)
    protected_spans = [
        span for span in spans if _is_authoritatively_protected(span, structure.annotations)
    ]
    plain_spans = [span for span in spans if span not in protected_spans]
    languages: list[str] = []
    changes: list[SpeechChange] = []
    warnings: list[str] = []
    edits: list[tuple[int, int, _Candidate]] = []

    for span in plain_spans:
        language = _run_language(span, structure, options)
        if language is None:
            warnings.append("No effective language; semantic speech preparation was skipped.")
            continue
        if language not in languages:
            languages.append(language)

        plain_text = structure.clean_text[span.char_start : span.char_end]
        if not plain_text:
            continue
        if "\ufffd" in plain_text:
            warnings.append("Skipped semantic speech preparation for a text run containing U+FFFD.")
            continue

        profile = _speech_profile(language, options.pronunciations)
        glossary_matches = _find_glossary_matches(plain_text, options.pronunciations)
        protected_glossary_spans = tuple((start, end) for start, end, _, _ in glossary_matches)
        prepared = _prepare_plain_run(
            plain_text,
            language,
            options.sequence_fallback_mode,
            profile=profile,
            protected_spans=protected_glossary_spans,
        )
        warnings.extend(str(item) for item in prepared.warnings)
        glossary_candidates, glossary_warnings = _glossary_candidates(
            plain_text,
            language,
            profile,
            glossary_matches,
        )
        warnings.extend(glossary_warnings)
        candidates, preskipped = _resolve_candidates(
            _generic_candidates(prepared, language),
            glossary_candidates,
        )

        for candidate, skip_reason in preskipped:
            local_range = (
                source_range_for_clean_span(
                    source,
                    structure,
                    span.char_start + candidate.start,
                    span.char_start + candidate.end,
                )
                if 0 <= candidate.start < candidate.end <= len(plain_text)
                else None
            )
            changes.append(
                _speech_change(candidate, local_range, status="skipped", reason=skip_reason)
            )

        for candidate in candidates:
            valid_range = 0 <= candidate.start < candidate.end <= len(plain_text)
            source_matches = (
                valid_range and plain_text[candidate.start : candidate.end] == candidate.source_text
            )
            source_range = (
                source_range_for_clean_span(
                    source,
                    structure,
                    span.char_start + candidate.start,
                    span.char_start + candidate.end,
                )
                if valid_range
                else None
            )
            reason = None
            if not source_matches:
                reason = "replacement does not exactly match its plain-text source"
            elif not candidate.spoken_text.strip():
                reason = "spoken replacement is empty"
            elif candidate.spoken_text == candidate.source_text:
                reason = "spoken replacement is identical to source"
            elif "\n" in candidate.source_text or "\r" in candidate.source_text:
                reason = "source token crosses a line boundary"
            elif source_range is None:
                reason = "SSMD source leaf is escaped or normalized; source mapping is not exact"
            else:
                try:
                    format_sub_annotation(candidate.source_text, candidate.spoken_text)
                except ValueError as error:
                    reason = str(error)

            if reason is not None:
                changes.append(
                    _speech_change(candidate, source_range, status="skipped", reason=reason)
                )
                continue
            if options.mode == "audit":
                changes.append(
                    _speech_change(
                        candidate,
                        source_range,
                        status="skipped",
                        reason="audit mode does not modify source",
                    )
                )
                continue

            assert source_range is not None
            changes.append(_speech_change(candidate, source_range, status="applied", reason=None))
            edits.append((source_range[0], source_range[1], candidate))

    has_unprotected_text = bool(plain_spans)
    if options.mode == "annotate" and has_unprotected_text and not languages:
        raise ValueError("speech annotation requires --language or document language metadata")
    if has_unprotected_text and not languages:
        warnings.append("No effective language; semantic speech preparation was skipped.")

    issues = audit_residual_characters(source, structure)
    if options.strict and any(issue.severity == "error" for issue in issues):
        raise ValueError(
            "Speech QC strict mode failed: source contains U+FFFD or another error-level issue"
        )

    output = (
        _apply_source_edits(source, structure, edits)
        if options.mode == "annotate" and edits
        else source
    )
    changes.sort(
        key=lambda item: (
            item.source_start is None,
            item.source_start or 0,
            item.source_end or 0,
        )
    )
    report = SpeechPreparationReport(
        backend="spokenform",
        backend_version=_backend_version(),
        languages=tuple(languages),
        changes=tuple(changes),
        issues=issues,
        warnings=tuple(dict.fromkeys(warnings)),
    )
    return SpeechPreparationResult(ssmd=output, report=report)

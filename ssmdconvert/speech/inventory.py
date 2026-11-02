"""Deterministic discovery of source surfaces that may need speech decisions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ssmd import parse_structure

from ..analysis.models import LoadedSsmdSource, select_sections
from ..linguistics import LinguisticResourcePool, LinguisticsConfig, SpacyPolicy

_TOKEN_RE = re.compile(r"[^\W_]+(?:[-/'’&][^\W_]+)*", re.UNICODE)
_SLASH_PART_RE = re.compile(r"[^/]+")
_PARAGRAPH_RE = re.compile(r"\n(?:[ \t]*\n)+")
_REASON_PRIORITY = (
    "all-caps",
    "hyphenated-initialism",
    "mixed-case",
    "slash-sequence",
    "alpha-numeric-or-symbol-heavy",
    "hyphenated-name",
    "existing-sub",
    "profile-covered",
)
_REASON_RANK = {reason: index for index, reason in enumerate(_REASON_PRIORITY)}


@dataclass(frozen=True, slots=True)
class SpeechInventoryOptions:
    """Validated selection and enrichment settings for speech inventory."""

    chapters: str = "all"
    language: str | None = None
    spacy: SpacyPolicy = "off"
    pronunciations: Mapping[str, str] = field(default_factory=dict)
    include_existing: bool = True
    max_contexts: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.chapters, str) or not self.chapters.strip():
            raise ValueError("chapters must be a non-empty selector string")
        if self.language is not None and (
            not isinstance(self.language, str) or not self.language.strip()
        ):
            raise ValueError("language must be a non-empty language tag or None")
        if self.spacy not in {"off", "auto", "sm", "md", "lg", "trf"}:
            raise ValueError("spacy must be one of: off, auto, sm, md, lg, trf")
        if not isinstance(self.pronunciations, Mapping):
            raise TypeError("pronunciations must be a mapping of surfaces to spoken forms")
        frozen: dict[str, str] = {}
        for surface, spoken in self.pronunciations.items():
            if not isinstance(surface, str) or not surface or surface != surface.strip():
                raise ValueError(
                    "pronunciation keys must be non-empty strings without edge whitespace"
                )
            if not isinstance(spoken, str) or not spoken.strip():
                raise ValueError("pronunciation values must be non-empty strings")
            frozen[surface] = spoken
        if not isinstance(self.include_existing, bool):
            raise TypeError("include_existing must be a bool")
        if isinstance(self.max_contexts, bool) or not isinstance(self.max_contexts, int):
            raise TypeError("max_contexts must be an integer")
        if self.max_contexts < 0:
            raise ValueError("max_contexts must be at least 0")
        object.__setattr__(self, "pronunciations", MappingProxyType(frozen))


@dataclass(frozen=True, slots=True)
class SpeechInventoryOccurrence:
    """One bounded source-context sample for a candidate surface."""

    section_id: str
    section_index: int
    paragraph_index: int | None
    context: str
    pos: str | None = None
    proper_noun: bool | None = None
    lemma: str | None = None


@dataclass(frozen=True, slots=True)
class SpeechInventoryCandidate:
    """Grouped speech-risk surface and its deterministic review evidence."""

    surface: str
    count: int
    reasons: tuple[str, ...]
    section_ids: tuple[str, ...]
    existing_spoken_forms: tuple[str, ...]
    profile_replacement: str | None
    occurrences: tuple[SpeechInventoryOccurrence, ...]
    profile_shadowed: bool = False


@dataclass(frozen=True, slots=True)
class SpeechInventory:
    """Versioned inventory result for exactly the selected source chapters."""

    source: str
    chapters: tuple[str, ...]
    candidates: tuple[SpeechInventoryCandidate, ...]
    schema: str = "ssmdconvert.speech-inventory"
    version: int = 1


@dataclass(slots=True)
class _CandidateAccumulator:
    count: int = 0
    events: set[tuple[str, int, int | None, int, int]] = field(default_factory=set)
    reasons: set[str] = field(default_factory=set)
    section_ids: list[str] = field(default_factory=list)
    spoken_forms: set[str] = field(default_factory=set)
    profile_replacement: str | None = None
    profile_shadowed: bool = False
    occurrences: list[SpeechInventoryOccurrence] = field(default_factory=list)
    context_keys: set[tuple[str, int | None, str]] = field(default_factory=set)


def _paragraphs(text: str) -> tuple[tuple[int, int, int], ...]:
    spans: list[tuple[int, int, int]] = []
    cursor = 0
    paragraph_index = 0
    for match in _PARAGRAPH_RE.finditer(text):
        if text[cursor : match.start()].strip():
            paragraph_index += 1
            spans.append((paragraph_index, cursor, match.start()))
        cursor = match.end()
    if text[cursor:].strip():
        paragraph_index += 1
        spans.append((paragraph_index, cursor, len(text)))
    return tuple(spans)


def _surface_reasons(surface: str) -> set[str]:
    reasons: set[str] = set()
    letters = [character for character in surface if character.isalpha()]
    if len(letters) >= 2 and all(character.isupper() for character in letters):
        reasons.add("all-caps")
    parts = surface.split("-")
    if len(parts) >= 2 and all(
        len(part) == 1 and part.isalpha() and part.isupper() for part in parts
    ):
        reasons.add("hyphenated-initialism")
    if any(character.isupper() for character in surface[1:]) and any(
        character.islower() for character in surface
    ):
        reasons.add("mixed-case")
    if "/" in surface and any(character.isalpha() for character in surface):
        reasons.add("slash-sequence")
    if any(character.isalpha() for character in surface) and any(
        character.isdigit() for character in surface
    ):
        reasons.add("alpha-numeric-or-symbol-heavy")
    if "&" in surface:
        reasons.add("alpha-numeric-or-symbol-heavy")
    if "-" in surface and "hyphenated-initialism" not in reasons:
        pieces = surface.split("-")
        if len(pieces) > 1 and all(
            piece and piece[0].isupper() and any(character.islower() for character in piece)
            for piece in pieces
        ):
            reasons.add("hyphenated-name")
    return reasons


def _linguistic_facts(
    text: str,
    start: int,
    end: int,
    language: str | None,
    *,
    spacy: SpacyPolicy,
    pool: LinguisticResourcePool | None,
    selections: dict[str, Any],
) -> tuple[str | None, bool | None, str | None]:
    if spacy == "off" or language is None or pool is None:
        return None, None, None
    selection = selections.get(language)
    if selection is None:
        selection = pool.resolve(language, LinguisticsConfig(spacy=spacy))
        selections[language] = selection
    tokens = pool.analyze_text(text, selection)
    matching = [token for token in tokens if token.start < end and start < token.end]
    if not matching:
        return None, None, None
    return (
        matching[0].pos,
        matching[0].pos == "PROPN" if matching[0].pos is not None else None,
        matching[0].lemma,
    )


def _spoken_for_span(
    annotations: Mapping[tuple[int, int], str], start: int, end: int
) -> str | None:
    exact = annotations.get((start, end))
    if exact is not None:
        return exact
    return next(
        (
            spoken
            for (annotation_start, annotation_end), spoken in annotations.items()
            if annotation_start <= start and end <= annotation_end
        ),
        None,
    )


def inventory_loaded_source(
    source: LoadedSsmdSource,
    *,
    chapters: str = "all",
    language: str | None = None,
    pronunciations: Mapping[str, str] | None = None,
    include_existing: bool = True,
    max_contexts: int = 2,
    spacy: SpacyPolicy = "off",
) -> SpeechInventory:
    """Inventory parser-visible text and existing substitutions in an SSMD source."""
    options = SpeechInventoryOptions(
        chapters=chapters,
        language=language,
        spacy=spacy,
        pronunciations={} if pronunciations is None else pronunciations,
        include_existing=include_existing,
        max_contexts=max_contexts,
    )
    selected = select_sections(source, options.chapters)
    replacements = options.pronunciations
    builders: dict[str, _CandidateAccumulator] = {}
    pool = LinguisticResourcePool() if options.spacy != "off" else None
    selections: dict[str, Any] = {}

    def add_occurrence(
        surface: str,
        section_id: str,
        section_index: int,
        paragraph_index: int | None,
        context: str,
        start: int,
        end: int,
        *,
        reasons: set[str] | None = None,
        spoken: str | None = None,
        language_for_text: str | None = None,
        context_start: int = 0,
    ) -> None:
        if not surface:
            return
        accumulator = builders.setdefault(surface, _CandidateAccumulator())
        replacement = replacements.get(surface)
        if replacement is not None:
            accumulator.profile_replacement = replacement
            accumulator.reasons.add("profile-covered")
        if reasons:
            accumulator.reasons.update(reasons)
        if spoken is not None and options.include_existing:
            accumulator.reasons.add("existing-sub")
            accumulator.spoken_forms.add(spoken)
            if replacement is not None:
                accumulator.profile_shadowed = True
        event = (section_id, section_index, paragraph_index, start, end)
        if event not in accumulator.events:
            accumulator.events.add(event)
            accumulator.count += 1
            if section_id not in accumulator.section_ids:
                accumulator.section_ids.append(section_id)
            context_key = (section_id, paragraph_index, context)
            if (
                len(accumulator.occurrences) < options.max_contexts
                and context_key not in accumulator.context_keys
            ):
                pos, proper_noun, lemma = _linguistic_facts(
                    context,
                    max(0, start - context_start),
                    max(0, end - context_start),
                    language_for_text,
                    spacy=options.spacy,
                    pool=pool,
                    selections=selections,
                )
                accumulator.context_keys.add(context_key)
                accumulator.occurrences.append(
                    SpeechInventoryOccurrence(
                        section_id=section_id,
                        section_index=section_index,
                        paragraph_index=paragraph_index,
                        context=context,
                        pos=pos,
                        proper_noun=proper_noun,
                        lemma=lemma,
                    )
                )

    for section in selected:
        try:
            structure = parse_structure(section.ssmd, dialect="0.9", normalize=False)
        except Exception as exc:
            raise ValueError(f"could not parse SSMD section {section.id}: {exc}") from exc
        clean_text = structure.clean_text
        section_language = (
            language
            or next(
                (
                    structure.header[key].strip()
                    for key in ("language", "lang")
                    if isinstance(structure.header.get(key), str) and structure.header[key].strip()
                ),
                None,
            )
            or next(
                (
                    source.metadata[key].strip()
                    for key in ("language", "lang")
                    if isinstance(source.metadata.get(key), str) and source.metadata[key].strip()
                ),
                None,
            )
        )
        paragraph_spans = _paragraphs(clean_text)
        annotations = structure.effective_annotations or structure.annotations
        annotations_by_span: dict[tuple[int, int], str] = {}
        if options.include_existing:
            for annotation in annotations:
                spoken = annotation.attrs.get("sub")
                if (
                    not isinstance(spoken, str)
                    or not spoken.strip()
                    or annotation.char_start < 0
                    or annotation.char_end > len(clean_text)
                ):
                    continue
                start, end = annotation.char_start, annotation.char_end
                surface = clean_text[start:end]
                if not surface:
                    continue
                annotations_by_span[(start, end)] = spoken
                paragraph = next(
                    (
                        (index, para_start, para_end)
                        for index, para_start, para_end in paragraph_spans
                        if para_start <= start and end <= para_end
                    ),
                    None,
                )
                if paragraph is None:
                    paragraph_index = None
                    context_start = start
                    context = surface
                else:
                    paragraph_index, context_start, context_end = paragraph
                    context = clean_text[context_start:context_end]
                add_occurrence(
                    surface,
                    section.id,
                    section.index,
                    paragraph_index,
                    context,
                    start,
                    end,
                    reasons={"existing-sub"},
                    spoken=spoken,
                    language_for_text=section_language,
                    context_start=context_start,
                )

        for paragraph_index, paragraph_start, paragraph_end in paragraph_spans:
            context = clean_text[paragraph_start:paragraph_end]
            for match in _TOKEN_RE.finditer(context):
                surface = match.group(0)
                reasons = _surface_reasons(surface)
                if not reasons and surface not in replacements:
                    continue
                start = paragraph_start + match.start()
                end = paragraph_start + match.end()
                add_occurrence(
                    surface,
                    section.id,
                    section.index,
                    paragraph_index,
                    context,
                    start,
                    end,
                    reasons=reasons,
                    spoken=_spoken_for_span(annotations_by_span, start, end),
                    language_for_text=section_language,
                    context_start=paragraph_start,
                )

                if "/" in surface:
                    for component in _SLASH_PART_RE.finditer(surface):
                        part = component.group(0)
                        part_reasons = _surface_reasons(part)
                        if not part_reasons and part not in replacements:
                            continue
                        part_start = start + component.start()
                        part_end = start + component.end()
                        add_occurrence(
                            part,
                            section.id,
                            section.index,
                            paragraph_index,
                            context,
                            part_start,
                            part_end,
                            reasons=part_reasons,
                            spoken=_spoken_for_span(annotations_by_span, part_start, part_end),
                            language_for_text=section_language,
                            context_start=paragraph_start,
                        )
        if section.title:
            for match in _TOKEN_RE.finditer(section.title):
                surface = match.group(0)
                reasons = _surface_reasons(surface)
                if not reasons and surface not in replacements:
                    continue
                add_occurrence(
                    surface,
                    section.id,
                    section.index,
                    None,
                    section.title,
                    match.start(),
                    match.end(),
                    reasons=reasons,
                    language_for_text=section_language,
                    context_start=0,
                )
                if "/" in surface:
                    for component in _SLASH_PART_RE.finditer(surface):
                        part = component.group(0)
                        part_reasons = _surface_reasons(part)
                        if not part_reasons and part not in replacements:
                            continue
                        part_start = match.start() + component.start()
                        part_end = match.start() + component.end()
                        add_occurrence(
                            part,
                            section.id,
                            section.index,
                            None,
                            section.title,
                            part_start,
                            part_end,
                            reasons=part_reasons,
                            language_for_text=section_language,
                            context_start=0,
                        )

    candidates = [
        SpeechInventoryCandidate(
            surface=surface,
            count=accumulator.count,
            reasons=tuple(sorted(accumulator.reasons, key=lambda item: _REASON_RANK[item])),
            section_ids=tuple(accumulator.section_ids),
            existing_spoken_forms=tuple(sorted(accumulator.spoken_forms)),
            profile_replacement=accumulator.profile_replacement,
            occurrences=tuple(accumulator.occurrences),
            profile_shadowed=accumulator.profile_shadowed,
        )
        for surface, accumulator in builders.items()
    ]
    candidates.sort(
        key=lambda candidate: (
            candidate.profile_replacement is None,
            min((_REASON_RANK[reason] for reason in candidate.reasons), default=len(_REASON_RANK)),
            -candidate.count,
            candidate.surface,
        )
    )
    return SpeechInventory(
        source=str(source.path),
        chapters=tuple(section.id for section in selected),
        candidates=tuple(candidates),
    )


__all__ = [
    "SpeechInventory",
    "SpeechInventoryCandidate",
    "SpeechInventoryOccurrence",
    "SpeechInventoryOptions",
    "inventory_loaded_source",
]

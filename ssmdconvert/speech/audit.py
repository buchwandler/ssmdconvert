"""Conservative residual-Unicode checks for SSMD speech preparation."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from ssmd import ParseStructureResult

from .models import SpeechIssue

_PROSE_PUNCTUATION = frozenset(".,!?;:'\"()[]-–—")


@dataclass(frozen=True, slots=True)
class TextSpan:
    char_start: int
    char_end: int
    source_start: int
    source_end: int


def text_spans(source: str, structure: ParseStructureResult) -> tuple[TextSpan, ...]:
    """Map unchanged source text into clean-text coordinates conservatively."""
    lines = source.splitlines(keepends=True)
    source_body_start = 0
    if lines and lines[0].strip() == "---":
        offset = len(lines[0])
        for line in lines[1:]:
            offset += len(line)
            if line.strip() == "---":
                source_body_start = offset
                break

    body = source[source_body_start:]
    matcher = SequenceMatcher(None, body, structure.clean_text, autojunk=False)
    annotation_boundaries = {
        boundary
        for annotation in structure.annotations
        for boundary in (annotation.char_start, annotation.char_end)
    }
    spans: list[TextSpan] = []
    for match in matcher.get_matching_blocks():
        if not match.size:
            continue
        source_start = source_body_start + match.a
        source_end = source_start + match.size
        escaped = source_start > 0 and source[source_start - 1] == "\\"
        if escaped:
            spans.append(
                TextSpan(
                    char_start=match.b,
                    char_end=match.b + match.size,
                    source_start=source_start - 1,
                    source_end=source_end,
                )
            )
            continue

        split_points = [0]
        split_points.extend(
            boundary - match.b
            for boundary in sorted(annotation_boundaries)
            if match.b < boundary < match.b + match.size
        )
        split_points.append(match.size)
        for start, end in zip(split_points, split_points[1:], strict=False):
            spans.append(
                TextSpan(
                    char_start=match.b + start,
                    char_end=match.b + end,
                    source_start=source_start + start,
                    source_end=source_start + end,
                )
            )
    return tuple(spans)


def _source_range(
    source: str,
    structure: ParseStructureResult,
    spans: tuple[TextSpan, ...],
    char_start: int,
    char_end: int,
) -> tuple[int, int] | None:
    for span in spans:
        if span.char_start <= char_start and char_end <= span.char_end:
            raw_leaf = source[span.source_start : span.source_end]
            clean_leaf = structure.clean_text[span.char_start : span.char_end]
            if raw_leaf != clean_leaf:
                return None
            source_start = span.source_start + char_start - span.char_start
            source_end = source_start + char_end - char_start
            return source_start, source_end
    return None


def source_range_for_clean_span(
    source: str,
    structure: ParseStructureResult,
    char_start: int,
    char_end: int,
) -> tuple[int, int] | None:
    """Map a clean-text range only when its complete text span is verbatim in source."""
    return _source_range(source, structure, text_spans(source, structure), char_start, char_end)


def _is_noncharacter(character: str) -> bool:
    codepoint = ord(character)
    return 0xFDD0 <= codepoint <= 0xFDEF or (codepoint & 0xFFFF) in {0xFFFE, 0xFFFF}


def _issue_for_character(
    character: str,
    source_range: tuple[int, int] | None,
) -> SpeechIssue | None:
    if character in _PROSE_PUNCTUATION or character.isspace():
        return None

    category = unicodedata.category(character)
    codepoint = f"U+{ord(character):04X}"
    name = unicodedata.name(character, "UNNAMED CHARACTER")
    start, end = source_range if source_range is not None else (None, None)

    if character == "\ufffd":
        return SpeechIssue(
            code="source.decode_replacement",
            severity="error",
            source_start=start,
            source_end=end,
            text=character,
            message=(
                "Source contains U+FFFD replacement character; original bytes cannot be recovered."
            ),
            codepoint=codepoint,
            unicode_name=name,
        )
    if _is_noncharacter(character):
        code = "speech.residual_noncharacter"
        message = "A Unicode noncharacter remains without a deterministic spoken replacement."
    elif category == "Co":
        code = "speech.residual_private_use"
        message = "A private-use character remains without a deterministic spoken replacement."
    elif category.startswith("S"):
        code = "speech.residual_symbol"
        message = "No deterministic spoken replacement was produced."
    elif category in {"Cc", "Cf", "Cs"}:
        code = "speech.residual_control"
        message = (
            "A control or format character remains without a deterministic spoken replacement."
        )
    elif category.startswith("P"):
        code = "speech.residual_punctuation"
        message = "Unusual punctuation remains without a deterministic spoken replacement."
    else:
        return None

    return SpeechIssue(
        code=code,
        severity="warning",
        source_start=start,
        source_end=end,
        text=character,
        message=message,
        codepoint=codepoint,
        unicode_name=name,
    )


def audit_residual_characters(
    source: str,
    structure: ParseStructureResult,
) -> tuple[SpeechIssue, ...]:
    """Report suspicious residual characters without altering or removing them."""
    spans = text_spans(source, structure)
    issues: list[SpeechIssue] = []
    for position, character in enumerate(structure.clean_text):
        source_range = _source_range(source, structure, spans, position, position + 1)
        issue = _issue_for_character(character, source_range)
        if issue is not None:
            issues.append(issue)
    return tuple(issues)

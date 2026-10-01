"""Conservative residual-Unicode checks for SSMD speech preparation."""

from __future__ import annotations

import unicodedata

from ssmd import ParseStructureResult

from .models import SpeechIssue

_PROSE_PUNCTUATION = frozenset(".,!?;:'\"()[]-–—")


def _is_noncharacter(character: str) -> bool:
    codepoint = ord(character)
    return 0xFDD0 <= codepoint <= 0xFDEF or (codepoint & 0xFFFF) in {0xFFFE, 0xFFFF}


def source_range_for_clean_span(
    source: str,
    structure: ParseStructureResult,
    char_start: int,
    char_end: int,
) -> tuple[int, int] | None:
    """Map a clean-text range only when its complete leaf is verbatim in source."""
    for span in structure.text_spans:
        if span.char_start <= char_start and char_end <= span.char_end:
            raw_leaf = source[span.source_start : span.source_end]
            clean_leaf = structure.clean_text[span.char_start : span.char_end]
            if raw_leaf != clean_leaf:
                return None
            source_start = span.source_start + char_start - span.char_start
            source_end = source_start + char_end - char_start
            if source[source_start:source_end] == structure.clean_text[char_start:char_end]:
                return source_start, source_end
            return None
    return None


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
    issues: list[SpeechIssue] = []
    for position, character in enumerate(structure.clean_text):
        source_range = source_range_for_clean_span(
            source,
            structure,
            position,
            position + 1,
        )
        issue = _issue_for_character(character, source_range)
        if issue is not None:
            issues.append(issue)
    return tuple(issues)

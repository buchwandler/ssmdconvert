"""Narrow local escaping for generated SSMD substitution attributes."""

from __future__ import annotations

_ESCAPED_ATTRIBUTE_CHARACTERS = frozenset('\\"[]{}')


def escape_sub_alias(value: str) -> str:
    """Escape characters that can change the SSMD annotation grammar."""
    if "\n" in value or "\r" in value:
        raise ValueError("SSMD sub aliases cannot contain line breaks")
    return "".join(
        f"\\{character}" if character in _ESCAPED_ATTRIBUTE_CHARACTERS else character
        for character in value
    )


def format_sub_annotation(source_text: str, spoken_text: str) -> str:
    """Wrap a verbatim source token in a generated SSMD substitution annotation."""
    if not source_text or not spoken_text.strip():
        raise ValueError("SSMD substitutions require non-empty source and spoken text")
    if "\n" in source_text or "\r" in source_text:
        raise ValueError("SSMD substitution source tokens cannot contain line breaks")
    return f'[{source_text}]{{sub="{escape_sub_alias(spoken_text)}"}}'

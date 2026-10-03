from __future__ import annotations

from typing import Literal

SequenceFallbackMode = Literal["preserve", "spell"]
DEFAULT_SEQUENCE_FALLBACK_MODE: SequenceFallbackMode = "preserve"


def validate_sequence_fallback_mode(value: object) -> SequenceFallbackMode:
    """Return a supported sequence fallback policy or raise a clear error."""
    if value == "preserve":
        return "preserve"
    if value == "spell":
        return "spell"
    raise ValueError("sequence_fallback_mode must be 'preserve' or 'spell'")

import pytest

from ssmdconvert.policy import (
    DEFAULT_SEQUENCE_FALLBACK_MODE,
    validate_sequence_fallback_mode,
)


@pytest.mark.parametrize("mode", ["spell", "preserve"])
def test_validate_sequence_fallback_mode_accepts_supported_values(mode: str) -> None:
    assert validate_sequence_fallback_mode(mode) == mode


@pytest.mark.parametrize("mode", ["invalid", None, [], 1])
def test_validate_sequence_fallback_mode_rejects_unsupported_values(mode: object) -> None:
    with pytest.raises(ValueError, match="sequence_fallback_mode"):
        validate_sequence_fallback_mode(mode)


def test_default_sequence_fallback_mode_is_preserve() -> None:
    assert DEFAULT_SEQUENCE_FALLBACK_MODE == "preserve"

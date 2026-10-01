from pathlib import Path

import pytest

from ssmdconvert import Converter, convert
from ssmdconvert.errors import UnsupportedInputError


def test_convenience_convert(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("Hello", encoding="utf-8")
    assert "Hello" in convert(source).ssmd


def test_unsupported_suffix_is_clear(tmp_path: Path) -> None:
    source = tmp_path / "a.xyz"
    source.write_text("Hello", encoding="utf-8")
    with pytest.raises(UnsupportedInputError):
        Converter().convert(source)

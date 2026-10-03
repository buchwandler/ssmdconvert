from pathlib import Path

import pytest
from ssmd import parse_structure

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


def test_convert_persists_default_sequence_fallback_mode(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("in-system", encoding="utf-8")

    result = convert(source)

    structure = parse_structure(result.ssmd, dialect="0.9")
    assert structure.header["sequence_fallback_mode"] == "spell"
    assert result.document.metadata["sequence_fallback_mode"] == "spell"


def test_convert_persists_explicit_preserve_sequence_fallback_mode(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("in-system", encoding="utf-8")

    result = convert(source, sequence_fallback_mode="preserve")

    assert (
        parse_structure(result.ssmd, dialect="0.9").header["sequence_fallback_mode"] == "preserve"
    )


def test_convert_rejects_invalid_sequence_fallback_mode(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("in-system", encoding="utf-8")

    with pytest.raises(ValueError, match="sequence_fallback_mode"):
        convert(source, sequence_fallback_mode="invalid")  # type: ignore[arg-type]


def test_convert_overrides_source_sequence_fallback_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "a.txt"
    source.write_text("in-system", encoding="utf-8")
    converter = Converter()
    document = converter.load(source)
    document.metadata["sequence_fallback_mode"] = "preserve"
    monkeypatch.setattr(converter, "load", lambda _source: document)

    result = converter.convert(source)

    assert result.document.metadata["sequence_fallback_mode"] == "spell"
    assert parse_structure(result.ssmd, dialect="0.9").header["sequence_fallback_mode"] == "spell"

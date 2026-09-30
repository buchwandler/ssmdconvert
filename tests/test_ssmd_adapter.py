from pathlib import Path

from ssmd import parse_structure

from ssmdconvert import Converter


def test_existing_ssmd_is_reemitted_as_09(tmp_path: Path) -> None:
    source = tmp_path / "in.ssmd"
    source.write_text('---\nssmd_version: "0.9"\ntitle: Existing\n---\nHello.\n', encoding="utf-8")
    result = Converter().convert(source)
    parsed = parse_structure(result.ssmd, dialect="0.9")
    assert parsed.header["title"] == "Existing"
    assert parsed.clean_text.strip() == "Hello."

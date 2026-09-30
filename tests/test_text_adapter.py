from pathlib import Path

from ssmdconvert import Converter


def test_text_conversion_splits_common_chapter_headings(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    source.write_text("Preface\n\nChapter 1\nHello.\n\nChapter 2\nWorld.\n", encoding="utf-8")
    result = Converter().convert(source)
    assert len(result.document.sections) == 3
    assert "# Chapter 1" in result.ssmd
    assert "# Chapter 2" in result.ssmd
    assert 'ssmd_version: "0.9"' in result.ssmd or "ssmd_version: '0.9'" in result.ssmd

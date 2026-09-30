from __future__ import annotations

from pathlib import Path

import pytest
from epub_support import make_epub

from ssmdconvert import ConversionResult, Converter
from ssmdconvert.epub_options import default_epub_chapter_options
from ssmdconvert.errors import SSMDConvertError


def test_epub_is_standalone_and_follows_navigation_and_spine(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    result = Converter().convert(source)

    assert isinstance(result, ConversionResult)
    assert result.document.metadata["title"] == "Demo Book"
    assert result.document.metadata["author"] == "A. Author"
    assert result.document.metadata["language"] == "en"
    assert [section.title for section in result.document.sections] == ["One", "Two"]
    assert [section.level for section in result.document.sections] == [1, 1]
    assert [section.source_ref for section in result.document.sections] == ["c1.xhtml", "c2.xhtml"]
    assert "# One" in result.ssmd and "# Two" in result.ssmd
    assert result.ssmd.index("Hello") < result.ssmd.index("World")
    assert "## Opening" in result.ssmd
    assert "*emphasis*" in result.ssmd
    assert "**strong**" in result.ssmd
    assert "*CSS emphasis*" in result.ssmd
    assert "\n---\n" in result.ssmd
    assert "世界" in result.ssmd


def test_epub_spine_fallback_is_in_source_order(tmp_path: Path) -> None:
    source = tmp_path / "fallback.epub"
    make_epub(source, with_navigation=False)

    result = Converter().convert(source)

    assert len(result.document.sections) == 2
    assert result.ssmd.index("Hello") < result.ssmd.index("World")


def test_epub_chapter_options_are_centralized() -> None:
    from epub2text import ChapterMarkdownOptions

    assert default_epub_chapter_options() == ChapterMarkdownOptions(
        include_title=False,
        minimum_body_heading_level=2,
        preserve_emphasis=True,
        preserve_strong=True,
        link_mode="preserve",
        code_mode="preserve",
        resolve_css_emphasis=True,
        preserve_scene_breaks=True,
    )


def test_malformed_epub_has_a_contextual_conversion_error(tmp_path: Path) -> None:
    source = tmp_path / "malformed.epub"
    source.write_bytes(b"not an EPUB")

    with pytest.raises(SSMDConvertError, match="malformed.epub"):
        Converter().convert(source)


def test_duplicate_visible_chapter_titles_are_not_deduplicated(tmp_path: Path) -> None:
    source = tmp_path / "duplicates.epub"
    make_epub(source, duplicate_visible_titles=True)

    result = Converter().convert(source)

    assert [section.title for section in result.document.sections] == ["One", "One"]
    assert [section.source_ref for section in result.document.sections] == [
        "c1.xhtml",
        "c2.xhtml",
    ]
    assert result.ssmd.index("Hello") < result.ssmd.index("World")


def test_empty_spine_items_do_not_disrupt_chapter_order(tmp_path: Path) -> None:
    source = tmp_path / "empty-spine-item.epub"
    make_epub(source, include_empty_spine_item=True)

    result = Converter().convert(source)

    assert [section.source_ref for section in result.document.sections] == [
        "c1.xhtml",
        "c2.xhtml",
    ]
    assert result.ssmd.index("Hello") < result.ssmd.index("World")

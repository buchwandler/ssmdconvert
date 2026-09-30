from __future__ import annotations

from pathlib import Path

import pytest
from epub_support import make_epub

from ssmdconvert import BookError, BookInspection, UnsupportedBookSourceError, inspect_book


def test_inspect_book_preserves_order_metadata_and_source_provenance(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    inspection = inspect_book(source)

    assert isinstance(inspection, BookInspection)
    assert inspection.source == source.resolve()
    assert inspection.source_format == "epub"
    assert inspection.metadata == {
        "title": "Demo Book",
        "language": "en",
        "identifier": "demo-id",
        "authors": ["A. Author"],
        "publisher": "Demo Press",
    }
    assert [chapter.source_number for chapter in inspection.chapters] == [1, 2]
    assert [chapter.id for chapter in inspection.chapters] == ["chapter-0001", "chapter-0002"]
    assert [chapter.title for chapter in inspection.chapters] == ["One", "Two"]
    assert all(
        chapter.source_id and chapter.source_id.startswith("nav:")
        for chapter in inspection.chapters
    )
    assert [chapter.href for chapter in inspection.chapters] == ["c1.xhtml", "c2.xhtml"]
    assert [chapter.parent_id for chapter in inspection.chapters] == [None, None]
    assert [chapter.level for chapter in inspection.chapters] == [1, 1]
    assert all(chapter.char_count and chapter.char_count > 0 for chapter in inspection.chapters)
    assert all(isinstance(chapter.diagnostics, tuple) for chapter in inspection.chapters)


def test_inspect_book_preserves_nested_navigation_hierarchy(tmp_path: Path) -> None:
    source = tmp_path / "nested.epub"
    make_epub(source, nested_navigation=True)

    chapters = inspect_book(source).chapters

    assert [chapter.source_number for chapter in chapters] == [1, 2, 3, 4]
    assert [chapter.title for chapter in chapters] == ["Part One", "One", "Two", "Three"]
    assert [chapter.level for chapter in chapters] == [1, 2, 2, 1]
    assert chapters[0].parent_id is None
    assert chapters[1].parent_id == chapters[0].source_id
    assert chapters[2].parent_id == chapters[0].source_id
    assert chapters[3].parent_id is None


def test_inspect_book_rejects_missing_and_unsupported_sources(tmp_path: Path) -> None:
    with pytest.raises(BookError, match="regular file"):
        inspect_book(tmp_path / "missing.epub")

    source = tmp_path / "source.txt"
    source.write_text("not an EPUB", encoding="utf-8")
    with pytest.raises(UnsupportedBookSourceError, match="unsupported book source format"):
        inspect_book(source)

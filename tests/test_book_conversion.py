from __future__ import annotations

from pathlib import Path

from epub_support import make_epub
from ssmd import lint

from ssmdconvert import Book, BookChapter, Converter, convert_book


def test_convert_book_renders_valid_standalone_chapters(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    book = convert_book(source)

    assert isinstance(book, Book)
    assert book.source.path == source.resolve()
    assert book.source.format == "epub"
    assert book.metadata["title"] == "Demo Book"
    assert book.source_chapter_count == 2
    assert [chapter.source_number for chapter in book.chapters] == [1, 2]
    assert [chapter.id for chapter in book.chapters] == ["chapter-0001", "chapter-0002"]
    assert [chapter.title for chapter in book.chapters] == ["One", "Two"]
    assert [chapter.href for chapter in book.chapters] == ["c1.xhtml", "c2.xhtml"]
    assert all(isinstance(chapter, BookChapter) for chapter in book.chapters)

    first = book.chapters[0]
    assert "title: One" in first.ssmd
    assert "language: en" in first.ssmd
    assert "author: A. Author" in first.ssmd
    assert "# One" in first.ssmd
    assert "Hello" in first.ssmd and "世界" in first.ssmd
    assert "*emphasis*" in first.ssmd
    assert "**strong**" in first.ssmd
    assert not [
        issue
        for issue in lint(first.ssmd, profile="ssmd-core", dialect="0.9")
        if issue.severity == "error"
    ]
    assert "# Two" in book.chapters[1].ssmd
    assert "World." in book.chapters[1].ssmd


def test_convert_book_selection_preserves_source_numbers(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    book = Converter().convert_book(source, chapters="2")

    assert book.source_chapter_count == 2
    assert len(book.chapters) == 1
    assert book.chapters[0].source_number == 2
    assert book.chapters[0].id == "chapter-0002"
    assert book.chapters[0].title == "Two"

from __future__ import annotations

import json
from pathlib import Path

from epub_support import make_epub
from ssmd import lint

from ssmdconvert import (
    Book,
    BookChapter,
    Converter,
    SpeechPreparationOptions,
    convert_book,
    load_book_bundle,
    write_book_bundle,
)


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


def test_book_speech_is_chapter_scoped_and_keeps_bundle_schema(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source, chapter_one_suffix=" ☯")
    baseline = convert_book(source)
    assert baseline.speech_reports == {}
    speech_options = SpeechPreparationOptions(
        mode="annotate",
        pronunciations={"Hello": "greetings", "World": "planet"},
    )

    book = Converter().convert_book(source, chapters="2,1", speech_options=speech_options)
    assert [chapter.source_number for chapter in book.chapters] == [1, 2]
    assert [chapter.id for chapter in book.chapters] == ["chapter-0001", "chapter-0002"]
    assert book.metadata == baseline.metadata
    assert book.source_chapter_count == baseline.source_chapter_count
    assert '[Hello]{sub="greetings"}' in book.chapters[0].ssmd
    assert '[World]{sub="planet"}' in book.chapters[1].ssmd
    assert tuple(book.speech_reports) == ("chapter-0001", "chapter-0002")
    assert book.speech_reports["chapter-0001"].issues[0].code == "speech.residual_symbol"
    assert any(item["code"] == "speech.residual_symbol" for item in book.chapters[0].diagnostics)

    baseline_bundle = write_book_bundle(baseline, tmp_path / "baseline.ssmdbook")
    speech_bundle = write_book_bundle(book, tmp_path / "speech.ssmdbook")
    baseline_manifest = json.loads((baseline_bundle / "manifest.json").read_text(encoding="utf-8"))
    speech_manifest = json.loads((speech_bundle / "manifest.json").read_text(encoding="utf-8"))
    assert set(speech_manifest) == set(baseline_manifest)
    assert set(speech_manifest["chapters"][0]) == set(baseline_manifest["chapters"][0])
    assert "speech_reports" not in speech_manifest
    loaded = load_book_bundle(speech_bundle)
    assert [chapter.ssmd for chapter in loaded.chapters] == [
        chapter.ssmd for chapter in book.chapters
    ]
    assert loaded.speech_reports == {}

    selected = Converter().convert_book(
        source,
        chapters="2",
        speech_options=speech_options,
    )
    assert tuple(selected.speech_reports) == ("chapter-0002",)
    assert [chapter.source_number for chapter in selected.chapters] == [2]

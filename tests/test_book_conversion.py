from pathlib import Path

from epub_support import make_epub
from ssmd import lint, parse_structure

from ssmdconvert import Book, BookChapter, convert_book
from ssmdconvert.metadata import PORTABLE_SSMD_METADATA_KEYS
from ssmdconvert.render import validate_ssmd_document


def test_convert_book_renders_valid_standalone_chapters(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    book = convert_book(source)

    assert isinstance(book, Book)
    assert book.source.path == source.resolve()
    assert book.source.format == "epub"
    assert book.source.name == source.name
    assert book.source.media_type == "application/epub+zip"
    assert len(book.source_sha256) == 64
    assert all(character in "0123456789abcdef" for character in book.source_sha256)
    assert not hasattr(book, "source_name")
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

    book = convert_book(source, chapters="2")

    assert book.source_chapter_count == 2
    assert len(book.chapters) == 1
    assert book.chapters[0].source_number == 2
    assert book.chapters[0].id == "chapter-0002"
    assert book.chapters[0].title == "Two"


def test_convert_book_persists_default_sequence_fallback_mode(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    book = convert_book(source)

    assert book.metadata["sequence_fallback_mode"] == "preserve"
    for chapter in book.chapters:
        header = parse_structure(chapter.ssmd, dialect="0.9").header
        assert header["sequence_fallback_mode"] == "preserve"


def test_convert_book_persists_explicit_preserve_sequence_fallback_mode(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    book = convert_book(source, sequence_fallback_mode="preserve")

    assert book.metadata["sequence_fallback_mode"] == "preserve"
    for chapter in book.chapters:
        header = parse_structure(chapter.ssmd, dialect="0.9").header
        assert header["sequence_fallback_mode"] == "preserve"


def test_convert_book_language_override_and_absent_source_language(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    source_language = convert_book(source)
    assert source_language.metadata["language"] == "en"
    assert all(
        parse_structure(chapter.ssmd, dialect="0.9").header["language"] == "en"
        for chapter in source_language.chapters
    )

    overridden = convert_book(source, language="de-DE")
    assert overridden.metadata["language"] == "de-DE"
    assert all(
        parse_structure(chapter.ssmd, dialect="0.9").header["language"] == "de-DE"
        for chapter in overridden.chapters
    )

    no_language_source = tmp_path / "no-language.epub"
    make_epub(no_language_source, language=None)
    absent = convert_book(no_language_source)
    assert "language" not in absent.metadata
    assert all(
        "language" not in parse_structure(chapter.ssmd, dialect="0.9").header
        for chapter in absent.chapters
    )

    supplied = convert_book(no_language_source, language="fr-FR")
    assert supplied.metadata["language"] == "fr-FR"
    assert all(
        parse_structure(chapter.ssmd, dialect="0.9").header["language"] == "fr-FR"
        for chapter in supplied.chapters
    )


def test_convert_book_mirrors_all_portable_metadata_into_valid_chapters(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    metadata = {
        "language": "de-DE",
        "sequence_fallback_mode": "preserve",
        "voice_bindings": {},
        "voice_defaults": {},
        "pause_defaults": {},
        "prosody_transitions": {},
        "language_detection": {"mode": "auto", "languages": ["en", "fr"]},
        "requires": {"extensions": ["amazon.whisper"]},
    }

    book = convert_book(source, metadata_overrides=metadata)

    for chapter in book.chapters:
        validate_ssmd_document(chapter.ssmd)
        header = parse_structure(chapter.ssmd, dialect="0.9").header
        for key in PORTABLE_SSMD_METADATA_KEYS:
            assert header[key] == metadata[key]

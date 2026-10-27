from __future__ import annotations

from pathlib import Path

import pytest
from epub_support import make_epub
from ssmd import parse_structure

from ssmdconvert import Book
from ssmdconvert.bundle import (
    convert_bundle,
    inspect_bundle_source,
    load_bundle,
    validate_bundle,
)
from ssmdconvert.errors import BundleIdentityError
from ssmdconvert.results import BookConversionResult

VALID_SSMD = '---\nssmd_version: "0.9"\ntitle: "Story"\n---\n\nHello.\n'


def test_convert_document_source_uses_canonical_bundle_lifecycle(tmp_path: Path) -> None:
    source = tmp_path / "story.md"
    source.write_text("# Story\n\nHello world.\n", encoding="utf-8")

    result = convert_bundle(source)

    assert result.kind == "document"
    assert result.output == tmp_path / "story.ssmd-bundle"
    assert load_bundle(result.output).kind == "document"
    assert validate_bundle(result.output) == "document"
    assert inspect_bundle_source(source).kind == "document"
    assert inspect_bundle_source(result.output).kind == "document"


def test_public_book_conversion_bundle_contains_frozen_speech_aliases(tmp_path: Path) -> None:
    source = tmp_path / "speech.epub"
    make_epub(
        source,
        chapter_one_suffix=(
            " Because someone (ART) approved it. ART’s module stayed open. "
            "Later ART checked the open/close control and asked where/who. "
            "target/destination head/processor torus/whatever we/somebody "
            "where/who proximity/safety"
        ),
    )
    output = tmp_path / "frozen.ssmd-bundle"

    converted = convert_bundle(source, output=output, chapters="1")

    assert converted.kind == "book"
    assert converted.output == output
    frozen = load_bundle(output)
    assert frozen.kind == "book"
    assert isinstance(frozen.value, Book)
    chapter = frozen.value.chapters[0]
    for alias in (
        '[ART]{sub="A R T"}',
        '[ART’s]{sub="A R T’s"}',
        '[open/close]{sub="open slash close"}',
        '[where/who]{sub="where slash who"}',
        '[target/destination]{sub="target slash destination"}',
        '[head/processor]{sub="head slash processor"}',
        '[torus/whatever]{sub="torus slash whatever"}',
        '[we/somebody]{sub="we slash somebody"}',
        '[proximity/safety]{sub="proximity slash safety"}',
    ):
        assert alias in chapter.ssmd
    clean_text = parse_structure(chapter.ssmd, dialect="0.9", normalize=False).clean_text
    assert "Because someone (ART) approved it. ART’s module stayed open." in clean_text
    assert "Later ART checked the open/close control and asked where/who." in clean_text


def test_convert_standalone_ssmd_source_uses_stem_without_double_extension(
    tmp_path: Path,
) -> None:
    source = tmp_path / "story.ssmd.md"
    source.write_text(VALID_SSMD, encoding="utf-8")

    result = convert_bundle(source)

    assert result.output == tmp_path / "story.ssmd-bundle"
    assert load_bundle(result.output).kind == "document"


def test_epub_conversion_uses_same_command_and_chapter_selection(tmp_path: Path) -> None:
    source = tmp_path / "novel.epub"
    make_epub(source)

    result = convert_bundle(source, chapters="1", speech_semantics="preserve")

    assert result.kind == "book"
    assert isinstance(result.value, BookConversionResult)
    assert len(result.value.book.chapters) == 1
    assert result.output == tmp_path / "novel.ssmd-bundle"
    assert load_bundle(result.output).kind == "book"
    assert inspect_bundle_source(source).kind == "book"


def test_document_chapter_selector_and_noncanonical_output_are_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "story.md"
    source.write_text("Story text.", encoding="utf-8")

    with pytest.raises(ValueError, match="only available for book sources"):
        convert_bundle(source, chapters="2")
    with pytest.raises(BundleIdentityError, match="must end with '.ssmd-bundle'"):
        convert_bundle(source, output=tmp_path / "story.not-a-bundle")


def test_force_replaces_the_complete_workspace(tmp_path: Path) -> None:
    source = tmp_path / "story.md"
    source.write_text("First version.", encoding="utf-8")
    output = tmp_path / "published.ssmd-bundle"
    convert_bundle(source, output=output)
    (output / "stale.txt").write_text("stale", encoding="utf-8")
    source.write_text("Second version.", encoding="utf-8")

    convert_bundle(source, output=output, force=True)

    assert not (output / "stale.txt").exists()
    assert load_bundle(output).value.source.name == "story.md"


def test_package_exports_kind_neutral_bundle_lifecycle_only() -> None:
    import ssmdconvert

    assert callable(ssmdconvert.convert_bundle)
    assert callable(ssmdconvert.inspect_bundle_source)
    assert callable(ssmdconvert.load_bundle)
    assert callable(ssmdconvert.validate_bundle)
    for removed in (
        "load_book_bundle",
        "load_document_bundle",
        "write_book_bundle",
        "write_document_bundle",
        "validate_book_bundle",
        "validate_document_bundle",
    ):
        assert not hasattr(ssmdconvert, removed)

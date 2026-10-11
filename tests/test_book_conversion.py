from dataclasses import replace
from pathlib import Path

import pytest
import ttsready
from epub_support import make_epub
from ssmd import lint, parse_structure

from ssmdconvert import Book, BookChapter, convert_book
from ssmdconvert.analysis import analyze_ssmd_source, load_ssmd_source
from ssmdconvert.analysis.models import LoadedSsmdSection, LoadedSsmdSource
from ssmdconvert.analysis.units import extract_units
from ssmdconvert.books import render_standalone_chapter
from ssmdconvert.errors import MaterializationError
from ssmdconvert.metadata import PORTABLE_SSMD_METADATA_KEYS
from ssmdconvert.render import validate_ssmd_document
from ssmdconvert.speech.conversion import materialize_book_speech
from ssmdconvert.speech.workflows import materialize_analysis


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
    make_epub(no_language_source, language=None, chapter_language=None)
    absent = convert_book(no_language_source, speech_semantics="preserve")
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


def test_book_language_override_changes_base_but_not_inline_language(tmp_path: Path, monkeypatch):
    source = tmp_path / "book.epub"
    make_epub(source)

    def render_with_inline_language(_title, _markdown, metadata):
        return (
            '---\nssmd_version: "0.9"\ntitle: "Sample title"\n'
            f"language: {metadata['language']}\n---\n"
            'English [bonjour]{lang="fr-FR"} end.\n'
        )

    monkeypatch.setattr("ssmdconvert.books.render_standalone_chapter", render_with_inline_language)
    book = convert_book(source, language="de-DE", speech_semantics="preserve")

    chapter = book.chapters[0]
    structure = parse_structure(chapter.ssmd, dialect="0.9")
    assert structure.header["language"] == "de-DE"

    chapter_path = tmp_path / "chapter.ssmd"
    chapter_path.write_text(chapter.ssmd, encoding="utf-8")
    extracted = extract_units(load_ssmd_source(chapter_path), language="de-DE")
    assert [unit.language for unit in extracted.units if unit.role == "title"] == ["de-DE"]
    assert [unit.language for unit in extracted.units if unit.role == "prose"] == [
        "de-DE",
        "fr-FR",
        "de-DE",
    ]


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


def test_book_freeze_proves_narratable_epub_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "coverage.epub"
    suffix = (
        "</p><h2>1</h2><p>Measure 3–2–1, .02, 70s, 20, 2.0, "
        "Null+1, ART, et cetera. Closing sentence."
    )
    make_epub(source, chapter_one_suffix=suffix)
    original_renderer = render_standalone_chapter

    def render_with_multilingual_span(title, markdown, metadata):
        rendered = original_renderer(title, markdown, metadata)
        return rendered.replace(
            "Hello, 世界",
            'Hello [bonjour]{lang="fr-FR"}, 世界',
        )

    monkeypatch.setattr(
        "ssmdconvert.books.render_standalone_chapter",
        render_with_multilingual_span,
    )
    structural = convert_book(source, speech_semantics="preserve")
    assert all('{sub="' not in chapter.ssmd for chapter in structural.chapters)

    frozen = materialize_book_speech(structural, source_path=source)
    context_text = "\n".join(context.source_text for context in frozen.analysis.contexts)

    assert frozen.analysis.coverage.complete
    assert frozen.analysis.coverage.narratable_contexts == frozen.analysis.coverage.covered_contexts
    assert frozen.analysis.coverage.excluded_title_contexts == len(structural.chapters)
    assert "Opening" in context_text and "1" in context_text and "bonjour" in context_text
    assert "Closing sentence" in context_text and "3–2–1" in context_text
    assert "fr-FR" in frozen.analysis.effective_languages
    assert len(frozen.materialization.changes) == len(frozen.analysis.preparation.changes)
    assert all(
        change.final_disposition
        in {"applied", "already-authoritative", "author-owned", "unresolved"}
        for change in frozen.materialization.changes
    )
    assert frozen.materialization.summary.complete
    assert frozen.materialization.summary.unresolved == 0
    for structural_chapter, frozen_chapter in zip(
        structural.chapters, frozen.book.chapters, strict=True
    ):
        assert (
            parse_structure(structural_chapter.ssmd, dialect="0.9", normalize=False).clean_text
            == parse_structure(frozen_chapter.ssmd, dialect="0.9", normalize=False).clean_text
        )


def test_book_freeze_rejects_incomplete_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "coverage-gap.epub"
    make_epub(source)
    structural = convert_book(source, speech_semantics="preserve")
    original_analyze = analyze_ssmd_source

    def analyze_with_gap(loaded, **kwargs):
        analysis = original_analyze(loaded, **kwargs)
        coverage = replace(
            analysis.coverage,
            covered_contexts=analysis.coverage.covered_contexts - 1,
            uncovered_context_ids=("injected-gap",),
        )
        return replace(analysis, coverage=coverage)

    monkeypatch.setattr("ssmdconvert.speech.conversion.analyze_ssmd_source", analyze_with_gap)
    with pytest.raises(MaterializationError, match="coverage"):
        materialize_book_speech(structural, source_path=source)


def test_convert_book_freezes_upstream_speech_decisions_by_default(tmp_path: Path) -> None:
    source = tmp_path / "speech-book.epub"
    body = (
        " <em>Initiate in 3–2–1</em>. Three hesitated for .02 seconds. "
        "There was a chance in the high 70s. We were on level 20. "
        "We had built Murderbot 2.0. Target Null+1 on approach."
        "</p><h2>1</h2><p>Closing sentence."
    )
    make_epub(source, chapter_one_suffix=body)

    structural = convert_book(source, speech_semantics="preserve")
    frozen = convert_book(source)
    before = structural.chapters[0]
    after = frozen.chapters[0]

    assert after.id == before.id
    assert '[3–2–1]{sub="three - two - one"}' in after.ssmd
    assert '[.02]{sub="point zero two"}' in after.ssmd
    assert '[70s]{sub="seventies"}' in after.ssmd
    assert '[20]{sub="twenty"}' in after.ssmd
    assert '*Initiate in [3–2–1]{sub="three - two - one"}*' in after.ssmd
    assert '## [1]{sub="one"}' in after.ssmd
    validate_ssmd_document(after.ssmd)
    assert (
        parse_structure(after.ssmd, dialect="0.9", normalize=False).clean_text
        == parse_structure(before.ssmd, dialect="0.9", normalize=False).clean_text
    )

    upstream_version = ttsready.prepare_text("Murderbot 2.0", language="en-US")
    version_change = next(
        (change for change in upstream_version.changes if change.source == "2.0"),
        None,
    )
    if version_change is None:
        assert "Murderbot 2.0" in after.ssmd
    else:
        assert f'[2.0]{{sub="{version_change.replacement}"}}' in after.ssmd

    upstream_identifier = ttsready.prepare_text("Target Null+1", language="en-US")
    identifier_change = next(
        (change for change in upstream_identifier.changes if change.source == "Null+1"),
        None,
    )
    if identifier_change is None:
        assert "Target Null+1" in after.ssmd
    else:
        assert f'[Null+1]{{sub="{identifier_change.replacement}"}}' in after.ssmd

    frozen_path = tmp_path / "frozen-chapter.ssmd"
    frozen_path.write_text(after.ssmd, encoding="utf-8")
    analysis = analyze_ssmd_source(frozen_path, include_titles=False)
    second = materialize_analysis(analysis).section_ssmd[analysis.sections[0].id]
    assert second == after.ssmd


def test_convert_book_freeze_requires_language_and_preserve_does_not(tmp_path: Path) -> None:
    source = tmp_path / "unresolved.epub"
    make_epub(source, language=None, chapter_language=None)

    with pytest.raises(MaterializationError, match="cannot freeze speech semantics"):
        convert_book(source)

    preserved = convert_book(source, speech_semantics="preserve")
    assert len(preserved.chapters) == 2
    assert "language" not in preserved.metadata


def test_convert_book_freezing_only_returns_the_selected_source_chapters(tmp_path: Path) -> None:
    source = tmp_path / "selected.epub"
    make_epub(source, chapter_one_suffix=" 3–2–1.")

    book = convert_book(source, chapters="2")

    assert book.source_chapter_count == 2
    assert [chapter.source_number for chapter in book.chapters] == [2]
    assert [chapter.id for chapter in book.chapters] == ["chapter-0002"]
    assert "3–2–1" not in book.chapters[0].ssmd


def test_conversion_materialization_respects_existing_author_semantics(tmp_path: Path) -> None:
    original = (
        '---\nssmd_version: "0.9"\nlanguage: en-US\n---\n'
        '[20]{sub="twenty"}. [123]{as="digits"}. '
        '[word]{phoneme="W ER D"}. [text]{lang="en-US"}. '
        '[5]{tts-provider="author"}.\n'
    )
    loaded = LoadedSsmdSource(
        path=tmp_path / "author.ssmd",
        kind="ssmd",
        input_format="ssmd",
        title=None,
        metadata={"language": "en-US"},
        sections=(
            LoadedSsmdSection(
                id="document-0001",
                index=1,
                title=None,
                level=1,
                ssmd=original,
            ),
        ),
        source_sha256="1" * 64,
        content_fingerprint="2" * 64,
        workspace_type="standalone",
        workspace_status="valid",
    )

    analysis = analyze_ssmd_source(loaded, include_titles=False)
    materialized = materialize_analysis(analysis).section_ssmd[analysis.sections[0].id]

    assert materialized == original
    assert materialized.count("{sub=") == 1
    assert '[123]{as="digits"}' in materialized
    assert '[word]{phoneme="W ER D"}' in materialized
    assert '[text]{lang="en-US"}' in materialized
    assert '[5]{tts-provider="author"}' in materialized


def test_materialize_book_speech_returns_immutable_analysis_backed_book(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source, chapter_one_suffix=" Initiate in 3–2–1.")
    book = convert_book(source, speech_semantics="preserve")

    result = materialize_book_speech(
        book,
        source_path=source,
        language="en-US",
    )

    assert result.book is not book
    assert result.book.chapters[0] is not book.chapters[0]
    assert "Initiate in 3–2–1" in book.chapters[0].ssmd
    assert '[3–2–1]{sub="three - two - one"}' in result.book.chapters[0].ssmd
    assert result.analysis.source.workspace_type == "generated"
    assert result.analysis.sections[0].id == book.chapters[0].id


def test_book_progress_counts_selected_chapters_and_propagates_callback_errors(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    events = []

    book = convert_book(source, speech_semantics="preserve", on_progress=events.append)

    assert len(book.chapters) == 2
    rendered = [
        event
        for event in events
        if event.phase == "book.chapter.render" and event.kind == "chapter.completed"
    ]
    assert [event.completed for event in rendered] == [1, 2]
    assert [event.chapter_id for event in rendered] == ["chapter-0001", "chapter-0002"]
    assert any(
        event.kind == "phase.started" and event.phase == "book.epub.load" for event in events
    )
    assert any(
        event.kind == "phase.completed" and event.phase == "book.chapter.render" for event in events
    )

    def cancel(event):
        if event.kind == "chapter.started":
            raise ValueError("stop book conversion")

    with pytest.raises(ValueError, match="stop book conversion"):
        convert_book(source, speech_semantics="preserve", on_progress=cancel)

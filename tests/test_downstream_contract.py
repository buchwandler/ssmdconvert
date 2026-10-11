from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from ssmd import parse_structure

from ssmdconvert import Book, BookChapter, BookInspection, BookInspectionChapter, SourceInfo
from ssmdconvert.analysis.prepare import analyze_ssmd_source
from ssmdconvert.speech.workflows import materialize_analysis


def _field_names(model: type[object]) -> list[str]:
    return [item.name for item in fields(model)]


def test_public_source_and_book_model_field_contract() -> None:
    assert _field_names(SourceInfo) == ["format", "media_type", "path", "name"]
    assert _field_names(Book) == [
        "source",
        "metadata",
        "chapters",
        "source_sha256",
        "source_chapter_count",
        "speech_semantics",
    ]
    assert _field_names(BookChapter) == [
        "id",
        "source_number",
        "title",
        "ssmd",
        "source_id",
        "href",
        "source_parent_id",
        "parent_id",
        "level",
        "char_count",
        "diagnostics",
    ]
    assert _field_names(BookInspection) == ["source", "metadata", "chapters"]
    assert _field_names(BookInspectionChapter) == [
        "id",
        "source_number",
        "title",
        "source_id",
        "href",
        "source_parent_id",
        "parent_id",
        "level",
        "char_count",
        "diagnostics",
    ]


def test_obsolete_provenance_fields_are_not_exposed() -> None:
    assert "source_name" not in _field_names(Book)
    assert "source_format" not in _field_names(BookInspection)
    assert "bundle_path" not in _field_names(BookChapter)


def test_reviewed_ssmd_handoff_fixture_preserves_visible_text_and_aliases() -> None:
    fixture = Path(__file__).parent / "fixtures" / "ssmd-speech-handoff" / "reviewed.ssmd"
    analysis = analyze_ssmd_source(fixture)
    result = materialize_analysis(analysis)
    frozen = result.section_ssmd[analysis.sections[0].id]
    before = parse_structure(analysis.sections[0].ssmd, dialect="0.9", normalize=False)
    after = parse_structure(frozen, dialect="0.9", normalize=False)

    assert result.summary.complete
    assert result.summary.unresolved == 0
    assert analysis.coverage.complete
    assert before.clean_text == after.clean_text
    assert "ART" in after.clean_text and ".02" in after.clean_text
    assert '[ART]{sub="A R T"}' in frozen
    assert '[.02]{sub="point zero two"}' in frozen

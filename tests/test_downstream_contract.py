from __future__ import annotations

from dataclasses import fields

from ssmdconvert import Book, BookChapter, BookInspection, BookInspectionChapter, SourceInfo


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

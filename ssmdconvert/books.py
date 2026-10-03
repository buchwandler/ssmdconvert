from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._epub import ExtractedChapter, load_epub
from .chapter_selection import parse_chapter_selection
from .errors import BookError
from .metadata import merge_document_metadata
from .models import Book, BookChapter, BookInspection, BookInspectionChapter, SourceInfo
from .policy import DEFAULT_SEQUENCE_FALLBACK_MODE, SequenceFallbackMode
from .render import render_standalone_chapter


def _source_info(path: Path) -> SourceInfo:
    return SourceInfo(
        format="epub",
        media_type="application/epub+zip",
        path=path,
        name=path.name,
    )


def _inspection_chapter(chapter: ExtractedChapter) -> BookInspectionChapter:
    return BookInspectionChapter(
        id=chapter.id,
        source_number=chapter.source_number,
        title=chapter.title,
        source_id=chapter.source_id,
        href=chapter.href,
        source_parent_id=chapter.source_parent_id,
        parent_id=chapter.parent_id,
        level=chapter.level,
        char_count=chapter.char_count,
        diagnostics=chapter.diagnostics,
    )


def _inspect_epub(source: str | Path) -> tuple[BookInspection, tuple[ExtractedChapter, ...]]:
    extracted = load_epub(source)
    inspection = BookInspection(
        source=_source_info(extracted.source),
        metadata=extracted.metadata,
        chapters=tuple(_inspection_chapter(chapter) for chapter in extracted.chapters),
    )
    return inspection, extracted.chapters


def inspect_book(source: str | Path) -> BookInspection:
    """Return EPUB metadata and its ordered source chapter inventory."""
    inspection, _chapters = _inspect_epub(source)
    return inspection


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise BookError(f"could not hash source EPUB {path}: {exc}") from exc
    return digest.hexdigest()


def convert_book(
    source: str | Path,
    *,
    chapters: str | None = "all",
    language: str | None = None,
    metadata_overrides: Mapping[str, Any] | None = None,
    sequence_fallback_mode: SequenceFallbackMode = DEFAULT_SEQUENCE_FALLBACK_MODE,
) -> Book:
    """Convert selected EPUB chapters to standalone SSMD in source order."""
    inspection, extracted_chapters = _inspect_epub(source)
    metadata = merge_document_metadata(
        inspection.metadata,
        metadata_overrides=metadata_overrides,
        language=language,
        sequence_fallback_mode=sequence_fallback_mode,
    )
    source_path = inspection.source.path
    assert source_path is not None
    source_sha256 = _source_sha256(source_path)
    selected_numbers = parse_chapter_selection(
        chapters,
        available_numbers=tuple(chapter.source_number for chapter in inspection.chapters),
    )
    selected = set(selected_numbers)
    book_chapters: list[BookChapter] = []

    for chapter in extracted_chapters:
        if chapter.source_number not in selected:
            continue
        try:
            ssmd = render_standalone_chapter(chapter.title, chapter.markdown, metadata)
        except ValueError as exc:
            raise BookError(
                f"generated SSMD for source chapter {chapter.source_number} is invalid: {exc}"
            ) from exc
        book_chapters.append(
            BookChapter(
                id=chapter.id,
                source_number=chapter.source_number,
                title=chapter.title,
                ssmd=ssmd,
                source_id=chapter.source_id,
                href=chapter.href,
                source_parent_id=chapter.source_parent_id,
                parent_id=chapter.parent_id,
                level=chapter.level,
                char_count=chapter.char_count,
                diagnostics=chapter.diagnostics,
            )
        )

    return Book(
        source=inspection.source,
        metadata=metadata,
        chapters=tuple(book_chapters),
        source_sha256=source_sha256,
        source_chapter_count=len(inspection.chapters),
    )

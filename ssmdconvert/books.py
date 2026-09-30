from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from epub2text import ChapterDocument, EPUBParser, Metadata

from .chapter_selection import parse_chapter_selection
from .epub_options import default_epub_chapter_options
from .errors import BookError, UnsupportedBookSourceError
from .models import (
    Book,
    BookChapter,
    BookInspection,
    BookInspectionChapter,
    SourceInfo,
)
from .render import render_standalone_chapter


def _source_metadata(value: Metadata) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("title", "language", "publisher", "identifier"):
        item = getattr(value, key)
        if item:
            metadata[key] = item
    if value.authors:
        metadata["authors"] = list(value.authors)
    return metadata


def _load_epub(
    source: str | Path,
) -> tuple[Path, dict[str, Any], list[ChapterDocument]]:
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise BookError(f"book source is not a regular file: {path}")
    if path.suffix.lower() != ".epub":
        raise UnsupportedBookSourceError(
            f"unsupported book source format: {path.suffix or '<none>'}"
        )

    try:
        parser = EPUBParser(str(path))
        documents = parser.get_chapter_documents(options=default_epub_chapter_options())
        metadata = _source_metadata(parser.get_metadata())
    except (OSError, ValueError) as exc:
        raise BookError(f"could not inspect EPUB {path.name}: {exc}") from exc
    if not documents:
        raise BookError(f"EPUB did not yield any readable chapters: {path.name}")
    return path, metadata, documents


def _inspection_chapters(
    documents: list[ChapterDocument],
) -> tuple[BookInspectionChapter, ...]:
    return tuple(
        BookInspectionChapter(
            id=f"chapter-{number:04d}",
            source_number=number,
            title=str(document.title or f"Chapter {number}"),
            source_id=str(document.id),
            href=document.href,
            parent_id=document.parent_id,
            level=int(document.level),
            char_count=int(document.char_count),
            diagnostics=tuple(asdict(item) for item in document.diagnostics),
        )
        for number, document in enumerate(documents, start=1)
    )


def _inspect_epub(
    source: str | Path,
) -> tuple[BookInspection, list[ChapterDocument]]:
    path, metadata, documents = _load_epub(source)
    inspection = BookInspection(
        source=path,
        source_format="epub",
        metadata=metadata,
        chapters=_inspection_chapters(documents),
    )
    return inspection, documents


def inspect_book(source: str | Path) -> BookInspection:
    """Return EPUB metadata and its ordered source chapter inventory."""
    inspection, _documents = _inspect_epub(source)
    return inspection


def convert_book(
    source: str | Path,
    *,
    chapters: str | None = "all",
) -> Book:
    """Convert selected EPUB chapters to standalone SSMD in source order."""
    inspection, source_documents = _inspect_epub(source)
    selected_numbers = parse_chapter_selection(
        chapters,
        available_numbers=tuple(chapter.source_number for chapter in inspection.chapters),
    )
    selected = set(selected_numbers)
    book_chapters: list[BookChapter] = []

    for chapter, source_document in zip(inspection.chapters, source_documents, strict=True):
        if chapter.source_number not in selected:
            continue
        markdown = source_document.to_markdown(include_title=True, title_level=1)
        try:
            ssmd = render_standalone_chapter(chapter.title, markdown, inspection.metadata)
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
                parent_id=chapter.parent_id,
                level=chapter.level,
                char_count=chapter.char_count,
                diagnostics=chapter.diagnostics,
            )
        )

    return Book(
        source=SourceInfo(inspection.source, "epub", "application/epub+zip"),
        metadata=inspection.metadata,
        chapters=tuple(book_chapters),
        source_chapter_count=len(inspection.chapters),
    )

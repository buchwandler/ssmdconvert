"""Canonical private EPUB extraction backend."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from epub2text import ChapterDocument, ChapterMarkdownOptions, EPUBParser, Metadata

from .errors import BookError, UnsupportedBookSourceError


@dataclass(frozen=True, slots=True)
class ExtractedChapter:
    id: str
    source_number: int
    title: str
    markdown: str
    source_id: str | None
    source_parent_id: str | None
    parent_id: str | None
    href: str | None
    level: int
    char_count: int
    diagnostics: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class ExtractedEpub:
    source: Path
    metadata: dict[str, Any]
    chapters: tuple[ExtractedChapter, ...]


def _chapter_markdown_options() -> ChapterMarkdownOptions:
    return ChapterMarkdownOptions(
        include_title=False,
        minimum_body_heading_level=2,
        preserve_emphasis=True,
        preserve_strong=True,
        link_mode="unwrap",
        code_mode="preserve",
        resolve_css_emphasis=True,
        preserve_scene_breaks=True,
    )


def _source_metadata(value: Metadata, source: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {"title": value.title or source.stem}
    if value.authors:
        metadata["authors"] = list(value.authors)
    for key in ("language", "publisher", "identifier"):
        item = getattr(value, key)
        if item:
            metadata[key] = item
    return metadata


def _extract_chapter(number: int, document: ChapterDocument) -> ExtractedChapter:
    return ExtractedChapter(
        id=f"chapter-{number:04d}",
        source_number=number,
        title=str(document.title or f"Chapter {number}"),
        markdown=document.to_markdown(include_title=True, title_level=1),
        source_id=str(document.id) if document.id is not None else None,
        source_parent_id=(str(document.parent_id) if document.parent_id is not None else None),
        parent_id=None,
        href=document.href,
        level=int(document.level),
        char_count=int(document.char_count),
        diagnostics=tuple(asdict(item) for item in document.diagnostics),
    )


def load_epub(source: str | Path) -> ExtractedEpub:
    """Extract EPUB metadata and ordered chapter documents once for all projections."""
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise BookError(f"book source is not a regular file: {path}")
    if path.suffix.lower() != ".epub":
        raise UnsupportedBookSourceError(
            f"unsupported book source format: {path.suffix or '<none>'}"
        )

    try:
        parser = EPUBParser(str(path))
        documents = parser.get_chapter_documents(options=_chapter_markdown_options())
        metadata = _source_metadata(parser.get_metadata(), path)
    except (OSError, ValueError) as exc:
        raise BookError(f"could not inspect EPUB {path.name}: {exc}") from exc
    if not documents:
        raise BookError(f"EPUB did not yield any readable chapters: {path.name}")

    extracted_chapters = tuple(
        _extract_chapter(number, document) for number, document in enumerate(documents, start=1)
    )
    source_ids = {
        chapter.source_id: chapter.id
        for chapter in extracted_chapters
        if chapter.source_id is not None
    }
    chapters = tuple(
        replace(chapter, parent_id=source_ids.get(chapter.source_parent_id))
        for chapter in extracted_chapters
    )
    return ExtractedEpub(source=path, metadata=metadata, chapters=chapters)

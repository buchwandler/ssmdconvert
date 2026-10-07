"""Canonical loading for standalone SSMD and SSMD book sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ssmd import parse_structure

from ..bundle import load_book_bundle, load_book_workspace
from ..errors import AnalysisSourceError
from ..models import Book, BookWorkspace
from ..render import validate_ssmd_document
from .fingerprints import content_fingerprint, sha256_bytes, sha256_file
from .models import LoadedSsmdSection, LoadedSsmdSource


def _title(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("title")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _book_source(
    path: Path,
    book: Book,
    *,
    workspace_type: str,
    workspace_status: str,
    dirty_chapters: tuple[str, ...] = (),
    artifact_sha256: str | None = None,
) -> LoadedSsmdSource:
    metadata = dict(book.metadata)
    sections: list[LoadedSsmdSection] = []
    hashes: list[tuple[str, str]] = []
    for index, chapter in enumerate(book.chapters, start=1):
        chapter_hash = sha256_bytes(chapter.ssmd.encode("utf-8"))
        hashes.append((chapter.id, chapter_hash))
        sections.append(
            LoadedSsmdSection(
                id=chapter.id,
                index=index,
                title=chapter.title or None,
                level=chapter.level,
                ssmd=chapter.ssmd,
                source_number=chapter.source_number,
                href=chapter.href,
                parent_id=chapter.parent_id,
                source_ref=chapter.href,
                chapter_sha256=chapter_hash,
            )
        )
    return LoadedSsmdSource(
        path=path,
        kind="ssmdbook",
        input_format="ssmdbook",
        title=_title(metadata),
        metadata=metadata,
        sections=tuple(sections),
        source_sha256=artifact_sha256 or book.source_sha256,
        content_fingerprint=content_fingerprint(hashes, metadata),
        workspace_type=workspace_type,  # type: ignore[arg-type]
        workspace_status=workspace_status,  # type: ignore[arg-type]
        dirty_chapters=dirty_chapters,
    )


def load_ssmd_source(source: str | Path) -> LoadedSsmdSource:
    """Load and validate a supported SSMD file, bundle, or editable workspace."""
    requested = Path(source).expanduser()
    try:
        path = requested.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AnalysisSourceError(
            f"SSMD source does not exist or cannot be resolved: {requested}: {exc}"
        ) from exc

    if path.is_dir():
        try:
            workspace: BookWorkspace = load_book_workspace(path)
        except Exception as exc:
            raise AnalysisSourceError(f"could not load SSMD book workspace {path}: {exc}") from exc
        dirty = tuple(chapter.id for chapter in workspace.chapters if chapter.dirty)
        return _book_source(
            path,
            workspace.book,
            workspace_type="directory",
            workspace_status="dirty" if workspace.dirty else "clean",
            dirty_chapters=dirty,
        )

    if not path.is_file():
        raise AnalysisSourceError(
            f"SSMD source is not a regular file or workspace directory: {path}"
        )

    lowered_name = path.name.lower()
    if lowered_name.endswith(".ssmdbook") or lowered_name.endswith(".ssmdbook.zip"):
        try:
            book = load_book_bundle(path)
        except Exception as exc:
            raise AnalysisSourceError(f"could not load SSMD book bundle {path}: {exc}") from exc
        return _book_source(
            path,
            book,
            workspace_type="zip",
            workspace_status="valid",
            artifact_sha256=sha256_file(path),
        )

    if not (lowered_name.endswith(".ssmd") or lowered_name.endswith(".ssmd.md")):
        raise AnalysisSourceError(
            f"unsupported SSMD source {path}; expected .ssmd, .ssmd.md, or .ssmdbook"
        )

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AnalysisSourceError(f"could not read SSMD source {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AnalysisSourceError(f"SSMD source is not valid UTF-8: {path}: {exc}") from exc
    try:
        validate_ssmd_document(text)
        structure = parse_structure(text, dialect="0.9", normalize=False)
    except Exception as exc:
        raise AnalysisSourceError(f"SSMD source is not valid SSMD 0.9: {path}: {exc}") from exc

    metadata = dict(structure.header)
    chapter_hash = sha256_bytes(raw)
    section = LoadedSsmdSection(
        id="document-0001",
        index=1,
        title=_title(metadata),
        level=1,
        ssmd=text,
        chapter_sha256=chapter_hash,
    )
    return LoadedSsmdSource(
        path=path,
        kind="ssmd",
        input_format="ssmd",
        title=_title(metadata),
        metadata=metadata,
        sections=(section,),
        source_sha256=chapter_hash,
        content_fingerprint=content_fingerprint(((section.id, chapter_hash),), metadata),
        workspace_type="standalone",
        workspace_status="valid",
    )

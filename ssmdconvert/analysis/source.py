"""Canonical loading for standalone SSMD and SSMD book sources."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ssmd import parse_structure

from ..bundle import load_bundle, load_bundle_workspace
from ..errors import AnalysisSourceError
from ..models import Book, BookWorkspace, DocumentWorkspace, SsmdDocument
from ..render import validate_ssmd_document
from .fingerprints import content_fingerprint, sha256_bytes, sha256_file
from .models import (
    LoadedSsmdSection,
    LoadedSsmdSource,
    WorkspaceStatus,
    WorkspaceType,
)


def _title(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("title")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_newlines(text: str) -> str:
    """Use LF internally so parsing and write-back are platform-independent."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def loaded_source_from_book(
    book: Book,
    *,
    path: Path,
    workspace_type: WorkspaceType,
    workspace_status: WorkspaceStatus,
    dirty_chapters: tuple[str, ...] = (),
    artifact_sha256: str | None = None,
    chapter_hashes: Mapping[str, str] | None = None,
) -> LoadedSsmdSource:
    """Adapt an in-memory book to the canonical SSMD analysis source model."""
    metadata = dict(book.metadata)
    sections: list[LoadedSsmdSection] = []
    hashes: list[tuple[str, str]] = []
    for index, chapter in enumerate(book.chapters, start=1):
        chapter_hash = (chapter_hashes or {}).get(chapter.id) or sha256_bytes(
            chapter.ssmd.encode("utf-8")
        )
        hashes.append((chapter.id, chapter_hash))
        sections.append(
            LoadedSsmdSection(
                id=chapter.id,
                index=index,
                title=chapter.title or None,
                level=chapter.level,
                ssmd=_normalize_newlines(chapter.ssmd),
                source_number=chapter.source_number,
                href=chapter.href,
                parent_id=chapter.parent_id,
                source_ref=chapter.href,
                chapter_sha256=chapter_hash,
            )
        )
    return LoadedSsmdSource(
        path=path,
        kind="bundle",
        input_format="ssmd-bundle",
        bundle_kind="book",
        title=_title(metadata),
        metadata=metadata,
        sections=tuple(sections),
        source_sha256=artifact_sha256 or book.source_sha256,
        content_fingerprint=content_fingerprint(hashes, metadata),
        workspace_type=workspace_type,
        workspace_status=workspace_status,
        dirty_chapters=dirty_chapters,
    )


def loaded_source_from_document(
    document: SsmdDocument,
    *,
    path: Path,
    workspace_type: WorkspaceType,
    workspace_status: WorkspaceStatus,
    dirty: bool = False,
    actual_sha256: str | None = None,
    artifact_sha256: str | None = None,
) -> LoadedSsmdSource:
    """Adapt a rendered document to the canonical one-section analysis source."""
    try:
        structure = parse_structure(document.ssmd, dialect="0.9", normalize=False)
    except Exception as exc:
        raise AnalysisSourceError(f"could not parse document metadata from {path}: {exc}") from exc
    metadata = dict(structure.header)
    metadata.pop("ssmd_version", None)
    document_sha256 = actual_sha256 or sha256_bytes(document.ssmd.encode("utf-8"))
    section = LoadedSsmdSection(
        id="document-0001",
        index=1,
        title=_title(metadata),
        level=1,
        ssmd=_normalize_newlines(document.ssmd),
        source_number=1,
        chapter_sha256=document_sha256,
    )
    return LoadedSsmdSource(
        path=path,
        kind="bundle",
        input_format="ssmd-bundle",
        bundle_kind="document",
        title=_title(metadata),
        metadata=metadata,
        sections=(section,),
        source_sha256=artifact_sha256 or document.source_sha256,
        content_fingerprint=content_fingerprint(((section.id, document_sha256),), metadata),
        workspace_type=workspace_type,
        workspace_status=workspace_status,
        dirty_chapters=(section.id,) if dirty else (),
    )


def load_ssmd_source(source: str | Path) -> LoadedSsmdSource:
    """Load standalone SSMD or a canonical bundle workspace/archive."""
    requested = Path(source).expanduser()
    try:
        path = requested.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AnalysisSourceError(
            f"SSMD source does not exist or cannot be resolved: {requested}: {exc}"
        ) from exc

    if path.is_dir():
        if not path.name.endswith(".ssmd-bundle"):
            raise AnalysisSourceError(f"expected an editable .ssmd-bundle workspace: {path}")
        try:
            workspace = load_bundle_workspace(path)
        except Exception as exc:
            raise AnalysisSourceError(
                f"could not load SSMD bundle workspace {path}: {exc}"
            ) from exc
        if workspace.kind == "document":
            document_workspace = workspace.value
            assert isinstance(document_workspace, DocumentWorkspace)
            return loaded_source_from_document(
                document_workspace.document,
                path=path,
                workspace_type="directory",
                workspace_status="dirty" if document_workspace.dirty else "clean",
                dirty=document_workspace.dirty,
                actual_sha256=document_workspace.status.actual_sha256,
            )
        book_workspace = workspace.value
        assert isinstance(book_workspace, BookWorkspace)
        dirty = tuple(chapter.id for chapter in book_workspace.chapters if chapter.dirty)
        chapter_hashes = {chapter.id: chapter.actual_sha256 for chapter in book_workspace.chapters}
        return loaded_source_from_book(
            book_workspace.book,
            path=path,
            workspace_type="directory",
            workspace_status="dirty" if book_workspace.dirty else "clean",
            dirty_chapters=dirty,
            chapter_hashes=chapter_hashes,
        )

    if not path.is_file():
        raise AnalysisSourceError(f"SSMD source is not a regular file: {path}")

    lowered_name = path.name.lower()
    if lowered_name.endswith(".ssmd-bundle.zip"):
        try:
            loaded = load_bundle(path)
        except Exception as exc:
            raise AnalysisSourceError(f"could not load packed SSMD bundle {path}: {exc}") from exc
        if loaded.kind == "document":
            assert isinstance(loaded.value, SsmdDocument)
            return loaded_source_from_document(
                loaded.value,
                path=path,
                workspace_type="zip",
                workspace_status="valid",
                artifact_sha256=sha256_file(path),
            )
        assert isinstance(loaded.value, Book)
        return loaded_source_from_book(
            loaded.value,
            path=path,
            workspace_type="zip",
            workspace_status="valid",
            artifact_sha256=sha256_file(path),
        )

    if not (lowered_name.endswith(".ssmd") or lowered_name.endswith(".ssmd.md")):
        raise AnalysisSourceError(
            f"unsupported SSMD source {path}; expected .ssmd, .ssmd.md, "
            ".ssmd-bundle, or .ssmd-bundle.zip"
        )

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AnalysisSourceError(f"could not read SSMD source {path}: {exc}") from exc
    try:
        text = _normalize_newlines(raw.decode("utf-8", errors="strict"))
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

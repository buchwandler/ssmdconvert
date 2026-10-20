"""Kind-neutral public API for canonical SSMD bundle workspaces."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from . import _book_bundle, _document_bundle
from .bundle_identity import (
    BundleKind,
    BundleStorage,
    default_bundle_archive_path,
    default_bundle_workspace_path,
    probe_bundle_kind,
    require_bundle_archive_path,
    require_bundle_workspace_path,
)
from .errors import BundleIdentityError
from .linguistics import SpacyPolicy
from .models import (
    Book,
    BookInspection,
    BookWorkspace,
    Document,
    DocumentWorkspace,
    SsmdDocument,
)
from .policy import SequenceFallbackMode
from .progress import ProgressCallback
from .results import BookConversionResult

BundleValue = Book | SsmdDocument
BundleInspectionValue = BookInspection | Book | Document | SsmdDocument
BundleWorkspaceValue = BookWorkspace | DocumentWorkspace


@dataclass(frozen=True, slots=True)
class BundleInspection:
    kind: BundleKind
    value: BundleInspectionValue


@dataclass(frozen=True, slots=True)
class BundleConversionResult:
    kind: BundleKind
    value: BookConversionResult | SsmdDocument
    output: Path | None = None


@dataclass(frozen=True, slots=True)
class LoadedBundle:
    kind: BundleKind
    value: BundleValue


@dataclass(frozen=True, slots=True)
class BundleWorkspace:
    kind: BundleKind
    value: BundleWorkspaceValue


def _require_storage_path(path: str | Path) -> Path:
    source = Path(path).expanduser()
    if source.name.endswith(".ssmd-bundle"):
        return require_bundle_workspace_path(source)
    if source.name.endswith(".ssmd-bundle.zip"):
        return require_bundle_archive_path(source)
    raise BundleIdentityError(
        f"{source}: expected an .ssmd-bundle workspace or .ssmd-bundle.zip archive"
    )


def inspect_bundle_source(source: str | Path) -> BundleInspection:
    """Inspect a supported source or canonical bundle and include its detected kind."""
    path = Path(source).expanduser()
    if path.name.endswith((".ssmd-bundle", ".ssmd-bundle.zip")):
        loaded = load_bundle(path)
        return BundleInspection(kind=loaded.kind, value=loaded.value)
    from .services.bundle_conversion import detect_source_kind

    kind = detect_source_kind(path)
    if kind == "book":
        from .books import inspect_book

        value: BundleInspectionValue = inspect_book(path)
    else:
        from .api import inspect_document

        value = inspect_document(path)
    return BundleInspection(kind=kind, value=value)


def convert_bundle(
    source: str | Path,
    *,
    output: str | Path | None = None,
    chapters: str = "all",
    language: str | None = None,
    metadata_overrides: Mapping[str, Any] | None = None,
    sequence_fallback_mode: SequenceFallbackMode | None = None,
    speech_semantics: Literal["freeze", "preserve"] = "freeze",
    spacy: SpacyPolicy = "off",
    force: bool = False,
    on_progress: ProgressCallback | None = None,
) -> BundleConversionResult:
    """Convert an EPUB or supported document and publish a canonical directory bundle."""
    from .services.bundle_conversion import convert_bundle as service_convert_bundle

    return service_convert_bundle(
        source,
        output=output,
        chapters=chapters,
        language=language,
        metadata_overrides=metadata_overrides,
        sequence_fallback_mode=sequence_fallback_mode,
        speech_semantics=speech_semantics,
        spacy=spacy,
        force=force,
        on_progress=on_progress,
    )


def load_bundle(source: str | Path) -> LoadedBundle:
    """Load and strictly validate a packed or editable bundle by manifest kind."""
    path = _require_storage_path(source)
    kind = probe_bundle_kind(path)
    value = (
        _book_bundle.load_book_bundle(path)
        if kind == "book"
        else _document_bundle.load_document_bundle(path)
    )
    return LoadedBundle(kind=kind, value=value)


def validate_bundle(source: str | Path) -> BundleKind:
    """Strictly validate a canonical directory or archive and return its kind."""
    return load_bundle(source).kind


def load_bundle_workspace(path: str | Path) -> BundleWorkspace:
    """Load current editable workspace state without rejecting dirty content."""
    root = require_bundle_workspace_path(path)
    kind = probe_bundle_kind(root)
    value = (
        _book_bundle.load_book_workspace(root)
        if kind == "book"
        else _document_bundle.load_document_workspace(root)
    )
    return BundleWorkspace(kind=kind, value=value)


def refresh_bundle_workspace(path: str | Path) -> BundleWorkspace:
    """Refresh kind-specific content digests in a canonical editable workspace."""
    root = require_bundle_workspace_path(path)
    kind = probe_bundle_kind(root)
    value = (
        _book_bundle.refresh_book_workspace(root)
        if kind == "book"
        else _document_bundle.refresh_document_workspace(root)
    )
    return BundleWorkspace(kind=kind, value=value)


def pack_bundle(workspace: str | Path, output: str | Path | None = None) -> Path:
    """Write a deterministic canonical ZIP archive from an editable workspace."""
    root = require_bundle_workspace_path(workspace)
    kind = probe_bundle_kind(root)
    destination = default_bundle_archive_path(root) if output is None else Path(output).expanduser()
    if not destination.name.endswith(".ssmd-bundle.zip"):
        raise BundleIdentityError("packed bundle output must end with '.ssmd-bundle.zip'")
    if destination.exists() or destination.is_symlink():
        raise BundleIdentityError(f"packed bundle output already exists: {destination}")
    if kind == "book":
        book_value = _book_bundle.load_book_bundle(root)
        return _book_bundle.write_book_bundle(book_value, destination, format="zip")
    document_value = _document_bundle.load_document_bundle(root)
    return _document_bundle.write_document_bundle(document_value, destination, format="zip")


def write_bundle(
    value: BundleValue,
    output: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write a book or document bundle to a canonical directory workspace."""
    destination = Path(output).expanduser()
    if not destination.name.endswith(".ssmd-bundle"):
        raise BundleIdentityError("bundle output must end with '.ssmd-bundle'")
    if isinstance(value, Book):
        return _book_bundle.write_book_bundle(
            value, destination, format="directory", overwrite=overwrite
        )
    if isinstance(value, SsmdDocument):
        return _document_bundle.write_document_bundle(
            value, destination, format="directory", overwrite=overwrite
        )
    raise TypeError("bundle value must be a Book or SsmdDocument")


def read_current_bundle_item_bytes(source: str | Path, item_id: str) -> bytes:
    """Read current content for one chapter/document from a canonical bundle."""
    path = Path(source).expanduser()
    if path.name.endswith(".ssmd-bundle.zip"):
        loaded = load_bundle(path)
        if loaded.kind == "book":
            book = loaded.value
            assert isinstance(book, Book)
            chapter = next((item for item in book.chapters if item.id == item_id), None)
            if chapter is None:
                raise BundleIdentityError(f"{path}: item {item_id!r} is not present in the bundle")
            return chapter.ssmd.encode("utf-8")
        document = loaded.value
        assert isinstance(document, SsmdDocument)
        if item_id != "document-0001":
            raise BundleIdentityError(f"{path}: item {item_id!r} is not present in the bundle")
        return document.ssmd.encode("utf-8")

    root = require_bundle_workspace_path(path)
    workspace = load_bundle_workspace(root)
    if workspace.kind == "book":
        book_workspace = workspace.value
        assert isinstance(book_workspace, BookWorkspace)
        chapter = next(
            (chapter for chapter in book_workspace.book.chapters if chapter.id == item_id), None
        )
        if chapter is None:
            raise BundleIdentityError(f"{root}: item {item_id!r} is not present in the bundle")
        return chapter.ssmd.encode("utf-8")
    document_workspace = workspace.value
    assert isinstance(document_workspace, DocumentWorkspace)
    if item_id != "document-0001":
        raise BundleIdentityError(f"{root}: item {item_id!r} is not present in the bundle")
    return (root / document_workspace.status.path).read_bytes()


__all__ = [
    "BundleConversionResult",
    "BundleInspection",
    "BundleKind",
    "BundleStorage",
    "BundleWorkspace",
    "LoadedBundle",
    "convert_bundle",
    "default_bundle_archive_path",
    "default_bundle_workspace_path",
    "inspect_bundle_source",
    "load_bundle",
    "load_bundle_workspace",
    "pack_bundle",
    "probe_bundle_kind",
    "read_current_bundle_item_bytes",
    "refresh_bundle_workspace",
    "validate_bundle",
    "write_bundle",
]

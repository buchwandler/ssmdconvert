"""Source-kind detection and unified conversion for bundle artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from ..bundle import BundleConversionResult, write_bundle
from ..bundle_identity import BundleKind, default_bundle_workspace_path
from ..errors import BundleIdentityError
from ..linguistics import SpacyPolicy
from ..models import SsmdDocument
from ..options import BookConversionOptions, DocumentConversionOptions, SpeechOptions
from ..policy import DEFAULT_SEQUENCE_FALLBACK_MODE, SequenceFallbackMode
from ..progress import ProgressCallback
from ..results import BookConversionResult


def detect_source_kind(source: str | Path) -> BundleKind:
    """Use the registered source adapter to distinguish EPUB books from documents."""
    from ..converter import Converter

    path = Path(source).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"source is not a regular file: {path}")
    return "book" if Converter().adapter_for(path).name == "epub" else "document"


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
    """Convert an EPUB or supported document through one bundle lifecycle."""
    source_path = Path(source).expanduser().resolve(strict=True)
    kind = detect_source_kind(source_path)
    destination = (
        default_bundle_workspace_path(source_path) if output is None else Path(output).expanduser()
    )
    if not destination.name.endswith(".ssmd-bundle"):
        raise BundleIdentityError("bundle output must end with '.ssmd-bundle'")

    if kind == "book":
        if speech_semantics not in {"freeze", "preserve"}:
            raise ValueError("speech_semantics must be 'freeze' or 'preserve'")
        options = BookConversionOptions(
            chapters=chapters,
            language=language,
            metadata_overrides={} if metadata_overrides is None else metadata_overrides,
            sequence_fallback_mode=sequence_fallback_mode or DEFAULT_SEQUENCE_FALLBACK_MODE,
            speech=SpeechOptions(mode=speech_semantics, spacy=spacy),
        )
        from .book_conversion import convert_book_pipeline

        book_result = convert_book_pipeline(source_path, options, on_progress=on_progress)
        value: BookConversionResult | SsmdDocument = book_result
        written = write_bundle(book_result.book, destination, overwrite=force)
    else:
        if chapters != "all":
            raise ValueError("--chapters is only available for book sources")
        document_options = DocumentConversionOptions(
            language=language,
            metadata_overrides={} if metadata_overrides is None else metadata_overrides,
            sequence_fallback_mode=sequence_fallback_mode or DEFAULT_SEQUENCE_FALLBACK_MODE,
        )
        from .document_conversion import convert_document_artifact

        value = convert_document_artifact(
            source_path,
            language=document_options.language,
            metadata_overrides=document_options.metadata_overrides,
            sequence_fallback_mode=sequence_fallback_mode,
        )
        written = write_bundle(value, destination, overwrite=force)
    return BundleConversionResult(kind=kind, value=value, output=written)

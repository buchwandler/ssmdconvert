"""Conversion service for rendered single-document SSMD artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ssmd import parse_structure

from ..api import convert_document
from ..models import SourceInfo, SsmdDocument
from ..options import DocumentConversionOptions
from ..policy import DEFAULT_SEQUENCE_FALLBACK_MODE, SequenceFallbackMode
from ..render import render_document, validate_ssmd_document


def _is_ssmd_path(path: Path) -> bool:
    return path.name.lower().endswith((".ssmd", ".ssmd.md"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_from_ssmd(raw: bytes, path: Path) -> tuple[str, dict[str, Any]]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"SSMD source is not valid UTF-8: {path}: {exc}") from exc
    try:
        validate_ssmd_document(text)
        structure = parse_structure(text, dialect="0.9", normalize=False)
    except Exception as exc:
        raise ValueError(f"SSMD source is not valid SSMD 0.9: {path}: {exc}") from exc
    metadata = dict(structure.header)
    metadata.pop("ssmd_version", None)
    return text, metadata


def convert_document_artifact(
    source: str | Path,
    *,
    title: str | None = None,
    author: str | None = None,
    language: str | None = None,
    metadata_overrides: Mapping[str, Any] | None = None,
    sequence_fallback_mode: SequenceFallbackMode | None = None,
) -> SsmdDocument:
    """Convert a source into a provenance-bearing SSMD artifact.

    Already-valid SSMD passes through byte-for-byte unless a metadata override or
    sequence-fallback policy was explicitly requested.
    """
    path = Path(source).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"document source is not a regular file: {path}")
    overrides = {} if metadata_overrides is None else dict(metadata_overrides)
    ssmd_input = _is_ssmd_path(path)

    if ssmd_input:
        original_bytes = path.read_bytes()
        source_sha256 = hashlib.sha256(original_bytes).hexdigest()
        exact_text, source_metadata = _metadata_from_ssmd(original_bytes, path)
        if (
            title is None
            and author is None
            and language is None
            and not overrides
            and sequence_fallback_mode is None
        ):
            return SsmdDocument(
                source=SourceInfo(
                    format="ssmd",
                    media_type="text/markdown",
                    path=path,
                    name=path.name,
                ),
                metadata=source_metadata,
                ssmd=exact_text,
                source_sha256=source_sha256,
            )
    else:
        source_sha256 = _sha256_file(path)
        source_metadata = {}

    effective_mode = sequence_fallback_mode or DEFAULT_SEQUENCE_FALLBACK_MODE
    options = DocumentConversionOptions(
        title=title,
        author=author,
        language=language,
        metadata_overrides=overrides,
        sequence_fallback_mode=effective_mode,
    )
    result = convert_document(path, options=options)
    result_ssmd = result.ssmd

    if ssmd_input and sequence_fallback_mode is None:
        # Converter's established default is useful for ordinary source formats,
        # but must not silently replace an existing SSMD sequence policy.
        if "sequence_fallback_mode" in overrides:
            result.document.metadata["sequence_fallback_mode"] = overrides["sequence_fallback_mode"]
        elif "sequence_fallback_mode" in source_metadata:
            result.document.metadata["sequence_fallback_mode"] = source_metadata[
                "sequence_fallback_mode"
            ]
        else:
            result.document.metadata.pop("sequence_fallback_mode", None)
        result_ssmd = render_document(result.document)

    if _sha256_file(path) != source_sha256:
        raise ValueError(f"document source changed during conversion: {path}")
    metadata = dict(result.document.metadata)
    metadata.pop("ssmd_version", None)
    return SsmdDocument(
        source=result.document.source,
        metadata=metadata,
        ssmd=result_ssmd,
        source_sha256=source_sha256,
    )

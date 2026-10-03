from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

from .adapters import (
    ContentAdapter,
    InputAdapter,
    default_adapters,
    default_content_adapters,
)
from .errors import UnsupportedInputError
from .metadata import merge_document_metadata
from .models import ConversionResult, Document
from .policy import (
    DEFAULT_SEQUENCE_FALLBACK_MODE,
    SequenceFallbackMode,
    validate_sequence_fallback_mode,
)
from .render import render_document

ContentInputFormat = Literal["text", "markdown", "html"]


class Converter:
    """Convert source documents through the registered input adapters."""

    def __init__(self, adapters: Iterable[InputAdapter] | None = None) -> None:
        self.adapters = list(adapters) if adapters is not None else default_adapters()
        self.content_adapters: dict[str, ContentAdapter] = default_content_adapters()

    def adapter_for(self, source: str | Path) -> InputAdapter:
        """Select the adapter that supports a source path."""
        path = Path(source).expanduser().resolve()
        for adapter in self.adapters:
            if adapter.supports(path):
                return adapter
        supported = ", ".join(adapter.name for adapter in self.adapters)
        raise UnsupportedInputError(
            f"Unsupported input: {path.suffix or '<no suffix>'}; adapters: {supported}"
        )

    def load(self, source: str | Path) -> Document:
        """Load a source into the normalized document model."""
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return self.adapter_for(path).load(path)

    def _render(
        self,
        document: Document,
        *,
        title: str | None,
        author: str | None = None,
        language: str | None,
        sequence_fallback_mode: SequenceFallbackMode,
        metadata_overrides: Mapping[str, Any] | None,
    ) -> ConversionResult:
        cli_overrides: dict[str, Any] = {}
        if title is not None:
            cli_overrides["title"] = title
        if author is not None:
            cli_overrides["author"] = author
        document.metadata = merge_document_metadata(
            document.metadata,
            metadata_overrides=metadata_overrides,
            cli_overrides=cli_overrides,
            language=language,
            sequence_fallback_mode=sequence_fallback_mode,
        )
        return ConversionResult(document=document, ssmd=render_document(document))

    def convert(
        self,
        source: str | Path,
        *,
        title: str | None = None,
        author: str | None = None,
        language: str | None = None,
        metadata_overrides: Mapping[str, Any] | None = None,
        sequence_fallback_mode: SequenceFallbackMode = DEFAULT_SEQUENCE_FALLBACK_MODE,
    ) -> ConversionResult:
        """Convert a source into one combined SSMD document."""
        mode = validate_sequence_fallback_mode(sequence_fallback_mode)
        document = self.load(source)
        return self._render(
            document,
            title=title,
            author=author,
            language=language,
            metadata_overrides=metadata_overrides,
            sequence_fallback_mode=mode,
        )

    def convert_content(
        self,
        content: str,
        *,
        input_format: ContentInputFormat,
        source_name: str = "<memory>",
        title: str | None = None,
        language: str | None = None,
        metadata_overrides: Mapping[str, Any] | None = None,
        sequence_fallback_mode: SequenceFallbackMode = DEFAULT_SEQUENCE_FALLBACK_MODE,
    ) -> ConversionResult:
        """Convert in-memory text, Markdown, or HTML into one SSMD document."""
        mode = validate_sequence_fallback_mode(sequence_fallback_mode)
        adapter = self.content_adapters.get(input_format)
        if adapter is None:
            supported = ", ".join(sorted(self.content_adapters))
            raise UnsupportedInputError(
                f"Unsupported content format: {input_format}; adapters: {supported}"
            )
        document = adapter.load_content(content, source_name)
        return self._render(
            document,
            title=title,
            language=language,
            metadata_overrides=metadata_overrides,
            sequence_fallback_mode=mode,
        )


def convert(
    source: str | Path,
    *,
    title: str | None = None,
    author: str | None = None,
    language: str | None = None,
    metadata_overrides: Mapping[str, Any] | None = None,
    sequence_fallback_mode: SequenceFallbackMode = DEFAULT_SEQUENCE_FALLBACK_MODE,
) -> ConversionResult:
    """Convert a source path with the default adapters."""
    return Converter().convert(
        source,
        title=title,
        author=author,
        language=language,
        metadata_overrides=metadata_overrides,
        sequence_fallback_mode=sequence_fallback_mode,
    )


def convert_content(
    content: str,
    *,
    input_format: ContentInputFormat,
    source_name: str = "<memory>",
    title: str | None = None,
    language: str | None = None,
    metadata_overrides: Mapping[str, Any] | None = None,
    sequence_fallback_mode: SequenceFallbackMode = DEFAULT_SEQUENCE_FALLBACK_MODE,
) -> ConversionResult:
    """Convert in-memory text, Markdown, or HTML with the default adapters."""
    return Converter().convert_content(
        content,
        input_format=input_format,
        source_name=source_name,
        title=title,
        language=language,
        metadata_overrides=metadata_overrides,
        sequence_fallback_mode=sequence_fallback_mode,
    )

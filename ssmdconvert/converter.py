from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .adapters import InputAdapter, default_adapters
from .books import convert_book as _convert_book
from .errors import UnsupportedInputError
from .models import Book, ConversionResult, Document
from .render import render_document


class Converter:
    """Convert source documents through the registered input adapters."""

    def __init__(self, adapters: Iterable[InputAdapter] | None = None) -> None:
        self.adapters = list(adapters) if adapters is not None else default_adapters()

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

    def convert_book(
        self,
        source: str | Path,
        *,
        chapters: str | None = "all",
    ) -> Book:
        """Convert selected EPUB chapters into standalone SSMD documents."""
        return _convert_book(source, chapters=chapters)

    def convert(
        self,
        source: str | Path,
        *,
        title: str | None = None,
        author: str | None = None,
        language: str | None = None,
    ) -> ConversionResult:
        """Convert a source into one combined SSMD document."""
        document = self.load(source)
        if title is not None:
            document.metadata["title"] = title
        if author is not None:
            document.metadata["author"] = author
        if language is not None:
            document.metadata["language"] = language
        return ConversionResult(document=document, ssmd=render_document(document))


def convert(source: str | Path, **kwargs: object) -> ConversionResult:
    """Convert a source path with the default adapters."""
    return Converter().convert(source, **kwargs)

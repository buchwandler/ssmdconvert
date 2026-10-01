from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .adapters import InputAdapter, default_adapters
from .books import convert_book as _convert_book
from .errors import UnsupportedInputError
from .models import Book, ConversionResult, Document
from .render import render_document
from .speech import SpeechPreparationOptions, prepare_ssmd_for_speech


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
        speech_options: SpeechPreparationOptions | None = None,
    ) -> Book:
        """Convert selected EPUB chapters into standalone SSMD documents."""
        return _convert_book(source, chapters=chapters, speech_options=speech_options)

    def convert(
        self,
        source: str | Path,
        *,
        title: str | None = None,
        author: str | None = None,
        language: str | None = None,
        speech_options: SpeechPreparationOptions | None = None,
    ) -> ConversionResult:
        """Convert a source into one combined SSMD document."""
        document = self.load(source)
        if title is not None:
            document.metadata["title"] = title
        if author is not None:
            document.metadata["author"] = author
        if language is not None:
            document.metadata["language"] = language
        ssmd = render_document(document)
        speech_report = None
        if speech_options is not None:
            speech_result = prepare_ssmd_for_speech(ssmd, options=speech_options)
            ssmd = speech_result.ssmd
            speech_report = speech_result.report
        return ConversionResult(document=document, ssmd=ssmd, speech_report=speech_report)


def convert(source: str | Path, **kwargs: Any) -> ConversionResult:
    """Convert a source path with the default adapters."""
    return Converter().convert(source, **kwargs)

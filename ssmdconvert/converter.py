from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .adapters import InputAdapter, default_adapters
from .errors import UnsupportedInputError
from .models import ConversionResult, Document
from .render import render_document


class Converter:
    def __init__(self, adapters: Iterable[InputAdapter] | None = None) -> None:
        self.adapters = list(adapters) if adapters is not None else default_adapters()

    def adapter_for(self, source: str | Path) -> InputAdapter:
        path = Path(source).expanduser().resolve()
        for adapter in self.adapters:
            if adapter.supports(path):
                return adapter
        supported = ", ".join(adapter.name for adapter in self.adapters)
        raise UnsupportedInputError(
            f"Unsupported input: {path.suffix or '<no suffix>'}; adapters: {supported}"
        )

    def load(self, source: str | Path) -> Document:
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return self.adapter_for(path).load(path)

    def convert(
        self,
        source: str | Path,
        *,
        title: str | None = None,
        author: str | None = None,
        language: str | None = None,
    ) -> ConversionResult:
        document = self.load(source)
        if title is not None:
            document.metadata["title"] = title
        if author is not None:
            document.metadata["author"] = author
        if language is not None:
            document.metadata["language"] = language
        return ConversionResult(document=document, ssmd=render_document(document))


def convert(source: str | Path, **kwargs: object) -> ConversionResult:
    return Converter().convert(source, **kwargs)

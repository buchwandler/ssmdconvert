from __future__ import annotations

from pathlib import Path

from ..models import Document, Section, SourceInfo
from .common import read_text_file, split_plain_text


class TextAdapter:
    name = "text"
    suffixes = {".txt", ".text"}

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() in self.suffixes

    def load(self, source: Path) -> Document:
        text = read_text_file(source)
        sections = [
            Section(id=f"section-{index:04d}", title=title, markdown=body)
            for index, (title, body) in enumerate(split_plain_text(text), start=1)
            if body
        ]
        return Document(
            source=SourceInfo(
                format="text", media_type="text/plain", path=source, name=source.name
            ),
            sections=sections or [Section("section-0001", "")],
            metadata={"title": source.stem},
        )

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
        return self.load_content(read_text_file(source), source.name, source)

    def load_content(
        self, content: str, source_name: str, source_path: Path | None = None
    ) -> Document:
        sections = [
            Section(id=f"section-{index:04d}", title=title, markdown=body)
            for index, (title, body) in enumerate(split_plain_text(content), start=1)
            if body
        ]
        return Document(
            source=SourceInfo(
                format="text", media_type="text/plain", path=source_path, name=source_name
            ),
            sections=sections or [Section("section-0001", "")],
            metadata={"title": Path(source_name).stem},
        )

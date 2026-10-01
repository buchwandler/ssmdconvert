from __future__ import annotations

from pathlib import Path

from ssmd import parse_front_matter

from ..models import Document, Section, SourceInfo
from .common import is_ssmd_path, read_text_file


class SsmdAdapter:
    name = "ssmd"

    def supports(self, source: Path) -> bool:
        return is_ssmd_path(source)

    def load(self, source: Path) -> Document:
        raw = read_text_file(source)
        parsed = parse_front_matter(raw)
        metadata = dict(parsed.data) if parsed.present else {}
        metadata.setdefault("title", source.stem)
        return Document(
            source=SourceInfo(
                format="ssmd", media_type="text/markdown", path=source, name=source.name
            ),
            sections=[Section("section-0001", parsed.body if parsed.present else raw)],
            metadata=metadata,
        )

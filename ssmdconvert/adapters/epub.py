from __future__ import annotations

from pathlib import Path

from .._epub import load_epub
from ..models import Document, Section, SourceInfo


class EpubAdapter:
    name = "epub"

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() == ".epub"

    def load(self, source: Path) -> Document:
        extracted = load_epub(source)
        metadata = dict(extracted.metadata)
        authors = metadata.pop("authors", [])
        if authors:
            metadata["author"] = authors[0]
        sections = [
            Section(
                id=chapter.id,
                markdown=chapter.markdown,
                title=chapter.title,
                level=chapter.level,
                source_ref=chapter.href,
            )
            for chapter in extracted.chapters
        ]
        return Document(
            source=SourceInfo(
                format="epub",
                media_type="application/epub+zip",
                path=extracted.source,
                name=extracted.source.name,
            ),
            sections=sections,
            metadata=metadata,
        )

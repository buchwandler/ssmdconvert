from __future__ import annotations

from pathlib import Path

from epub2text import EPUBParser

from ..epub_options import default_epub_chapter_options
from ..errors import SSMDConvertError
from ..models import Document, Section, SourceInfo


class EpubAdapter:
    name = "epub"

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() == ".epub"

    def load(self, source: Path) -> Document:
        try:
            parser = EPUBParser(str(source))
            chapters = parser.get_chapter_documents(options=default_epub_chapter_options())
            epub_metadata = parser.get_metadata()
        except (OSError, ValueError) as exc:
            raise SSMDConvertError(f"Could not read EPUB {source.name}: {exc}") from exc

        metadata: dict[str, str] = {"title": epub_metadata.title or source.stem}
        if epub_metadata.authors:
            metadata["author"] = epub_metadata.authors[0]
        if epub_metadata.language:
            metadata["language"] = epub_metadata.language
        if epub_metadata.publisher:
            metadata["publisher"] = epub_metadata.publisher
        if epub_metadata.identifier:
            metadata["identifier"] = epub_metadata.identifier

        sections = [
            Section(
                id=chapter.id,
                markdown=chapter.to_markdown(include_title=True, title_level=1),
                title=chapter.title,
                level=chapter.level,
                source_ref=chapter.href,
            )
            for chapter in chapters
        ]
        if not sections:
            raise SSMDConvertError(f"EPUB did not yield any readable chapters: {source.name}")

        return Document(
            source=SourceInfo(source, "epub", "application/epub+zip"),
            sections=sections,
            metadata=metadata,
        )

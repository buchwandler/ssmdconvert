from __future__ import annotations

from pathlib import Path

from ..errors import MissingDependencyError
from ..models import Document, Section, SourceInfo


class PdfAdapter:
    name = "pdf"

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() == ".pdf"

    def load(self, source: Path) -> Document:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise MissingDependencyError(
                "PDF input requires: pip install 'ssmdconvert[pdf]'"
            ) from exc
        reader = PdfReader(str(source))
        parts: list[str] = []
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                parts.append(text)
        metadata: dict[str, str] = {"title": source.stem}
        if reader.metadata:
            if reader.metadata.title:
                metadata["title"] = str(reader.metadata.title)
            if reader.metadata.author:
                metadata["author"] = str(reader.metadata.author)
        text = "\n\n".join(parts)
        return Document(
            source=SourceInfo(
                format="pdf", media_type="application/pdf", path=source, name=source.name
            ),
            sections=[Section("section-0001", text)],
            metadata=metadata,
        )

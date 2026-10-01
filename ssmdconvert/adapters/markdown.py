from __future__ import annotations

import re
from pathlib import Path

from ..models import Document, Section, SourceInfo
from .common import is_ssmd_path, read_text_file

_H1_RE = re.compile(r"^#\s+(.+?)\s*$")


def split_markdown(text: str) -> list[tuple[str | None, str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    starts = [
        (idx, match.group(1).strip())
        for idx, line in enumerate(lines)
        if (match := _H1_RE.match(line))
    ]
    if not starts:
        return [(None, "\n".join(lines).strip())]
    result: list[tuple[str | None, str]] = []
    if starts[0][0] > 0 and any(line.strip() for line in lines[: starts[0][0]]):
        result.append((None, "\n".join(lines[: starts[0][0]]).strip()))
    for pos, (start, title) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        result.append((title, "\n".join(lines[start:end]).strip()))
    return result


class MarkdownAdapter:
    name = "markdown"
    suffixes = {".md", ".markdown", ".mdown", ".mkd"}

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() in self.suffixes and not is_ssmd_path(source)

    def load(self, source: Path) -> Document:
        text = read_text_file(source)
        sections = [
            Section(id=f"section-{index:04d}", title=title, markdown=body)
            for index, (title, body) in enumerate(split_markdown(text), start=1)
            if body
        ]
        return Document(
            source=SourceInfo(
                format="markdown", media_type="text/markdown", path=source, name=source.name
            ),
            sections=sections or [Section("section-0001", "")],
            metadata={"title": source.stem},
        )

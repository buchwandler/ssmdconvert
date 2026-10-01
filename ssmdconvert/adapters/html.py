from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from ..models import Document, Section, SourceInfo
from .common import read_text_file

_BLOCKS = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "aside",
    "nav",
    "ul",
    "ol",
    "blockquote",
}


class _HTMLToMarkdown(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignore_depth = 0
        self.title_parts: list[str] = []
        self.in_title = False
        self.first_heading: str | None = None
        self._heading_text: list[str] | None = None

    def _newline(self, count: int = 1) -> None:
        if not self.parts:
            return
        current = "".join(self.parts)
        missing = count - (len(current) - len(current.rstrip("\n")))
        if missing > 0:
            self.parts.append("\n" * missing)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "svg", "math"}:
            self.ignore_depth += 1
            return
        if self.ignore_depth:
            return
        if tag == "title":
            self.in_title = True
        elif re.fullmatch(r"h[1-6]", tag):
            self._newline(2)
            level = int(tag[1])
            self.parts.append("#" * level + " ")
            self._heading_text = []
        elif tag in _BLOCKS:
            self._newline(2)
            if tag == "blockquote":
                self.parts.append("> ")
        elif tag == "br":
            self._newline(1)
        elif tag == "li":
            self._newline(1)
            self.parts.append("- ")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(str(alt))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "svg", "math"}:
            if self.ignore_depth:
                self.ignore_depth -= 1
            return
        if self.ignore_depth:
            return
        if tag == "title":
            self.in_title = False
        elif re.fullmatch(r"h[1-6]", tag):
            if self.first_heading is None and self._heading_text:
                self.first_heading = "".join(self._heading_text).strip()
            self._heading_text = None
            self._newline(2)
        elif tag in _BLOCKS:
            self._newline(2)
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag == "code":
            self.parts.append("`")

    def handle_data(self, data: str) -> None:
        if self.ignore_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
            return
        if self._heading_text is not None:
            self._heading_text.append(data)
        if not data:
            return
        collapsed = re.sub(r"\s+", " ", data)
        core = collapsed.strip()
        if not core:
            if self.parts and not self.parts[-1].endswith((" ", "\n")):
                self.parts.append(" ")
            return
        if collapsed.startswith(" ") and self.parts and not self.parts[-1].endswith((" ", "\n")):
            self.parts.append(" ")
        elif (
            self.parts
            and not self.parts[-1].endswith(("\n", " ", "*", "`", "> ", "- "))
            and not core.startswith((".", ",", ";", ":", "!", "?", "”", "’"))
        ):
            self.parts.append(" ")
        self.parts.append(core)
        if collapsed.endswith(" "):
            self.parts.append(" ")

    def result(self) -> tuple[str, str | None, str | None]:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        title = re.sub(r"\s+", " ", "".join(self.title_parts)).strip() or None
        return text, title, self.first_heading


def html_to_markdown(html: str) -> tuple[str, str | None, str | None]:
    parser = _HTMLToMarkdown()
    parser.feed(html)
    parser.close()
    return parser.result()


class HtmlAdapter:
    name = "html"
    suffixes = {".html", ".htm", ".xhtml"}

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() in self.suffixes

    def load(self, source: Path) -> Document:
        markdown, title, first_heading = html_to_markdown(read_text_file(source))
        metadata = {"title": title or first_heading or source.stem}
        return Document(
            source=SourceInfo(format="html", media_type="text/html", path=source, name=source.name),
            sections=[Section("section-0001", markdown, first_heading)],
            metadata=metadata,
        )

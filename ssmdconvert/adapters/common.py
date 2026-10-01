from __future__ import annotations

import re
from pathlib import Path

_CHAPTER_RE = re.compile(
    r"^(?P<title>(?:chapter|part|book)\s+(?:[0-9ivxlcdm]+|[\w'’-]+)(?:\s*[:.—-]\s*.*)?|prologue|epilogue)\s*$",
    re.IGNORECASE,
)


def is_ssmd_path(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".ssmd", ".ssmd.md"))


def read_text_file(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def split_plain_text(text: str) -> list[tuple[str | None, str]]:
    """Split common prose chapter headings while preserving all text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    starts: list[int] = []
    titles: dict[int, str] = {}
    for idx, line in enumerate(lines):
        match = _CHAPTER_RE.match(line.strip())
        if match:
            starts.append(idx)
            titles[idx] = match.group("title").strip()
    if not starts:
        return [(None, text.strip())]

    sections: list[tuple[str | None, str]] = []
    if starts[0] > 0 and any(line.strip() for line in lines[: starts[0]]):
        sections.append((None, "\n".join(lines[: starts[0]]).strip()))
    for pos, start in enumerate(starts):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(lines)
        title = titles[start]
        body = "\n".join(lines[start + 1 : end]).strip()
        markdown = f"# {title}"
        if body:
            markdown += f"\n\n{body}"
        sections.append((title, markdown))
    return sections

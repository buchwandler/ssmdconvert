from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..models import Document


class InputAdapter(Protocol):
    name: str

    def supports(self, source: Path) -> bool: ...

    def load(self, source: Path) -> Document: ...


class ContentAdapter(Protocol):
    name: str

    def load_content(
        self, content: str, source_name: str, source_path: Path | None = None
    ) -> Document: ...

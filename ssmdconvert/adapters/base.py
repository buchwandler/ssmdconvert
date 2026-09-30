from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..models import Document


class InputAdapter(Protocol):
    name: str

    def supports(self, source: Path) -> bool: ...

    def load(self, source: Path) -> Document: ...

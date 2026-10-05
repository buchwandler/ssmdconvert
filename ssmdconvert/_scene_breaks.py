from __future__ import annotations

import re

SCENE_BREAK_CONTROL = "...p"


def project_scene_breaks(markdown: str) -> str:
    """Project standalone Markdown scene-break blocks into canonical SSMD controls."""
    return re.sub(r"(?m)^[ \t]*---[ \t]*$", SCENE_BREAK_CONTROL, markdown)

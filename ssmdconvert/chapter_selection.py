from __future__ import annotations

import re
from collections.abc import Collection

from .errors import ChapterSelectionError

_RANGE = re.compile(r"(\d+)\s*-\s*(\d+)")


def parse_chapter_selection(
    spec: str | None,
    *,
    available_numbers: Collection[int],
) -> tuple[int, ...]:
    """Parse a chapter selector and return selected source numbers in source order.

    Selectors accept ``all``, a source number, a range, or comma-separated
    combinations such as ``1,3-5``. Unavailable or malformed selections raise
    :class:`ChapterSelectionError`.
    """
    available = tuple(sorted(set(available_numbers)))
    available_set = set(available)

    if spec is None or spec.strip().lower() == "all":
        return available
    if not spec.strip():
        raise ChapterSelectionError("chapter selection is empty")

    selected: set[int] = set()
    for raw_token in spec.split(","):
        token = raw_token.strip()
        if not token:
            raise ChapterSelectionError("chapter selection contains an empty item")

        range_match = _RANGE.fullmatch(token)
        if range_match:
            first, last = (int(value) for value in range_match.groups())
            if first < 1 or last < 1:
                raise ChapterSelectionError("chapter numbers must be positive")
            if first > last:
                raise ChapterSelectionError(f"chapter range is reversed: {token}")
            requested: Collection[int] = range(first, last + 1)
        elif token.isdecimal():
            number = int(token)
            if number < 1:
                raise ChapterSelectionError("chapter numbers must be positive")
            requested = (number,)
        else:
            raise ChapterSelectionError(f"invalid chapter selection item: {token!r}")

        for number in requested:
            if number not in available_set:
                raise ChapterSelectionError(f"chapter number {number} is not available")
            selected.add(number)

    return tuple(number for number in available if number in selected)

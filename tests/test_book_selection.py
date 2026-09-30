from __future__ import annotations

import pytest

from ssmdconvert import ChapterSelectionError, parse_chapter_selection

AVAILABLE = (1, 2, 3, 4, 5, 7, 9, 10)


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (None, AVAILABLE),
        ("all", AVAILABLE),
        ("3", (3,)),
        ("2-4", (2, 3, 4)),
        ("1-3,7,9-10", (1, 2, 3, 7, 9, 10)),
        ("5,2,4", (2, 4, 5)),
        (" 2 - 4 , 5 ", (2, 3, 4, 5)),
    ],
)
def test_chapter_selection_follows_source_order(
    spec: str | None, expected: tuple[int, ...]
) -> None:
    assert parse_chapter_selection(spec, available_numbers=AVAILABLE) == expected


def test_duplicate_source_numbers_are_selected_once() -> None:
    assert parse_chapter_selection("5,2-3,3", available_numbers=AVAILABLE) == (2, 3, 5)


def test_subset_bundle_source_numbers_are_not_renumbered() -> None:
    available = (2, 4, 5)

    assert parse_chapter_selection("all", available_numbers=available) == (2, 4, 5)
    assert parse_chapter_selection("5,2,4", available_numbers=available) == (2, 4, 5)
    with pytest.raises(ChapterSelectionError, match="3 is not available"):
        parse_chapter_selection("3", available_numbers=available)
    with pytest.raises(ChapterSelectionError, match="3 is not available"):
        parse_chapter_selection("2-4", available_numbers=available)


@pytest.mark.parametrize(
    "spec",
    ["", "1,,2", "chapter one", "0", "-1", "4-2", "1-3"],
)
def test_invalid_or_unavailable_chapter_selections_fail(spec: str) -> None:
    with pytest.raises(ChapterSelectionError):
        parse_chapter_selection(spec, available_numbers=(1, 2, 4))

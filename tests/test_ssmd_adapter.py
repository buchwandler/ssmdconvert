from pathlib import Path

import pytest
from ssmd import lint, parse_structure

from ssmdconvert import Converter
from ssmdconvert.adapters import MarkdownAdapter, SsmdAdapter
from ssmdconvert.adapters.common import is_ssmd_path


@pytest.mark.parametrize(
    ("name", "expected_adapter"),
    [
        ("input.ssmd", SsmdAdapter),
        ("input.SSMD", SsmdAdapter),
        ("input.ssmd.md", SsmdAdapter),
        ("input.SSMD.MD", SsmdAdapter),
        ("input.md", MarkdownAdapter),
    ],
)
def test_ssmd_path_routes_to_the_correct_adapter(
    tmp_path: Path,
    name: str,
    expected_adapter: type[object],
) -> None:
    source = tmp_path / name
    selected = Converter().adapter_for(source)
    assert isinstance(selected, expected_adapter)
    assert is_ssmd_path(source) is (expected_adapter is SsmdAdapter)


def test_markdown_adapter_does_not_claim_canonical_ssmd_suffix() -> None:
    adapter = MarkdownAdapter()
    assert not adapter.supports(Path("input.ssmd.md"))
    assert adapter.supports(Path("input.md"))


@pytest.mark.parametrize("filename", ["input.ssmd", "input.SSMD.MD"])
def test_existing_ssmd_is_reemitted_as_09_without_duplicate_front_matter(
    tmp_path: Path,
    filename: str,
) -> None:
    source = tmp_path / filename
    source.write_text(
        '---\nssmd_version: "0.9"\ntitle: Existing\nlanguage: en\n---\nHello.\n',
        encoding="utf-8",
    )

    result = Converter().convert(source)
    parsed = parse_structure(result.ssmd, dialect="0.9")

    assert parsed.header["title"] == "Existing"
    assert parsed.header["language"] == "en"
    assert parsed.clean_text.strip() == "Hello."
    assert result.ssmd.count("ssmd_version:") == 1
    assert not [
        issue
        for issue in lint(result.ssmd, profile="ssmd-core", dialect="0.9")
        if issue.severity == "error"
    ]

from pathlib import Path

from ssmdconvert import Converter


def test_markdown_stays_markdown_and_splits_h1(tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    source.write_text("# One\n\nHello *world*.\n\n# Two\n\nBye.\n", encoding="utf-8")
    result = Converter().convert(source)
    assert len(result.document.sections) == 2
    assert "Hello *world*." in result.ssmd


def test_html_converts_headings_paragraphs_and_emphasis(tmp_path: Path) -> None:
    source = tmp_path / "page.html"
    source.write_text(
        "<html><head><title>Sample</title></head>"
        "<body><h1>Start</h1><p>Hello <em>there</em>.</p></body></html>",
        encoding="utf-8",
    )
    result = Converter().convert(source)
    assert result.document.metadata["title"] == "Sample"
    assert "# Start" in result.ssmd
    assert "Hello *there*." in result.ssmd

from pathlib import Path

from ssmd import parse_structure

from ssmdconvert import Converter, convert_content


def test_markdown_becomes_safe_speech_sections(tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    source.write_text("# One\n\nHello *world*.\n\n# Two\n\nBye.\n", encoding="utf-8")
    result = Converter().convert(source)
    assert len(result.document.sections) == 2
    assert "Hello world." in result.ssmd


def test_markdown_semantics_are_safe_for_ssmd_controls() -> None:
    source = (
        "# Intro\n\nThis is *important*, **critical**, and ~~old~~.\n\n"
        "Read the [guide](https://example.invalid). ![diagram](image.png) and `code`.\n\n"
        "- [x] done\n- [ ] later\n\n"
        '```text\n[x]{rate="fast"}\n...500ms\n@chapter\n```\n\n'
        "A claim.[^1]\n\n[^1]: Supporting detail."
    )
    result = convert_content(source, input_format="markdown", source_name="notes.md")

    assert "Read the guide." in result.ssmd
    assert "Image: diagram." in result.ssmd
    assert "Checked: done." in result.ssmd
    assert "Footnote 1. Supporting detail." in result.ssmd
    assert '[x]{rate="fast"}' not in result.ssmd
    assert "500ms" in result.ssmd
    assert "chapter" in result.ssmd


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


def test_in_memory_conversions_match_path_adapters(tmp_path: Path) -> None:
    inputs = (
        ("notes.txt", "text", "Chapter One\n\nPlain text."),
        ("notes.md", "markdown", "# Notes\n\nA *Markdown* paragraph."),
        (
            "page.html",
            "html",
            "<html><head><title>Sample</title></head>"
            "<body><h1>Start</h1><p>Hello <em>there</em>.</p></body></html>",
        ),
    )
    converter = Converter()
    for source_name, input_format, content in inputs:
        source = tmp_path / source_name
        source.write_text(content, encoding="utf-8")
        from_path = converter.convert(source)
        from_content = convert_content(content, input_format=input_format, source_name=source_name)

        assert from_content.ssmd == from_path.ssmd
        assert from_content.document.sections == from_path.document.sections
        assert from_content.document.metadata == from_path.document.metadata
        assert from_content.document.source.path is None
        assert from_content.document.source.name == source_name


def test_markdown_scene_breaks_become_native_ssmd_breaks() -> None:
    source = "Scene one.\n\n---\n\nScene two.\n\n---\n\nScene three."
    result = convert_content(source, input_format="markdown", source_name="scenes.md")
    structure = parse_structure(result.ssmd, dialect="0.9")

    assert result.ssmd.count("...p") == 2
    assert "<paragraph pause>" not in result.ssmd
    assert "---" not in structure.clean_text
    scene_breaks = [
        event
        for event in structure.events
        if event.kind == "break" and event.attrs.get("strength") == "x-strong"
    ]
    assert len(scene_breaks) == 2


def test_html_hr_becomes_native_ssmd_breaks() -> None:
    source = "<p>Scene one.</p><hr><p>Scene two.</p><hr><p>Scene three.</p>"
    result = convert_content(source, input_format="html", source_name="scenes.html")
    structure = parse_structure(result.ssmd, dialect="0.9")

    assert result.ssmd.count("...p") == 2
    assert "<paragraph pause>" not in result.ssmd
    assert "---" not in structure.clean_text
    scene_breaks = [
        event
        for event in structure.events
        if event.kind == "break" and event.attrs.get("strength") == "x-strong"
    ]
    assert len(scene_breaks) == 2

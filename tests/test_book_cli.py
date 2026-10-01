from __future__ import annotations

import json
from pathlib import Path

from epub_support import make_epub
from typer.testing import CliRunner

from ssmdconvert import load_book_bundle
from ssmdconvert.cli import app

runner = CliRunner()


def test_book_chapters_human_and_json_output(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    human = runner.invoke(app, ["book", "chapters", str(source)])
    assert human.exit_code == 0, human.output
    assert "0001  One [level 1]" in human.output
    assert "href=c1.xhtml" in human.output

    result = runner.invoke(app, ["book", "chapters", str(source), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [chapter["source_number"] for chapter in payload["chapters"]] == [1, 2]
    assert [chapter["title"] for chapter in payload["chapters"]] == ["One", "Two"]
    assert payload["chapters"][0]["source_id"].startswith("nav:")


def test_book_command_writes_directory_zip_and_selected_subset(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    directory = tmp_path / "book.ssmdbook"
    archive = tmp_path / "book.ssmdbook.zip"
    subset = tmp_path / "subset.ssmdbook"

    result = runner.invoke(app, ["book", str(source), "-o", str(directory)])
    assert result.exit_code == 0, result.output
    assert directory.is_dir()
    assert len(load_book_bundle(directory).chapters) == 2

    result = runner.invoke(app, ["book", str(source), "--chapters", "2", "-o", str(subset)])
    assert result.exit_code == 0, result.output
    selected = load_book_bundle(subset).chapters
    assert len(selected) == 1
    assert selected[0].id == "chapter-0002"

    result = runner.invoke(app, ["book", str(source), "-o", str(archive)])
    assert result.exit_code == 0, result.output
    assert archive.is_file()
    assert len(load_book_bundle(archive).chapters) == 2


def test_book_validate_reports_success_and_actionable_failures(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    bundle = tmp_path / "book.ssmdbook"
    result = runner.invoke(app, ["book", str(source), "-o", str(bundle)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["book", "validate", str(bundle)])
    assert result.exit_code == 0, result.output
    assert "Valid book bundle" in result.output

    invalid = tmp_path / "invalid.ssmdbook"
    invalid.mkdir()
    result = runner.invoke(app, ["book", "validate", str(invalid)])
    assert result.exit_code != 0
    assert "manifest.json" in result.output


def test_book_command_rejects_invalid_selection_and_missing_source(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    result = runner.invoke(app, ["book", str(source), "--chapters", "5"])
    assert result.exit_code != 0
    assert "chapter number 5 is not available" in result.output

    result = runner.invoke(app, ["book", "chapters"])
    assert result.exit_code != 0
    assert "requires an EPUB SOURCE" in result.output


def test_book_cli_writes_selected_chapter_speech_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    glossary = tmp_path / "pronunciations.json"
    glossary.write_text('{"World":"planet"}', encoding="utf-8")
    bundle = tmp_path / "selected.ssmdbook"

    result = runner.invoke(
        app,
        [
            "book",
            str(source),
            "--chapters",
            "2",
            "--speech",
            "annotate",
            "--pronunciations",
            str(glossary),
            "--output",
            str(bundle),
        ],
    )

    sidecar = tmp_path / "selected.ssmdbook.speech-report.json"
    assert result.exit_code == 0, result.output
    assert sidecar.is_file()
    assert "Speech report:" in result.output
    converted = load_book_bundle(bundle)
    assert [chapter.source_number for chapter in converted.chapters] == [2]
    assert '[World]{sub="planet"}' in converted.chapters[0].ssmd
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert [chapter["chapter_id"] for chapter in payload["chapters"]] == ["chapter-0002"]
    assert payload["chapters"][0]["report"]["changes"][0]["source_text"] == "World"

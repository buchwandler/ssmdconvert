from __future__ import annotations

import json
from pathlib import Path

from click import unstyle
from epub_support import make_epub
from typer.testing import CliRunner

from ssmdconvert import load_book_bundle
from ssmdconvert.cli import app

runner = CliRunner()


def test_book_inspection_human_and_json_output(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    human = runner.invoke(app, ["book", "inspect", str(source)])
    assert human.exit_code == 0, human.output
    assert "Source format: epub" in human.output
    assert "0001  One" in human.output

    result = runner.invoke(app, ["book", "inspect", str(source), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [chapter["source_number"] for chapter in payload["chapters"]] == [1, 2]
    assert [chapter["title"] for chapter in payload["chapters"]] == ["One", "Two"]
    assert payload["source"]["format"] == "epub"
    assert payload["chapters"][0]["source_id"].startswith("nav:")


def test_book_convert_writes_directory_zip_and_selected_subset(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    directory = tmp_path / "book.ssmdbook"
    archive = tmp_path / "book.ssmdbook.zip"
    subset = tmp_path / "subset.ssmdbook"

    result = runner.invoke(app, ["book", "convert", str(source), "-o", str(directory)])
    assert result.exit_code == 0, result.output
    assert directory.is_dir()
    assert len(load_book_bundle(directory).chapters) == 2

    result = runner.invoke(
        app,
        ["book", "convert", str(source), "--chapters", "2,1", "-o", str(subset)],
    )
    assert result.exit_code == 0, result.output
    selected = load_book_bundle(subset).chapters
    assert [chapter.source_number for chapter in selected] == [1, 2]

    result = runner.invoke(app, ["book", "convert", str(source), "-o", str(archive)])
    assert result.exit_code == 0, result.output
    assert archive.is_file()
    assert len(load_book_bundle(archive).chapters) == 2


def test_book_validate_reports_success_and_actionable_failures(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    bundle = tmp_path / "book.ssmdbook"
    result = runner.invoke(app, ["book", "convert", str(source), "-o", str(bundle)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["book", "validate", str(bundle)])
    assert result.exit_code == 0, result.output
    assert "Valid book bundle" in result.output

    result = runner.invoke(app, ["book", "validate", str(bundle), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"valid": True, "bundle": str(bundle)}

    invalid = tmp_path / "invalid.ssmdbook"
    invalid.mkdir()
    result = runner.invoke(app, ["book", "validate", str(invalid)])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "manifest.json" in result.output


def test_book_convert_rejects_invalid_selection_and_removed_speech_flags(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    result = runner.invoke(app, ["book", "convert", str(source), "--chapters", "5"])
    assert result.exit_code == 1
    assert "chapter number 5 is not available" in result.output

    result = runner.invoke(app, ["book", "convert", str(source), "--speech", "annotate"])
    assert result.exit_code == 2
    assert "No such option: --speech" in unstyle(result.output)

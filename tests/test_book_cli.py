from __future__ import annotations

import json
from pathlib import Path

from epub_support import make_epub
from ssmd import parse_structure
from typer.testing import CliRunner

from ssmdconvert import Book, load_bundle
from ssmdconvert.cli import app

runner = CliRunner()


def test_bundle_inspection_and_conversion_preserve_chapter_selection(tmp_path: Path) -> None:
    source = tmp_path / "novel.epub"
    make_epub(source)

    inspection = runner.invoke(app, ["bundle", "inspect", str(source), "--json"])
    assert inspection.exit_code == 0, inspection.output
    inspected = json.loads(inspection.output)
    assert inspected["kind"] == "book"
    assert [item["source_number"] for item in inspected["chapters"]] == [1, 2]

    output = tmp_path / "selected.ssmd-bundle"
    converted = runner.invoke(
        app,
        [
            "bundle",
            "convert",
            str(source),
            "--chapters",
            "2,1",
            "--speech-semantics",
            "preserve",
            "--output",
            str(output),
        ],
    )
    assert converted.exit_code == 0, converted.output
    loaded = load_bundle(output)
    assert loaded.kind == "book"
    assert isinstance(loaded.value, Book)
    assert [chapter.source_number for chapter in loaded.value.chapters] == [1, 2]


def test_bundle_convert_metadata_language_and_report_options(tmp_path: Path) -> None:
    source = tmp_path / "novel.epub"
    make_epub(source)
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text("title: File title\nvoice_defaults: {}\n", encoding="utf-8")
    output = tmp_path / "novel.ssmd-bundle"
    report = tmp_path / "conversion.json"

    converted = runner.invoke(
        app,
        [
            "bundle",
            "convert",
            str(source),
            "--metadata-file",
            str(metadata_file),
            "--language",
            "de-DE",
            "--speech-semantics",
            "preserve",
            "--output",
            str(output),
            "--report-output",
            str(report),
            "--report-format",
            "json",
        ],
    )
    assert converted.exit_code == 0, converted.output
    loaded = load_bundle(output)
    assert isinstance(loaded.value, Book)
    assert loaded.value.metadata["title"] == "File title"
    assert loaded.value.metadata["language"] == "de-DE"
    assert loaded.value.metadata["voice_defaults"] == {}
    for chapter in loaded.value.chapters:
        header = parse_structure(chapter.ssmd, dialect="0.9").header
        assert header["language"] == "de-DE"
    report_payload = json.loads(report.read_text(encoding="utf-8"))
    assert report_payload["kind"] == "book"
    assert report_payload["output"] == str(output)


def test_bundle_convert_freezes_by_default_and_preserves_when_requested(tmp_path: Path) -> None:
    source = tmp_path / "speech.epub"
    make_epub(source, chapter_one_suffix=" Initiate in 3–2–1.")
    frozen_path = tmp_path / "frozen.ssmd-bundle"
    preserved_path = tmp_path / "preserved.ssmd-bundle"

    frozen_result = runner.invoke(app, ["bundle", "convert", str(source), "-o", str(frozen_path)])
    assert frozen_result.exit_code == 0, frozen_result.output
    frozen = load_bundle(frozen_path)
    assert isinstance(frozen.value, Book)
    assert frozen.value.speech_semantics is not None
    assert frozen.value.speech_semantics["status"] == "complete"
    assert '[3–2–1]{sub="three - two - one"}' in frozen.value.chapters[0].ssmd

    preserved_result = runner.invoke(
        app,
        [
            "bundle",
            "convert",
            str(source),
            "--speech-semantics",
            "preserve",
            "-o",
            str(preserved_path),
        ],
    )
    assert preserved_result.exit_code == 0, preserved_result.output
    preserved = load_bundle(preserved_path)
    assert isinstance(preserved.value, Book)
    assert preserved.value.speech_semantics["status"] == "preserved"
    assert "{sub=" not in preserved.value.chapters[0].ssmd

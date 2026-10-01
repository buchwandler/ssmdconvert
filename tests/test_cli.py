import json
from pathlib import Path

import pytest
from click import unstyle
from typer.testing import CliRunner

from ssmdconvert.cli import app

runner = CliRunner()


def test_direct_cli_conversion_is_local(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    target = tmp_path / "book.ssmd"
    source.write_text("Hello.", encoding="utf-8")
    result = runner.invoke(app, ["convert", str(source), "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert target.is_file()
    assert "no content was sent to JEV" in result.output


def test_enrich_requires_explicit_cloud_ack(tmp_path: Path) -> None:
    source = tmp_path / "book.ssmd"
    source.write_text('---\nssmd_version: "0.9"\n---\nHello.\n', encoding="utf-8")
    result = runner.invoke(app, ["enrich", str(source), "--speakers"])
    assert result.exit_code != 0
    assert "--yes-cloud" in unstyle(result.output)


@pytest.mark.parametrize(
    ("extension", "contents"),
    [
        (".json", '{"H2O":"water"}'),
        (".toml", '[pronunciations]\nH2O = "water"\n'),
    ],
)
def test_convert_cli_loads_glossary_and_writes_speech_report(
    tmp_path: Path,
    extension: str,
    contents: str,
) -> None:
    source = tmp_path / "speech.txt"
    glossary = tmp_path / f"pronunciations{extension}"
    target = tmp_path / "speech.ssmd"
    report = tmp_path / "speech-report.json"
    source.write_text("H2O has 5 kg.", encoding="utf-8")
    glossary.write_text(contents, encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "convert",
            str(source),
            "--output",
            str(target),
            "--language",
            "en",
            "--speech",
            "annotate",
            "--pronunciations",
            str(glossary),
            "--speech-report",
            str(report),
        ],
    )

    assert result.exit_code == 0, result.output
    assert '[H2O]{sub="water"}' in target.read_text(encoding="utf-8")
    assert '[5 kg]{sub="five kilograms"}' in target.read_text(encoding="utf-8")
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["backend"] == "spokenform"
    assert {change["source_text"] for change in payload["changes"]} == {"H2O", "5 kg"}
    assert "Speech report ->" in result.output


def test_convert_cli_strict_mode_surfaces_source_corruption(tmp_path: Path) -> None:
    source = tmp_path / "broken.ssmd"
    source.write_text(
        '---\nssmd_version: "0.9"\nlanguage: en\n---\ncaf�.\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["convert", str(source), "--speech", "audit", "--strict-speech"])

    assert result.exit_code != 0
    assert "Speech QC strict mode failed" in unstyle(result.output)


def test_convert_cli_annotation_requires_language(tmp_path: Path) -> None:
    source = tmp_path / "plain.txt"
    source.write_text("H2O.", encoding="utf-8")

    result = runner.invoke(app, ["convert", str(source), "--speech", "annotate"])

    assert result.exit_code != 0
    assert "speech annotation requires --language" in unstyle(result.output)

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click import unstyle
from epub_support import make_epub
from ssmd import parse_structure
from typer.testing import CliRunner

from ssmdconvert import cli as cli_module
from ssmdconvert import load_book_bundle
from ssmdconvert.cli import app

runner = CliRunner()


def test_direct_cli_conversion_is_local(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    target = tmp_path / "book.ssmd"
    source.write_text("Hello.", encoding="utf-8")
    result = runner.invoke(app, ["convert", str(source), "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert target.is_file()
    assert "Hello." in target.read_text(encoding="utf-8")


def test_generic_inspect_json_is_machine_readable(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("Hello.", encoding="utf-8")

    result = runner.invoke(app, ["inspect", str(source), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["adapter"] == "text"
    assert payload["source"] == str(source)
    assert payload["sections"][0]["chars"] > 0


def test_enrichment_is_not_a_cli_command() -> None:
    result = runner.invoke(app, ["enrich", "book.ssmd", "--speakers"])
    assert result.exit_code != 0
    assert "No such command 'enrich'" in result.output


def test_real_command_groups_and_subcommand_help() -> None:
    expected_commands = {
        ("--help",): ("convert", "inspect", "book"),
        ("convert", "--help"): ("--force", "--output", "--sequence-fallback-mode"),
        ("book", "--help"): ("inspect", "convert", "validate"),
        ("book", "inspect", "--help"): ("--json",),
        ("book", "convert", "--help"): (
            "--chapters",
            "--format",
            "--force",
            "--sequence-fallback-mode",
        ),
        ("book", "validate", "--help"): ("--json",),
    }
    for args, expected in expected_commands.items():
        result = runner.invoke(app, list(args))
        assert result.exit_code == 0, result.output
        assert all(item in unstyle(result.output) for item in expected)


def test_convert_refuses_collisions_and_force_replaces_atomically(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    output = tmp_path / "result.ssmd"
    source.write_text("Converted content.", encoding="utf-8")
    output.write_text("original", encoding="utf-8")

    refused = runner.invoke(app, ["convert", str(source), "-o", str(output)])
    assert refused.exit_code == 1
    assert "already exists" in refused.output
    assert output.read_text(encoding="utf-8") == "original"

    replaced = runner.invoke(app, ["convert", str(source), "-o", str(output), "--force"])
    assert replaced.exit_code == 0, replaced.output
    assert "Converted content." in output.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".result.ssmd.tmp-*"))


def test_convert_never_overwrites_an_ssmd_input_even_with_force(tmp_path: Path) -> None:
    source = tmp_path / "source.ssmd"
    source.write_text("Hello.", encoding="utf-8")
    original = source.read_text(encoding="utf-8")

    result = runner.invoke(app, ["convert", str(source), "--force"])

    assert result.exit_code == 1
    assert "must not be the input file" in result.output
    assert source.read_text(encoding="utf-8") == original


def test_failed_atomic_text_write_preserves_existing_output(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    source = tmp_path / "source.txt"
    output = tmp_path / "result.ssmd"
    source.write_text("Converted content.", encoding="utf-8")
    output.write_text("original", encoding="utf-8")

    def fail_fsync(_fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(cli_module.os, "fsync", fail_fsync)
    result = runner.invoke(app, ["convert", str(source), "-o", str(output), "--force"])

    assert result.exit_code == 1
    assert "simulated fsync failure" in result.output
    assert output.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob(".result.ssmd.tmp-*"))


def test_book_subcommands_json_and_bundle_format_inference(tmp_path: Path) -> None:
    source = tmp_path / "novel.epub"
    make_epub(source, nested_navigation=True)

    inspection = runner.invoke(app, ["book", "inspect", str(source), "--json"])
    assert inspection.exit_code == 0, inspection.output
    payload = json.loads(inspection.output)
    assert payload["source"]["format"] == "epub"
    assert payload["source"]["name"] == source.name
    assert payload["chapters"][1]["source_parent_id"] == payload["chapters"][0]["source_id"]
    assert payload["chapters"][1]["parent_id"] == payload["chapters"][0]["id"]

    output = tmp_path / "novel.ssmdbook.zip"
    converted = runner.invoke(
        app,
        ["book", "convert", str(source), "--chapters", "2,1", "-o", str(output)],
    )
    assert converted.exit_code == 0, converted.output
    assert [chapter.source_number for chapter in load_book_bundle(output).chapters] == [1, 2]

    args = ["book", "convert", str(source), "--chapters", "2,1", "-o", str(output)]
    refused = runner.invoke(app, args)
    assert refused.exit_code == 1
    assert "already exists" in refused.output

    forced = runner.invoke(app, [*args, "--force"])
    assert forced.exit_code == 0, forced.output

    validated = runner.invoke(app, ["book", "validate", str(output), "--json"])
    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.output) == {"valid": True, "bundle": str(output)}


def test_book_convert_rejects_ambiguous_output_and_same_input(tmp_path: Path) -> None:
    source = tmp_path / "novel.epub"
    make_epub(source)

    ambiguous = runner.invoke(
        app,
        ["book", "convert", str(source), "-o", str(tmp_path / "book.zip")],
    )
    assert ambiguous.exit_code != 0
    assert "cannot infer bundle format" in ambiguous.output
    assert not (tmp_path / "book.zip").exists()

    same_path = runner.invoke(
        app,
        ["book", "convert", str(source), "-o", str(source), "--format", "zip", "--force"],
    )
    assert same_path.exit_code == 1
    assert "must not be the input file" in same_path.output


def test_sequence_fallback_mode_cli_default_preserve_and_invalid_values(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("Hello.", encoding="utf-8")

    default_output = tmp_path / "default.ssmd"
    default = runner.invoke(app, ["convert", str(source), "--output", str(default_output)])
    assert default.exit_code == 0, default.output
    assert (
        parse_structure(default_output.read_text(encoding="utf-8"), dialect="0.9").header[
            "sequence_fallback_mode"
        ]
        == "spell"
    )

    preserve_output = tmp_path / "preserve.ssmd"
    preserve = runner.invoke(
        app,
        [
            "convert",
            str(source),
            "--output",
            str(preserve_output),
            "--sequence-fallback-mode",
            "preserve",
        ],
    )
    assert preserve.exit_code == 0, preserve.output
    assert (
        parse_structure(preserve_output.read_text(encoding="utf-8"), dialect="0.9").header[
            "sequence_fallback_mode"
        ]
        == "preserve"
    )

    invalid = runner.invoke(
        app,
        [
            "convert",
            str(source),
            "--sequence-fallback-mode",
            "invalid",
        ],
    )
    assert invalid.exit_code == 2
    assert "sequence-fallback-mode" in invalid.output

    book_source = tmp_path / "book.epub"
    make_epub(book_source)
    book_default_path = tmp_path / "default.ssmdbook"
    book_default = runner.invoke(
        app,
        ["book", "convert", str(book_source), "--output", str(book_default_path)],
    )
    assert book_default.exit_code == 0, book_default.output
    assert load_book_bundle(book_default_path).metadata["sequence_fallback_mode"] == "spell"

    book_preserve_path = tmp_path / "preserve.ssmdbook"
    book_preserve = runner.invoke(
        app,
        [
            "book",
            "convert",
            str(book_source),
            "--output",
            str(book_preserve_path),
            "--sequence-fallback-mode",
            "preserve",
        ],
    )
    assert book_preserve.exit_code == 0, book_preserve.output
    assert load_book_bundle(book_preserve_path).metadata["sequence_fallback_mode"] == "preserve"

    invalid_book = runner.invoke(
        app,
        [
            "book",
            "convert",
            str(book_source),
            "--sequence-fallback-mode",
            "invalid",
        ],
    )
    assert invalid_book.exit_code == 2
    assert "sequence-fallback-mode" in invalid_book.output

from __future__ import annotations

import json
from pathlib import Path

import pytest
from epub_support import make_epub
from typer.testing import CliRunner

from ssmdconvert.cli import app

runner = CliRunner()


@pytest.mark.parametrize("kind", ["book", "document"])
def test_bundle_cli_lifecycle_dispatches_by_manifest_kind(tmp_path: Path, kind: str) -> None:
    if kind == "book":
        source = tmp_path / "story.epub"
        make_epub(source)
    else:
        source = tmp_path / "story.md"
        source.write_text("# Story\n\nHello world.\n", encoding="utf-8")

    converted = runner.invoke(
        app,
        [
            "bundle",
            "convert",
            str(source),
            "--speech-semantics",
            "preserve",
        ],
    )
    assert converted.exit_code == 0, converted.output
    workspace = tmp_path / "story.ssmd-bundle"
    assert workspace.is_dir()

    inspected = runner.invoke(app, ["bundle", "inspect", str(workspace), "--json"])
    assert inspected.exit_code == 0, inspected.output
    assert json.loads(inspected.output)["kind"] == kind

    metadata = runner.invoke(app, ["bundle", "metadata", str(workspace), "--json"])
    assert metadata.exit_code == 0, metadata.output
    assert json.loads(metadata.output)["kind"] == kind

    refreshed = runner.invoke(app, ["bundle", "refresh", str(workspace), "--check"])
    assert refreshed.exit_code == 0, refreshed.output

    packed = runner.invoke(app, ["bundle", "pack", str(workspace)])
    assert packed.exit_code == 0, packed.output
    archive = tmp_path / "story.ssmd-bundle.zip"
    assert archive.is_file()

    validated = runner.invoke(app, ["bundle", "validate", str(archive), "--json"])
    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.output) == {
        "valid": True,
        "bundle": str(archive),
        "kind": kind,
    }

    packed_inspection = runner.invoke(app, ["bundle", "inspect", str(archive), "--json"])
    assert packed_inspection.exit_code == 0, packed_inspection.output
    assert json.loads(packed_inspection.output)["kind"] == kind

    read_only_refresh = runner.invoke(app, ["bundle", "refresh", str(archive)])
    assert read_only_refresh.exit_code != 0


def test_bundle_cli_exposes_six_commands_and_rejects_removed_surfaces(
    tmp_path: Path,
) -> None:
    help_result = runner.invoke(app, ["bundle", "--help"])
    assert help_result.exit_code == 0, help_result.output
    for command in ("inspect", "convert", "metadata", "refresh", "pack", "validate"):
        assert command in help_result.output

    for removed_group in ("book", "document"):
        removed = runner.invoke(app, [removed_group, "--help"])
        assert removed.exit_code != 0

    source = tmp_path / "notes.md"
    source.write_text("Notes.", encoding="utf-8")
    noncanonical_output = runner.invoke(
        app,
        [
            "bundle",
            "convert",
            str(source),
            "--output",
            str(tmp_path / "notes.not-a-bundle"),
            "--speech-semantics",
            "preserve",
        ],
    )
    assert noncanonical_output.exit_code != 0
    assert "must end with '.ssmd-bundle'" in noncanonical_output.output

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ssmdconvert import SsmdDocument, load_bundle
from ssmdconvert.cli import app

runner = CliRunner()


def test_bundle_convert_preserves_standalone_ssmd_and_inspects_document_kind(
    tmp_path: Path,
) -> None:
    source = tmp_path / "story.ssmd.md"
    original = '---\nssmd_version: "0.9"\ntitle: "Story"\nlanguage: en-US\n---\n\nMeasure 5 kg.\n'
    source.write_text(original, encoding="utf-8")
    output = tmp_path / "story.ssmd-bundle"

    converted = runner.invoke(app, ["bundle", "convert", str(source), "-o", str(output)])
    assert converted.exit_code == 0, converted.output
    loaded = load_bundle(output)
    assert loaded.kind == "document"
    assert isinstance(loaded.value, SsmdDocument)
    assert loaded.value.ssmd == original

    inspected = runner.invoke(app, ["bundle", "inspect", str(output), "--json"])
    assert inspected.exit_code == 0, inspected.output
    assert json.loads(inspected.output)["kind"] == "document"

    validated = runner.invoke(app, ["bundle", "validate", str(output), "--json"])
    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.output)["kind"] == "document"

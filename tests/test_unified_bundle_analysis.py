from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from epub_support import make_epub
from typer.testing import CliRunner

import ssmdconvert.cli as cli_module
from ssmdconvert.bundle import convert_bundle, load_bundle, pack_bundle
from ssmdconvert.cli import app

runner = CliRunner()


@pytest.mark.parametrize("kind", ["book", "document"])
@pytest.mark.parametrize("packed", [False, True])
def test_analysis_report_txt_and_speech_accept_both_bundle_kinds(
    tmp_path: Path, kind: str, packed: bool
) -> None:
    if kind == "book":
        source = tmp_path / "story.epub"
        make_epub(source, chapter_one_suffix=" Measure 5 kg.")
    else:
        source = tmp_path / "story.ssmd.md"
        source.write_text(
            '---\nssmd_version: "0.9"\ntitle: "Story"\nlanguage: en-US\n---\n\nMeasure 5 kg.\n',
            encoding="utf-8",
        )

    converted = convert_bundle(source, speech_semantics="preserve")
    assert converted.output is not None
    workspace = converted.output
    bundle_path = workspace
    if packed:
        bundle_path = pack_bundle(workspace)
    before = hashlib.sha256(bundle_path.read_bytes()).hexdigest() if packed else None

    report = runner.invoke(app, ["report", str(bundle_path), "--format", "json"])
    assert report.exit_code == 0, report.output
    report_payload = json.loads(report.output)
    assert report_payload["source"]["kind"] == "bundle"
    assert report_payload["source"]["bundle_kind"] == kind
    change_id = report_payload["changes"][0]["id"]
    context = runner.invoke(app, ["context", str(bundle_path), change_id, "--json"])
    assert context.exit_code == 0, context.output
    assert json.loads(context.output)["source_kind"] == "bundle"
    assert json.loads(context.output)["bundle_kind"] == kind

    txt_output = tmp_path / f"{kind}-{packed}.txt"
    projected = runner.invoke(app, ["txt", str(bundle_path), "--output", str(txt_output)])
    assert projected.exit_code == 0, projected.output
    assert txt_output.is_file()

    speech_output = tmp_path / f"annotated-{kind}-{packed}.ssmd-bundle"
    annotated = runner.invoke(
        app,
        ["speech", "annotate", str(bundle_path), "--output", str(speech_output)],
    )
    assert annotated.exit_code == 0, annotated.output
    assert load_bundle(speech_output).kind == kind

    if packed:
        assert hashlib.sha256(bundle_path.read_bytes()).hexdigest() == before


def test_atomic_text_publish_falls_back_without_os_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.md"
    source.write_text("input", encoding="utf-8")
    output = tmp_path / "report.txt"
    monkeypatch.delattr(cli_module.os, "link", raising=False)

    cli_module._write_text_atomically("published", output, source=source, force=False)
    assert output.read_text(encoding="utf-8") == "published"

    with pytest.raises(ValueError, match="already exists"):
        cli_module._write_text_atomically("replacement", output, source=source, force=False)
    assert output.read_text(encoding="utf-8") == "published"

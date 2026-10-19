from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import pytest
from ssmd import parse_structure
from typer.testing import CliRunner

import ssmdconvert.cli as cli_module
from ssmdconvert.cli import app
from ssmdconvert.document_bundle import (
    load_document_bundle,
    load_document_workspace,
    write_document_bundle,
)
from ssmdconvert.models import SourceInfo, SsmdDocument

runner = CliRunner()


def _document() -> SsmdDocument:
    ssmd = '---\nssmd_version: "0.9"\ntitle: "Speech test"\nlanguage: en-US\n---\nMeasure 5 kg.\n'
    return SsmdDocument(
        source=SourceInfo(
            format="markdown",
            media_type="text/markdown",
            name="source.md",
        ),
        metadata={"title": "Speech test", "language": "en-US"},
        ssmd=ssmd,
        source_sha256=hashlib.sha256(b"source artifact").hexdigest(),
    )


def _workspace_bytes(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


@pytest.mark.parametrize(
    ("source_format", "output_format"),
    [("directory", "directory"), ("directory", "zip"), ("zip", "directory"), ("zip", "zip")],
)
def test_speech_freeze_publishes_ssmdoc_without_mutating_source(
    tmp_path: Path,
    source_format: Literal["directory", "zip"],
    output_format: Literal["directory", "zip"],
) -> None:
    source = tmp_path / ("source.ssmdoc" if source_format == "directory" else "source.ssmdoc.zip")
    output = tmp_path / ("frozen.ssmdoc" if output_format == "directory" else "frozen.ssmdoc.zip")
    original = _document()
    write_document_bundle(original, source, format=source_format)
    before = _workspace_bytes(source) if source.is_dir() else source.read_bytes()

    result = runner.invoke(app, ["speech", "freeze", str(source), "-o", str(output)])

    assert result.exit_code == 0, result.output
    frozen = load_document_bundle(output)
    assert "{sub=" in frozen.ssmd
    assert (
        parse_structure(frozen.ssmd, dialect="0.9", normalize=False).clean_text
        == parse_structure(original.ssmd, dialect="0.9", normalize=False).clean_text
    )
    assert frozen.source_sha256 == original.source_sha256
    assert frozen.metadata == original.metadata
    assert frozen.speech_semantics is not None
    assert frozen.speech_semantics["status"] == "complete"
    assert frozen.speech_semantics["source_sha256"] == original.source_sha256
    after = _workspace_bytes(source) if source.is_dir() else source.read_bytes()
    assert after == before


def test_speech_freeze_accepts_dirty_workspace_and_preserves_its_current_content(
    tmp_path: Path,
) -> None:
    source = tmp_path / "dirty.ssmdoc"
    output = tmp_path / "frozen.ssmdoc"
    write_document_bundle(_document(), source, format="directory")
    current_path = source / "document.ssmd.md"
    current_path.write_text(
        current_path.read_text(encoding="utf-8").replace("Measure", "Please measure"),
        encoding="utf-8",
    )
    dirty_before = _workspace_bytes(source)
    assert load_document_workspace(source).dirty

    result = runner.invoke(app, ["speech", "freeze", str(source), "-o", str(output)])

    assert result.exit_code == 0, result.output
    frozen = load_document_bundle(output)
    assert frozen.ssmd.startswith('---\nssmd_version: "0.9"')
    assert "Please measure" in frozen.ssmd
    assert "{sub=" in frozen.ssmd
    assert _workspace_bytes(source) == dirty_before


def test_speech_freeze_rejects_source_change_during_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.ssmdoc"
    output = tmp_path / "must-not-exist.ssmdoc"
    write_document_bundle(_document(), source, format="directory")
    document_path = source / "document.ssmd.md"
    original_freeze = cli_module.freeze_speech_api

    def mutate_after_freeze(analysis: object) -> object:
        frozen = original_freeze(analysis)  # type: ignore[arg-type]
        document_path.write_text(
            document_path.read_text(encoding="utf-8").replace("5 kg", "6 kg"),
            encoding="utf-8",
        )
        return frozen

    monkeypatch.setattr(cli_module, "freeze_speech_api", mutate_after_freeze)
    result = runner.invoke(app, ["speech", "freeze", str(source), "-o", str(output)])

    assert result.exit_code == 1
    assert "source section document-0001 changed" in result.output
    assert not output.exists()
    assert "6 kg" in document_path.read_text(encoding="utf-8")

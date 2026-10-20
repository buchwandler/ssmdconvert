from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import pytest
from ssmd import parse_structure
from typer.testing import CliRunner

import ssmdconvert.cli as cli_module
from ssmdconvert import SsmdDocument, load_bundle
from ssmdconvert._document_bundle import write_document_bundle
from ssmdconvert.cli import app
from ssmdconvert.models import SourceInfo

runner = CliRunner()


def _document() -> SsmdDocument:
    ssmd = '---\nssmd_version: "0.9"\ntitle: "Speech test"\nlanguage: en-US\n---\nMeasure 5 kg.\n'
    return SsmdDocument(
        source=SourceInfo(format="markdown", media_type="text/markdown", name="source.md"),
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


@pytest.mark.parametrize("source_format", ["directory", "zip"])
def test_speech_freeze_publishes_canonical_document_bundle_without_mutating_source(
    tmp_path: Path, source_format: Literal["directory", "zip"]
) -> None:
    source = tmp_path / (
        "source.ssmd-bundle" if source_format == "directory" else "source.ssmd-bundle.zip"
    )
    output = tmp_path / f"frozen-{source_format}.ssmd-bundle"
    original = _document()
    write_document_bundle(original, source, format=source_format)
    before = _workspace_bytes(source) if source.is_dir() else source.read_bytes()

    result = runner.invoke(app, ["speech", "freeze", str(source), "-o", str(output)])

    assert result.exit_code == 0, result.output
    frozen = load_bundle(output)
    assert frozen.kind == "document"
    assert isinstance(frozen.value, SsmdDocument)
    assert "{sub=" in frozen.value.ssmd
    assert (
        parse_structure(frozen.value.ssmd, dialect="0.9", normalize=False).clean_text
        == parse_structure(original.ssmd, dialect="0.9", normalize=False).clean_text
    )
    assert frozen.value.source_sha256 == original.source_sha256
    assert frozen.value.metadata == original.metadata
    assert frozen.value.speech_semantics is not None
    assert frozen.value.speech_semantics["status"] == "complete"
    after = _workspace_bytes(source) if source.is_dir() else source.read_bytes()
    assert after == before


def test_speech_freeze_accepts_dirty_workspace_and_preserves_current_content(
    tmp_path: Path,
) -> None:
    source = tmp_path / "dirty.ssmd-bundle"
    output = tmp_path / "frozen.ssmd-bundle"
    write_document_bundle(_document(), source, format="directory")
    current_path = source / "document.ssmd.md"
    current_path.write_text(
        current_path.read_text(encoding="utf-8").replace("Measure", "Please measure"),
        encoding="utf-8",
    )
    dirty_before = _workspace_bytes(source)

    result = runner.invoke(app, ["speech", "freeze", str(source), "-o", str(output)])

    assert result.exit_code == 0, result.output
    frozen = load_bundle(output)
    assert isinstance(frozen.value, SsmdDocument)
    assert "Please measure" in frozen.value.ssmd
    assert "{sub=" in frozen.value.ssmd
    assert _workspace_bytes(source) == dirty_before


def test_speech_freeze_rejects_source_change_during_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.ssmd-bundle"
    output = tmp_path / "must-not-exist.ssmd-bundle"
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

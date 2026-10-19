from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from ssmd import parse_structure
from typer.testing import CliRunner

from ssmdconvert.cli import app
from ssmdconvert.document_bundle import load_document_bundle

runner = CliRunner()
SSMD = (
    '---\nssmd_version: "0.9"\ntitle: "Reviewed story"\nlanguage: "en"\n'
    "pause_defaults:\n  enabled: true\n---\n\n"
    "Opening paragraph.\n\n"
    ':::{voice="guest"}\nGuest text.\n:::\n'
)


def test_document_convert_preserves_reviewed_ssmd_and_default_name(tmp_path: Path) -> None:
    source = tmp_path / "story.ssmd.md"
    source.write_bytes(SSMD.encode("utf-8"))

    result = runner.invoke(app, ["document", "convert", str(source)])

    bundle = tmp_path / "story.ssmdoc"
    assert result.exit_code == 0, result.output
    assert bundle.is_dir()
    assert not (tmp_path / "story.ssmd.ssmdoc").exists()
    assert (bundle / "document.ssmd.md").read_bytes() == source.read_bytes()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["name"] == source.name
    assert manifest["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest["metadata"]["title"] == "Reviewed story"
    assert manifest["metadata"]["language"] == "en"
    assert manifest["metadata"]["pause_defaults"] == {"enabled": True}
    assert 'voice="guest"' in (bundle / "document.ssmd.md").read_text(encoding="utf-8")


def test_document_convert_non_ssmd_source_captures_original_hash(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n\nA paragraph.", encoding="utf-8")

    result = runner.invoke(app, ["document", "convert", str(source)])

    output = tmp_path / "notes.ssmdoc"
    assert result.exit_code == 0, result.output
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["format"] == "markdown"
    assert manifest["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert load_document_bundle(output).ssmd.startswith("---\n")

    ssmd_source = tmp_path / "draft.ssmd"
    ssmd_source.write_text(SSMD, encoding="utf-8")
    result = runner.invoke(app, ["document", "convert", str(ssmd_source)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "draft.ssmdoc" / "document.ssmd.md").is_file()


def test_document_convert_metadata_override_rerenders_ssmd(tmp_path: Path) -> None:
    source = tmp_path / "story.ssmd"
    source.write_text(SSMD, encoding="utf-8")
    output = tmp_path / "reviewed.ssmdoc"

    result = runner.invoke(
        app,
        ["document", "convert", str(source), "-o", str(output), "--title", "New title"],
    )

    assert result.exit_code == 0, result.output
    document = load_document_bundle(output)
    assert document.metadata["title"] == "New title"
    header = parse_structure(document.ssmd, dialect="0.9").header
    assert header["title"] == "New title"
    assert "sequence_fallback_mode" not in header
    assert 'voice="guest"' in document.ssmd


def test_document_convert_zip_format_and_nonstandard_output_error(tmp_path: Path) -> None:
    source = tmp_path / "story.ssmd.md"
    source.write_text(SSMD, encoding="utf-8")
    archive = tmp_path / "story.ssmdoc.zip"
    result = runner.invoke(app, ["document", "convert", str(source), "-o", str(archive)])
    assert result.exit_code == 0, result.output
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist() == ["manifest.json", "document.ssmd.md"]

    bad = runner.invoke(app, ["document", "convert", str(source), "-o", str(tmp_path / "artifact")])
    assert bad.exit_code == 2
    assert "pass --format directory or --format zip" in bad.output

    explicit = runner.invoke(
        app,
        [
            "document",
            "convert",
            str(source),
            "-o",
            str(tmp_path / "artifact"),
            "--format",
            "directory",
        ],
    )
    assert explicit.exit_code == 0, explicit.output
    assert (tmp_path / "artifact" / "manifest.json").is_file()


def test_document_cli_validate_metadata_refresh_and_pack(tmp_path: Path) -> None:
    source = tmp_path / "source.ssmd.md"
    source.write_text(SSMD, encoding="utf-8")
    bundle = tmp_path / "source.ssmdoc"
    converted = runner.invoke(app, ["document", "convert", str(source)])
    assert converted.exit_code == 0, converted.output

    derived_files = {
        bundle / "utterplan" / "cache.txt": "semantic state",
        bundle / "renderplan" / "voice" / "state.toml": "renderer state",
    }
    for path, contents in derived_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    validated = runner.invoke(app, ["document", "validate", str(bundle)])
    assert validated.exit_code == 0, validated.output
    assert "Valid document bundle" in validated.output
    json_validated = runner.invoke(app, ["document", "validate", str(bundle), "--json"])
    assert json_validated.exit_code == 0
    assert json.loads(json_validated.output) == {"valid": True, "bundle": str(bundle)}

    metadata = runner.invoke(app, ["document", "metadata", str(bundle)])
    assert metadata.exit_code == 0, metadata.output
    assert "Workspace: directory" in metadata.output
    assert "Dirty document: 0" in metadata.output
    assert "Title: Reviewed story" in metadata.output
    metadata_json = runner.invoke(app, ["document", "metadata", str(bundle), "--json"])
    assert metadata_json.exit_code == 0
    assert json.loads(metadata_json.output)["metadata"]["language"] == "en"

    (bundle / "document.ssmd.md").write_text(SSMD + "\nChanged.\n", encoding="utf-8")
    dirty = runner.invoke(app, ["document", "metadata", str(bundle)])
    assert dirty.exit_code == 0, dirty.output
    assert "Status: dirty" in dirty.output
    check = runner.invoke(app, ["document", "refresh", str(bundle), "--check"])
    assert check.exit_code == 1
    assert "Workspace dirty" in check.output
    refreshed = runner.invoke(app, ["document", "refresh", str(bundle)])
    assert refreshed.exit_code == 0, refreshed.output
    assert "Status: clean" in refreshed.output
    for path, contents in derived_files.items():
        assert path.read_text(encoding="utf-8") == contents

    archive = tmp_path / "packed.ssmdoc.zip"
    packed = runner.invoke(app, ["document", "pack", str(bundle), "-o", str(archive)])
    assert packed.exit_code == 0, packed.output
    assert load_document_bundle(archive).ssmd.endswith("Changed.\n")
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.namelist() == ["manifest.json", "document.ssmd.md"]
    for path, contents in derived_files.items():
        assert path.read_text(encoding="utf-8") == contents

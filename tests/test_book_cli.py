from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from click import unstyle
from epub_support import make_epub
from ssmd import parse_structure
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


def test_book_convert_language_and_metadata_file_overrides(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text(
        "title: File title\nlanguage: fr-FR\nvoice_defaults: {}\n", encoding="utf-8"
    )
    bundle_path = tmp_path / "book.ssmdbook.zip"

    result = runner.invoke(
        app,
        [
            "book",
            "convert",
            str(source),
            "--metadata-file",
            str(metadata_file),
            "-l",
            "de-DE",
            "--output",
            str(bundle_path),
        ],
    )

    assert result.exit_code == 0, result.output
    book = load_book_bundle(bundle_path)
    assert book.metadata["title"] == "File title"
    assert book.metadata["language"] == "de-DE"
    assert book.metadata["sequence_fallback_mode"] == "preserve"
    assert book.metadata["voice_defaults"] == {}
    for chapter in book.chapters:
        header = parse_structure(chapter.ssmd, dialect="0.9").header
        assert header["language"] == "de-DE"
        assert header["sequence_fallback_mode"] == "preserve"
        assert header["voice_defaults"] == {}


def test_book_metadata_displays_directory_and_zip_metadata(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source, language=None)
    metadata_file = tmp_path / "metadata.yaml"
    metadata_file.write_text(
        """\
        title: Platform Decay
        authors:
          - Martha Wells
        voice_defaults:
          narrator:
            rate: slow
        """,
        encoding="utf-8",
    )

    for bundle_name in ("book.ssmdbook", "book.ssmdbook.zip"):
        bundle = tmp_path / bundle_name
        converted = runner.invoke(
            app,
            [
                "book",
                "convert",
                str(source),
                "--metadata-file",
                str(metadata_file),
                "--output",
                str(bundle),
            ],
        )
        assert converted.exit_code == 0, converted.output

        human = runner.invoke(app, ["book", "metadata", str(bundle)])
        assert human.exit_code == 0, human.output
        assert "Title: Platform Decay" in human.output
        if bundle_name.endswith(".zip"):
            assert "Workspace: no" in human.output
            assert "Status: valid" in human.output
        else:
            assert "Workspace: directory" in human.output
            assert "Status: clean" in human.output
            assert "Dirty chapters: 0" in human.output
        assert "Authors: Martha Wells" in human.output
        assert "Language: not set" in human.output
        assert "Sequence fallback mode: preserve" in human.output
        assert '"narrator"' in human.output
        assert '"rate": "slow"' in human.output

        stored = load_book_bundle(bundle)
        json_result = runner.invoke(app, ["book", "metadata", str(bundle), "--json"])
        assert json_result.exit_code == 0, json_result.output
        expected = {"metadata": dict(stored.metadata)}
        assert json.loads(json_result.output) == expected
        assert json_result.output == (
            json.dumps(
                expected,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
        assert "language" not in expected["metadata"]


def test_book_metadata_reports_missing_and_invalid_bundles(tmp_path: Path) -> None:
    missing = runner.invoke(app, ["book", "metadata", str(tmp_path / "missing.ssmdbook")])
    assert missing.exit_code != 0
    assert "does not exist" in unstyle(missing.output)

    invalid = tmp_path / "invalid.ssmdbook"
    invalid.mkdir()
    result = runner.invoke(app, ["book", "metadata", str(invalid)])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "manifest.json" in result.output


def test_book_refresh_and_non_mutating_check(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    bundle = tmp_path / "book.ssmdbook"
    converted = runner.invoke(app, ["book", "convert", str(source), "-o", str(bundle)])
    assert converted.exit_code == 0, converted.output

    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chapter_entry = manifest["chapters"][0]
    chapter_path = bundle / chapter_entry["path"]
    edited_text = chapter_path.read_text(encoding="utf-8") + "\n\nEdited in workspace.\n"
    chapter_path.write_bytes(edited_text.encode("utf-8"))
    dirty_manifest = manifest_path.read_bytes()

    check = runner.invoke(app, ["book", "refresh", str(bundle), "--check"])
    assert check.exit_code == 1, check.output
    assert "Workspace dirty" in check.output
    assert "Dirty chapters: 1" in check.output
    assert manifest_path.read_bytes() == dirty_manifest

    refreshed = runner.invoke(app, ["book", "refresh", str(bundle)])
    assert refreshed.exit_code == 0, refreshed.output
    assert "Changed digests: 1" in refreshed.output
    assert "Status: clean" in refreshed.output
    assert load_book_bundle(bundle).chapters[0].ssmd == edited_text

    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    updated_entry = updated_manifest["chapters"][0]
    assert updated_entry["sha256"] == hashlib.sha256(edited_text.encode("utf-8")).hexdigest()
    assert updated_entry["char_count"] == len(edited_text)
    clean_check = runner.invoke(app, ["book", "refresh", str(bundle), "--check"])
    assert clean_check.exit_code == 0, clean_check.output
    assert "Workspace clean" in clean_check.output


def test_book_metadata_reports_dirty_workspace_before_stored_metadata(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    bundle = tmp_path / "book.ssmdbook"
    converted = runner.invoke(app, ["book", "convert", str(source), "-o", str(bundle)])
    assert converted.exit_code == 0, converted.output

    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    chapter_path = bundle / manifest["chapters"][0]["path"]
    chapter_path.write_text(
        chapter_path.read_text(encoding="utf-8") + "\n\nMetadata sees edits.\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["book", "metadata", str(bundle)])
    assert result.exit_code == 0, result.output
    assert "Workspace: directory" in result.output
    assert "Status: dirty" in result.output
    assert "Dirty chapters: 1" in result.output
    assert result.output.index("Dirty chapters: 1") < result.output.index("Stored metadata")


def test_book_pack_packs_dirty_workspace_without_readio_or_source_mutation(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    bundle = tmp_path / "book.ssmdbook"
    converted = runner.invoke(app, ["book", "convert", str(source), "-o", str(bundle)])
    assert converted.exit_code == 0, converted.output

    manifest_path = bundle / "manifest.json"
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    chapter_entry = manifest["chapters"][0]
    chapter_path = bundle / chapter_entry["path"]
    edited_text = chapter_path.read_text(encoding="utf-8") + "\n\nPacked current edit.\n"
    chapter_path.write_bytes(edited_text.encode("utf-8"))
    local_state = bundle / ".readio" / "cache"
    local_state.mkdir(parents=True)
    (local_state / "state.json").write_text("downstream-only", encoding="utf-8")

    archive = tmp_path / "book.ssmdbook.zip"
    packed = runner.invoke(app, ["book", "pack", str(bundle), "-o", str(archive)])
    assert packed.exit_code == 0, packed.output
    assert "Packed SSMD book ZIP" in packed.output
    assert manifest_path.read_bytes() == original_manifest
    assert load_book_bundle(archive).chapters[0].ssmd == edited_text

    with zipfile.ZipFile(archive) as zip_file:
        assert zip_file.namelist() == [
            "manifest.json",
            "chapters/chapter-0001.ssmd.md",
            "chapters/chapter-0002.ssmd.md",
        ]
        assert not any(name.startswith(".readio/") for name in zip_file.namelist())
        assert zip_file.read(chapter_entry["path"]).decode("utf-8") == edited_text

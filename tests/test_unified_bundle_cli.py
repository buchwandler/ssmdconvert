from __future__ import annotations

import json
from pathlib import Path

import pytest
from epub_support import make_epub
from typer.testing import CliRunner

from ssmdconvert._book_bundle import load_book_bundle
from ssmdconvert.cli import app

runner = CliRunner()


def test_bundle_convert_uses_profile_for_every_chapter_and_preserve_mode(tmp_path: Path) -> None:
    source = tmp_path / "profile.epub"
    profile = tmp_path / "speech.toml"
    make_epub(
        source,
        chapter_one_suffix=" ART B-E ART’s.",
        chapter_two_suffix=" B-E ART.",
    )
    profile.write_text(
        """schema = "ssmdconvert-speech-profile"
version = 1
[replacements]
"ART" = "art"
"B-E" = "B E"
""",
        encoding="utf-8",
    )

    output = tmp_path / "frozen.ssmd-bundle"
    frozen = runner.invoke(
        app,
        [
            "bundle",
            "convert",
            str(source),
            "-o",
            str(output),
            "--speech-profile",
            str(profile),
        ],
    )
    assert frozen.exit_code == 0, frozen.output
    book = load_book_bundle(output)
    assert len(book.chapters) == 2
    for chapter in book.chapters:
        assert '[ART]{sub="art"}' in chapter.ssmd
        assert '[B-E]{sub="B E"}' in chapter.ssmd
    assert '[ART’s]{sub="art’s"}' in book.chapters[0].ssmd

    preserved_output = tmp_path / "preserved.ssmd-bundle"
    preserved = runner.invoke(
        app,
        [
            "bundle",
            "convert",
            str(source),
            "-o",
            str(preserved_output),
            "--speech-profile",
            str(profile),
            "--speech-semantics",
            "preserve",
        ],
    )
    assert preserved.exit_code == 0, preserved.output
    assert "Speech profile: loaded, not materialized because speech semantics are preserved." in (
        preserved.output
    )
    preserved_book = load_book_bundle(preserved_output)
    assert all('{sub="art"}' not in chapter.ssmd for chapter in preserved_book.chapters)

    document = tmp_path / "profile.md"
    document.write_text("# Document\n\nART B-E.\n", encoding="utf-8")
    document_output = tmp_path / "document.ssmd-bundle"
    document_result = runner.invoke(
        app,
        [
            "bundle",
            "convert",
            str(document),
            "-o",
            str(document_output),
            "--speech-profile",
            str(profile),
        ],
    )
    assert document_result.exit_code == 0, document_result.output
    stored_profile = (document_output / "speech.toml").read_text(encoding="utf-8")
    assert '"ART" = "art"' in stored_profile
    assert '"B-E" = "B E"' in stored_profile


def test_forced_conversion_reuses_destination_profile_without_external_option(
    tmp_path: Path,
) -> None:
    source = tmp_path / "profile-rebuild.epub"
    make_epub(source, chapter_one_suffix=" ART B-E.")
    output = tmp_path / "profile-rebuild.ssmd-bundle"
    initial = runner.invoke(app, ["bundle", "convert", str(source), "-o", str(output)])
    assert initial.exit_code == 0, initial.output
    (output / "speech.toml").write_text(
        """schema = "ssmdconvert-speech-profile"
version = 1
[replacements]
"ART" = "art"
"B-E" = "B E"
""",
        encoding="utf-8",
    )

    rebuilt = runner.invoke(
        app,
        ["bundle", "convert", str(source), "-o", str(output), "--force"],
    )
    assert rebuilt.exit_code == 0, rebuilt.output
    book = load_book_bundle(output)
    assert '[ART]{sub="art"}' in book.chapters[0].ssmd
    assert '[B-E]{sub="B E"}' in book.chapters[0].ssmd
    stored_profile = (output / "speech.toml").read_text(encoding="utf-8")
    assert '"ART" = "art"' in stored_profile
    assert '"B-E" = "B E"' in stored_profile

    external = tmp_path / "override.toml"
    external.write_text(
        'schema = "ssmdconvert-speech-profile"\nversion = 1\n[replacements]\n"ART" = "A R T"\n',
        encoding="utf-8",
    )
    overridden = runner.invoke(
        app,
        [
            "bundle",
            "convert",
            str(source),
            "-o",
            str(output),
            "--force",
            "--speech-profile",
            str(external),
        ],
    )
    assert overridden.exit_code == 0, overridden.output
    assert "replacing bundle-local profile" in overridden.output
    assert '[ART]{sub="A R T"}' in load_book_bundle(output).chapters[0].ssmd
    assert '"ART" = "A R T"' in (output / "speech.toml").read_text(encoding="utf-8")


def test_invalid_destination_profile_aborts_forced_rebuild_untouched(tmp_path: Path) -> None:
    source = tmp_path / "invalid-rebuild.epub"
    make_epub(source, chapter_one_suffix=" ART.")
    output = tmp_path / "invalid-rebuild.ssmd-bundle"
    initial = runner.invoke(app, ["bundle", "convert", str(source), "-o", str(output)])
    assert initial.exit_code == 0, initial.output
    chapter_path = output / "chapters" / "chapter-0001.ssmd.md"
    original_chapter = chapter_path.read_bytes()
    invalid_profile = output / "speech.toml"
    invalid_profile.write_text("not a speech profile", encoding="utf-8")

    rebuilt = runner.invoke(
        app,
        ["bundle", "convert", str(source), "-o", str(output), "--force"],
    )
    assert rebuilt.exit_code != 0
    assert "invalid speech profile" in rebuilt.output
    assert chapter_path.read_bytes() == original_chapter
    assert invalid_profile.read_text(encoding="utf-8") == "not a speech profile"


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

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ssmd import parse_structure
from typer.testing import CliRunner

import ssmdconvert.cli as cli_module
from ssmdconvert import Book, BookChapter, SourceInfo, SsmdDocument, pack_bundle, write_bundle
from ssmdconvert._book_bundle import load_book_bundle, write_book_bundle
from ssmdconvert.cli import app
from ssmdconvert.speech.profile import parse_speech_profile, speech_profile_fingerprint

runner = CliRunner()


def _document(body: str, *, language: str | None = "en-US") -> str:
    language_line = f"language: {language}\n" if language is not None else ""
    return f'---\nssmd_version: "0.9"\n{language_line}---\n{body}\n'


def _book(path: Path) -> Path:
    book = Book(
        source=SourceInfo(format="epub", media_type="application/epub+zip", name="input.epub"),
        metadata={"title": "Speech test", "language": "en-US"},
        chapters=(
            BookChapter(
                id="chapter-0001",
                source_number=1,
                title="First",
                ssmd=_document("Measure 5 kg."),
            ),
            BookChapter(
                id="chapter-0002",
                source_number=2,
                title="Second",
                ssmd=_document("This chapter stays unchanged."),
            ),
        ),
        source_sha256="1" * 64,
        source_chapter_count=2,
    )
    return write_book_bundle(book, path, format="directory")  # type: ignore[arg-type]


def _speech_document_bundle(path: Path) -> Path:
    document = SsmdDocument(
        source=SourceInfo(format="ssmd", media_type="text/markdown", name="source.ssmd.md"),
        metadata={"language": "en-US"},
        ssmd=_document("ART met B-E."),
        source_sha256="2" * 64,
    )
    return write_bundle(document, path)


def test_speech_audit_json_is_read_only_and_uses_shared_change_ids(tmp_path: Path) -> None:
    source = tmp_path / "audit.ssmd"
    original = _document("Measure 5 kg.")
    source.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["speech", "audit", str(source), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "ssmdconvert.speech-audit.v2"
    assert payload["changes"][0]["id"].startswith("chg:v1:")
    assert payload["changes"][0]["source"] == "5 kg"
    assert payload["changes"][0]["replacement"] == "five kilograms"
    assert payload["changes"][0]["ssmd"]["mapping_status"] == "exact"
    assert payload["changes"][0]["ssmd"]["final_disposition"] == "applied"
    assert source.read_text(encoding="utf-8") == original

    assert payload["freeze_mapping"]["complete"] is True
    assert payload["freeze_mapping"]["applied"] == 1


def test_speech_profile_is_consistent_across_analysis_and_freeze_commands(tmp_path: Path) -> None:
    source = tmp_path / "profile-source.ssmd"
    profile = tmp_path / "speech.toml"
    original = _document("ART met B-E. ART’s comm stayed open.")
    source.write_text(original, encoding="utf-8")
    profile.write_text(
        """schema = "ssmdconvert-speech-profile"
version = 1
[replacements]
"ART" = "art"
"B-E" = "B E"
""",
        encoding="utf-8",
    )

    report = runner.invoke(
        app, ["report", str(source), "--speech-profile", str(profile), "--format", "md"]
    )
    assert report.exit_code == 0, report.output
    assert "Speech profile" in report.output
    assert "explicit replacements: 2" in report.output

    txt = runner.invoke(app, ["txt", str(source), "--speech-profile", str(profile)])
    assert txt.exit_code == 0, txt.output
    assert "art met B E. art’s comm stayed open." in txt.output

    audit = runner.invoke(
        app, ["speech", "audit", str(source), "--speech-profile", str(profile), "--json"]
    )
    assert audit.exit_code == 0, audit.output
    changes = {item["source"]: item["replacement"] for item in json.loads(audit.output)["changes"]}
    assert changes["ART"] == "art"
    assert changes["B-E"] == "B E"
    assert changes["ART’s"] == "art’s"

    annotated = tmp_path / "annotated.ssmd"
    annotation = runner.invoke(
        app,
        [
            "speech",
            "annotate",
            str(source),
            "-o",
            str(annotated),
            "--speech-profile",
            str(profile),
        ],
    )
    assert annotation.exit_code == 0, annotation.output
    frozen = annotated.read_text(encoding="utf-8")
    assert '[ART]{sub="art"}' in frozen
    assert '[B-E]{sub="B E"}' in frozen
    assert '[ART’s]{sub="art’s"}' in frozen
    assert (
        parse_structure(frozen, dialect="0.9").clean_text
        == parse_structure(original, dialect="0.9").clean_text
    )

    freeze_output = tmp_path / "frozen.ssmd"
    freeze = runner.invoke(
        app,
        [
            "speech",
            "freeze",
            str(source),
            "-o",
            str(freeze_output),
            "--speech-profile",
            str(profile),
        ],
    )
    assert freeze.exit_code == 0, freeze.output
    assert freeze_output.read_text(encoding="utf-8") == frozen
    assert source.read_text(encoding="utf-8") == original


def test_speech_profile_management_commands_are_safe_and_idempotent(tmp_path: Path) -> None:
    bundle = _book(tmp_path / "legacy.ssmd-bundle")
    profile_path = bundle / "speech.toml"
    assert not profile_path.exists()

    added = runner.invoke(app, ["speech", "set", str(bundle), "ART", "art"])
    assert added.exit_code == 0, added.output
    assert '"ART" = "art"' in profile_path.read_text(encoding="utf-8")
    assert "Re-run bundle conversion" in added.output

    unchanged = runner.invoke(app, ["speech", "set", str(bundle), "ART", "art"])
    assert unchanged.exit_code == 0, unchanged.output
    assert "profile unchanged" in unchanged.output

    updated = runner.invoke(app, ["speech", "set", str(bundle), "ART", "A R T"])
    assert updated.exit_code == 0, updated.output
    assert "ART: art -> A R T" in updated.output

    removed = runner.invoke(app, ["speech", "remove", str(bundle), "ART"])
    assert removed.exit_code == 0, removed.output
    assert "[replacements]" in profile_path.read_text(encoding="utf-8")
    absent = runner.invoke(app, ["speech", "remove", str(bundle), "ART"])
    assert absent.exit_code == 1
    assert "no explicit replacement" in absent.output

    runner.invoke(app, ["speech", "set", str(bundle), "ART", "art"])
    archive = pack_bundle(bundle, tmp_path / "legacy.ssmd-bundle.zip")
    exported = tmp_path / "portable.toml"
    export_result = runner.invoke(app, ["speech", "export", str(archive), "-o", str(exported)])
    assert export_result.exit_code == 0, export_result.output
    assert parse_speech_profile(exported.read_text(encoding="utf-8")).replacements["ART"] == "art"

    refused = runner.invoke(app, ["speech", "export", str(bundle), "-o", str(exported)])
    assert refused.exit_code == 1
    assert "already exists" in refused.output
    overwrite = runner.invoke(
        app, ["speech", "export", str(bundle), "-o", str(exported), "--force"]
    )
    assert overwrite.exit_code == 0, overwrite.output

    inside = runner.invoke(
        app,
        ["speech", "export", str(bundle), "-o", str(bundle / "copy.toml")],
    )
    assert inside.exit_code == 1
    assert "outside the source bundle workspace" in inside.output
    mutation = runner.invoke(app, ["speech", "set", str(archive), "ART", "art"])
    assert mutation.exit_code == 1


def test_bundle_local_profile_is_discovered_by_speech_commands(tmp_path: Path) -> None:
    bundle = _speech_document_bundle(tmp_path / "speech.ssmd-bundle")
    set_art = runner.invoke(app, ["speech", "set", str(bundle), "ART", "art"])
    assert set_art.exit_code == 0, set_art.output
    set_be = runner.invoke(app, ["speech", "set", str(bundle), "B-E", "B E"])
    assert set_be.exit_code == 0, set_be.output

    report = runner.invoke(app, ["report", str(bundle), "--format", "md"])
    assert report.exit_code == 0, report.output
    assert "bundle speech.toml" in report.output

    projected = runner.invoke(app, ["txt", str(bundle)])
    assert projected.exit_code == 0, projected.output
    assert "art met B E." in projected.output

    audit = runner.invoke(app, ["speech", "audit", str(bundle), "--json"])
    assert audit.exit_code == 0, audit.output
    changes = {item["source"]: item["replacement"] for item in json.loads(audit.output)["changes"]}
    assert changes["ART"] == "art"
    assert changes["B-E"] == "B E"

    inventory = runner.invoke(app, ["speech", "inventory", str(bundle), "--format", "json"])
    assert inventory.exit_code == 0, inventory.output
    assert json.loads(inventory.output)["speech_profile"]["explicit_replacements"] == 2

    annotated = tmp_path / "annotated.ssmd-bundle"
    annotation = runner.invoke(app, ["speech", "annotate", str(bundle), "-o", str(annotated)])
    assert annotation.exit_code == 0, annotation.output
    assert (annotated / "speech.toml").is_file()
    assert '[ART]{sub="art"}' in (annotated / "document.ssmd.md").read_text(encoding="utf-8")

    frozen = tmp_path / "frozen.ssmd-bundle"
    freeze = runner.invoke(app, ["speech", "freeze", str(bundle), "-o", str(frozen)])
    assert freeze.exit_code == 0, freeze.output
    assert (frozen / "speech.toml").is_file()
    assert '[B-E]{sub="B E"}' in (frozen / "document.ssmd.md").read_text(encoding="utf-8")
    expected_profile_fingerprint = speech_profile_fingerprint(
        parse_speech_profile((bundle / "speech.toml").read_text(encoding="utf-8"))
    )
    frozen_manifest = json.loads((frozen / "manifest.json").read_text(encoding="utf-8"))
    assert (
        frozen_manifest["speech_semantics"]["speech_profile_fingerprint"]
        == expected_profile_fingerprint
    )

    packed = pack_bundle(bundle, tmp_path / "speech.ssmd-bundle.zip")
    packed_audit = runner.invoke(app, ["speech", "audit", str(packed), "--json"])
    assert packed_audit.exit_code == 0, packed_audit.output
    packed_changes = {
        item["source"]: item["replacement"] for item in json.loads(packed_audit.output)["changes"]
    }
    assert packed_changes["ART"] == "art"

    external = tmp_path / "override.toml"
    external.write_text(
        'schema = "ssmdconvert-speech-profile"\nversion = 1\n[replacements]\n"ART" = "A R T"\n',
        encoding="utf-8",
    )
    override = runner.invoke(
        app,
        ["speech", "audit", str(bundle), "--speech-profile", str(external), "--json"],
    )
    assert override.exit_code == 0, override.output
    override_changes = {
        item["source"]: item["replacement"] for item in json.loads(override.output)["changes"]
    }
    assert override_changes["ART"] == "A R T"


def test_speech_freeze_reports_json_and_human_summaries(tmp_path: Path) -> None:
    source = tmp_path / "freeze-source.ssmd"
    output = tmp_path / "frozen.ssmd"
    report_path = tmp_path / "freeze-report.json"
    source.write_text(_document("Measure 5 kg."), encoding="utf-8")

    human = runner.invoke(
        app,
        ["speech", "freeze", str(source), "-o", str(output), "--report", str(report_path)],
    )
    assert human.exit_code == 0, human.output
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["format"] == "ssmdconvert-speech-freeze-report"
    assert report["version"] == 1
    assert report["status"] == "complete"
    assert report["summary"]["unresolved"] == 0
    assert "Speech freeze complete:" in human.output
    assert "author-owned" in human.output
    assert "{sub=" in output.read_text(encoding="utf-8")

    json_output = tmp_path / "frozen-json.ssmd"
    machine = runner.invoke(
        app,
        ["speech", "freeze", str(source), "-o", str(json_output), "--json"],
    )
    assert machine.exit_code == 0, machine.output
    payload = json.loads(machine.output)
    assert payload["status"] == "complete"
    assert payload["output"] == str(json_output)
    assert payload["summary"]["unresolved"] == 0


def test_speech_freeze_failure_reports_incomplete_without_ssmd_output(tmp_path: Path) -> None:
    source = tmp_path / "unresolved.ssmd"
    output = tmp_path / "must-not-exist.ssmd"
    report_path = tmp_path / "incomplete-report.json"
    source.write_text(_document("Measure 5 kg.", language=None), encoding="utf-8")

    result = runner.invoke(
        app,
        ["speech", "freeze", str(source), "-o", str(output), "--report", str(report_path)],
    )

    assert result.exit_code == 1
    assert not output.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "incomplete"
    assert report["complete"] is False
    assert report["output"] is None
    assert report["failure"]


def test_speech_freeze_report_write_failure_names_published_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.ssmd"
    output = tmp_path / "published.ssmd"
    report_path = tmp_path / "freeze-report.json"
    source.write_text(_document("Measure 5 kg."), encoding="utf-8")
    write_text = cli_module._write_text_atomically

    def fail_report_write(text: str, path: Path, **kwargs: object) -> None:
        if path == report_path:
            raise OSError("report disk full")
        write_text(text, path, **kwargs)

    monkeypatch.setattr(cli_module, "_write_text_atomically", fail_report_write)
    result = runner.invoke(
        app,
        ["speech", "freeze", str(source), "-o", str(output), "--report", str(report_path)],
    )

    assert result.exit_code == 1
    assert output.is_file()
    assert "SSMD speech artifact was published at" in result.output
    assert "freeze report was not written to" in result.output


def test_standalone_annotate_is_safe_and_freeze_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source.ssmd"
    annotated = tmp_path / "annotated.ssmd"
    frozen = tmp_path / "frozen.ssmd"
    original = _document("Dr. Smith has 5 kg.")
    source.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["speech", "annotate", str(source), "-o", str(annotated)])
    assert result.exit_code == 0, result.output
    first = annotated.read_text(encoding="utf-8")
    assert "{sub=" in first
    assert parse_structure(first, dialect="0.9", normalize=False).clean_text == (
        parse_structure(original, dialect="0.9", normalize=False).clean_text
    )
    assert source.read_text(encoding="utf-8") == original

    second = runner.invoke(app, ["speech", "freeze", str(annotated), "-o", str(frozen)])
    assert second.exit_code == 0, second.output
    assert frozen.read_bytes() == annotated.read_bytes()

    refused = runner.invoke(app, ["speech", "freeze", str(source), "-o", str(source), "--force"])
    assert refused.exit_code == 1
    assert "must not be the input file" in refused.output
    assert source.read_text(encoding="utf-8") == original


def test_speech_destination_overwrite_requires_force(tmp_path: Path) -> None:
    source = tmp_path / "source.ssmd"
    output = tmp_path / "existing.ssmd"
    source.write_text(_document("Measure 5 kg."), encoding="utf-8")
    output.write_text("keep this output", encoding="utf-8")

    refused = runner.invoke(app, ["speech", "annotate", str(source), "-o", str(output)])
    assert refused.exit_code == 1
    assert "already exists" in refused.output
    assert output.read_text(encoding="utf-8") == "keep this output"

    replaced = runner.invoke(
        app,
        ["speech", "annotate", str(source), "-o", str(output), "--force"],
    )
    assert replaced.exit_code == 0, replaced.output
    assert "{sub=" in output.read_text(encoding="utf-8")


def test_annotate_rejects_unresolved_language_without_creating_output(tmp_path: Path) -> None:
    source = tmp_path / "unresolved.ssmd"
    output = tmp_path / "annotated.ssmd"
    source.write_text(_document("Measure 5 kg.", language=None), encoding="utf-8")

    result = runner.invoke(app, ["speech", "annotate", str(source), "-o", str(output)])

    assert result.exit_code == 1
    assert "effective language is unresolved" in result.output
    assert not output.exists()


def test_bundle_chapter_selection_and_freeze_roundtrip(tmp_path: Path) -> None:
    source = _book(tmp_path / "source.ssmd-bundle")
    annotated = tmp_path / "annotated.ssmd-bundle"
    frozen = tmp_path / "frozen.ssmd-bundle"

    first = runner.invoke(
        app,
        ["speech", "annotate", str(source), "--chapters", "1", "-o", str(annotated)],
    )
    assert first.exit_code == 0, first.output
    annotated_book = load_book_bundle(annotated)
    assert "{sub=" in annotated_book.chapters[0].ssmd
    assert annotated_book.chapters[1].ssmd == load_book_bundle(source).chapters[1].ssmd

    second = runner.invoke(
        app,
        ["speech", "freeze", str(annotated), "--chapters", "1", "-o", str(frozen)],
    )
    assert second.exit_code == 0, second.output
    frozen_book = load_book_bundle(frozen)
    assert frozen_book.chapters == annotated_book.chapters
    assert frozen_book.speech_semantics is not None
    assert frozen_book.speech_semantics["status"] == "complete"


def test_dirty_workspace_writes_only_to_a_new_destination(tmp_path: Path) -> None:
    workspace = _book(tmp_path / "workspace.ssmd-bundle")
    manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    chapter = next(item for item in manifest["chapters"] if item["id"] == "chapter-0001")
    chapter_path = workspace / chapter["path"]
    chapter_path.write_text(
        chapter_path.read_text(encoding="utf-8").replace("5 kg", "6 kg"),
        encoding="utf-8",
    )

    inside = runner.invoke(
        app,
        ["speech", "annotate", str(workspace), "-o", str(workspace / "nested.ssmd-bundle")],
    )
    assert inside.exit_code == 1
    assert "outside the source workspace" in inside.output
    assert not (workspace / "nested.ssmd-bundle").exists()

    output = tmp_path / "clean-copy.ssmd-bundle"
    result = runner.invoke(app, ["speech", "annotate", str(workspace), "-o", str(output)])
    assert result.exit_code == 0, result.output
    output_book = load_book_bundle(output)
    assert "{sub=" in output_book.chapters[0].ssmd
    assert "6 kg" in output_book.chapters[0].ssmd
    assert workspace.is_dir()

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ssmd import parse_structure
from typer.testing import CliRunner

import ssmdconvert.cli as cli_module
from ssmdconvert import Book, BookChapter, SourceInfo
from ssmdconvert._book_bundle import load_book_bundle, write_book_bundle
from ssmdconvert.cli import app

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

from __future__ import annotations

import json
from pathlib import Path

from ssmd import parse_structure
from typer.testing import CliRunner

from ssmdconvert import Book, BookChapter, SourceInfo, load_book_bundle, write_book_bundle
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
    assert payload["schema"] == "ssmdconvert.speech-audit.v1"
    assert payload["changes"][0]["id"].startswith("chg:v1:")
    assert payload["changes"][0]["source"] == "5 kg"
    assert payload["changes"][0]["replacement"] == "five kilograms"
    assert payload["changes"][0]["ssmd"]["mapping_status"] == "exact"
    assert source.read_text(encoding="utf-8") == original


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
    source = _book(tmp_path / "source.ssmdbook")
    annotated = tmp_path / "annotated.ssmdbook.zip"
    frozen = tmp_path / "frozen.ssmdbook.zip"

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
    assert frozen.read_bytes() == annotated.read_bytes()


def test_dirty_workspace_writes_only_to_a_new_destination(tmp_path: Path) -> None:
    workspace = _book(tmp_path / "workspace.ssmdbook")
    manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    chapter = next(item for item in manifest["chapters"] if item["id"] == "chapter-0001")
    chapter_path = workspace / chapter["path"]
    chapter_path.write_text(
        chapter_path.read_text(encoding="utf-8").replace("5 kg", "6 kg"),
        encoding="utf-8",
    )

    inside = runner.invoke(
        app,
        ["speech", "annotate", str(workspace), "-o", str(workspace / "nested.ssmdbook")],
    )
    assert inside.exit_code == 1
    assert "outside the source workspace" in inside.output
    assert not (workspace / "nested.ssmdbook").exists()

    output = tmp_path / "clean-copy.ssmdbook"
    result = runner.invoke(app, ["speech", "annotate", str(workspace), "-o", str(output)])
    assert result.exit_code == 0, result.output
    output_book = load_book_bundle(output)
    assert "{sub=" in output_book.chapters[0].ssmd
    assert "6 kg" in output_book.chapters[0].ssmd
    assert workspace.is_dir()

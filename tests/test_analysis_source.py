from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ssmdconvert import Book, BookChapter, SourceInfo, write_book_bundle
from ssmdconvert.analysis import load_ssmd_source, select_sections
from ssmdconvert.analysis.fingerprints import content_fingerprint, sha256_file
from ssmdconvert.errors import AnalysisSourceError


def _ssmd(title: str, body: str) -> str:
    return f'---\nssmd_version: "0.9"\ntitle: "{title}"\nlanguage: en-US\n---\n{body}\n'


def _book() -> Book:
    return Book(
        source=SourceInfo(format="epub", media_type="application/epub+zip", name="book.epub"),
        metadata={"title": "Book title", "language": "en-US"},
        chapters=(
            BookChapter(
                id="chapter-0005",
                source_number=5,
                title="Fifth first",
                ssmd=_ssmd("Fifth first", "Content from source chapter five."),
                level=1,
            ),
            BookChapter(
                id="chapter-0002",
                source_number=2,
                title="Second in source",
                ssmd=_ssmd("Second in source", "Content from source chapter two."),
                level=2,
            ),
        ),
        source_sha256="1" * 64,
        source_chapter_count=5,
    )


def _bundle(tmp_path: Path, *, format: str = "directory") -> Path:
    output = tmp_path / ("book.ssmdbook" if format == "directory" else "book.ssmdbook.zip")
    return write_book_bundle(_book(), output, format=format)  # type: ignore[arg-type]


@pytest.mark.parametrize("suffix", [".ssmd", ".ssmd.md"])
def test_load_standalone_ssmd_and_ssmd_md(tmp_path: Path, suffix: str) -> None:
    source_path = tmp_path / f"story{suffix}"
    raw = _ssmd("Story", "Hello there.").encode("utf-8")
    source_path.write_bytes(raw)

    source = load_ssmd_source(source_path)

    assert source.kind == "ssmd"
    assert source.workspace_type == "standalone"
    assert source.workspace_status == "valid"
    assert source.title == "Story"
    assert source.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert source.sections[0].id == "document-0001"
    assert source.sections[0].chapter_sha256 == source.source_sha256
    assert source.sections[0].ssmd == raw.decode("utf-8")
    assert select_sections(source, "1") == source.sections


def test_load_zip_bundle_and_preserve_source_order_for_selection(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, format="zip")

    source = load_ssmd_source(bundle)
    selected = select_sections(source, "2,5")

    assert source.workspace_type == "zip"
    assert source.workspace_status == "valid"
    assert source.title == "Book title"
    assert [section.id for section in source.sections] == ["chapter-0005", "chapter-0002"]
    assert [section.id for section in selected] == ["chapter-0005", "chapter-0002"]
    assert source.source_sha256 == hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert all(section.chapter_sha256 for section in source.sections)


def test_load_clean_and_dirty_directory_workspace_uses_current_chapter_bytes(
    tmp_path: Path,
) -> None:
    workspace_path = _bundle(tmp_path)
    clean = load_ssmd_source(workspace_path)
    manifest = json.loads((workspace_path / "manifest.json").read_text(encoding="utf-8"))
    chapter_path = workspace_path / manifest["chapters"][0]["path"]
    chapter_path.write_text(_ssmd("Edited", "Current dirty content."), encoding="utf-8")

    dirty = load_ssmd_source(workspace_path)

    assert clean.workspace_status == "clean"
    assert clean.dirty_chapters == ()
    assert dirty.workspace_type == "directory"
    assert dirty.workspace_status == "dirty"
    assert dirty.dirty_chapters == ("chapter-0005",)
    assert dirty.sections[0].ssmd.endswith("Current dirty content.\n")
    assert dirty.sections[0].chapter_sha256 == hashlib.sha256(chapter_path.read_bytes()).hexdigest()
    assert dirty.content_fingerprint != clean.content_fingerprint


def test_dot_loads_current_directory_when_it_is_a_book_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _bundle(tmp_path)
    monkeypatch.chdir(workspace)

    source = load_ssmd_source(".")

    assert source.path == workspace.resolve()
    assert source.workspace_type == "directory"
    assert len(source.sections) == 2


def test_invalid_source_manifest_is_reported_as_source_error(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.ssmdbook"
    invalid.mkdir()
    (invalid / "manifest.json").write_text("{", encoding="utf-8")

    with pytest.raises(AnalysisSourceError, match="could not load SSMD book workspace"):
        load_ssmd_source(invalid)


def test_invalid_chapter_utf8_is_rejected_for_workspace(tmp_path: Path) -> None:
    workspace = _bundle(tmp_path)
    manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    (workspace / manifest["chapters"][0]["path"]).write_bytes(b"\xff")

    with pytest.raises(AnalysisSourceError, match="not UTF-8"):
        load_ssmd_source(workspace)


def test_invalid_standalone_utf8_and_ssmd_are_rejected(tmp_path: Path) -> None:
    invalid_utf8 = tmp_path / "invalid.ssmd"
    invalid_utf8.write_bytes(b"\xff")
    with pytest.raises(AnalysisSourceError, match="not valid UTF-8"):
        load_ssmd_source(invalid_utf8)

    invalid_ssmd = tmp_path / "invalid-content.ssmd"
    invalid_ssmd.write_text("plain text", encoding="utf-8")
    with pytest.raises(AnalysisSourceError, match="not valid SSMD 0.9"):
        load_ssmd_source(invalid_ssmd)


def test_unsupported_source_extension_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "story.md"
    source.write_text(_ssmd("Story", "Hello."), encoding="utf-8")

    with pytest.raises(AnalysisSourceError, match="unsupported SSMD source"):
        load_ssmd_source(source)


def test_content_fingerprint_includes_ordered_hashes_and_metadata() -> None:
    chapters = (("one", "a" * 64), ("two", "b" * 64))
    original = content_fingerprint(chapters, {"language": "en-US", "title": "Book"})

    assert original == content_fingerprint(chapters, {"title": "Book", "language": "en-US"})
    assert original != content_fingerprint(
        tuple(reversed(chapters)), {"language": "en-US", "title": "Book"}
    )
    assert original != content_fingerprint(chapters, {"language": "fr-FR", "title": "Book"})


def test_sha256_file_streams_to_expected_digest(tmp_path: Path) -> None:
    path = tmp_path / "bytes.bin"
    path.write_bytes(b"some exact bytes")
    assert sha256_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_invalid_chapter_ssmd_is_rejected_for_workspace(tmp_path: Path) -> None:
    workspace = _bundle(tmp_path)
    manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    (workspace / manifest["chapters"][0]["path"]).write_text("not SSMD", encoding="utf-8")

    with pytest.raises(AnalysisSourceError, match="not valid SSMD 0.9"):
        load_ssmd_source(workspace)

from __future__ import annotations

import hashlib
import importlib
import json
import stat
import warnings
import zipfile
from pathlib import Path
from typing import Any

import pytest
from epub_support import make_epub
from ssmd import parse_structure

from ssmdconvert import (
    BookBundleError,
    BookBundleValidationError,
    convert_book,
    load_book_bundle,
    validate_book_bundle,
    write_book_bundle,
)


def _book(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "book.epub"
    make_epub(source)
    return source, convert_book(source)


def _write_directory(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    _source, book = _book(tmp_path)
    directory = write_book_bundle(book, tmp_path / "book.ssmdbook", format="directory")
    return directory, json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(directory: Path, manifest: dict[str, Any]) -> None:
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _assert_same_book(expected: Any, actual: Any) -> None:
    assert actual.metadata == expected.metadata
    assert actual.source.format == expected.source.format
    assert actual.source.media_type == expected.source.media_type
    assert actual.source.name == expected.source.name
    assert actual.source.path is None
    assert actual.source_sha256 == expected.source_sha256
    assert actual.source_chapter_count == expected.source_chapter_count
    assert [
        (
            chapter.id,
            chapter.source_number,
            chapter.title,
            chapter.ssmd,
            chapter.href,
            chapter.source_id,
            chapter.source_parent_id,
            chapter.parent_id,
        )
        for chapter in actual.chapters
    ] == [
        (
            chapter.id,
            chapter.source_number,
            chapter.title,
            chapter.ssmd,
            chapter.href,
            chapter.source_id,
            chapter.source_parent_id,
            chapter.parent_id,
        )
        for chapter in expected.chapters
    ]


def test_directory_and_zip_roundtrip_and_equivalence(tmp_path: Path) -> None:
    source, book = _book(tmp_path)
    directory = write_book_bundle(book, tmp_path / "book.ssmdbook", format="directory")
    archive = write_book_bundle(book, tmp_path / "book.ssmdbook.zip", format="zip")

    from_directory = load_book_bundle(directory)
    from_archive = load_book_bundle(archive)
    _assert_same_book(book, from_directory)
    _assert_same_book(book, from_archive)
    assert from_directory.chapters == from_archive.chapters
    validate_book_bundle(directory)
    validate_book_bundle(archive)

    manifest_bytes = (directory / "manifest.json").read_bytes()
    with zipfile.ZipFile(archive) as zip_file:
        assert zip_file.read("manifest.json") == manifest_bytes
        assert zip_file.namelist() == [
            "manifest.json",
            "chapters/chapter-0001.ssmd.md",
            "chapters/chapter-0002.ssmd.md",
        ]
        for chapter in book.chapters:
            path = f"chapters/{chapter.id}.ssmd.md"
            assert zip_file.read(path) == (directory / path).read_bytes()

    assert from_directory.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    repacked = write_book_bundle(from_directory, tmp_path / "repacked.ssmdbook.zip", format="zip")
    assert load_book_bundle(repacked).chapters == from_directory.chapters


def test_source_hash_is_captured_before_bundle_write(tmp_path: Path) -> None:
    source, book = _book(tmp_path)
    original_hash = book.source_sha256
    source.write_bytes(b"mutated source")

    bundle = write_book_bundle(book, tmp_path / "captured.ssmdbook", format="directory")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["source"]["sha256"] == original_hash
    assert manifest["source"]["sha256"] != hashlib.sha256(source.read_bytes()).hexdigest()


def test_bundle_paths_keep_selected_source_numbers(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    book = convert_book(source, chapters="2")
    directory = write_book_bundle(book, tmp_path / "subset", format="directory")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["chapters"][0]["id"] == "chapter-0002"
    assert manifest["chapters"][0]["source_number"] == 2
    assert manifest["chapters"][0]["path"] == "chapters/chapter-0002.ssmd.md"
    assert (directory / manifest["chapters"][0]["path"]).is_file()


def test_bundle_roundtrip_preserves_source_and_canonical_parent_ids(tmp_path: Path) -> None:
    source = tmp_path / "nested.epub"
    make_epub(source, nested_navigation=True)
    book = convert_book(source)
    directory = write_book_bundle(book, tmp_path / "nested.ssmdbook", format="directory")

    loaded = load_book_bundle(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert loaded.chapters[1].source_parent_id == book.chapters[1].source_parent_id
    assert loaded.chapters[1].parent_id == "chapter-0001"
    assert manifest["chapters"][1]["source_parent_id"] == book.chapters[1].source_parent_id
    assert manifest["chapters"][1]["parent_id"] == "chapter-0001"


def test_manifest_order_is_authoritative_and_zip_is_deterministic(tmp_path: Path) -> None:
    _source, book = _book(tmp_path)
    first = write_book_bundle(book, tmp_path / "first.zip", format="zip")
    second = write_book_bundle(book, tmp_path / "second.zip", format="zip")
    assert first.read_bytes() == second.read_bytes()

    with zipfile.ZipFile(first) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == [
            "manifest.json",
            "chapters/chapter-0001.ssmd.md",
            "chapters/chapter-0002.ssmd.md",
        ]
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
        assert all(stat.S_ISREG(info.external_attr >> 16) for info in infos)

    directory = write_book_bundle(book, tmp_path / "ordered", format="directory")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["chapters"].reverse()
    _write_manifest(directory, manifest)
    assert [chapter.source_number for chapter in load_book_bundle(directory).chapters] == [2, 1]


def test_bundle_output_refuses_overwrite_and_removes_stale_files(tmp_path: Path) -> None:
    _source, book = _book(tmp_path)
    output = write_book_bundle(book, tmp_path / "replace", format="directory")
    stale = output / "stale-file"
    stale.write_text("stale", encoding="utf-8")

    with pytest.raises(BookBundleError, match="already exists"):
        write_book_bundle(book, output, format="directory")
    assert stale.is_file()

    write_book_bundle(book, output, format="directory", overwrite=True)
    assert not stale.exists()
    assert load_book_bundle(output).chapters == book.chapters


def test_failed_zip_overwrite_preserves_existing_output(tmp_path: Path, monkeypatch: Any) -> None:
    _source, book = _book(tmp_path)
    output = write_book_bundle(book, tmp_path / "existing.zip", format="zip")
    original = output.read_bytes()
    bundle_module = importlib.import_module("ssmdconvert.bundle")

    def fail_write(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(bundle_module, "_write_zip", fail_write)
    with pytest.raises(BookBundleError, match="simulated write failure"):
        write_book_bundle(book, output, format="zip", overwrite=True)

    assert output.read_bytes() == original
    assert not list(tmp_path.glob(".existing.zip.tmp-*"))


def test_failed_directory_overwrite_preserves_existing_tree(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _source, book = _book(tmp_path)
    output = write_book_bundle(book, tmp_path / "existing-directory", format="directory")
    original_manifest = (output / "manifest.json").read_bytes()
    stale = output / "stale-file"
    stale.write_text("keep until replacement succeeds", encoding="utf-8")
    bundle_module = importlib.import_module("ssmdconvert.bundle")

    def fail_write(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("simulated directory write failure")

    monkeypatch.setattr(bundle_module, "_write_directory", fail_write)
    with pytest.raises(BookBundleError, match="simulated directory write failure"):
        write_book_bundle(book, output, format="directory", overwrite=True)

    assert (output / "manifest.json").read_bytes() == original_manifest
    assert stale.read_text(encoding="utf-8") == "keep until replacement succeeds"
    assert not list(tmp_path.glob(".existing-directory.tmp-*"))


@pytest.mark.parametrize("format", ["directory", "zip"])
def test_bundle_enforces_manifest_and_chapter_size_limits(
    tmp_path: Path,
    monkeypatch: Any,
    format: str,
) -> None:
    _source, book = _book(tmp_path)
    output = tmp_path / ("limited" if format == "directory" else "limited.zip")
    bundle = write_book_bundle(book, output, format=format)  # type: ignore[arg-type]
    bundle_module = importlib.import_module("ssmdconvert.bundle")

    monkeypatch.setattr(bundle_module, "_MAX_MANIFEST_BYTES", 1)
    with pytest.raises(BookBundleValidationError, match="size limit"):
        load_book_bundle(bundle)

    monkeypatch.setattr(bundle_module, "_MAX_MANIFEST_BYTES", 2 * 1024 * 1024)
    monkeypatch.setattr(bundle_module, "_MAX_CHAPTER_BYTES", 1)
    with pytest.raises(BookBundleValidationError, match="limit"):
        load_book_bundle(bundle)


@pytest.mark.parametrize("format", ["directory", "zip"])
def test_bundle_enforces_total_chapter_size_limit(
    tmp_path: Path,
    monkeypatch: Any,
    format: str,
) -> None:
    _source, book = _book(tmp_path)
    output = tmp_path / ("limited-total" if format == "directory" else "limited-total.zip")
    bundle = write_book_bundle(book, output, format=format)  # type: ignore[arg-type]
    bundle_module = importlib.import_module("ssmdconvert.bundle")

    monkeypatch.setattr(bundle_module, "_MAX_TOTAL_CHAPTER_BYTES", 1)
    with pytest.raises(BookBundleValidationError, match="total size limit"):
        load_book_bundle(bundle)


def test_bundle_rejects_missing_manifest_and_bad_json(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    missing.mkdir()
    with pytest.raises(BookBundleValidationError, match="manifest.json"):
        load_book_bundle(missing)

    directory, _manifest = _write_directory(tmp_path / "bad-json")
    (directory / "manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises(BookBundleValidationError, match="valid UTF-8 JSON"):
        load_book_bundle(directory)

    archive = tmp_path / "missing-manifest.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("chapters/unused", b"unused")
    with pytest.raises(BookBundleValidationError, match="manifest.json"):
        load_book_bundle(archive)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("format", "other", "unsupported bundle format"),
        ("schema_version", 2, "unsupported schema version"),
        ("ssmd_version", "0.8", "unsupported SSMD version"),
        ("metadata", [], "metadata must be a JSON object"),
    ],
)
def test_bundle_rejects_invalid_manifest_header(
    tmp_path: Path,
    field: str,
    value: Any,
    message: str,
) -> None:
    directory, manifest = _write_directory(tmp_path)
    manifest[field] = value
    _write_manifest(directory, manifest)

    with pytest.raises(BookBundleValidationError, match=message):
        load_book_bundle(directory)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("id", "duplicate chapter id"),
        ("source_number", "duplicate source_number"),
        ("path", "duplicate chapter path"),
    ],
)
def test_bundle_rejects_duplicate_chapter_identifiers_and_provenance(
    tmp_path: Path,
    field: str,
    message: str,
) -> None:
    directory, manifest = _write_directory(tmp_path)
    manifest["chapters"][1][field] = manifest["chapters"][0][field]
    _write_manifest(directory, manifest)

    with pytest.raises(BookBundleValidationError, match=message):
        load_book_bundle(directory)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/absolute/chapter.md",
        "C:/chapters/chapter.md",
        "chapters/../escape.md",
        "chapters\\escape.md",
        "chapters/with\x00nul.md",
    ],
)
def test_bundle_rejects_unsafe_manifest_chapter_paths(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    directory, manifest = _write_directory(tmp_path)
    manifest["chapters"][0]["path"] = unsafe_path
    _write_manifest(directory, manifest)

    with pytest.raises(BookBundleValidationError, match="path"):
        load_book_bundle(directory)


def test_bundle_rejects_missing_chapters_and_hash_corruption(tmp_path: Path) -> None:
    directory, manifest = _write_directory(tmp_path / "missing-chapter")
    (directory / manifest["chapters"][0]["path"]).unlink()
    with pytest.raises(BookBundleValidationError, match="missing or unresolvable"):
        load_book_bundle(directory)

    directory, manifest = _write_directory(tmp_path / "wrong-hash")
    chapter_path = directory / manifest["chapters"][0]["path"]
    chapter_path.write_bytes(chapter_path.read_bytes() + b"corruption")
    with pytest.raises(BookBundleValidationError, match="SHA256 mismatch"):
        load_book_bundle(directory)


def test_bundle_rejects_invalid_ssmd_even_when_hash_matches(tmp_path: Path) -> None:
    directory, manifest = _write_directory(tmp_path)
    entry = manifest["chapters"][0]
    raw = b"plain text without SSMD front matter"
    (directory / entry["path"]).write_bytes(raw)
    entry["sha256"] = hashlib.sha256(raw).hexdigest()
    _write_manifest(directory, manifest)

    with pytest.raises(BookBundleValidationError, match="not valid SSMD"):
        load_book_bundle(directory)


def test_directory_bundle_rejects_symlink_escape(tmp_path: Path) -> None:
    directory, manifest = _write_directory(tmp_path / "symlink")
    chapter = directory / manifest["chapters"][0]["path"]
    outside = tmp_path / "outside.ssmd"
    outside.write_bytes(chapter.read_bytes())
    chapter.unlink()
    chapter.symlink_to(outside)

    with pytest.raises(BookBundleValidationError, match="outside the bundle directory"):
        load_book_bundle(directory)


def test_zip_bundle_rejects_duplicate_names_symlinks_and_traversal(tmp_path: Path) -> None:
    _source, book = _book(tmp_path)
    valid = write_book_bundle(book, tmp_path / "valid.zip", format="zip")

    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(valid) as original, zipfile.ZipFile(duplicate, "w") as output:
        entries = [(info.filename, original.read(info)) for info in original.infolist()]
        for name, data in entries:
            output.writestr(name, data)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            output.writestr("manifest.json", entries[0][1])
    with pytest.raises(BookBundleValidationError, match="duplicate member names"):
        load_book_bundle(duplicate)

    symlink = tmp_path / "symlink.zip"
    with zipfile.ZipFile(valid) as original, zipfile.ZipFile(symlink, "w") as output:
        for info in original.infolist():
            data = original.read(info)
            if info.filename.startswith("chapters/"):
                info = zipfile.ZipInfo(info.filename)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                data = b"../outside"
            output.writestr(info, data)
    with pytest.raises(BookBundleValidationError, match="symlink entries"):
        load_book_bundle(symlink)

    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(valid) as original, zipfile.ZipFile(traversal, "w") as output:
        for info in original.infolist():
            output.writestr(info, original.read(info))
        output.writestr("../escape", b"bad")
    with pytest.raises(BookBundleValidationError, match="relative and normalized"):
        load_book_bundle(traversal)


def test_bundle_validation_uses_the_loader(tmp_path: Path) -> None:
    _source, book = _book(tmp_path)
    archive = write_book_bundle(book, tmp_path / "book.zip", format="zip")

    assert validate_book_bundle(archive) is None


@pytest.mark.parametrize("format", ["directory", "zip"])
def test_bundle_roundtrip_preserves_sequence_fallback_mode(tmp_path: Path, format: str) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    book = convert_book(source, sequence_fallback_mode="preserve")
    output = tmp_path / ("preserve.ssmdbook" if format == "directory" else "preserve.ssmdbook.zip")

    bundle = write_book_bundle(book, output, format=format)  # type: ignore[arg-type]
    loaded = load_book_bundle(bundle)

    assert loaded.metadata["sequence_fallback_mode"] == "preserve"
    for chapter in loaded.chapters:
        assert (
            parse_structure(chapter.ssmd, dialect="0.9").header["sequence_fallback_mode"]
            == "preserve"
        )
    if format == "directory":
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["schema_version"] == 1
        assert manifest["metadata"]["sequence_fallback_mode"] == "preserve"


def test_bundle_without_sequence_fallback_metadata_remains_valid(tmp_path: Path) -> None:
    _source, book = _book(tmp_path)
    bundle = write_book_bundle(book, tmp_path / "old.ssmdbook", format="directory")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    del manifest["metadata"]["sequence_fallback_mode"]
    for chapter in manifest["chapters"]:
        path = bundle / chapter["path"]
        content = path.read_text(encoding="utf-8")
        legacy_content = content.replace("sequence_fallback_mode: spell\n", "")
        assert legacy_content != content
        path.write_text(legacy_content, encoding="utf-8")
        chapter["sha256"] = hashlib.sha256(legacy_content.encode("utf-8")).hexdigest()
    _write_manifest(bundle, manifest)

    loaded = load_book_bundle(bundle)

    assert "sequence_fallback_mode" not in loaded.metadata
    for chapter in loaded.chapters:
        assert "sequence_fallback_mode" not in parse_structure(chapter.ssmd, dialect="0.9").header

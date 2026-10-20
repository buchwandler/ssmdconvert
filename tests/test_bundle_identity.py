from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from ssmdconvert.bundle import load_bundle, validate_bundle, write_bundle
from ssmdconvert.bundle_identity import (
    default_bundle_archive_path,
    default_bundle_workspace_path,
    probe_bundle_kind,
    require_bundle_workspace_path,
)
from ssmdconvert.errors import BundleIdentityError
from ssmdconvert.models import Book, BookChapter, SourceInfo, SsmdDocument


def _workspace(root: Path, manifest: bytes) -> Path:
    path = root / "item.ssmd-bundle"
    path.mkdir()
    (path / "manifest.json").write_bytes(manifest)
    return path


def _archive(path: Path, members: list[tuple[str, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members:
            archive.writestr(name, data)
    return path


@pytest.mark.parametrize(
    ("bundle_format", "kind"),
    [("ssmdconvert.book", "book"), ("ssmdconvert.document", "document")],
)
def test_probe_directory_kind_uses_only_format_and_schema(
    tmp_path: Path, bundle_format: str, kind: str
) -> None:
    manifest = json.dumps(
        {"format": bundle_format, "schema_version": 1, "unvalidated": object.__name__}
    ).encode()
    path = _workspace(tmp_path, manifest)

    assert probe_bundle_kind(path) == kind
    assert require_bundle_workspace_path(path) == path.resolve()


@pytest.mark.parametrize(
    ("bundle_format", "kind"),
    [("ssmdconvert.book", "book"), ("ssmdconvert.document", "document")],
)
def test_probe_archive_kind(tmp_path: Path, bundle_format: str, kind: str) -> None:
    path = _archive(
        tmp_path / "item.ssmd-bundle.zip",
        [("manifest.json", json.dumps({"format": bundle_format, "schema_version": 1}).encode())],
    )

    assert probe_bundle_kind(path) == kind


@pytest.mark.parametrize(
    "manifest",
    [
        b'{"format": "ssmdconvert.book", "schema_version": 1,}',
        b"\xff\xfe",
        b'{"format":"ssmdconvert.book","format":"ssmdconvert.document","schema_version":1}',
        b'{"format":"ssmdconvert.book","schema_version":NaN}',
    ],
)
def test_probe_rejects_non_strict_json(tmp_path: Path, manifest: bytes) -> None:
    path = _workspace(tmp_path, manifest)

    with pytest.raises(BundleIdentityError, match="strict UTF-8 JSON"):
        probe_bundle_kind(path)


def test_probe_rejects_missing_unknown_and_wrong_schema(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ssmd-bundle"
    missing.mkdir()
    with pytest.raises(BundleIdentityError, match="manifest.json"):
        probe_bundle_kind(missing)

    unknown = _workspace(
        tmp_path,
        b'{"format":"other","schema_version":1}',
    )
    with pytest.raises(BundleIdentityError, match="unsupported SSMD bundle manifest format"):
        probe_bundle_kind(unknown)

    wrong_schema = tmp_path / "schema.ssmd-bundle"
    wrong_schema.mkdir()
    (wrong_schema / "manifest.json").write_text(
        '{"format":"ssmdconvert.book","schema_version":2}', encoding="utf-8"
    )
    with pytest.raises(BundleIdentityError, match="unsupported SSMD bundle manifest schema"):
        probe_bundle_kind(wrong_schema)


@pytest.mark.parametrize("schema_version", [2, True, 1.0])
def test_probe_requires_integer_schema_version(tmp_path: Path, schema_version: object) -> None:
    path = _workspace(
        tmp_path,
        json.dumps({"format": "ssmdconvert.book", "schema_version": schema_version}).encode(),
    )

    with pytest.raises(BundleIdentityError, match="unsupported SSMD bundle manifest schema"):
        probe_bundle_kind(path)


def test_probe_rejects_duplicate_archive_manifests(tmp_path: Path) -> None:
    path = _archive(
        tmp_path / "duplicate.ssmd-bundle.zip",
        [
            ("manifest.json", b'{"format":"ssmdconvert.book","schema_version":1}'),
            ("manifest.json", b'{"format":"ssmdconvert.document","schema_version":1}'),
        ],
    )

    with pytest.raises(BundleIdentityError, match="duplicate manifest.json"):
        probe_bundle_kind(path)


def test_probe_rejects_noncanonical_workspace_path(tmp_path: Path) -> None:
    path = tmp_path / "legacy-workspace"
    path.mkdir()
    (path / "manifest.json").write_text(
        '{"format":"ssmdconvert.book","schema_version":1}', encoding="utf-8"
    )

    with pytest.raises(BundleIdentityError, match="expected a .ssmd-bundle workspace"):
        probe_bundle_kind(path)


def test_default_bundle_names() -> None:
    assert default_bundle_workspace_path(Path("novel.epub")).name == "novel.ssmd-bundle"
    assert default_bundle_workspace_path(Path("story.md")).name == "story.ssmd-bundle"
    assert default_bundle_workspace_path(Path("story.ssmd")).name == "story.ssmd-bundle"
    assert default_bundle_workspace_path(Path("story.ssmd.md")).name == "story.ssmd-bundle"
    assert default_bundle_archive_path(Path("novel.ssmd-bundle")).name == "novel.ssmd-bundle.zip"


@pytest.mark.parametrize("packed", [False, True])
def test_probe_rejects_oversized_manifests(tmp_path: Path, packed: bool) -> None:
    raw = b" " * (2 * 1024 * 1024 + 1)
    if packed:
        path = _archive(tmp_path / "large.ssmd-bundle.zip", [("manifest.json", raw)])
    else:
        path = _workspace(tmp_path, raw)

    with pytest.raises(BundleIdentityError, match="2 MiB size limit"):
        probe_bundle_kind(path)


def test_neutral_bundle_facade_dispatches_both_manifest_kinds(tmp_path: Path) -> None:
    source_bytes = b"novel source"
    chapter_ssmd = '---\nssmd_version: "0.9"\ntitle: "Chapter"\n---\n\nChapter text.\n'
    book = Book(
        source=SourceInfo(format="epub", media_type="application/epub+zip", name="novel.epub"),
        metadata={"title": "Novel"},
        chapters=(BookChapter("chapter-0001", 1, "Chapter", chapter_ssmd),),
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        source_chapter_count=1,
    )
    book_path = write_bundle(book, tmp_path / "novel.ssmd-bundle")

    document = SsmdDocument(
        source=SourceInfo(format="ssmd", media_type="text/markdown", name="story.ssmd.md"),
        metadata={"title": "Story"},
        ssmd='---\nssmd_version: "0.9"\ntitle: "Story"\n---\n\nHello.\n',
        source_sha256=hashlib.sha256(b"source bytes").hexdigest(),
    )
    document_path = write_bundle(document, tmp_path / "story.ssmd-bundle")

    assert load_bundle(book_path).kind == "book"
    assert load_bundle(document_path).kind == "document"
    assert validate_bundle(book_path) == "book"
    assert validate_bundle(document_path) == "document"

from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from ssmdconvert.document_bundle import (
    load_document_bundle,
    load_document_workspace,
    refresh_document_workspace,
    validate_document_bundle,
    write_document_bundle,
)
from ssmdconvert.errors import DocumentBundleError, DocumentBundleValidationError
from ssmdconvert.models import SourceInfo, SsmdDocument

SSMD = (
    '---\nssmd_version: "0.9"\ntitle: "Funny printer story"\nlanguage: "en"\n---\n\nHello, 世界.\n'
)
SOURCE_SHA256 = hashlib.sha256(b"source bytes").hexdigest()


def artifact(ssmd: str = SSMD) -> SsmdDocument:
    return SsmdDocument(
        source=SourceInfo(
            format="ssmd",
            media_type="text/markdown",
            name="story.ssmd.md",
        ),
        metadata={"title": "Funny printer story", "language": "en"},
        ssmd=ssmd,
        source_sha256=SOURCE_SHA256,
    )


def test_directory_and_zip_roundtrip_and_canonical_members(tmp_path: Path) -> None:
    directory = write_document_bundle(artifact(), tmp_path / "story.ssmdoc", format="directory")
    archive = write_document_bundle(artifact(), tmp_path / "story.ssmdoc.zip", format="zip")

    assert sorted(path.name for path in directory.iterdir()) == [
        "document.ssmd.md",
        "manifest.json",
    ]
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist() == ["manifest.json", "document.ssmd.md"]
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in bundle.infolist())
        assert all(stat.S_ISREG(info.external_attr >> 16) for info in bundle.infolist())
    assert load_document_bundle(directory) == artifact()
    assert load_document_bundle(archive) == artifact()
    validate_document_bundle(directory)
    validate_document_bundle(archive)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "ssmdconvert.document"
    assert manifest["schema_version"] == 1
    assert manifest["source"]["sha256"] == SOURCE_SHA256
    assert manifest["document"]["char_count"] == len(SSMD)


def test_zip_publication_is_deterministic(tmp_path: Path) -> None:
    one = write_document_bundle(artifact(), tmp_path / "one.ssmdoc.zip", format="zip")
    two = write_document_bundle(artifact(), tmp_path / "two.ssmdoc.zip", format="zip")
    assert one.read_bytes() == two.read_bytes()


def test_strict_loader_rejects_dirty_workspace_but_workspace_loads_it(tmp_path: Path) -> None:
    bundle = write_document_bundle(artifact(), tmp_path / "story.ssmdoc", format="directory")
    edited = SSMD.replace("Hello", "Hello again")
    (bundle / "document.ssmd.md").write_text(edited, encoding="utf-8")

    workspace = load_document_workspace(bundle)
    assert workspace.dirty is True
    assert workspace.status.id == "document-0001"
    assert workspace.document.ssmd == edited
    with pytest.raises(DocumentBundleValidationError, match="SHA256 mismatch"):
        load_document_bundle(bundle)


def test_refresh_preserves_manifest_mode_and_unreferenced_local_state(
    tmp_path: Path,
) -> None:
    bundle = write_document_bundle(artifact(), tmp_path / "story.ssmdoc", format="directory")
    manifest_path = bundle / "manifest.json"
    manifest_path.chmod(0o640)
    manifest_mode = stat.S_IMODE(manifest_path.stat().st_mode)
    unreferenced_files = {
        bundle / "utterplan" / "cache.txt": "semantic state",
        bundle / "renderplan" / "voice" / "state.toml": "renderer state",
        bundle / "tool-state" / "cache" / "state.json": "local cache state",
    }
    for path, contents in unreferenced_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    validate_document_bundle(bundle)
    assert load_document_workspace(bundle).dirty is False
    edited = SSMD + "\nMore text.\n"
    (bundle / "document.ssmd.md").write_text(edited, encoding="utf-8")

    refreshed = refresh_document_workspace(bundle)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["document"]["sha256"] == hashlib.sha256(edited.encode()).hexdigest()
    assert manifest["document"]["char_count"] == len(edited)
    assert stat.S_IMODE(manifest_path.stat().st_mode) == manifest_mode
    assert refreshed.dirty is False
    for path, contents in unreferenced_files.items():
        assert path.read_text(encoding="utf-8") == contents
    validate_document_bundle(bundle)


def test_forced_directory_replacement_removes_unrelated_stale_files(tmp_path: Path) -> None:
    bundle = write_document_bundle(artifact(), tmp_path / "story.ssmdoc", format="directory")
    (bundle / "stale.txt").write_text("stale", encoding="utf-8")
    with pytest.raises(DocumentBundleError, match="already exists"):
        write_document_bundle(artifact(), bundle, format="directory")

    write_document_bundle(artifact(), bundle, format="directory", overwrite=True)
    assert not (bundle / "stale.txt").exists()
    validate_document_bundle(bundle)


def test_failed_forced_directory_replacement_restores_previous_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ssmdconvert import document_bundle

    bundle = write_document_bundle(artifact(), tmp_path / "story.ssmdoc", format="directory")
    (bundle / "keep.txt").write_text("old bundle", encoding="utf-8")
    original_manifest = (bundle / "manifest.json").read_bytes()
    original_replace = document_bundle.os.replace
    failed = False

    def fail_publish(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        nonlocal failed
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            not failed
            and destination_path == bundle
            and source_path.name.startswith(".story.ssmdoc.tmp-")
        ):
            failed = True
            raise OSError("simulated final rename failure")
        original_replace(source, destination)

    monkeypatch.setattr(document_bundle.os, "replace", fail_publish)
    with pytest.raises(DocumentBundleError, match="simulated final rename failure"):
        write_document_bundle(artifact(), bundle, format="directory", overwrite=True)

    assert failed
    assert (bundle / "keep.txt").read_text(encoding="utf-8") == "old bundle"
    assert (bundle / "manifest.json").read_bytes() == original_manifest


def test_directory_symlink_escape_is_rejected(tmp_path: Path) -> None:
    bundle = write_document_bundle(artifact(), tmp_path / "story.ssmdoc", format="directory")
    outside = tmp_path / "outside.ssmd.md"
    outside.write_text(SSMD, encoding="utf-8")
    (bundle / "document.ssmd.md").unlink()
    try:
        (bundle / "document.ssmd.md").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(DocumentBundleValidationError, match="outside the bundle directory"):
        load_document_bundle(bundle)


def test_manifest_schema_and_content_corruption_are_rejected(tmp_path: Path) -> None:
    bundle = write_document_bundle(artifact(), tmp_path / "story.ssmdoc", format="directory")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["document"]["id"] = "chapter-0001"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DocumentBundleValidationError, match="document id"):
        load_document_bundle(bundle)

    write_document_bundle(artifact(), bundle, format="directory", overwrite=True)
    (bundle / "document.ssmd.md").write_bytes(b"\xff")
    with pytest.raises(DocumentBundleValidationError, match="not UTF-8"):
        load_document_workspace(bundle)


def test_zip_duplicate_names_and_symlinks_are_rejected(tmp_path: Path) -> None:
    good = write_document_bundle(artifact(), tmp_path / "good.ssmdoc.zip", format="zip")
    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(good) as source, zipfile.ZipFile(duplicate, "w") as target:
        target.writestr("manifest.json", source.read("manifest.json"))
        target.writestr("document.ssmd.md", source.read("document.ssmd.md"))
        target.writestr("document.ssmd.md", source.read("document.ssmd.md"))
    with pytest.raises(DocumentBundleValidationError, match="duplicate"):
        load_document_bundle(duplicate)

    symlink = tmp_path / "symlink.zip"
    with zipfile.ZipFile(good) as source, zipfile.ZipFile(symlink, "w") as target:
        for info in source.infolist():
            copied = zipfile.ZipInfo(info.filename)
            copied.external_attr = info.external_attr
            target.writestr(copied, source.read(info.filename))
        entry = zipfile.ZipInfo("evil")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        target.writestr(entry, "../../outside")
    with pytest.raises(DocumentBundleValidationError, match="symlink"):
        load_document_bundle(symlink)

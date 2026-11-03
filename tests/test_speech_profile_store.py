from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ssmdconvert.speech.profile import (
    empty_speech_profile,
    parse_speech_profile,
    render_speech_profile,
)
from ssmdconvert.speech.profile_store import (
    BUNDLE_SPEECH_PROFILE_PATH,
    MAX_SPEECH_PROFILE_BYTES,
    read_archive_speech_profile,
    read_bundle_speech_profile,
    read_workspace_speech_profile,
    resolve_conversion_speech_profile,
    resolve_operation_speech_profile,
    write_bundle_speech_profile,
)

_VALID = """schema = "ssmdconvert-speech-profile"
version = 1

[replacements]
"ART" = "art"
"""
_MANIFEST = json.dumps({"format": "ssmdconvert.book", "schema_version": 1}).encode()


def _workspace(tmp_path: Path, name: str = "book.ssmd-bundle") -> Path:
    workspace = tmp_path / name
    workspace.mkdir()
    (workspace / "manifest.json").write_bytes(_MANIFEST)
    return workspace


def _archive(path: Path, *, profile: bytes | None = None, duplicate_profile: bool = False) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", _MANIFEST)
        if profile is not None:
            archive.writestr(BUNDLE_SPEECH_PROFILE_PATH, profile)
            if duplicate_profile:
                archive.writestr(BUNDLE_SPEECH_PROFILE_PATH, profile)
    return path


def test_missing_workspace_and_archive_profiles_resolve_to_empty(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    archive = _archive(tmp_path / "book.ssmd-bundle.zip")

    assert read_workspace_speech_profile(workspace) == empty_speech_profile()
    assert read_workspace_speech_profile(workspace, missing="none") is None
    assert read_archive_speech_profile(archive) == empty_speech_profile()
    assert read_bundle_speech_profile(archive) == empty_speech_profile()
    assert read_archive_speech_profile(archive, missing="none") is None


def test_valid_workspace_profile_loads_and_writes_canonically(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / BUNDLE_SPEECH_PROFILE_PATH).write_text(_VALID, encoding="utf-8")
    assert read_workspace_speech_profile(workspace) == parse_speech_profile(_VALID)

    changed = parse_speech_profile(_VALID.replace('"art"', '"Art"'))
    written = write_bundle_speech_profile(workspace, changed)
    assert written == workspace / BUNDLE_SPEECH_PROFILE_PATH
    assert written.read_text(encoding="utf-8") == render_speech_profile(changed)
    assert read_workspace_speech_profile(workspace) == changed


@pytest.mark.parametrize(
    ("raw", "message"),
    [(b"not toml", "invalid speech profile"), (b"\xff", "strict UTF-8")],
)
def test_invalid_workspace_profile_fails_closed(tmp_path: Path, raw: bytes, message: str) -> None:
    workspace = _workspace(tmp_path)
    (workspace / BUNDLE_SPEECH_PROFILE_PATH).write_bytes(raw)
    with pytest.raises(ValueError, match=message):
        read_workspace_speech_profile(workspace)


def test_oversized_workspace_profile_is_rejected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / BUNDLE_SPEECH_PROFILE_PATH).write_bytes(b" " * (MAX_SPEECH_PROFILE_BYTES + 1))
    with pytest.raises(ValueError, match="size limit"):
        read_workspace_speech_profile(workspace)


def test_external_symlink_escape_is_rejected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    outside = tmp_path / "outside.toml"
    outside.write_text(_VALID, encoding="utf-8")
    (workspace / BUNDLE_SPEECH_PROFILE_PATH).symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        read_workspace_speech_profile(workspace)


def test_archive_profile_loads_and_rejects_oversized_or_duplicate_members(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "valid.ssmd-bundle.zip", profile=_VALID.encode())
    assert read_archive_speech_profile(archive) == parse_speech_profile(_VALID)

    oversized = _archive(
        tmp_path / "oversized.ssmd-bundle.zip",
        profile=b" " * (MAX_SPEECH_PROFILE_BYTES + 1),
    )
    with pytest.raises(ValueError, match="size limit"):
        read_archive_speech_profile(oversized)

    duplicate = _archive(
        tmp_path / "duplicate.ssmd-bundle.zip",
        profile=_VALID.encode(),
        duplicate_profile=True,
    )
    with pytest.raises(ValueError, match="duplicate member"):
        read_archive_speech_profile(duplicate)


def test_explicit_profile_wins_and_bundle_profile_precedes_empty(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    profile = parse_speech_profile(_VALID)
    (workspace / BUNDLE_SPEECH_PROFILE_PATH).write_text(_VALID, encoding="utf-8")
    external = tmp_path / "external.toml"
    external.write_text(render_speech_profile(empty_speech_profile()), encoding="utf-8")

    resolved_bundle = resolve_operation_speech_profile(workspace)
    resolved_explicit = resolve_operation_speech_profile(workspace, external)
    resolved_default = resolve_operation_speech_profile(tmp_path / "input.epub")

    assert resolved_bundle.source == "bundle"
    assert resolved_bundle.profile == profile
    assert resolved_explicit.source == "explicit"
    assert resolved_explicit.profile == empty_speech_profile()
    assert resolved_default.source == "default-empty"


def test_destination_profile_is_resolved_before_replacement(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / BUNDLE_SPEECH_PROFILE_PATH).write_text(_VALID, encoding="utf-8")
    external = tmp_path / "external.toml"
    external.write_text(render_speech_profile(empty_speech_profile()), encoding="utf-8")

    from_destination = resolve_conversion_speech_profile(workspace)
    from_explicit = resolve_conversion_speech_profile(workspace, external)

    assert from_destination.source == "destination"
    assert from_destination.profile == parse_speech_profile(_VALID)
    assert from_explicit.source == "explicit"
    assert from_explicit.profile == empty_speech_profile()
    assert from_explicit.replaces_destination
    assert (workspace / BUNDLE_SPEECH_PROFILE_PATH).read_text(encoding="utf-8") == _VALID


def test_malformed_recognized_destination_profile_fails_closed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / BUNDLE_SPEECH_PROFILE_PATH).write_text("invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid speech profile"):
        resolve_conversion_speech_profile(workspace)


def test_write_refuses_symlink_sidecar(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    outside = tmp_path / "outside.toml"
    outside.write_text(_VALID, encoding="utf-8")
    (workspace / BUNDLE_SPEECH_PROFILE_PATH).symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        write_bundle_speech_profile(workspace, empty_speech_profile())

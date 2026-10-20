"""Canonical bundle paths and safe, kind-only manifest dispatch."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Literal, NoReturn

from .errors import BundleIdentityError

BundleKind = Literal["book", "document"]
BundleStorage = Literal["directory", "zip"]

_WORKSPACE_SUFFIX = ".ssmd-bundle"
_ARCHIVE_SUFFIX = ".ssmd-bundle.zip"
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 10_000
_FORMAT_KINDS: dict[str, BundleKind] = {
    "ssmdconvert.book": "book",
    "ssmdconvert.document": "document",
}


def _fail(path: Path, message: str) -> NoReturn:
    raise BundleIdentityError(f"{path}: {message}")


def require_bundle_workspace_path(path: str | Path) -> Path:
    """Resolve and require an existing canonical editable bundle directory."""
    source = Path(path).expanduser()
    if not source.name.endswith(_WORKSPACE_SUFFIX):
        _fail(source, "expected an editable .ssmd-bundle workspace")
    if not source.is_dir():
        _fail(source, "expected an editable .ssmd-bundle workspace directory")
    try:
        return source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _fail(source, f"could not resolve bundle workspace: {exc}")


def require_bundle_archive_path(path: str | Path) -> Path:
    """Resolve and require an existing canonical packed bundle archive."""
    source = Path(path).expanduser()
    if not source.name.endswith(_ARCHIVE_SUFFIX):
        _fail(source, "expected a packed .ssmd-bundle.zip archive")
    if not source.is_file():
        _fail(source, "expected a regular .ssmd-bundle.zip archive")
    try:
        return source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _fail(source, f"could not resolve packed bundle: {exc}")


def default_bundle_workspace_path(source: str | Path) -> Path:
    """Return the canonical editable workspace name for a source file."""
    source_path = Path(source)
    name = source_path.name
    lowered = name.lower()
    if lowered.endswith(".ssmd.md"):
        stem = name[: -len(".ssmd.md")]
    elif lowered.endswith(".ssmd"):
        stem = name[: -len(".ssmd")]
    else:
        stem = source_path.stem
    return source_path.with_name(f"{stem}{_WORKSPACE_SUFFIX}")


def default_bundle_archive_path(workspace: str | Path) -> Path:
    """Return the canonical packed archive name for an editable workspace."""
    path = Path(workspace)
    if not path.name.endswith(_WORKSPACE_SUFFIX):
        _fail(path, "expected an editable .ssmd-bundle workspace")
    return path.with_name(f"{path.name}{'.zip'}")


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _parse_dispatch_manifest(raw: bytes, path: Path) -> BundleKind:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _fail(path, f"manifest.json is not strict UTF-8 JSON: {exc}")
    if not isinstance(value, dict):
        _fail(path, "manifest.json must contain a JSON object")

    bundle_format = value.get("format")
    kind = _FORMAT_KINDS.get(bundle_format) if isinstance(bundle_format, str) else None
    if kind is None:
        _fail(path, f"unsupported SSMD bundle manifest format: {bundle_format!r}")

    schema_version = value.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        _fail(path, f"unsupported SSMD bundle manifest schema version: {schema_version!r}")
    return kind


def _read_directory_manifest(root: Path, display: Path) -> bytes:
    manifest = root / "manifest.json"
    try:
        if manifest.is_symlink() or not manifest.is_file():
            _fail(display, "manifest.json must be a regular file")
        size = manifest.stat().st_size
        if size > _MAX_MANIFEST_BYTES:
            _fail(display, "manifest.json exceeds the 2 MiB size limit")
        raw = manifest.read_bytes()
    except BundleIdentityError:
        raise
    except OSError as exc:
        _fail(display, f"could not read manifest.json: {exc}")
    if len(raw) > _MAX_MANIFEST_BYTES:
        _fail(display, "manifest.json exceeds the 2 MiB size limit")
    return raw


def _read_archive_manifest(archive_path: Path, display: Path) -> bytes:
    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        _fail(display, f"not a readable packed bundle: {exc}")
    with archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ARCHIVE_MEMBERS:
            _fail(display, "packed bundle contains too many archive members")
        manifests = [info for info in infos if info.filename == "manifest.json"]
        if not manifests:
            _fail(display, "packed bundle is missing manifest.json")
        if len(manifests) != 1:
            _fail(display, "packed bundle contains duplicate manifest.json members")
        info = manifests[0]
        if info.is_dir() or info.file_size > _MAX_MANIFEST_BYTES:
            _fail(display, "packed bundle manifest.json is invalid or exceeds the 2 MiB size limit")
        try:
            with archive.open(info, "r") as stream:
                raw = stream.read(_MAX_MANIFEST_BYTES + 1)
        except (OSError, EOFError, RuntimeError, zipfile.BadZipFile) as exc:
            _fail(display, f"could not read packed bundle manifest.json: {exc}")
        if len(raw) > _MAX_MANIFEST_BYTES:
            _fail(display, "packed bundle manifest.json exceeds the 2 MiB size limit")
        return raw


def probe_bundle_kind(path: str | Path) -> BundleKind:
    """Identify a supported bundle by only its manifest format and schema."""
    source = Path(path).expanduser()
    if source.name.endswith(_WORKSPACE_SUFFIX):
        root = require_bundle_workspace_path(source)
        raw = _read_directory_manifest(root, source)
    elif source.name.endswith(_ARCHIVE_SUFFIX):
        archive_path = require_bundle_archive_path(source)
        raw = _read_archive_manifest(archive_path, source)
    else:
        _fail(source, "expected a .ssmd-bundle workspace or .ssmd-bundle.zip archive")
    return _parse_dispatch_manifest(raw, source)

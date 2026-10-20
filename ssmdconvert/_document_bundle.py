"""Secure serialization and editable-workspace lifecycle for single SSMD documents."""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
import zipfile
import zlib
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Literal, NoReturn, TypeGuard

from .errors import DocumentBundleError, DocumentBundleValidationError
from .models import (
    DocumentWorkspace,
    SourceInfo,
    SsmdDocument,
    WorkspaceDocumentStatus,
)
from .render import validate_ssmd_document

_DOCUMENT_FORMAT = "ssmdconvert.document"
_DOCUMENT_SCHEMA_VERSION = 1
_SSMD_VERSION = "0.9"
_DOCUMENT_ID = "document-0001"
_DOCUMENT_PATH = "document.ssmd.md"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:")
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 10_000


def _invalid(display: str, message: str) -> NoReturn:
    raise DocumentBundleValidationError(f"{display}: {message}")


def _is_integer(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_newlines(text: str) -> str:
    """Use LF for document content and digests on every platform."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _canonical_document_bytes(text: str) -> bytes:
    return _normalize_newlines(text).encode("utf-8", errors="strict")


def _validate_relative_path(value: Any, display: str, *, allow_directory: bool = False) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        _invalid(display, f"invalid bundle path: {value!r}")
    if "\\" in value or value.startswith("/") or _WINDOWS_DRIVE.match(value):
        _invalid(display, f"bundle path must be relative and POSIX-normalized: {value!r}")
    normalized = value[:-1] if allow_directory and value.endswith("/") else value
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or path.as_posix() != normalized
        or any(part in {".", ".."} for part in path.parts)
    ):
        _invalid(display, f"bundle path must be relative and normalized: {value!r}")
    return normalized


def _validate_source_name(value: Any, display: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "\x00" in value
        or "/" in value
        or "\\" in value
        or _WINDOWS_DRIVE.match(value)
    ):
        _invalid(display, f"source name must be a portable filename: {value!r}")
    return value


def _json_value(value: Any, display: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _invalid(display, "metadata must not contain NaN or Infinity")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _invalid(display, "metadata object keys must be strings")
            result[key] = _json_value(item, display)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_value(item, display) for item in value]
    _invalid(display, f"metadata contains a non-JSON value: {type(value).__name__}")


def _validate_speech_semantics(value: Any, display: str) -> None:
    if not isinstance(value, dict):
        _invalid(display, "manifest speech_semantics must be a JSON object")
    status = value.get("status")
    if status not in {"complete", "preserved"}:
        _invalid(display, f"unsupported speech_semantics status: {status!r}")
    if value.get("owner") != "ssmdconvert":
        _invalid(display, "manifest speech_semantics owner must be 'ssmdconvert'")
    if not _is_sha256(value.get("source_sha256")):
        _invalid(
            display, "manifest speech_semantics source_sha256 must be a lowercase SHA256 digest"
        )
    if status == "complete":
        if value.get("engine") != "ttsready":
            _invalid(display, "complete speech_semantics engine must be 'ttsready'")
        for key in (
            "ttsready_version",
            "spokenform_version",
            "profile_fingerprint",
            "override_fingerprint",
            "runtime_fingerprint",
            "prepared_fingerprint",
        ):
            item = value.get(key)
            if not isinstance(item, str) or not item:
                _invalid(display, f"complete speech_semantics {key} must be a non-empty string")
        for key in (
            "profile_fingerprint",
            "override_fingerprint",
            "runtime_fingerprint",
            "prepared_fingerprint",
        ):
            if not _is_sha256(value.get(key)):
                _invalid(
                    display, f"complete speech_semantics {key} must be a lowercase SHA256 digest"
                )


def _validate_manifest(value: Any, display: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _invalid(display, "manifest root must be a JSON object")
    if value.get("format") != _DOCUMENT_FORMAT:
        _invalid(display, f"unsupported bundle format: {value.get('format')!r}")
    if (
        not _is_integer(value.get("schema_version"))
        or value["schema_version"] != _DOCUMENT_SCHEMA_VERSION
    ):
        _invalid(display, f"unsupported schema version: {value.get('schema_version')!r}")
    if value.get("ssmd_version") != _SSMD_VERSION:
        _invalid(display, f"unsupported SSMD version: {value.get('ssmd_version')!r}")
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        _invalid(display, "manifest metadata must be a JSON object")
    if "ssmd_version" in metadata:
        _invalid(display, "manifest metadata must not contain reserved ssmd_version")
    _json_value(metadata, display)

    source = value.get("source")
    if not isinstance(source, dict):
        _invalid(display, "manifest source must be a JSON object")
    if not isinstance(source.get("format"), str) or not source["format"]:
        _invalid(display, "source format must be a non-empty string")
    if "media_type" not in source:
        _invalid(display, "source media_type is required")
    if source["media_type"] is not None and not isinstance(source["media_type"], str):
        _invalid(display, "source media_type must be a string or null")
    _validate_source_name(source.get("name"), display)
    if not _is_sha256(source.get("sha256")):
        _invalid(display, "source sha256 must be a lowercase SHA256 digest")

    document = value.get("document")
    if not isinstance(document, dict):
        _invalid(display, "manifest document must be a JSON object")
    if document.get("id") != _DOCUMENT_ID:
        _invalid(display, f"document id must be {_DOCUMENT_ID!r}")
    if document.get("path") != _DOCUMENT_PATH:
        _invalid(display, f"document path must be {_DOCUMENT_PATH!r}")
    _validate_relative_path(document.get("path"), display)
    char_count = document.get("char_count")
    if not _is_integer(char_count) or char_count < 0:
        _invalid(display, "document char_count must be a non-negative integer")
    if not _is_sha256(document.get("sha256")):
        _invalid(display, "document sha256 must be a lowercase SHA256 digest")
    if "speech_semantics" in value:
        _validate_speech_semantics(value["speech_semantics"], display)
        if value["speech_semantics"]["source_sha256"] != source["sha256"]:
            _invalid(
                display, "manifest speech_semantics source_sha256 does not match source sha256"
            )
    return value


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant {value}")


def _parse_manifest(raw: bytes, display: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _invalid(display, f"manifest is not valid UTF-8 JSON: {exc}")
    return _validate_manifest(value, display)


def _manifest_for_document(document: SsmdDocument) -> tuple[bytes, bytes]:
    if not isinstance(document, SsmdDocument):
        raise DocumentBundleError("write_document_bundle requires an SsmdDocument")
    if not isinstance(document.ssmd, str):
        raise DocumentBundleValidationError("document SSMD must be text")
    try:
        validate_ssmd_document(document.ssmd)
        document_bytes = document.ssmd.encode("utf-8", errors="strict")
        canonical_document_bytes = _canonical_document_bytes(document.ssmd)
    except Exception as exc:
        raise DocumentBundleValidationError(
            f"document does not contain valid UTF-8 SSMD 0.9: {exc}"
        ) from exc
    if len(document_bytes) > _MAX_DOCUMENT_BYTES:
        raise DocumentBundleValidationError("document exceeds the 64 MiB size limit")
    source_name = document.source.name
    if source_name is None and document.source.path is not None:
        source_name = document.source.path.name
    display = "document bundle"
    _validate_source_name(source_name, display)
    if not _is_sha256(document.source_sha256):
        raise DocumentBundleValidationError("document source SHA-256 is missing or invalid")
    metadata = _json_value(document.metadata, display)
    if not isinstance(metadata, dict):
        raise DocumentBundleValidationError("document metadata must be a mapping")
    metadata.pop("ssmd_version", None)
    speech_semantics = None
    if document.speech_semantics is not None:
        speech_semantics = _json_value(document.speech_semantics, display)
        _validate_speech_semantics(speech_semantics, display)
        if speech_semantics.get("source_sha256") != document.source_sha256:
            raise DocumentBundleValidationError(
                "document speech_semantics source_sha256 does not match source sha256"
            )
    manifest: dict[str, Any] = {
        "format": _DOCUMENT_FORMAT,
        "schema_version": _DOCUMENT_SCHEMA_VERSION,
        "ssmd_version": _SSMD_VERSION,
        "metadata": metadata,
        "source": {
            "format": document.source.format,
            "media_type": document.source.media_type,
            "name": source_name,
            "sha256": document.source_sha256,
        },
        "document": {
            "id": _DOCUMENT_ID,
            "path": _DOCUMENT_PATH,
            "char_count": len(_normalize_newlines(document.ssmd)),
            "sha256": _sha256(canonical_document_bytes),
        },
    }
    if not isinstance(document.source.format, str) or not document.source.format:
        raise DocumentBundleValidationError("document source format must be a non-empty string")
    if document.source.media_type is not None and not isinstance(document.source.media_type, str):
        raise DocumentBundleValidationError("document source media_type must be a string or None")
    if speech_semantics is not None:
        manifest["speech_semantics"] = speech_semantics
    _validate_manifest(manifest, "document bundle")
    try:
        raw_manifest = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise DocumentBundleValidationError(
            f"could not serialize document manifest: {exc}"
        ) from exc
    if len(raw_manifest) > _MAX_MANIFEST_BYTES:
        raise DocumentBundleValidationError("document manifest exceeds the 2 MiB size limit")
    return raw_manifest, document_bytes


def _is_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _read_directory_file(root: Path, name: str, display: str, *, max_bytes: int) -> bytes:
    normalized = _validate_relative_path(name, display)
    target = root.joinpath(*PurePosixPath(normalized).parts)
    try:
        resolved = target.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _invalid(display, f"missing or unresolvable bundle file {name!r}: {exc}")
    if not _is_below(resolved, root):
        _invalid(display, f"bundle file resolves outside the bundle directory: {name!r}")
    if not resolved.is_file():
        _invalid(display, f"bundle entry is not a regular file: {name!r}")
    try:
        if resolved.stat().st_size > max_bytes:
            _invalid(display, f"bundle file {name!r} exceeds the size limit ({max_bytes} bytes)")
        data = resolved.read_bytes()
    except OSError as exc:
        _invalid(display, f"could not read bundle file {name!r}: {exc}")
    if len(data) > max_bytes:
        _invalid(display, f"bundle file {name!r} exceeds the size limit ({max_bytes} bytes)")
    return data


def _document_from_manifest(
    manifest: dict[str, Any],
    read_bytes: Callable[[str], bytes],
    display: str,
    *,
    verify_sha256: bool = True,
    statuses: list[WorkspaceDocumentStatus] | None = None,
) -> SsmdDocument:
    entry = manifest["document"]
    raw = read_bytes(entry["path"])
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _invalid(display, f"document {entry['path']!r} is not UTF-8: {exc}")
    text = _normalize_newlines(text)
    actual_sha256 = _sha256(text.encode("utf-8"))
    dirty = actual_sha256 != entry["sha256"]
    if verify_sha256 and dirty:
        _invalid(display, f"SHA256 mismatch for document {entry['path']!r}")
    try:
        validate_ssmd_document(text)
    except Exception as exc:
        _invalid(display, f"document {entry['path']!r} is not valid SSMD 0.9: {exc}")
    if len(text) != entry["char_count"] and verify_sha256:
        _invalid(display, f"document {entry['path']!r} character count does not match manifest")
    if statuses is not None:
        statuses.append(
            WorkspaceDocumentStatus(
                id=entry["id"],
                path=entry["path"],
                expected_sha256=entry["sha256"],
                actual_sha256=actual_sha256,
                dirty=dirty,
            )
        )
    source = manifest["source"]
    return SsmdDocument(
        source=SourceInfo(
            format=source["format"],
            media_type=source["media_type"],
            name=source["name"],
        ),
        metadata=dict(manifest["metadata"]),
        ssmd=text,
        source_sha256=source["sha256"],
        speech_semantics=(
            dict(manifest["speech_semantics"]) if "speech_semantics" in manifest else None
        ),
    )


def _read_directory_bundle(
    source: Path, *, workspace: bool = False
) -> SsmdDocument | DocumentWorkspace:
    display = str(source)
    try:
        root = source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _invalid(display, f"could not resolve bundle directory: {exc}")
    if not root.is_dir():
        _invalid(display, "bundle source is not a directory")
    manifest_bytes = _read_directory_file(
        root, "manifest.json", display, max_bytes=_MAX_MANIFEST_BYTES
    )
    manifest = _parse_manifest(manifest_bytes, display)
    statuses: list[WorkspaceDocumentStatus] | None = [] if workspace else None
    document = _document_from_manifest(
        manifest,
        lambda name: _read_directory_file(root, name, display, max_bytes=_MAX_DOCUMENT_BYTES),
        display,
        verify_sha256=not workspace,
        statuses=statuses,
    )
    if not workspace:
        return document
    assert statuses is not None
    status = statuses[0]
    return DocumentWorkspace(
        path=root,
        document=document,
        status=status,
        dirty=status.dirty,
    )


def _validate_zip_member(info: zipfile.ZipInfo, display: str) -> None:
    _validate_relative_path(info.filename, display, allow_directory=info.is_dir())
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        _invalid(display, f"ZIP symlink entries are not allowed: {info.filename!r}")


def _read_zip_bundle(source: Path) -> SsmdDocument:
    display = str(source)
    try:
        archive = zipfile.ZipFile(source, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        _invalid(display, f"not a readable document ZIP: {exc}")
    with archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ARCHIVE_MEMBERS:
            _invalid(display, "ZIP contains too many archive members")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            _invalid(display, "ZIP contains duplicate member names")
        for info in infos:
            _validate_zip_member(info, display)
        members = {info.filename: info for info in infos}
        manifest_info = members.get("manifest.json")
        if manifest_info is None or manifest_info.is_dir():
            _invalid(display, "ZIP is missing manifest.json")
        if manifest_info.file_size > _MAX_MANIFEST_BYTES:
            _invalid(display, "ZIP manifest.json exceeds the size limit")
        try:
            manifest_bytes = archive.read(manifest_info)
        except (OSError, EOFError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
            _invalid(display, f"could not read ZIP manifest.json: {exc}")
        if len(manifest_bytes) > _MAX_MANIFEST_BYTES:
            _invalid(display, "ZIP manifest.json exceeds the size limit")
        manifest = _parse_manifest(manifest_bytes, display)

        def read_member(name: str) -> bytes:
            info = members.get(name)
            if info is None or info.is_dir():
                _invalid(display, f"ZIP is missing document file {name!r}")
            if info.file_size > _MAX_DOCUMENT_BYTES:
                _invalid(display, f"ZIP document {name!r} exceeds the 64 MiB size limit")
            try:
                data = archive.read(info)
            except (OSError, EOFError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
                _invalid(display, f"could not read ZIP document {name!r}: {exc}")
            if len(data) > _MAX_DOCUMENT_BYTES:
                _invalid(display, f"ZIP document {name!r} exceeds the 64 MiB size limit")
            return data

        return _document_from_manifest(manifest, read_member, display)


def _write_zip(target: Path, manifest: bytes, document: bytes) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in (("manifest.json", manifest), (_DOCUMENT_PATH, document)):
            info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _write_directory(target: Path, manifest: bytes, document: bytes) -> None:
    root = target.resolve()
    for name, data in (("manifest.json", manifest), (_DOCUMENT_PATH, document)):
        normalized = _validate_relative_path(name, str(target))
        destination = root.joinpath(*PurePosixPath(normalized).parts)
        if not _is_below(destination.resolve(strict=False), root):
            raise DocumentBundleError(f"bundle output path escapes the directory: {name!r}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not _is_below(destination.resolve(strict=False), root):
            raise DocumentBundleError(f"bundle output path escapes the directory: {name!r}")
        destination.write_bytes(data)


def _destination_exists(target: Path) -> bool:
    return target.exists() or target.is_symlink()


def _publish_path_no_replace(source: Path, target: Path) -> None:
    link = getattr(os, "link", None)
    if link is not None:
        try:
            link(source, target)
            return
        except OSError as exc:
            unsupported = {
                errno.EPERM,
                errno.EXDEV,
                getattr(errno, "EOPNOTSUPP", -1),
                getattr(errno, "ENOTSUP", -1),
                getattr(errno, "ENOSYS", -1),
            }
            if exc.errno not in unsupported:
                raise
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    reservation = os.fstat(fd)
    os.close(fd)
    try:
        os.replace(source, target)
    except OSError:
        try:
            current = target.stat()
            if (current.st_dev, current.st_ino) == (reservation.st_dev, reservation.st_ino):
                target.unlink()
        except FileNotFoundError:
            pass
        raise


def _write_zip_atomic(target: Path, manifest: bytes, document: bytes, *, overwrite: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or (target.exists() and target.is_dir()):
        raise DocumentBundleError(f"ZIP bundle output must be a regular file: {target}")
    if _destination_exists(target) and not overwrite:
        raise DocumentBundleError(f"bundle output already exists: {target}")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.tmp-", dir=target.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        _write_zip(temporary, manifest, document)
        os.chmod(temporary, 0o644)
        _read_zip_bundle(temporary)
        if overwrite:
            os.replace(temporary, target)
        else:
            try:
                _publish_path_no_replace(temporary, target)
            except FileExistsError as exc:
                raise DocumentBundleError(f"bundle output already exists: {target}") from exc
            temporary.unlink(missing_ok=True)
    finally:
        temporary.unlink(missing_ok=True)


def _new_backup_path(target: Path) -> Path:
    backup = Path(tempfile.mkdtemp(prefix=f".{target.name}.backup-", dir=target.parent))
    backup.rmdir()
    return backup


def _write_directory_atomic(
    target: Path,
    manifest: bytes,
    document: bytes,
    *,
    overwrite: bool,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise DocumentBundleError(f"directory bundle output must be a directory: {target}")
    if _destination_exists(target) and not overwrite:
        raise DocumentBundleError(f"bundle output already exists: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent))
    backup: Path | None = None
    try:
        _write_directory(temporary, manifest, document)
        _read_directory_bundle(temporary)
        if _destination_exists(target):
            if not overwrite:
                raise DocumentBundleError(f"bundle output already exists: {target}")
            if target.is_symlink() or not target.is_dir():
                raise DocumentBundleError(f"directory bundle output must be a directory: {target}")
            backup = _new_backup_path(target)
            os.replace(target, backup)
        try:
            os.replace(temporary, target)
        except OSError:
            if backup is not None:
                os.replace(backup, target)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
            backup = None
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def write_document_bundle(
    document: SsmdDocument,
    output: str | Path,
    *,
    format: Literal["directory", "zip"],
    overwrite: bool = False,
) -> Path:
    """Atomically write a strict single-document directory or ZIP bundle."""
    if format not in ("directory", "zip"):
        raise DocumentBundleError("bundle format must be 'directory' or 'zip'")
    manifest, document_bytes = _manifest_for_document(document)
    raw_target = Path(os.path.abspath(Path(output).expanduser()))
    target = raw_target.parent.resolve() / raw_target.name
    try:
        if format == "zip":
            _write_zip_atomic(target, manifest, document_bytes, overwrite=overwrite)
        else:
            _write_directory_atomic(target, manifest, document_bytes, overwrite=overwrite)
    except DocumentBundleError:
        raise
    except OSError as exc:
        raise DocumentBundleError(f"could not write document bundle {target}: {exc}") from exc
    return target


def load_document_bundle(source: str | Path) -> SsmdDocument:
    """Load and strictly validate a document directory or ZIP bundle."""
    path = Path(source).expanduser()
    if not path.exists():
        _invalid(str(path), "bundle does not exist")
    if path.is_dir():
        result = _read_directory_bundle(path)
        assert isinstance(result, SsmdDocument)
        return result
    if path.is_file():
        return _read_zip_bundle(path)
    _invalid(str(path), "bundle is not a regular file or directory")


def validate_document_bundle(source: str | Path) -> None:
    """Validate a document bundle using the same strict loader as deserialization."""
    load_document_bundle(source)


def load_document_workspace(path: str | Path) -> DocumentWorkspace:
    """Load current valid document text while reporting stale digest as editable state."""
    source = Path(path).expanduser()
    if not source.is_dir():
        _invalid(str(source), "document workspace must be a directory")
    result = _read_directory_bundle(source, workspace=True)
    assert isinstance(result, DocumentWorkspace)
    return result


def refresh_document_workspace(path: str | Path) -> DocumentWorkspace:
    """Refresh the manifest digest and character count for a valid edited document."""
    workspace = load_document_workspace(path)
    manifest_path = workspace.path / "manifest.json"
    try:
        manifest = _parse_manifest(
            _read_directory_file(
                workspace.path,
                "manifest.json",
                str(workspace.path),
                max_bytes=_MAX_MANIFEST_BYTES,
            ),
            str(workspace.path),
        )
        manifest["document"]["sha256"] = workspace.status.actual_sha256
        manifest["document"]["char_count"] = len(workspace.document.ssmd)
        _validate_manifest(manifest, str(workspace.path))
        raw = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(raw) > _MAX_MANIFEST_BYTES:
            raise DocumentBundleValidationError("document manifest exceeds the 2 MiB size limit")
        mode = stat.S_IMODE(manifest_path.stat().st_mode)
        fd, temporary_name = tempfile.mkstemp(prefix=".manifest.json.tmp-", dir=workspace.path)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, manifest_path)
        finally:
            temporary.unlink(missing_ok=True)
    except DocumentBundleError:
        raise
    except (OSError, TypeError, ValueError, UnicodeEncodeError) as exc:
        raise DocumentBundleError(
            f"could not refresh workspace manifest {manifest_path}: {exc}"
        ) from exc
    validate_document_bundle(workspace.path)
    return load_document_workspace(workspace.path)


def read_current_document_bytes(source: str | Path) -> bytes:
    """Read current document bytes from a workspace, bundle, or standalone SSMD file."""
    path = Path(source).expanduser()
    if path.is_dir():
        workspace = load_document_workspace(path)
        return workspace.document.ssmd.encode("utf-8")
    if not path.is_file():
        _invalid(str(path), "source is not a regular file or workspace directory")
    if path.name.lower().endswith(".ssmd-bundle.zip"):
        return load_document_bundle(path).ssmd.encode("utf-8")
    try:
        if path.stat().st_size > _MAX_DOCUMENT_BYTES:
            _invalid(str(path), "SSMD document exceeds the size limit")
        return path.read_bytes()
    except OSError as exc:
        _invalid(str(path), f"could not read SSMD document: {exc}")

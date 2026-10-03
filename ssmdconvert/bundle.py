from __future__ import annotations

import errno
import hashlib
import json
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

from .errors import BookBundleError, BookBundleValidationError
from .models import Book, BookChapter, BookWorkspace, SourceInfo, WorkspaceChapterStatus
from .render import validate_ssmd_document

_FORMAT = "ssmdconvert.book"
_SCHEMA_VERSION = 1
_SSMD_VERSION = "0.9"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:")
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)

_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_CHAPTER_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_CHAPTER_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 10_000


def _invalid(display: str, message: str) -> NoReturn:
    raise BookBundleValidationError(f"{display}: {message}")


def _is_integer(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _validate_relative_path(
    value: Any,
    display: str,
    *,
    allow_directory: bool = False,
) -> str:
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


def _validate_chapter_path(value: Any, display: str) -> str:
    path = _validate_relative_path(value, display)
    if not path.startswith("chapters/") or len(PurePosixPath(path).parts) < 2:
        _invalid(display, f"chapter path must be below chapters/: {path!r}")
    return path


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


def _validate_manifest(value: Any, display: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _invalid(display, "manifest root must be a JSON object")
    if value.get("format") != _FORMAT:
        _invalid(display, f"unsupported bundle format: {value.get('format')!r}")
    if not _is_integer(value.get("schema_version")) or value["schema_version"] != _SCHEMA_VERSION:
        _invalid(display, f"unsupported schema version: {value.get('schema_version')!r}")
    if value.get("ssmd_version") != _SSMD_VERSION:
        _invalid(display, f"unsupported SSMD version: {value.get('ssmd_version')!r}")
    if not isinstance(value.get("metadata"), dict):
        _invalid(display, "manifest metadata must be a JSON object")

    source = value.get("source")
    if not isinstance(source, dict):
        _invalid(display, "manifest source must be a JSON object")
    if not isinstance(source.get("format"), str) or not source["format"]:
        _invalid(display, "source format must be a non-empty string")
    if source.get("media_type") is not None and not isinstance(source["media_type"], str):
        _invalid(display, "source media_type must be a string or null")
    _validate_source_name(source.get("name"), display)
    if not _is_sha256(source.get("sha256")):
        _invalid(display, "source sha256 must be a lowercase SHA256 digest")
    chapter_count = source.get("chapter_count")
    if not _is_integer(chapter_count) or chapter_count < 0:
        _invalid(display, "source chapter_count must be a non-negative integer")

    chapters = value.get("chapters")
    if not isinstance(chapters, list):
        _invalid(display, "manifest chapters must be a JSON array")

    ids: set[str] = set()
    paths: set[str] = set()
    source_numbers: set[int] = set()
    for index, chapter in enumerate(chapters, start=1):
        label = f"chapter entry {index}"
        if not isinstance(chapter, dict):
            _invalid(display, f"{label} must be a JSON object")
        chapter_id = chapter.get("id")
        if not isinstance(chapter_id, str) or not chapter_id:
            _invalid(display, f"{label} id must be a non-empty string")
        if chapter_id in ids:
            _invalid(display, f"duplicate chapter id: {chapter_id!r}")
        ids.add(chapter_id)

        source_number = chapter.get("source_number")
        if not _is_integer(source_number) or source_number < 1:
            _invalid(display, f"{label} source_number must be a positive integer")
        if source_number > chapter_count:
            _invalid(display, f"{label} source_number exceeds source chapter_count")
        if source_number in source_numbers:
            _invalid(display, f"duplicate source_number: {source_number}")
        source_numbers.add(source_number)

        path = _validate_chapter_path(chapter.get("path"), display)
        if path in paths:
            _invalid(display, f"duplicate chapter path: {path!r}")
        paths.add(path)
        if not isinstance(chapter.get("title"), str):
            _invalid(display, f"{label} title must be a string")
        if not _is_integer(chapter.get("level")) or chapter["level"] < 1:
            _invalid(display, f"{label} level must be a positive integer")
        char_count = chapter.get("char_count")
        if char_count is not None and (not _is_integer(char_count) or char_count < 0):
            _invalid(display, f"{label} char_count must be a non-negative integer or null")
        if not _is_sha256(chapter.get("sha256")):
            _invalid(display, f"{label} sha256 must be a lowercase SHA256 digest")
        diagnostics = chapter.get("diagnostics")
        if not isinstance(diagnostics, list) or any(
            not isinstance(item, dict) or any(not isinstance(key, str) for key in item)
            for item in diagnostics
        ):
            _invalid(display, f"{label} diagnostics must be an array of JSON objects")
        for key in ("source_id", "source_parent_id", "href", "parent_id"):
            if key in chapter and chapter[key] is not None and not isinstance(chapter[key], str):
                _invalid(display, f"{label} {key} must be a string or null")

    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value}")


def _parse_manifest(raw: bytes, display: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _invalid(display, f"manifest is not valid UTF-8 JSON: {exc}")
    return _validate_manifest(value, display)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_for_book(book: Book) -> tuple[bytes, list[tuple[str, bytes]]]:
    if not isinstance(book, Book):
        raise BookBundleError("write_book_bundle requires a Book")

    source_name = book.source.name
    if source_name is None and book.source.path is not None:
        source_name = book.source.path.name
    if source_name is None:
        raise BookBundleError("book source name is missing")
    source_sha256 = book.source_sha256
    if not _is_sha256(source_sha256):
        raise BookBundleError("book source SHA-256 is missing or invalid")
    source_chapter_count = (
        book.source_chapter_count if book.source_chapter_count is not None else len(book.chapters)
    )

    chapter_data: list[tuple[str, bytes]] = []
    chapter_entries: list[dict[str, Any]] = []
    for chapter in book.chapters:
        if not isinstance(chapter, BookChapter):
            raise BookBundleValidationError("book chapters must be BookChapter values")
        if not isinstance(chapter.ssmd, str):
            raise BookBundleValidationError(f"chapter {chapter.id!r} SSMD must be text")
        try:
            validate_ssmd_document(chapter.ssmd)
            data = chapter.ssmd.encode("utf-8")
        except Exception as exc:
            raise BookBundleValidationError(
                f"chapter {chapter.id!r} does not contain valid UTF-8 SSMD: {exc}"
            ) from exc

        diagnostics = []
        for item in chapter.diagnostics:
            if not isinstance(item, Mapping):
                raise BookBundleValidationError(
                    f"chapter {chapter.id!r} diagnostics must be mappings"
                )
            diagnostics.append(dict(item))
        path = f"chapters/{chapter.id}.ssmd.md"
        chapter_data.append((path, data))
        chapter_entries.append(
            {
                "id": chapter.id,
                "source_number": chapter.source_number,
                "path": path,
                "title": chapter.title,
                "source_id": chapter.source_id,
                "source_parent_id": chapter.source_parent_id,
                "href": chapter.href,
                "parent_id": chapter.parent_id,
                "level": chapter.level,
                "char_count": chapter.char_count,
                "sha256": _sha256(data),
                "diagnostics": diagnostics,
            }
        )

    manifest: dict[str, Any] = {
        "format": _FORMAT,
        "schema_version": _SCHEMA_VERSION,
        "ssmd_version": _SSMD_VERSION,
        "metadata": dict(book.metadata),
        "source": {
            "format": book.source.format,
            "media_type": book.source.media_type,
            "name": source_name,
            "sha256": source_sha256,
            "chapter_count": source_chapter_count,
        },
        "chapters": chapter_entries,
    }
    _validate_manifest(manifest, "book")
    try:
        manifest_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise BookBundleValidationError(f"book metadata is not JSON serializable: {exc}") from exc
    return manifest_bytes, chapter_data


def _is_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _read_directory_file(
    root: Path,
    name: str,
    display: str,
    *,
    max_bytes: int,
) -> bytes:
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
        size = resolved.stat().st_size
        if size > max_bytes:
            _invalid(display, f"bundle file {name!r} exceeds the size limit ({max_bytes} bytes)")
        data = resolved.read_bytes()
    except OSError as exc:
        _invalid(display, f"could not read bundle file {name!r}: {exc}")
    if len(data) > max_bytes:
        _invalid(display, f"bundle file {name!r} exceeds the size limit ({max_bytes} bytes)")
    return data


def _read_directory_bundle(source: Path) -> Book:
    display = str(source)
    try:
        root = source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _invalid(display, f"could not resolve bundle directory: {exc}")
    manifest_bytes = _read_directory_file(
        root,
        "manifest.json",
        display,
        max_bytes=_MAX_MANIFEST_BYTES,
    )
    manifest = _parse_manifest(manifest_bytes, display)
    total_chapter_bytes = 0

    def read_chapter(name: str) -> bytes:
        nonlocal total_chapter_bytes
        data = _read_directory_file(
            root,
            name,
            display,
            max_bytes=_MAX_CHAPTER_BYTES,
        )
        total_chapter_bytes += len(data)
        if total_chapter_bytes > _MAX_TOTAL_CHAPTER_BYTES:
            _invalid(display, "referenced chapter files exceed the total size limit")
        return data

    return _book_from_manifest(manifest, read_chapter, display)


def _validate_zip_member(info: zipfile.ZipInfo, display: str) -> None:
    name = info.filename
    _validate_relative_path(name, display, allow_directory=info.is_dir())
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        _invalid(display, f"ZIP symlink entries are not allowed: {name!r}")


def _read_zip_bundle(source: Path) -> Book:
    display = str(source)
    try:
        archive = zipfile.ZipFile(source, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        _invalid(display, f"not a readable book ZIP: {exc}")

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
        total_chapter_bytes = 0

        def read_member(name: str) -> bytes:
            nonlocal total_chapter_bytes
            info = members.get(name)
            if info is None or info.is_dir():
                _invalid(display, f"ZIP is missing chapter file {name!r}")
            if info.file_size > _MAX_CHAPTER_BYTES:
                _invalid(display, f"ZIP chapter {name!r} exceeds the size limit")
            if total_chapter_bytes + info.file_size > _MAX_TOTAL_CHAPTER_BYTES:
                _invalid(display, "referenced ZIP chapters exceed the total size limit")
            try:
                data = archive.read(info)
            except (OSError, EOFError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
                _invalid(display, f"could not read ZIP chapter {name!r}: {exc}")
            if len(data) > _MAX_CHAPTER_BYTES:
                _invalid(display, f"ZIP chapter {name!r} exceeds the size limit")
            total_chapter_bytes += len(data)
            if total_chapter_bytes > _MAX_TOTAL_CHAPTER_BYTES:
                _invalid(display, "referenced ZIP chapters exceed the total size limit")
            return data

        return _book_from_manifest(manifest, read_member, display)


def _book_from_manifest(
    manifest: dict[str, Any],
    read_bytes: Callable[[str], bytes],
    display: str,
    *,
    verify_sha256: bool = True,
    workspace_chapters: list[WorkspaceChapterStatus] | None = None,
) -> Book:
    source = manifest["source"]
    chapters: list[BookChapter] = []
    for entry in manifest["chapters"]:
        path = entry["path"]
        raw = read_bytes(path)
        actual_sha256 = _sha256(raw)
        dirty = actual_sha256 != entry["sha256"]
        if verify_sha256 and dirty:
            _invalid(display, f"SHA256 mismatch for chapter {path!r}")
        if workspace_chapters is not None:
            workspace_chapters.append(
                WorkspaceChapterStatus(
                    id=entry["id"],
                    path=path,
                    expected_sha256=entry["sha256"],
                    actual_sha256=actual_sha256,
                    dirty=dirty,
                )
            )
        try:
            ssmd = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            _invalid(display, f"chapter {path!r} is not UTF-8: {exc}")
        try:
            validate_ssmd_document(ssmd)
        except Exception as exc:
            _invalid(display, f"chapter {path!r} is not valid SSMD 0.9: {exc}")
        chapters.append(
            BookChapter(
                id=entry["id"],
                source_number=entry["source_number"],
                title=entry["title"],
                ssmd=ssmd,
                source_id=entry.get("source_id"),
                href=entry.get("href"),
                source_parent_id=entry.get("source_parent_id"),
                parent_id=entry.get("parent_id"),
                level=entry["level"],
                char_count=entry.get("char_count"),
                diagnostics=tuple(dict(item) for item in entry["diagnostics"]),
            )
        )

    return Book(
        source=SourceInfo(
            format=source["format"],
            media_type=source.get("media_type"),
            name=source["name"],
        ),
        metadata=dict(manifest["metadata"]),
        chapters=tuple(chapters),
        source_sha256=source["sha256"],
        source_chapter_count=source["chapter_count"],
    )


def _write_zip(target: Path, manifest: bytes, chapters: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(
        target,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, data in [("manifest.json", manifest), *chapters]:
            info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _write_directory(
    target: Path,
    manifest: bytes,
    chapters: list[tuple[str, bytes]],
) -> None:
    root = target.resolve()
    for name, data in [("manifest.json", manifest), *chapters]:
        normalized = _validate_relative_path(name, str(target))
        destination = root.joinpath(*PurePosixPath(normalized).parts)
        if not _is_below(destination.resolve(strict=False), root):
            raise BookBundleError(f"bundle output path escapes the directory: {name!r}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not _is_below(destination.resolve(strict=False), root):
            raise BookBundleError(f"bundle output path escapes the directory: {name!r}")
        destination.write_bytes(data)


def _destination_exists(target: Path) -> bool:
    return target.exists() or target.is_symlink()


def _publish_path_no_replace(source: Path, target: Path) -> None:
    """Publish a completed file without overwriting an existing destination."""
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


def _write_zip_atomic(
    target: Path,
    manifest: bytes,
    chapters: list[tuple[str, bytes]],
    *,
    overwrite: bool,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or (target.exists() and target.is_dir()):
        raise BookBundleError(f"ZIP bundle output must be a regular file: {target}")
    if _destination_exists(target) and not overwrite:
        raise BookBundleError(f"bundle output already exists: {target}")

    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.tmp-", dir=target.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        _write_zip(temporary, manifest, chapters)
        os.chmod(temporary, 0o644)
        _read_zip_bundle(temporary)
        if overwrite:
            os.replace(temporary, target)
        else:
            try:
                _publish_path_no_replace(temporary, target)
            except FileExistsError as exc:
                raise BookBundleError(f"bundle output already exists: {target}") from exc
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
    chapters: list[tuple[str, bytes]],
    *,
    overwrite: bool,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise BookBundleError(f"directory bundle output must be a directory: {target}")
    if _destination_exists(target) and not overwrite:
        raise BookBundleError(f"bundle output already exists: {target}")

    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent))
    backup: Path | None = None
    try:
        _write_directory(temporary, manifest, chapters)
        _read_directory_bundle(temporary)
        if _destination_exists(target):
            if not overwrite:
                raise BookBundleError(f"bundle output already exists: {target}")
            if target.is_symlink() or not target.is_dir():
                raise BookBundleError(f"directory bundle output must be a directory: {target}")
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


def write_book_bundle(
    book: Book,
    output: str | Path,
    *,
    format: Literal["directory", "zip"],
    overwrite: bool = False,
) -> Path:
    """Write a complete directory or ZIP bundle atomically beside its destination."""
    if format not in ("directory", "zip"):
        raise BookBundleError("bundle format must be 'directory' or 'zip'")
    manifest, chapters = _manifest_for_book(book)
    raw_target = Path(os.path.abspath(Path(output).expanduser()))
    target = raw_target.parent.resolve() / raw_target.name
    try:
        if format == "zip":
            _write_zip_atomic(target, manifest, chapters, overwrite=overwrite)
        else:
            _write_directory_atomic(target, manifest, chapters, overwrite=overwrite)
    except BookBundleError:
        raise
    except OSError as exc:
        raise BookBundleError(f"could not write book bundle {target}: {exc}") from exc
    return target


def load_book_bundle(source: str | Path) -> Book:
    """Load and strictly validate a directory or ZIP book bundle."""
    path = Path(source).expanduser()
    if not path.exists():
        _invalid(str(path), "bundle does not exist")
    if path.is_dir():
        return _read_directory_bundle(path)
    if path.is_file():
        return _read_zip_bundle(path)
    _invalid(str(path), "bundle is not a regular file or directory")


def validate_book_bundle(source: str | Path) -> None:
    """Validate a book bundle using the same strict loader as deserialization."""
    load_book_bundle(source)


def load_book_workspace(path: str | Path) -> BookWorkspace:
    """Load current chapter content from an editable directory book workspace.

    Unlike :func:`load_book_bundle`, stale chapter digests are reported as
    workspace state instead of making the directory unreadable. No files are
    modified by this operation.
    """
    source = Path(path).expanduser()
    display = str(source)
    if not source.is_dir():
        _invalid(display, "book workspace must be a directory")
    try:
        root = source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _invalid(display, f"could not resolve workspace directory: {exc}")

    manifest_bytes = _read_directory_file(
        root,
        "manifest.json",
        display,
        max_bytes=_MAX_MANIFEST_BYTES,
    )
    manifest = _parse_manifest(manifest_bytes, display)
    total_chapter_bytes = 0

    def read_chapter(name: str) -> bytes:
        nonlocal total_chapter_bytes
        data = _read_directory_file(
            root,
            name,
            display,
            max_bytes=_MAX_CHAPTER_BYTES,
        )
        total_chapter_bytes += len(data)
        if total_chapter_bytes > _MAX_TOTAL_CHAPTER_BYTES:
            _invalid(display, "referenced chapter files exceed the total size limit")
        return data

    statuses: list[WorkspaceChapterStatus] = []
    book = _book_from_manifest(
        manifest,
        read_chapter,
        display,
        verify_sha256=False,
        workspace_chapters=statuses,
    )
    chapters = tuple(statuses)
    return BookWorkspace(
        path=root,
        book=book,
        chapters=chapters,
        dirty=any(chapter.dirty for chapter in chapters),
    )


def refresh_book_workspace(path: str | Path) -> BookWorkspace:
    """Refresh chapter digests and character counts in a workspace manifest."""
    workspace = load_book_workspace(path)
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
        chapters_by_id = {chapter.id: chapter for chapter in workspace.book.chapters}
        status_by_id = {chapter.id: chapter for chapter in workspace.chapters}
        for entry in manifest["chapters"]:
            chapter = chapters_by_id[entry["id"]]
            status = status_by_id[entry["id"]]
            entry["sha256"] = status.actual_sha256
            entry["char_count"] = len(chapter.ssmd)
        _validate_manifest(manifest, str(workspace.path))
        manifest_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        file_mode = stat.S_IMODE(manifest_path.stat().st_mode)
        fd, temporary_name = tempfile.mkstemp(
            prefix=".manifest.json.tmp-",
            dir=workspace.path,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(manifest_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, file_mode)
            os.replace(temporary, manifest_path)
        finally:
            temporary.unlink(missing_ok=True)
    except BookBundleError:
        raise
    except (OSError, TypeError, ValueError, UnicodeEncodeError) as exc:
        raise BookBundleError(
            f"could not refresh workspace manifest {manifest_path}: {exc}"
        ) from exc

    validate_book_bundle(workspace.path)
    return load_book_workspace(workspace.path)

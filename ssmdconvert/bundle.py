from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
import zlib
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import BookBundleError, BookBundleValidationError
from .models import Book, BookChapter, SourceInfo
from .render import validate_ssmd_document

_FORMAT = "ssmdconvert.book"
_SCHEMA_VERSION = 1
_SSMD_VERSION = "0.9"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:")
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _invalid(display: str, message: str) -> None:
    raise BookBundleValidationError(f"{display}: {message}")


def _is_integer(value: Any) -> bool:
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
    _validate_source_name(source.get("name"), display)
    if not _is_sha256(source.get("sha256")):
        _invalid(display, "source sha256 must be a lowercase SHA256 digest")
    if not _is_integer(source.get("chapter_count")) or source["chapter_count"] < 0:
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
        if source_number > source["chapter_count"]:
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
        for key in ("source_id", "href", "parent_id"):
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_for_book(book: Book) -> tuple[bytes, list[tuple[str, bytes]]]:
    if not isinstance(book, Book):
        raise BookBundleError("write_book_bundle requires a Book")

    source_name = book.source_name or book.source.path.name
    source_sha256 = book.source_sha256
    if source_sha256 is None:
        if not book.source.path.is_file():
            raise BookBundleError(f"source EPUB is unavailable for hashing: {book.source.path}")
        try:
            source_sha256 = _sha256_file(book.source.path)
        except OSError as exc:
            raise BookBundleError(f"could not hash source EPUB: {exc}") from exc
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
        path = (
            chapter.bundle_path
            if chapter.bundle_path is not None
            else f"chapters/chapter-{chapter.source_number:04d}.ssmd.md"
        )
        chapter_data.append((path, data))
        chapter_entries.append(
            {
                "id": chapter.id,
                "source_number": chapter.source_number,
                "path": path,
                "title": chapter.title,
                "source_id": chapter.source_id,
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


def _read_directory_file(root: Path, name: str, display: str) -> bytes:
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
        return resolved.read_bytes()
    except OSError as exc:
        _invalid(display, f"could not read bundle file {name!r}: {exc}")


def _read_directory_bundle(source: Path) -> Book:
    display = str(source)
    try:
        root = source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _invalid(display, f"could not resolve bundle directory: {exc}")
    manifest_bytes = _read_directory_file(root, "manifest.json", display)
    manifest = _parse_manifest(manifest_bytes, display)
    return _book_from_manifest(
        manifest,
        lambda name: _read_directory_file(root, name, display),
        display,
    )


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
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            _invalid(display, "ZIP contains duplicate member names")
        for info in infos:
            _validate_zip_member(info, display)
        members = {info.filename: info for info in infos}
        manifest_info = members.get("manifest.json")
        if manifest_info is None or manifest_info.is_dir():
            _invalid(display, "ZIP is missing manifest.json")
        try:
            manifest_bytes = archive.read(manifest_info)
        except (OSError, EOFError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
            _invalid(display, f"could not read ZIP manifest.json: {exc}")
        manifest = _parse_manifest(manifest_bytes, display)

        def read_member(name: str) -> bytes:
            info = members.get(name)
            if info is None or info.is_dir():
                _invalid(display, f"ZIP is missing chapter file {name!r}")
            try:
                return archive.read(info)
            except (OSError, EOFError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
                _invalid(display, f"could not read ZIP chapter {name!r}: {exc}")

        return _book_from_manifest(manifest, read_member, display)


def _book_from_manifest(
    manifest: dict[str, Any],
    read_bytes: Callable[[str], bytes],
    display: str,
) -> Book:
    source = manifest["source"]
    chapters: list[BookChapter] = []
    for entry in manifest["chapters"]:
        path = entry["path"]
        raw = read_bytes(path)
        if _sha256(raw) != entry["sha256"]:
            _invalid(display, f"SHA256 mismatch for chapter {path!r}")
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
                parent_id=entry.get("parent_id"),
                level=entry["level"],
                char_count=entry.get("char_count"),
                diagnostics=tuple(dict(item) for item in entry["diagnostics"]),
                bundle_path=path,
            )
        )

    return Book(
        source=SourceInfo(Path(source["name"]), source["format"]),
        metadata=dict(manifest["metadata"]),
        chapters=tuple(chapters),
        source_chapter_count=source["chapter_count"],
        source_name=source["name"],
        source_sha256=source["sha256"],
    )


def _write_zip(target: Path, manifest: bytes, chapters: list[tuple[str, bytes]]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
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
    if target.exists() and not target.is_dir():
        raise BookBundleError(f"directory bundle output is not a directory: {target}")
    target.mkdir(parents=True, exist_ok=True)
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


def write_book_bundle(book: Book, output: str | Path) -> Path:
    """Write a Book as an editable directory or portable ZIP bundle."""
    manifest, chapters = _manifest_for_book(book)
    target = Path(output).expanduser().resolve()
    try:
        if target.suffix.lower() == ".zip":
            if target.exists() and target.is_dir():
                raise BookBundleError(f"ZIP bundle output is a directory: {target}")
            _write_zip(target, manifest, chapters)
        else:
            _write_directory(target, manifest, chapters)
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

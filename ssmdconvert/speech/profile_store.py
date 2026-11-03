"""Safe persistence and automatic resolution for bundle-local speech profiles."""

from __future__ import annotations

import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..bundle_identity import (
    probe_bundle_kind,
    require_bundle_archive_path,
    require_bundle_workspace_path,
)
from .profile import (
    SpeechReplacementProfile,
    empty_speech_profile,
    parse_speech_profile,
    render_speech_profile,
    speech_profile_fingerprint,
    write_speech_profile,
)

BUNDLE_SPEECH_PROFILE_PATH = "speech.toml"
MAX_SPEECH_PROFILE_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ResolvedSpeechProfile:
    """Selected semantic profile and its source for one operation."""

    profile: SpeechReplacementProfile
    source: Literal["explicit", "bundle", "destination", "default-empty"]
    path: Path | None
    raw: bytes
    replaces_destination: bool = False


def _parse_profile_bytes(raw: bytes, display: Path) -> SpeechReplacementProfile:
    if len(raw) > MAX_SPEECH_PROFILE_BYTES:
        raise ValueError(
            f"speech profile {display} exceeds the {MAX_SPEECH_PROFILE_BYTES}-byte size limit"
        )
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"speech profile {display} is not strict UTF-8: {exc}") from exc
    try:
        return parse_speech_profile(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid speech profile {display}: {exc}") from exc


def _read_external_profile(path: Path) -> tuple[SpeechReplacementProfile, bytes]:
    expanded = path.expanduser()
    try:
        if expanded.stat().st_size > MAX_SPEECH_PROFILE_BYTES:
            raise ValueError(
                f"speech profile {expanded} exceeds the {MAX_SPEECH_PROFILE_BYTES}-byte size limit"
            )
        raw = expanded.read_bytes()
    except OSError as exc:
        raise ValueError(f"could not read speech profile {expanded}: {exc}") from exc
    if len(raw) > MAX_SPEECH_PROFILE_BYTES:
        raise ValueError(
            f"speech profile {expanded} exceeds the {MAX_SPEECH_PROFILE_BYTES}-byte size limit"
        )
    return _parse_profile_bytes(raw, expanded), raw


def read_workspace_speech_profile(
    workspace: str | Path,
    *,
    missing: Literal["empty", "none"] = "empty",
) -> SpeechReplacementProfile | None:
    """Read and validate the canonical sidecar from an editable bundle workspace."""
    root = require_bundle_workspace_path(workspace)
    try:
        probe_bundle_kind(root)
    except Exception as exc:
        raise ValueError(f"not a recognizable bundle workspace {root}: {exc}") from exc
    target = root / BUNDLE_SPEECH_PROFILE_PATH
    if target.is_symlink():
        raise ValueError(f"bundle speech profile cannot be a symlink: {target}")
    try:
        resolved = target.resolve(strict=True)
    except FileNotFoundError as exc:
        if target.is_symlink():
            raise ValueError(f"bundle speech profile is a dangling symlink: {target}") from exc
        return empty_speech_profile() if missing == "empty" else None
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"could not resolve bundle speech profile {target}: {exc}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"bundle speech profile resolves outside the bundle directory: {target}"
        ) from exc
    if not resolved.is_file():
        raise ValueError(f"bundle speech profile is not a regular file: {target}")
    try:
        if resolved.stat().st_size > MAX_SPEECH_PROFILE_BYTES:
            raise ValueError(
                f"speech profile {target} exceeds the {MAX_SPEECH_PROFILE_BYTES}-byte size limit"
            )
        raw = resolved.read_bytes()
    except OSError as exc:
        raise ValueError(f"could not read bundle speech profile {target}: {exc}") from exc
    return _parse_profile_bytes(raw, target)


def read_archive_speech_profile(
    archive_path: str | Path,
    *,
    missing: Literal["empty", "none"] = "empty",
) -> SpeechReplacementProfile | None:
    """Read only the canonical sidecar from a packed bundle without extracting it."""
    archive_path = require_bundle_archive_path(archive_path)
    try:
        probe_bundle_kind(archive_path)
    except Exception as exc:
        raise ValueError(f"not a recognizable packed bundle {archive_path}: {exc}") from exc
    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"not a readable packed bundle {archive_path}: {exc}") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > 10_000:
            raise ValueError(f"packed bundle {archive_path} contains too many archive members")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError(f"packed bundle {archive_path} contains duplicate member names")
        info = next((item for item in infos if item.filename == BUNDLE_SPEECH_PROFILE_PATH), None)
        if info is None:
            return empty_speech_profile() if missing == "empty" else None
        if info.is_dir():
            raise ValueError(f"packed bundle speech profile is not a regular file: {archive_path}")
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise ValueError(f"packed bundle speech profile cannot be a symlink: {archive_path}")
        if info.file_size > MAX_SPEECH_PROFILE_BYTES:
            raise ValueError(
                f"speech profile in {archive_path} exceeds the "
                f"{MAX_SPEECH_PROFILE_BYTES}-byte size limit"
            )
        try:
            with archive.open(info, "r") as stream:
                raw = stream.read(MAX_SPEECH_PROFILE_BYTES + 1)
        except (OSError, EOFError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
            raise ValueError(f"could not read speech profile from {archive_path}: {exc}") from exc
        return _parse_profile_bytes(raw, archive_path)


def read_bundle_speech_profile(
    bundle: str | Path,
    *,
    missing: Literal["empty", "none"] = "empty",
) -> SpeechReplacementProfile | None:
    """Read a bundle-local speech profile from a workspace or packed archive."""
    path = Path(bundle).expanduser()
    if path.name.endswith(".ssmd-bundle.zip"):
        return read_archive_speech_profile(path, missing=missing)
    return read_workspace_speech_profile(path, missing=missing)


def write_bundle_speech_profile(
    workspace: str | Path,
    profile: SpeechReplacementProfile,
) -> Path:
    """Atomically write the canonical profile sidecar into a workspace."""
    root = require_bundle_workspace_path(workspace)
    try:
        probe_bundle_kind(root)
    except Exception as exc:
        raise ValueError(f"not a recognizable bundle workspace {root}: {exc}") from exc
    target = root / BUNDLE_SPEECH_PROFILE_PATH
    if target.is_symlink():
        raise ValueError(f"refusing to replace symlink bundle speech profile: {target}")
    try:
        return write_speech_profile(target, profile, overwrite=True)
    except OSError as exc:
        raise ValueError(f"could not write bundle speech profile {target}: {exc}") from exc


def _recognized_destination(destination: Path) -> bool:
    if not destination.name.endswith(".ssmd-bundle") or not destination.is_dir():
        return False
    try:
        probe_bundle_kind(destination)
    except Exception:
        return False
    return True


def resolve_operation_speech_profile(
    source: str | Path,
    explicit: str | Path | None = None,
) -> ResolvedSpeechProfile:
    """Select an explicit profile or the profile owned by a bundle input."""
    if explicit is not None:
        path = Path(explicit).expanduser()
        profile, raw = _read_external_profile(path)
        return ResolvedSpeechProfile(profile, "explicit", path, raw)
    source_path = Path(source).expanduser()
    if source_path.name.endswith((".ssmd-bundle", ".ssmd-bundle.zip")):
        bundle_profile = read_bundle_speech_profile(source_path, missing="empty")
        assert bundle_profile is not None
        profile_path = (
            source_path / BUNDLE_SPEECH_PROFILE_PATH if source_path.is_dir() else source_path
        )
        return ResolvedSpeechProfile(
            bundle_profile,
            "bundle",
            profile_path,
            render_speech_profile(bundle_profile).encode("utf-8"),
        )
    profile = empty_speech_profile()
    return ResolvedSpeechProfile(
        profile,
        "default-empty",
        None,
        render_speech_profile(profile).encode("utf-8"),
    )


def resolve_conversion_speech_profile(
    destination: str | Path,
    explicit: str | Path | SpeechReplacementProfile | None = None,
) -> ResolvedSpeechProfile:
    """Resolve an explicit profile before a recognizable destination profile."""
    target = Path(destination).expanduser()
    explicit_result: ResolvedSpeechProfile | None = None
    if isinstance(explicit, SpeechReplacementProfile):
        explicit_result = ResolvedSpeechProfile(
            explicit,
            "explicit",
            None,
            render_speech_profile(explicit).encode("utf-8"),
        )
    elif explicit is not None:
        path = Path(explicit).expanduser()
        profile, raw = _read_external_profile(path)
        explicit_result = ResolvedSpeechProfile(profile, "explicit", path, raw)
    if _recognized_destination(target):
        destination_profile = read_workspace_speech_profile(target, missing="empty")
        assert destination_profile is not None
        if explicit_result is not None:
            if speech_profile_fingerprint(destination_profile) != speech_profile_fingerprint(
                explicit_result.profile
            ):
                # The caller can surface this source transition without losing the override.
                return ResolvedSpeechProfile(
                    explicit_result.profile,
                    "explicit",
                    explicit_result.path,
                    explicit_result.raw,
                    replaces_destination=True,
                )
            return explicit_result
        return ResolvedSpeechProfile(
            destination_profile,
            "destination",
            target / BUNDLE_SPEECH_PROFILE_PATH,
            render_speech_profile(destination_profile).encode("utf-8"),
        )
    if explicit_result is not None:
        return explicit_result
    profile = empty_speech_profile()
    return ResolvedSpeechProfile(
        profile,
        "default-empty",
        None,
        render_speech_profile(profile).encode("utf-8"),
    )

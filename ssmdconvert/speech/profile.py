"""Versioned TOML speech-replacement profiles."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[no-redef, import-not-found]


PROFILE_SCHEMA = "ssmdconvert-speech-profile"
PROFILE_VERSION = 1
_ALLOWED_KEYS = {"schema", "version", "derive_possessives", "replacements"}


@dataclass(frozen=True, slots=True)
class SpeechReplacementProfile:
    """Immutable, validated pronunciation replacements from a TOML profile."""

    schema: str
    version: int
    replacements: Mapping[str, str]
    derive_possessives: bool = True

    def __post_init__(self) -> None:
        if self.schema != PROFILE_SCHEMA:
            raise ValueError(f"schema must be {PROFILE_SCHEMA!r}")
        if type(self.version) is not int or self.version != PROFILE_VERSION:
            raise ValueError(f"version must be {PROFILE_VERSION}")
        if not isinstance(self.derive_possessives, bool):
            raise ValueError("derive_possessives must be a boolean")
        if not isinstance(self.replacements, Mapping):
            raise ValueError("[replacements] must be a table")
        normalized: dict[str, str] = {}
        for surface, spoken in self.replacements.items():
            if not isinstance(surface, str) or not surface or surface != surface.strip():
                raise ValueError(
                    "replacement keys must be non-empty strings without edge whitespace"
                )
            if not isinstance(spoken, str) or not spoken.strip():
                raise ValueError("replacement values must be non-empty, non-whitespace strings")
            normalized[surface] = spoken
        object.__setattr__(self, "replacements", MappingProxyType(normalized))


def parse_speech_profile(text: str) -> SpeechReplacementProfile:
    """Parse and strictly validate a version-1 speech profile TOML document."""
    if not isinstance(text, str):
        raise TypeError("speech profile text must be a string")
    try:
        data: Any = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, TypeError) as exc:
        raise ValueError(f"invalid speech profile TOML: {exc}") from exc
    if not isinstance(data, dict):  # TOML documents always decode to a table.
        raise ValueError("speech profile must contain a TOML table")
    unknown = sorted(set(data) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"unknown speech profile top-level key(s): {', '.join(unknown)}")
    schema = data.get("schema")
    if schema != PROFILE_SCHEMA:
        raise ValueError(f"schema must be {PROFILE_SCHEMA!r}")
    version = data.get("version")
    if type(version) is not int or version != PROFILE_VERSION:
        raise ValueError(f"version must be {PROFILE_VERSION}")
    derive_possessives = data.get("derive_possessives", True)
    if not isinstance(derive_possessives, bool):
        raise ValueError("derive_possessives must be a boolean")
    replacements = data.get("replacements")
    if not isinstance(replacements, dict):
        raise ValueError("[replacements] must be a table")
    return SpeechReplacementProfile(
        schema=schema,
        version=version,
        replacements=replacements,
        derive_possessives=derive_possessives,
    )


def load_speech_profile(path: str | Path) -> SpeechReplacementProfile:
    """Load a speech profile from an explicitly supplied UTF-8 TOML path."""
    return parse_speech_profile(Path(path).read_text(encoding="utf-8"))


def effective_replacements(profile: SpeechReplacementProfile) -> Mapping[str, str]:
    """Return explicit plus narrowly derived ASCII/typographic possessive forms."""
    if not isinstance(profile, SpeechReplacementProfile):
        raise TypeError("profile must be a SpeechReplacementProfile")
    result = dict(profile.replacements)
    if profile.derive_possessives:
        explicit = set(result)
        for surface, spoken in profile.replacements.items():
            if surface.endswith(("'s", "’s")):
                continue
            for apostrophe in ("'", "’"):
                derived_surface = f"{surface}{apostrophe}s"
                if derived_surface not in explicit:
                    result[derived_surface] = f"{spoken}{apostrophe}s"
    return MappingProxyType(result)


def speech_profile_fingerprint(profile: SpeechReplacementProfile) -> str:
    """Hash canonical profile semantics, independent of path and TOML key order."""
    if not isinstance(profile, SpeechReplacementProfile):
        raise TypeError("profile must be a SpeechReplacementProfile")
    canonical = json.dumps(
        {
            "schema": profile.schema,
            "version": profile.version,
            "derive_possessives": profile.derive_possessives,
            "replacements": dict(sorted(profile.replacements.items())),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def empty_speech_profile() -> SpeechReplacementProfile:
    """Return the canonical empty version-1 replacement profile."""
    return SpeechReplacementProfile(
        schema=PROFILE_SCHEMA,
        version=PROFILE_VERSION,
        replacements={},
        derive_possessives=True,
    )


def _toml_string(value: str) -> str:
    """Quote one TOML basic string, including control characters safely."""
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("speech profile strings must be valid UTF-8") from exc
    escaped: list[str] = ['"']
    for char in value:
        codepoint = ord(char)
        if char == "\\":
            escaped.append("\\\\")
        elif char == '"':
            escaped.append('\\"')
        elif char == "\b":
            escaped.append("\\b")
        elif char == "\t":
            escaped.append("\\t")
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\f":
            escaped.append("\\f")
        elif char == "\r":
            escaped.append("\\r")
        elif codepoint < 0x20 or codepoint == 0x7F:
            escaped.append(f"\\u{codepoint:04X}")
        else:
            escaped.append(char)
    escaped.append('"')
    return "".join(escaped)


def render_speech_profile(profile: SpeechReplacementProfile) -> str:
    """Render semantic profile data as deterministic UTF-8-compatible TOML."""
    if not isinstance(profile, SpeechReplacementProfile):
        raise TypeError("profile must be a SpeechReplacementProfile")
    lines = [
        f"schema = {_toml_string(profile.schema)}",
        f"version = {profile.version}",
        f"derive_possessives = {'true' if profile.derive_possessives else 'false'}",
        "",
        "[replacements]",
    ]
    lines.extend(
        f"{_toml_string(surface)} = {_toml_string(profile.replacements[surface])}"
        for surface in sorted(profile.replacements)
    )
    return "\n".join(lines) + "\n"


def write_speech_profile(
    path: str | Path,
    profile: SpeechReplacementProfile,
    *,
    overwrite: bool = False,
) -> Path:
    """Write a canonical profile, atomically replacing only when overwrite is enabled."""
    target = Path(path).expanduser()
    rendered = render_speech_profile(profile).encode("utf-8", errors="strict")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.tmp-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        if overwrite:
            os.replace(temporary, target)
        else:
            link = getattr(os, "link", None)
            if link is not None:
                try:
                    link(temporary, target)
                except FileExistsError:
                    raise FileExistsError(
                        f"speech profile output already exists: {target}"
                    ) from None
                temporary.unlink()
            else:
                try:
                    output_fd = os.open(
                        target,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o644,
                    )
                except FileExistsError:
                    raise FileExistsError(
                        f"speech profile output already exists: {target}"
                    ) from None
                try:
                    os.close(output_fd)
                    os.replace(temporary, target)
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
    finally:
        temporary.unlink(missing_ok=True)
    return target


def with_speech_replacement(
    profile: SpeechReplacementProfile,
    surface: str,
    spoken: str,
) -> SpeechReplacementProfile:
    """Return a copy with one explicit replacement added or updated."""
    if not isinstance(profile, SpeechReplacementProfile):
        raise TypeError("profile must be a SpeechReplacementProfile")
    updated = dict(profile.replacements)
    updated[surface] = spoken
    return SpeechReplacementProfile(
        schema=profile.schema,
        version=profile.version,
        replacements=updated,
        derive_possessives=profile.derive_possessives,
    )


def without_speech_replacement(
    profile: SpeechReplacementProfile,
    surface: str,
) -> SpeechReplacementProfile:
    """Return a copy with one explicit replacement removed."""
    if not isinstance(profile, SpeechReplacementProfile):
        raise TypeError("profile must be a SpeechReplacementProfile")
    if surface not in profile.replacements:
        raise ValueError(f"speech profile has no explicit replacement for {surface!r}")
    updated = dict(profile.replacements)
    del updated[surface]
    return SpeechReplacementProfile(
        schema=profile.schema,
        version=profile.version,
        replacements=updated,
        derive_possessives=profile.derive_possessives,
    )

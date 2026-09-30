#!/usr/bin/env python3
"""Validate release distributions against the version named by RELEASE_TAG."""

from __future__ import annotations

import os
import re
import sys
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

from packaging.utils import canonicalize_name, parse_sdist_filename, parse_wheel_filename

_TAG_PATTERN = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_WHEEL_DEVELOPMENT_PARTS = {
    ".github",
    ".git",
    ".ledger",
    ".coverage",
    ".mypy_cache",
    ".nox",
    ".ruff_cache",
    ".tox",
    ".pytest_cache",
    ".taskledger",
    ".venv",
    "__pycache__",
    "build",
    "docs",
    "dist",
    "tests",
    "tools",
}
_WHEEL_DEVELOPMENT_FILES = {
    ".pre-commit-config.yaml",
    "01_todo.md",
    "MANIFEST.in",
    "RELEASING.md",
    ".gitignore",
    ".codecrate.toml",
    "CHANGELOG.md",
    "Makefile",
    "setup.cfg",
    "tox.ini",
    "pyproject.toml",
}
_SDIST_FORBIDDEN_PARTS = {
    ".coverage",
    ".git",
    ".ledger",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".taskledger",
    ".tox",
    "__pycache__",
    "build",
    "dist",
}


class ArtifactValidationError(Exception):
    """A release distribution does not satisfy the repository release policy."""


def _check_distribution_name(name: str, artifact: Path) -> None:
    if canonicalize_name(name) != "ssmdconvert":
        raise ArtifactValidationError(
            f"{artifact.name} is for distribution {name!r}, expected 'ssmdconvert'."
        )


def _development_members(
    members: list[str],
    forbidden_parts: set[str],
    *,
    reject_egg_info: bool = True,
) -> list[str]:
    rejected = []
    for member in members:
        path = PurePosixPath(member)
        if any(part in forbidden_parts for part in path.parts):
            rejected.append(member)
        elif reject_egg_info and any(part.endswith(".egg-info") for part in path.parts):
            rejected.append(member)
        elif member.endswith(".pyc"):
            rejected.append(member)
    return rejected


def _check_wheel(wheel_path: Path, expected_version: str) -> None:
    try:
        distribution, version, _build, _tags = parse_wheel_filename(wheel_path.name)
    except ValueError as exc:
        raise ArtifactValidationError(f"invalid wheel filename {wheel_path.name!r}: {exc}") from exc
    _check_distribution_name(distribution, wheel_path)
    if str(version) != expected_version:
        raise ArtifactValidationError(
            f"wheel filename version is {version}, expected {expected_version}: {wheel_path.name}"
        )

    try:
        with zipfile.ZipFile(wheel_path) as archive:
            members = archive.namelist()
            metadata_paths = [
                member for member in members if member.endswith(".dist-info/METADATA")
            ]
            if len(metadata_paths) != 1:
                raise ArtifactValidationError(
                    "wheel must contain exactly one .dist-info/METADATA, "
                    f"found {len(metadata_paths)}"
                )
            metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))
            if canonicalize_name(metadata.get("Name", "")) != "ssmdconvert":
                raise ArtifactValidationError(
                    f"wheel METADATA Name is {metadata.get('Name')!r}, expected 'ssmdconvert'"
                )
            if metadata.get("Version") != expected_version:
                raise ArtifactValidationError(
                    "wheel METADATA version is "
                    f"{metadata.get('Version')!r}, expected {expected_version}"
                )
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArtifactValidationError(f"could not read wheel archive {wheel_path}: {exc}") from exc

    if "ssmdconvert/__init__.py" not in members:
        raise ArtifactValidationError("wheel does not contain the ssmdconvert package")
    marker_count = members.count("ssmdconvert/py.typed")
    if marker_count != 1:
        raise ArtifactValidationError(
            f"wheel must contain ssmdconvert/py.typed exactly once, found {marker_count}"
        )

    development_members = _development_members(members, _WHEEL_DEVELOPMENT_PARTS)
    development_members.extend(
        member for member in members if PurePosixPath(member).name in _WHEEL_DEVELOPMENT_FILES
    )
    if development_members:
        raise ArtifactValidationError(
            "wheel contains development-only content: "
            + ", ".join(sorted(set(development_members)))
        )


def _check_sdist(sdist_path: Path, expected_version: str) -> None:
    try:
        distribution, version = parse_sdist_filename(sdist_path.name)
    except ValueError as exc:
        raise ArtifactValidationError(f"invalid sdist filename {sdist_path.name!r}: {exc}") from exc
    _check_distribution_name(distribution, sdist_path)
    if str(version) != expected_version:
        raise ArtifactValidationError(
            f"sdist filename version is {version}, expected {expected_version}: {sdist_path.name}"
        )

    try:
        with tarfile.open(sdist_path, "r:gz") as archive:
            members = archive.getnames()
    except (OSError, tarfile.TarError) as exc:
        raise ArtifactValidationError(f"could not read sdist archive {sdist_path}: {exc}") from exc

    if not any(PurePosixPath(member).name == "pyproject.toml" for member in members):
        raise ArtifactValidationError("sdist does not contain pyproject.toml")
    if not any(member.endswith("/ssmdconvert/__init__.py") for member in members):
        raise ArtifactValidationError("sdist does not contain the ssmdconvert package")
    if not any(member.endswith("/ssmdconvert/py.typed") for member in members):
        raise ArtifactValidationError("sdist does not contain ssmdconvert/py.typed")
    development_members = _development_members(
        members, _SDIST_FORBIDDEN_PARTS, reject_egg_info=False
    )
    if development_members:
        raise ArtifactValidationError(
            "sdist contains forbidden local state: " + ", ".join(sorted(set(development_members)))
        )


def validate_release_artifacts(tag: str | None, dist_dir: Path = Path("dist")) -> str:
    """Validate the wheel and source archive built for a release tag."""
    if not tag:
        raise ArtifactValidationError(
            "RELEASE_TAG is required; pass the published GitHub release tag."
        )
    match = _TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ArtifactValidationError(
            f"invalid release tag {tag!r}; expected vX.Y.Z (for example v0.1.0)."
        )
    expected_version = ".".join(match.groups())

    if not dist_dir.is_dir():
        raise ArtifactValidationError(f"distribution directory does not exist: {dist_dir}")
    wheels = sorted(path for path in dist_dir.rglob("*.whl") if path.is_file())
    sdists = sorted(path for path in dist_dir.rglob("*.tar.gz") if path.is_file())
    if len(wheels) != 1:
        raise ArtifactValidationError(
            f"expected exactly one .whl under {dist_dir}, found {len(wheels)}"
        )
    if len(sdists) != 1:
        raise ArtifactValidationError(
            f"expected exactly one .tar.gz under {dist_dir}, found {len(sdists)}"
        )

    _check_wheel(wheels[0], expected_version)
    _check_sdist(sdists[0], expected_version)
    return (
        f"Validated release {tag} (version {expected_version}): "
        f"{wheels[0].name} and {sdists[0].name}"
    )


def main() -> int:
    try:
        summary = validate_release_artifacts(os.environ.get("RELEASE_TAG"))
    except ArtifactValidationError as exc:
        print(f"Release artifact validation failed: {exc}", file=sys.stderr)
        return 1
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

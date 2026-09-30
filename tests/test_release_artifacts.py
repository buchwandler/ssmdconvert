from __future__ import annotations

import tarfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from tools.check_release_artifacts import ArtifactValidationError, validate_release_artifacts


def _write_artifacts(
    dist: Path,
    *,
    wheel_filename_version: str = "0.1.0",
    metadata_version: str = "0.1.0",
    sdist_version: str = "0.1.0",
    include_marker: bool = True,
    wheel_extra: str | None = None,
    sdist_extra: str | None = None,
) -> tuple[Path, Path]:
    dist.mkdir(parents=True, exist_ok=True)
    wheel_path = dist / f"ssmdconvert-{wheel_filename_version}-py3-none-any.whl"
    with ZipFile(wheel_path, "w") as wheel:
        wheel.writestr(
            "ssmdconvert-0.1.0.dist-info/METADATA",
            f"Name: ssmdconvert\nVersion: {metadata_version}\n",
        )
        wheel.writestr("ssmdconvert/__init__.py", "")
        if include_marker:
            wheel.writestr("ssmdconvert/py.typed", "")
        if wheel_extra:
            wheel.writestr(wheel_extra, "")

    sdist_path = dist / f"ssmdconvert-{sdist_version}.tar.gz"
    root = f"ssmdconvert-{sdist_version}"
    sdist_members = {
        f"{root}/pyproject.toml": b"[build-system]\n",
        f"{root}/ssmdconvert/__init__.py": b"",
        f"{root}/ssmdconvert.egg-info/PKG-INFO": b"Name: ssmdconvert",
        f"{root}/ssmdconvert/py.typed": b"",
    }
    if sdist_extra:
        sdist_members[f"{root}/{sdist_extra}"] = b""
    with tarfile.open(sdist_path, "w:gz") as sdist:
        for name, content in sdist_members.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            sdist.addfile(member, BytesIO(content))
    return wheel_path, sdist_path


def test_validates_release_artifacts(tmp_path: Path) -> None:
    wheel, sdist = _write_artifacts(tmp_path / "dist")

    summary = validate_release_artifacts("v0.1.0", tmp_path / "dist")

    assert "Validated release v0.1.0 (version 0.1.0)" in summary
    assert wheel.name in summary
    assert sdist.name in summary


def test_requires_release_tag(tmp_path: Path) -> None:
    with pytest.raises(ArtifactValidationError, match="RELEASE_TAG is required"):
        validate_release_artifacts(None, tmp_path)


@pytest.mark.parametrize("tag", ["0.1.0", "v0.1", "v01.2.3"])
def test_rejects_tags_outside_release_policy(tmp_path: Path, tag: str) -> None:
    with pytest.raises(ArtifactValidationError, match="expected vX.Y.Z"):
        validate_release_artifacts(tag, tmp_path)


def test_rejects_wheel_filename_version_mismatch(tmp_path: Path) -> None:
    _write_artifacts(tmp_path / "dist", wheel_filename_version="0.2.0")

    with pytest.raises(ArtifactValidationError, match="wheel filename version"):
        validate_release_artifacts("v0.1.0", tmp_path / "dist")


def test_rejects_wheel_metadata_version_mismatch(tmp_path: Path) -> None:
    _write_artifacts(tmp_path / "dist", metadata_version="0.2.0")

    with pytest.raises(ArtifactValidationError, match="wheel METADATA version"):
        validate_release_artifacts("v0.1.0", tmp_path / "dist")


def test_rejects_sdist_filename_version_mismatch(tmp_path: Path) -> None:
    _write_artifacts(tmp_path / "dist", sdist_version="0.2.0")

    with pytest.raises(ArtifactValidationError, match="sdist filename version"):
        validate_release_artifacts("v0.1.0", tmp_path / "dist")


def test_requires_typed_marker_in_wheel(tmp_path: Path) -> None:
    _write_artifacts(tmp_path / "dist", include_marker=False)

    with pytest.raises(ArtifactValidationError, match="ssmdconvert/py.typed exactly once"):
        validate_release_artifacts("v0.1.0", tmp_path / "dist")


def test_rejects_development_content_in_wheel(tmp_path: Path) -> None:
    _write_artifacts(tmp_path / "dist", wheel_extra="tests/test_internal.py")

    with pytest.raises(ArtifactValidationError, match="development-only content"):
        validate_release_artifacts("v0.1.0", tmp_path / "dist")


def test_rejects_ledger_state_in_sdist(tmp_path: Path) -> None:
    _write_artifacts(tmp_path / "dist", sdist_extra=".ledger/taskledger/private.yaml")

    with pytest.raises(ArtifactValidationError, match="forbidden local state"):
        validate_release_artifacts("v0.1.0", tmp_path / "dist")


def test_requires_exactly_one_of_each_artifact(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    wheel, _sdist = _write_artifacts(dist)
    (dist / "extra.whl").touch()

    with pytest.raises(ArtifactValidationError, match="exactly one .whl"):
        validate_release_artifacts("v0.1.0", dist)

    wheel.unlink()

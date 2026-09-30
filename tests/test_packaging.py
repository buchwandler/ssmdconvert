from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


def test_dynamic_versioning_and_flat_layout() -> None:
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dynamic"] == ["version"]
    assert data["tool"]["setuptools_scm"]["version_file"] == "ssmdconvert/_version.py"
    assert (root / "ssmdconvert").is_dir()
    assert not (root / "src").exists()


def test_py_typed_marker_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "ssmdconvert" / "py.typed").is_file()


def test_packaging_metadata_matches_release_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["license"] == "Apache-2.0"
    extras = data["project"]["optional-dependencies"]
    assert "sfx" not in extras
    assert all("sfxrender" not in dependency for dependency in extras["all"])

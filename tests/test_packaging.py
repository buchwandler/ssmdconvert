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
    assert "jev" not in extras
    assert "speech" in extras
    assert all("sfxrender" not in dependency for dependency in extras["all"])


def test_speech_preparation_dependencies_are_bounded() -> None:
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]

    assert "ssmd>=0.9.3,<0.10" in dependencies
    assert "epub2text>=0.2.8,<0.3" in dependencies
    assert "typer>=0.20,<1" in dependencies
    assert "spokenform>=0.4.3,<0.5" not in dependencies
    assert "tomli>=2; python_version < '3.11'" in dependencies
    extras = data["project"]["optional-dependencies"]
    assert extras["speech"] == ["spokenform>=0.4.3,<0.5"]
    assert "spokenform>=0.4.3,<0.5" in extras["all"]

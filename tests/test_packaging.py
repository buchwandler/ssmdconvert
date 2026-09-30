from pathlib import Path

import tomllib


def test_dynamic_versioning_and_flat_layout() -> None:
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dynamic"] == ["version"]
    assert data["tool"]["setuptools_scm"]["version_file"] == "ssmdconvert/_version.py"
    assert (root / "ssmdconvert").is_dir()
    assert not (root / "src").exists()

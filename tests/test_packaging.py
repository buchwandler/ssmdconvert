import ast
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
    assert "speech" not in extras
    assert all("sfxrender" not in dependency for dependency in extras["all"])


def test_ttsready_is_core_and_spokenform_is_not_a_direct_dependency() -> None:
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]

    assert "ssmd>=0.9.3,<0.10" in dependencies
    assert "ttsready>=0.2,<0.3" in dependencies
    assert "epub2text>=0.2.8,<0.3" in dependencies
    assert "typer>=0.20,<1" in dependencies
    assert "spokenform>=0.4.3,<0.5" not in dependencies
    assert "tomli>=2; python_version < '3.11'" in dependencies
    extras = data["project"]["optional-dependencies"]
    assert all("spokenform" not in dependency for items in extras.values() for dependency in items)


def test_ssmdconvert_has_no_direct_spokenform_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    violations = []
    for source in (root / "ssmdconvert").rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                violations.extend(
                    f"{source}:{node.lineno}: {alias.name}"
                    for alias in node.names
                    if alias.name == "spokenform" or alias.name.startswith("spokenform.")
                )
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module == "spokenform" or node.module.startswith("spokenform."):
                    violations.append(f"{source}:{node.lineno}: from {node.module}")
    assert not violations, "direct spokenform imports found: " + ", ".join(violations)

# Releasing ssmdconvert

Package versions are derived from Git tags by `setuptools-scm`. Release tags use the `vX.Y.Z` form, for example `v0.1.0`.

## 1. Local release-readiness checks

Run these checks before creating a release tag:

```bash
python -m pip install -e ".[all,dev]"
python -m compileall -q ssmdconvert tests tools
python -m pytest -m "not slow"
python -m ruff check .
python -m mypy --config-file tests/typecheck/mypy.ini tests/typecheck/public_api.py
python -m pip install -r docs/requirements.txt
python -m sphinx -W --keep-going -b html docs docs/_build/html
rm -rf dist build
SETUPTOOLS_SCM_PRETEND_VERSION=0.1.0 python -m build
python -m twine check dist/*
RELEASE_TAG=v0.1.0 python tools/check_release_artifacts.py
```

Install the built wheel in a clean environment and smoke-test the installed package, not the checkout:

```bash
repo="$(pwd)"
python -m venv /tmp/ssmdconvert-wheel-smoke
/tmp/ssmdconvert-wheel-smoke/bin/python -m pip install dist/*.whl
cd /tmp
/tmp/ssmdconvert-wheel-smoke/bin/python -c "import ssmdconvert; print(ssmdconvert.__version__)"
/tmp/ssmdconvert-wheel-smoke/bin/ssmdconvert --version
/tmp/ssmdconvert-wheel-smoke/bin/ssmdconvert --help
/tmp/ssmdconvert-wheel-smoke/bin/python "$repo/tools/smoke_installed.py"
/tmp/ssmdconvert-wheel-smoke/bin/python -m pip check
```

CI also checks the exact minimum versions of `ssmd`, `epub2text`, Typer, and the optional speech dependency, tests base installation without extras, and runs separate optional-extra checks.

Review the generated changelog and planned releaseledger entry. Do not publish from a dirty or unverified working tree.

## 2. Verify the release version

Create and push the annotated tag only after the main branch checks are green:

```bash
git tag -a v0.1.0 -m "ssmdconvert 0.1.0"
git push origin v0.1.0
```

The publish workflow checks out the full tag history, builds from that tag, checks the distributions, installs and smoke-tests the wheel, and validates artifact filenames and metadata against the tag version. The wheel must contain `ssmdconvert/py.typed` without development-only files.

## 3. Publish the GitHub Release

The PyPI workflow is triggered by a **published GitHub Release**, not by a tag push alone. Create and publish the GitHub Release for the verified tag after its CI checks are green.

## 4. PyPI Trusted Publishing

The release workflow uses OpenID Connect through PyPI Trusted Publishing. Configure the PyPI trusted publisher for:

- Owner: `buchwandler`
- Repository: `ssmdconvert`
- Workflow: `python-publish.yml`
- GitHub environment: `pypi`

The workflow grants `id-token: write` only to the deployment job and publishes through `pypa/gh-action-pypi-publish`. No long-lived PyPI API token is required.

## 5. Post-release verification

Install the published version in a clean environment and check the CLI:

```bash
python -m pip install --no-cache-dir ssmdconvert==0.1.0
ssmdconvert --version
ssmdconvert --help
```

Verify the PyPI project metadata, README rendering, Apache-2.0 license, wheel, and source distribution. Then mark the releaseledger release as released with the actual release date and artifact evidence.

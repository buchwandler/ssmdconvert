# Releasing ssmdconvert

Package versions are derived from Git tags by `setuptools-scm`. Release tags use the `vX.Y.Z` form, for example `v0.1.0`.

## 1. Pre-release checks

Start from a clean `main` branch and verify the release notes and planned releaseledger entry.

```bash
git status --short
python -m pip install -e ".[all,dev]"
python -m compileall -q ssmdconvert tests
python -m pytest
python -m ruff check .
python -m mypy --config-file tests/typecheck/mypy.ini tests/typecheck/public_api.py
python -m pip install -r docs/requirements.txt
python -m sphinx -W --keep-going -b html docs docs/_build/html
rm -rf dist build
python -m build
python -m twine check dist/*
```

Before release, ensure the changelog contains the reviewed 0.1.0 notes and the releaseledger record remains planned until publication.

## 2. Verify the release version

Create and push the annotated tag only after the main branch checks are green:

```bash
git tag -a v0.1.0 -m "ssmdconvert 0.1.0"
git push origin v0.1.0
```

The publish workflow checks out the full tag history, builds from that tag, verifies the artifact filenames and metadata against the tag version, and checks that the wheel contains `ssmdconvert/py.typed` without development-only files.

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

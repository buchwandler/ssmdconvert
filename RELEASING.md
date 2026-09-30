# Releasing

`ssmdconvert` uses Git tags and `setuptools-scm`; there is no manually maintained
version constant and no `src/` directory.

```bash
python -m pytest
python -m build
python -m twine check dist/*
git tag -a v0.1.0 -m "ssmdconvert 0.1.0"
git push origin v0.1.0
```

The PyPI workflow listens for a published GitHub Release event, not for a tag push alone. After
pushing the version tag, publish a GitHub Release for that tag to trigger the configured OIDC
upload. Configure PyPI Trusted Publishing for repository `buchwandler/ssmdconvert` and the
`pypi` GitHub environment before the first release.

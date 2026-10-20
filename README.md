# ssmdconvert

`ssmdconvert` is a deterministic, local conversion library and CLI for turning
common documents and EPUB books into valid SSMD 0.9. It can also analyze,
project, and safely update SSMD speech annotations.

## Install

```bash
python -m pip install ssmdconvert
```

PDF, DOCX, and local spaCy enrichment are optional:

```bash
python -m pip install "ssmdconvert[pdf]"
python -m pip install "ssmdconvert[docx]"
python -m pip install "ssmdconvert[spacy]"
```

Python 3.10 or newer is required. Conversion and analysis run locally. SSMDConvert
does not download language models; the default `--spacy off` avoids loading spaCy.

## One bundle workflow

Book and document sources use the same bundle commands and canonical artifact
names. Editable workspaces are directories ending in `.ssmd-bundle`; portable
archives end in `.ssmd-bundle.zip`. The manifest retains the existing kind-specific
format and determines how the content is validated.

```bash
ssmdconvert bundle inspect novel.epub --json
ssmdconvert bundle convert novel.epub --chapters 2-20 -o novel.ssmd-bundle
ssmdconvert bundle convert notes.md -o notes.ssmd-bundle
ssmdconvert bundle validate novel.ssmd-bundle
ssmdconvert bundle pack notes.ssmd-bundle
```

When output is omitted, conversion creates a workspace beside the source. Use
`--force` to replace an existing workspace. Chapter selection applies to books
and uses original one-based source numbers.

The `bundle` command group provides six operations: `inspect`, `convert`,
`metadata`, `refresh`, `pack`, and `validate`. Only directory workspaces can be
refreshed or packed; ZIP archives are read-only. See the [bundle guide](docs/bundles.md)
for dirty-workspace behavior and manifest details.

A standalone SSMD file can also be rendered with the top-level converter:

```bash
ssmdconvert convert manuscript.md -o manuscript.ssmd
ssmdconvert inspect manuscript.ssmd --json
```

## Analysis and speech workflows

Reports, context lookup, plain-text projection, and speech commands accept
standalone SSMD and either bundle storage form:

```bash
ssmdconvert report novel.ssmd-bundle.zip --chapters 2-20
ssmdconvert context novel.ssmd-bundle chg:v1:0123456789abcdef0123456789abcdef
ssmdconvert txt notes.ssmd-bundle -o prepared.txt
ssmdconvert speech audit notes.ssmd-bundle --json
ssmdconvert speech freeze novel.ssmd-bundle.zip -o frozen.ssmd-bundle.zip
```

Book conversion freezes eligible automatic speech decisions by default. Use
`--speech-semantics preserve` for structural-only conversion. Speech write-back
publishes a new destination and never mutates a workspace in place. The
[analysis workflow guide](docs/analysis-workflows.md) describes cache freshness,
language handling, progress, and safe publication.

## Python API

The `convert_bundle()` API dispatches supported sources and publishes a canonical
workspace. Bundle loading, inspection, validation, refresh, and packing use the
same neutral facade:

```python
from ssmdconvert import convert_bundle, load_bundle, pack_bundle

result = convert_bundle("novel.epub", output="novel.ssmd-bundle")
loaded = load_bundle(result.output)
assert loaded.kind == "book"
archive = pack_bundle("novel.ssmd-bundle")
```

Lower-level document and book conversion functions remain available for callers
that need in-memory models or custom publication. See the [Python API reference](docs/api.md).

## Documentation

- [Installation](docs/installation.md)
- [Bundle workspaces](docs/bundles.md)
- [CLI usage](docs/usage.md)
- [Analysis and speech workflows](docs/analysis-workflows.md)
- [Python API](docs/api.md)

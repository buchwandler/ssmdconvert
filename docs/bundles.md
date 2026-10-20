# SSMD bundle workspaces

SSMDConvert stores converted books and single documents in one kind-neutral
artifact lifecycle. The manifest identifies whether a bundle contains a book or
a document; users do not choose a storage type.

## Canonical names

An editable workspace is a directory named `<name>.ssmd-bundle/`. A portable,
immutable archive is named `<name>.ssmd-bundle.zip`. Both contain the existing
kind-specific manifest format and schema version; the outer artifact name is
shared.

```text
novel.ssmd-bundle/
novel.ssmd-bundle.zip
notes.ssmd-bundle/
notes.ssmd-bundle.zip
```

## Convert and inspect

```bash
ssmdconvert bundle inspect novel.epub --json
ssmdconvert bundle convert novel.epub --chapters 2-20 -o novel.ssmd-bundle
ssmdconvert bundle convert notes.md -o notes.ssmd-bundle
ssmdconvert bundle convert reviewed.ssmd.md
ssmdconvert bundle validate novel.ssmd-bundle
```

When the output is omitted, conversion creates a directory workspace beside the
source using its filename stem. `--force` replaces the complete existing
workspace atomically. `bundle inspect` accepts a supported source or a canonical
bundle and reports the detected kind.

`--chapters` selects original, one-based source chapter numbers for books. A
single document accepts the default `all` value; another chapter selector is a
usage error. Book chapters remain in source order.

## Lifecycle commands

The `bundle` command group contains exactly these lifecycle operations:

- `inspect SOURCE` inspects a supported source or bundle.
- `convert SOURCE` creates an editable workspace.
- `metadata BUNDLE` displays stored metadata.
- `refresh WORKSPACE` updates recorded content digests; `--check` only checks
  whether the workspace is clean.
- `pack WORKSPACE` creates a deterministic `.ssmd-bundle.zip` archive.
- `validate BUNDLE` strictly checks the manifest and referenced content.

Only a directory workspace can be refreshed or packed. ZIP archives are
read-only. `validate` and strict bundle loading verify manifest hashes; analysis
workflows can read current valid content from a dirty directory workspace
without silently refreshing it. Packing reads current valid workspace content
and does not change the workspace manifest.

```bash
ssmdconvert bundle metadata notes.ssmd-bundle --json
ssmdconvert bundle refresh notes.ssmd-bundle --check
ssmdconvert bundle refresh notes.ssmd-bundle
ssmdconvert bundle pack notes.ssmd-bundle
ssmdconvert bundle validate notes.ssmd-bundle.zip
```

## Shared downstream workflows

Reports, cached context, plain-text projection, and speech workflows accept
standalone SSMD or either canonical bundle storage form:

```bash
ssmdconvert report novel.ssmd-bundle.zip --chapters 2-8
ssmdconvert context novel.ssmd-bundle chg:v1:0123456789abcdef0123456789abcdef
ssmdconvert txt notes.ssmd-bundle -o notes.txt
ssmdconvert speech audit notes.ssmd-bundle --json
ssmdconvert speech freeze novel.ssmd-bundle.zip -o frozen.ssmd-bundle.zip
```

Speech writes publish to a new destination; they never mutate a workspace in
place. Book conversion freezes eligible automatic speech decisions by default.
Use `--speech-semantics preserve` for structural-only book conversion.

## Python API

The public storage API is kind-neutral. Internal manifest formats continue to
dispatch to their existing validators.

```python
from ssmdconvert import (
    convert_bundle,
    load_bundle,
    pack_bundle,
    refresh_bundle_workspace,
    validate_bundle,
)

result = convert_bundle("novel.epub", output="novel.ssmd-bundle")
loaded = load_bundle(result.output)
assert loaded.kind == "book"

workspace = refresh_bundle_workspace("novel.ssmd-bundle")
archive = pack_bundle("novel.ssmd-bundle")
assert validate_bundle(archive) == workspace.kind
```

See the [Python API reference](api.md), [analysis workflows](analysis-workflows.md),
and [manifest implementation details](bundle-format.md) for further information.

# CLI usage

SSMDConvert uses one bundle lifecycle for EPUB books, ordinary documents, and
existing SSMD sources. Every editable workspace ends in `.ssmd-bundle`; a packed
archive ends in `.ssmd-bundle.zip`.

## Convert, inspect, and validate

```bash
ssmdconvert bundle inspect novel.epub --json
ssmdconvert bundle convert novel.epub --chapters 2-20 -o novel.ssmd-bundle
ssmdconvert bundle convert notes.md -o notes.ssmd-bundle
ssmdconvert bundle convert reviewed.ssmd.md
ssmdconvert bundle validate novel.ssmd-bundle
```

When `-o` is omitted, `bundle convert` creates an editable workspace beside the
source. Existing outputs are refused unless `--force` is supplied; forced
workspace publication replaces the complete directory atomically.

`--chapters` accepts original one-based book chapter numbers, as a number, a
range, a comma-separated list, or a mixture such as `1,3-5`. It defaults to
`all`. A non-default selector is not valid for a single-document source.

The lifecycle group contains six commands:

```text
ssmdconvert bundle inspect SOURCE
ssmdconvert bundle convert SOURCE
ssmdconvert bundle metadata BUNDLE [--json]
ssmdconvert bundle refresh WORKSPACE [--check]
ssmdconvert bundle pack WORKSPACE [-o ARCHIVE]
ssmdconvert bundle validate BUNDLE [--json]
```

Only directory workspaces can be refreshed or packed. ZIP archives are
read-only. `refresh --check` does not write; `pack` creates a deterministic
archive without refreshing or otherwise changing the workspace.

## Standalone SSMD conversion

The top-level converter remains available for writing one standalone SSMD file:

```bash
ssmdconvert convert manuscript.txt -o manuscript.ssmd
ssmdconvert convert report.pdf -o report.ssmd
ssmdconvert inspect manuscript.md --json
```

PDF and DOCX inputs require the matching optional extras. Writes are atomic and
refuse existing outputs unless `--force` is supplied. The input file is never a
valid output destination.

Conversion commands accept `--metadata-file PATH` for a UTF-8 YAML mapping.
Metadata precedence is source, file, and explicit CLI values. The sequence
fallback mode defaults to `preserve`; the option is available when a caller
needs `spell`.

```yaml
language: de-DE
voice_defaults:
  narrator:
    rate: slow
```

## Reports and speech workflows

```bash
ssmdconvert report novel.ssmd-bundle.zip --chapters 2-8 --format json
ssmdconvert context novel.ssmd-bundle chg:v1:0123456789abcdef0123456789abcdef
ssmdconvert txt notes.ssmd-bundle -o prepared.txt
ssmdconvert speech audit notes.ssmd-bundle --json
ssmdconvert speech annotate notes.ssmd-bundle -o annotated.ssmd-bundle
ssmdconvert speech freeze novel.ssmd-bundle.zip -o frozen.ssmd-bundle.zip
```

Analysis accepts standalone SSMD and canonical directory or ZIP bundles.
Speech audit is read-only. Annotation and freeze publish a new destination and
never modify a workspace in place. See [analysis and speech workflows](analysis-workflows.md)
for cache freshness, language behavior, and output policy.

## Bundle-local speech profiles and inventory

New bundles contain an editable root-level `speech.toml`. Bundle inputs automatically use that profile for `report`, `txt`, `speech audit`, `speech inventory`, `speech annotate`, and `speech freeze`. An explicit `--speech-profile PATH` overrides the local recipe for that operation; SSMDConvert never searches ambient directories. Legacy bundles without the sidecar use an empty profile and remain readable.

```bash
# Bootstrap from inventory and copy an external profile into a new bundle.
ssmdconvert speech inventory novel.epub --format toml -o speech.toml
ssmdconvert bundle convert novel.epub -o novel.ssmd-bundle --speech-profile speech.toml

# Or edit the bundle's recipe with the CLI or a text editor.
ssmdconvert speech set novel.ssmd-bundle ART art
ssmdconvert speech set novel.ssmd-bundle B-E "B E"
ssmdconvert speech remove novel.ssmd-bundle B-E
ssmdconvert report novel.ssmd-bundle
ssmdconvert speech audit novel.ssmd-bundle --json

# Rebuild from the original source; the destination profile is reused automatically.
ssmdconvert bundle convert novel.epub -o novel.ssmd-bundle --force
ssmdconvert speech export novel.ssmd-bundle -o portable-speech.toml
```

Direct edits to `speech.toml` do not require `bundle refresh` and do not rewrite materialized chapters. Changing a recipe requires rebuilding from the original source; `--force` intentionally replaces the complete destination bundle and any chapter edits. Existing SSMD `sub` annotations remain authoritative. `speech set` and `speech remove` modify directory workspaces only; `speech export` accepts a workspace or packed archive and refuses an existing output unless `--force` is supplied.

`--speech-profile PATH` remains available on `bundle convert`, `report`, `txt`, `speech audit`, `speech inventory`, `speech annotate`, and `speech freeze`. For conversion, an explicit profile wins over an existing destination recipe; without it, the destination's `speech.toml` is reused, or an empty profile is used for a new destination. Selection and validation occur before forced replacement. With `--speech-semantics preserve`, conversion stores the selected recipe but does not materialize its replacements.

The inventory command identifies candidate surfaces in raw EPUB/document sources, standalone SSMD, and directory or ZIP bundles. Its default output is a table; `--format json` emits a versioned result and `--format toml` writes a portable profile template. Inventory output must be written outside a bundle workspace.

See [speech replacement profiles](speech-profiles.md) for profile schema, matching policy, precedence, and the rebuild workflow, and [speech-risk inventory](speech-inventory.md) for candidate signals and output formats.

## Help

```bash
ssmdconvert --help
ssmdconvert bundle --help
ssmdconvert bundle convert --help
ssmdconvert bundle validate --help
ssmdconvert report --help
ssmdconvert speech --help
```

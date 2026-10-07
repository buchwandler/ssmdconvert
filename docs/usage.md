# CLI usage

## Convert a document

```bash
ssmdconvert convert INPUT [-o OUTPUT] [--title TITLE] [--author AUTHOR] [-l|--language LANGUAGE] [--metadata-file PATH] [--sequence-fallback-mode spell|preserve]
```

Examples:

```bash
ssmdconvert convert manuscript.txt -o manuscript.ssmd
ssmdconvert convert novel.md -o novel.ssmd
ssmdconvert convert page.html -o page.ssmd
ssmdconvert convert book.epub -o book.ssmd
ssmdconvert convert report.pdf -o report.ssmd
ssmdconvert convert manuscript.docx -o manuscript.ssmd
ssmdconvert convert existing.ssmd.md -o normalized.ssmd
```

PDF and DOCX require the `[pdf]` and `[docx]` extras. SSMD detection accepts `.ssmd` and `.ssmd.md` case-insensitively. If `-o` is omitted, the output is written beside the input with a `.ssmd` suffix.

Writes are atomic and refuse existing destinations unless `--force` is supplied. The input path is never accepted as the output, even with `--force`. A failed write leaves a prior output intact.

Optional metadata can be supplied during conversion:

```bash
ssmdconvert convert manuscript.txt \
  --title "Example" \
  --author "A. Writer" \
  -l en
```

Pass a UTF-8 YAML mapping with `--metadata-file PATH` to either `convert` or `book convert` for nested portable metadata and bibliographic overrides. Values are JSON-compatible; only supported metadata keys are accepted. Metadata precedence is source, file, then explicit CLI values. The effective sequence fallback option is applied last.

```yaml
language: de-DE
voice_defaults:
  narrator:
    rate: slow
```

The sequence fallback policy controls residual sequence handling for downstream speech preparation. New conversions default to `preserve`; pass `--sequence-fallback-mode spell` to select `spell` explicitly. The chosen value is persisted in SSMD front matter and, for books, in manifest metadata and every chapter. This writer default does not change consumer behavior for legacy files or bundles where the field is absent.

```bash
ssmdconvert convert manuscript.md -o manuscript.ssmd
ssmdconvert book convert novel.epub -l de-DE -o novel.ssmdbook
```

## Inspect a source

Inspect the selected local adapter and normalized document without writing output:

```bash
ssmdconvert inspect book.epub
ssmdconvert inspect book.epub --json
```

JSON output includes the source path, selected adapter, normalized metadata, and section identifiers, titles, character counts, and source references.

## EPUB book commands

The book CLI uses explicit subcommands:

```bash
ssmdconvert book inspect novel.epub [--json]
ssmdconvert book convert novel.epub [--chapters SELECTOR] [-o OUTPUT] [-l|--language LANGUAGE] [--metadata-file PATH] [--sequence-fallback-mode spell|preserve]
ssmdconvert book validate BUNDLE [--json]
ssmdconvert book metadata BUNDLE [--json]
```

Selectors use original 1-based source chapter numbers. They accept a single number, a range, a comma-separated list, or a mixture such as `1,3-5`. Selected chapters remain in original source order.

Book output format is inferred only from `.ssmdbook` (directory) and `.ssmdbook.zip` (ZIP). For other names, specify `--format directory` or `--format zip`. Existing bundles are refused unless `--force` is supplied. A forced directory output replaces the complete previous directory; stale files are not merged into the new bundle.

Use `ssmdconvert book metadata BUNDLE` to display validated metadata stored in either a directory or ZIP bundle. Add `--json` for a deterministic `{"metadata": ...}` object. The human form labels absent known values as `not set` and renders nested values indented.

## SSMD analysis and speech commands

Use the shared SSMD-aware analysis commands for reports, context lookup, prepared TXT, and speech write-back:

```bash
ssmdconvert report SOURCE [--chapters SELECTOR] [--format md|json] [--refresh]
ssmdconvert context SOURCE CHANGE_ID [--paragraph] [--json]
ssmdconvert txt SOURCE [--chapters SELECTOR] [-o OUTPUT]
ssmdconvert speech audit SOURCE [--json]
ssmdconvert speech annotate SOURCE -o OUTPUT
ssmdconvert speech freeze SOURCE -o OUTPUT
```

The commands accept standalone SSMD, validated ZIP bundles, and directory workspaces. Reports and TXT share a projection; `context` resolves a generic change ID from a report cache. `speech audit` is read-only. Annotation and freeze write to a new destination by default, preserve visible text, and refuse to modify a source workspace in place. Existing output requires `--force`; the input cannot be overwritten. See [SSMD analysis and speech workflows](analysis-workflows.md) for language handling, cache freshness, workspace policy, and migration from the removed `ttsready` CLI.

## Help

```bash
ssmdconvert --help
ssmdconvert convert --help
ssmdconvert inspect --help
ssmdconvert book --help
ssmdconvert book inspect --help
ssmdconvert book convert --help
ssmdconvert book validate --help
ssmdconvert book metadata --help
ssmdconvert report --help
ssmdconvert context --help
ssmdconvert txt --help
ssmdconvert speech --help
ssmdconvert speech audit --help
ssmdconvert speech annotate --help
ssmdconvert speech freeze --help
```

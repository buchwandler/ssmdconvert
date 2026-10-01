# CLI usage

## Convert a document

```bash
ssmdconvert convert INPUT [-o OUTPUT] [--title TITLE] [--author AUTHOR] [--language LANGUAGE]
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
  --language en
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
ssmdconvert book convert novel.epub [--chapters SELECTOR] [-o OUTPUT]
ssmdconvert book validate BUNDLE [--json]
```

Selectors use original 1-based source chapter numbers. They accept a single number, a range, a comma-separated list, or a mixture such as `1,3-5`. Selected chapters remain in original source order.

Book output format is inferred only from `.ssmdbook` (directory) and `.ssmdbook.zip` (ZIP). For other names, specify `--format directory` or `--format zip`. Existing bundles are refused unless `--force` is supplied. A forced directory output replaces the complete previous directory; stale files are not merged into the new bundle.

## Help

```bash
ssmdconvert --help
ssmdconvert convert --help
ssmdconvert inspect --help
ssmdconvert book --help
ssmdconvert book inspect --help
ssmdconvert book convert --help
ssmdconvert book validate --help
```

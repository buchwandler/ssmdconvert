# EPUB chapters and book bundles

The book API provides ordered chapter inventory, source-number selection, standalone SSMD chapter conversion, and directory or ZIP bundles.

## Inspect chapters

```bash
ssmdconvert book chapters novel.epub
ssmdconvert book chapters novel.epub --json
```

The inventory reports original source chapter numbers and available navigation metadata.

## Select chapters

```bash
ssmdconvert book novel.epub --chapters 1 -o chapter-one.ssmdbook
ssmdconvert book novel.epub --chapters 1,3-5 -o selected.ssmdbook
ssmdconvert book novel.epub --chapters 2-20 -o selected.ssmdbook
```

Selectors use original 1-based source chapter numbers and address the complete source inventory. The output remains in source order even if selector text is unsorted. Duplicate numbers do not duplicate chapters. Missing chapters, zero or negative numbers, reversed ranges, and malformed tokens raise `ChapterSelectionError`.

## Speech preparation and reports

Speech preparation can be enabled independently for the selected chapters:

```bash
ssmdconvert book novel.epub \
  --chapters 2-5 \
  --speech annotate \
  --speech-language en \
  --pronunciations pronunciations.json
```

`--speech` supports `off` (default), `audit`, and `annotate`. Each selected chapter is prepared separately using its effective language. If speech preparation is enabled and `--speech-report` is omitted, the CLI writes a sibling JSON sidecar named `<bundle-name>.speech-report.json`; supply `--speech-report PATH` to choose another location. The sidecar identifies chapters by ID and includes each deterministic speech report. Speech-off mode writes no automatic sidecar, though an explicit `--speech-report` can request an empty report.

The Python `Book.speech_reports` mapping contains the reports for selected chapter IDs. Unresolved Unicode issues, skipped unsafe mappings, and language warnings are also projected into the existing chapter `diagnostics` list. The detailed report mapping is transient: it is not added to the version-1 bundle manifest, so the bundle schema and chapter order/metadata remain unchanged. `--strict-speech` fails the conversion on error-level QC findings. All processing is local; nothing is sent to JEV or a cloud provider.

Generated `sub` annotations keep source text visible. Existing author `sub`, `as`/`say-as`, and phoneme instructions are preserved. Any existing `say-as` interpretation remains dependent on the downstream consumer/provider.

## Directory bundle

```bash
ssmdconvert book novel.epub -o novel.ssmdbook
```

A `.ssmdbook` directory is editable. It contains a `manifest.json` and one standalone SSMD file per selected chapter. Chapter documents can be revised independently.

## ZIP bundle

```bash
ssmdconvert book novel.epub -o novel.ssmdbook.zip
```

A `.zip` bundle is portable and uses the same manifest model as a directory bundle. The manifest chapter array defines order.

## Validate a bundle

```bash
ssmdconvert book validate novel.ssmdbook
ssmdconvert book validate novel.ssmdbook.zip
```

Loading a bundle performs the same strict validation as the validation command.

## Python API

```python
from ssmdconvert import (
    convert_book,
    inspect_book,
    load_book_bundle,
    validate_book_bundle,
    write_book_bundle,
)

inspection = inspect_book("novel.epub")
book = convert_book("novel.epub", chapters="2-20")
write_book_bundle(book, "selected.ssmdbook")
loaded = load_book_bundle("selected.ssmdbook")
validate_book_bundle("selected.ssmdbook")
```

## Preserve the combined conversion API

The existing EPUB conversion remains a single combined SSMD document:

```text
Converter.convert(epub) -> one combined SSMD document
convert_book(epub)     -> chapter-aware Book model
```

The chapter-aware API is separate, so existing `convert()` callers retain their behavior.

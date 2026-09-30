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

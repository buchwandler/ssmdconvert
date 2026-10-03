# EPUB chapters and book bundles

The book API provides ordered EPUB chapter inspection, source-number selection, standalone SSMD chapter conversion, and directory or ZIP bundles. Combined EPUB conversion through `ssmdconvert convert` remains a single SSMD document.

## Inspect chapters

```bash
ssmdconvert book inspect novel.epub
ssmdconvert book inspect novel.epub --json
```

Inspection returns source metadata and the complete ordered chapter inventory. `source_id` and `source_parent_id` preserve identifiers from the EPUB navigation data. `id` is the stable canonical `chapter-NNNN` identity, and `parent_id` refers to the canonical ID of the parent chapter when it is present in the inventory.

## Select chapters

```bash
ssmdconvert book convert novel.epub --chapters 1 -o chapter-one.ssmdbook
ssmdconvert book convert novel.epub --chapters 1,3-5 -o selected.ssmdbook
ssmdconvert book convert novel.epub --chapters 2-20 -o selected.ssmdbook
```

Selectors use original 1-based source chapter numbers. They address the complete source inventory, even when the output contains only a subset. Selected chapters always remain in source order. Duplicate numbers do not duplicate chapters. Missing chapters, zero or negative numbers, reversed ranges, and malformed tokens raise `ChapterSelectionError`.

New book conversions default to `sequence_fallback_mode=preserve`; `spell` remains an explicit option. The selected policy is written to the book manifest and mirrored into each chapter so extracted chapters remain self-contained. Existing bundles may omit the field, and this writer default does not redefine how consumers handle that absence.

```bash
ssmdconvert book convert novel.epub -l de-DE --metadata-file book-metadata.yaml -o novel.ssmdbook
```


`-l/--language` overrides the EPUB language. Without an override, the EPUB value is retained; if the source has no language, conversion leaves it absent. The effective language is stored in the bundle metadata and every chapter. `--metadata-file` accepts UTF-8 YAML with supported bibliographic and portable SSMD fields. Source metadata is overridden by the file, explicit CLI flags override the file, and the effective sequence policy takes final precedence.

Inspect the validated stored metadata in either bundle format:

```bash
ssmdconvert book metadata novel.ssmdbook
ssmdconvert book metadata novel.ssmdbook.zip --json
```

## Write and validate bundles

A directory bundle is editable. A ZIP bundle is portable. Both use the same manifest and chapter documents:

```bash
ssmdconvert book convert novel.epub -o novel.ssmdbook
ssmdconvert book convert novel.epub -o novel.ssmdbook.zip
ssmdconvert book validate novel.ssmdbook
ssmdconvert book validate novel.ssmdbook.zip --json
```

The CLI infers formats only from `.ssmdbook` and `.ssmdbook.zip`. Use `--format directory` or `--format zip` for another output name. Existing outputs are refused by default. `--force` replaces the complete directory bundle or ZIP file atomically; directory output does not merge stale files.

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
write_book_bundle(book, "selected.ssmdbook", format="directory")
loaded = load_book_bundle("selected.ssmdbook")
validate_book_bundle("selected.ssmdbook")
```

`Book.source_sha256` is captured during conversion. Bundle writing persists that captured hash and does not reread the source file. After loading a bundle, source provenance remains available in `Book.source`, but its local `path` is `None`.


`convert_book()` also accepts `language` and `metadata_overrides`. The explicit language wins over source and metadata-file values. The returned `Book.metadata` includes the effective language and portable metadata, and every chapter copies each supported portable SSMD key before SSMD 0.9 validation.

See [Bundle format](bundle-format.md) for manifest fields, canonical paths, integrity checks, and resource limits.

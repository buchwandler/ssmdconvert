# Book bundle format

A book bundle is a versioned interchange format. Directory and ZIP bundles use the same manifest model.

```text
format:         ssmdconvert.book
schema_version: 1
ssmd_version:   0.9
```

## Manifest example

```json
{
  "format": "ssmdconvert.book",
  "schema_version": 1,
  "ssmd_version": "0.9",
  "metadata": {
    "title": "Example Book",
    "sequence_fallback_mode": "preserve"
  },
  "source": {
    "format": "epub",
    "media_type": "application/epub+zip",
    "name": "example.epub",
    "sha256": "<64 lowercase hex characters>",
    "chapter_count": 12
  },
  "chapters": [
    {
      "id": "chapter-0001",
      "source_number": 1,
      "path": "chapters/chapter-0001.ssmd.md",
      "title": "Chapter One",
      "source_id": "nav:0:example",
      "source_parent_id": null,
      "href": "chapter-1.xhtml",
      "parent_id": null,
      "level": 1,
      "char_count": 1234,
      "sha256": "<64 lowercase hex characters>",
      "diagnostics": []
    }
  ]
}
```

`metadata.sequence_fallback_mode` is application metadata with the values `spell` and `preserve`. New conversions always write it, defaulting to `preserve`; `spell` is still available explicitly. Each chapter mirrors the same setting in its SSMD front matter. Older bundles may omit the value and remain valid. The new writer default does not define or change consumer behavior for an absent legacy field.


`metadata` remains an open JSON object within schema version 1. Converters may store portable SSMD keys such as `language`, `voice_bindings`, `voice_defaults`, `pause_defaults`, `prosody_transitions`, `language_detection`, and `requires`, along with bibliographic values. Readers do not require these optional keys and continue to accept unknown third-party metadata keys. Generated chapters mirror the portable SSMD keys and are validated as SSMD 0.9.

Use `ssmdconvert book metadata BUNDLE` to inspect metadata only after the bundle passes normal validation. The optional `--json` form emits a stable `{"metadata": ...}` object; nested values are rendered as indented JSON in human output.

The `chapters` array order is authoritative for book order. Consumers must not sort directory entries or filenames to infer order. Chapter IDs are canonical `chapter-NNNN` identities; each bundle path is derived from the ID. `source_id` and `source_parent_id` preserve EPUB navigation identifiers, while `parent_id` refers to a canonical chapter ID when the parent appears in the book inventory.

Each chapter file is an independently valid SSMD 0.9 document. Source and chapter SHA-256 values detect changed or corrupted data. The source hash is captured by `convert_book()` and stored with the resulting `Book`; writing a bundle does not reread or rehash the EPUB. Loading a bundle retains source name, format, and media type, but cannot provide a local source path.

## Validation and resource limits

Directory and ZIP bundles are validated before chapter content is returned. Validation includes:

- supported manifest format, schema, and SSMD version;
- normalized relative POSIX paths, with traversal, absolute, Windows-drive, and non-normalized paths rejected;
- duplicate chapter IDs, source numbers, paths, and ZIP member names rejected;
- ZIP symlinks rejected;
- required `manifest.json` and chapter files;
- source and chapter SHA-256 verification;
- UTF-8 decoding and standalone SSMD validation of every chapter.

The loader limits the manifest to 2 MiB, each referenced chapter to 64 MiB uncompressed, the total referenced chapter content to 512 MiB, and ZIP archives to 10,000 members. These bounds limit bundle content processed by the loader; they do not make bundle parsing a sandbox or establish general safety against every resource-exhaustion attack. Treat bundles as data and use the public validation API rather than reading archive paths directly.

ZIP output uses fixed timestamps and deterministic member metadata. Bundle writes build and validate a complete temporary sibling before publication. Existing destinations are refused by default. With `overwrite=True`, a directory bundle replaces the complete prior directory and does not retain stale files.

## Python API

```python
from ssmdconvert import load_book_bundle, validate_book_bundle, write_book_bundle

write_book_bundle(book, "book.ssmdbook", format="directory")
write_book_bundle(book, "book.ssmdbook.zip", format="zip")
write_book_bundle(book, "replacement.ssmdbook", format="directory", overwrite=True)
loaded = load_book_bundle("book.ssmdbook")
validate_book_bundle("book.ssmdbook")
```

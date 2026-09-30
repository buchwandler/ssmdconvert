# Book bundle format

A book bundle is a versioned interchange format. The directory and ZIP forms share the same manifest model.

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
    "title": "Example Book"
  },
  "source": {
    "format": "epub",
    "name": "example.epub",
    "sha256": "<64 lowercase hex characters>",
    "chapter_count": 12
  },
  "chapters": [
    {
      "id": "chapter-1",
      "source_number": 1,
      "path": "chapters/chapter-0001.ssmd.md",
      "title": "Chapter One",
      "source_id": null,
      "href": null,
      "parent_id": null,
      "level": 1,
      "char_count": 1234,
      "sha256": "<64 lowercase hex characters>",
      "diagnostics": []
    }
  ]
}
```

The `chapters` array order is authoritative for book and playback order. Filenames are storage paths, not an ordering contract. Consumers must not sort directory entries to infer chapter order. Each chapter file is an independently valid SSMD 0.9 document.

The source and chapter SHA-256 values detect changed or corrupted data. The loader rejects unsupported schema or SSMD versions rather than treating them as version 1.

## Validation and security

Directory and ZIP bundles are validated before chapter content is returned. Validation includes:

- supported manifest format, schema, and SSMD version;
- normalized relative POSIX paths, with traversal, absolute, Windows-drive, and non-normalized paths rejected;
- duplicate chapter IDs, source numbers, and paths rejected;
- duplicate ZIP members and ZIP symlinks rejected;
- a required `manifest.json`;
- source and chapter SHA-256 verification;
- UTF-8 decoding and standalone SSMD validation of every chapter.

ZIP output uses a fixed timestamp for deterministic archives. Treat bundles from untrusted sources as data and load them through the public validation API rather than reading chapter paths directly.

## Python API

```python
from ssmdconvert import load_book_bundle, validate_book_bundle, write_book_bundle

write_book_bundle(book, "book.ssmdbook")
loaded = load_book_bundle("book.ssmdbook")
validate_book_bundle("book.ssmdbook")
```

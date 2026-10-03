# Book bundle format

A directory ending in `.ssmdbook/` is the canonical editable book workspace; a `.ssmdbook.zip` is an immutable portable artifact. Both use the same versioned manifest model. `load_book_bundle()` and `validate_book_bundle()` remain strict for both formats, including recorded chapter digests. Use the separate workspace API to inspect edited directory chapters whose digests are stale.

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

Use `ssmdconvert book metadata BUNDLE` to inspect stored metadata. For a directory workspace, metadata inspection uses current valid chapter text even when hashes are stale and prints `Workspace: directory`, `Status: clean|dirty`, and `Dirty chapters: N` before the stored metadata. For a ZIP artifact it first performs strict validation and reports `Workspace: no` and `Status: valid`. The optional `--json` form continues to emit a stable `{"metadata": ...}` object; nested values are rendered as indented JSON in human output.

The `chapters` array order is authoritative for book order. Consumers must not sort directory entries or filenames to infer order. Chapter IDs are canonical `chapter-NNNN` identities; each bundle path is derived from the ID. `source_id` and `source_parent_id` preserve EPUB navigation identifiers, while `parent_id` refers to a canonical chapter ID when the parent appears in the book inventory.

Each chapter file is an independently valid SSMD 0.9 document. Source and chapter SHA-256 values detect changed or corrupted data. The source hash is captured by `convert_book()` and stored with the resulting `Book`; writing a bundle does not reread or rehash the EPUB. Loading a bundle retains source name, format, and media type, but cannot provide a local source path.

## Validation and resource limits

The strict `load_book_bundle()` and `validate_book_bundle()` APIs validate directory bundles and ZIPs before returning chapter content. Both require all of the following:

- supported manifest format, schema, and SSMD version;
- normalized relative POSIX paths, with traversal, absolute, Windows-drive, and non-normalized paths rejected;
- duplicate chapter IDs, source numbers, paths, and ZIP member names rejected;
- ZIP symlinks rejected;
- required `manifest.json` and chapter files;
- source and chapter SHA-256 verification;
- UTF-8 decoding and standalone SSMD validation of every chapter.

The loader limits the manifest to 2 MiB, each referenced chapter to 64 MiB uncompressed, the total referenced chapter content to 512 MiB, and ZIP archives to 10,000 members. These bounds limit bundle content processed by the loader; they do not make bundle parsing a sandbox or establish general safety against every resource-exhaustion attack. Treat bundles as data and use the public validation API rather than reading archive paths directly.

Directory readers load only `manifest.json` and its referenced chapter files. Arbitrary workspace-local files do not alter validation; `.readio/` is reserved for downstream local state. It is not part of the portable book format, and pack output never includes it.

ZIP output uses fixed timestamps and deterministic member metadata. Bundle writes build and validate a complete temporary sibling before publication. Existing destinations are refused by default. With `overwrite=True`, a directory bundle replaces the complete prior directory and does not retain stale files.

## Editable workspace maintenance

Editing a referenced chapter file makes a directory workspace dirty because its recorded SHA-256 no longer matches. Workspace loading validates the manifest, paths, UTF-8, and SSMD 0.9, then returns the actual current chapter text and explicit expected/actual digests without changing files. Invalid SSMD and unsafe or missing paths remain errors. ZIP artifacts never use this relaxed digest handling.

Refresh is the explicit source-maintenance operation:

```bash
ssmdconvert book refresh novel.ssmdbook
ssmdconvert book refresh novel.ssmdbook --check
ssmdconvert book pack novel.ssmdbook -o novel.ssmdbook.zip
```

`refresh` validates the chapters and atomically updates manifest chapter digests and `char_count` values. `--check` performs no writes and exits successfully only when the workspace is valid and clean. `pack` reads the current valid chapter contents and writes canonical ZIP members with fresh digests; it does not update the workspace manifest. The ZIP omits `.readio/` and other unreferenced local files. Rendering or inspecting a workspace never refreshes it automatically, and no Readio-specific metadata is stored in `manifest.json`.

## Python API

```python
from ssmdconvert import (
    BookWorkspace,
    WorkspaceChapterStatus,
    load_book_bundle,
    load_book_workspace,
    refresh_book_workspace,
    validate_book_bundle,
    write_book_bundle,
)

write_book_bundle(book, "book.ssmdbook", format="directory")
write_book_bundle(book, "book.ssmdbook.zip", format="zip")
write_book_bundle(book, "replacement.ssmdbook", format="directory", overwrite=True)
loaded = load_book_bundle("book.ssmdbook")
workspace: BookWorkspace = load_book_workspace("book.ssmdbook")
chapter_status: WorkspaceChapterStatus = workspace.chapters[0]
refreshed = refresh_book_workspace("book.ssmdbook")
validate_book_bundle("book.ssmdbook")
```

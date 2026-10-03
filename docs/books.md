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

Inspect stored metadata in either bundle format. The command reports directory workspace status (including dirty chapters) before the metadata; ZIP inputs are strictly validated:

```bash
ssmdconvert book metadata novel.ssmdbook
ssmdconvert book metadata novel.ssmdbook.zip --json
```

## Write and validate bundles

A directory ending in `.ssmdbook/` is the editable canonical workspace. A `.ssmdbook.zip` is an immutable portable artifact. Both use the same manifest and chapter documents; strict bundle loading and validation require the recorded chapter hashes to match:

```bash
ssmdconvert book convert novel.epub -o novel.ssmdbook
ssmdconvert book convert novel.epub -o novel.ssmdbook.zip
ssmdconvert book validate novel.ssmdbook
ssmdconvert book validate novel.ssmdbook.zip --json
```

## Edit, refresh, and pack a workspace

Editing a chapter in a directory workspace makes its manifest digest stale, but does not prevent workspace consumers from using the current chapter text. `ssmdconvert book metadata` reports whether the directory is clean or dirty and counts dirty chapters. Workspace loading does not rewrite the manifest; invalid SSMD, missing files, or unsafe paths remain errors.

Use `refresh` when the edited source is ready to have its manifest hashes and character counts updated. The check form never mutates files and exits non-zero when the workspace is dirty or invalid. To create a portable artifact from the current edited content, use `pack`; this writes a strict ZIP with current chapter text and fresh hashes without modifying the directory workspace.

```bash
ssmdconvert book refresh novel.ssmdbook --check
ssmdconvert book refresh novel.ssmdbook
ssmdconvert book pack novel.ssmdbook -o novel.ssmdbook.zip
```

`.readio/` is reserved for downstream local state. It is ignored by workspace and strict directory validation and is never included in a packed ZIP. Readio can consume edited text through `load_book_workspace()`; reading or rendering does not refresh the source manifest, and no Readio-specific fields are stored there.
The CLI infers formats only from `.ssmdbook` and `.ssmdbook.zip`. Use `--format directory` or `--format zip` for another output name. Existing outputs are refused by default. `--force` replaces the complete directory bundle or ZIP file atomically; directory output does not merge stale files.

## Python API

```python
from ssmdconvert import (
    BookWorkspace,
    WorkspaceChapterStatus,
    convert_book,
    inspect_book,
    load_book_bundle,
    load_book_workspace,
    refresh_book_workspace,
    validate_book_bundle,
    write_book_bundle,
)

inspection = inspect_book("novel.epub")
book = convert_book("novel.epub", chapters="2-20")
write_book_bundle(book, "selected.ssmdbook", format="directory")
loaded = load_book_bundle("selected.ssmdbook")
workspace: BookWorkspace = load_book_workspace("selected.ssmdbook")
workspace_status: WorkspaceChapterStatus = workspace.chapters[0]
refreshed_workspace: BookWorkspace = refresh_book_workspace("selected.ssmdbook")
validate_book_bundle("selected.ssmdbook")
```

`Book.source_sha256` is captured during conversion. Bundle writing persists that captured hash and does not reread the source file. After loading a bundle, source provenance remains available in `Book.source`, but its local `path` is `None`.

`convert_book()` also accepts `language` and `metadata_overrides`. The explicit language wins over source and metadata-file values. The returned `Book.metadata` includes the effective language and portable metadata, and every chapter copies each supported portable SSMD key before SSMD 0.9 validation.

See [Bundle format](bundle-format.md) for manifest fields, canonical paths, integrity checks, and resource limits.

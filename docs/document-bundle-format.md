# `.ssmdoc` bundle format

`.ssmdoc` is a versioned single-document artifact, not a one-chapter
`.ssmdbook`. Its manifest format is `ssmdconvert.document`; the current schema
version is `1` and the stored document is validated as SSMD `0.9`.

A directory bundle is the canonical editable workspace:

```text
story.ssmdoc/
├── manifest.json
└── document.ssmd.md
```

The equivalent portable ZIP has exactly the canonical members `manifest.json`
and `document.ssmd.md` in that order. ZIP timestamps and member metadata are
fixed for deterministic output.

## Manifest

A manifest has this shape (digests abbreviated):

```json
{
  "format": "ssmdconvert.document",
  "schema_version": 1,
  "ssmd_version": "0.9",
  "metadata": {
    "title": "Example",
    "language": "en-US"
  },
  "source": {
    "format": "markdown",
    "media_type": "text/markdown",
    "name": "story.md",
    "sha256": "<64 lowercase hexadecimal characters>"
  },
  "document": {
    "id": "document-0001",
    "path": "document.ssmd.md",
    "char_count": 42,
    "sha256": "<64 lowercase hexadecimal characters>"
  }
}
```

`metadata` contains effective document metadata without the reserved
`ssmd_version` key. `source.sha256` is the hash of the original input bytes,
captured during conversion; bundle publication does not reread the source.
`document.sha256` hashes the exact stored UTF-8 SSMD bytes, and `char_count` is
the Python character count. The canonical document identity and path are fixed
as `document-0001` and `document.ssmd.md`.

An optional `speech_semantics` object stores speech-provenance fields when a
speech operation has materialized decisions. Its source digest must match
`source.sha256`. Normal document conversion does not require this field.

Manifest JSON is UTF-8, strict JSON, and serialized deterministically. Metadata
must be JSON-compatible; NaN and Infinity are rejected.

## Strict bundles and editable workspaces

`load_document_bundle()` and `validate_document_bundle()` strictly verify either
a directory or ZIP: manifest fields and versions, canonical paths, source digest
shape, document digest, UTF-8, and SSMD 0.9 validity. A stale document digest
makes a directory invalid as a strict bundle.

`load_document_workspace()` is the relaxed directory-workspace API. It still
validates the manifest and safely reads and validates the current document, but
returns that text when its digest differs and reports the expected digest,
actual digest, and `dirty` state. It does not change files. ZIP artifacts never
use relaxed digest handling.

Use `ssmdconvert document refresh WORKSPACE` as the explicit operation that
updates the manifest digest and character count after editing. `--check` is
read-only and reports a dirty workspace as a failure. `document pack` creates a
strict ZIP using current valid text and fresh hashes without refreshing or
otherwise modifying the source workspace.

## Path and resource safety

Bundle paths must be normalized relative POSIX paths. Absolute paths, traversal,
`.`/`..` components, Windows drive paths, backslashes, NUL bytes, symlink
escapes, duplicate ZIP names, and ZIP symlinks are rejected. The document path
must equal the canonical path shown above. Directory reads are limited to
manifest-referenced files; unrelated files do not become bundle content.

The manifest is limited to 2 MiB, the document to 64 MiB, and a ZIP to 10,000
members. These bounds limit bundle content processed by the loader; they do not
make parsing a sandbox or guarantee safety against every resource-exhaustion
attack. Treat bundles as data and use the public validation API.

Writes build and validate a complete temporary artifact before publication.
Existing destinations are refused by default. With overwrite enabled, a
complete directory workspace is replaced rather than merged, and ZIP output is
published atomically. The optional workspace-local `.readio/` directory is
reserved for downstream state: it is not referenced by the manifest and is
never included in a packed ZIP.

See [Single-document SSMD workspaces](documents.md) for CLI usage and the public
Python API.

# Book manifest format (implementation detail)

This page documents the existing book manifest carried inside a canonical
bundle. It is an implementation detail; users manage either source kind through
the common lifecycle described in [Bundle workspaces](bundles.md).

The book manifest keeps its existing format identifier and schema version:

```text
format:         ssmdconvert.book
schema_version: 1
ssmd_version:   0.9
```

It stores JSON-compatible metadata, source provenance, and an ordered `chapters`
array. Each chapter entry identifies the stable chapter ID, original source
number, relative SSMD path, title, navigation references, character count, and
SHA-256 digest. The array order is authoritative; directory filenames are not
used to infer reading order. Chapter documents remain independently valid SSMD
0.9.

An optional `speech_semantics` object records speech-freeze provenance. Existing
metadata fields and schema version are unchanged by the unified outer bundle
name.

## Validation and workspace behavior

Strict loading and validation check the manifest format and versions, normalized
relative paths, duplicate IDs and members, UTF-8, SSMD validity, and source and
chapter digests. ZIP symlinks and unsafe paths are rejected. The loader applies
bounds to manifest size, chapter sizes, total referenced content, and archive
member count.

An editable directory can be loaded as a workspace when chapter text is valid
but its recorded digest is stale. The workspace reports dirty state and current
content without rewriting the manifest. `bundle refresh` is the explicit
operation to update digests and character counts. `bundle pack` writes a strict
archive from current valid content without changing the directory workspace.
Unreferenced local files are not portable bundle members.

ZIP output uses fixed timestamps and deterministic member metadata. Forced
publication replaces the complete directory rather than merging stale files.
The separate document-manifest layout is described in [Document manifest format](document-bundle-format.md).

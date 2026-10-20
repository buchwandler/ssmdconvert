# Document manifest format (implementation detail)

This page documents the existing single-document manifest carried inside a
canonical bundle. It is an implementation detail; users manage either source
kind through the common lifecycle described in [Bundle workspaces](bundles.md).

The document manifest keeps its existing format identifier and schema version:

```text
format:         ssmdconvert.document
schema_version: 1
ssmd_version:   0.9
```

The manifest contains JSON-compatible metadata, source provenance, and one
canonical document entry with ID `document-0001`, path `document.ssmd.md`,
character count, and content digest. Manifest JSON is UTF-8 and strict JSON;
metadata must be JSON-compatible. The source digest is captured during
conversion, and publication does not reread the source.

## Validation and workspace behavior

Strict loading checks manifest fields and versions, canonical paths, source and
document digest shape and content, UTF-8, and SSMD 0.9 validity. ZIP duplicate
members, symlinks, unsafe paths, oversized content, and excessive member counts
are rejected.

An editable directory workspace can expose valid current SSMD when its recorded
digest is stale. It reports expected and actual digests without modifying the
manifest. `bundle refresh` explicitly updates the digest and character count;
`bundle pack` writes a strict archive from current valid text without changing
the source workspace. Unreferenced local files are not portable members.

The existing manifest format, schema version, and document path remain
unchanged by the unified outer artifact name. See [Bundle workspaces](bundles.md)
for the common user-facing lifecycle.

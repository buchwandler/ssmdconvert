# Single-document SSMD workspaces

Use the `document` command group to place one rendered SSMD document in a managed
`.ssmdoc` workspace. This is separate from the existing top-level `convert`
command: `ssmdconvert convert SOURCE` continues to write a standalone `.ssmd`
file, and `book convert` continues to create an `.ssmdbook`.

## Convert a document

```bash
ssmdconvert document convert story.ssmd.md
# creates story.ssmdoc/

ssmdconvert document convert notes.md -o notes.ssmdoc.zip
ssmdconvert document convert report.docx -o reviewed.ssmdoc --language en-US
```

When output is omitted, the workspace is created beside the source. `.ssmdoc`
selects a directory and `.ssmdoc.zip` selects a ZIP artifact; other output names
require `--format directory` or `--format zip`. Existing destinations are
refused unless `--force` is supplied. Forced directory writes replace the whole
workspace rather than merging files.

Already-valid `.ssmd` and `.ssmd.md` input is validated as SSMD 0.9. With no
metadata-changing options, its exact UTF-8 document bytes and author-owned SSMD
annotations are preserved. Explicit metadata or sequence-policy overrides use
the normal conversion pipeline. Ordinary non-SSMD inputs use the same adapters
as `ssmdconvert convert`. `document convert` does not automatically freeze
speech decisions; use the speech commands when write-back is wanted.

## Inspect and maintain workspaces

```bash
ssmdconvert document inspect story.ssmd.md [--json]
ssmdconvert document validate story.ssmdoc [--json]
ssmdconvert document metadata story.ssmdoc [--json]
ssmdconvert document refresh story.ssmdoc --check
ssmdconvert document refresh story.ssmdoc
ssmdconvert document pack story.ssmdoc -o story.ssmdoc.zip
```

A `.ssmdoc/` directory is editable. Editing `document.ssmd.md` makes its
recorded digest stale, but workspace loading uses the current valid SSMD and
reports the workspace as dirty. `document metadata` shows this status.
`refresh --check` never writes and exits non-zero for a dirty workspace;
`refresh` explicitly updates the manifest digest and character count. `pack`
creates a strict ZIP using the current valid text and fresh hashes without
modifying the source workspace. The manifest and its referenced canonical document define source truth. Unreferenced local files—including downstream stage directories—are not source members; workspace readers and validators follow the manifest, while pack/export emits only portable bundle members and leaves unrelated local files untouched.

Strict bundle loading, validation, and ZIP handling verify the manifest, paths,
SSMD 0.9 content, size bounds, and SHA-256 digests. See [Document bundle
format](document-bundle-format.md) for the manifest and security rules.

## Analysis and speech

A document bundle is a single analysis section identified as `document-0001`.
It can be passed directly to the generic report, TXT, context, and speech audit
commands. For example:

```bash
ssmdconvert report story.ssmdoc
ssmdconvert report story.ssmdoc.zip --format json
ssmdconvert txt story.ssmdoc -o story.txt
ssmdconvert speech audit story.ssmdoc --json
ssmdconvert speech freeze story.ssmdoc -o frozen.ssmdoc
ssmdconvert speech freeze story.ssmdoc -o frozen.ssmdoc.zip
```

Speech write-back checks that the current document still matches the analyzed
content before publishing. It writes a new document bundle with speech
provenance and never mutates the source workspace. Existing destinations still
require `--force`.

## Python API

The rendered artifact (`SsmdDocument`) is distinct from the source-neutral
`Document` model returned by `convert_document()`. The artifact builder captures
source provenance, while bundle publication is explicit:

```python
from ssmdconvert import (
    DocumentWorkspace,
    SsmdDocument,
    WorkspaceDocumentStatus,
    convert_document_artifact,
    load_document_bundle,
    load_document_workspace,
    refresh_document_workspace,
    validate_document_bundle,
    write_document_bundle,
)

artifact: SsmdDocument = convert_document_artifact("story.ssmd.md")
write_document_bundle(artifact, "story.ssmdoc", format="directory")
loaded: SsmdDocument = load_document_bundle("story.ssmdoc")
workspace: DocumentWorkspace = load_document_workspace("story.ssmdoc")
status: WorkspaceDocumentStatus = workspace.status
refreshed = refresh_document_workspace("story.ssmdoc")
validate_document_bundle("story.ssmdoc")
```

The strict loader accepts a directory bundle or ZIP. The workspace loader only
accepts a directory and returns valid current text even if its stored document
digest is stale. Neither load operation refreshes the manifest.

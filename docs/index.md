# SSMDConvert User Guide

SSMDConvert converts local documents and EPUB books into SSMD 0.9, then provides
analysis, reporting, plain-text projection, and safe speech write-back. The common
bundle lifecycle stores books and documents in canonical directory workspaces or
read-only ZIP archives.

## Quick start

```bash
ssmdconvert bundle inspect novel.epub --json
ssmdconvert bundle convert novel.epub --chapters 2-20 -o novel.ssmd-bundle
ssmdconvert bundle convert notes.md -o notes.ssmd-bundle
ssmdconvert bundle validate novel.ssmd-bundle
```

Use `ssmdconvert bundle metadata`, `refresh`, `pack`, and `validate` to manage an
editable workspace and its archive. The manifest identifies the content kind;
see [Bundle workspaces](bundles.md) for the complete lifecycle.

## Ownership boundary

SSMDConvert owns source ingestion, SSMD semantics, chapter identity, analysis,
reporting, text projection, and safe write-back. It uses the public `ttsready`
Python API for source-neutral speech preparation and QA; it does not rely on a
separate downstream CLI.

```{toctree}
:maxdepth: 2
:caption: User guide

installation
bundles
usage
books
documents
analysis-workflows
report
context
txt
speech-audit
speech-annotations
freeze
analysis-cache
migration-from-ttsready-cli
api
bundle-format
document-bundle-format
changelog
```

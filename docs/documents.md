# Document source conversion

Supported document sources and existing SSMD files use the same bundle
conversion command as EPUB input:

```bash
ssmdconvert bundle inspect notes.md --json
ssmdconvert bundle convert notes.md -o notes.ssmd-bundle
ssmdconvert bundle convert report.docx -o reviewed.ssmd-bundle --language en-US
ssmdconvert bundle convert reviewed.ssmd.md -o reviewed.ssmd-bundle
```

PDF and DOCX conversion require the matching optional extras. A valid SSMD input
is preserved byte-for-byte when no metadata or sequence-policy override is
requested. Ordinary source formats use the installed input adapters. Document
bundles expose one analysis section, `document-0001`.

The resulting directory or ZIP uses the shared bundle lifecycle for validation,
metadata, refresh, and packing. See [Bundle workspaces](bundles.md) for artifact
and dirty-workspace behavior, and [analysis workflows](analysis-workflows.md)
for generic reports and speech operations.

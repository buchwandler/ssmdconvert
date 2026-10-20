# EPUB source conversion

EPUB is the book source format. Use the shared bundle commands to inspect the
navigation inventory and convert all or selected chapters:

```bash
ssmdconvert bundle inspect novel.epub --json
ssmdconvert bundle convert novel.epub --chapters 1 -o chapter-one.ssmd-bundle
ssmdconvert bundle convert novel.epub --chapters 1,3-5 -o selected.ssmd-bundle
ssmdconvert bundle convert novel.epub --chapters 2-20 -o selected.ssmd-bundle
```

Selectors use original one-based source chapter numbers. They refer to the
complete source inventory even when the output contains a subset. Selected
chapters remain in source order; duplicate numbers do not duplicate chapters.
Missing chapters, zero or negative numbers, reversed ranges, and malformed
tokens are rejected.

Use `--language` for the base language and `--metadata-file` for supported
bibliographic and SSMD metadata. Source metadata is overridden by the file, then
explicit command-line values. Inline SSMD language spans remain authoritative.

Book conversion freezes eligible automatic speech decisions by default. Freeze
requires a resolvable language for each text run. Use
`--speech-semantics preserve` for structural-only conversion. Speech decisions
preserve visible text and author-owned annotations. `--spacy off|auto|sm|md|lg|trf`
selects local enrichment; models are never downloaded automatically.

The resulting workspace uses the common bundle lifecycle for validation,
metadata, refresh, and packing. See [Bundle workspaces](bundles.md) for dirty
chapter behavior and [analysis workflows](analysis-workflows.md) for reports and
speech details.

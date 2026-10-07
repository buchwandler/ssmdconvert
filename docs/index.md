# ssmdconvert Documentation

`ssmdconvert` converts common local documents and EPUB books into SSMD 0.9. The
base package supports text, Markdown, HTML, EPUB, SSMD analysis, and speech
audit/annotation. PDF and DOCX adapters are optional extras; the public `ttsready`
preparation API is a core dependency.

Convert a document:

```bash
ssmdconvert convert manuscript.md -o manuscript.ssmd
```

Inspect EPUB chapters or create a chapter-aware bundle:

```bash
ssmdconvert book inspect novel.epub --json
ssmdconvert book convert novel.epub -o novel.ssmdbook
ssmdconvert book validate novel.ssmdbook
```

The CLI refuses to overwrite existing output unless `--force` is supplied. Output writes are atomic, and forced directory-bundle writes replace the complete prior bundle.

## Ownership boundary

`ssmdconvert` owns source ingestion, canonical SSMD conversion, chapter identity,
`.ssmdbook` integrity, SSMD reports/context/TXT projection, and safe speech
write-back. `ttsready` supplies generic preparation and QA through its public Python
API; it is not a user-facing CLI or a source of SSMD-specific storage semantics.
`ssmdconvert` uses one analysis pipeline for reports and speech workflows and never
mutates a directory workspace in place.

```{toctree}
:maxdepth: 2
:caption: User guide

installation
usage
analysis-workflows
report
context
txt
speech-audit
speech-annotations
freeze
analysis-cache
migration-from-ttsready-cli
books
bundle-format
api
changelog
```

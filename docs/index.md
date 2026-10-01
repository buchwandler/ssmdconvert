# ssmdconvert Documentation

`ssmdconvert` converts common local documents and EPUB books into SSMD 0.9. The base package supports text, Markdown, HTML, EPUB, and SSMD. PDF, DOCX, and speech-preparation APIs are optional extras.

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

```{toctree}
:maxdepth: 2
:caption: User guide

installation
usage
books
bundle-format
api
changelog
```

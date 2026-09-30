# CLI usage

## Convert a document

```bash
ssmdconvert convert INPUT [-o OUTPUT]
```

Examples:

```bash
ssmdconvert convert manuscript.txt -o manuscript.ssmd
ssmdconvert convert novel.md -o novel.ssmd
ssmdconvert convert page.html -o page.ssmd
ssmdconvert convert book.epub -o book.ssmd
ssmdconvert convert report.pdf -o report.ssmd
ssmdconvert convert manuscript.docx -o manuscript.ssmd
ssmdconvert convert existing.ssmd -o normalized.ssmd
```

PDF and DOCX require the `[pdf]` and `[docx]` extras. When `-o` is omitted, output is written next to the source using `source.with_suffix(".ssmd")`.

Optional metadata can be supplied during conversion:

```bash
ssmdconvert convert manuscript.txt \
  --title "Example" \
  --author "A. Writer" \
  --language en
```

Core conversion is local and does not send content to JEV.

## Inspect a source

Inspect the local adapter and normalized sections without writing output:

```bash
ssmdconvert inspect book.epub
ssmdconvert inspect book.epub --json
```

Inspection reports the selected adapter, normalized section titles, character counts, and source references.

## Supported inputs

| Format | Install | Notes |
|---|---|---|
| TXT | core | Plain-text section splitting |
| Markdown | core | Normalized into source-neutral sections |
| HTML | core | Converted to normalized Markdown and SSMD |
| EPUB | core | Chapter extraction delegates to `epub2text` |
| SSMD | core | Parsed and re-emitted as SSMD 0.9 |
| PDF | `[pdf]` | `pypdf` text extraction; no OCR for scanned pages |
| DOCX | `[docx]` | Extracts paragraphs and headings; complex floating layout is ignored |

Chapter-aware EPUB conversion and bundle commands are described in [Books](books.md).

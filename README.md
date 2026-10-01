# ssmdconvert

**Convert documents and EPUB books into Speech Synthesis Markdown (SSMD).**

`ssmdconvert` is a source-neutral ingestion layer for text-to-speech and audiobook workflows. It converts common document formats into SSMD 0.9 and can split EPUB books into standalone SSMD chapters. Optional semantic enrichment adds speaker or voice decisions.

Core conversion is local and does not require JEV or Readio. JEV-backed enrichment is opt-in and requires an explicit `--yes-cloud` acknowledgement.

Speech preparation and Unicode QC are also opt-in (`--speech audit` or `--speech annotate`); the default remains unchanged. Annotation uses SSMD `sub` to keep written text visible, reports unsafe or suspicious mappings instead of guessing, and runs locally without JEV or cloud calls. See [CLI usage](docs/usage.md#opt-in-speech-preparation-and-qc) for language, glossary, strictness, and JSON report options.

## Install

```bash
python -m pip install ssmdconvert
```

Optional format support:

```bash
python -m pip install "ssmdconvert[pdf]"
python -m pip install "ssmdconvert[docx]"
```

Optional JEV enrichment:

```bash
python -m pip install "ssmdconvert[jev]"
```

Install all published extras:

```bash
python -m pip install "ssmdconvert[all]"
```

Python 3.10 or newer is required.

## Quick start

Convert a text or document file to SSMD:

```bash
ssmdconvert convert manuscript.txt -o manuscript.ssmd
ssmdconvert convert novel.md -o novel.ssmd
ssmdconvert convert page.html -o page.ssmd
ssmdconvert convert book.epub -o book.ssmd
```

PDF and DOCX use optional extras:

```bash
ssmdconvert convert report.pdf -o report.ssmd
ssmdconvert convert manuscript.docx -o manuscript.ssmd
```

Inspect a source without writing output:

```bash
ssmdconvert inspect book.epub
```

## EPUB chapters and book bundles

Normal EPUB conversion remains a single combined SSMD document:

```bash
ssmdconvert convert novel.epub -o novel.ssmd
```

For chapter-aware workflows, inspect the EPUB chapter inventory:

```bash
ssmdconvert book chapters novel.epub
ssmdconvert book chapters novel.epub --json
```

Create an editable directory bundle with one standalone SSMD document per selected chapter:

```bash
ssmdconvert book novel.epub -o novel.ssmdbook
ssmdconvert book novel.epub --chapters 2-20 -o selected.ssmdbook
```

Create a portable ZIP bundle:

```bash
ssmdconvert book novel.epub -o novel.ssmdbook.zip
```

Validate either form:

```bash
ssmdconvert book validate novel.ssmdbook
ssmdconvert book validate novel.ssmdbook.zip
```

Chapter selectors use original 1-based source numbers. They accept a single number, a range, a comma-separated list, or a mixture such as `1,3-5`. Selected chapters remain in source order. Bundle playback order comes from the manifest chapter array, not filenames.

Speech preparation remains opt-in for books too. For selected chapters, `--speech annotate` adds safe `sub` aliases and writes a sibling `<bundle-name>.speech-report.json` sidecar; `--speech audit` reports without changing chapter SSMD. Speech reports are not added to the version-1 bundle manifest. See [Books](docs/books.md#speech-preparation-and-reports) for JSON/TOML glossary and strict-QC options.

## Python API

Convert a normal document:

```python
from ssmdconvert import Converter

result = Converter().convert("book.epub")
print(result.ssmd)
```

Work with an EPUB as a chapter-aware book:

```python
from ssmdconvert import (
    convert_book,
    inspect_book,
    load_book_bundle,
    validate_book_bundle,
    write_book_bundle,
)

inspection = inspect_book("novel.epub")
book = convert_book("novel.epub", chapters="2-20")
write_book_bundle(book, "selected.ssmdbook")
loaded = load_book_bundle("selected.ssmdbook")
validate_book_bundle("selected.ssmdbook")
```

## Supported inputs

| Input      | Install             | Notes                                                    |
| ---------- | ------------------- | -------------------------------------------------------- |
| Plain text | core                | Local conversion                                         |
| Markdown   | core                | Normalized into source-neutral sections                  |
| HTML       | core                | Converted to normalized Markdown and SSMD                |
| EPUB       | core                | Extraction uses `epub2text`                              |
| SSMD       | core                | Parsed and re-emitted as SSMD 0.9                        |
| PDF        | `ssmdconvert[pdf]`  | Text extraction only, no OCR                             |
| DOCX       | `ssmdconvert[docx]` | Paragraphs and headings; complex layout is not preserved |

## Optional semantic enrichment

JEV-backed operations are separate from core conversion and require explicit cloud acknowledgement:

```bash
ssmdconvert enrich book.ssmd \
  -o book.enriched.ssmd \
  --speakers \
  --yes-cloud
```

Speaker attribution first uses deterministic local discovery. Ambiguous dialogue may then be judged against the finite discovered cast by JEV. Voice casting uses a finite caller-supplied inventory. See [Enrichment](docs/enrichment.md) for details.

## Documentation

The [documentation index](docs/index.md) links to installation, CLI usage, EPUB books, bundle format, enrichment, and the Python API.

## Limitations

- EPUB extraction follows `epub2text`'s document model; it is not a browser layout engine.
- PDF support uses `pypdf` text extraction and does not OCR scanned pages.
- DOCX support extracts paragraphs and headings; complex floating layout is ignored.
- Semantic enrichment is intended for prose-oriented inputs and is separate from deterministic local conversion.

## License

Apache-2.0. See [LICENSE](LICENSE).

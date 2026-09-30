# ssmdconvert

**Convert documents and books into SSMD, with optional semantic enrichment.**

`ssmdconvert` is intended to be the ingestion layer in front of Readio:

```text
TXT / Markdown / HTML / EPUB / PDF / DOCX / SSMD
                      |
                      v
                 ssmdconvert
                      |
            optional enrichers
        speakers / voices / SFX via JEV
                      |
                      v
                    SSMD
                      |
                      v
                   Readio
```

The core conversion path is local and does **not** require JEV or Readio. Readio can
therefore depend on `ssmdconvert` without creating a dependency cycle.

## Install

```bash
pip install ssmdconvert
```

Optional inputs and enrichment:

```bash
pip install "ssmdconvert[pdf]"
pip install "ssmdconvert[docx]"
pip install "ssmdconvert[jev]"
pip install "ssmdconvert[jev,sfx]"
```

The repository uses a flat package layout (`ssmdconvert/`, no `src/`) and dynamic
versions from Git tags via `setuptools-scm`.

## Local conversion

```bash
ssmdconvert convert manuscript.txt -o manuscript.ssmd
ssmdconvert convert novel.md -o novel.ssmd
ssmdconvert convert book.epub -o book.ssmd
ssmdconvert convert page.html -o page.ssmd
ssmdconvert convert report.pdf -o report.ssmd       # requires [pdf]
ssmdconvert convert manuscript.docx -o manuscript.ssmd  # requires [docx]
```

Inspect without writing:

```bash
ssmdconvert inspect book.epub
```

Python:

```python
from ssmdconvert import Converter

result = Converter().convert("book.epub")
print(result.ssmd)
```

## EPUB chapters and book bundles

EPUB extraction and chapter semantics are provided by the public `epub2text` chapter API. The
existing conversion path still returns one combined SSMD document, so current `convert()` and
`Converter.convert()` callers do not need to change:

```bash
ssmdconvert convert novel.epub -o novel.ssmd
```

To inspect the source chapter inventory, create one standalone SSMD document per chapter, or
validate a saved bundle:

```bash
ssmdconvert book chapters novel.epub
ssmdconvert book chapters novel.epub --json
ssmdconvert book novel.epub -o novel.ssmdbook
ssmdconvert book novel.epub --chapters 2-20 -o selected.ssmdbook
ssmdconvert book novel.epub -o novel.ssmdbook.zip
ssmdconvert book validate novel.ssmdbook
```

Chapter selectors use the original 1-based source numbers. Selectors can be a single number, a
range, a comma-separated list, or a mixture such as `1,3-5`; selected chapters remain in source
order. Each generated chapter is independently valid SSMD 0.9 and includes a spoken H1 title.
Chapter metadata retains source provenance and navigation hierarchy where available.

A `.ssmdbook` directory is the editable form. Each chapter is a regular SSMD file that can be
revised in place. A `.zip` output is the portable form. Both formats use the same
`manifest.json`; its chapter array is authoritative for playback and book order, not filenames,
titles, or directory enumeration. Downstream tools can consume the SSMD chapter files without
requiring Readio.

The Python API exposes the same operations:

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

The default adapters normalize sources into a small source-neutral document model and
then render SSMD 0.9. Existing `.ssmd` is parsed and re-emitted as SSMD 0.9 rather than
being routed through an EPUB- or Readio-specific model.

## Optional JEV enrichment

Cloud operations are opt-in and require `--yes-cloud`:

```bash
ssmdconvert enrich book.ssmd -o book.enriched.ssmd \
  --speakers --yes-cloud
```

Speaker attribution first uses deterministic local attribution such as `Alice said, “...”`; ambiguous dialogue can then be judged against the finite discovered cast by JEV.

Voice casting uses a finite inventory and never asks JEV to invent provider IDs:

```bash
ssmdconvert enrich book.ssmd -o book.voiced.ssmd \
  --speakers \
  --voices voices.json \
  --provider kokoro \
  --yes-cloud
```

Example `voices.json`:

```json
{
  "af_bella": "English female voice; warm and conversational",
  "am_adam": "English male voice; neutral adult narrator"
}
```

SFX authoring is also optional and uses SFXRender's advertised authoring catalog. The
MVP asks JEV to select only from catalog effects and materializes a catalog-provided,
validated example URI; it does not invent new `sfx:` effect names or parameters:

```bash
ssmdconvert enrich book.ssmd -o book.fx.ssmd \
  --sfx --max-sfx 8 --yes-cloud
```

Use `--report decisions.json` to persist speaker/SFX/voice decisions and confidence data.

## Library boundary

- `ssmd`: syntax, parser, validation, rendering semantics.
- `ssmdconvert`: supported input -> SSMD, plus optional semantic enrichment.
- `pyjev`: optional cloud judgment backend.
- `sfxrender`: semantic `sfx:` URI -> PCM.
- `readio`: SSMD -> speech/media planning, synthesis, composition.
- `ttsforge`: audiobook-oriented workflow/build/export frontend.

## MVP limitations

- EPUB chapter extraction delegates to `epub2text`; it is not a full browser layout engine.
  becomes one section.
- PDF extraction uses `pypdf` text extraction and cannot OCR scanned pages.
- DOCX support extracts paragraphs/headings; complex floating layout is ignored.
- JEV enrichers are intended for freshly converted prose. A future release should move
  enrichment onto the SSMD structural AST for arbitrary pre-annotated documents.

## License

MIT

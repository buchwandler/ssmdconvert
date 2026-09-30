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

- EPUB conversion is intentionally dependency-light and implements the normal EPUB
  container/OPF/spine path. It is not a replacement for a full browser layout engine.
- TXT chapter detection is heuristic; a plain file without recognizable chapter headings
  becomes one section.
- PDF extraction uses `pypdf` text extraction and cannot OCR scanned pages.
- DOCX support extracts paragraphs/headings; complex floating layout is ignored.
- JEV enrichers are intended for freshly converted prose. A future release should move
  enrichment onto the SSMD structural AST for arbitrary pre-annotated documents.

## License

MIT

# ssmdconvert

`ssmdconvert` is a deterministic, local ingestion library and CLI that converts common documents and EPUB books into valid SSMD 0.9. It supports combined document conversion and ordered, standalone SSMD chapters in directory or ZIP book bundles.

## SSMD ownership boundary

`ssmdconvert` owns source ingestion, canonical SSMD conversion, chapter identity, and `.ssmdbook` integrity. `ttsready` is a separate downstream workflow that reads canonical SSMD, analyzes and reviews speech semantics, and writes approved changes into SSMD. Applications exchange reviewed content through SSMD documents or book bundles, not through a runtime dependency on `ttsready`. Existing optional `ssmdconvert.speech` APIs remain available for compatibility and are not required by `ttsready`.

## Install

```bash
python -m pip install ssmdconvert
```

The base install supports text, Markdown, HTML, EPUB, and SSMD. Optional adapters and local speech-preparation APIs are installed separately:

```bash
python -m pip install "ssmdconvert[pdf]"
python -m pip install "ssmdconvert[docx]"
python -m pip install "ssmdconvert[speech]"
python -m pip install "ssmdconvert[all]"
```

Python 3.10 or newer is required. Conversion and EPUB extraction run locally. Speech preparation is an optional API and is not part of normal conversion.

## Convert a document

```bash
ssmdconvert convert manuscript.txt -o manuscript.ssmd
ssmdconvert convert novel.md -o novel.ssmd
ssmdconvert inspect manuscript.md --json
```

PDF and DOCX conversion require their corresponding optional extras. Writes are atomic, refuse existing destinations by default, and support `--force` to replace an existing output. The input file is never a valid output destination, even with `--force`.

Both `convert` and `book convert` accept `--sequence-fallback-mode spell|preserve`. New conversions default to `preserve`; `spell` remains available explicitly. The effective value is stored in standalone SSMD front matter, book manifest metadata, and each generated chapter. The writer default does not change how consumers interpret legacy files or bundles that omit the field.


Use `--metadata-file PATH` on either conversion command for nested SSMD metadata and bibliographic overrides from a UTF-8 YAML mapping. Source metadata is overridden by the file, explicit CLI values override the file, and the effective sequence fallback option is applied last.

```yaml
language: de-DE
voice_defaults:
  narrator:
    rate: slow
```

```bash
ssmdconvert convert manuscript.md -o manuscript.ssmd
ssmdconvert book convert novel.epub --language de-DE --metadata-file book-metadata.yaml -o novel.ssmdbook
```

## Convert an EPUB book

```bash
ssmdconvert book inspect novel.epub --json
ssmdconvert book convert novel.epub --chapters 2-20 -l de-DE -o selected.ssmdbook
ssmdconvert book convert novel.epub -o novel.ssmdbook.zip
ssmdconvert book validate novel.ssmdbook.zip --json
ssmdconvert book metadata novel.ssmdbook.zip
ssmdconvert book metadata novel.ssmdbook.zip --json
```

Chapter selectors use original 1-based source numbers. Selected chapters remain in source order. Use `--format directory` or `--format zip` when the output name does not end in `.ssmdbook` or `.ssmdbook.zip`. Bundle destinations are not overwritten unless `--force` is given; forced directory writes replace the complete prior directory rather than merging files.

## Python API

```python
from ssmdconvert import (
    convert,
    convert_content,
    convert_book,
    inspect_book,
    load_book_bundle,
    validate_book_bundle,
    write_book_bundle,
)

result = convert("manuscript.md")
content = convert_content(
    "# Notes\n\nRead this.", input_format="markdown", source_name="notes.md"
)
inspection = inspect_book("novel.epub")
book = convert_book(
    "novel.epub",
    chapters="2-20",
    language="de-DE",
    metadata_overrides={"voice_defaults": {"narrator": {"rate": "slow"}}},
)
write_book_bundle(book, "selected.ssmdbook", format="directory")
loaded = load_book_bundle("selected.ssmdbook")
validate_book_bundle("selected.ssmdbook")
```

See the [documentation](docs/index.md) for supported inputs, CLI options, book models, and bundle validation details.

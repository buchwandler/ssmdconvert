# ssmdconvert Documentation

`ssmdconvert` converts documents and EPUB books into SSMD 0.9. Core conversion and inspection run locally. Optional `spokenform` speech preparation and Unicode QC are opt-in and remain local; JEV semantic enrichment is separate and requires explicit acknowledgement before selected content is sent to a configured backend.

Install the core package with:

```bash
python -m pip install ssmdconvert
```

Convert a document locally:

```bash
ssmdconvert convert manuscript.txt -o manuscript.ssmd
```

For chapter-aware EPUB workflows, inspect a source and write an ordered book bundle:

```bash
ssmdconvert book chapters novel.epub
ssmdconvert book novel.epub -o novel.ssmdbook
```

Python 3.10 or newer is supported.

```{toctree}
:maxdepth: 2
:caption: User guide

installation
usage
books
bundle-format
enrichment
api
changelog
```

# Python API

The core names documented here are exported from `ssmdconvert` and listed in `ssmdconvert.__all__`.

## Conversion

```{autofunction} ssmdconvert.convert

```

```{autoclass} ssmdconvert.Converter
:members:
```

```{autoclass} ssmdconvert.ConversionResult
:members:
```

`Converter.convert()` returns one combined SSMD document. Input paths ending in `.ssmd` or `.ssmd.md` are recognized case-insensitively and parsed as SSMD before being rendered.

`Converter.convert()`, the convenience `convert()`, and `convert_content()` accept `sequence_fallback_mode`, which may be `spell` or `preserve`. New conversions default to `preserve`; the selected value is written to generated SSMD front matter and normalized document metadata. This writer default does not change how consumers handle legacy SSMD documents where the field is absent.

```python
result = convert("manuscript.md", sequence_fallback_mode="preserve")
```

`metadata_overrides` accepts a mapping of supported portable SSMD and bibliographic values in the Python conversion APIs. The CLI counterpart is `--metadata-file PATH`, a UTF-8 YAML mapping. Values merge in source, file, then explicit CLI order; the effective `sequence_fallback_mode` is applied last. For example:

```python
result = convert(
    "manuscript.md",
    metadata_overrides={"voice_defaults": {"narrator": {"rate": "slow"}}},
)
```

## Source-neutral models

```{autoclass} ssmdconvert.SourceInfo
:members:
```

```{autoclass} ssmdconvert.Section
:members:
```

```{autoclass} ssmdconvert.Document
:members:
```

`SourceInfo.path` is populated when the source is locally available. Bundle-loaded provenance keeps its source name, format, and media type, but has no local path.

## Books and chapters

```{autoclass} ssmdconvert.Book
:members:
```

```{autoclass} ssmdconvert.BookChapter
:members:
```

```{autoclass} ssmdconvert.BookInspection
:members:
```

```{autoclass} ssmdconvert.BookInspectionChapter
:members:
```

```{autofunction} ssmdconvert.inspect_book

```

```{autofunction} ssmdconvert.convert_book

```

`BookChapter.id` is the canonical chapter identity. `source_id` and `source_parent_id` preserve source navigation identifiers; `parent_id` refers to the canonical parent chapter ID when present in the inventory. `Book.source_sha256` is captured during conversion.

`convert_book()` defaults to `sequence_fallback_mode=preserve`, accepts an optional `language` override and `metadata_overrides` mapping, and records effective metadata in `Book.metadata` and portable keys in each generated chapter. Source language is retained by default; absent source language stays absent unless supplied. For example:

```python
book = convert_book(
    "novel.epub",
    language="de-DE",
    metadata_overrides={"voice_defaults": {"narrator": {"rate": "slow"}}},
)
```

## Bundles

```{autofunction} ssmdconvert.write_book_bundle

```

```{autofunction} ssmdconvert.load_book_bundle

```

```{autofunction} ssmdconvert.validate_book_bundle

```

The writer requires `format="directory"` or `format="zip"`. Existing destinations are refused unless `overwrite=True` is supplied. See [Bundle format](bundle-format.md) for atomic replacement, validation, and resource limits.

## Errors

```{autoclass} ssmdconvert.SSMDConvertError

```

```{autoclass} ssmdconvert.UnsupportedInputError

```

```{autoclass} ssmdconvert.MissingDependencyError

```

```{autoclass} ssmdconvert.BookError

```

```{autoclass} ssmdconvert.UnsupportedBookSourceError

```

```{autoclass} ssmdconvert.ChapterSelectionError

```

```{autoclass} ssmdconvert.BookBundleError

```

```{autoclass} ssmdconvert.BookBundleValidationError

```

## SSMD analysis and speech workflows

SSMD report, context lookup, TXT projection, speech audit, annotation, and freeze are
user-facing CLI workflows. The former optional `SpeechPreparationOptions` /
`prepare_ssmd_for_speech` engine and its direct `spokenform` runtime dependency have
been removed; `ttsready>=0.2,<0.3` supplies generic preparation through its public
Python API.

See [SSMD analysis and speech workflows](analysis-workflows.md) for command usage,
cache ownership, source mapping, safe write-back, and migration from the removed
`ttsready` CLI.

## Version

```{autodata} ssmdconvert.__version__

```

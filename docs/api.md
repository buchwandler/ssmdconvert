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

`Converter.convert()`, the convenience `convert()`, and `convert_content()` accept `sequence_fallback_mode`, which may be `spell` or `preserve`. The default is `spell`; the selected value is written to the generated SSMD front matter and normalized document metadata.

```python
result = convert("manuscript.md", sequence_fallback_mode="preserve")
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

`convert_book()` accepts the same policy, defaults to `spell`, and records it in `Book.metadata` and each generated chapter. For example:

```python
book = convert_book("novel.epub", sequence_fallback_mode="preserve")
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

## Optional speech preparation

Install the `[speech]` extra before importing `ssmdconvert.speech`. These APIs are separate from core conversion and do not alter conversion output unless called explicitly.

`SpeechPreparationOptions.sequence_fallback_mode` uses the same `spell` or `preserve` values and defaults to `spell`.

```python
from ssmdconvert.speech import SpeechPreparationOptions, prepare_ssmd_for_speech

result = prepare_ssmd_for_speech(
    source_ssmd,
    options=SpeechPreparationOptions(mode="annotate", language="en"),
)
```

```{autoclass} ssmdconvert.speech.SpeechPreparationOptions
:members:
```

```{autoclass} ssmdconvert.speech.SpeechPreparationResult
:members:
```

```{autoclass} ssmdconvert.speech.SpeechPreparationReport
:members:
```

```{autoclass} ssmdconvert.speech.SpeechChange
:members:
```

```{autoclass} ssmdconvert.speech.SpeechIssue
:members:
```

```{autofunction} ssmdconvert.speech.prepare_ssmd_for_speech

```

## Version

```{autodata} ssmdconvert.__version__

```

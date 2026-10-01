# Python API

The names documented here are exported from `ssmdconvert` and listed in `ssmdconvert.__all__`.

## Conversion

```{autofunction} ssmdconvert.convert

```

```{autoclass} ssmdconvert.Converter
:members:
```

```{autoclass} ssmdconvert.ConversionResult
:members:
```

## Speech preparation and quality control

Speech settings are passed as an immutable options value. `SpeechPreparationOptions()` defaults to `mode="off"`; normal conversion is unchanged unless audit or annotation is explicitly requested.

```python
from ssmdconvert import Converter, SpeechPreparationOptions

result = Converter().convert(
    "chapter.txt",
    language="en",
    speech_options=SpeechPreparationOptions(
        mode="annotate",
        strict=False,
        sequence_fallback_mode="spell",
        pronunciations={"H2O": "water"},
    ),
)
print(result.ssmd)
print(result.speech_report.to_json() if result.speech_report else "no report")
```

Inline `lang`/`language` annotations take precedence over `SpeechPreparationOptions.language`, which takes precedence over SSMD document language metadata. When no language is available, audit reports a warning and still checks Unicode; annotation fails if no text run has an effective language. Existing `sub`, `as`/`say-as`, and `ph`/`phonemes` annotations are protected. Generated pronunciations use `sub`, preserving visible written text.

Audit does not modify SSMD. Annotation only wraps exact source slices when public `ssmd.TextSpan` coordinates prove the mapping safe; it validates output and verifies visible text is unchanged. Overlaps, cross-run candidates, source mismatches, and inexact escaped mappings are skipped and reported. The report includes backend/version, languages, source-coordinate changes, warnings, and residual Unicode issues. U+FFFD is an error; `strict=True` raises on error-level QC findings. Processing is local and makes no cloud/JEV calls.

`pronunciations` is a literal, case-sensitive source-to-spoken mapping. Project terms take precedence over generic normalization. `sequence_fallback_mode` accepts `"preserve"` or `"spell"`.

```{autoclass} ssmdconvert.SpeechPreparationOptions
:members:
```

```{autoclass} ssmdconvert.SpeechPreparationResult
:members:
```

```{autoclass} ssmdconvert.SpeechPreparationReport
:members:
```

```{autoclass} ssmdconvert.SpeechChange
:members:
```

```{autoclass} ssmdconvert.SpeechIssue
:members:
```

```{autofunction} ssmdconvert.prepare_ssmd_for_speech

```

For EPUB chapter conversion, `Converter.convert_book(..., speech_options=...)` returns a transient `Book.speech_reports` mapping keyed by selected chapter ID. The book CLI writes detailed JSON sidecars; see [Books](books.md#speech-preparation-and-reports).

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

```{autofunction} ssmdconvert.parse_chapter_selection

```

## Bundles

```{autofunction} ssmdconvert.write_book_bundle

```

```{autofunction} ssmdconvert.load_book_bundle

```

```{autofunction} ssmdconvert.validate_book_bundle

```

## Errors

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

## Version

```{autodata} ssmdconvert.__version__

```

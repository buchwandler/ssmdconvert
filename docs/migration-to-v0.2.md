# Migration to v0.2

Version 0.2.0 intentionally replaces ambiguous Python convenience functions with
an options-based, typed facade. This is a Python API migration: the CLI command
surface and `.ssmdbook` manifest schema v1 remain unchanged.

## Conversion functions

The old root-level `convert()` alias is removed. Use `convert_document()` for a
source path or `convert_content()` for in-memory content. Settings are passed in
a frozen, keyword-only options object instead of as unrelated function
keywords.

```python
from ssmdconvert import DocumentConversionOptions, convert_document

result = convert_document(
    "manuscript.md",
    options=DocumentConversionOptions(
        language="en-US",
        title="Notes",
        metadata_overrides={"voice_defaults": {"narrator": {"rate": "slow"}}},
    ),
)
ssmd = result.ssmd
```

For in-memory content, keep the explicit source format:

```python
from ssmdconvert import DocumentConversionOptions, convert_content

result = convert_content(
    "# Notes\n\nRead this.",
    input_format="markdown",
    source_name="notes.md",
    options=DocumentConversionOptions(language="en-US"),
)
```

`ConversionResult` still exposes `ssmd` and the normalized `document`.
`inspect_document(source)` is the stable inspection function. The `Converter`
class remains available for callers that need to select or work with adapters
directly.

## Book conversion return value

`convert_book()` now returns `BookConversionResult`, not a bare `Book`. Move
book-specific options into `BookConversionOptions`; speech policy is a nested
`SpeechOptions` value. Access `result.book` and explicitly publish it when
needed.

```python
from ssmdconvert import (
    BookConversionOptions,
    SpeechOptions,
    convert_book,
    write_book_bundle,
)

result = convert_book(
    "novel.epub",
    options=BookConversionOptions(
        chapters="2-20",
        language="de-DE",
        speech=SpeechOptions(mode="freeze", spacy="off"),
    ),
)
book = result.book
freeze_report = result.speech.to_dict()
write_book_bundle(book, "selected.ssmdbook", format="directory")
```

Migration pattern for existing callers:

| Before v0.2                          | v0.2                                                                       |
| ------------------------------------ | -------------------------------------------------------------------------- | ------ | ---- | ---- | ---- | ------- |
| `convert(path)`                      | `convert_document(path, options=DocumentConversionOptions(...))`           |
| `convert(path, language="en")`       | `convert_document(path, options=DocumentConversionOptions(language="en"))` |
| `convert_book(path, chapters="2-4")` | `convert_book(path, options=BookConversionOptions(chapters="2-4"))`        |
| `book = convert_book(path)`          | `result = convert_book(path); book = result.book`                          |
| `speech_semantics="preserve"`        | `speech=SpeechOptions(mode="preserve")` inside `BookConversionOptions`     |
| `linguistics=LinguisticsConfig(...)` | `speech=SpeechOptions(spacy="off"                                          | "auto" | "sm" | "md" | "lg" | "trf")` |

`SpeechOutcome` distinguishes `complete` from `preserved`, includes a versioned
report, and carries a summary only for a complete freeze. Incomplete freezes
raise `SpeechFreezeFailure` with structured partial evidence. File and bundle
publication remain explicit operations and are not performed by `convert_book()`.

The CLI retains its existing `ssmdconvert convert`, `ssmdconvert book convert`,
report, TXT, and speech command names and option syntax. The breaking migration
is confined to Python call signatures and `convert_book()`'s return type.

## Analysis and speech APIs

Use the same typed `AnalysisOptions` and `TextProjectionOptions` across the
analysis functions. Reuse a projection when its exact output digest should appear
in the report:

```python
from ssmdconvert import (
    AnalysisOptions,
    TextProjectionOptions,
    analyze_ssmd,
    build_report,
    project_text,
)

analysis = analyze_ssmd("chapter.ssmd", options=AnalysisOptions(spacy="off"))
projection = project_text(
    analysis,
    options=TextProjectionOptions(max_paragraph_chars=1000),
)
report = build_report(analysis, projection=projection)
```

`analyze_ssmd()` also accepts an in-memory `Book` or `BookConversionResult`;
it creates no temporary bundle. `audit_speech()`, `freeze_speech()`, and
`lookup_change_context()` consume existing analysis/evidence and do not repeat
preparation. Disk persistence is opt-in through `analyze_cached()` and
`lookup_cached_context()`; `analyze_ssmd()` never silently creates or reads a
cache.

The model policy defaults to `spacy="off"`. Selecting `auto` or a local model
tier does not download models; SSMDConvert uses only installed local resources.
See the [Python API reference](api.md) and [analysis workflow guide](analysis-workflows.md)
for detailed option and cache behavior.

## Compatibility boundary

No bundle schema migration is required: directory and ZIP bundles remain schema
v1, and SSMD output remains version 0.9. Version 0.2.0 is the release target
for this breaking API cycle. The project does not claim 1.0.0 stability yet;
that milestone is deferred until the documented compatibility and support gates
are established. This implementation work does not publish a release or create
a Git tag.

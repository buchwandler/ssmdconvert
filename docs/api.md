# Python API

The `ssmdconvert` package exposes typed conversion and analysis APIs. Bundle
storage and lifecycle operations use a single kind-neutral facade; existing
book and document manifest formats remain internal implementation details.

## Bundle lifecycle

`convert_bundle()` detects the source kind, converts the input, and writes a
canonical directory workspace. `inspect_bundle_source()` inspects a source or
bundle. `load_bundle()` and `validate_bundle()` strictly verify supported
manifest content. `load_bundle_workspace()` reads current valid directory
content and reports dirty state; `refresh_bundle_workspace()` updates recorded
digests. `pack_bundle()` writes a canonical archive without changing the
workspace.

```python
from ssmdconvert import (
    convert_bundle,
    inspect_bundle_source,
    load_bundle,
    pack_bundle,
    refresh_bundle_workspace,
    validate_bundle,
)

result = convert_bundle("novel.epub", output="novel.ssmd-bundle")
assert result.kind == "book"
loaded = load_bundle(result.output)
assert loaded.kind == result.kind

inspection = inspect_bundle_source("notes.md")
assert inspection.kind == "document"
workspace = refresh_bundle_workspace("novel.ssmd-bundle")
archive = pack_bundle("novel.ssmd-bundle")
assert validate_bundle(archive) == workspace.kind
```

`convert_bundle()` accepts conversion options such as `chapters`, `language`,
`metadata_overrides`, `speech_semantics`, and local spaCy policy. `chapters` is
meaningful for books; a document accepts only the default `all` selector.

```{autofunction} ssmdconvert.convert_bundle

```

```{autofunction} ssmdconvert.inspect_bundle_source

```

```{autofunction} ssmdconvert.load_bundle

```

```{autofunction} ssmdconvert.load_bundle_workspace

```

```{autofunction} ssmdconvert.refresh_bundle_workspace

```

```{autofunction} ssmdconvert.pack_bundle

```

```{autofunction} ssmdconvert.validate_bundle

```

```{autoclass} ssmdconvert.BundleConversionResult
:members:
```

```{autoclass} ssmdconvert.BundleInspection
:members:
```

```{autoclass} ssmdconvert.LoadedBundle
:members:
```

## In-memory conversion

For callers that need in-memory models, `convert_document()` and
`convert_content()` return a `ConversionResult`; `convert_book()` returns a
`BookConversionResult` containing the converted book and speech outcome.
Publication remains explicit with the neutral `write_bundle()` API.

```python
from ssmdconvert import (
    BookConversionOptions,
    DocumentConversionOptions,
    SpeechOptions,
    convert_book,
    convert_content,
    convert_document,
    write_bundle,
)

document = convert_document(
    "manuscript.md",
    options=DocumentConversionOptions(language="en-US"),
)
content = convert_content("# Notes\n\nRead this.", input_format="markdown")
book_result = convert_book(
    "novel.epub",
    options=BookConversionOptions(
        chapters="2-20",
        language="de-DE",
        speech=SpeechOptions(mode="preserve"),
    ),
)
write_bundle(book_result.book, "selected.ssmd-bundle")
```

## Analysis, reports, and speech

`analyze_ssmd()` accepts standalone SSMD, either canonical bundle storage form,
or an in-memory `Book` or `BookConversionResult`. Analysis and text projection
are separate so the same projection can be reused in a report and downstream
workflow. `analyze_ssmd()` does not write or read a persistent cache; use
`analyze_cached()` and `lookup_cached_context()` for explicit cached analysis.

```python
from ssmdconvert import (
    AnalysisOptions,
    TextProjectionOptions,
    analyze_ssmd,
    build_report,
    project_text,
)

analysis = analyze_ssmd("notes.ssmd-bundle", options=AnalysisOptions(spacy="off"))
projection = project_text(analysis, options=TextProjectionOptions())
report = build_report(analysis, projection=projection)
```

`freeze_speech()` rewrites an existing analysis in memory and never writes to
the source. An incomplete freeze raises `SpeechFreezeFailure` with partial
evidence. See [analysis and speech workflows](analysis-workflows.md) for CLI
usage, cache freshness, and safe publication.

```{autofunction} ssmdconvert.analyze_ssmd

```

```{autofunction} ssmdconvert.project_text

```

```{autofunction} ssmdconvert.build_report

```

```{autofunction} ssmdconvert.freeze_speech

```

```{autoclass} ssmdconvert.AnalysisOptions
:members:
```

```{autoclass} ssmdconvert.TextProjectionOptions
:members:
```

```{autoclass} ssmdconvert.BookConversionOptions
:members:
```

```{autoclass} ssmdconvert.DocumentConversionOptions
:members:
```

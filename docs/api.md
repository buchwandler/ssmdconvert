# Python API

The v0.2 facade is exported from `ssmdconvert` and listed in
`ssmdconvert.__all__`. Conversion and analysis return in-memory results; writing
files, bundles, or analysis caches is explicit. The Python migration from the
pre-0.2 signatures is covered in [Migration to v0.2](migration-to-v0.2.md).

## Documents

`convert_document()` converts a path to an in-memory `ConversionResult`.
`convert_content()` converts in-memory text, Markdown, or HTML. Both use the
same immutable, keyword-only `DocumentConversionOptions` object.

```python
from ssmdconvert import DocumentConversionOptions, convert_content, convert_document

result = convert_document(
    "manuscript.md",
    options=DocumentConversionOptions(language="en-US", title="Notes"),
)
text_result = convert_content(
    "# Notes\n\nRead this.",
    input_format="markdown",
    source_name="notes.md",
    options=DocumentConversionOptions(language="en-US"),
)
```

A small executable example:

```{doctest}
>>> from ssmdconvert import DocumentConversionOptions, convert_content
>>> result = convert_content("Hello.", input_format="text", options=DocumentConversionOptions(language="en-US"))
>>> result.document.metadata["language"]
'en-US'
```

`inspect_document(source)` returns the normalized `Document` without rendering
or writing an output file. The lower-level `Converter` and the source-neutral
`Document`, `Section`, `SourceInfo`, and `ConversionResult` models remain
available for callers that need adapter control.

```{autofunction} ssmdconvert.inspect_document

```

```{autofunction} ssmdconvert.convert_document

```

```{autofunction} ssmdconvert.convert_content

```

```{autoclass} ssmdconvert.DocumentConversionOptions
:members:
```

```{autoclass} ssmdconvert.ConversionResult
:members:
```

## EPUB books

`convert_book()` returns `BookConversionResult`, not a bare `Book`. The result
contains the converted `book`, a discriminated `speech` outcome, and structured
`issues`. Use `result.book` when you want to explicitly publish a bundle.

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
        metadata_overrides={"voice_defaults": {"narrator": {"rate": "slow"}}},
        speech=SpeechOptions(mode="freeze", spacy="off"),
    ),
)
write_book_bundle(result.book, "selected.ssmdbook", format="directory")
report = result.speech.to_dict()
```

The default speech mode is `freeze`; select `SpeechOptions(mode="preserve")` for
structural-only conversion. Freeze requires a resolvable language. Inline SSMD
language scopes and author-owned annotations remain authoritative. `SpeechOutcome`
contains a versioned JSON-ready report and, for a complete freeze, a summary.
Failed freezes raise `SpeechFreezeFailure` with structured partial evidence.

```{autofunction} ssmdconvert.inspect_book

```

```{autofunction} ssmdconvert.convert_book

```

```{autoclass} ssmdconvert.BookConversionOptions
:members:
```

```{autoclass} ssmdconvert.SpeechOptions
:members:
```

```{autoclass} ssmdconvert.BookConversionResult
:members:
```

```{autoclass} ssmdconvert.SpeechOutcome
:members:
```

```{autoclass} ssmdconvert.SpeechFreezeFailure
:members:
```

## SSMD analysis, reports, and TXT

`analyze_ssmd()` accepts standalone SSMD, a validated SSMD book/workspace path,
or an in-memory `Book` or `BookConversionResult`. In-memory books are adapted
with `loaded_source_from_book`; analysis does not write a temporary bundle.
Analysis and projection are separate, so a report can reuse the exact projection
whose text and digest are returned to a downstream caller.

```python
from ssmdconvert import (
    AnalysisOptions,
    TextProjectionOptions,
    analyze_ssmd,
    audit_speech,
    build_report,
    project_text,
)

analysis = analyze_ssmd("chapter.ssmd", options=AnalysisOptions(spacy="off"))
projection = project_text(
    analysis,
    options=TextProjectionOptions(max_paragraph_chars=1000),
)
report = build_report(analysis, projection=projection)
audit = audit_speech(analysis)
assert report.projection.prepared_output_sha256 == projection.stats.prepared_output_sha256
```

```{doctest}
>>> from pathlib import Path
>>> from tempfile import TemporaryDirectory
>>> from ssmdconvert import AnalysisOptions, TextProjectionOptions, analyze_ssmd, build_report, freeze_speech, project_text
>>> with TemporaryDirectory() as directory:
...     source = Path(directory) / "example.ssmd"
...     _ = source.write_text('---\nssmd_version: "0.9"\nlanguage: en-US\n---\nRead.', encoding="utf-8")
...     analysis = analyze_ssmd(source, options=AnalysisOptions(spacy="off"))
...     projection = project_text(analysis, options=TextProjectionOptions(max_paragraph_chars=None))
...     report = build_report(analysis, projection=projection)
...     frozen = freeze_speech(analysis)
>>> projection.text
'Read.'
>>> report.projection.prepared_output_sha256 == projection.stats.prepared_output_sha256
True
>>> frozen.status
'complete'
```

`AnalysisOptions` controls section selection, language resolution, sequence
fallback, preparation profile, overrides, pronunciation mappings, title
coverage, and local spaCy policy. `TextProjectionOptions` controls title
projection and paragraph splitting. The default spaCy policy is `off`; models
are local-only and SSMDConvert never downloads spaCy or a language model.

```{autofunction} ssmdconvert.analyze_ssmd

```

```{autofunction} ssmdconvert.project_text

```

```{autofunction} ssmdconvert.build_report

```

```{autofunction} ssmdconvert.audit_speech

```

```{autoclass} ssmdconvert.AnalysisOptions
:members:
```

```{autoclass} ssmdconvert.TextProjectionOptions
:members:
```

```{autoclass} ssmdconvert.SsmdAnalysis
:members:
```

```{autoclass} ssmdconvert.SsmdAnalysisReport
:members:
```

## Speech audit, freeze, and change context

`freeze_speech(analysis)` freezes an existing analysis in memory and returns
`SpeechFreezeResult`: complete rendered section SSMD, the immutable speech
report, final mapped changes, and issues. It never writes to the source. An
incomplete freeze raises `SpeechFreezeFailure` and carries partial report
evidence instead of returning partially rewritten content.

`lookup_change_context(analysis_or_report, change_id)` resolves a change from
in-memory typed evidence. It does not require a prior report command or disk
cache. Persistent cache behavior is explicit and separately named:
`analyze_cached()` writes checksummed analysis records under the selected cache
root, while `lookup_cached_context()` checks the current source chapter against
that saved evidence before returning context. `analyze_ssmd()` does not create
or read this cache.

```python
from ssmdconvert import (
    AnalysisOptions,
    analyze_ssmd,
    freeze_speech,
    lookup_change_context,
)

analysis = analyze_ssmd("chapter.ssmd", options=AnalysisOptions(spacy="off"))
if analysis.preparation.changes:
    change_id = analysis.preparation.changes[0].id
    context = lookup_change_context(analysis, change_id)
frozen = freeze_speech(analysis)
```

```{autofunction} ssmdconvert.freeze_speech

```

```{autofunction} ssmdconvert.analyze_cached

```

```{autofunction} ssmdconvert.lookup_change_context

```

```{autofunction} ssmdconvert.lookup_cached_context

```

```{autoclass} ssmdconvert.SpeechFreezeResult
:members:
```

```{autoclass} ssmdconvert.SsmdChangeContext
:members:
```

See the [analysis workflow guide](analysis-workflows.md) for cache freshness,
progress, CLI usage, and safe artifact publication. See [book bundles](books.md)
and [bundle format](bundle-format.md) for explicit bundle/workspace operations.

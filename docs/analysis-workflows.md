# SSMD analysis and speech workflows

SSMDConvert owns SSMD-specific source loading, chapter selection, language and
context semantics, source mapping, reporting, text projection, and safe
write-back. It uses the public `ttsready` Python API for source-neutral speech
preparation and QA.

Reports, context lookup, TXT projection, and speech workflows accept standalone
`.ssmd` or `.ssmd.md` files and canonical `.ssmd-bundle` directory or ZIP paths.
The bundle manifest determines whether the source contains a book or document.
Book chapter selection uses original one-based source numbers; a single document
has the section ID `document-0001`.

## Python API and cache boundary

The root Python facade composes the same analysis, projection, report, and
speech materialization services as the CLI:

```python
from ssmdconvert import (
    AnalysisOptions,
    TextProjectionOptions,
    analyze_ssmd,
    build_report,
    freeze_speech,
    lookup_change_context,
    project_text,
)

analysis = analyze_ssmd("notes.ssmd-bundle", options=AnalysisOptions(spacy="off"))
projection = project_text(analysis, options=TextProjectionOptions(max_paragraph_chars=1000))
report = build_report(analysis, projection=projection)
if analysis.preparation.changes:
    context = lookup_change_context(analysis, analysis.preparation.changes[0].id)
frozen = freeze_speech(analysis)  # returns rewritten section text; writes nothing
```

`analyze_ssmd()` accepts standalone SSMD, validated bundles, editable workspaces,
and in-memory book models. It writes no temporary bundle or cache. Reusing a
projection in `build_report()` keeps its statistics and prepared-output digest
tied to the TXT result. `audit_speech()` and `freeze_speech()` consume existing
analysis and do not prepare it again.

Persistent analysis uses explicit controls. `analyze_cached(source, cache_root=..., refresh=...)` saves checksummed records; `lookup_cached_context()`
checks the current content item before returning context. Use
`lookup_change_context()` when evidence is already in memory and no cache lookup
is wanted.

## Reports and language

```bash
ssmdconvert report novel.ssmd-bundle.zip --chapters 2-8
ssmdconvert report notes.ssmd --format json -o report.json
ssmdconvert report novel.ssmd-bundle --fail-on-warning --refresh
```

Markdown goes to stdout by default. `--format md|json` or `-o` selects output.
Reports include selected-section statistics, mapped changes, and a TXT preview.
`--show-raw-spans` adds mapping details. `--fail-on-warning` emits the report
and returns a failing status when it contains a warning or error. `--refresh`
bypasses cached preparation for selected sections and saves a fresh snapshot.

`--language` sets the base language for unscoped text. Inline SSMD language
spans remain authoritative, with the innermost scope winning. Without an
explicit override, language is resolved from SSMD and bundle metadata. Unresolved
language is reported rather than silently defaulted. `--sequence-fallback-mode`,
`--max-paragraph-chars`, and `--include-titles` control preparation and
projection.

## Local spaCy and progress

Bundle conversion, reports, TXT, and speech-preparation commands accept
`--spacy off|auto|sm|md|lg|trf`; the default is `off`. `auto` checks locally
installed models for each effective language and continues without hints if no
compatible model is available. Explicit tiers require their local model.
SSMDConvert never downloads spaCy or models.

Long-running commands accept `--progress` / `--no-progress`. Progress is
automatic only when stderr is a terminal. Rich UI or concise plain status output
is written to stderr; report, TXT, and JSON output remain on stdout. Python
callbacks are synchronous and provider-neutral.

## Context lookup

First create a report so the generic change ID is in the local analysis cache,
then request that ID for the same source:

```bash
ssmdconvert report novel.ssmd-bundle.zip
ssmdconvert context novel.ssmd-bundle.zip chg:v1:0123456789abcdef0123456789abcdef
ssmdconvert context novel.ssmd-bundle.zip chg:v1:0123456789abcdef0123456789abcdef --paragraph --json
```

Context checks the current bytes of the affected chapter or document before
returning cached data. Editing that item makes its old analysis stale; rerun the
report with `--refresh` and use the new change ID. Unrelated chapter edits do not
invalidate another chapter's context. Mixed-language paragraphs are shown as
whole paragraphs. Review `--bug-report` output for sensitive text before sharing.

## TXT projection

```bash
ssmdconvert txt novel.ssmd-bundle.zip --chapters 2-8 -o prepared.txt
ssmdconvert txt notes.ssmd --no-include-titles
```

TXT is the generic prepared plain-text projection used by report previews and
statistics, not a substitute for SSMD: annotations are not included. Output goes
to stdout unless `-o` is given. Existing destinations require `--force`; the
input is never a valid output path.

## Speech audit, annotate, and freeze

```bash
ssmdconvert speech audit notes.ssmd --json
ssmdconvert speech annotate notes.ssmd -o annotated.ssmd
ssmdconvert speech freeze novel.ssmd-bundle.zip --chapters 2-8 -o frozen.ssmd-bundle.zip
```

Audit is read-only and uses the same analysis pipeline and generic change IDs as
reporting. Annotation and freeze materialize eligible automatic decisions as
explicit SSMD substitutions. They validate source spans, reject unsafe or
overlapping edits, and preserve visible text. Existing authoritative
annotations are not duplicated; unresolved language or unsafe mappings prevent
write-back.

Speech writes require a new destination by default, use atomic publication, and
never mutate a workspace in place. A dirty directory workspace can be read as-is;
selected items are written to the new bundle and unselected book chapters remain
unchanged. See [Bundle workspaces](bundles.md) for the canonical artifact and
workspace rules.

## Cache and data handling

Reports create checksummed, versioned analysis snapshots in the user cache. See
[Analysis cache](analysis-cache.md) for the location, retention, freshness, and
removal details.

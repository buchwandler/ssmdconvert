# SSMD analysis and speech workflows

`ssmdconvert` owns SSMD-specific source loading, chapter selection, language/context
semantics, source mapping, reporting, TXT projection, and write-back. It uses the
public `ttsready>=0.2,<0.3` Python API for source-neutral speech preparation and QA;
`ttsready` is a core dependency. Generic analysis IDs and change provenance are
reported without exposing replacement identities as application-specific rules.

Conceptually, the layers are:

```text
spokenform → ttsready → ssmdconvert
```

`spokenform` handles linguistic normalization; `ttsready` provides generic preparation
and QA; `ssmdconvert` owns SSMD application semantics and write-back. `ssmdconvert`
depends directly on the public `ttsready` API, not on `spokenform`.

The commands accept a standalone `.ssmd`/`.ssmd.md` file, a validated
`.ssmdbook.zip`, or an editable `.ssmdbook/` directory workspace. Chapter selectors
are original 1-based source chapter numbers and preserve source order.

## Report

```bash
ssmdconvert report BOOK.ssmdbook.zip --chapters 2-8
ssmdconvert report chapter.ssmd --format json -o report.json
ssmdconvert report BOOK.ssmdbook --fail-on-warning --refresh
```

Markdown goes to stdout by default. Use `--format md|json` or let `-o` infer the
format from `.md` or `.json`. Reports use the selected chapters for preparation,
statistics, mapped changes, and TXT preview. `--show-raw-spans` adds raw SSMD
mapping details to Markdown; `--fail-on-warning` emits the report and exits
non-zero if a warning or error was reported. Each report run saves a source-level
snapshot and may reuse compatible per-chapter preparation results. `--refresh`
bypasses the chapter cache and reruns preparation for the selected sections.

`--language` supplies an explicit language override. Without one, language is
resolved from SSMD and book metadata. Unresolved language is reported; the tool
does not silently assume English. `--sequence-fallback-mode`,
`--max-paragraph-chars`, and `--include-titles/--no-include-titles` control the
same preparation/projection options used by `txt`.

## Context lookup

First create a report so the generic change ID is in the local analysis cache,
then request that ID for the same source:

```bash
ssmdconvert report BOOK.ssmdbook.zip
ssmdconvert context BOOK.ssmdbook.zip chg:v1:0123456789abcdef0123456789abcdef
ssmdconvert context BOOK.ssmdbook.zip chg:v1:0123456789abcdef0123456789abcdef --paragraph --json
```

`context` checks the current bytes of the affected chapter before returning a cached
result. Editing that chapter makes its old analysis stale; rerun the report with, for
example, `ssmdconvert report SOURCE --refresh`, and use the change ID from the new
report. Unrelated chapter edits do not invalidate a change's chapter context.
Mixed-language paragraphs are shown as whole paragraphs so language boundaries
remain clear. `--bug-report` adds reproducibility fingerprints and unit text; review
it for sensitive content before sharing.

## TXT projection

```bash
ssmdconvert txt BOOK.ssmdbook.zip --chapters 2-8 -o prepared.txt
ssmdconvert txt chapter.ssmd --no-include-titles
```

The output is the generic prepared plain-text projection used by the report
preview and statistics. It is not a substitute for SSMD: it contains no SSMD
annotations. Output goes to stdout unless `-o` is given. Existing destinations
are refused unless `--force` is supplied; the input is never a valid output.

## Speech audit, annotate, and freeze

```bash
ssmdconvert speech audit chapter.ssmd --json
ssmdconvert speech annotate chapter.ssmd -o annotated.ssmd
ssmdconvert speech freeze BOOK.ssmdbook.zip --chapters 2-8 -o frozen.ssmdbook.zip
```

`audit` is read-only and uses the same analysis pipeline and generic change IDs
as `report`. `annotate` and `freeze` materialize eligible automatic decisions as
explicit SSMD substitutions. They share the validated mapping and write path;
materialization verifies parser-owned source spans, rejects unsafe/overlapping
edits, and preserves visible text. Existing authoritative SSMD speech semantics
are not duplicated. Unresolved effective language or unsafe mapping prevents
write-back.

Speech writes require a new destination by default. Standalone SSMD and book
outputs are written atomically, existing destinations require `--force`, and the
input cannot be overwritten even with `--force`. Dirty directory workspaces are
read as-is, but output must be outside the source workspace; selected chapters
are updated in the new bundle while unselected chapters remain unchanged. For
bundle destinations use `.ssmdbook` for a directory or `.ssmdbook.zip` for a ZIP,
or pass `--format directory|zip`.

## Cache and data handling

Reports create checksummed, versioned analysis snapshots in the user cache.
See [Analysis cache](analysis-cache.md) for the location, retention, freshness,
and removal details.

## Command migration

The old `ttsready` CLI is not part of this workflow. See
[Migration from the ttsready CLI](migration-from-ttsready-cli.md) for direct
command replacements and commands that are intentionally not migrated.

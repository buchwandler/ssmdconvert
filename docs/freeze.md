# `ssmdconvert speech freeze`

Freeze selected eligible automatic speech decisions into explicit SSMD semantics
in a destination document or book bundle.

```bash
ssmdconvert speech freeze chapter.ssmd -o frozen.ssmd
ssmdconvert speech freeze BOOK.ssmd-bundle.zip --chapters 2-4 -o frozen.ssmd-bundle.zip
ssmdconvert speech freeze SOURCE -o frozen.ssmd --json
ssmdconvert speech freeze SOURCE -o frozen.ssmd --report freeze-report.json
```

Fresh EPUB conversion applies this freeze automatically: `ssmdconvert bundle convert novel.epub -o novel.ssmd-bundle`. Use `--speech-semantics preserve` to request the historical structural-only result. The conversion-time aliases come from `ttsready`/`spokenform`, do not alter visible source text, and do not override author-owned annotations. A resolvable language is required for freeze; use `--language` to set the base for unscoped text or use preserve when none is available. Inline SSMD language scopes remain authoritative.

## Ownership boundary

Spokenform recognizes linguistic forms and proposes spoken replacements. TTSReady provides
preparation-set consistency and quality checks. SSMDConvert parses and maps those source-relative
changes, then persists them in SSMD without rewriting visible text. SSMDConvert is not an acronym
detector or punctuation normalizer.

```markdown
[open/close]{sub="open slash close"}
[ART’s]{sub="A R T’s"}
```

`freeze` uses the same fail-closed mapping, validation, and atomic writer as
[`speech annotate`](speech-annotations.md). It preserves visible text, does not
duplicate authoritative SSMD substitutions, refuses unresolved effective
language, and never overwrites its input. Existing output requires `--force`.

Successful freezes print terminal disposition counts. `--json` emits the versioned `ssmdconvert-speech-freeze-report` (version 1) to stdout; `--report PATH` writes the same JSON report atomically. It records source/runtime provenance, narration-coverage evidence, exact per-change mappings, and applied, already-authoritative, author-owned, and unresolved totals. If freezing is incomplete, the command exits non-zero and does not publish the SSMD destination; when requested, its report is marked `incomplete` and includes the failure and unresolved changes.

## In-memory Python API

```python
from ssmdconvert import AnalysisOptions, analyze_ssmd, freeze_speech

analysis = analyze_ssmd("chapter.ssmd", options=AnalysisOptions(spacy="off"))
frozen = freeze_speech(analysis)
for section_id, updated_ssmd in frozen.sections.items():
    ...  # explicitly decide whether and where to publish this text
report = frozen.speech.to_dict()
```

`freeze_speech()` returns `SpeechFreezeResult` with complete rewritten section
text and final mapping/issue evidence; it never writes the source or a bundle.
An incomplete attempt raises `SpeechFreezeFailure` with a versioned partial
report and unresolved change evidence. See the [Python API reference](api.md)
for the options and result contract.

Book bundles store this provenance in `manifest.json`, not in invented SSMD metadata. A successful default freeze records `status: complete`, TTSReady/Spokenform versions, and fingerprints. `--speech-semantics preserve` records `status: preserved` and does not claim a completed freeze.
Dirty directory workspaces may be read, but the output must be a new path outside
the workspace. Selected chapters are materialized in the output; unselected
chapters remain unchanged. Bundle outputs use the canonical `.ssmd-bundle` workspace and `.ssmd-bundle.zip` archive suffixes.

To preview without writing, run [`speech audit`](speech-audit.md). For the
complete source, context, cache, and projection workflow, see
[SSMD analysis workflows](analysis-workflows.md).

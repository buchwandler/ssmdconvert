# `ssmdconvert speech freeze`

Freeze selected eligible automatic speech decisions into explicit SSMD semantics
in a destination document or book bundle.

```bash
ssmdconvert speech freeze chapter.ssmd -o frozen.ssmd
ssmdconvert speech freeze BOOK.ssmdbook.zip --chapters 2-4 -o frozen.ssmdbook.zip
ssmdconvert speech freeze SOURCE -o frozen.ssmd --json
ssmdconvert speech freeze SOURCE -o frozen.ssmd --report freeze-report.json
```

Fresh EPUB conversion applies this freeze automatically: `ssmdconvert book convert novel.epub -o novel.ssmdbook`. Use `--speech-semantics preserve` to request the historical structural-only result. The conversion-time aliases come from `ttsready`/`spokenform`, do not alter visible source text, and do not override author-owned annotations. A resolvable language is required for freeze; use `--language` to set the base for unscoped text or use preserve when none is available. Inline SSMD language scopes remain authoritative.

`freeze` uses the same fail-closed mapping, validation, and atomic writer as
[`speech annotate`](speech-annotations.md). It preserves visible text, does not
duplicate authoritative SSMD substitutions, refuses unresolved effective
language, and never overwrites its input. Existing output requires `--force`.



Successful freezes print terminal disposition counts. `--json` emits the versioned `ssmdconvert-speech-freeze-report` (version 1) to stdout; `--report PATH` writes the same JSON report atomically. It records source/runtime provenance, narration-coverage evidence, exact per-change mappings, and applied, already-authoritative, author-owned, and unresolved totals. If freezing is incomplete, the command exits non-zero and does not publish the SSMD destination; when requested, its report is marked `incomplete` and includes the failure and unresolved changes.

Book bundles store this provenance in `manifest.json`, not in invented SSMD metadata. A successful default freeze records `status: complete`, TTSReady/Spokenform versions, and fingerprints. `--speech-semantics preserve` records `status: preserved` and does not claim a completed freeze.
Dirty directory workspaces may be read, but the output must be a new path outside
the workspace. Selected chapters are materialized in the output; unselected
chapters remain unchanged. Bundle type is inferred from `.ssmdbook` or
`.ssmdbook.zip`, or can be set with `--format directory|zip`.

To preview without writing, run [`speech audit`](speech-audit.md). For the
complete source, context, cache, and projection workflow, see
[SSMD analysis workflows](analysis-workflows.md).

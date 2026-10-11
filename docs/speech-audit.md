# `ssmdconvert speech audit`

Audit automatic speech-preparation changes without modifying SSMD.

```bash
ssmdconvert speech audit SOURCE
ssmdconvert speech audit BOOK.ssmdbook.zip --chapters 3 --json
ssmdconvert speech audit SOURCE --language en-US --fail-on-warning
```

Audit uses the same source loader, selected chapters, generic change IDs, and
analysis pipeline as `report`; it is a speech-focused view, not a separate
normalizer. `--json` emits a versioned JSON result. `--fail-on-warning` returns a
non-zero status when the audit contains warnings or errors. `--language`, chapter
selection, fallback mode, and title inclusion control the analysis as in `report`.

Human output and JSON include the same mapping counts: applied, already authoritative, author-owned, and unresolved. `--json` emits `ssmdconvert.speech-audit.v2`, including each change's final disposition and a `freeze_mapping` summary. The audit is read-only; an `applied` disposition means the exact mapping is safe to write, not that the audit changed the source.

Audit is read-only. To materialize eligible changes into SSMD, use
[`speech annotate`](speech-annotations.md) or [`speech freeze`](freeze.md).

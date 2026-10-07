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

Audit is read-only. To materialize eligible changes into SSMD, use
[`speech annotate`](speech-annotations.md) or [`speech freeze`](freeze.md).

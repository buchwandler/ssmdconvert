# `ssmdconvert context`

Context lookup connects a generic change ID from a report to the corresponding
source and prepared text.

```bash
ssmdconvert report SOURCE
ssmdconvert context SOURCE chg:v1:0123456789abcdef0123456789abcdef
ssmdconvert context SOURCE chg:v1:0123456789abcdef0123456789abcdef --paragraph --json
```

The requested source must match a source with a saved report analysis. Context
checks the current raw bytes of the affected chapter; if that chapter changed,
refresh with `ssmdconvert report SOURCE --refresh` and use the new report's change
ID. It does not invalidate context for edits to unrelated chapters. Mixed-language
paragraphs are rendered as whole paragraphs to keep language boundaries intact.

`--paragraph` expands sentence context, `--json` returns the versioned context
object, and `--bug-report` adds reproducibility fingerprints and unit text. The
latter may contain source text; review it before sharing. See
[Analysis cache](analysis-cache.md) for storage and freshness behavior.

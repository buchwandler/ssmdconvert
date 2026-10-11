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
object. `--bug-report` adds reproducibility fingerprints and unit text; review it
for sensitive content before sharing. See [Analysis cache](analysis-cache.md) for
storage and freshness behavior.

In Python, `lookup_change_context(analysis_or_report, change_id)` uses typed
in-memory evidence directly and needs no prior report/cache. For persistence, use
`analyze_cached(..., cache_root=...)` and the separately named
`lookup_cached_context(source, change_id, cache_root=...)`; the latter validates
freshness against the affected source chapter. Plain `analyze_ssmd()` does not
read or write a cache. See the [Python API reference](api.md) for both paths.

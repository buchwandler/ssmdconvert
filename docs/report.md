# `ssmdconvert report`

Analyze SSMD with the same selected source sections, preparation options, and TXT
projection used by the other analysis commands.

```bash
ssmdconvert report SOURCE
ssmdconvert report BOOK.ssmdbook.zip --chapters 1,3-5 --format json -o report.json
ssmdconvert report SOURCE --refresh --fail-on-warning
```

Output is Markdown to stdout unless `--format json` is selected or `-o` names a
`.json` file. File output can use `--format md|json`; Markdown output may include
`--show-raw-spans`. Existing output paths are refused unless `--force` is given.

Common options:

- `--chapters SELECTOR`: source chapter numbers for SSMD books; defaults to all.
- `--language LANG`: explicit language override; unresolved language is reported,
  never silently defaulted.
- `--sequence-fallback-mode spell|preserve`: preparation fallback policy.
- `--max-paragraph-chars N`: projection wrapping limit; default `1000`.
- `--include-titles` / `--no-include-titles`: include or omit title units.
- `--refresh`: bypass cached per-chapter preparation, rerun the selected sections,
  and save a fresh report snapshot.
- `--fail-on-warning`: emit the report and return a failing exit status if it
  contains a warning or error.

JSON is versioned and owned by `ssmdconvert`. The report records generic change
IDs, source mapping status, selected-section statistics, and the exact TXT
projection hash. See [Analysis cache](analysis-cache.md) and
[SSMD analysis workflows](analysis-workflows.md).

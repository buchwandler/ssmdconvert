# `ssmdconvert speech freeze`

Freeze selected eligible automatic speech decisions into explicit SSMD semantics
in a destination document or book bundle.

```bash
ssmdconvert speech freeze chapter.ssmd -o frozen.ssmd
ssmdconvert speech freeze BOOK.ssmdbook.zip --chapters 2-4 -o frozen.ssmdbook.zip
```

`freeze` uses the same fail-closed mapping, validation, and atomic writer as
[`speech annotate`](speech-annotations.md). It preserves visible text, does not
duplicate authoritative SSMD substitutions, refuses unresolved effective
language, and never overwrites its input. Existing output requires `--force`.

Dirty directory workspaces may be read, but the output must be a new path outside
the workspace. Selected chapters are materialized in the output; unselected
chapters remain unchanged. Bundle type is inferred from `.ssmdbook` or
`.ssmdbook.zip`, or can be set with `--format directory|zip`.

To preview without writing, run [`speech audit`](speech-audit.md). For the
complete source, context, cache, and projection workflow, see
[SSMD analysis workflows](analysis-workflows.md).

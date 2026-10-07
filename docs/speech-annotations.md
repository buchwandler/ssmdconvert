# `ssmdconvert speech annotate`

Write selected eligible automatic speech changes as explicit SSMD substitutions
in a new destination.

```bash
ssmdconvert speech annotate chapter.ssmd -o annotated.ssmd
ssmdconvert speech annotate BOOK.ssmdbook --chapters 2-4 -o annotated-copy.ssmdbook
```

For book sources, chapter selectors use original 1-based source numbers. Unselected
chapters remain unchanged. Directory workspaces, including dirty workspaces, are
read as-is, but the output destination must be outside the source workspace. Use
`.ssmdbook` for a directory or `.ssmdbook.zip` for a ZIP; `--format directory|zip` overrides inference for another output name.

Writes use parser-owned source spans, verify exact source slices, reject unsafe or
overlapping changes, validate the resulting SSMD, and prove that visible text is
unchanged. Existing authoritative speech annotations are not duplicated. If the
effective language is unresolved or mapping is unsafe, materialization fails
closed. Existing destinations require `--force`; the input can never be
overwritten, even with `--force`.

For the freeze-oriented command spelling, see [`speech freeze`](freeze.md). Both
commands share the same validated materialization path.

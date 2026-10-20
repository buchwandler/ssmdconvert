# `ssmdconvert speech annotate`

Write selected eligible automatic speech changes as explicit SSMD substitutions
in a new destination.

```bash
ssmdconvert speech annotate chapter.ssmd -o annotated.ssmd
ssmdconvert speech annotate BOOK.ssmd-bundle --chapters 2-4 -o annotated-copy.ssmd-bundle
```

For a new EPUB artifact, `ssmdconvert bundle convert` freezes eligible automatic decisions during conversion by default; choose `--speech-semantics preserve` for a structural-only result. This one-pass path uses the same analysis/materialization rules described here. `speech annotate` remains useful for existing SSMD sources and review workflows.

For book sources, chapter selectors use original 1-based source numbers. Unselected
chapters remain unchanged. Directory workspaces, including dirty workspaces, are
read as-is, but the output destination must be outside the source workspace. Use
Use `.ssmd-bundle` for directories and `.ssmd-bundle.zip` for ZIP archives.

Writes use parser-owned source spans, verify exact source slices, reject unsafe or
overlapping changes, validate the resulting SSMD, and prove that visible text is
unchanged. Existing authoritative speech annotations are not duplicated. If the
effective language is unresolved or mapping is unsafe, materialization fails
closed. Existing destinations require `--force`; the input can never be
overwritten, even with `--force`.

For the freeze-oriented command spelling, see [`speech freeze`](freeze.md). Both
commands share the same validated materialization path.

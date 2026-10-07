# `ssmdconvert txt`

Project SSMD into generic prepared plain text for downstream TTS tools. The
projection uses the same selected sections and rendering logic as the report's
TXT preview and statistics.

```bash
ssmdconvert txt SOURCE
ssmdconvert txt BOOK.ssmdbook.zip --chapters 2-8 -o prepared.txt
ssmdconvert txt SOURCE --language de-DE --no-include-titles
```

Text goes to stdout by default. `-o` writes a file atomically; an existing output
requires `--force`, and the input cannot be used as the output. `--chapters`,
`--language`, `--sequence-fallback-mode`, `--max-paragraph-chars`, and title
options have the same meaning as in `report`. TXT is a projection only: it does
not contain SSMD source annotations and does not write back to the source.

See [Report](report.md) and [SSMD analysis workflows](analysis-workflows.md).

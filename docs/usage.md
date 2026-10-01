# CLI usage

## Convert a document

```bash
ssmdconvert convert INPUT [-o OUTPUT]
```

Examples:

```bash
ssmdconvert convert manuscript.txt -o manuscript.ssmd
ssmdconvert convert novel.md -o novel.ssmd
ssmdconvert convert page.html -o page.ssmd
ssmdconvert convert book.epub -o book.ssmd
ssmdconvert convert report.pdf -o report.ssmd
ssmdconvert convert manuscript.docx -o manuscript.ssmd
ssmdconvert convert existing.ssmd -o normalized.ssmd
```

PDF and DOCX require the `[pdf]` and `[docx]` extras. When `-o` is omitted, output is written next to the source using `source.with_suffix(".ssmd")`.

Optional metadata can be supplied during conversion:

```bash
ssmdconvert convert manuscript.txt \
  --title "Example" \
  --author "A. Writer" \
  --language en
```

Core conversion is local and does not send content to JEV.

## Opt-in speech preparation and QC

Speech preparation is disabled by default. The default conversion path does not call `spokenform` and emits the same SSMD as before. Opt in to a report-only audit or safe SSMD annotations:

```bash
ssmdconvert convert chapter.txt \
  --language en \
  --speech audit \
  --speech-report chapter.speech-report.json

ssmdconvert convert chapter.txt \
  --language en \
  --speech annotate \
  --sequence-fallback spell \
  --pronunciations pronunciations.json \
  --speech-report chapter.speech-report.json
```

`--speech` accepts `off` (the default), `audit`, or `annotate`. Audit leaves the document unchanged and records candidate pronunciations, skipped mappings, warnings, and QC issues. Annotate wraps only exact, safely mapped candidates in SSMD `sub` annotations; visible source text stays unchanged. For example, the written `5 kg` can be emitted as `[5 kg]{sub="five kilograms"}`.

The effective speech language is selected from an enclosing inline `lang`/`language` annotation, `--speech-language`, `--language`, and document language metadata, in that precedence order. `--language` also sets output metadata; `--speech-language` only overrides speech preparation. A run without a language is skipped and reported; annotation fails if no run has an effective language. Audit without one still performs character QC.

Pronunciation files may be JSON (`{"H2O": "water"}`) or TOML (`[pronunciations]` followed by `H2O = "water"`). Glossary terms are matched literally and case-sensitively, and take precedence over generic normalization. `--sequence-fallback` accepts `preserve` or `spell` (default `spell`).

Existing author `sub`, `as`/`say-as`, and `ph`/`phonemes` annotations remain authoritative. Generated `sub` retains the written form while supplying a spoken alias. Existing `say-as` behavior depends on the downstream consumer/provider; `ssmdconvert` does not claim uniform provider support or replace author instructions.

Reports flag U+FFFD, unresolved symbols, private-use/noncharacter/control characters, and unusual punctuation without deleting or guessing at them. `--strict-speech` makes error-level QC findings, including U+FFFD, fail conversion. All speech preparation and QC run locally through `spokenform`; they do not send content to JEV or another cloud service.

## Inspect a source

Inspect the local adapter and normalized sections without writing output:

```bash
ssmdconvert inspect book.epub
ssmdconvert inspect book.epub --json
```

Inspection reports the selected adapter, normalized section titles, character counts, and source references.

## Supported inputs

| Format   | Install  | Notes                                                                |
| -------- | -------- | -------------------------------------------------------------------- |
| TXT      | core     | Plain-text section splitting                                         |
| Markdown | core     | Normalized into source-neutral sections                              |
| HTML     | core     | Converted to normalized Markdown and SSMD                            |
| EPUB     | core     | Chapter extraction delegates to `epub2text`                          |
| SSMD     | core     | Parsed and re-emitted as SSMD 0.9                                    |
| PDF      | `[pdf]`  | `pypdf` text extraction; no OCR for scanned pages                    |
| DOCX     | `[docx]` | Extracts paragraphs and headings; complex floating layout is ignored |

Chapter-aware EPUB conversion and bundle commands are described in [Books](books.md).

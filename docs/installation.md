# Installation

## Requirements

- Python 3.10 or newer
- An operating system supported by Python

## Base package

```bash
python -m pip install ssmdconvert
```

The base install supports plain text, Markdown, HTML, EPUB, and SSMD inputs,
including SSMD-aware report/context/TXT and speech audit/annotate/freeze commands.
EPUB extraction uses the local `epub2text` dependency. `ttsready>=0.2,<0.3` is a core
dependency for source-neutral preparation and QA.

## Optional extras

Install only the additional support you need:

```bash
python -m pip install "ssmdconvert[pdf]"     # PDF text extraction
python -m pip install "ssmdconvert[docx]"    # DOCX paragraphs and headings
python -m pip install "ssmdconvert[all]"     # all optional extras
```

PDF extraction does not perform OCR. DOCX extraction does not preserve complex
floating layout. Speech analysis commands operate on SSMD and are independent of
document conversion. The former `SpeechPreparationOptions` /
`prepare_ssmd_for_speech` engine is removed; see [the workflow docs](analysis-workflows.md)
for current CLI commands.

## Source installation

```bash
git clone https://github.com/buchwandler/ssmdconvert.git
cd ssmdconvert
python -m pip install -e ".[dev]"
```

## Verify the installation

```bash
ssmdconvert --version
ssmdconvert --help
ssmdconvert book --help
```

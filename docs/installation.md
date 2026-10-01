# Installation

## Requirements

- Python 3.10 or newer
- An operating system supported by Python

## Base package

```bash
python -m pip install ssmdconvert
```

The base install supports plain text, Markdown, HTML, EPUB, and SSMD inputs. EPUB extraction uses the local `epub2text` dependency. Importing `ssmdconvert` does not import the optional speech package.

## Optional extras

Install only the additional support you need:

```bash
python -m pip install "ssmdconvert[pdf]"     # PDF text extraction
python -m pip install "ssmdconvert[docx]"    # DOCX paragraphs and headings
python -m pip install "ssmdconvert[speech]"  # local speech-preparation API
python -m pip install "ssmdconvert[all]"     # all optional extras
```

PDF extraction does not perform OCR. DOCX extraction does not preserve complex floating layout. Speech preparation is an optional Python API under `ssmdconvert.speech`; normal conversion remains unchanged.

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

# Installation

## Requirements

- Python 3.10 or newer
- An operating system supported by Python

## Core package

Install core conversion and EPUB support from PyPI:

```bash
python -m pip install ssmdconvert
```

The core install supports text, Markdown, HTML, EPUB, and SSMD inputs. It does not require JEV or Readio.

The core install includes the local `spokenform` backend used by opt-in speech preparation and QC. It performs no cloud calls; JEV enrichment remains a separate optional extra.

## Optional extras

Install PDF text extraction or DOCX support when needed:

```bash
python -m pip install "ssmdconvert[pdf]"
python -m pip install "ssmdconvert[docx]"
```

Install JEV-backed semantic enrichment:

```bash
python -m pip install "ssmdconvert[jev]"
```

Install all published extras:

```bash
python -m pip install "ssmdconvert[all]"
```

The `all` extra includes JEV, PDF, and DOCX dependencies. It does not add Readio as a dependency.

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
```

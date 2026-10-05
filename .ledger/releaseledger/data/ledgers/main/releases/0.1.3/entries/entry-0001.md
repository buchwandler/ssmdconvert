---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: 0.1.3
kind: added
summary: Added native SSMD scene-break handling for Markdown, HTML, and EPUB conversions
status: accepted
audience: null
scopes: []
source_refs:
  - git:0aafda12fe948a7364b441e6981980c15e6cd337
paths:
  - pyproject.toml
  - ssmdconvert/_scene_breaks.py
  - ssmdconvert/adapters/html.py
  - ssmdconvert/adapters/markdown_speech.py
  - ssmdconvert/render.py
  - tests/epub_support.py
  - tests/test_converter_api.py
  - tests/test_epub_adapter.py
  - tests/test_markdown_html.py
  - tests/test_packaging.py
  - tests/test_ssmd_adapter.py
issues: []
prs: []
sources:
  - git:0aafda12fe948a7364b441e6981980c15e6cd337
contributors:
  - "@holgern"
breaking: false
internal: false
order: 1
---

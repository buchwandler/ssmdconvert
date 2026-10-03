---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0002
release_version: 0.1.1
kind: added
summary:
  Added in-memory conversion of text, Markdown, and HTML, with Markdown rendered
  as SSMD-safe spoken text
status: accepted
audience: null
scopes: []
source_refs:
  - git:4b19351704da02578b56ce86c1ce7935be442821
paths:
  - README.md
  - pyproject.toml
  - ssmdconvert/__init__.py
  - ssmdconvert/adapters/__init__.py
  - ssmdconvert/adapters/base.py
  - ssmdconvert/adapters/html.py
  - ssmdconvert/adapters/markdown.py
  - ssmdconvert/adapters/markdown_speech.py
  - ssmdconvert/adapters/text.py
  - ssmdconvert/converter.py
  - tests/test_markdown_html.py
  - tests/typecheck/public_api.py
issues: []
prs: []
sources:
  - git:4b19351704da02578b56ce86c1ce7935be442821
contributors:
  - "@holgern"
breaking: false
internal: false
order: 2
---

---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0003
release_version: 0.1.1
kind: added
summary:
  Added spell or preserve sequence fallback modes to document and book conversion,
  saved in SSMD and book metadata
status: accepted
audience: null
scopes: []
source_refs:
  - git:b1f342fbb57e2c0a04fceee24b32d9adf503dbcf
paths:
  - README.md
  - docs/api.md
  - docs/books.md
  - docs/bundle-format.md
  - docs/usage.md
  - ssmdconvert/adapters/markdown.py
  - ssmdconvert/books.py
  - ssmdconvert/cli.py
  - ssmdconvert/converter.py
  - ssmdconvert/policy.py
  - ssmdconvert/render.py
  - ssmdconvert/speech/models.py
  - tests/test_book_bundle.py
  - tests/test_book_conversion.py
  - tests/test_cli.py
  - tests/test_converter_api.py
  - tests/test_markdown_html.py
  - tests/test_sequence_fallback_policy.py
issues: []
prs: []
sources:
  - git:b1f342fbb57e2c0a04fceee24b32d9adf503dbcf
contributors:
  - "@holgern"
breaking: false
internal: false
order: 3
---

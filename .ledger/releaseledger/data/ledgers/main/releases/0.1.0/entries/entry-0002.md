---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0002
release_version: 0.1.0
kind: changed
summary:
  Changed EPUB chapter extraction to use epub2text while preserving combined
  conversion results
status: accepted
audience: null
scopes: []
source_refs: []
paths:
  - ssmdconvert/adapters/epub.py
  - ssmdconvert/converter.py
issues: []
prs: []
sources:
  - tl:task-0001
contributors: []
breaking: false
internal: false
order: 2
---

The existing `convert()` and `Converter.convert()` APIs continue to return one combined `ConversionResult`.

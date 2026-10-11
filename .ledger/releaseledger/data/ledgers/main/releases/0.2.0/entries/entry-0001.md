---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0001
release_version: 0.2.0
kind: changed
summary:
  Changed language resolution to preserve inline SSMD scopes over base-language
  overrides
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0011
paths:
  - ssmdconvert/analysis/units.py
  - ssmdconvert/books.py
  - docs/books.md
  - docs/analysis-workflows.md
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 1
---

The innermost inline language scope now determines its text run even when a document or CLI base language is supplied; unscoped text continues to use the base-language precedence.

---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 3
entry_id: entry-0001
release_version: 0.1.0
kind: added
summary:
  Added EPUB chapter inspection, source-number selection, and standalone SSMD
  chapter conversion
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0001
paths:
  - ssmdconvert/books.py
  - ssmdconvert/bundle.py
  - ssmdconvert/cli.py
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 1
---

The `book` CLI and public Python APIs create standalone SSMD chapters in editable directory bundles or portable ZIP archives. The manifest chapter list defines playback order.

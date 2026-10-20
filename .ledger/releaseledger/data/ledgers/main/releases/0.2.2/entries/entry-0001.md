---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: 0.2.2
kind: changed
summary: Unified book and document bundle operations under canonical artifact names
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0016
paths:
  - ssmdconvert/bundle.py
  - ssmdconvert/cli.py
  - docs/bundles.md
issues: []
prs: []
sources: []
contributors: []
breaking: true
internal: false
order: 1
---

The six bundle commands now own conversion, inspection, metadata, refresh, packing, and validation for both content kinds. The separate kind-specific CLI groups are removed; existing manifest formats and schema versions remain unchanged.

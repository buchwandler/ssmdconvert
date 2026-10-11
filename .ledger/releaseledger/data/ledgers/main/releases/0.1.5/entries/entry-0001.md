---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: 0.1.5
kind: changed
summary: EPUB book conversion freezes safe automatic speech decisions by default
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0010
paths:
  - ssmdconvert/books.py
  - ssmdconvert/cli.py
  - ssmdconvert/speech/conversion.py
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 1
---

Use --speech-semantics preserve for structural-only output. Generated aliases come from the existing ttsready/spokenform pipeline, visible text is unchanged, and freeze requires an effective language.

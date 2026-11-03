---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: 0.2.4
kind: added
summary: Added bundle-owned speech profiles that can be edited and reused on rebuild
status: accepted
audience: null
scopes: []
source_refs: []
paths:
  - ssmdconvert/speech/profile_store.py
  - ssmdconvert/cli.py
  - docs/speech-profiles.md
  - docs/bundles.md
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 1
---

New bundles carry a portable speech.toml recipe. Bundle-aware speech commands discover it automatically, and forced conversion rebuilds reuse the destination profile without repeating an external path.

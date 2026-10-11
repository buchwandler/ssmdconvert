---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0002
release_version: 0.2.0
kind: added
summary: Added opt-in local spaCy enrichment and stderr progress to speech workflows
status: accepted
audience: null
scopes: []
source_refs: []
paths:
  - ssmdconvert/linguistics.py
  - ssmdconvert/progress.py
  - ssmdconvert/cli.py
  - ssmdconvert/analysis/cache.py
  - pyproject.toml
  - docs/installation.md
  - docs/usage.md
  - docs/analysis-workflows.md
  - docs/report.md
issues: []
prs: []
sources:
  - tl:task-0011
contributors: []
breaking: false
internal: false
order: 2
---

spaCy defaults to off and uses only explicitly installed local models when selected; policy and provider/model versions participate in analysis-cache identity. Typed progress remains provider-neutral in Python, while the CLI renders it on stderr and preserves machine-readable stdout.

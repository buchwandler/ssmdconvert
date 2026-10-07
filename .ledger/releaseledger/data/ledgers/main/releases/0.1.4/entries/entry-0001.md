---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: 0.1.4
kind: added
summary:
  Added SSMD-aware reporting, context lookup, TXT projection, and safe speech
  audit and write-back workflows
status: accepted
audience: null
scopes: []
source_refs:
  - git:045bb1dd673e9f386126827cebd0a93160ed57d0
paths:
  - MANIFEST.in
  - README.md
  - docs/analysis-cache.md
  - docs/analysis-workflows.md
  - docs/api.md
  - docs/context.md
  - docs/freeze.md
  - docs/index.md
  - docs/installation.md
  - docs/migration-from-ttsready-cli.md
  - docs/report.md
  - docs/speech-annotations.md
  - docs/speech-audit.md
  - docs/txt.md
  - docs/usage.md
  - pyproject.toml
  - ssmdconvert/analysis/__init__.py
  - ssmdconvert/analysis/cache.py
  - ssmdconvert/analysis/context.py
  - ssmdconvert/analysis/fingerprints.py
  - ssmdconvert/analysis/models.py
  - ssmdconvert/analysis/prepare.py
  - ssmdconvert/analysis/projection.py
  - ssmdconvert/analysis/reporting.py
  - ssmdconvert/analysis/serialization.py
  - ssmdconvert/analysis/source.py
  - ssmdconvert/analysis/units.py
  - ssmdconvert/bundle.py
  - ssmdconvert/chapter_selection.py
  - ssmdconvert/cli.py
  - ssmdconvert/errors.py
  - ssmdconvert/speech/__init__.py
  - ssmdconvert/speech/audit.py
  - ssmdconvert/speech/mapping.py
  - ssmdconvert/speech/materialize.py
  - ssmdconvert/speech/models.py
  - ssmdconvert/speech/prepare.py
  - ssmdconvert/speech/workflows.py
  - tests/test_analysis_cache.py
  - tests/test_analysis_context.py
  - tests/test_analysis_prepare.py
  - tests/test_analysis_reporting.py
  - tests/test_analysis_source.py
  - tests/test_book_selection.py
  - tests/test_cli.py
  - tests/test_packaging.py
  - tests/test_sequence_fallback_policy.py
  - tests/test_speech_cli.py
  - tests/test_speech_mapping.py
  - tests/test_speech_preparation.py
  - tools/smoke_installed.py
issues: []
prs: []
sources:
  - git:045bb1dd673e9f386126827cebd0a93160ed57d0
contributors:
  - "@holgern"
breaking: false
internal: false
order: 1
---

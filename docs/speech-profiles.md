# Speech replacement profiles

A speech profile is an explicitly selected, reusable TOML mapping from visible SSMD source surfaces to spoken forms. It lets conversion, analysis, TXT projection, audit, annotation, and freeze use the same project vocabulary without rewriting source text.

## Version 1 format

```toml
schema = "ssmdconvert-speech-profile"
version = 1

# Enabled by default. Only English 's / ’s possessives are derived.
derive_possessives = true

[replacements]
"ART" = "art"
"B-E" = "B E"
```

`schema`, `version`, and `[replacements]` are required. The only optional top-level key is `derive_possessives`. Unknown keys, malformed TOML, empty surfaces, edge whitespace in surfaces, and empty or whitespace-only spoken forms are rejected before analysis. Matching is case-sensitive and whole-surface/whole-token; profiles do not support regexes, globs, substring replacement, per-chapter rules, lowercasing, or Unicode normalization.

When possessive derivation is enabled, a base entry such as `"ART" = "art"` adds `ART's -> art's` and `ART’s -> art’s`. Derivation is deliberately limited to those two possessive suffixes; it does not infer plurals or other morphology. An explicit possessive entry wins over a derived one:

```toml
[replacements]
"ART" = "art"
"ART’s" = "A R T possessive"
```

Profile fingerprints describe canonical profile semantics, not the file path or TOML key order. The effective replacement overrides are also included in TTSReady preparation/cache identity.

## Selection and precedence

Pass a profile with `--speech-profile PATH`; SSMDConvert never discovers one from the current directory. The same option is available on:

- `bundle convert`
- `report` and `txt`
- `speech audit`, `speech annotate`, `speech freeze`, and `speech inventory`

For example:

```bash
ssmdconvert speech inventory novel.epub --format toml -o speech.toml
# Review/edit speech.toml, then reuse it across workflows.
ssmdconvert bundle convert novel.epub -o novel.ssmd-bundle --speech-profile speech.toml
ssmdconvert report novel.ssmd-bundle --speech-profile speech.toml
ssmdconvert txt novel.ssmd-bundle --speech-profile speech.toml -o prepared.txt
ssmdconvert speech audit novel.ssmd-bundle --speech-profile speech.toml --json
ssmdconvert speech freeze novel.ssmd-bundle --speech-profile speech.toml -o frozen.ssmd-bundle
```

The ownership and replacement order is:

1. Existing authoritative SSMD `sub` annotations.
2. Explicitly selected speech-profile replacements.
3. Other explicit Python `SpeechOverride` values.
4. Automatic TTSReady/Spokenform suggestions.

A profile is a global mapping for the selected operation: all selected chapters receive the same rules. On a fresh EPUB conversion, profile replacements flow through the existing speech-preparation path and automatic freeze writes them as SSMD `sub` annotations. Visible source text remains unchanged. No raw string replacement is used.

Existing `sub` annotations are authoritative and are never overwritten by a profile. A profile rule that matches an annotated surface is reported as shadowed by inventory/audit; regenerate from the original EPUB or use a preserved bundle if an earlier frozen value must be reconsidered. There is no force-over-existing-sub option.

With `--speech-semantics preserve`, `bundle convert` still validates a supplied profile but does not materialize its replacements. The CLI reports that the profile was loaded but not materialized; the profile remains external for a later audit or freeze.

## Python API

```python
from ssmdconvert import (
    effective_replacements,
    load_speech_profile,
    parse_speech_profile,
    speech_profile_fingerprint,
)

profile = load_speech_profile("speech.toml")
replacements = effective_replacements(profile)
fingerprint = speech_profile_fingerprint(profile)
```

The stable `SpeechReplacementProfile` model and parsing helpers are exported from `ssmdconvert`. Analysis APIs continue to accept the existing `AnalysisOptions.pronunciations` mapping, so callers without profiles retain their current behavior.

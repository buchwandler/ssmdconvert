# Speech replacement profiles

A speech profile is an editable, reusable TOML recipe mapping visible SSMD source surfaces to spoken forms. New bundles own a root-level `speech.toml`; an external TOML remains supported for bootstrapping a bundle or exporting vocabulary for reuse elsewhere.

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

Complete bundle speech provenance can record this as `speech_profile_fingerprint`, separate from the existing TTSReady preparation `profile_fingerprint`. The field is optional for backward compatibility with older bundle provenance.

## Bundle ownership and selection

Every new `.ssmd-bundle` workspace contains canonical `speech.toml`. The file is separate from generated chapter/document SSMD and is not hashed as content; editing it directly does not require `bundle refresh`. Legacy bundles without it are read as having an empty profile and are not modified merely by reading them. Packing carries the validated profile into the archive (and emits an empty profile when packing a legacy workspace).

For a speech-aware operation on a bundle input, profile selection is:

1. Explicit `--speech-profile PATH`, when supplied.
2. The input bundle's `speech.toml`, for directory workspaces and ZIP archives.
3. An empty profile.

This applies to `report`, `txt`, `speech audit`, `speech inventory`, `speech annotate`, and `speech freeze`. An explicit profile overrides the bundle recipe for that operation only; read-only commands do not change the bundle. SSMDConvert does not search the current directory, source parents, home directories, or environment-specific profile folders.

For `bundle convert`, the source is not a bundle, so rebuild selection is explicit `--speech-profile`, then the recognized destination bundle's existing `speech.toml`, then an empty profile. The destination recipe is loaded and validated before `--force` replaces the workspace. The chosen canonical profile is written into the new bundle.

```bash
# First conversion creates an empty bundle-local recipe.
ssmdconvert bundle convert novel.epub -o novel.ssmd-bundle

# Add an explicit rule, or edit novel.ssmd-bundle/speech.toml directly.
ssmdconvert speech set novel.ssmd-bundle ART art
ssmdconvert speech set novel.ssmd-bundle B-E "B E"
ssmdconvert speech remove novel.ssmd-bundle B-E

# No --speech-profile path is needed to rebuild from the original source.
ssmdconvert bundle convert novel.epub -o novel.ssmd-bundle --force

# Export for reuse on another machine; ZIP bundles are supported too.
ssmdconvert speech export novel.ssmd-bundle -o speech.toml
ssmdconvert speech export novel.ssmd-bundle.zip -o portable.toml
```

`speech set` and `speech remove` modify directory workspaces only. `speech export` reads either a workspace or archive, writes canonical explicit profile semantics, and refuses an existing output unless `--force` is supplied. CLI mutations serialize semantic TOML canonically, so comments and key ordering may be normalized.

Changing a profile does not patch already materialized SSMD. Rebuild from the original source to apply the new recipe; `--force` replaces the complete destination and any chapter edits. Existing SSMD `sub` annotations remain authoritative and are never overwritten by a profile. No force-over-existing-sub option exists.

The ownership and replacement order remains:

1. Existing authoritative SSMD `sub` annotations.
2. Explicitly selected speech-profile replacements.
3. Other explicit Python `SpeechOverride` values.
4. Automatic TTSReady/Spokenform suggestions.

A profile is a global mapping for the selected operation: all selected chapters receive the same rules. Profile replacements flow through speech preparation rather than raw text replacement. A rule shadowed by an existing `sub` is reported by inventory/audit.

With `--speech-semantics preserve`, `bundle convert` still validates and stores the selected profile but does not materialize its replacements. A later speech operation can discover the stored recipe automatically.

## Python API

```python
from ssmdconvert import (
    empty_speech_profile,
    effective_replacements,
    load_speech_profile,
    parse_speech_profile,
    render_speech_profile,
    speech_profile_fingerprint,
    with_speech_replacement,
    without_speech_replacement,
    write_speech_profile,
)

profile = load_speech_profile("speech.toml")
profile = with_speech_replacement(profile, "ART", "art")
profile = without_speech_replacement(profile, "B-E")
replacements = effective_replacements(profile)
fingerprint = speech_profile_fingerprint(profile)
canonical_toml = render_speech_profile(profile)
write_speech_profile("portable.toml", profile)
```

The stable `SpeechReplacementProfile` model and parsing helpers are exported from `ssmdconvert`. Analysis APIs continue to accept the existing `AnalysisOptions.pronunciations` mapping, so callers without profiles retain their current behavior.

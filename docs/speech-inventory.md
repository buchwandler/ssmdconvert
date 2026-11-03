# Speech-risk inventory

`ssmdconvert speech inventory SOURCE` scans visible, parser-clean text and reports unique surfaces that may deserve a pronunciation decision. It reports orthographic signals; it does **not** classify words as English/non-English or guess a correct pronunciation. No dictionary, network lookup, or model download is used.

## Sources and examples

Inventory accepts raw EPUB, supported single-document sources, standalone `.ssmd` / `.ssmd.md`, `.ssmd-bundle` workspaces, and `.ssmd-bundle.zip` archives. A raw EPUB is structurally converted in memory with speech semantics preserved; inventory writes no temporary bundle. Bundle and SSMD inputs use the canonical loader/parser and include existing `sub` annotations by default. For either bundle form, `speech.toml` is discovered automatically; an explicit `--speech-profile` overrides it. A legacy bundle without the sidecar behaves as an empty profile, and no ambient directories are searched.

```bash
# Inspect before creating a frozen bundle.
ssmdconvert speech inventory novel.epub --chapters all

# Inventory a source before conversion and use the reviewed profile once.
ssmdconvert speech inventory novel.epub --format toml -o speech.toml
ssmdconvert bundle convert novel.epub -o novel.ssmd-bundle --speech-profile speech.toml

# Or use and edit the recipe owned by an existing workspace.
ssmdconvert speech inventory novel.ssmd-bundle
ssmdconvert speech set novel.ssmd-bundle ART art
ssmdconvert bundle convert novel.epub -o novel.ssmd-bundle --force
ssmdconvert speech freeze novel.ssmd-bundle -o spoken.ssmd-bundle
```

The first command prints a review table. `-o, --output PATH` writes the selected format atomically; existing files are refused unless `--force` is supplied. The source cannot be used as output, and a bundle-workspace inventory must be written outside that workspace.

## Options

```text
--chapters SELECTOR                default: all
--language LANG                    base-language override
--spacy off|auto|sm|md|lg|trf       default: off
--speech-profile PATH              explicit TOML profile override
--format table|json|toml           default: table
-o, --output PATH
--force
--include-existing / --no-include-existing    default: include
--max-contexts N                   default: 2
```

A selected profile, whether explicit or discovered from a bundle, marks inventory candidates as covered and shows the effective replacement. It never changes the input. An explicit `--speech-profile` overrides the local recipe for this operation only. `--include-existing` controls discovery from SSMD substitutions; parser-clean visible text is still scanned either way. `--max-contexts` bounds example contexts per candidate, not occurrence counts.

## Signals

Version 1 scans deterministically for:

- all-caps forms such as `ART`, `NASA`, and `ID`;
- hyphenated initialisms such as `B-E` and `A-B-C`;
- mixed/camel case such as `SecUnit`, `MotilitySys`, and `targetSystem`;
- slash sequences such as `screen/ID` and risky components within them such as `ID`;
- alphanumeric or symbol-heavy forms such as `X12`, `A-17`, and `R&D`;
- visible surfaces carrying an existing `sub` value;
- candidates covered by the selected profile.

Ordinary sentence-start capitalization is not a signal. Lowercase coined words and other cases that do not match these heuristics may be missed; the inventory is a discovery aid, not an English-word classifier. Candidate order is stable: profile-covered candidates first, then signal priority, descending occurrence count, and Unicode surface order. Existing spoken forms and whether a profile rule is shadowed by an authoritative `sub` are shown separately.

With an explicitly enabled local spaCy tier, occurrences can include POS, proper-noun status, and lemma. `auto` never downloads models and may proceed without hints when no compatible local model is available; an explicit tier requires an installed model. spaCy OOV status is not used as an English classifier.

## Output formats

### Table

The default table lists surface, occurrence count, signals, current spoken form, effective profile replacement, and bounded source contexts. A profile rule covered by an existing `sub` is labelled as shadowed rather than treated as applied.

### JSON

JSON is deterministic and versioned with schema `ssmdconvert.speech-inventory`, version `1`. The top-level object contains `source`, selected `chapters`, `candidate_count`, `speech_profile` metadata (null when no profile is in effect, such as an unprofiled standalone source; otherwise schema, version, explicit/effective replacement counts, and canonical fingerprint), and grouped `candidates`. Candidate records include reasons, section IDs, existing spoken forms, profile replacement/shadow status, and bounded occurrence contexts with optional linguistic metadata.

### TOML template

`--format toml` emits a valid version-1 speech profile. Unresolved candidates are comments, never active entries with empty values. When an explicit profile or a bundle-local profile is selected, its explicit active entries and possessive-derivation setting are preserved; additional uncovered candidates are shown as commented suggestions. Review the template and fill in spoken forms before using it as a profile.

```toml
schema = "ssmdconvert-speech-profile"
version = 1
derive_possessives = true

[replacements]

# 4 occurrence(s); signals: hyphenated-initialism.
# "B-E" = ""
```

See [Speech replacement profiles](speech-profiles.md) for the profile schema, matching policy, and precedence contract.

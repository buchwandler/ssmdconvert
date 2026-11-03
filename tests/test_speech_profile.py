from __future__ import annotations

from pathlib import Path

import pytest
import ttsready

from ssmdconvert.speech.profile import (
    SpeechReplacementProfile,
    effective_replacements,
    empty_speech_profile,
    load_speech_profile,
    parse_speech_profile,
    render_speech_profile,
    speech_profile_fingerprint,
    with_speech_replacement,
    without_speech_replacement,
)

_VALID = """schema = "ssmdconvert-speech-profile"
version = 1

[replacements]
"ART" = "art"
"B-E" = "B E"
"""


def test_profile_parses_and_expands_only_english_possessives() -> None:
    profile = parse_speech_profile(_VALID)
    effective = effective_replacements(profile)

    assert dict(profile.replacements) == {"ART": "art", "B-E": "B E"}
    assert effective["ART"] == "art"
    assert effective["ART's"] == "art's"
    assert effective["ART’s"] == "art’s"
    assert effective["B-E"] == "B E"
    assert effective["B-E's"] == "B E's"
    assert "ARTS" not in effective
    assert "arts" not in effective
    assert isinstance(profile, SpeechReplacementProfile)
    with pytest.raises(TypeError):
        profile.replacements["new"] = "value"  # type: ignore[index]


def test_explicit_possessive_replacement_wins_over_derived_form() -> None:
    profile = parse_speech_profile(
        """schema = "ssmdconvert-speech-profile"
version = 1
[replacements]
"ART" = "art"
"ART’s" = "A R T possessive"
"""
    )

    effective = effective_replacements(profile)
    assert effective["ART’s"] == "A R T possessive"
    assert effective["ART's"] == "art's"


def test_possessive_derivation_can_be_disabled() -> None:
    profile = parse_speech_profile(
        """schema = "ssmdconvert-speech-profile"
version = 1
derive_possessives = false
[replacements]
"ART" = "art"
"""
    )

    assert dict(effective_replacements(profile)) == {"ART": "art"}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('version = 1\n[replacements]\n"ART" = "art"\n', "schema"),
        (_VALID.replace("ssmdconvert-speech-profile", "wrong", 1), "schema"),
        (_VALID.replace("version = 1", "version = 2", 1), "version"),
        ('schema = "ssmdconvert-speech-profile"\nversion = 1\n', "replacements"),
        (_VALID.replace('"ART" = "art"', '"" = "art"'), "keys"),
        (_VALID.replace('"ART" = "art"', '" ART " = "art"'), "keys"),
        (_VALID.replace('"ART" = "art"', '"ART" = "  "'), "values"),
        (_VALID.replace("[replacements]", "unexpected = true\n\n[replacements]"), "unknown"),
        (_VALID + "[extra]\nvalue = 1\n", "unknown"),
        ("schema = [not valid", "TOML"),
    ],
)
def test_invalid_profiles_are_rejected(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_speech_profile(text)


def test_profile_fingerprint_ignores_key_order_and_file_path(tmp_path: Path) -> None:
    first = parse_speech_profile(_VALID)
    second = parse_speech_profile(
        """version = 1
schema = "ssmdconvert-speech-profile"
[replacements]
"B-E" = "B E"
"ART" = "art"
"""
    )
    assert speech_profile_fingerprint(first) == speech_profile_fingerprint(second)

    left = tmp_path / "left.toml"
    right = tmp_path / "right.toml"
    left.write_text(_VALID, encoding="utf-8")
    right.write_text(_VALID, encoding="utf-8")
    assert speech_profile_fingerprint(load_speech_profile(left)) == speech_profile_fingerprint(
        load_speech_profile(right)
    )


def test_profile_fingerprint_changes_when_derivation_policy_changes() -> None:
    enabled = parse_speech_profile(_VALID)
    disabled = parse_speech_profile(
        _VALID.replace("version = 1", "version = 1\nderive_possessives = false")
    )
    assert speech_profile_fingerprint(enabled) != speech_profile_fingerprint(disabled)


def test_ttsready_word_override_matches_b_e_but_not_larger_hyphenated_surface() -> None:
    override = ttsready.SpeechOverride(
        surface="B-E",
        spoken="B E",
        match="word",
        case_sensitive=True,
    )

    matched = ttsready.prepare_units(
        [ttsready.TextUnit(id="matched", text="B-E security", language="en-US")],
        overrides=(override,),
        strict=False,
    ).units[0]
    unrelated = ttsready.prepare_units(
        [ttsready.TextUnit(id="unrelated", text="X-B-E-Y", language="en-US")],
        overrides=(override,),
        strict=False,
    ).units[0]

    assert matched.spoken_text == "B E security"
    assert len(matched.changes) == 1
    assert unrelated.spoken_text == "X-B-E-Y"
    assert unrelated.changes == ()


def test_empty_profile_round_trips_with_canonical_empty_replacements_table() -> None:
    profile = empty_speech_profile()
    rendered = render_speech_profile(profile)

    assert rendered == (
        'schema = "ssmdconvert-speech-profile"\n'
        "version = 1\n"
        "derive_possessives = true\n\n"
        "[replacements]\n"
    )
    assert parse_speech_profile(rendered) == profile


def test_profile_rendering_is_deterministic_sorted_and_toml_quoted() -> None:
    profile = parse_speech_profile(
        'schema = "ssmdconvert-speech-profile"\n'
        "version = 1\n"
        "[replacements]\n"
        '"z" = "back\\\\slash"\n'
        '"a\\"é" = "line\\nfeed \'quote\'"\n'
    )

    rendered = render_speech_profile(profile)
    assert rendered.endswith("\n") and not rendered.endswith("\n\n")
    assert rendered.index('"a\\"é"') < rendered.index('"z"')
    assert parse_speech_profile(rendered) == profile
    assert speech_profile_fingerprint(parse_speech_profile(rendered)) == speech_profile_fingerprint(
        profile
    )


def test_profile_mutators_return_independent_profiles() -> None:
    original = parse_speech_profile(_VALID)
    added = with_speech_replacement(original, "NEW", "New Name")
    updated = with_speech_replacement(added, "ART", "A R T")
    removed = without_speech_replacement(updated, "B-E")

    assert dict(original.replacements) == {"ART": "art", "B-E": "B E"}
    assert dict(added.replacements)["ART"] == "art"
    assert dict(updated.replacements)["ART"] == "A R T"
    assert dict(removed.replacements) == {"ART": "A R T", "NEW": "New Name"}
    assert original.derive_possessives is added.derive_possessives
    with pytest.raises(ValueError, match="no explicit replacement"):
        without_speech_replacement(original, "MISSING")

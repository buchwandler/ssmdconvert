from __future__ import annotations

from pathlib import Path

import pytest
import ttsready

from ssmdconvert.analysis import load_ssmd_source
from ssmdconvert.analysis.prepare import analyze_ssmd_source
from ssmdconvert.analysis.units import extract_units


def _write_source(tmp_path: Path, body: str, *, language: str | None = "en-US") -> Path:
    header = 'ssmd_version: "0.9"\ntitle: "Sample title"'
    if language is not None:
        header += f"\nlanguage: {language}"
    path = tmp_path / "sample.ssmd"
    path.write_text(f"---\n{header}\n---\n{body}\n", encoding="utf-8")
    return path


def test_inline_language_scopes_create_plain_explicit_language_runs(tmp_path: Path) -> None:
    path = _write_source(
        tmp_path,
        'English 5 kg, then [bonjour]{lang="fr-FR"} and English again.\n\n'
        '[AWS]{sub="Amazon Web Services"}; [SKU-42]{as="characters"}.',
    )
    source = load_ssmd_source(path)

    extracted = extract_units(source)

    assert [unit.language for unit in extracted.units] == [
        "en-US",
        "en-US",
        "fr-FR",
        "en-US",
        "en-US",
    ]
    # One title unit, three language runs in the first paragraph, and one paragraph-two unit.
    assert [unit.role for unit in extracted.units] == ["title", "prose", "prose", "prose", "prose"]
    assert extracted.units[0].text == "Sample title"
    runs = [unit.text for unit in extracted.units[1:4]]
    assert runs == ["English 5 kg, then ", "bonjour", " and English again."]
    assert all("[" not in unit.text and "{" not in unit.text for unit in extracted.units)
    assert extracted.units[-1].text == "AWS; SKU-42."
    assert extracted.units[-1].protected_spans
    assert (
        extracted.units[-1].text[
            extracted.units[-1].protected_spans[0].start : extracted.units[-1]
            .protected_spans[0]
            .end
        ]
        == "SKU-42"
    )
    assert extracted.overrides[0].surface == "AWS"
    assert extracted.overrides[0].spoken == "Amazon Web Services"
    assert extracted.overrides[0].provenance == {"origin": "ssmd", "annotation": "sub"}
    assert all(
        not isinstance(value, Path) for unit in extracted.units for value in unit.metadata.values()
    )
    assert [context.paragraph_index for context in extracted.contexts] == [-1, 1, 2]
    assert extracted.contexts[1].unit_ids == tuple(unit.id for unit in extracted.units[1:4])


def test_inline_language_is_explicit_and_cli_language_overrides_annotation(tmp_path: Path) -> None:
    path = _write_source(
        tmp_path,
        'English [bonjour]{lang="fr-FR"} end.',
    )
    source = load_ssmd_source(path)
    inline = extract_units(source)
    overridden = extract_units(source, language="de-DE")

    assert [unit.language for unit in inline.units if unit.role == "prose"] == [
        "en-US",
        "fr-FR",
        "en-US",
    ]
    assert [unit.language for unit in overridden.units if unit.role == "prose"] == ["de-DE"]
    assert overridden.units[-1].text == "English bonjour end."


def test_missing_language_is_structured_and_never_defaults_to_english(tmp_path: Path) -> None:
    path = _write_source(tmp_path, "Unspecified 5 kg.", language=None)
    source = load_ssmd_source(path)

    analysis = analyze_ssmd_source(source)

    assert analysis.preparation.units == ()
    assert analysis.effective_languages == ()
    assert any(issue.code == "analysis.language_unresolved" for issue in analysis.issues)
    assert analyze_ssmd_source(source, language="en-US").preparation.units


def test_author_sub_and_project_pronunciations_use_ttsready_override_api(tmp_path: Path) -> None:
    path = _write_source(
        tmp_path,
        '[AWS]{sub="Amazon Web Services"}; NASA and 5 kg.',
    )
    analysis = analyze_ssmd_source(path, pronunciations={"NASA": "N A S A"})

    changes = analysis.preparation.changes
    author_change = next(change for change in changes if change.source == "AWS")
    project_change = next(change for change in changes if change.source == "NASA")

    assert author_change.replacement == "Amazon Web Services"
    assert author_change.provenance["origin"] == "ssmd"
    assert author_change.provenance["annotation"] == "sub"
    assert project_change.replacement == "N A S A"
    assert project_change.provenance["origin"] == "ssmdconvert"
    assert project_change.provenance["source"] == "pronunciation-profile"
    assert all(change.id.startswith("chg:v1:") for change in changes)
    assert all(unit.unit_id.startswith("unit:v1:") for unit in analysis.preparation.units)


def test_sequence_fallback_policy_is_forwarded_to_public_ttsready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_source(tmp_path, "10-12.")
    original = ttsready.prepare_units
    seen: list[ttsready.PreparationProfile] = []

    def record(units: object, **kwargs: object) -> ttsready.PreparationResult:
        seen.append(kwargs["profile"])  # type: ignore[arg-type]
        return original(units, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ttsready, "prepare_units", record)
    analysis = analyze_ssmd_source(path, sequence_fallback_mode="spell")

    assert seen
    assert seen[0].sequence_fallback_mode == "spell"
    assert analysis.effective_sequence_fallback == "spell"


def test_stored_sequence_fallback_and_explicit_language_fallback_are_used(tmp_path: Path) -> None:
    path = tmp_path / "stored.ssmd"
    path.write_text(
        '---\nssmd_version: "0.9"\nlanguage: en-US\nsequence_fallback_mode: spell\n---\n10-12.\n',
        encoding="utf-8",
    )

    analysis = analyze_ssmd_source(path)

    assert analysis.stored_sequence_fallback == "spell"
    assert analysis.effective_sequence_fallback == "spell"

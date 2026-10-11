from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import ttsready

from ssmdconvert.analysis import load_ssmd_source
from ssmdconvert.analysis.prepare import analyze_ssmd_source
from ssmdconvert.analysis.units import extract_units
from ssmdconvert.errors import MaterializationError
from ssmdconvert.speech.workflows import materialize_analysis


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


def test_inline_language_scopes_remain_authoritative_over_cli_base_override(tmp_path: Path) -> None:
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
    assert overridden.units[0].role == "title"
    assert overridden.units[0].language == "de-DE"
    assert [unit.language for unit in overridden.units if unit.role == "prose"] == [
        "de-DE",
        "fr-FR",
        "de-DE",
    ]
    assert (
        "".join(unit.text for unit in overridden.units if unit.role == "prose")
        == "English bonjour end."
    )


def test_innermost_nested_language_annotation_beats_base_override(tmp_path: Path) -> None:
    path = _write_source(
        tmp_path,
        'Before [outer [bonjour]{lang="fr-FR"} after]{lang="de-DE"} end.',
    )

    extracted = extract_units(load_ssmd_source(path), language="it-IT")
    prose = [unit for unit in extracted.units if unit.role == "prose"]

    assert [unit.language for unit in prose] == [
        "it-IT",
        "de-DE",
        "fr-FR",
        "de-DE",
        "it-IT",
    ]
    assert [unit.text for unit in prose] == ["Before ", "outer ", "bonjour", " after", " end."]


def test_missing_language_is_structured_and_never_defaults_to_english(tmp_path: Path) -> None:
    path = _write_source(tmp_path, "Unspecified 5 kg.", language=None)
    source = load_ssmd_source(path)

    analysis = analyze_ssmd_source(source)

    assert analysis.preparation.units == ()
    assert analysis.effective_languages == ()
    assert not analysis.coverage.complete
    assert analysis.coverage.uncovered_context_ids
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



def test_unit_coverage_proves_exact_context_text_and_documents_excluded_titles(
    tmp_path: Path,
) -> None:
    path = _write_source(
        tmp_path,
        'A heading [1]{sub="one"}.\n\nText [SKU-42]{as="characters"}.',
    )
    source = load_ssmd_source(path)

    included = extract_units(source)
    body_only = extract_units(source, include_titles=False)

    assert included.coverage.complete
    assert included.coverage.narratable_contexts == included.coverage.covered_contexts == 3
    assert included.coverage.excluded_title_contexts == 0
    assert included.coverage.protected_units == 1
    assert body_only.coverage.complete
    assert body_only.coverage.narratable_contexts == body_only.coverage.covered_contexts == 2
    assert body_only.coverage.excluded_title_contexts == 1


def test_freeze_summary_uses_one_preparation_result_and_keeps_fingerprints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_source(tmp_path, '[AWS]{sub="Amazon Web Services"}; Measure 5 kg.')
    original = ttsready.prepare_units
    calls = 0

    def record(units: object, **kwargs: object) -> ttsready.PreparationResult:
        nonlocal calls
        calls += 1
        return original(units, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ttsready, "prepare_units", record)
    analysis = analyze_ssmd_source(path)

    assert calls == 1
    assert analysis.preparation.profile_fingerprint
    assert analysis.preparation.override_fingerprint
    assert analysis.preparation.runtime_fingerprint
    assert analysis.preparation.prepared_fingerprint
    assert analysis.coverage.complete

    def unexpected_prepare(*args: object, **kwargs: object) -> ttsready.PreparationResult:
        raise AssertionError("materialization must use the analyzed PreparationResult")

    monkeypatch.setattr(ttsready, "prepare_units", unexpected_prepare)
    materialized = materialize_analysis(analysis)

    assert calls == 1
    assert materialized.summary.complete
    assert materialized.summary.changes_total == len(analysis.preparation.changes)
    assert materialized.summary.applied > 0
    assert materialized.summary.already_authoritative == 1
    assert materialized.summary.unresolved == 0



def test_freeze_refuses_incomplete_narratable_coverage(tmp_path: Path) -> None:
    path = _write_source(tmp_path, "Measure 5 kg.")
    analysis = analyze_ssmd_source(path)
    incomplete_coverage = replace(
        analysis.coverage,
        covered_contexts=analysis.coverage.covered_contexts - 1,
        uncovered_context_ids=("injected-gap",),
    )

    with pytest.raises(MaterializationError, match="narratable-text coverage"):
        materialize_analysis(replace(analysis, coverage=incomplete_coverage))

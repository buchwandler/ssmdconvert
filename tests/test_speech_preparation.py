from __future__ import annotations

from pathlib import Path

import pytest

from ssmdconvert.analysis.prepare import analyze_ssmd_source
from ssmdconvert.errors import MaterializationError
from ssmdconvert.speech.audit import audit_ssmd
from ssmdconvert.speech.workflows import materialize_analysis


def _document(body: str, *, language: str | None = "en-US") -> str:
    language_line = f"language: {language}\n" if language is not None else ""
    return f'---\nssmd_version: "0.9"\n{language_line}---\n{body}\n'


def test_speech_audit_uses_ttsready_changes_and_keeps_generic_ids(tmp_path: Path) -> None:
    path = tmp_path / "audit.ssmd"
    path.write_text(_document("Measure 5 kg."), encoding="utf-8")

    report = audit_ssmd(path)

    assert report.mapped_changes
    assert report.mapped_changes[0].change.id.startswith("chg:v1:")
    assert report.mapped_changes[0].change.source == "5 kg"
    assert report.mapped_changes[0].change.replacement == "five kilograms"
    assert report.mapped_changes[0].change.provenance["origin"] == "spokenform"


def test_shared_materialization_preserves_visible_text_and_is_idempotent(tmp_path: Path) -> None:
    source = _document("Dr. Smith has 5 kg.")
    path = tmp_path / "source.ssmd"
    output = tmp_path / "annotated.ssmd"
    path.write_text(source, encoding="utf-8")

    analysis = analyze_ssmd_source(path)
    first = materialize_analysis(analysis)
    output.write_text(first.section_ssmd[analysis.sections[0].id], encoding="utf-8")

    frozen_analysis = analyze_ssmd_source(output)
    second = materialize_analysis(frozen_analysis)

    assert output.read_text(encoding="utf-8") != source
    assert "{sub=" in output.read_text(encoding="utf-8")
    assert (
        first.section_ssmd[analysis.sections[0].id]
        == second.section_ssmd[frozen_analysis.sections[0].id]
    )
    assert analysis.structures[analysis.sections[0].id].clean_text == (
        frozen_analysis.structures[frozen_analysis.sections[0].id].clean_text
    )
    assert path.read_text(encoding="utf-8") == source


def test_materialization_refuses_unresolved_language_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "unresolved.ssmd"
    path.write_text(_document("Measure 5 kg.", language=None), encoding="utf-8")
    analysis = analyze_ssmd_source(path)

    assert any(issue.code == "analysis.language_unresolved" for issue in analysis.issues)
    with pytest.raises(MaterializationError, match="language is unresolved"):
        materialize_analysis(analysis)

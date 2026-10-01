from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

import pytest
import spokenform
from ssmd import parse_structure

from ssmdconvert import (
    SpeechPreparationOptions,
    prepare_ssmd_for_speech,
)


def _document(body: str, *, language: str | None = "en") -> str:
    header = 'ssmd_version: "0.9"'
    if language is not None:
        header += f"\nlanguage: {language}"
    return f"---\n{header}\n---\n{body}\n"


def test_off_mode_returns_exact_source_without_calling_spokenform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("ssmdconvert.speech.prepare")

    def unexpected_call(*args: object, **kwargs: object) -> object:
        raise AssertionError("speech-off mode must not invoke spokenform")

    monkeypatch.setattr(module.spokenform, "prepare", unexpected_call)
    source = _document("Unchanged 5 kg.")
    result = prepare_ssmd_for_speech(source, options=SpeechPreparationOptions())

    assert result.ssmd == source
    assert result.report.changes == ()
    assert result.report.issues == ()
    assert result.report.languages == ()


def test_audit_calls_spokenform_on_plain_text_with_local_deterministic_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("ssmdconvert.speech.prepare")
    original_prepare = spokenform.prepare
    calls: list[tuple[str, dict[str, object]]] = []

    def recording_prepare(text: str, **kwargs: object) -> object:
        calls.append((text, kwargs))
        return original_prepare(text, **kwargs)

    monkeypatch.setattr(module.spokenform, "prepare", recording_prepare)
    source = _document('Hello *there*; use [NASA]{as="characters"}.')
    result = prepare_ssmd_for_speech(
        source,
        options=SpeechPreparationOptions(mode="audit"),
    )

    assert result.ssmd == source
    assert calls
    assert all("[" not in text and "{" not in text and "*" not in text for text, _ in calls)
    assert all(options["language"] == "en" for _, options in calls)
    assert all(options["use_spacy"] is False for _, options in calls)
    assert all(options["symbol_mode"] == "none" for _, options in calls)
    assert result.report.languages == ("en",)


def test_existing_speech_annotations_are_protected_from_spokenform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("ssmdconvert.speech.prepare")
    original_prepare = spokenform.prepare
    calls: list[str] = []

    def recording_prepare(text: str, **kwargs: object) -> object:
        calls.append(text)
        return original_prepare(text, **kwargs)

    monkeypatch.setattr(module.spokenform, "prepare", recording_prepare)
    source = _document(
        'Use [AWS]{sub="Amazon Web Services"}, call [+1-555-0123]{as="telephone"}, '
        'and say [tomato]{ph="təˈmeɪtoʊ"}.'
    )
    prepare_ssmd_for_speech(source, options=SpeechPreparationOptions(mode="audit"))

    assert calls
    joined = "".join(calls)
    assert "AWS" not in joined
    assert "+1-555-0123" not in joined
    assert "tomato" not in joined


def test_inline_language_annotations_split_runs_and_override_document_language() -> None:
    source = _document('English [5 kg]{lang="fr"}.')
    result = prepare_ssmd_for_speech(source, options=SpeechPreparationOptions(mode="audit"))

    assert result.report.languages == ("en", "fr")


def test_explicit_language_overrides_document_language() -> None:
    source = _document("5 kg.", language="de")
    result = prepare_ssmd_for_speech(
        source,
        options=SpeechPreparationOptions(mode="audit", language="en"),
    )

    assert result.report.languages == ("en",)


def test_audit_without_language_still_reports_unicode_and_skips_semantic_preparation() -> None:
    source = _document("The emblem is ☯.", language=None)
    result = prepare_ssmd_for_speech(source, options=SpeechPreparationOptions(mode="audit"))

    assert result.ssmd == source
    assert result.report.languages == ()
    assert any("No effective language" in warning for warning in result.report.warnings)
    assert any(issue.code == "speech.residual_symbol" for issue in result.report.issues)


def test_inline_language_run_is_processed_without_a_document_language() -> None:
    source = _document('Unspecified 5 kg; [5 kg]{lang="fr"}.', language=None)
    result = prepare_ssmd_for_speech(source, options=SpeechPreparationOptions(mode="audit"))

    assert result.report.languages == ("fr",)
    assert any("No effective language" in warning for warning in result.report.warnings)


def test_annotation_without_any_effective_language_fails_clearly() -> None:
    source = _document("H2O is important.", language=None)

    with pytest.raises(ValueError, match="speech annotation requires --language"):
        prepare_ssmd_for_speech(source, options=SpeechPreparationOptions(mode="annotate"))


def test_replacement_character_is_an_error_and_strict_mode_fails() -> None:
    source = _document("caf�.")
    result = prepare_ssmd_for_speech(source, options=SpeechPreparationOptions(mode="audit"))
    issue = next(item for item in result.report.issues if item.code == "source.decode_replacement")

    assert issue.severity == "error"
    assert issue.text == "�"
    assert issue.codepoint == "U+FFFD"
    assert issue.source_start == source.index("�")
    assert issue.source_end == issue.source_start + 1
    assert "original bytes cannot be recovered" in issue.message
    with pytest.raises(ValueError, match="Speech QC strict mode failed"):
        prepare_ssmd_for_speech(
            source,
            options=SpeechPreparationOptions(mode="audit", strict=True),
        )


def test_corrupt_text_run_is_not_sent_to_spokenform(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("ssmdconvert.speech.prepare")
    calls: list[str] = []

    def recording_prepare(text: str, **kwargs: object) -> object:
        calls.append(text)
        return spokenform.prepare(text, **kwargs)

    monkeypatch.setattr(module.spokenform, "prepare", recording_prepare)
    source = _document("caf�.")
    result = prepare_ssmd_for_speech(source, options=SpeechPreparationOptions(mode="audit"))

    assert calls == []
    assert any(issue.code == "source.decode_replacement" for issue in result.report.issues)


def test_residual_symbol_is_retained_and_reports_unicode_identity() -> None:
    source = _document("The emblem is ☯.")
    result = prepare_ssmd_for_speech(source, options=SpeechPreparationOptions(mode="audit"))
    issue = next(item for item in result.report.issues if item.code == "speech.residual_symbol")

    assert result.ssmd == source
    assert issue.severity == "warning"
    assert issue.text == "☯"
    assert issue.codepoint == "U+262F"
    assert issue.unicode_name == "YIN YANG"
    assert issue.source_start == source.index("☯")
    assert issue.source_end == issue.source_start + 1


def test_ordinary_prose_punctuation_does_not_generate_residual_issues() -> None:
    source = _document("One, two! Is this? (yes) - okay – sure — done; that's all.")
    result = prepare_ssmd_for_speech(source, options=SpeechPreparationOptions(mode="audit"))

    assert result.report.issues == ()


def test_audit_report_json_is_deterministic_and_exposes_replacement_provenance() -> None:
    source = _document("Dr. Smith has 5 kg.")
    options = SpeechPreparationOptions(mode="audit")
    first = prepare_ssmd_for_speech(source, options=options).report
    second = prepare_ssmd_for_speech(source, options=options).report
    payload = json.loads(first.to_json())

    assert first.to_json() == second.to_json()
    assert list(payload) == [
        "backend",
        "backend_version",
        "languages",
        "changes",
        "issues",
        "warnings",
    ]
    assert payload["backend"] == "spokenform"
    assert payload["backend_version"]
    assert payload["changes"]
    for change in payload["changes"]:
        assert change["status"] == "skipped"
        assert change["reason"] == "audit mode does not modify source"
        assert change["source_start"] is not None
        assert change["source_text"]
        assert change["spoken_text"]


def test_annotate_writes_sub_annotations_right_to_left_and_is_idempotent() -> None:
    source = _document("Dr. Smith has 5 kg and 12 km.")
    options = SpeechPreparationOptions(mode="annotate")
    before = parse_structure(source, dialect="0.9", normalize=False)

    first = prepare_ssmd_for_speech(source, options=options)
    after = parse_structure(first.ssmd, dialect="0.9", normalize=False)
    second = prepare_ssmd_for_speech(first.ssmd, options=options)

    assert first.ssmd != source
    assert after.clean_text == before.clean_text
    generated = [annotation for annotation in after.annotations if "sub" in annotation.attrs]
    assert [annotation.attrs["sub"] for annotation in generated] == [
        "Doctor",
        "five kilograms",
        "twelve kilometers",
    ]
    assert [change.status for change in first.report.changes] == ["applied"] * 3
    assert all(
        change.source_start is not None
        and change.source_end is not None
        and source[change.source_start : change.source_end] == change.source_text
        for change in first.report.changes
    )
    assert [change.source_start for change in first.report.changes] == sorted(
        change.source_start for change in first.report.changes if change.source_start is not None
    )
    assert second.ssmd == first.ssmd
    assert second.report.changes == ()


def test_project_glossary_uses_spokenform_profile_and_overrides_structured_rules() -> None:
    source = _document("H2O and H2O; remember 5 kg.")
    result = prepare_ssmd_for_speech(
        source,
        options=SpeechPreparationOptions(
            mode="annotate",
            pronunciations={"H2O": "water"},
        ),
    )

    assert result.ssmd.count('[H2O]{sub="water"}') == 2
    assert '[5 kg]{sub="five kilograms"}' in result.ssmd
    glossary_changes = [change for change in result.report.changes if change.kind == "glossary"]
    assert len(glossary_changes) == 2
    assert all(change.rule == "abbr:H2O" for change in glossary_changes)
    assert all(change.status == "applied" for change in glossary_changes)
    before = parse_structure(source, dialect="0.9", normalize=False)
    after = parse_structure(result.ssmd, dialect="0.9", normalize=False)
    assert after.clean_text == before.clean_text


def test_existing_author_sub_annotation_takes_precedence_over_project_glossary() -> None:
    source = _document('[H2O]{sub="author pronunciation"} and H2O.')
    result = prepare_ssmd_for_speech(
        source,
        options=SpeechPreparationOptions(
            mode="annotate",
            pronunciations={"H2O": "project pronunciation"},
        ),
    )

    assert '[H2O]{sub="author pronunciation"}' in result.ssmd
    assert '[H2O]{sub="project pronunciation"}' in result.ssmd
    assert sum(change.kind == "glossary" for change in result.report.changes) == 1


def test_generated_sub_alias_escapes_annotation_grammar_and_round_trips() -> None:
    pronunciation = 'say "yes" [now] {later} \\stop'
    source = _document("H2O.")
    result = prepare_ssmd_for_speech(
        source,
        options=SpeechPreparationOptions(
            mode="annotate",
            pronunciations={"H2O": pronunciation},
        ),
    )
    structure = parse_structure(result.ssmd, dialect="0.9", normalize=False)

    assert '\\"yes\\" \\[now\\] \\{later\\} \\\\stop' in result.ssmd
    annotation = next(
        annotation for annotation in structure.annotations if "sub" in annotation.attrs
    )
    assert annotation.attrs["sub"] == pronunciation


def test_escaped_source_leaf_with_an_inexact_map_is_not_annotated() -> None:
    source = _document(r"Take \*5 kg\*.")
    result = prepare_ssmd_for_speech(
        source,
        options=SpeechPreparationOptions(mode="annotate"),
    )

    assert result.ssmd == source
    assert any(
        change.status == "skipped"
        and change.reason
        == ("SSMD source leaf is escaped or normalized; source mapping is not exact")
        for change in result.report.changes
    )


def _fake_replacement(start: int, end: int, source_text: str, spoken_text: str) -> SimpleNamespace:
    return SimpleNamespace(
        source_start=start,
        source_end=end,
        source=source_text,
        replacement=spoken_text,
        language="en",
        kind="test",
        rule="test.rule",
    )


@pytest.mark.parametrize(
    ("replacements", "reason"),
    [
        (
            (_fake_replacement(0, 4, "abcd", "first"), _fake_replacement(3, 6, "def", "second")),
            "overlaps another replacement candidate",
        ),
        ((_fake_replacement(0, 3, "BAD", "replacement"),), "does not exactly match"),
    ],
)
def test_overlapping_and_source_mismatched_candidates_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    replacements: tuple[SimpleNamespace, ...],
    reason: str,
) -> None:
    module = importlib.import_module("ssmdconvert.speech.prepare")

    def fake_prepare(text: str, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(warnings=(), source_replacements=replacements)

    monkeypatch.setattr(module.spokenform, "prepare", fake_prepare)
    source = _document("abcdef.")
    result = prepare_ssmd_for_speech(
        source,
        options=SpeechPreparationOptions(mode="annotate"),
    )

    assert result.ssmd == source
    assert result.report.changes
    assert all(change.status == "skipped" for change in result.report.changes)
    assert all(reason in (change.reason or "") for change in result.report.changes)


def test_candidate_cannot_cross_a_plain_text_run_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("ssmdconvert.speech.prepare")

    def fake_prepare(text: str, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            warnings=(),
            source_replacements=(_fake_replacement(0, len(text) + 1, text + "x", "unsafe"),),
        )

    monkeypatch.setattr(module.spokenform, "prepare", fake_prepare)
    source = _document("plain *emphasis* text")
    result = prepare_ssmd_for_speech(
        source,
        options=SpeechPreparationOptions(mode="annotate"),
    )

    assert result.ssmd == source
    assert result.report.changes
    assert all(change.status == "skipped" for change in result.report.changes)


def test_candidate_cannot_cross_a_language_run_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("ssmdconvert.speech.prepare")
    calls: list[tuple[str, str]] = []

    def fake_prepare(text: str, **kwargs: object) -> SimpleNamespace:
        calls.append((text, str(kwargs["language"])))
        return SimpleNamespace(
            warnings=(),
            source_replacements=(_fake_replacement(0, len(text) + 1, text + "x", "unsafe"),),
        )

    monkeypatch.setattr(module.spokenform, "prepare", fake_prepare)
    source = _document('first [middle]{lang="fr"} last')
    result = prepare_ssmd_for_speech(
        source,
        options=SpeechPreparationOptions(mode="annotate"),
    )

    assert calls == [("first ", "en"), ("middle", "fr"), (" last", "en")]
    assert result.ssmd == source
    assert {change.language for change in result.report.changes} == {"en", "fr"}
    assert all(change.status == "skipped" for change in result.report.changes)

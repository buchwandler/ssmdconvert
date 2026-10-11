from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import ttsready
from ttsready import LinguisticToken

from ssmdconvert.analysis.prepare import analyze_ssmd_source
from ssmdconvert.linguistics import LinguisticsConfig
from ssmdconvert.progress import ProgressEvent


def _source(path: Path, text: str = "Measure 5 kg.") -> Path:
    path.write_text(
        f'---\nssmd_version: "0.9"\nlanguage: en-US\n---\n{text}\n',
        encoding="utf-8",
    )
    return path


def test_progress_events_are_immutable_json_safe_and_analysis_is_invariant(tmp_path: Path) -> None:
    event = ProgressEvent(
        "phase.completed",
        "analysis",
        completed=2,
        total=2,
        details={"counts": [1, 2], "fallback": None},
    )
    assert json.loads(json.dumps(event.to_dict()))["details"] == {
        "counts": [1, 2],
        "fallback": None,
    }
    with pytest.raises(TypeError):
        event.details["changed"] = True  # type: ignore[index]

    source = _source(tmp_path / "sample.ssmd")
    baseline = analyze_ssmd_source(source, include_titles=False)
    events: list[ProgressEvent] = []
    observed = analyze_ssmd_source(
        source,
        include_titles=False,
        linguistics=LinguisticsConfig("off"),
        on_progress=events.append,
    )

    assert ttsready.result_to_dict(observed.preparation) == ttsready.result_to_dict(
        baseline.preparation
    )
    assert events[0].kind == "phase.started" and events[0].phase == "analysis"
    assert events[-1].kind == "phase.completed" and events[-1].phase == "analysis"
    prepared_units = [
        event
        for event in events
        if event.phase == "speech.prepare" and event.kind == "unit.completed"
    ]
    assert [event.completed for event in prepared_units] == list(range(1, len(prepared_units) + 1))
    assert all(event.total == len(prepared_units) for event in prepared_units)


def test_callback_exceptions_escape_analysis_unchanged(tmp_path: Path) -> None:
    source = _source(tmp_path / "sample.ssmd")

    def cancel(event: ProgressEvent) -> None:
        if event.phase == "speech.prepare" and event.kind == "unit.started":
            raise ValueError("cancel from observer")

    with pytest.raises(ValueError, match="cancel from observer"):
        analyze_ssmd_source(source, include_titles=False, on_progress=cancel)


def test_spacy_hints_reach_ttsready_and_respect_protected_ssmd_spans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded_models: list[str] = []
    prepared_inputs: list[tuple[ttsready.TextUnit, ...]] = []
    original_prepare = ttsready.prepare_units

    def load_model(name: str):
        loaded_models.append(name)

        def analyze(text: str):
            return (
                type(
                    "Token",
                    (),
                    {
                        "idx": 0,
                        "text": text,
                        "pos_": "NOUN",
                        "tag_": "NN",
                        "lemma_": text.lower(),
                    },
                )(),
            )

        return analyze

    fake_spacy = SimpleNamespace(
        __version__="3.8.0",
        util=SimpleNamespace(get_installed_models=lambda: ("en_core_web_sm",)),
        load=load_model,
    )
    monkeypatch.setitem(sys.modules, "spacy", fake_spacy)
    monkeypatch.setattr(
        "ssmdconvert.linguistics.version",
        lambda name: "3.8.0" if name == "spacy" else "1.0.0",
    )

    def capture(units, **kwargs):
        materialized = tuple(units)
        prepared_inputs.append(materialized)
        return original_prepare(materialized, **kwargs)

    monkeypatch.setattr(ttsready, "prepare_units", capture)
    source = _source(tmp_path / "protected.ssmd", '[SKU-42]{as="characters"}')
    events: list[ProgressEvent] = []

    analysis = analyze_ssmd_source(
        source,
        include_titles=False,
        linguistics=LinguisticsConfig("sm"),
        on_progress=events.append,
    )

    assert loaded_models == ["en_core_web_sm"]
    assert prepared_inputs[0][0].linguistic_tokens == (
        LinguisticToken(
            0, 6, text="SKU-42", pos="NOUN", tag="NN", lemma="sku-42", language="en-US"
        ),
    )
    assert analysis.preparation.units[0].spoken_text == "SKU-42"
    assert [event.kind for event in events if event.phase == "linguistics.model"] == [
        "model.started",
        "model.completed",
    ]


def test_spacy_enrichment_uses_inline_language_scopes_before_base_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded_models: list[str] = []
    analyzed: list[tuple[str, str]] = []

    def load_model(name: str):
        loaded_models.append(name)

        def analyze(text: str):
            analyzed.append((name, text))
            return ()

        return analyze

    fake_spacy = SimpleNamespace(
        util=SimpleNamespace(get_installed_models=lambda: ("de_core_news_sm", "fr_core_news_sm")),
        load=load_model,
    )
    monkeypatch.setitem(sys.modules, "spacy", fake_spacy)
    monkeypatch.setattr("ssmdconvert.linguistics.version", lambda _name: "1.0.0")
    source = _source(
        tmp_path / "scoped.ssmd",
        'English [bonjour]{lang="fr-FR"} end.',
    )

    analyze_ssmd_source(
        source,
        language="de-DE",
        include_titles=False,
        linguistics=LinguisticsConfig("auto"),
    )

    assert loaded_models == ["de_core_news_sm", "fr_core_news_sm"]
    assert analyzed == [
        ("de_core_news_sm", "English "),
        ("fr_core_news_sm", "bonjour"),
        ("de_core_news_sm", " end."),
    ]

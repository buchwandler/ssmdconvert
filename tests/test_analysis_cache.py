from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ssmdconvert.analysis.cache import AnalysisCache, analyze_with_cache
from ssmdconvert.errors import AnalysisCacheError
from ssmdconvert.linguistics import LinguisticsConfig


def _source(path: Path, body: str = "Measure 5 kg.") -> Path:
    path.write_text(
        f'---\nssmd_version: "0.9"\nlanguage: en-US\n---\n{body}\n',
        encoding="utf-8",
    )
    return path


def test_chapter_cache_reuse_refresh_and_path_independent_analysis_ids(tmp_path: Path) -> None:
    cache = AnalysisCache(tmp_path / "cache")
    first_source = _source(tmp_path / "first.ssmd")
    first = analyze_with_cache(first_source, cache=cache, max_paragraph_chars=None)
    repeated = analyze_with_cache(first_source, cache=cache, max_paragraph_chars=None)

    assert first.chapter_cache_misses == 1
    assert first.chapter_cache_hits == 0
    assert repeated.chapter_cache_hits == 1
    assert repeated.chapter_cache_misses == 0
    assert first.analysis_id == repeated.analysis_id
    assert first.analysis.preparation.changes

    second_source = _source(tmp_path / "second.ssmd")
    copied = analyze_with_cache(second_source, cache=cache, max_paragraph_chars=None)
    assert copied.analysis_id == first.analysis_id
    assert copied.chapter_cache_hits == 1
    assert len(list((cache.root / "analyses").glob("*.json"))) == 2
    assert cache.snapshots_for_source(second_source)[0]["source"]["path"] == str(
        second_source.resolve()
    )

    refreshed = analyze_with_cache(
        first_source,
        cache=cache,
        max_paragraph_chars=None,
        refresh=True,
    )
    assert refreshed.analysis_id == first.analysis_id
    assert refreshed.chapter_cache_misses == 1
    assert refreshed.chapter_cache_hits == 0

    changed_source = _source(first_source, "Measure 6 kg.")
    changed = analyze_with_cache(changed_source, cache=cache, max_paragraph_chars=None)
    assert changed.analysis_id != first.analysis_id
    assert changed.chapter_cache_misses == 1


def test_snapshot_checksum_rejects_tampering(tmp_path: Path) -> None:
    source = _source(tmp_path / "sample.ssmd")
    cache = AnalysisCache(tmp_path / "cache")
    analyze_with_cache(source, cache=cache, max_paragraph_chars=None)
    path = next((cache.root / "analyses").glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["app"]["report"]["source"]["title"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AnalysisCacheError, match="checksum does not match"):
        cache.snapshots_for_source(source)


def test_analysis_id_tracks_source_bytes_and_has_expected_sha256_shape(tmp_path: Path) -> None:
    source = _source(tmp_path / "sample.ssmd")
    cache = AnalysisCache(tmp_path / "cache")
    result = analyze_with_cache(source, cache=cache, max_paragraph_chars=None)
    snapshot = cache.snapshots_for_source(source)[0]

    assert result.analysis_id.startswith("ana:v1:")
    assert snapshot["source"]["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert snapshot["source"]["content_fingerprint"] == result.report.source.content_fingerprint


def test_linguistics_policy_and_model_versions_fingerprint_cache_without_hit_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    versions = {
        "spacy": "3.8.0",
        "en_core_web_sm": "1.0.0",
        "en_core_web_md": "1.0.0",
    }
    loaded_models: list[str] = []
    analyzed_texts: list[str] = []
    downloads: list[str] = []

    def load_model(name: str):
        loaded_models.append(name)

        def analyze(text: str):
            analyzed_texts.append(text)
            return ()

        return analyze

    fake_spacy = SimpleNamespace(
        __version__="3.8.0",
        util=SimpleNamespace(get_installed_models=lambda: ("en_core_web_sm", "en_core_web_md")),
        load=load_model,
        download=downloads.append,
    )
    monkeypatch.setitem(sys.modules, "spacy", fake_spacy)
    monkeypatch.setattr(
        "ssmdconvert.linguistics.version",
        lambda name: versions.get(name, "unknown"),
    )

    source = _source(tmp_path / "sample.ssmd")
    cache = AnalysisCache(tmp_path / "cache")

    def analyze(config: LinguisticsConfig):
        return analyze_with_cache(
            source,
            cache=cache,
            include_titles=False,
            max_paragraph_chars=None,
            linguistics=config,
        )

    off = analyze(LinguisticsConfig("off"))
    off_hit = analyze(LinguisticsConfig("off"))
    assert off.chapter_cache_misses == 1
    assert off_hit.chapter_cache_hits == 1
    assert analyzed_texts == []

    small = analyze(LinguisticsConfig("sm"))
    small_hit = analyze(LinguisticsConfig("sm"))
    assert small.chapter_cache_misses == 1
    assert small_hit.chapter_cache_hits == 1
    assert analyzed_texts == ["Measure 5 kg."]
    assert loaded_models == ["en_core_web_sm"]

    versions["en_core_web_sm"] = "2.0.0"
    changed_model = analyze(LinguisticsConfig("sm"))
    assert changed_model.chapter_cache_misses == 1
    assert changed_model.analysis_id != small.analysis_id
    assert len(analyzed_texts) == 2

    versions["spacy"] = "3.9.0"
    changed_spacy = analyze(LinguisticsConfig("sm"))
    assert changed_spacy.chapter_cache_misses == 1
    assert changed_spacy.analysis_id != changed_model.analysis_id
    assert len(analyzed_texts) == 3

    automatic = analyze(LinguisticsConfig("auto"))
    assert automatic.chapter_cache_misses == 1
    assert automatic.analysis_id != changed_spacy.analysis_id
    medium = analyze(LinguisticsConfig("md"))
    assert medium.chapter_cache_misses == 1
    assert medium.analysis_id != automatic.analysis_id
    assert loaded_models[-1] == "en_core_web_md"
    assert downloads == []


def test_cache_progress_reports_chapter_and_hit_miss_counts(tmp_path: Path) -> None:
    source = _source(tmp_path / "sample.ssmd")
    cache = AnalysisCache(tmp_path / "cache")
    first_events = []
    repeated_events = []

    first = analyze_with_cache(
        source,
        cache=cache,
        include_titles=False,
        max_paragraph_chars=None,
        on_progress=first_events.append,
    )
    repeated = analyze_with_cache(
        source,
        cache=cache,
        include_titles=False,
        max_paragraph_chars=None,
        on_progress=repeated_events.append,
    )

    assert first.chapter_cache_misses == 1
    assert repeated.chapter_cache_hits == 1
    chapter_events = [
        event
        for event in first_events
        if event.phase == "analysis.cache" and event.kind.startswith("chapter.")
    ]
    assert [(event.kind, event.completed, event.total) for event in chapter_events] == [
        ("chapter.started", 0, 1),
        ("chapter.completed", 1, 1),
    ]
    assert any(event.kind == "cache.miss" for event in first_events)
    assert any(event.kind == "cache.hit" for event in repeated_events)
    assert not any(event.phase == "speech.prepare" for event in repeated_events)
    assert first_events[-1].phase == "analysis.cache"
    assert first_events[-1].details == {"hits": 0, "misses": 1}


def test_cached_analysis_propagates_progress_callback_exceptions(tmp_path: Path) -> None:
    source = _source(tmp_path / "sample.ssmd")

    def cancel(event):
        if event.phase == "speech.prepare" and event.kind == "unit.started":
            raise ValueError("cancel cached analysis")

    with pytest.raises(ValueError, match="cancel cached analysis"):
        analyze_with_cache(
            source,
            cache=AnalysisCache(tmp_path / "cache"),
            include_titles=False,
            max_paragraph_chars=None,
            on_progress=cancel,
        )

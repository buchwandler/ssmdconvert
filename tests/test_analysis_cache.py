from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ssmdconvert.analysis.cache import AnalysisCache, analyze_with_cache
from ssmdconvert.errors import AnalysisCacheError


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

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ssmd import parse_structure

from ssmdconvert.analysis.prepare import analyze_ssmd_source
from ssmdconvert.speech.mapping import map_analysis_changes
from ssmdconvert.speech.workflows import materialize_analysis


def _document(body: str) -> str:
    return f'---\nssmd_version: "0.9"\nlanguage: en-US\n---\n{body}\n'


def _write_source(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(_document(body), encoding="utf-8")
    return path


def test_synthetic_speech_freeze_integrates_consistency_slashes_and_is_idempotent(
    tmp_path: Path,
) -> None:
    body = (
        "Because someone (ART) approved it. ART’s module stayed open.\n\n"
        "Later ART checked the open/close control and asked where/who.\n\n"
        "target/destination head/processor torus/whatever we/somebody "
        "where/who proximity/safety"
    )
    source_path = _write_source(tmp_path, "synthetic.ssmd", body)
    analysis = analyze_ssmd_source(source_path, include_titles=False)
    changes = analysis.preparation.changes

    seed = next(
        change
        for change in changes
        if change.source == "ART" and change.provenance.get("origin") == "spokenform"
    )
    possessive = next(change for change in changes if change.source == "ART’s")
    propagated_bare = next(
        change
        for change in changes
        if change.source == "ART" and change.provenance.get("origin") == "ttsready.consistency"
    )
    assert seed.replacement == "A R T"
    assert possessive.replacement == "A R T’s"
    assert possessive.provenance["origin"] == "ttsready.consistency"
    assert possessive.provenance["seed_change_id"] == seed.id
    assert possessive.provenance["seed_rule"] == seed.rule
    assert propagated_bare.replacement == "A R T"
    assert propagated_bare.provenance["seed_change_id"] == seed.id

    slash_speech = {
        "open/close": "open slash close",
        "where/who": "where slash who",
        "target/destination": "target slash destination",
        "head/processor": "head slash processor",
        "torus/whatever": "torus slash whatever",
        "we/somebody": "we slash somebody",
        "proximity/safety": "proximity slash safety",
    }
    slash_changes = [change for change in changes if change.source in slash_speech]
    assert Counter(change.source for change in slash_changes) == Counter(
        {
            "open/close": 1,
            "where/who": 2,
            "target/destination": 1,
            "head/processor": 1,
            "torus/whatever": 1,
            "we/somebody": 1,
            "proximity/safety": 1,
        }
    )
    for change in slash_changes:
        assert change.replacement == slash_speech[change.source]
        assert change.provenance["origin"] == "spokenform"

    mapped = map_analysis_changes(analysis)
    assert mapped
    assert all(item.mapping_status == "exact" for item in mapped)
    assert all(item.materialization_status == "available" for item in mapped)
    section = analysis.sections[0]
    spans = []
    for item in mapped:
        assert item.raw_source_start is not None and item.raw_source_end is not None
        assert section.ssmd[item.raw_source_start : item.raw_source_end] == item.change.source
        spans.append((item.raw_source_start, item.raw_source_end))
    ordered_spans = sorted(spans)
    assert all(
        left[1] <= right[0] for left, right in zip(ordered_spans, ordered_spans[1:], strict=False)
    )

    frozen_result = materialize_analysis(analysis)
    frozen = frozen_result.section_ssmd[section.id]
    assert frozen_result.summary.complete
    assert frozen_result.summary.unresolved == 0
    expected_alias_counts = {
        '[ART]{sub="A R T"}': 2,
        '[ART’s]{sub="A R T’s"}': 1,
        '[open/close]{sub="open slash close"}': 1,
        '[where/who]{sub="where slash who"}': 2,
        '[target/destination]{sub="target slash destination"}': 1,
        '[head/processor]{sub="head slash processor"}': 1,
        '[torus/whatever]{sub="torus slash whatever"}': 1,
        '[we/somebody]{sub="we slash somebody"}': 1,
        '[proximity/safety]{sub="proximity slash safety"}': 1,
    }
    for alias, count in expected_alias_counts.items():
        assert frozen.count(alias) == count
    assert "[/]{sub=" not in frozen
    assert '{sub="slash"}' not in frozen

    before = parse_structure(section.ssmd, dialect="0.9", normalize=False)
    after = parse_structure(frozen, dialect="0.9", normalize=False)
    assert after.clean_text == before.clean_text

    frozen_path = tmp_path / "already-frozen.ssmd"
    frozen_path.write_text(frozen, encoding="utf-8")
    second_analysis = analyze_ssmd_source(frozen_path, include_titles=False)
    second_result = materialize_analysis(second_analysis)
    assert second_result.section_ssmd[second_analysis.sections[0].id] == frozen
    assert second_result.summary.complete


def test_existing_art_sub_alias_remains_authoritative(tmp_path: Path) -> None:
    source_path = _write_source(
        tmp_path,
        "author-alias.ssmd",
        'Because [ART]{sub="A R T"} was already annotated.',
    )
    analysis = analyze_ssmd_source(source_path, include_titles=False)
    mapped = map_analysis_changes(analysis)
    author_alias = next(item for item in mapped if item.change.source == "ART")

    assert author_alias.materialization_status == "already-authoritative"
    result = materialize_analysis(analysis)
    assert result.section_ssmd[analysis.sections[0].id] == analysis.sections[0].ssmd
    assert result.section_ssmd[analysis.sections[0].id].count('[ART]{sub="A R T"}') == 1

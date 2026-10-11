from __future__ import annotations

from pathlib import Path

import pytest
from epub_support import make_epub

from ssmdconvert import (
    AnalysisOptions,
    BookConversionOptions,
    SpeechFreezeFailure,
    SpeechOptions,
    TextProjectionOptions,
    analyze_cached,
    analyze_ssmd,
    audit_speech,
    build_report,
    convert_book,
    freeze_speech,
    lookup_cached_context,
    lookup_change_context,
    project_text,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ssmd-speech-handoff" / "reviewed.ssmd"


def test_in_memory_book_analysis_needs_no_temporary_bundle(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    converted = convert_book(
        source,
        options=BookConversionOptions(speech=SpeechOptions(mode="preserve")),
    )

    from_result = analyze_ssmd(converted, options=AnalysisOptions(spacy="off"))
    from_book = analyze_ssmd(converted.book, options=AnalysisOptions(spacy="off"))

    assert from_result.source.workspace_type == "generated"
    assert [section.id for section in from_result.sections] == [
        chapter.id for chapter in converted.book.chapters
    ]
    assert from_book.source.content_fingerprint == from_result.source.content_fingerprint
    assert list(tmp_path.iterdir()) == [source]


def test_analysis_projection_report_audit_and_freeze_share_in_memory_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = analyze_ssmd(FIXTURE, options=AnalysisOptions(spacy="off"))
    from ssmdconvert.analysis import prepare as prepare_module

    def fail_reanalysis(*args: object, **kwargs: object) -> None:
        raise AssertionError("an existing analysis must not be prepared again")

    monkeypatch.setattr(prepare_module, "analyze_ssmd_source", fail_reanalysis)
    projection = project_text(
        analysis,
        options=TextProjectionOptions(max_paragraph_chars=None),
    )
    report = build_report(analysis, projection=projection)
    audit = audit_speech(analysis)

    assert projection.text
    assert report.projection == projection.stats
    assert report.reproducibility.prepared_output_sha256 == projection.stats.prepared_output_sha256
    assert report.preparation.prepared_fingerprint == analysis.preparation.prepared_fingerprint
    assert audit.preparation.prepared_fingerprint == analysis.preparation.prepared_fingerprint

    frozen = freeze_speech(analysis)
    assert frozen.status == "complete"
    assert frozen.speech.to_dict()["complete"] is True
    assert set(frozen.sections) == {section.id for section in analysis.sections}
    assert isinstance(frozen.changes, tuple)


def test_change_context_accepts_analysis_and_typed_report() -> None:
    analysis = analyze_ssmd(FIXTURE, options=AnalysisOptions(spacy="off"))
    change_id = analysis.preparation.changes[0].id
    report = build_report(analysis)

    from_analysis = lookup_change_context(analysis, change_id)
    from_report = lookup_change_context(report, change_id)

    assert from_analysis.change.change.id == change_id
    assert from_analysis.source_text
    assert from_analysis.spoken_text
    assert from_report.change == from_analysis.change
    assert from_report.source_sentences == from_analysis.source_sentences


def test_cached_analysis_and_disk_context_are_explicit(tmp_path: Path) -> None:
    cache_root = tmp_path / "analysis-cache"
    options = AnalysisOptions(spacy="off")
    cached = analyze_cached(FIXTURE, options=options, cache_root=cache_root)
    repeated = analyze_cached(FIXTURE, options=options, cache_root=cache_root)

    assert cached.chapter_cache_misses > 0
    assert repeated.chapter_cache_hits > 0
    assert cached.analysis_id == repeated.analysis_id
    assert cache_root.is_dir()

    change_id = cached.report.mapped_changes[0].change.id
    context = lookup_cached_context(FIXTURE, change_id, cache_root=cache_root)
    assert context["change"]["id"] == change_id


def test_in_memory_freeze_surfaces_structured_incomplete_evidence(tmp_path: Path) -> None:
    source = tmp_path / "unresolved.epub"
    make_epub(source, language=None, chapter_language=None)
    converted = convert_book(
        source,
        options=BookConversionOptions(speech=SpeechOptions(mode="preserve")),
    )
    analysis = analyze_ssmd(converted, options=AnalysisOptions(spacy="off"))

    with pytest.raises(SpeechFreezeFailure) as caught:
        freeze_speech(analysis)

    assert caught.value.report["status"] == "incomplete"
    assert caught.value.report["failure"]

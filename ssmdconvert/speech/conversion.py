"""Conversion-time speech materialization for in-memory SSMD books."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ..analysis.models import SsmdAnalysis
from ..analysis.prepare import analyze_ssmd_source
from ..analysis.source import loaded_source_from_book
from ..linguistics import LinguisticsConfig
from ..models import Book
from ..policy import SequenceFallbackMode
from ..progress import ProgressCallback, emit_progress
from .failures import make_speech_freeze_failure
from .provenance import build_speech_provenance
from .workflows import AnalysisMaterialization, materialize_analysis


@dataclass(frozen=True, slots=True)
class BookSpeechMaterialization:
    """Materialized book and the analysis evidence used to produce it."""

    book: Book
    analysis: SsmdAnalysis
    materialization: AnalysisMaterialization


def materialize_book_speech(
    book: Book,
    *,
    source_path: Path,
    language: str | None = None,
    sequence_fallback_mode: SequenceFallbackMode | None = None,
    linguistics: LinguisticsConfig | None = None,
    on_progress: ProgressCallback | None = None,
) -> BookSpeechMaterialization:
    """Freeze safe automatic speech decisions into the selected book's SSMD."""
    emit_progress(on_progress, "phase.started", "speech.materialize")
    loaded = loaded_source_from_book(
        book,
        path=source_path,
        workspace_type="generated",
        workspace_status="clean",
    )
    analysis = analyze_ssmd_source(
        loaded,
        chapters="all",
        language=language,
        sequence_fallback_mode=sequence_fallback_mode,
        include_titles=False,
        linguistics=linguistics,
        on_progress=on_progress,
    )
    if any(issue.code == "analysis.language_unresolved" for issue in analysis.issues):
        raise make_speech_freeze_failure(
            analysis,
            "cannot freeze speech semantics because no effective language could be resolved; "
            "pass --language <LANG> or use --speech-semantics preserve",
        )
    if not analysis.coverage.complete:
        raise make_speech_freeze_failure(
            analysis,
            "cannot freeze book speech semantics because narratable-text coverage is incomplete",
        )
    expected_excluded_titles = sum(bool(chapter.title) for chapter in book.chapters)
    if analysis.coverage.excluded_title_contexts != expected_excluded_titles:
        raise make_speech_freeze_failure(
            analysis,
            "cannot verify intentionally excluded book metadata titles during speech freezing",
        )
    emit_progress(on_progress, "phase.started", "speech.materialize.apply")
    try:
        materialization = materialize_analysis(analysis)
    except Exception as exc:
        raise make_speech_freeze_failure(analysis, str(exc)) from exc
    if not materialization.summary.complete:
        raise make_speech_freeze_failure(
            analysis,
            "cannot return a book with incomplete speech semantics "
            f"({materialization.summary.unresolved} unresolved changes)",
        )
    chapters = tuple(
        replace(
            chapter,
            ssmd=materialization.section_ssmd.get(chapter.id, chapter.ssmd),
        )
        for chapter in book.chapters
    )
    emit_progress(
        on_progress,
        "phase.completed",
        "speech.materialize.apply",
        completed=len(materialization.section_ssmd),
        total=len(materialization.section_ssmd),
    )
    result = BookSpeechMaterialization(
        book=replace(
            book,
            chapters=chapters,
            speech_semantics=build_speech_provenance(analysis),
        ),
        analysis=analysis,
        materialization=materialization,
    )
    emit_progress(
        on_progress,
        "phase.completed",
        "speech.materialize",
        completed=len(book.chapters),
        total=len(book.chapters),
    )
    return result

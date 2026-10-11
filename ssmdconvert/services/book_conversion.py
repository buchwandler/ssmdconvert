"""Shared application service for EPUB conversion and speech disposition."""

from __future__ import annotations

from pathlib import Path

from ..books import convert_book as _convert_structural_book
from ..linguistics import LinguisticsConfig
from ..options import BookConversionOptions, thaw_metadata
from ..progress import ProgressCallback
from ..results import BookConversionResult, SpeechOutcome, report_mapping
from ..speech.conversion import materialize_book_speech
from ..speech.reporting import build_preserved_speech_report, build_speech_freeze_report


def convert_book_pipeline(
    source: str | Path,
    options: BookConversionOptions,
    *,
    on_progress: ProgressCallback | None = None,
) -> BookConversionResult:
    """Convert selected EPUB chapters once, then preserve or freeze speech semantics."""
    if not isinstance(options, BookConversionOptions):
        raise TypeError("options must be a BookConversionOptions instance")

    book = _convert_structural_book(
        source,
        chapters=options.chapters,
        language=options.language,
        metadata_overrides=thaw_metadata(options.metadata_overrides),
        sequence_fallback_mode=options.sequence_fallback_mode,
        speech_semantics="preserve",
        on_progress=on_progress,
    )
    if options.speech.mode == "preserve":
        report = build_preserved_speech_report(book.source_sha256)
        return BookConversionResult(
            book=book,
            speech=SpeechOutcome(status="preserved", summary=None, report=report),
            issues=(),
        )

    source_path = book.source.path
    if source_path is None:
        raise ValueError("converted EPUB book is missing its source path")
    materialization = materialize_book_speech(
        book,
        source_path=source_path,
        language=options.language,
        sequence_fallback_mode=options.sequence_fallback_mode,
        linguistics=LinguisticsConfig(spacy=options.speech.spacy),
        on_progress=on_progress,
    )
    report = build_speech_freeze_report(
        materialization.analysis,
        materialization.materialization.changes,
        materialization.materialization.summary,
    )
    issues = (*materialization.analysis.issues, *materialization.materialization.issues)
    return BookConversionResult(
        book=materialization.book,
        speech=SpeechOutcome(
            status="complete",
            summary=materialization.materialization.summary,
            report=report_mapping(report),
            analysis_id=None,
        ),
        issues=issues,
    )

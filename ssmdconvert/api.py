"""Stable application-facing Python API.

The command-line interface adapts arguments and output policy around these
side-effect-limited operations; artifact publication remains explicit.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .converter import ContentInputFormat, Converter
from .models import Book, ConversionResult, Document
from .options import (
    AnalysisOptions,
    BookConversionOptions,
    DocumentConversionOptions,
    TextProjectionOptions,
    thaw_metadata,
)
from .progress import ProgressCallback
from .results import (
    BookConversionResult,
    SpeechFreezeResult,
    SpeechOutcome,
    SsmdChangeContext,
)

if TYPE_CHECKING:
    from .analysis.cache import CachedAnalysis
    from .analysis.models import LoadedSsmdSource, SsmdAnalysis, SsmdAnalysisReport
    from .analysis.projection import ProjectedText


def inspect_document(source: str | Path) -> Document:
    """Load a supported document into the normalized in-memory model."""
    return Converter().load(source)


def convert_document(
    source: str | Path,
    *,
    options: DocumentConversionOptions | None = None,
) -> ConversionResult:
    """Convert one supported source document to standalone SSMD in memory."""
    selected = DocumentConversionOptions() if options is None else options
    if not isinstance(selected, DocumentConversionOptions):
        raise TypeError("options must be a DocumentConversionOptions instance")
    return Converter().convert(
        source,
        title=selected.title,
        author=selected.author,
        language=selected.language,
        metadata_overrides=thaw_metadata(selected.metadata_overrides),
        sequence_fallback_mode=selected.sequence_fallback_mode,
    )


def convert_content(
    content: str,
    *,
    input_format: ContentInputFormat,
    source_name: str = "<memory>",
    options: DocumentConversionOptions | None = None,
) -> ConversionResult:
    """Convert in-memory text, Markdown, or HTML to standalone SSMD."""
    selected = DocumentConversionOptions() if options is None else options
    if not isinstance(selected, DocumentConversionOptions):
        raise TypeError("options must be a DocumentConversionOptions instance")
    return Converter().convert_content(
        content,
        input_format=input_format,
        source_name=source_name,
        title=selected.title,
        language=selected.language,
        metadata_overrides=thaw_metadata(selected.metadata_overrides),
        sequence_fallback_mode=selected.sequence_fallback_mode,
    )


def convert_book(
    source: str | Path,
    *,
    options: BookConversionOptions | None = None,
    on_progress: ProgressCallback | None = None,
) -> BookConversionResult:
    """Convert an EPUB and return its book plus freeze/preserve evidence."""
    selected = BookConversionOptions() if options is None else options
    if not isinstance(selected, BookConversionOptions):
        raise TypeError("options must be a BookConversionOptions instance")
    from .services.book_conversion import convert_book_pipeline

    return convert_book_pipeline(source, selected, on_progress=on_progress)


def analyze_ssmd(
    source: str | Path | Book | BookConversionResult,
    *,
    options: AnalysisOptions | None = None,
    on_progress: ProgressCallback | None = None,
) -> SsmdAnalysis:
    """Analyze SSMD or an in-memory book without writing temporary artifacts or caches."""
    selected = AnalysisOptions() if options is None else options
    if not isinstance(selected, AnalysisOptions):
        raise TypeError("options must be an AnalysisOptions instance")

    from .analysis.prepare import analyze_ssmd_source
    from .analysis.source import loaded_source_from_book
    from .linguistics import LinguisticsConfig

    def loaded_book(book: Book) -> LoadedSsmdSource:
        return loaded_source_from_book(
            book,
            path=book.source.path or Path("<memory>"),
            workspace_type="generated",
            workspace_status="clean",
        )

    loaded: LoadedSsmdSource | str | Path
    if isinstance(source, BookConversionResult):
        loaded = loaded_book(source.book)
    elif isinstance(source, Book):
        loaded = loaded_book(source)
    else:
        loaded = source
    return analyze_ssmd_source(
        loaded,
        chapters=selected.chapters,
        language=selected.language,
        fallback_language=selected.fallback_language,
        sequence_fallback_mode=selected.sequence_fallback_mode,
        include_titles=selected.include_titles,
        profile=selected.profile,
        overrides=selected.overrides,
        pronunciations=dict(selected.pronunciations),
        linguistics=LinguisticsConfig(spacy=selected.spacy),
        on_progress=on_progress,
    )


def project_text(
    analysis: SsmdAnalysis,
    *,
    options: TextProjectionOptions | None = None,
) -> ProjectedText:
    """Project prepared text using the shared deterministic TXT rules."""
    from .analysis.models import SsmdAnalysis as AnalysisModel
    from .analysis.projection import project_txt

    if not isinstance(analysis, AnalysisModel):
        raise TypeError("analysis must be an SsmdAnalysis instance")
    selected = (
        TextProjectionOptions(include_titles=analysis.include_titles)
        if options is None
        else options
    )
    if not isinstance(selected, TextProjectionOptions):
        raise TypeError("options must be a TextProjectionOptions instance")
    return project_txt(
        analysis,
        max_paragraph_chars=selected.max_paragraph_chars,
        include_titles=selected.include_titles,
    )


def build_report(
    analysis: SsmdAnalysis,
    *,
    projection: ProjectedText | None = None,
    options: TextProjectionOptions | None = None,
    analysis_id: str | None = None,
) -> SsmdAnalysisReport:
    """Build a typed report from existing analysis and projection, without reanalysis."""
    from .analysis.models import SsmdAnalysis as AnalysisModel
    from .analysis.projection import ProjectedText as ProjectedTextModel
    from .analysis.reporting import build_analysis_report

    if not isinstance(analysis, AnalysisModel):
        raise TypeError("analysis must be an SsmdAnalysis instance")
    if options is not None and not isinstance(options, TextProjectionOptions):
        raise TypeError("options must be a TextProjectionOptions instance")
    if projection is not None and not isinstance(projection, ProjectedTextModel):
        raise TypeError("projection must be a ProjectedText instance or None")
    if (
        projection is not None
        and options is not None
        and (
            projection.max_paragraph_chars != options.max_paragraph_chars
            or projection.include_titles != options.include_titles
        )
    ):
        raise ValueError("projection settings do not match the supplied options")
    if projection is None:
        selected = options or TextProjectionOptions(include_titles=analysis.include_titles)
        projection = project_text(analysis, options=selected)
    return build_analysis_report(
        analysis,
        projection,
        analysis_id=analysis_id,
        include_titles=projection.include_titles,
        max_paragraph_chars=projection.max_paragraph_chars,
    )


def audit_speech(analysis: SsmdAnalysis) -> SsmdAnalysisReport:
    """Return the review report for an existing analysis without preparing it again."""
    return build_report(analysis)


def freeze_speech(analysis: SsmdAnalysis) -> SpeechFreezeResult:
    """Freeze an existing analysis in memory and return exact sections plus evidence."""
    from .errors import MaterializationError
    from .speech.failures import SpeechFreezeFailure, make_speech_freeze_failure
    from .speech.reporting import build_speech_freeze_report
    from .speech.workflows import materialize_analysis

    try:
        materialization = materialize_analysis(analysis)
    except SpeechFreezeFailure:
        raise
    except MaterializationError as exc:
        raise make_speech_freeze_failure(analysis, str(exc)) from exc
    report = build_speech_freeze_report(
        analysis,
        materialization.changes,
        materialization.summary,
    )
    speech = SpeechOutcome(
        status="complete",
        summary=materialization.summary,
        report=report,
    )
    return SpeechFreezeResult(
        status="complete",
        sections=materialization.section_ssmd,
        speech=speech,
        changes=materialization.changes,
        issues=materialization.issues,
    )


def analyze_cached(
    source: str | Path,
    *,
    options: AnalysisOptions | None = None,
    projection_options: TextProjectionOptions | None = None,
    cache_root: str | Path | None = None,
    refresh: bool = False,
    on_progress: ProgressCallback | None = None,
) -> CachedAnalysis:
    """Analyze a filesystem source with explicit, validated disk-cache persistence."""
    selected = AnalysisOptions() if options is None else options
    if not isinstance(selected, AnalysisOptions):
        raise TypeError("options must be an AnalysisOptions instance")
    projection = (
        TextProjectionOptions(include_titles=selected.include_titles)
        if projection_options is None
        else projection_options
    )
    if not isinstance(projection, TextProjectionOptions):
        raise TypeError("projection_options must be a TextProjectionOptions instance")
    if projection.include_titles != selected.include_titles:
        raise ValueError("cached analysis requires matching analysis and projection title settings")
    if not isinstance(refresh, bool):
        raise TypeError("refresh must be a bool")

    from .analysis.cache import AnalysisCache, analyze_with_cache
    from .linguistics import LinguisticsConfig

    return analyze_with_cache(
        source,
        chapters=selected.chapters,
        language=selected.language,
        fallback_language=selected.fallback_language,
        sequence_fallback_mode=selected.sequence_fallback_mode,
        include_titles=selected.include_titles,
        max_paragraph_chars=projection.max_paragraph_chars,
        profile=selected.profile,
        overrides=selected.overrides,
        pronunciations=dict(selected.pronunciations),
        cache=AnalysisCache(cache_root),
        refresh=refresh,
        linguistics=LinguisticsConfig(spacy=selected.spacy),
        on_progress=on_progress,
    )


def lookup_change_context(
    subject: SsmdAnalysis | SsmdAnalysisReport,
    change_id: str,
) -> SsmdChangeContext:
    """Resolve one change from in-memory analysis/report evidence without disk lookup."""
    import ttsready

    from .analysis.models import SsmdAnalysis as AnalysisModel
    from .analysis.models import SsmdAnalysisReport as ReportModel
    from .errors import ContextLookupError
    from .speech.mapping import map_analysis_changes
    from .speech.models import SsmdMappedChange

    if isinstance(subject, AnalysisModel):
        changes = map_analysis_changes(subject)
        analysis_id = None
    elif isinstance(subject, ReportModel):
        changes = tuple(subject.mapped_changes)
        if any(not isinstance(item, SsmdMappedChange) for item in changes):
            raise TypeError("analysis report contains invalid mapped-change records")
        analysis_id = subject.analysis_id
    else:
        raise TypeError("subject must be an SsmdAnalysis or SsmdAnalysisReport instance")
    mapped_change = next(
        (item for item in changes if item.change.id == change_id),
        None,
    )
    if mapped_change is None:
        raise ContextLookupError(f"analysis has no speech change {change_id!r}")
    try:
        context = ttsready.context_for_change(subject.preparation, change_id)
    except Exception as exc:
        raise ContextLookupError(f"could not resolve speech change {change_id!r}: {exc}") from exc
    return SsmdChangeContext(
        change=mapped_change,
        language=context.unit.language,
        source_text=context.unit.source_text,
        spoken_text=context.unit.spoken_text,
        source_sentences=tuple(sentence.text for sentence in context.source_sentences),
        spoken_sentences=tuple(sentence.text for sentence in context.spoken_sentences),
        analysis_id=analysis_id,
    )


def lookup_cached_context(
    source: str | Path,
    change_id: str,
    *,
    cache_root: str | Path | None = None,
    paragraph: bool = False,
    bug_report: bool = False,
) -> dict[str, object]:
    """Resolve a persisted change context after explicit freshness-checked cache lookup."""
    from .analysis.cache import AnalysisCache
    from .analysis.context import lookup_context

    return lookup_context(
        source,
        change_id,
        cache=AnalysisCache(cache_root),
        paragraph=paragraph,
        bug_report=bug_report,
    )


__all__ = [
    "AnalysisOptions",
    "BookConversionOptions",
    "BookConversionResult",
    "DocumentConversionOptions",
    "SpeechFreezeResult",
    "SpeechOutcome",
    "SsmdChangeContext",
    "TextProjectionOptions",
    "analyze_cached",
    "analyze_ssmd",
    "audit_speech",
    "build_report",
    "convert_book",
    "convert_content",
    "convert_document",
    "freeze_speech",
    "inspect_document",
    "lookup_cached_context",
    "lookup_change_context",
    "project_text",
]

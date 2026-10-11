from pathlib import Path

from ssmdconvert import (
    AnalysisOptions,
    Book,
    BookChapter,
    BookConversionOptions,
    BookConversionResult,
    BookInspection,
    BookInspectionChapter,
    BookWorkspace,
    CachedAnalysis,
    ConversionResult,
    Converter,
    DocumentConversionOptions,
    MissingDependencyError,
    ProjectedText,
    SourceInfo,
    SpeechFreezeFailure,
    SpeechFreezeResult,
    SpeechOptions,
    SsmdAnalysis,
    SsmdAnalysisReport,
    SsmdChangeContext,
    SSMDConvertError,
    TextProjectionOptions,
    UnsupportedInputError,
    WorkspaceChapterStatus,
    analyze_cached,
    analyze_ssmd,
    audit_speech,
    build_report,
    convert_book,
    convert_content,
    convert_document,
    freeze_speech,
    inspect_book,
    inspect_document,
    load_book_bundle,
    load_book_workspace,
    lookup_cached_context,
    lookup_change_context,
    project_text,
    refresh_book_workspace,
    validate_book_bundle,
    write_book_bundle,
)

source = Path("book.epub")
converter: Converter = Converter()
converted: ConversionResult = converter.convert(source, language="en")
document_options = DocumentConversionOptions(title="A Book", author="An Author")
document_result: ConversionResult = convert_document(source, options=document_options)
content_result: ConversionResult = convert_content(
    "# Notes\n\nRead this.",
    input_format="markdown",
    source_name="notes.md",
    options=DocumentConversionOptions(language="en"),
)
document: object = inspect_document(source)
inspection: BookInspection = inspect_book(source)
source_info: SourceInfo = inspection.source
source_path: Path | None = source_info.path
source_name: str | None = source_info.name
source_media_type: str | None = source_info.media_type
inspection_chapter: BookInspectionChapter = inspection.chapters[0]
inspection_source_parent: str | None = inspection_chapter.source_parent_id
conversion: BookConversionResult = convert_book(
    source,
    options=BookConversionOptions(chapters="1-2", speech=SpeechOptions(mode="preserve")),
)
book: Book = conversion.book
chapter: BookChapter = book.chapters[0]
source_parent: str | None = chapter.source_parent_id
canonical_parent: str | None = chapter.parent_id
source_hash: str = book.source_sha256
source_chapter_count: int | None = book.source_chapter_count
bundle: Path = write_book_bundle(book, Path("book.ssmdbook"), format="directory")
loaded: Book = load_book_bundle(bundle)
workspace: BookWorkspace = load_book_workspace(Path("book.ssmdbook"))
workspace_status: WorkspaceChapterStatus = workspace.chapters[0]
refreshed_workspace: BookWorkspace = refresh_book_workspace(Path("book.ssmdbook"))
validate_book_bundle(bundle)
analysis_options = AnalysisOptions(chapters="all", spacy="off")
projection_options = TextProjectionOptions(max_paragraph_chars=1000)
analysis: SsmdAnalysis = analyze_ssmd(source, options=analysis_options)
projected: ProjectedText = project_text(analysis, options=projection_options)
analysis_report: SsmdAnalysisReport = build_report(analysis, projection=projected)
audited_report: SsmdAnalysisReport = audit_speech(analysis)
freeze_result: SpeechFreezeResult = freeze_speech(analysis)
freeze_error: type[Exception] = SpeechFreezeFailure
change_context: SsmdChangeContext = lookup_change_context(analysis_report, "change-id")
cached_result: CachedAnalysis = analyze_cached(source, options=analysis_options)
cached_context: dict[str, object] = lookup_cached_context(source, "change-id")

try:
    raise UnsupportedInputError("unsupported")
except SSMDConvertError:
    pass

try:
    raise MissingDependencyError("missing optional dependency")
except SSMDConvertError:
    pass

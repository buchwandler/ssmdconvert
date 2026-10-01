from pathlib import Path

from ssmdconvert import (
    Book,
    BookChapter,
    BookInspection,
    BookInspectionChapter,
    ConversionResult,
    Converter,
    MissingDependencyError,
    SourceInfo,
    SSMDConvertError,
    UnsupportedInputError,
    convert,
    convert_book,
    inspect_book,
    load_book_bundle,
    validate_book_bundle,
    write_book_bundle,
)

source = Path("book.epub")
converter: Converter = Converter()
result: ConversionResult = converter.convert(source, language="en")
converted: ConversionResult = convert(source, title="A Book", author="An Author")
inspection: BookInspection = inspect_book(source)
source_info: SourceInfo = inspection.source
source_path: Path | None = source_info.path
source_name: str | None = source_info.name
source_media_type: str | None = source_info.media_type
inspection_chapter: BookInspectionChapter = inspection.chapters[0]
inspection_source_parent: str | None = inspection_chapter.source_parent_id
book: Book = convert_book(source, chapters="1-2")
chapter: BookChapter = book.chapters[0]
source_parent: str | None = chapter.source_parent_id
canonical_parent: str | None = chapter.parent_id
source_hash: str = book.source_sha256
source_chapter_count: int | None = book.source_chapter_count
bundle: Path = write_book_bundle(book, Path("book.ssmdbook"), format="directory")
loaded: Book = load_book_bundle(bundle)
validate_book_bundle(bundle)

try:
    raise UnsupportedInputError("unsupported")
except SSMDConvertError:
    pass

try:
    raise MissingDependencyError("missing optional dependency")
except SSMDConvertError:
    pass

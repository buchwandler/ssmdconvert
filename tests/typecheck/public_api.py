from pathlib import Path

from ssmdconvert import (
    Book,
    BookInspection,
    ConversionResult,
    Converter,
    convert_book,
    inspect_book,
    load_book_bundle,
    parse_chapter_selection,
    validate_book_bundle,
    write_book_bundle,
)

source = Path("book.epub")
converter: Converter = Converter()
result: ConversionResult = converter.convert(source)
inspection: BookInspection = inspect_book(source)
book: Book = convert_book(source, chapters="1-2")
selected: tuple[int, ...] = parse_chapter_selection("1-2", available_numbers={1, 2, 3})
bundle: Path = write_book_bundle(book, Path("book.ssmdbook"))
loaded: Book = load_book_bundle(bundle)
validate_book_bundle(bundle)

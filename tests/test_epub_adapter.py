from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from ssmdconvert import Converter


def make_epub(path: Path) -> None:
    with ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="EPUB/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
            compress_type=ZIP_DEFLATED,
        )
        zf.writestr(
            "EPUB/package.opf",
            (
                '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                "<dc:title>Demo Book</dc:title><dc:creator>A. Author</dc:creator>"
                "<dc:language>en</dc:language></metadata><manifest>"
                '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="c2" href="c2.xhtml" media-type="application/xhtml+xml"/>'
                '</manifest><spine><itemref idref="c1"/><itemref idref="c2"/>'
                "</spine></package>"
            ),
            compress_type=ZIP_DEFLATED,
        )
        zf.writestr("EPUB/c1.xhtml", "<html><body><h1>One</h1><p>Hello.</p></body></html>")
        zf.writestr("EPUB/c2.xhtml", "<html><body><h1>Two</h1><p>World.</p></body></html>")


def test_epub_is_standalone_and_follows_spine(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    result = Converter().convert(source)
    assert result.document.metadata["title"] == "Demo Book"
    assert result.document.metadata["author"] == "A. Author"
    assert [s.title for s in result.document.sections] == ["One", "Two"]
    assert "# One" in result.ssmd and "# Two" in result.ssmd

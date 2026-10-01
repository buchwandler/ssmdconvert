from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import ssmdconvert


def _write_epub(path: Path) -> None:
    files = {
        "META-INF/container.xml": (
            '<?xml version="1.0"?>'
            '<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>'
        ),
        "OEBPS/content.opf": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
            'unique-identifier="pub-id"><metadata '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="pub-id">smoke</dc:identifier>'
            "<dc:title>Smoke Book</dc:title><dc:language>en</dc:language>"
            "<dc:creator>Smoke Author</dc:creator></metadata><manifest>"
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/><item id="chapter" href="chapter.xhtml" '
            'media-type="application/xhtml+xml"/></manifest><spine>'
            '<itemref idref="chapter"/></spine></package>'
        ),
        "OEBPS/nav.xhtml": (
            '<?xml version="1.0"?><html '
            'xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title>'
            '</head><body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">'
            "Chapter One</a></li></ol></nav></body></html>"
        ),
        "OEBPS/chapter.xhtml": (
            '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
            "<head><title>Chapter One</title></head><body><h1>Chapter One</h1>"
            "<p>Hello from the installed package.</p></body></html>"
        ),
    }
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        for name, content in files.items():
            archive.writestr(name, content, compress_type=ZIP_DEFLATED)


def _run(workdir: Path, *arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "ssmdconvert", *arguments],
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        command = " ".join(arguments)
        raise RuntimeError(f"command failed: {command}\n{result.stdout}{result.stderr}")
    return result.stdout


def main() -> None:
    package_path = Path(ssmdconvert.__file__).resolve()
    repository_root = Path(__file__).resolve().parents[1]
    if repository_root in package_path.parents:
        raise RuntimeError(
            f"smoke test imported the source tree instead of an installed package: {package_path}"
        )
    if "ssmdconvert.speech" in sys.modules or "spokenform" in sys.modules:
        raise RuntimeError("base package import loaded the optional speech extra")

    with tempfile.TemporaryDirectory(prefix="ssmdconvert-smoke-") as temporary_dir:
        workdir = Path(temporary_dir)
        for name, content in (
            ("sample.txt", "Plain text smoke test."),
            ("markdown.md", "# Markdown\n\nMarkdown smoke test."),
            ("page.html", "<html><body><h1>HTML</h1><p>HTML smoke test.</p></body></html>"),
        ):
            source = workdir / name
            source.write_text(content, encoding="utf-8")
            destination = source.with_suffix(".ssmd")
            _run(workdir, "convert", str(source), "-o", str(destination))
            if not destination.is_file():
                raise RuntimeError(f"conversion did not create {destination.name}")

        epub = workdir / "sample.epub"
        _write_epub(epub)
        _run(workdir, "convert", str(epub), "-o", str(workdir / "combined.ssmd"))
        inspection = json.loads(_run(workdir, "book", "inspect", str(epub), "--json"))
        if inspection["source"]["format"] != "epub" or not inspection["chapters"]:
            raise RuntimeError("installed book inspection returned an unexpected result")

        bundle = workdir / "sample.ssmdbook.zip"
        _run(workdir, "book", "convert", str(epub), "-o", str(bundle))
        validation = json.loads(_run(workdir, "book", "validate", str(bundle), "--json"))
        if not validation["valid"]:
            raise RuntimeError("installed bundle validation failed")

    print(f"Installed ssmdconvert {ssmdconvert.__version__} smoke test passed")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
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
    environment = os.environ.copy()
    environment["XDG_CACHE_HOME"] = str(workdir / ".cache")
    result = subprocess.run(
        [sys.executable, "-m", "ssmdconvert", *arguments],
        cwd=workdir,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode:
        command = " ".join(arguments)
        raise RuntimeError(f"command failed: {command}\n{result.stdout}{result.stderr}")
    return result.stdout


def _console_help() -> str:
    executable = Path(sys.executable).with_name("ssmdconvert")
    if os.name == "nt":
        executable = executable.with_suffix(".exe")
    result = subprocess.run(
        [str(executable), "--help"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"installed console entry point failed: {result.stderr}")
    return result.stdout


def main() -> None:
    package_path = Path(ssmdconvert.__file__).resolve()
    repository_root = Path(__file__).resolve().parents[1]
    if repository_root in package_path.parents:
        raise RuntimeError(
            f"smoke test imported the source tree instead of an installed package: {package_path}"
        )
    if "ssmdconvert.speech" in sys.modules or "spokenform" in sys.modules:
        raise RuntimeError("core package import eagerly loaded speech internals")

    entrypoint_help = _console_help()
    if not all(command in entrypoint_help for command in ("report", "context", "txt", "speech")):
        raise RuntimeError("installed ssmdconvert entry point is missing analysis commands")

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
        ssmd_source = workdir / "sample.ssmd"
        ssmd_source.write_text(
            '---\nssmd_version: "0.9"\nlanguage: en-US\n---\nMeasure 5 kg.\n',
            encoding="utf-8",
        )
        report = json.loads(_run(workdir, "report", str(ssmd_source), "--format", "json"))
        if report.get("schema") != "ssmdconvert.report.v1" or not report.get("changes"):
            raise RuntimeError("installed report command returned an unexpected result")
        change_id = report["changes"][0]["id"]
        context = json.loads(_run(workdir, "context", str(ssmd_source), change_id, "--json"))
        if context["change"]["id"] != change_id:
            raise RuntimeError("installed context command returned an unexpected result")
        if "five kilograms" not in _run(workdir, "txt", str(ssmd_source)):
            raise RuntimeError("installed TXT command omitted prepared speech text")
        audit = json.loads(_run(workdir, "speech", "audit", str(ssmd_source), "--json"))
        if audit.get("schema") != "ssmdconvert.speech-audit.v1":
            raise RuntimeError("installed speech audit returned an unexpected result")
        annotated = workdir / "annotated.ssmd"
        frozen = workdir / "frozen.ssmd"
        _run(workdir, "speech", "annotate", str(ssmd_source), "-o", str(annotated))
        _run(workdir, "speech", "freeze", str(annotated), "-o", str(frozen))
        if frozen.read_bytes() != annotated.read_bytes():
            raise RuntimeError("installed freeze command was not idempotent")

    print(f"Installed ssmdconvert {ssmdconvert.__version__} smoke test passed")


if __name__ == "__main__":
    main()

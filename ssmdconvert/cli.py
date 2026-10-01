from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

import typer

from . import __version__
from .books import convert_book, inspect_book
from .bundle import validate_book_bundle, write_book_bundle
from .converter import Converter
from .errors import SSMDConvertError

app = typer.Typer(help="Convert documents and books into SSMD.", no_args_is_help=True)
book_app = typer.Typer(help="Inspect and convert EPUB books.", no_args_is_help=True)
app.add_typer(book_app, name="book")


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    """Convert documents and books into Speech Synthesis Markdown."""
    del version


def _run_with_domain_errors(operation: Callable[[], None]) -> None:
    try:
        operation()
    except (SSMDConvertError, OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _output_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(path.expanduser()))
    return absolute.parent.resolve() / absolute.name


def _same_path(left: Path, right: Path) -> bool:
    left_resolved = left.resolve(strict=False)
    right_resolved = right.resolve(strict=False)
    if left_resolved == right_resolved:
        return True
    return left.exists() and right.exists() and os.path.samefile(left, right)


def _reject_input_overwrite(source: Path, destination: Path) -> None:
    if _same_path(source, destination):
        raise ValueError("output destination must not be the input file")


def _write_text_atomically(
    text: str,
    destination: Path,
    *,
    source: Path,
    force: bool,
) -> None:
    destination = _output_path(destination)
    _reject_input_overwrite(source, destination)
    if destination.is_symlink():
        raise ValueError(f"output destination must not be a symbolic link: {destination}")
    if destination.exists() and destination.is_dir():
        raise ValueError(f"output destination is a directory: {destination}")
    if destination.exists() and not force:
        raise ValueError(f"output destination already exists: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        if force:
            os.replace(temporary, destination)
        else:
            try:
                os.link(temporary, destination)
            except FileExistsError as exc:
                raise ValueError(f"output destination already exists: {destination}") from exc
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)


def _book_output_format(
    destination: Path,
    requested: str | None,
) -> Literal["directory", "zip"]:
    if requested is not None:
        normalized = requested.lower()
        if normalized == "directory":
            return "directory"
        if normalized == "zip":
            return "zip"
        raise typer.BadParameter("--format must be 'directory' or 'zip'")

    name = destination.name.lower()
    if name.endswith(".ssmdbook.zip"):
        return "zip"
    if name.endswith(".ssmdbook"):
        return "directory"
    raise typer.BadParameter(
        "cannot infer bundle format from this output name; pass --format directory or --format zip"
    )


@app.command()
def convert(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    title: Annotated[str | None, typer.Option("--title")] = None,
    author: Annotated[str | None, typer.Option("--author")] = None,
    language: Annotated[str | None, typer.Option("--language")] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Replace an existing output file.")
    ] = False,
) -> None:
    """Convert a supported input into one SSMD document."""

    def run() -> None:
        result = Converter().convert(source, title=title, author=author, language=language)
        destination = output or source.with_suffix(".ssmd")
        _write_text_atomically(result.ssmd, destination, source=source, force=force)
        typer.echo(f"Converted {source} -> {_output_path(destination)}")

    _run_with_domain_errors(run)


@app.command()
def inspect(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect the selected local adapter and normalized document shape."""

    def run() -> None:
        converter = Converter()
        adapter = converter.adapter_for(source)
        document = converter.load(source)
        payload = {
            "source": str(source),
            "adapter": adapter.name,
            "metadata": dict(document.metadata),
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "chars": len(section.markdown),
                    "source_ref": section.source_ref,
                }
                for section in document.sections
            ],
        }
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        typer.echo(f"Adapter: {adapter.name}")
        typer.echo(f"Sections: {len(document.sections)}")
        for section in document.sections:
            typer.echo(
                f"  {section.id}: {section.title or '(untitled)'} ({len(section.markdown)} chars)"
            )

    _run_with_domain_errors(run)


@book_app.command("inspect")
def book_inspect(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect EPUB metadata and its chapter hierarchy."""

    def run() -> None:
        inspection = inspect_book(source)
        source_info = inspection.source
        payload = {
            "source": {
                "path": str(source_info.path) if source_info.path is not None else None,
                "name": source_info.name,
                "format": source_info.format,
                "media_type": source_info.media_type,
            },
            "metadata": dict(inspection.metadata),
            "chapters": [asdict(chapter) for chapter in inspection.chapters],
        }
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        typer.echo(f"Source format: {source_info.format}")
        typer.echo(f"Chapters: {len(inspection.chapters)}")
        for chapter in inspection.chapters:
            indent = "  " * (chapter.level - 1)
            typer.echo(f"{chapter.source_number:04d}  {indent}{chapter.title}")

    _run_with_domain_errors(run)


@book_app.command("convert")
def book_convert(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    chapters: Annotated[str, typer.Option("--chapters")] = "all",
    bundle_format: Annotated[str | None, typer.Option("--format")] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing bundle.")] = False,
) -> None:
    """Convert an EPUB into an SSMD book bundle."""

    def run() -> None:
        book = convert_book(source, chapters=chapters)
        destination = output or source.with_suffix(".ssmdbook")
        _reject_input_overwrite(source, _output_path(destination))
        selected_format = _book_output_format(destination, bundle_format)
        written = write_book_bundle(
            book,
            destination,
            format=selected_format,
            overwrite=force,
        )
        typer.echo(f"Created SSMD book bundle: {written}")
        typer.echo(f"Chapters: {len(book.chapters)}")

    _run_with_domain_errors(run)


@book_app.command("validate")
def book_validate(
    bundle: Annotated[Path, typer.Argument(exists=True, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate a directory or ZIP SSMD book bundle."""

    def run() -> None:
        validate_book_bundle(bundle)
        if json_output:
            typer.echo(json.dumps({"valid": True, "bundle": str(bundle)}, ensure_ascii=False))
            return
        typer.echo(f"Valid book bundle: {bundle}")

    _run_with_domain_errors(run)

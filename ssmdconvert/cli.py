from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .books import convert_book, inspect_book
from .bundle import validate_book_bundle, write_book_bundle
from .converter import Converter
from .enrich import enrich_ssmd, load_voice_inventory
from .errors import SSMDConvertError

app = typer.Typer(
    help="Convert documents and books to SSMD; optionally enrich them with JEV.",
    no_args_is_help=True,
)


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
    """Source-neutral SSMD conversion and optional semantic enrichment."""
    del version


@app.command()
def convert(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    title: Annotated[str | None, typer.Option("--title")] = None,
    author: Annotated[str | None, typer.Option("--author")] = None,
    language: Annotated[str | None, typer.Option("--language")] = None,
) -> None:
    """Convert a supported input into SSMD locally."""
    try:
        result = Converter().convert(source, title=title, author=author, language=language)
    except (SSMDConvertError, OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    destination = output or source.with_suffix(".ssmd")
    destination.write_text(result.ssmd, encoding="utf-8", newline="\n")
    typer.echo(f"Converted {source} -> {destination}")
    typer.echo("Local conversion: no content was sent to JEV.")


@app.command()
def inspect(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect which local adapter will be used and the normalized document shape."""
    converter = Converter()
    try:
        adapter = converter.adapter_for(source)
        document = converter.load(source)
    except (SSMDConvertError, OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    payload = {
        "source": str(source),
        "adapter": adapter.name,
        "metadata": document.metadata,
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
    for item in payload["sections"]:
        typer.echo(f"  {item['id']}: {item['title'] or '(untitled)'} ({item['chars']} chars)")
    typer.echo("Local inspection: no content was sent to JEV.")


@app.command("book")
def book(
    source_or_action: Annotated[str, typer.Argument()],
    source: Annotated[Path | None, typer.Argument()] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    chapters: Annotated[str, typer.Option("--chapters")] = "all",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect EPUB chapters, create book bundles, or validate bundles."""
    try:
        if source_or_action == "chapters":
            if source is None:
                raise typer.BadParameter("book chapters requires an EPUB SOURCE")
            inspection = inspect_book(source)
            payload = {
                "source": str(inspection.source),
                "source_format": inspection.source_format,
                "metadata": dict(inspection.metadata),
                "chapters": [asdict(chapter) for chapter in inspection.chapters],
            }
            if json_output:
                typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
                return
            for chapter in inspection.chapters:
                indent = "  " * (chapter.level - 1)
                provenance = f"id={chapter.source_id}" if chapter.source_id else ""
                if chapter.href:
                    provenance = (
                        f"{provenance}, href={chapter.href}"
                        if provenance
                        else f"href={chapter.href}"
                    )
                suffix = f" ({provenance})" if provenance else ""
                typer.echo(
                    f"{chapter.source_number:04d}  {indent}{chapter.title} "
                    f"[level {chapter.level}]{suffix}"
                )
            return
        if source_or_action == "validate":
            if source is None:
                raise typer.BadParameter("book validate requires a BUNDLE path")
            validate_book_bundle(source)
            typer.echo(f"Valid book bundle: {source}")
            return
        if source is not None:
            raise typer.BadParameter("book conversion accepts one EPUB SOURCE followed by options")
        source_path = Path(source_or_action)
        book_data = convert_book(source_path, chapters=chapters)
        destination = output or source_path.with_suffix(".ssmdbook")
        written = write_book_bundle(book_data, destination)
    except (SSMDConvertError, OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Created SSMD book bundle: {written}")
    typer.echo(f"Chapters: {len(book_data.chapters)}")


@app.command()
def enrich(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    speakers: Annotated[bool, typer.Option("--speakers/--no-speakers")] = False,
    sfx: Annotated[bool, typer.Option("--sfx/--no-sfx")] = False,
    voices: Annotated[Path | None, typer.Option("--voices", exists=True, dir_okay=False)] = None,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    max_sfx: Annotated[int, typer.Option("--max-sfx", min=0)] = 8,
    report: Annotated[Path | None, typer.Option("--report")] = None,
    yes_cloud: Annotated[
        bool,
        typer.Option("--yes-cloud", help="Acknowledge that selected content will be sent to JEV."),
    ] = False,
) -> None:
    """[CLOUD/JEV] Add speaker/voice/SFX semantics to an SSMD document."""
    if not (speakers or sfx or voices):
        raise typer.BadParameter("select at least one of --speakers, --sfx, or --voices")
    if not yes_cloud:
        raise typer.BadParameter("cloud enrichment requires explicit --yes-cloud")
    if voices and not provider:
        raise typer.BadParameter("--provider is required with --voices")
    raw = source.read_text(encoding="utf-8")
    inventory = load_voice_inventory(voices) if voices else None
    typer.echo("JEV CLOUD: selected document context will be submitted for semantic analysis.")
    try:
        result = enrich_ssmd(
            raw,
            speakers_enabled=speakers,
            sfx_enabled=sfx,
            voice_inventory=inventory,
            provider=provider,
            model=model,
            max_sfx=max_sfx,
        )
    except (SSMDConvertError, OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    destination = output or source.with_name(source.stem + ".enriched.ssmd")
    destination.write_text(result.ssmd, encoding="utf-8", newline="\n")
    if report:
        report.write_text(
            json.dumps(
                [decision.to_dict() for decision in result.decisions], ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
            newline="\n",
        )
    typer.echo(f"Enriched {source} -> {destination}")
    if report:
        typer.echo(f"Decision report -> {report}")

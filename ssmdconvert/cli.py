from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from . import __version__
from .analysis.cache import analyze_with_cache
from .analysis.context import lookup_context, render_context
from .analysis.prepare import analyze_ssmd_source
from .analysis.projection import project_txt
from .analysis.reporting import (
    render_json_report,
    render_markdown_report,
    report_to_dict,
)
from .books import convert_book, inspect_book
from .bundle import (
    _publish_path_no_replace,
    load_book_bundle,
    load_book_workspace,
    refresh_book_workspace,
    validate_book_bundle,
    write_book_bundle,
)
from .cli_help import AdaptiveTyper, AdaptiveTyperGroup
from .converter import Converter
from .errors import SSMDConvertError
from .metadata import load_metadata_file
from .policy import DEFAULT_SEQUENCE_FALLBACK_MODE
from .speech.audit import audit_ssmd
from .speech.workflows import materialize_analysis

app = AdaptiveTyper(
    cls=AdaptiveTyperGroup,
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode=None,
    help="Convert documents and books into SSMD.",
)
book_app = AdaptiveTyper(
    cls=AdaptiveTyperGroup,
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode=None,
    help="Inspect and convert EPUB books.",
)
app.add_typer(book_app, name="book")
speech_app = AdaptiveTyper(
    cls=AdaptiveTyperGroup,
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode=None,
    help="Audit, annotate, or freeze SSMD speech semantics.",
)
app.add_typer(speech_app, name="speech")


class SequenceFallbackModeOption(str, Enum):
    spell = "spell"
    preserve = "preserve"


_SEQUENCE_FALLBACK_OPTIONS = {option.value: option for option in SequenceFallbackModeOption}
DEFAULT_SEQUENCE_FALLBACK_MODE_OPTION = _SEQUENCE_FALLBACK_OPTIONS[DEFAULT_SEQUENCE_FALLBACK_MODE]


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()  # type: ignore[untyped-decorator]
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


def _canonical_ssmd_bytes(value: bytes) -> bytes:
    """Compare SSMD snapshots independently of platform newline translation."""
    return value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


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
                _publish_path_no_replace(temporary, destination)
            except FileExistsError as exc:
                raise ValueError(f"output destination already exists: {destination}") from exc
            temporary.unlink(missing_ok=True)
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


def _speech_materialize_to_destination(
    source: Path,
    output: Path,
    *,
    chapters: str,
    language: str | None,
    sequence_fallback_mode: SequenceFallbackModeOption,
    force: bool,
    bundle_format: str | None,
) -> Path:
    analysis = analyze_ssmd_source(
        source,
        chapters=chapters,
        language=language,
        sequence_fallback_mode=sequence_fallback_mode.value,
    )
    materialized = materialize_analysis(analysis)
    destination = _output_path(output)
    _reject_input_overwrite(source, destination)
    if bundle_format is not None and analysis.source.kind != "ssmdbook":
        raise ValueError("--format is only valid when writing an SSMD book bundle")


    if analysis.source.kind == "ssmdbook" and source.is_dir():
        workspace_root = source.resolve(strict=True)
        if destination.resolve(strict=False).is_relative_to(workspace_root):
            raise ValueError("bundle output must be outside the source workspace")
    from .bundle import read_current_chapter_bytes

    for section in analysis.sections:
        current = _canonical_ssmd_bytes(read_current_chapter_bytes(source, section.id))
        expected = _canonical_ssmd_bytes(section.ssmd.encode("utf-8"))
        if current != expected:
            raise ValueError(
                f"source chapter {section.id} changed during speech materialization; "
                "no output was written"
            )

    if analysis.source.kind == "ssmd":
        section = analysis.sections[0]
        _write_text_atomically(
            materialized.section_ssmd[section.id],
            destination,
            source=source,
            force=force,
        )
        return destination

    if source.is_dir():
        book = load_book_workspace(source).book
    else:
        book = load_book_bundle(source)
    current_by_id = {chapter.id: chapter for chapter in book.chapters}
    for section in analysis.sections:
        chapter = current_by_id.get(section.id)
        if (
            chapter is None
            or _canonical_ssmd_bytes(chapter.ssmd.encode("utf-8"))
            != _canonical_ssmd_bytes(section.ssmd.encode("utf-8"))
        ):
            raise ValueError(
                f"source chapter {section.id} changed during speech materialization; "
                "no output was written"
            )
    updated_book = replace(
        book,
        chapters=tuple(
            replace(chapter, ssmd=materialized.section_ssmd.get(chapter.id, chapter.ssmd))
            for chapter in book.chapters
        ),
    )
    selected_format = _book_output_format(destination, bundle_format)
    return write_book_bundle(
        updated_book,
        destination,
        format=selected_format,
        overwrite=force,
    )


def _speech_audit_payload(report: Any) -> dict[str, Any]:
    rendered = report_to_dict(report)
    return {
        "schema": "ssmdconvert.speech-audit.v1",
        "analysis_id": report.analysis_id,
        "source": rendered["source"],
        "summary": rendered["summary"],
        "changes": rendered["changes"],
        "issues": rendered["issues"],
    }


def _render_speech_audit(payload: dict[str, Any]) -> str:
    lines = [f"Speech audit: {payload['source']['path']}", ""]
    for change in payload["changes"]:
        section = f"{change['section_index']:04d} {change.get('section_title') or '(untitled)'}"
        paragraph = "title" if change["is_title"] else str(change["paragraph_index"])
        lines.append(
            f"{section} / {paragraph}: {change['source']} -> {change['replacement']} "
            f"[{change.get('rule') or 'no rule'}; {change['ssmd']['mapping_status']}]"
        )
    if not payload["changes"]:
        lines.append("No automatic speech changes.")
    if payload["issues"]:
        lines.extend(["", "Issues:"])
        lines.extend(
            f"{item['severity']}: {item['code']}: {item['message']}" for item in payload["issues"]
        )
    return "\n".join(lines) + "\n"


@app.command()  # type: ignore[untyped-decorator]
def convert(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    metadata_file: Annotated[
        Path | None,
        typer.Option("--metadata-file", help="YAML file with structured metadata overrides."),
    ] = None,
    title: Annotated[str | None, typer.Option("--title")] = None,
    author: Annotated[str | None, typer.Option("--author")] = None,
    language: Annotated[str | None, typer.Option("-l", "--language")] = None,
    sequence_fallback_mode: Annotated[
        SequenceFallbackModeOption,
        typer.Option("--sequence-fallback-mode"),
    ] = DEFAULT_SEQUENCE_FALLBACK_MODE_OPTION,
    force: Annotated[
        bool, typer.Option("--force", help="Replace an existing output file.")
    ] = False,
) -> None:
    """Convert a supported input into one SSMD document."""

    def run() -> None:
        result = Converter().convert(
            source,
            title=title,
            author=author,
            language=language,
            metadata_overrides=(
                load_metadata_file(metadata_file) if metadata_file is not None else None
            ),
            sequence_fallback_mode=sequence_fallback_mode.value,
        )
        destination = output or source.with_suffix(".ssmd")
        _write_text_atomically(result.ssmd, destination, source=source, force=force)
        typer.echo(f"Converted {source} -> {_output_path(destination)}")

    _run_with_domain_errors(run)


@app.command()  # type: ignore[untyped-decorator]
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


def _analyze_projection(
    source: Path,
    *,
    chapters: str,
    language: str | None,
    sequence_fallback_mode: SequenceFallbackModeOption,
    max_paragraph_chars: int,
    include_titles: bool,
):
    if max_paragraph_chars < 1:
        raise ValueError("--max-paragraph-chars must be at least 1")
    analysis = analyze_ssmd_source(
        source,
        chapters=chapters,
        language=language,
        sequence_fallback_mode=sequence_fallback_mode.value,
        include_titles=include_titles,
    )
    projection = project_txt(
        analysis,
        max_paragraph_chars=max_paragraph_chars,
        include_titles=include_titles,
    )
    return analysis, projection


def _report_format(
    output: Path | None, requested: Literal["md", "json"] | None
) -> Literal["md", "json"]:
    if requested is not None:
        return requested
    suffix = output.suffix.lower() if output is not None else ".md"
    if suffix == ".md":
        return "md"
    if suffix == ".json":
        return "json"
    raise ValueError("cannot infer report format; use a .md/.json output path or --format md|json")


@app.command("report")  # type: ignore[untyped-decorator]
def report(
    source: Annotated[Path, typer.Argument(exists=True, readable=True)],
    chapters: Annotated[str, typer.Option("--chapters", "-c")] = "all",
    language: Annotated[str | None, typer.Option("--language", "-l")] = None,
    sequence_fallback_mode: Annotated[
        SequenceFallbackModeOption,
        typer.Option("--sequence-fallback-mode"),
    ] = DEFAULT_SEQUENCE_FALLBACK_MODE_OPTION,
    max_paragraph_chars: Annotated[int, typer.Option("--max-paragraph-chars")] = 1000,
    include_titles: Annotated[
        bool,
        typer.Option("--include-titles/--no-include-titles"),
    ] = True,
    output_format: Annotated[
        Literal["md", "json"] | None,
        typer.Option("--format"),
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
    show_raw_spans: Annotated[bool, typer.Option("--show-raw-spans")] = False,
    fail_on_warning: Annotated[bool, typer.Option("--fail-on-warning")] = False,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
) -> None:
    """Report SSMD-aware preparation, source context, and TXT projection statistics."""

    def run() -> None:
        cached = analyze_with_cache(
            source,
            chapters=chapters,
            language=language,
            sequence_fallback_mode=sequence_fallback_mode.value,
            include_titles=include_titles,
            max_paragraph_chars=max_paragraph_chars,
            refresh=refresh,
        )
        analysis_report = cached.report
        selected_format = _report_format(output, output_format)
        rendered = (
            render_json_report(analysis_report)
            if selected_format == "json"
            else render_markdown_report(analysis_report, show_raw_spans=show_raw_spans)
        )
        if output is None:
            typer.echo(rendered, nl=False)
        else:
            _write_text_atomically(rendered, output, source=source, force=force)
            typer.echo(f"Wrote report: {_output_path(output)}", err=True)
        if fail_on_warning and any(
            issue.severity in {"warning", "error"} for issue in analysis_report.issues
        ):
            raise typer.Exit(code=1)

    _run_with_domain_errors(run)


@app.command("context")  # type: ignore[untyped-decorator]
def context(
    source: Annotated[Path, typer.Argument(exists=True, readable=True)],
    change_id: Annotated[str, typer.Argument()],
    paragraph: Annotated[bool, typer.Option("--paragraph")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    bug_report: Annotated[bool, typer.Option("--bug-report")] = False,
) -> None:
    """Show source and spoken context for one cached generic change ID."""

    def run() -> None:
        result = lookup_context(
            source,
            change_id,
            paragraph=paragraph,
            bug_report=bug_report,
        )
        if json_output:
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        else:
            typer.echo(render_context(result, paragraph=paragraph), nl=False)

    _run_with_domain_errors(run)


@app.command("txt")  # type: ignore[untyped-decorator]
def txt(
    source: Annotated[Path, typer.Argument(exists=True, readable=True)],
    chapters: Annotated[str, typer.Option("--chapters", "-c")] = "all",
    language: Annotated[str | None, typer.Option("--language", "-l")] = None,
    sequence_fallback_mode: Annotated[
        SequenceFallbackModeOption,
        typer.Option("--sequence-fallback-mode"),
    ] = DEFAULT_SEQUENCE_FALLBACK_MODE_OPTION,
    max_paragraph_chars: Annotated[int, typer.Option("--max-paragraph-chars")] = 1000,
    include_titles: Annotated[
        bool,
        typer.Option("--include-titles/--no-include-titles"),
    ] = True,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Project SSMD into generic prepared plain text for downstream TTS."""

    def run() -> None:
        _analysis, projection = _analyze_projection(
            source,
            chapters=chapters,
            language=language,
            sequence_fallback_mode=sequence_fallback_mode,
            max_paragraph_chars=max_paragraph_chars,
            include_titles=include_titles,
        )
        if output is None:
            typer.echo(projection.text, nl=False)
        else:
            _write_text_atomically(projection.text, output, source=source, force=force)
            typer.echo(f"Wrote prepared text: {_output_path(output)}", err=True)

    _run_with_domain_errors(run)


@speech_app.command("audit")  # type: ignore[untyped-decorator]
def speech_audit(
    source: Annotated[Path, typer.Argument(exists=True, readable=True)],
    chapters: Annotated[str, typer.Option("--chapters", "-c")] = "all",
    language: Annotated[str | None, typer.Option("--language", "-l")] = None,
    sequence_fallback_mode: Annotated[
        SequenceFallbackModeOption,
        typer.Option("--sequence-fallback-mode"),
    ] = DEFAULT_SEQUENCE_FALLBACK_MODE_OPTION,
    include_titles: Annotated[
        bool,
        typer.Option("--include-titles/--no-include-titles"),
    ] = True,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    fail_on_warning: Annotated[bool, typer.Option("--fail-on-warning")] = False,
) -> None:
    """Audit automatic speech changes using the shared SSMD analysis pipeline."""

    def run() -> None:
        report = audit_ssmd(
            source,
            chapters=chapters,
            language=language,
            sequence_fallback_mode=sequence_fallback_mode.value,
            include_titles=include_titles,
        )
        payload = _speech_audit_payload(report)
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
        else:
            typer.echo(_render_speech_audit(payload), nl=False)
        if fail_on_warning and any(
            issue["severity"] in {"warning", "error"} for issue in payload["issues"]
        ):
            raise typer.Exit(code=1)

    _run_with_domain_errors(run)


def _run_speech_materialization_command(
    command: str,
    source: Path,
    output: Path,
    *,
    chapters: str,
    language: str | None,
    sequence_fallback_mode: SequenceFallbackModeOption,
    force: bool,
    bundle_format: str | None,
) -> None:
    def run() -> None:
        destination = _speech_materialize_to_destination(
            source,
            output,
            chapters=chapters,
            language=language,
            sequence_fallback_mode=sequence_fallback_mode,
            force=force,
            bundle_format=bundle_format,
        )
        typer.echo(f"Wrote {command} SSMD: {destination}")

    _run_with_domain_errors(run)


@speech_app.command("annotate")  # type: ignore[untyped-decorator]
def speech_annotate(
    source: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    chapters: Annotated[str, typer.Option("--chapters", "-c")] = "all",
    language: Annotated[str | None, typer.Option("--language", "-l")] = None,
    sequence_fallback_mode: Annotated[
        SequenceFallbackModeOption,
        typer.Option("--sequence-fallback-mode"),
    ] = DEFAULT_SEQUENCE_FALLBACK_MODE_OPTION,
    bundle_format: Annotated[
        Literal["directory", "zip"] | None,
        typer.Option("--format"),
    ] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Write selected automatic speech decisions as SSMD substitutions."""
    _run_speech_materialization_command(
        "annotated",
        source,
        output,
        chapters=chapters,
        language=language,
        sequence_fallback_mode=sequence_fallback_mode,
        force=force,
        bundle_format=bundle_format,
    )


@speech_app.command("freeze")  # type: ignore[untyped-decorator]
def speech_freeze(
    source: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    chapters: Annotated[str, typer.Option("--chapters", "-c")] = "all",
    language: Annotated[str | None, typer.Option("--language", "-l")] = None,
    sequence_fallback_mode: Annotated[
        SequenceFallbackModeOption,
        typer.Option("--sequence-fallback-mode"),
    ] = DEFAULT_SEQUENCE_FALLBACK_MODE_OPTION,
    bundle_format: Annotated[
        Literal["directory", "zip"] | None,
        typer.Option("--format"),
    ] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Freeze selected automatic speech decisions into explicit SSMD semantics."""
    _run_speech_materialization_command(
        "frozen",
        source,
        output,
        chapters=chapters,
        language=language,
        sequence_fallback_mode=sequence_fallback_mode,
        force=force,
        bundle_format=bundle_format,
    )


@book_app.command("inspect")  # type: ignore[untyped-decorator]
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


_BOOK_METADATA_FIELDS = (
    ("title", "Title"),
    ("authors", "Authors"),
    ("language", "Language"),
    ("sequence_fallback_mode", "Sequence fallback mode"),
    ("voice_bindings", "Voice bindings"),
    ("voice_defaults", "Voice defaults"),
    ("pause_defaults", "Pause defaults"),
    ("prosody_transitions", "Prosody transitions"),
    ("language_detection", "Language detection"),
    ("requires", "Requires"),
    ("publisher", "Publisher"),
    ("identifier", "Identifier"),
)


def _metadata_entry_lines(key: str, label: str, metadata: Mapping[str, Any]) -> list[str]:
    if key not in metadata:
        return [f"{label}: not set"]
    value = metadata[key]
    if (
        key == "authors"
        and isinstance(value, list)
        and all(isinstance(author, str) for author in value)
    ):
        rendered = ", ".join(value) if value else "[]"
    elif isinstance(value, str):
        rendered = value
    else:
        rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    if "\n" not in rendered:
        return [f"{label}: {rendered}"]
    return [f"{label}:", *(f"  {line}" for line in rendered.splitlines())]


def _render_stored_metadata(metadata: Mapping[str, Any]) -> str:
    lines = ["Stored metadata", ""]
    known_keys = {key for key, _label in _BOOK_METADATA_FIELDS}
    for key, label in _BOOK_METADATA_FIELDS:
        lines.extend(_metadata_entry_lines(key, label, metadata))
    for key in sorted(metadata.keys() - known_keys):
        lines.extend(_metadata_entry_lines(key, key.replace("_", " ").title(), metadata))
    return "\n".join(lines)


@book_app.command("metadata")  # type: ignore[untyped-decorator]
def book_metadata(
    bundle: Annotated[Path, typer.Argument(exists=True, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Display metadata stored in a directory or ZIP SSMD book bundle."""

    def run() -> None:
        if bundle.is_dir():
            workspace = load_book_workspace(bundle)
            book = workspace.book
            dirty_count = sum(chapter.dirty for chapter in workspace.chapters)
            workspace_lines = [
                "Workspace: directory",
                f"Status: {'dirty' if workspace.dirty else 'clean'}",
                f"Dirty chapters: {dirty_count}",
            ]
        else:
            book = load_book_bundle(bundle)
            workspace_lines = ["Workspace: no", "Status: valid"]
        if json_output:
            typer.echo(
                json.dumps(
                    {"metadata": dict(book.metadata)},
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
            )
            return
        typer.echo("\n".join(workspace_lines) + "\n\n" + _render_stored_metadata(book.metadata))

    _run_with_domain_errors(run)


@book_app.command("refresh")  # type: ignore[untyped-decorator]
def book_refresh(
    workspace: Annotated[Path, typer.Argument(exists=True, readable=True)],
    check: Annotated[bool, typer.Option("--check")] = False,
) -> None:
    """Refresh an editable workspace manifest, or check whether it is clean."""

    def run() -> None:
        if check:
            current = load_book_workspace(workspace)
            if current.dirty:
                dirty_count = sum(chapter.dirty for chapter in current.chapters)
                typer.echo(f"Workspace dirty: {workspace}", err=True)
                typer.echo(f"Dirty chapters: {dirty_count}", err=True)
                raise typer.Exit(code=1)
            typer.echo(f"Workspace clean: {workspace}")
            return

        current = load_book_workspace(workspace)
        changed_digests = sum(chapter.dirty for chapter in current.chapters)
        refreshed = refresh_book_workspace(workspace)
        typer.echo(f"Refreshed {workspace}")
        typer.echo(f"Chapters: {len(refreshed.chapters)}")
        typer.echo(f"Changed digests: {changed_digests}")
        typer.echo("Status: clean")

    _run_with_domain_errors(run)


@book_app.command("convert")  # type: ignore[untyped-decorator]
def book_convert(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    chapters: Annotated[str, typer.Option("--chapters")] = "all",
    language: Annotated[
        str | None, typer.Option("-l", "--language", help="Override the book language.")
    ] = None,
    metadata_file: Annotated[
        Path | None,
        typer.Option("--metadata-file", help="YAML file with structured metadata overrides."),
    ] = None,
    sequence_fallback_mode: Annotated[
        SequenceFallbackModeOption,
        typer.Option("--sequence-fallback-mode"),
    ] = DEFAULT_SEQUENCE_FALLBACK_MODE_OPTION,
    bundle_format: Annotated[str | None, typer.Option("--format")] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing bundle.")] = False,
) -> None:
    """Convert an EPUB into an SSMD book bundle."""

    def run() -> None:
        book = convert_book(
            source,
            chapters=chapters,
            language=language,
            metadata_overrides=(
                load_metadata_file(metadata_file) if metadata_file is not None else None
            ),
            sequence_fallback_mode=sequence_fallback_mode.value,
        )
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


@book_app.command("pack")  # type: ignore[untyped-decorator]
def book_pack(
    workspace: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    force: Annotated[bool, typer.Option("--force", help="Replace an existing ZIP bundle.")] = False,
) -> None:
    """Pack current valid workspace chapters into a strict portable ZIP."""

    def run() -> None:
        current = load_book_workspace(workspace)
        destination = _output_path(output)
        _reject_input_overwrite(workspace, destination)
        written = write_book_bundle(
            current.book,
            destination,
            format="zip",
            overwrite=force,
        )
        typer.echo(f"Packed SSMD book ZIP: {written}")
        typer.echo(f"Chapters: {len(current.book.chapters)}")

    _run_with_domain_errors(run)


@book_app.command("validate")  # type: ignore[untyped-decorator]
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

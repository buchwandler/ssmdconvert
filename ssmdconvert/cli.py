from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

import typer

from . import __version__
from .analysis.context import render_context
from .analysis.reporting import render_json_report, render_markdown_report, report_to_dict
from .api import (
    analyze_cached as analyze_cached_api,
)
from .api import (
    analyze_ssmd as analyze_ssmd_api,
)
from .api import (
    audit_speech as audit_speech_api,
)
from .api import (
    convert_book as convert_book_api,
)
from .api import (
    convert_document,
    inspect_document,
    lookup_cached_context,
    project_text,
)
from .api import (
    freeze_speech as freeze_speech_api,
)
from .books import inspect_book
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
from .document_bundle import (
    load_document_bundle,
    load_document_workspace,
    refresh_document_workspace,
    validate_document_bundle,
    write_document_bundle,
)
from .errors import BookError, DocumentBundleError, SSMDConvertError
from .linguistics import SpacyPolicy
from .metadata import load_metadata_file
from .options import (
    AnalysisOptions,
    BookConversionOptions,
    DocumentConversionOptions,
    SpeechOptions,
    TextProjectionOptions,
)
from .policy import DEFAULT_SEQUENCE_FALLBACK_MODE, SpeechSemanticsMode
from .progress import ProgressCallback, ProgressEvent
from .services.document_conversion import convert_document_artifact
from .speech.failures import SpeechFreezeFailure
from .speech.provenance import build_speech_provenance
from .speech.workflows import summarize_changes

if TYPE_CHECKING:
    from .analysis.models import SsmdAnalysis
    from .analysis.projection import ProjectedText

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
document_app = AdaptiveTyper(
    cls=AdaptiveTyperGroup,
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode=None,
    help="Convert and manage single-document SSMD workspaces.",
)
app.add_typer(document_app, name="document")
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


class _CliProgress:
    """Render API progress on stderr, using Rich only for a capable TTY."""

    def __init__(self, requested: bool | None) -> None:
        is_tty = bool(getattr(sys.stderr, "isatty", lambda: False)())
        self.enabled = is_tty if requested is None else requested
        self.use_rich = (
            self.enabled
            and is_tty
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM", "").lower() != "dumb"
        )
        self._progress: Any | None = None
        self._console: Any | None = None
        self._tasks: dict[str, Any] = {}

    def __enter__(self) -> _CliProgress:
        if self.use_rich:
            try:
                from rich.console import Console
                from rich.progress import (
                    BarColumn,
                    Progress,
                    SpinnerColumn,
                    TaskProgressColumn,
                    TextColumn,
                    TimeElapsedColumn,
                )
            except ImportError:
                self.use_rich = False
            else:
                self._console = Console(stderr=True, force_terminal=True)
                self._progress = Progress(
                    SpinnerColumn(),
                    TextColumn("{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeElapsedColumn(),
                    console=self._console,
                    transient=True,
                )
                self._progress.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._progress is not None:
            self._progress.stop()

    @staticmethod
    def _label(phase: str) -> str:
        return phase.replace(".", " ").replace("_", " ").capitalize()

    def _print(self, message: str, *, style: str | None = None) -> None:
        if self._console is not None and self.use_rich:
            self._console.print(message, style=style, markup=False)
        else:
            typer.echo(message, err=True)

    def _fallback_warnings(self, event: ProgressEvent) -> None:
        if event.phase != "linguistics.resolve" or event.kind != "phase.completed":
            return
        fallbacks = event.details.get("fallbacks", {})
        if not isinstance(fallbacks, Mapping):
            return
        for language, reason in fallbacks.items():
            self._print(
                f"Warning: spaCy auto fallback for {language}: {reason}. "
                "Continuing without linguistic hints.",
                style="yellow",
            )

    def __call__(self, event: ProgressEvent) -> None:
        self._fallback_warnings(event)
        if not self.enabled:
            return
        if self._progress is None:
            self._plain_event(event)
            return
        if event.kind == "phase.started":
            task_id = self._tasks.get(event.phase)
            label = self._label(event.phase)
            if task_id is None:
                self._tasks[event.phase] = self._progress.add_task(
                    label,
                    total=event.total,
                    completed=event.completed or 0,
                )
            else:
                self._progress.update(
                    task_id,
                    description=label,
                    total=event.total,
                    completed=event.completed or 0,
                    visible=True,
                )
        elif event.kind == "phase.completed":
            task_id = self._tasks.pop(event.phase, None)
            if task_id is not None:
                updates: dict[str, Any] = {"visible": False}
                if event.total is not None:
                    updates["total"] = event.total
                if event.completed is not None:
                    updates["completed"] = event.completed
                self._progress.update(task_id, **updates)
        elif event.kind in {
            "chapter.started",
            "chapter.completed",
            "unit.started",
            "unit.completed",
        }:
            task_id = self._tasks.get(event.phase)
            if task_id is not None:
                updates = {}
                if event.total is not None:
                    updates["total"] = event.total
                if (
                    event.kind in {"chapter.completed", "unit.completed"}
                    and event.completed is not None
                ):
                    updates["completed"] = event.completed
                if event.chapter_id is not None:
                    updates["description"] = f"{self._label(event.phase)}: {event.chapter_id}"
                self._progress.update(task_id, **updates)
        elif event.kind in {"cache.hit", "cache.miss"}:
            task_id = self._tasks.get(event.phase)
            if task_id is not None:
                self._progress.update(
                    task_id,
                    description=(
                        f"{self._label(event.phase)}: {event.kind[6:]} {event.chapter_id or ''}"
                    ),
                )
        elif event.kind in {"model.started", "model.completed"}:
            action = "Loading" if event.kind == "model.started" else "Loaded"
            if self._console is not None:
                self._console.print(
                    f"{action} local spaCy model {event.model} ({event.language})",
                    markup=False,
                )
            else:
                self._print(f"{action} local spaCy model {event.model} ({event.language})")

    def _plain_event(self, event: ProgressEvent) -> None:
        if event.kind == "phase.started":
            self._print(f"Starting {self._label(event.phase)}")
        elif event.kind == "phase.completed":
            count = ""
            if event.completed is not None and event.total is not None:
                count = f" ({event.completed}/{event.total})"
            self._print(f"Completed {self._label(event.phase)}{count}")
        elif event.kind == "chapter.completed":
            self._print(
                f"{self._label(event.phase)}: {event.completed}/{event.total} "
                f"{event.chapter_id or ''} complete"
            )
        elif event.kind == "unit.completed" and (
            event.completed == event.total or (event.completed or 0) % 10 == 0
        ):
            self._print(f"{self._label(event.phase)}: {event.completed}/{event.total} units")
        elif event.kind in {"model.started", "model.completed"}:
            action = "Loading" if event.kind == "model.started" else "Loaded"
            self._print(f"{action} local spaCy model {event.model} ({event.language})")
        elif event.kind in {"cache.hit", "cache.miss"}:
            self._print(f"Cache {event.kind[6:]}: {event.chapter_id}")

    def success(self, message: str) -> None:
        if self.enabled:
            self._print(f"Completed: {message}", style="green")


def _run_with_cli_progress(
    requested: bool | None,
    operation: Callable[[ProgressCallback], None],
    success_message: str,
) -> None:
    reporter = _CliProgress(requested)
    with reporter:
        _run_with_domain_errors(lambda: operation(reporter))
    reporter.success(success_message)


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


def _preflight_report_output(
    report_output: Path | None,
    *,
    source: Path,
    output: Path,
    force: bool,
) -> Path | None:
    if report_output is None:
        return None
    report = _output_path(report_output)
    destination = _output_path(output)
    _reject_input_overwrite(source, report)
    if _same_path(report, destination) or report.is_relative_to(destination):
        raise ValueError("freeze report path must be separate from the SSMD output")
    if source.is_dir() and report.is_relative_to(source.resolve(strict=True)):
        raise ValueError("freeze report path must be outside the source workspace")
    if report.is_symlink():
        raise ValueError(f"report destination must not be a symbolic link: {report}")
    if report.exists() and report.is_dir():
        raise ValueError(f"report destination is a directory: {report}")
    if report.exists() and not force:
        raise ValueError(f"report destination already exists: {report}")
    return report


def _publish_speech_report(
    report: dict[str, Any],
    *,
    report_destination: Path | None,
    source: Path,
    force: bool,
    json_output: bool,
) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if report_destination is not None:
        _write_text_atomically(
            rendered + "\n",
            report_destination,
            source=source,
            force=force,
        )
    if json_output:
        typer.echo(rendered)


def _render_freeze_summary(
    report: dict[str, Any],
    *,
    output: Path | None = None,
    operation: str = "Speech freeze",
) -> str:
    if report["status"] == "preserved":
        lines = ["Speech semantics: preserved (structural-only; no automatic changes frozen)."]
    else:
        summary = report["summary"]
        lines = [
            f"{operation} {report['status']}: {summary['changes_total']} changes "
            f"({summary['applied']} applied, "
            f"{summary['already_authoritative']} already authoritative, "
            f"{summary['author_owned']} author-owned, {summary['unresolved']} unresolved)."
        ]
    if output is not None:
        lines.append(f"Output: {_output_path(output)}")
    if report.get("failure"):
        lines.append(f"Failure: {report['failure']}")
    return "\n".join(lines)


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


def _default_document_bundle_path(source: Path) -> Path:
    lower = source.name.lower()
    if lower.endswith(".ssmd.md"):
        base = source.name[: -len(".ssmd.md")]
    elif lower.endswith(".ssmd"):
        base = source.name[: -len(".ssmd")]
    else:
        base = source.stem
    return source.with_name(f"{base}.ssmdoc")


def _document_output_format(
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
    if name.endswith(".ssmdoc.zip"):
        return "zip"
    if name.endswith(".ssmdoc"):
        return "directory"
    raise typer.BadParameter(
        "cannot infer document bundle format from this output name; "
        "pass --format directory or --format zip"
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
    spacy: SpacyPolicy,
    on_progress: ProgressCallback,
    report_output: Path | None = None,
    json_output: bool = False,
) -> tuple[Path, dict[str, Any]]:
    destination = _output_path(output)
    _reject_input_overwrite(source, destination)
    report_destination = _preflight_report_output(
        report_output,
        source=source,
        output=destination,
        force=force,
    )
    analysis = analyze_ssmd_api(
        source,
        options=AnalysisOptions(
            chapters=chapters,
            language=language,
            sequence_fallback_mode=sequence_fallback_mode.value,
            spacy=spacy,
        ),
        on_progress=on_progress,
    )
    if bundle_format is not None and analysis.source.kind not in {"ssmdbook", "ssmdoc"}:
        raise ValueError("--format is only valid when writing an SSMD book or document bundle")

    if analysis.source.kind in {"ssmdbook", "ssmdoc"} and source.is_dir():
        workspace_root = source.resolve(strict=True)
        if destination.resolve(strict=False).is_relative_to(workspace_root):
            raise ValueError("bundle output must be outside the source workspace")
    from .bundle import read_current_section_bytes

    try:
        frozen = freeze_speech_api(analysis)
    except SpeechFreezeFailure as failure:
        if report_destination is not None or json_output:
            failure_report = dict(failure.report)
            failure_report["output"] = None
            failure_report["chapter_count"] = len(analysis.sections)
            _publish_speech_report(
                failure_report,
                report_destination=report_destination,
                source=source,
                force=force,
                json_output=json_output,
            )
        raise

    for section in analysis.sections:
        current = _canonical_ssmd_bytes(read_current_section_bytes(source, section.id))
        expected = _canonical_ssmd_bytes(section.ssmd.encode("utf-8"))
        if current != expected:
            raise ValueError(
                f"source section {section.id} changed during speech materialization; "
                "no output was written"
            )

    if analysis.source.kind == "ssmd":
        section = analysis.sections[0]
        _write_text_atomically(
            frozen.sections[section.id],
            destination,
            source=source,
            force=force,
        )
    elif analysis.source.kind == "ssmdoc":
        if source.is_dir():
            document = load_document_workspace(source).document
        else:
            document = load_document_bundle(source)
        if len(analysis.sections) != 1 or analysis.sections[0].id != "document-0001":
            raise ValueError("SSMD document analysis did not contain document-0001")
        section = analysis.sections[0]
        current_document = _canonical_ssmd_bytes(document.ssmd.encode("utf-8"))
        expected_document = _canonical_ssmd_bytes(section.ssmd.encode("utf-8"))
        if current_document != expected_document:
            raise ValueError(
                "source document changed during speech materialization; no output was written"
            )
        updated_document = replace(
            document,
            ssmd=frozen.sections.get(section.id, document.ssmd),
            metadata=analysis.source.metadata,
            speech_semantics=build_speech_provenance(
                analysis,
                source_sha256=document.source_sha256,
            ),
        )
        selected_format = _document_output_format(destination, bundle_format)
        write_document_bundle(
            updated_document,
            destination,
            format=selected_format,
            overwrite=force,
        )
    else:
        if source.is_dir():
            book = load_book_workspace(source).book
        else:
            book = load_book_bundle(source)
        current_by_id = {chapter.id: chapter for chapter in book.chapters}
        for section in analysis.sections:
            chapter = current_by_id.get(section.id)
            if chapter is None or _canonical_ssmd_bytes(
                chapter.ssmd.encode("utf-8")
            ) != _canonical_ssmd_bytes(section.ssmd.encode("utf-8")):
                raise ValueError(
                    f"source chapter {section.id} changed during speech materialization; "
                    "no output was written"
                )
        updated_book = replace(
            book,
            chapters=tuple(
                replace(chapter, ssmd=frozen.sections.get(chapter.id, chapter.ssmd))
                for chapter in book.chapters
            ),
            speech_semantics=build_speech_provenance(
                analysis,
                source_sha256=book.source_sha256,
            ),
        )
        selected_format = _book_output_format(destination, bundle_format)
        write_book_bundle(
            updated_book,
            destination,
            format=selected_format,
            overwrite=force,
        )

    report = frozen.speech.to_dict()
    report["output"] = str(destination)
    try:
        _publish_speech_report(
            report,
            report_destination=report_destination,
            source=source,
            force=force,
            json_output=json_output,
        )
    except Exception as exc:
        failed_outputs = []
        if report_destination is not None:
            failed_outputs.append(
                f"freeze report was not written to {_output_path(report_destination)}"
            )
        if json_output:
            failed_outputs.append("freeze report could not be written to stdout")
        requested = " and ".join(failed_outputs) or "requested report output failed"
        message = f"SSMD speech artifact was published at {destination}, but {requested}: {exc}"
        if analysis.source.kind == "ssmdoc":
            raise DocumentBundleError(message) from exc
        raise BookError(message) from exc
    return destination, report


def _speech_audit_payload(report: Any) -> dict[str, Any]:
    rendered = report_to_dict(report)
    counts = summarize_changes(tuple(report.mapped_changes))
    return {
        "schema": "ssmdconvert.speech-audit.v2",
        "analysis_id": report.analysis_id,
        "source": rendered["source"],
        "summary": rendered["summary"],
        "freeze_mapping": {
            "complete": counts.complete,
            "changes_total": counts.changes_total,
            "applied": counts.applied,
            "already_authoritative": counts.already_authoritative,
            "author_owned": counts.author_owned,
            "unresolved": counts.unresolved,
        },
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
            f"[{change.get('rule') or 'no rule'}; "
            f"{change['ssmd']['final_disposition']}]"
        )
    mapping = payload["freeze_mapping"]
    lines.extend(
        [
            "",
            f"Decision counts: {mapping['changes_total']} total; "
            f"{mapping['applied']} applied, "
            f"{mapping['already_authoritative']} already authoritative, "
            f"{mapping['author_owned']} author-owned, "
            f"{mapping['unresolved']} unresolved.",
        ]
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
        result = convert_document(
            source,
            options=DocumentConversionOptions(
                title=title,
                author=author,
                language=language,
                metadata_overrides=(
                    load_metadata_file(metadata_file) if metadata_file is not None else {}
                ),
                sequence_fallback_mode=sequence_fallback_mode.value,
            ),
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
        document = inspect_document(source)
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
    spacy: SpacyPolicy,
    on_progress: ProgressCallback,
) -> tuple[SsmdAnalysis, ProjectedText]:
    if max_paragraph_chars < 1:
        raise ValueError("--max-paragraph-chars must be at least 1")
    analysis = analyze_ssmd_api(
        source,
        options=AnalysisOptions(
            chapters=chapters,
            language=language,
            sequence_fallback_mode=sequence_fallback_mode.value,
            include_titles=include_titles,
            spacy=spacy,
        ),
        on_progress=on_progress,
    )
    projection = project_text(
        analysis,
        options=TextProjectionOptions(
            max_paragraph_chars=max_paragraph_chars,
            include_titles=include_titles,
        ),
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
    spacy: Annotated[
        SpacyPolicy,
        typer.Option("--spacy", help="Use no spaCy hints or a locally installed model tier."),
    ] = "off",
    progress: Annotated[
        bool | None,
        typer.Option("--progress/--no-progress", help="Show conversion progress on stderr."),
    ] = None,
) -> None:
    """Report SSMD-aware preparation, source context, and TXT projection statistics."""

    def run(on_progress: ProgressCallback) -> None:
        cached = analyze_cached_api(
            source,
            options=AnalysisOptions(
                chapters=chapters,
                language=language,
                sequence_fallback_mode=sequence_fallback_mode.value,
                include_titles=include_titles,
                spacy=spacy,
            ),
            projection_options=TextProjectionOptions(
                max_paragraph_chars=max_paragraph_chars,
                include_titles=include_titles,
            ),
            refresh=refresh,
            on_progress=on_progress,
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

    _run_with_cli_progress(progress, run, "SSMD report complete")


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
        result = lookup_cached_context(
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
    spacy: Annotated[
        SpacyPolicy,
        typer.Option("--spacy", help="Use no spaCy hints or a locally installed model tier."),
    ] = "off",
    progress: Annotated[
        bool | None,
        typer.Option("--progress/--no-progress", help="Show conversion progress on stderr."),
    ] = None,
) -> None:
    """Project SSMD into generic prepared plain text for downstream TTS."""

    def run(on_progress: ProgressCallback) -> None:
        _analysis, projection = _analyze_projection(
            source,
            chapters=chapters,
            language=language,
            sequence_fallback_mode=sequence_fallback_mode,
            max_paragraph_chars=max_paragraph_chars,
            include_titles=include_titles,
            spacy=spacy,
            on_progress=on_progress,
        )
        if output is None:
            typer.echo(projection.text, nl=False)
        else:
            _write_text_atomically(projection.text, output, source=source, force=force)
            typer.echo(f"Wrote prepared text: {_output_path(output)}", err=True)

    _run_with_cli_progress(progress, run, "prepared text complete")


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
    spacy: Annotated[
        SpacyPolicy,
        typer.Option("--spacy", help="Use no spaCy hints or a locally installed model tier."),
    ] = "off",
    progress: Annotated[
        bool | None,
        typer.Option("--progress/--no-progress", help="Show conversion progress on stderr."),
    ] = None,
) -> None:
    """Audit SSMD speech changes, per-change dispositions, and mapping summary counts."""

    def run(on_progress: ProgressCallback) -> None:
        analysis = analyze_ssmd_api(
            source,
            options=AnalysisOptions(
                chapters=chapters,
                language=language,
                sequence_fallback_mode=sequence_fallback_mode.value,
                include_titles=include_titles,
                spacy=spacy,
            ),
            on_progress=on_progress,
        )
        report = audit_speech_api(analysis)
        payload = _speech_audit_payload(report)
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
        else:
            typer.echo(_render_speech_audit(payload), nl=False)
        if fail_on_warning and any(
            issue["severity"] in {"warning", "error"} for issue in payload["issues"]
        ):
            raise typer.Exit(code=1)

    _run_with_cli_progress(progress, run, "speech audit complete")


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
    spacy: SpacyPolicy,
    progress: bool | None,
    report_output: Path | None = None,
    json_output: bool = False,
) -> None:
    def run(on_progress: ProgressCallback) -> None:
        destination, report = _speech_materialize_to_destination(
            source,
            output,
            chapters=chapters,
            language=language,
            sequence_fallback_mode=sequence_fallback_mode,
            force=force,
            bundle_format=bundle_format,
            spacy=spacy,
            on_progress=on_progress,
            report_output=report_output,
            json_output=json_output,
        )
        if not json_output:
            operation = "Speech freeze" if command == "frozen" else "Speech annotation"
            typer.echo(_render_freeze_summary(report, output=destination, operation=operation))
            if report_output is not None:
                typer.echo(f"Freeze report: {_output_path(report_output)}")

    _run_with_cli_progress(progress, run, f"{command} SSMD materialized")


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
    spacy: Annotated[
        SpacyPolicy,
        typer.Option("--spacy", help="Use no spaCy hints or a locally installed model tier."),
    ] = "off",
    progress: Annotated[
        bool | None,
        typer.Option("--progress/--no-progress", help="Show conversion progress on stderr."),
    ] = None,
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
        spacy=spacy,
        progress=progress,
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
    report_output: Annotated[
        Path | None,
        typer.Option("--report", help="Write the versioned freeze report to this JSON file."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write the freeze report to stdout.")
    ] = False,
    spacy: Annotated[
        SpacyPolicy,
        typer.Option("--spacy", help="Use no spaCy hints or a locally installed model tier."),
    ] = "off",
    progress: Annotated[
        bool | None,
        typer.Option("--progress/--no-progress", help="Show conversion progress on stderr."),
    ] = None,
) -> None:
    """Freeze safe speech decisions; emit a versioned report with --json or --report."""
    _run_speech_materialization_command(
        "frozen",
        source,
        output,
        chapters=chapters,
        language=language,
        sequence_fallback_mode=sequence_fallback_mode,
        force=force,
        bundle_format=bundle_format,
        spacy=spacy,
        progress=progress,
        report_output=report_output,
        json_output=json_output,
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
    speech_semantics: Annotated[
        SpeechSemanticsMode,
        typer.Option(
            "--speech-semantics",
            help="Freeze safe automatic speech decisions or preserve structural-only SSMD.",
        ),
    ] = "freeze",
    bundle_format: Annotated[str | None, typer.Option("--format")] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing bundle.")] = False,
    report_output: Annotated[
        Path | None,
        typer.Option("--report", help="Write the versioned speech-freeze report to JSON."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write the freeze report to stdout.")
    ] = False,
    spacy: Annotated[
        SpacyPolicy,
        typer.Option("--spacy", help="Use no spaCy hints or a locally installed model tier."),
    ] = "off",
    progress: Annotated[
        bool | None,
        typer.Option("--progress/--no-progress", help="Show conversion progress on stderr."),
    ] = None,
) -> None:
    """Convert an EPUB to SSMD, freezing speech by default or preserving structure explicitly."""

    def run(on_progress: ProgressCallback) -> None:
        destination = output or source.with_suffix(".ssmdbook")
        _reject_input_overwrite(source, _output_path(destination))
        report_destination = _preflight_report_output(
            report_output,
            source=source,
            output=destination,
            force=force,
        )
        selected_format = _book_output_format(destination, bundle_format)
        try:
            result = convert_book_api(
                source,
                options=BookConversionOptions(
                    chapters=chapters,
                    language=language,
                    metadata_overrides=(
                        load_metadata_file(metadata_file) if metadata_file is not None else {}
                    ),
                    sequence_fallback_mode=sequence_fallback_mode.value,
                    speech=SpeechOptions(mode=speech_semantics, spacy=spacy),
                ),
                on_progress=on_progress,
            )
        except SpeechFreezeFailure as failure:
            if report_destination is not None or json_output:
                failure_report = dict(failure.report)
                failure_report["output"] = None
                failure_report["chapter_count"] = len(failure.analysis.sections)
                json.dumps(failure_report, ensure_ascii=False, indent=2, allow_nan=False)
                _publish_speech_report(
                    failure_report,
                    report_destination=report_destination,
                    source=source,
                    force=force,
                    json_output=json_output,
                )
            raise

        book = result.book
        report = result.speech.to_dict()
        report["output"] = str(_output_path(destination))
        report["chapter_count"] = len(book.chapters)
        # Validate report serialization before publishing the bundle.
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        written = write_book_bundle(
            book,
            destination,
            format=selected_format,
            overwrite=force,
        )
        report["output"] = str(written)
        try:
            _publish_speech_report(
                report,
                report_destination=report_destination,
                source=source,
                force=force,
                json_output=json_output,
            )
        except Exception as exc:
            failed_outputs = []
            if report_destination is not None:
                failed_outputs.append(
                    f"freeze report was not written to {_output_path(report_destination)}"
                )
            if json_output:
                failed_outputs.append("freeze report could not be written to stdout")
            requested = " and ".join(failed_outputs) or "requested report output failed"
            raise BookError(
                f"SSMD book bundle was published at {written}, but {requested}: {exc}"
            ) from exc
        if not json_output:
            typer.echo(f"Created SSMD book bundle: {written}")
            typer.echo(f"Chapters: {len(book.chapters)}")
            typer.echo(_render_freeze_summary(report))
            if report_output is not None:
                typer.echo(f"Freeze report: {_output_path(report_output)}")

    _run_with_cli_progress(progress, run, "book conversion complete")


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


@document_app.command("convert")  # type: ignore[untyped-decorator]
def document_convert(
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
        SequenceFallbackModeOption | None,
        typer.Option("--sequence-fallback-mode"),
    ] = None,
    bundle_format: Annotated[str | None, typer.Option("--format")] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing bundle.")] = False,
) -> None:
    """Convert a supported source into an editable single-document SSMD workspace."""

    def run() -> None:
        destination = output or _default_document_bundle_path(source)
        resolved_destination = _output_path(destination)
        _reject_input_overwrite(source, resolved_destination)
        selected_format = _document_output_format(destination, bundle_format)
        metadata_overrides = (
            load_metadata_file(metadata_file) if metadata_file is not None else None
        )
        document = convert_document_artifact(
            source,
            title=title,
            author=author,
            language=language,
            metadata_overrides=metadata_overrides,
            sequence_fallback_mode=(
                sequence_fallback_mode.value if sequence_fallback_mode is not None else None
            ),
        )
        written = write_document_bundle(
            document,
            destination,
            format=selected_format,
            overwrite=force,
        )
        typer.echo(f"Created SSMD document bundle: {written}")

    _run_with_domain_errors(run)


@document_app.command("inspect")  # type: ignore[untyped-decorator]
def document_inspect(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect a supported source document before conversion."""

    def run() -> None:
        converter = Converter()
        adapter = converter.adapter_for(source)
        document = inspect_document(source)
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


@document_app.command("metadata")  # type: ignore[untyped-decorator]
def document_metadata(
    bundle: Annotated[Path, typer.Argument(exists=True, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Display metadata from a document workspace or ZIP bundle."""

    def run() -> None:
        if bundle.is_dir():
            workspace = load_document_workspace(bundle)
            document = workspace.document
            workspace_lines = [
                "Workspace: directory",
                f"Status: {'dirty' if workspace.dirty else 'clean'}",
                f"Dirty document: {int(workspace.dirty)}",
            ]
        else:
            document = load_document_bundle(bundle)
            workspace_lines = ["Workspace: no", "Status: valid"]
        if json_output:
            typer.echo(
                json.dumps(
                    {"metadata": dict(document.metadata)},
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
            )
            return
        typer.echo("\n".join(workspace_lines) + "\n\n" + _render_stored_metadata(document.metadata))

    _run_with_domain_errors(run)


@document_app.command("refresh")  # type: ignore[untyped-decorator]
def document_refresh(
    workspace: Annotated[Path, typer.Argument(exists=True, readable=True)],
    check: Annotated[bool, typer.Option("--check")] = False,
) -> None:
    """Refresh a document workspace manifest, or check whether it is clean."""

    def run() -> None:
        if check:
            current = load_document_workspace(workspace)
            if current.dirty:
                typer.echo(f"Workspace dirty: {workspace}", err=True)
                typer.echo("Dirty document: 1", err=True)
                raise typer.Exit(code=1)
            typer.echo(f"Workspace clean: {workspace}")
            return
        current = load_document_workspace(workspace)
        changed_digest = int(current.dirty)
        refresh_document_workspace(workspace)
        typer.echo(f"Refreshed {workspace}")
        typer.echo(f"Changed digest: {changed_digest}")
        typer.echo("Status: clean")

    _run_with_domain_errors(run)


@document_app.command("pack")  # type: ignore[untyped-decorator]
def document_pack(
    workspace: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    force: Annotated[bool, typer.Option("--force", help="Replace an existing ZIP bundle.")] = False,
) -> None:
    """Pack current valid workspace content into a strict portable ZIP."""

    def run() -> None:
        current = load_document_workspace(workspace)
        destination = _output_path(output)
        _reject_input_overwrite(workspace, destination)
        written = write_document_bundle(
            current.document,
            destination,
            format="zip",
            overwrite=force,
        )
        typer.echo(f"Packed SSMD document ZIP: {written}")

    _run_with_domain_errors(run)


@document_app.command("validate")  # type: ignore[untyped-decorator]
def document_validate(
    bundle: Annotated[Path, typer.Argument(exists=True, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate a directory or ZIP SSMD document bundle."""

    def run() -> None:
        validate_document_bundle(bundle)
        if json_output:
            typer.echo(json.dumps({"valid": True, "bundle": str(bundle)}, ensure_ascii=False))
            return
        typer.echo(f"Valid document bundle: {bundle}")

    _run_with_domain_errors(run)

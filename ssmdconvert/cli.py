from __future__ import annotations

import errno
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
    convert_document,
    inspect_document,
    lookup_cached_context,
    project_text,
)
from .api import (
    freeze_speech as freeze_speech_api,
)
from .bundle import (
    convert_bundle,
    inspect_bundle_source,
    load_bundle,
    load_bundle_workspace,
    pack_bundle,
    read_current_bundle_item_bytes,
    refresh_bundle_workspace,
    validate_bundle,
    write_bundle,
)
from .bundle_identity import default_bundle_workspace_path
from .cli_help import AdaptiveTyper, AdaptiveTyperGroup
from .converter import Converter
from .errors import BookError, DocumentBundleError, SSMDConvertError
from .linguistics import SpacyPolicy
from .metadata import load_metadata_file
from .models import Book, BookInspection, BookWorkspace, DocumentWorkspace, SsmdDocument
from .options import (
    AnalysisOptions,
    DocumentConversionOptions,
    TextProjectionOptions,
)
from .policy import DEFAULT_SEQUENCE_FALLBACK_MODE, SpeechSemanticsMode
from .progress import ProgressCallback, ProgressEvent
from .results import BookConversionResult
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
    help="Convert documents into canonical SSMD bundles.",
)
bundle_app = AdaptiveTyper(
    cls=AdaptiveTyperGroup,
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode=None,
    help="Inspect, convert, and manage SSMD bundles.",
)
app.add_typer(bundle_app, name="bundle")
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
    """Convert sources into Speech Synthesis Markdown."""
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


def _publish_path_no_replace(source: Path, target: Path) -> None:
    """Publish a completed file without replacing an existing destination."""
    link = getattr(os, "link", None)
    if link is not None:
        try:
            link(source, target)
            return
        except OSError as exc:
            unsupported = {
                errno.EPERM,
                errno.EXDEV,
                getattr(errno, "EOPNOTSUPP", -1),
                getattr(errno, "ENOTSUP", -1),
                getattr(errno, "ENOSYS", -1),
            }
            if exc.errno not in unsupported:
                raise

    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    reservation = os.fstat(fd)
    os.close(fd)
    try:
        os.replace(source, target)
    except OSError:
        try:
            current = target.stat()
            if (current.st_dev, current.st_ino) == (reservation.st_dev, reservation.st_ino):
                target.unlink()
        except FileNotFoundError:
            pass
        raise


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


def _speech_materialize_to_destination(
    source: Path,
    output: Path,
    *,
    chapters: str,
    language: str | None,
    sequence_fallback_mode: SequenceFallbackModeOption,
    force: bool,
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
    is_bundle = analysis.source.kind == "bundle"
    if is_bundle and not destination.name.endswith(".ssmd-bundle"):
        raise ValueError("bundle output must end with '.ssmd-bundle'")
    if is_bundle and source.is_dir():
        workspace_root = source.resolve(strict=True)
        if destination.resolve(strict=False).is_relative_to(workspace_root):
            raise ValueError("bundle output must be outside the source workspace")

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
        if is_bundle:
            current_bytes = read_current_bundle_item_bytes(source, section.id)
        elif len(analysis.sections) == 1:
            current_bytes = source.read_bytes()
        else:
            raise ValueError("standalone SSMD analysis must contain exactly one section")
        current = _canonical_ssmd_bytes(current_bytes)
        expected = _canonical_ssmd_bytes(section.ssmd.encode("utf-8"))
        if current != expected:
            raise ValueError(
                f"source section {section.id} changed during speech materialization; "
                "no output was written"
            )

    if not is_bundle:
        if len(analysis.sections) != 1:
            raise ValueError("standalone SSMD analysis must contain exactly one section")
        section = analysis.sections[0]
        _write_text_atomically(
            frozen.sections[section.id],
            destination,
            source=source,
            force=force,
        )
    elif analysis.source.bundle_kind == "document":
        if source.is_dir():
            workspace = load_bundle_workspace(source)
            document_workspace = workspace.value
            assert isinstance(document_workspace, DocumentWorkspace)
            document = document_workspace.document
        else:
            loaded = load_bundle(source)
            document_value = loaded.value
            assert isinstance(document_value, SsmdDocument)
            document = document_value
        if len(analysis.sections) != 1 or analysis.sections[0].id != "document-0001":
            raise ValueError("document bundle analysis did not contain document-0001")
        section = analysis.sections[0]
        updated_document = replace(
            document,
            ssmd=frozen.sections.get(section.id, document.ssmd),
            metadata=analysis.source.metadata,
            speech_semantics=build_speech_provenance(
                analysis,
                source_sha256=document.source_sha256,
            ),
        )
        write_bundle(updated_document, destination, overwrite=force)
    else:
        if source.is_dir():
            workspace = load_bundle_workspace(source)
            book_workspace = workspace.value
            assert isinstance(book_workspace, BookWorkspace)
            book = book_workspace.book
        else:
            loaded = load_bundle(source)
            book_value = loaded.value
            assert isinstance(book_value, Book)
            book = book_value
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
        write_bundle(updated_book, destination, overwrite=force)

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
        if analysis.source.bundle_kind == "document":
            raise DocumentBundleError(message) from exc
        if is_bundle:
            raise BookError(message) from exc
        raise SSMDConvertError(message) from exc
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
        spacy=spacy,
        progress=progress,
        report_output=report_output,
        json_output=json_output,
    )


@bundle_app.command("inspect")  # type: ignore[untyped-decorator]
def bundle_inspect(
    source: Annotated[Path, typer.Argument(exists=True, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect a supported source or canonical bundle and report its kind."""

    def run() -> None:
        inspection = inspect_bundle_source(source)
        value = inspection.value
        payload: dict[str, Any] = {"kind": inspection.kind, "source": str(source)}
        if isinstance(value, BookInspection):
            payload["metadata"] = dict(value.metadata)
            payload["chapters"] = [asdict(chapter) for chapter in value.chapters]
        elif isinstance(value, Book):
            payload["metadata"] = dict(value.metadata)
            payload["chapters"] = [asdict(chapter) for chapter in value.chapters]
        else:
            metadata = dict(value.metadata)
            if isinstance(value, SsmdDocument):
                char_count = len(value.ssmd)
            else:
                char_count = sum(len(section.markdown) for section in value.sections)
            payload["metadata"] = metadata
            payload["content_items"] = [
                {
                    "id": "document-0001",
                    "title": metadata.get("title"),
                    "char_count": char_count,
                }
            ]

        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        typer.echo(f"kind: {inspection.kind}")
        if inspection.kind == "book":
            chapters = payload["chapters"]
            typer.echo(f"Chapters: {len(chapters)}")
            for chapter in chapters:
                indent = "  " * (chapter["level"] - 1)
                typer.echo(f"{chapter['source_number']:04d}  {indent}{chapter['title']}")
        else:
            item = payload["content_items"][0]
            typer.echo("Content items: 1")
            typer.echo(f"Document: {item['title'] or '(untitled)'} ({item['char_count']} chars)")

    _run_with_domain_errors(run)


_BUNDLE_METADATA_FIELDS = (
    ("title", "Title"),
    ("authors", "Authors"),
    ("author", "Author"),
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
    lines: list[str] = []
    known_keys = {key for key, _label in _BUNDLE_METADATA_FIELDS}
    for key, label in _BUNDLE_METADATA_FIELDS:
        lines.extend(_metadata_entry_lines(key, label, metadata))
    for key in sorted(metadata.keys() - known_keys):
        lines.extend(_metadata_entry_lines(key, key.replace("_", " ").title(), metadata))
    return "\n".join(lines)


@bundle_app.command("metadata")  # type: ignore[untyped-decorator]
def bundle_metadata(
    bundle: Annotated[Path, typer.Argument(exists=True, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Display neutral metadata for either kind of canonical SSMD bundle."""

    def run() -> None:
        if bundle.is_dir():
            workspace = load_bundle_workspace(bundle)
            kind = workspace.kind
            value = workspace.value
            if isinstance(value, BookWorkspace):
                metadata = value.book.metadata
                dirty_count = sum(chapter.dirty for chapter in value.chapters)
            else:
                assert isinstance(value, DocumentWorkspace)
                metadata = value.document.metadata
                dirty_count = int(value.dirty)
            status = "dirty" if value.dirty else "clean"
        else:
            loaded = load_bundle(bundle)
            kind = loaded.kind
            metadata = loaded.value.metadata
            dirty_count = 0
            status = "valid"
        payload = {"kind": kind, "metadata": dict(metadata)}
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return
        lines = ["SSMD bundle metadata", f"kind: {kind}", f"Status: {status}"]
        if bundle.is_dir():
            lines.append(f"Dirty content items: {dirty_count}")
        typer.echo("\n".join(lines) + "\n\n" + _render_stored_metadata(metadata))

    _run_with_domain_errors(run)


@bundle_app.command("refresh")  # type: ignore[untyped-decorator]
def bundle_refresh(
    workspace: Annotated[Path, typer.Argument(exists=True, readable=True)],
    check: Annotated[bool, typer.Option("--check")] = False,
) -> None:
    """Check or refresh an editable bundle workspace of either kind."""

    def run() -> None:
        current = load_bundle_workspace(workspace)
        if isinstance(current.value, BookWorkspace):
            dirty_count = sum(chapter.dirty for chapter in current.value.chapters)
            item_label = "chapters"
        else:
            assert isinstance(current.value, DocumentWorkspace)
            dirty_count = int(current.value.dirty)
            item_label = "documents"
        if check:
            if current.value.dirty:
                typer.echo(f"Workspace dirty: {workspace}", err=True)
                typer.echo(f"Dirty {item_label}: {dirty_count}", err=True)
                raise typer.Exit(code=1)
            typer.echo(f"Workspace clean: {workspace}")
            return
        refreshed = refresh_bundle_workspace(workspace)
        typer.echo(f"Refreshed SSMD bundle workspace: {workspace}")
        typer.echo(f"kind: {refreshed.kind}")
        typer.echo(f"Changed content items: {dirty_count}")
        typer.echo("Status: clean")

    _run_with_domain_errors(run)


@bundle_app.command("convert")  # type: ignore[untyped-decorator]
def bundle_convert(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    chapters: Annotated[str, typer.Option("--chapters")] = "all",
    language: Annotated[str | None, typer.Option("-l", "--language")] = None,
    metadata_file: Annotated[
        Path | None,
        typer.Option("--metadata-file", help="YAML file with structured metadata overrides."),
    ] = None,
    sequence_fallback_mode: Annotated[
        SequenceFallbackModeOption | None,
        typer.Option("--sequence-fallback-mode"),
    ] = None,
    speech_semantics: Annotated[
        SpeechSemanticsMode,
        typer.Option("--speech-semantics"),
    ] = "freeze",
    spacy: Annotated[
        SpacyPolicy,
        typer.Option("--spacy", help="Use no spaCy hints or a locally installed model tier."),
    ] = "off",
    report_output: Annotated[Path | None, typer.Option("--report-output")] = None,
    report_format: Annotated[
        Literal["markdown", "json"], typer.Option("--report-format")
    ] = "markdown",
    force: Annotated[bool, typer.Option("--force", help="Replace an existing bundle.")] = False,
    progress: Annotated[
        bool | None,
        typer.Option("--progress/--no-progress", help="Show conversion progress on stderr."),
    ] = None,
) -> None:
    """Convert an EPUB or supported document into one editable SSMD bundle."""

    def run(on_progress: ProgressCallback) -> None:
        destination = output or default_bundle_workspace_path(source)
        _reject_input_overwrite(source, _output_path(destination))
        report_destination = _preflight_report_output(
            report_output,
            source=source,
            output=destination,
            force=force,
        )
        metadata_overrides = (
            load_metadata_file(metadata_file) if metadata_file is not None else None
        )
        try:
            result = convert_bundle(
                source,
                output=destination,
                chapters=chapters,
                language=language,
                metadata_overrides=metadata_overrides,
                sequence_fallback_mode=(
                    sequence_fallback_mode.value if sequence_fallback_mode is not None else None
                ),
                speech_semantics=speech_semantics,
                spacy=spacy,
                force=force,
                on_progress=on_progress,
            )
        except SpeechFreezeFailure as failure:
            if report_destination is not None:
                failure_payload = dict(failure.report)
                failure_payload["output"] = None
                report_text = (
                    json.dumps(failure_payload, ensure_ascii=False, indent=2, allow_nan=False)
                    if report_format == "json"
                    else _render_freeze_summary(failure_payload, operation="Bundle conversion")
                )
                _write_text_atomically(
                    report_text + "\n",
                    report_destination,
                    source=source,
                    force=force,
                )
            raise

        payload: dict[str, Any] = {
            "kind": result.kind,
            "output": str(_output_path(result.output or destination)),
        }
        if isinstance(result.value, BookConversionResult):
            payload["speech"] = result.value.speech.to_dict()
            payload["chapter_count"] = len(result.value.book.chapters)
        else:
            payload["metadata"] = dict(result.value.metadata)
        if report_destination is not None:
            if report_format == "json":
                report_text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
            else:
                markdown_lines = [
                    "SSMD bundle conversion",
                    f"kind: {result.kind}",
                    f"Output: {_output_path(result.output or destination)}",
                ]
                if "speech" in payload:
                    markdown_lines.append(
                        _render_freeze_summary(payload["speech"], operation="Bundle conversion")
                    )
                report_text = "\n".join(markdown_lines)
            _write_text_atomically(
                report_text + "\n",
                report_destination,
                source=source,
                force=force,
            )
        typer.echo(f"Created SSMD bundle: {result.output}")
        typer.echo(f"kind: {result.kind}")
        if "chapter_count" in payload:
            typer.echo(f"Chapters: {payload['chapter_count']}")
            typer.echo(_render_freeze_summary(payload["speech"], operation="Bundle conversion"))
        if report_destination is not None:
            typer.echo(f"Report: {_output_path(report_destination)}")

    _run_with_cli_progress(progress, run, "bundle conversion complete")


@bundle_app.command("pack")  # type: ignore[untyped-decorator]
def bundle_pack(
    workspace: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Pack an editable workspace into its canonical deterministic ZIP form."""

    def run() -> None:
        written = pack_bundle(workspace, output)
        kind = validate_bundle(written)
        typer.echo(f"Packed SSMD bundle: {written}")
        typer.echo(f"kind: {kind}")

    _run_with_domain_errors(run)


@bundle_app.command("validate")  # type: ignore[untyped-decorator]
def bundle_validate(
    bundle: Annotated[Path, typer.Argument(exists=True, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Strictly validate an editable bundle or packed bundle archive."""

    def run() -> None:
        kind = validate_bundle(bundle)
        if json_output:
            typer.echo(
                json.dumps(
                    {"valid": True, "bundle": str(bundle), "kind": kind},
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Valid SSMD bundle: {bundle}")
        typer.echo(f"kind: {kind}")

    _run_with_domain_errors(run)

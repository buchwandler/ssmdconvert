"""SSMD-specific report assembly and Markdown/JSON rendering."""

from __future__ import annotations

import importlib.metadata
import json
import platform
from collections import Counter
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from ..speech.mapping import map_analysis_changes, mapping_issues
from ..speech.models import SsmdMappedChange
from .models import (
    ConfigurationReport,
    ReproducibilityReport,
    SectionAnalysisStats,
    SemanticsReport,
    SourceReport,
    SsmdAnalysis,
    SsmdAnalysisReport,
    WorkspaceReport,
)
from .projection import ProjectedText

GENERIC_TXT_WARNING = (
    "Generic TXT output is intentionally lossy for SSMD-only voice, pause, and prosody delivery "
    "semantics."
)
_PORTABLE_METADATA_KEYS = (
    "ssmd_version",
    "title",
    "author",
    "authors",
    "language",
    "sequence_fallback_mode",
    "voice_defaults",
    "voice_bindings",
    "pause_defaults",
    "prosody_transitions",
)
_DISTRIBUTIONS = {
    "ssmdconvert": "ssmdconvert",
    "ssmd": "ssmd",
    "ttsready": "ttsready",
    "phrasplit": "phrasplit",
}


def _versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for label, distribution in _DISTRIBUTIONS.items():
        try:
            versions[label] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[label] = "not-installed"
    return versions


def _portable_metadata(analysis: SsmdAnalysis) -> dict[str, Any]:
    return {
        key: analysis.source.metadata[key]
        for key in _PORTABLE_METADATA_KEYS
        if key in analysis.source.metadata
    }


def _section_stats(
    analysis: SsmdAnalysis,
    projection: ProjectedText,
    changes: tuple[SsmdMappedChange, ...],
) -> tuple[SectionAnalysisStats, ...]:
    prepared_by_section = Counter(locator.section_id for locator in analysis.unit_locators.values())
    changes_by_section = Counter(change.section_id for change in changes)
    context_items: dict[str, list[str]] = {}
    for item in projection.items:
        context_items.setdefault(item.section_id, []).extend(item.parts)

    prepared_context_ids = {context.id for context in analysis.contexts if context.unit_ids}
    prepared_paragraphs = Counter(
        context.section_id
        for context in analysis.contexts
        if not context.is_title and context.id in prepared_context_ids
    )
    sections = []
    for section in analysis.sections:
        paragraph_count = sum(
            context.section_id == section.id and not context.is_title
            for context in analysis.contexts
        )
        section_parts = context_items.get(section.id, [])
        sections.append(
            SectionAnalysisStats(
                section_id=section.id,
                index=section.index,
                title=section.title,
                level=section.level,
                input_chars=len(analysis.structures[section.id].clean_text),
                source_paragraphs=paragraph_count,
                prepared_units=prepared_by_section[section.id],
                prepared_paragraphs=prepared_paragraphs[section.id],
                changes=changes_by_section[section.id],
                output_chars=len("\n\n".join(section_parts)),
                chapter_sha256=section.chapter_sha256,
            )
        )
    return tuple(sections)


def build_analysis_report(
    analysis: SsmdAnalysis,
    projection: ProjectedText,
    *,
    analysis_id: str | None = None,
    include_titles: bool = True,
    max_paragraph_chars: int | None = 1000,
) -> SsmdAnalysisReport:
    """Reconcile app-level SSMD facts with public ttsready preparation statistics."""
    mapped_changes = map_analysis_changes(analysis)
    issues = (*analysis.issues, *mapping_issues(mapped_changes))
    source = analysis.source
    metadata_language = source.metadata.get("language", source.metadata.get("lang"))
    if not isinstance(metadata_language, str):
        metadata_language = None
    configuration = ConfigurationReport(
        metadata_language=metadata_language,
        requested_language=analysis.requested_language,
        effective_languages=analysis.effective_languages,
        selected_sections=tuple(section.id for section in analysis.sections),
        stored_sequence_fallback=analysis.stored_sequence_fallback,
        effective_sequence_fallback=analysis.effective_sequence_fallback,
        include_titles=include_titles,
        max_paragraph_chars=max_paragraph_chars,
        output_layout=projection.stats.output_layout,
    )
    workspace = WorkspaceReport(
        type=source.workspace_type,
        status=source.workspace_status,
        dirty_chapters=source.dirty_chapters,
    )
    preparation = analysis.preparation
    reproducibility = ReproducibilityReport(
        source_sha256=source.source_sha256,
        content_fingerprint=source.content_fingerprint,
        prepared_output_sha256=projection.stats.prepared_output_sha256,
        analysis_id=analysis_id,
        tool_versions=_versions(),
        normalization_profile_sha256=preparation.profile_fingerprint,
        override_profile_sha256=preparation.override_fingerprint,
        runtime_fingerprint=preparation.runtime_fingerprint,
    )
    return SsmdAnalysisReport(
        source=SourceReport(
            path=str(source.path.resolve()),
            input_format=source.input_format,
            title=source.title,
            source_sha256=source.source_sha256,
            content_fingerprint=source.content_fingerprint,
        ),
        configuration=configuration,
        workspace=workspace,
        semantics=SemanticsReport(
            portable_metadata=_portable_metadata(analysis),
            generic_txt_warning=GENERIC_TXT_WARNING,
        ),
        reproducibility=reproducibility,
        sections=_section_stats(analysis, projection, mapped_changes),
        preparation=preparation,
        mapped_changes=mapped_changes,
        issues=issues,
        projection=projection.stats,
        contexts=analysis.contexts,
        analysis_id=analysis_id,
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "as_posix"):
        return value.as_posix()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"cannot serialize {type(value).__name__} in an SSMD analysis report")


def _mapped_change(change: Any) -> dict[str, Any]:
    generic = _jsonable(change.change)
    return {
        **generic,
        "section_id": change.section_id,
        "section_index": change.section_index,
        "section_title": change.section_title,
        "paragraph_index": change.paragraph_index,
        "is_title": change.is_title,
        "ssmd": {
            "clean_start": change.clean_start,
            "clean_end": change.clean_end,
            "raw_source_start": change.raw_source_start,
            "raw_source_end": change.raw_source_end,
            "mapping_status": change.mapping_status,
            "materialization_status": change.materialization_status,
            "reason": change.reason,
        },
    }


def report_to_dict(report: SsmdAnalysisReport) -> dict[str, Any]:
    """Return the stable machine-readable ssmdconvert report schema."""
    stats = report.preparation.stats
    context_ids = {
        unit_id: context.id for context in report.contexts for unit_id in context.unit_ids
    }
    changed_context_ids = {
        context_ids.get(change.change.unit_id)
        for change in report.mapped_changes
        if change.change.unit_id in context_ids
    }
    return {
        "schema": "ssmdconvert.report.v1",
        "analysis_id": report.analysis_id,
        "source": _jsonable(report.source),
        "configuration": _jsonable(report.configuration),
        "workspace": _jsonable(report.workspace),
        "semantics": _jsonable(report.semantics),
        "summary": {
            "sections": len(report.sections),
            "source_paragraphs": sum(item.source_paragraphs for item in report.sections),
            "contexts_processed": len(report.contexts),
            "contexts_changed": len(changed_context_ids),
            "prepared_units": stats.units_processed,
            "prepared_units_changed": stats.units_changed,
            "changes": stats.changes,
            "warning_count": stats.warning_count,
            "error_count": stats.error_count,
        },
        "section_stats": [_jsonable(item) for item in report.sections],
        "preparation": {
            "schema": report.preparation.schema,
            "stats": _jsonable(stats),
            "profile_fingerprint": report.preparation.profile_fingerprint,
            "override_fingerprint": report.preparation.override_fingerprint,
            "runtime_fingerprint": report.preparation.runtime_fingerprint,
            "prepared_fingerprint": report.preparation.prepared_fingerprint,
            "issues": _jsonable(report.preparation.issues),
        },
        "changes": [_mapped_change(item) for item in report.mapped_changes],
        "contexts": _jsonable(report.contexts),
        "projection": _jsonable(report.projection),
        "issues": _jsonable(report.issues),
        "reproducibility": _jsonable(report.reproducibility),
    }


def render_json_report(report: SsmdAnalysisReport) -> str:
    return json.dumps(report_to_dict(report), ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _cell(value: Any) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", "<br>")
        .replace("\n", "<br>")
    )


def _table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows)
    return lines


def render_markdown_report(
    report: SsmdAnalysisReport,
    *,
    show_raw_spans: bool = False,
) -> str:
    """Render the ordered human-facing ssmdconvert report sections."""
    stats = report.preparation.stats
    unit_contexts = {
        unit_id: context.id for context in report.contexts for unit_id in context.unit_ids
    }
    changed_contexts = {
        unit_contexts[item.change.unit_id]
        for item in report.mapped_changes
        if item.change.unit_id in unit_contexts
    }
    if len(report.configuration.effective_languages) == 1:
        language_line = f"- Effective language: {report.configuration.effective_languages[0]}"
    else:
        language_line = (
            "- Effective languages: "
            f"{_cell(', '.join(report.configuration.effective_languages) or 'none')}"
        )
    lines = [
        "# ssmdconvert report",
        "",
        "## Source",
        "",
        f"- Path: `{_cell(report.source.path)}`",
        f"- Input format: {_cell(report.source.input_format)}",
        f"- Document title: {_cell(report.source.title or 'not set')}",
        f"- Source SHA-256: `{report.source.source_sha256}`",
        "",
        "## Configuration",
        "",
        f"- Metadata language: {_cell(report.configuration.metadata_language or 'not set')}",
        f"- Requested language: {_cell(report.configuration.requested_language or 'not set')}",
        language_line,
        "- Stored sequence fallback: "
        f"{_cell(report.configuration.stored_sequence_fallback or 'not set')}",
        f"- Effective sequence fallback: {_cell(report.configuration.effective_sequence_fallback)}",
        f"- Output layout: {_cell(report.configuration.output_layout)}",
        f"- Include titles: {str(report.configuration.include_titles).lower()}",
        "- Maximum paragraph characters: "
        f"{_cell(report.configuration.max_paragraph_chars or 'none')}",
        "",
        "## Workspace",
        "",
        f"- Type: {report.workspace.type}",
        f"- Status: {report.workspace.status}",
        f"- Dirty chapters: {_cell(', '.join(report.workspace.dirty_chapters) or 'none')}",
        "",
        "## SSMD semantics",
        "",
        "Generic TXT output is intentionally lossy for SSMD-only voice, pause, and prosody "
        "delivery semantics.",
        "",
        "Portable metadata allowlist:",
        "",
    ]
    if report.semantics.portable_metadata:
        lines.extend(
            [
                "```json",
                json.dumps(report.semantics.portable_metadata, ensure_ascii=False, indent=2),
                "```",
            ]
        )
    else:
        lines.append("No allowlisted metadata is set.")
    lines.extend(
        [
            "",
            "## Reproducibility",
            "",
            f"- Source SHA-256: `{report.reproducibility.source_sha256}`",
            f"- Content fingerprint: `{report.reproducibility.content_fingerprint}`",
            f"- Prepared output SHA-256: `{report.reproducibility.prepared_output_sha256}`",
            f"- Analysis ID: {_cell(report.analysis_id or 'not cached')}",
            "- Normalization profile SHA-256: "
            f"`{report.reproducibility.normalization_profile_sha256}`",
            "- Override/pronunciation profile SHA-256: "
            f"`{report.reproducibility.override_profile_sha256}`",
            f"- Runtime fingerprint: `{report.reproducibility.runtime_fingerprint}`",
            "",
            "Tool versions:",
            "",
        ]
    )
    lines.extend(_table(("Tool", "Version"), sorted(report.reproducibility.tool_versions.items())))
    lines.extend(["", "## Section selection", ""])
    lines.extend(
        _table(
            (
                "#",
                "Level",
                "Title",
                "Input chars",
                "Source paragraphs",
                "Prepared paragraphs",
                "Spokenform changes",
                "Output chars",
            ),
            [
                (
                    item.index,
                    item.level,
                    f"{item.section_id}: {item.title or ''}",
                    item.input_chars,
                    item.source_paragraphs,
                    item.prepared_paragraphs,
                    item.changes,
                    item.output_chars,
                )
                for item in report.sections
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Conversion summary",
            "",
            f"- Selected sections: {len(report.sections)}",
            f"- Source paragraphs: {sum(item.source_paragraphs for item in report.sections)}",
            f"- Paragraphs/titles processed: {report.projection.source_prepared_items}",
            f"- Paragraphs/titles changed: {len(changed_contexts)}",
            f"- Calls / changed calls: {stats.units_processed} / {stats.units_changed}",
            f"- Source replacements: {stats.changes}",
            "- Mixed-language paragraphs may contain multiple calls/units.",
            "",
            "## Spokenform summary",
            "",
            f"- Units processed / changed: {stats.units_processed} / {stats.units_changed}",
            f"- Structured numeric edits: {stats.structured_numeric_edits}",
            f"- Source digit replacements: {stats.source_digit_replacements}",
            f"- Backend warnings / errors: {stats.warning_count} / {stats.error_count}",
            "",
            "## Spokenform stages",
            "",
        ]
    )
    lines.extend(
        _table(("Stage", "Edits"), sorted(stats.stage_edits.items()))
        if stats.stage_edits
        else ["No stage edits."]
    )
    lines.extend(["", "## Rules", ""])
    lines.extend(
        _table(("Rule", "Count"), sorted(stats.rules.items())) if stats.rules else ["No rules."]
    )
    lines.extend(["", "## Recognition domains", ""])
    lines.extend(
        _table(("Domain", "Count"), sorted(stats.recognition_domains.items()))
        if stats.recognition_domains
        else ["No recognition domains."]
    )
    lines.extend(["", "## Changes by section", ""])
    for section in report.sections:
        lines.extend([f"### {_cell(section.title or section.section_id)}", ""])
        section_changes = [
            item for item in report.mapped_changes if item.section_id == section.section_id
        ]
        if not section_changes:
            lines.extend(["No changes.", ""])
            continue
        headers = [
            "ID",
            "Paragraph",
            "Source",
            "Replacement",
            "Stages",
            "Rule",
            "Provenance",
            "Domain",
            "Source span",
            "Output span",
        ]
        if show_raw_spans:
            headers.extend(("Raw SSMD span", "Mapping"))
        rows = []
        for item in section_changes:
            change = item.change
            row: tuple[Any, ...] = (
                change.id,
                "title" if item.is_title else item.paragraph_index,
                change.source,
                change.replacement,
                ", ".join(change.stages),
                change.rule or "",
                json.dumps(dict(change.provenance), ensure_ascii=False, sort_keys=True),
                change.recognition_domain or "",
                f"{change.source_start}:{change.source_end}",
                f"{change.output_start}:{change.output_end}",
            )
            if show_raw_spans:
                row += (
                    (
                        f"{item.raw_source_start}:{item.raw_source_end}"
                        if item.raw_source_start is not None and item.raw_source_end is not None
                        else "unavailable"
                    ),
                    f"{item.mapping_status}/{item.materialization_status}",
                )
            rows.append(row)
        lines.extend(_table(tuple(headers), rows))
        lines.append("")
    projection = report.projection
    lines.extend(
        [
            "## Splitting",
            "",
            "- Maximum paragraph characters: "
            f"{_cell(report.configuration.max_paragraph_chars or 'none')}",
            f"- Split source items: {projection.split_source_items}",
            f"- Added split parts: {projection.added_split_parts}",
            f"- Maximum prepared paragraph characters: {projection.max_prepared_paragraph_chars}",
            "",
            "## Prepared text preview",
            "",
            f"- Source prepared items: {projection.source_prepared_items}",
            "- Output characters / lines / files: "
            f"{projection.output_chars} / {projection.output_lines} / {projection.output_files}",
            f"- Output layout: {_cell(projection.output_layout)}",
            f"- Prepared output SHA-256: `{projection.prepared_output_sha256}`",
            "",
            "## Warnings",
            "",
        ]
    )
    issue_counts = Counter((issue.severity, issue.origin) for issue in report.issues)
    if issue_counts:
        lines.extend(
            _table(
                ("Severity", "Origin", "Count"),
                [
                    (severity, origin, count)
                    for (severity, origin), count in sorted(issue_counts.items())
                ],
            )
        )
        lines.extend(["", "Details:", ""])
        lines.extend(
            _table(
                ("Severity", "Origin", "Section", "Paragraph", "Message"),
                [
                    (
                        issue.severity,
                        issue.origin,
                        issue.section_id or "",
                        issue.paragraph_index if issue.paragraph_index is not None else "",
                        issue.message,
                    )
                    for issue in report.issues
                ],
            )
        )
    else:
        lines.append("No warnings or errors.")
    return "\n".join(lines) + "\n"

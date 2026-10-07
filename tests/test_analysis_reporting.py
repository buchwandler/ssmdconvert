from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ssmdconvert.analysis.prepare import analyze_ssmd_source
from ssmdconvert.analysis.projection import project_txt
from ssmdconvert.analysis.reporting import (
    build_analysis_report,
    render_json_report,
    render_markdown_report,
)


def _source(tmp_path: Path, body: str, *, language: str | None = "en-US") -> Path:
    header = 'ssmd_version: "0.9"\ntitle: "Sample title"'
    if language is not None:
        header += f"\nlanguage: {language}"
    path = tmp_path / "sample.ssmd"
    path.write_text(f"---\n{header}\n---\n{body}\n", encoding="utf-8")
    return path


def test_prepared_txt_projection_and_report_reconcile_exact_stats(tmp_path: Path) -> None:
    path = _source(
        tmp_path,
        'Measure 5 kg for [AWS]{sub="Amazon Web Services"}; [bonjour]{lang="fr-FR"}.',
    )
    analysis = analyze_ssmd_source(path)
    projection = project_txt(analysis, max_paragraph_chars=None)
    report = build_analysis_report(
        analysis,
        projection,
        include_titles=True,
        max_paragraph_chars=None,
    )

    assert projection.text.startswith("Sample title\n\nMeasure five kilograms")
    assert "Amazon Web Services" in projection.text
    assert "bonjour" in projection.text
    assert "{sub=" not in projection.text and "{lang=" not in projection.text
    assert projection.stats.output_chars == len(projection.text)
    assert (
        projection.stats.prepared_output_sha256
        == hashlib.sha256(projection.text.encode("utf-8")).hexdigest()
    )
    assert report.configuration.effective_languages == ("en-US", "fr-FR")
    assert report.configuration.max_paragraph_chars is None
    assert report.preparation.stats == analysis.preparation.stats
    assert report.projection == projection.stats
    assert report.sections[0].source_paragraphs == 1
    assert report.sections[0].prepared_units == len(analysis.preparation.units)
    assert sum(section.changes for section in report.sections) == analysis.preparation.stats.changes
    assert report.projection.output_chars == len(projection.text)
    assert report.semantics.generic_txt_warning.startswith(
        "Generic TXT output is intentionally lossy"
    )

    markdown = render_markdown_report(report, show_raw_spans=True)
    expected_headings = (
        "# ssmdconvert report",
        "## Source",
        "## Configuration",
        "## Workspace",
        "## SSMD semantics",
        "## Reproducibility",
        "## Section selection",
        "## Conversion summary",
        "## Spokenform summary",
        "## Spokenform stages",
        "## Rules",
        "## Recognition domains",
        "## Changes by section",
        "## Splitting",
        "## Prepared text preview",
        "## Warnings",
    )
    heading_positions = [markdown.index(heading) for heading in expected_headings]
    assert heading_positions == sorted(heading_positions)
    assert "Raw SSMD span" in markdown
    assert "voice" in markdown.lower()

    payload = json.loads(render_json_report(report))
    assert payload["schema"] == "ssmdconvert.report.v1"
    assert (
        payload["projection"]["prepared_output_sha256"] == projection.stats.prepared_output_sha256
    )
    assert payload["preparation"]["stats"]["changes"] == analysis.preparation.stats.changes
    assert payload["changes"]
    assert payload["changes"][0]["ssmd"]["mapping_status"] in {"exact", "protected"}
    assert payload["contexts"][0]["is_title"] is True


def test_sentence_splitting_is_pure_and_counted_in_projection(tmp_path: Path) -> None:
    path = _source(tmp_path, "First sentence is long enough. Second sentence is also long enough.")
    analysis = analyze_ssmd_source(path)
    unsplit = project_txt(analysis, max_paragraph_chars=None, include_titles=False)
    projected = project_txt(analysis, max_paragraph_chars=24, include_titles=False)

    assert projected.stats.split_source_items == 1
    assert projected.stats.added_split_parts >= 1
    assert "".join(projected.items[0].parts) == projected.items[0].prepared_text
    assert projected.text.replace("\n\n", "") == unsplit.text
    assert projected.stats.output_chars == len(projected.text)


def test_unresolved_language_is_reported_and_plain_source_text_is_preserved(tmp_path: Path) -> None:
    path = _source(tmp_path, "No language should silently become English.", language=None)
    analysis = analyze_ssmd_source(path)
    projection = project_txt(analysis, max_paragraph_chars=None)
    report = build_analysis_report(analysis, projection, max_paragraph_chars=None)

    assert projection.text == "Sample title\n\nNo language should silently become English."
    assert analysis.effective_languages == ()
    assert any(issue.code == "analysis.language_unresolved" for issue in report.issues)
    assert report.configuration.effective_languages == ()

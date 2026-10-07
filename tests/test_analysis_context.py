from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ssmdconvert import Book, BookChapter, SourceInfo, write_book_bundle
from ssmdconvert.analysis.cache import AnalysisCache, analyze_with_cache
from ssmdconvert.analysis.context import lookup_context, render_context
from ssmdconvert.errors import ContextLookupError


def _source(path: Path, body: str) -> Path:
    path.write_text(
        f'---\nssmd_version: "0.9"\nlanguage: en-US\n---\n{body}\n',
        encoding="utf-8",
    )
    return path


def _book_source(path: Path) -> Path:
    def chapter(chapter_id: str, source_number: int, title: str, body: str) -> BookChapter:
        ssmd = f'---\nssmd_version: "0.9"\ntitle: "{title}"\nlanguage: en-US\n---\n{body}\n'
        return BookChapter(
            id=chapter_id,
            source_number=source_number,
            title=title,
            ssmd=ssmd,
        )

    book = Book(
        source=SourceInfo(format="epub", media_type="application/epub+zip", name="source.epub"),
        metadata={"title": "A book", "language": "en-US"},
        chapters=(
            chapter("chapter-0001", 1, "First", "Measure 5 kg."),
            chapter("chapter-0002", 2, "Second", "Unchanged content."),
        ),
        source_sha256="a" * 64,
        source_chapter_count=2,
    )
    return write_book_bundle(book, path, format="directory")  # type: ignore[arg-type]


def _change_id(result: Any) -> str:
    assert result.report.mapped_changes
    return result.report.mapped_changes[0].change.id


def test_context_enriches_generic_change_with_ssmd_and_exact_sentence(tmp_path: Path) -> None:
    source = _source(tmp_path / "sample.ssmd", "Measure 5 kg.")
    cache = AnalysisCache(tmp_path / "cache")
    analysis = analyze_with_cache(source, cache=cache, max_paragraph_chars=None)
    change_id = _change_id(analysis)

    context = lookup_context(source, change_id, cache=cache)
    rendered = render_context(context)

    assert context["change"]["id"] == change_id
    assert context["change"]["language"] == "en-US"
    assert context["change"]["source"] == "5 kg"
    assert context["change"]["replacement"] == "five kilograms"
    assert context["change"]["provenance"]["origin"] == "spokenform"
    assert context["change"]["ssmd"]["mapping_status"] == "exact"
    assert context["source_sentence"] == "Measure 5 kg."
    assert context["spoken_sentence"] == "Measure five kilograms."
    assert context["analysis_id"] == analysis.analysis_id
    assert "Source sentence:\nMeasure 5 kg." in rendered
    assert f"Change: {change_id}" in rendered

    paragraph = lookup_context(source, change_id, cache=cache, paragraph=True)
    assert paragraph["context_kind"] == "paragraph"
    assert paragraph["source_paragraph"] == "Measure 5 kg."
    bug_report = lookup_context(source, change_id, cache=cache, bug_report=True)
    assert bug_report["bug_report"]["prepared_fingerprint"]


def test_mixed_language_context_uses_coherent_paragraph_by_default(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "mixed.ssmd",
        'English 5 kg, then [bonjour]{lang="fr-FR"} and more English.',
    )
    cache = AnalysisCache(tmp_path / "cache")
    analysis = analyze_with_cache(source, cache=cache, max_paragraph_chars=None)
    context = lookup_context(source, _change_id(analysis), cache=cache)

    assert context["context_kind"] == "paragraph"
    assert context["source_paragraph"] == "English 5 kg, then bonjour and more English."
    assert "five kilograms" in context["spoken_paragraph"]
    assert "bonjour" in context["spoken_paragraph"]
    assert "and more English" in context["spoken_paragraph"]


def test_context_ignores_unrelated_chapter_edits_but_rejects_stale_target(tmp_path: Path) -> None:
    source = _book_source(tmp_path / "book.ssmdbook")
    cache = AnalysisCache(tmp_path / "cache")
    analysis = analyze_with_cache(source, cache=cache, max_paragraph_chars=None)
    change_id = _change_id(analysis)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    chapter_paths = {item["id"]: source / item["path"] for item in manifest["chapters"]}

    chapter_paths["chapter-0002"].write_text(
        chapter_paths["chapter-0002"].read_text(encoding="utf-8") + "\nDirty unrelated text.\n",
        encoding="utf-8",
    )
    context = lookup_context(source, change_id, cache=cache)
    assert context["change"]["section_id"] == "chapter-0001"

    chapter_paths["chapter-0001"].write_text(
        chapter_paths["chapter-0001"].read_text(encoding="utf-8") + "\nTarget changed.\n",
        encoding="utf-8",
    )
    with pytest.raises(ContextLookupError, match="stale for chapter-0001"):
        lookup_context(source, change_id, cache=cache)


def test_dirty_workspace_current_chapter_bytes_are_analyzable(tmp_path: Path) -> None:
    source = _book_source(tmp_path / "dirty.ssmdbook")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    first_chapter = next(item for item in manifest["chapters"] if item["id"] == "chapter-0001")
    chapter_path = source / first_chapter["path"]
    chapter_path.write_text(
        chapter_path.read_text(encoding="utf-8").replace("Measure 5 kg.", "Measure 6 kg."),
        encoding="utf-8",
    )
    cache = AnalysisCache(tmp_path / "cache")
    analysis = analyze_with_cache(source, cache=cache, max_paragraph_chars=None)
    context = lookup_context(source, _change_id(analysis), cache=cache)

    assert analysis.report.workspace.status == "dirty"
    assert context["source_sentence"] == "Measure 6 kg."
    assert context["change"]["source"] == "6 kg"

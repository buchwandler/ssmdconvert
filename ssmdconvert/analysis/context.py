"""Freshness-checked app context lookup for persisted SSMD analysis changes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ttsready

from ..bundle import read_current_chapter_bytes
from ..errors import AnalysisCacheError, ContextLookupError
from .cache import AnalysisCache
from .fingerprints import sha256_bytes


def _sentence_text(text: str, sentences: tuple[Any, ...]) -> str:
    if not sentences:
        return ""
    start = sentences[0].start
    end = sentences[-1].end
    if start < 0 or end < start or end > len(text):
        raise AnalysisCacheError("cached ttsready sentence spans are outside their unit text")
    return text[start:end]


def lookup_context(
    source: str | Path,
    change_id: str,
    *,
    cache: AnalysisCache | None = None,
    paragraph: bool = False,
    bug_report: bool = False,
) -> dict[str, Any]:
    """Resolve a cached change after checking only its current chapter bytes."""
    active_cache = cache or AnalysisCache()
    snapshot, change = active_cache.find_change(source, change_id)
    section_id = change.get("section_id")
    if not isinstance(section_id, str):
        raise AnalysisCacheError(f"cached change {change_id!r} has no section identity")
    section_entry = next(
        (item for item in snapshot["source"]["selected_sections"] if item["id"] == section_id),
        None,
    )
    if section_entry is None:
        raise AnalysisCacheError(f"cached change {change_id!r} references an unselected section")
    try:
        current_bytes = read_current_chapter_bytes(source, section_id)
    except Exception as exc:
        raise ContextLookupError(
            f"Analysis cache is stale for {section_id}. "
            f"Run `ssmdconvert report {source} --refresh`."
        ) from exc
    if sha256_bytes(current_bytes) != section_entry["sha256"]:
        raise ContextLookupError(
            f"Analysis cache is stale for {section_id}. "
            f"Run `ssmdconvert report {source} --refresh`."
        )

    try:
        preparation = ttsready.result_from_dict(snapshot["preparation"])
        generic = ttsready.context_for_change(preparation, change_id)
    except Exception as exc:
        raise AnalysisCacheError(
            f"could not reconstruct cached change {change_id!r}: {exc}"
        ) from exc

    unit_id = change.get("unit_id")
    if not isinstance(unit_id, str):
        raise AnalysisCacheError(f"cached change {change_id!r} has no unit identity")
    app = snapshot["app"]
    context_id = app["unit_contexts"].get(unit_id)
    context = next(
        (
            item
            for item in app["contexts"]
            if isinstance(item, dict) and item.get("id") == context_id
        ),
        None,
    )
    projected = next(
        (
            item
            for item in app["projection_items"]
            if isinstance(item, dict) and item.get("context_id") == context_id
        ),
        None,
    )
    if context is None or projected is None:
        raise AnalysisCacheError(f"cached app context for change {change_id!r} is missing")
    section_stats = next(
        (item for item in app["section_stats"] if item.get("section_id") == section_id),
        None,
    )
    if section_stats is None:
        raise AnalysisCacheError(f"cached section statistics for {section_id!r} are missing")

    unit_context_ids = context.get("unit_ids", [])
    languages = {
        app["unit_locators"][item]["language"]
        for item in unit_context_ids
        if item in app["unit_locators"]
        and isinstance(app["unit_locators"][item].get("language"), str)
    }
    is_mixed_language = len(languages) > 1
    show_paragraph = paragraph or is_mixed_language
    source_context = context.get("source_text")
    spoken_context = projected.get("prepared_text")
    if not isinstance(source_context, str) or not isinstance(spoken_context, str):
        raise AnalysisCacheError(f"cached paragraph text for change {change_id!r} is malformed")

    source_sentence = _sentence_text(generic.unit.source_text, generic.source_sentences)
    spoken_sentence = _sentence_text(generic.unit.spoken_text, generic.spoken_sentences)
    raw = change.get("ssmd")
    if not isinstance(raw, dict):
        raise AnalysisCacheError(f"cached change {change_id!r} has no SSMD mapping record")
    provenance = change.get("provenance", {})
    if not isinstance(provenance, dict):
        raise AnalysisCacheError(f"cached change {change_id!r} has malformed provenance")

    result: dict[str, Any] = {
        "schema": "ssmdconvert.context.v1",
        "analysis_id": snapshot["analysis_id"],
        "content_fingerprint": snapshot["source"]["content_fingerprint"],
        "source": snapshot["source"]["path"],
        "change": {
            "id": change_id,
            "unit_id": unit_id,
            "section_id": section_id,
            "section_index": section_stats["index"],
            "section_title": section_stats.get("title"),
            "paragraph_index": change.get("paragraph_index"),
            "is_title": change.get("is_title") is True,
            "language": generic.unit.language,
            "source": change.get("source"),
            "replacement": change.get("replacement"),
            "stages": change.get("stages", []),
            "rule": change.get("rule"),
            "recognition_domain": change.get("recognition_domain"),
            "provenance": provenance,
            "source_start": change.get("source_start"),
            "source_end": change.get("source_end"),
            "output_start": change.get("output_start"),
            "output_end": change.get("output_end"),
            "ssmd": raw,
        },
        "context_kind": "paragraph" if show_paragraph else "sentence",
        "source_sentence": source_sentence,
        "spoken_sentence": spoken_sentence,
        "source_paragraph": source_context,
        "spoken_paragraph": spoken_context,
    }
    if bug_report:
        result["bug_report"] = {
            "source_sha256": snapshot["source"].get("source_sha256"),
            "chapter_sha256": section_entry["sha256"],
            "profile_fingerprint": preparation.profile_fingerprint,
            "override_fingerprint": preparation.override_fingerprint,
            "runtime_fingerprint": preparation.runtime_fingerprint,
            "prepared_fingerprint": preparation.prepared_fingerprint,
            "unit_source_text": generic.unit.source_text,
            "unit_spoken_text": generic.unit.spoken_text,
        }
    return result


def render_context(context: dict[str, Any], *, paragraph: bool = False) -> str:
    """Render a compact human context, expanding mixed-language paragraphs coherently."""
    change = context["change"]
    ssmd_mapping = change["ssmd"]
    provenance = json.dumps(change.get("provenance", {}), ensure_ascii=False, sort_keys=True)
    raw_span = f"{ssmd_mapping.get('raw_source_start')}:{ssmd_mapping.get('raw_source_end')}"
    mapping_status = (
        f"{ssmd_mapping.get('mapping_status')}/{ssmd_mapping.get('materialization_status')}"
    )
    lines = [
        f"Change: {change['id']}",
        f"Section: {change['section_index']:04d} {change.get('section_title') or '(untitled)'}",
        f"Section ID: {change['section_id']}",
        f"Paragraph: {'title' if change['is_title'] else change['paragraph_index']}",
        f"Language: {change['language']}",
        "",
    ]
    show_paragraph = paragraph or context["context_kind"] == "paragraph"
    if show_paragraph:
        lines.extend(
            [
                "Source paragraph:",
                context["source_paragraph"],
                "",
                "Spoken paragraph:",
                context["spoken_paragraph"],
            ]
        )
    else:
        lines.extend(
            [
                "Source sentence:",
                context["source_sentence"],
                "",
                "Spoken sentence:",
                context["spoken_sentence"],
            ]
        )
    lines.extend(
        [
            "",
            "Focus:",
            str(change.get("source", "")),
            f"-> {change.get('replacement', '')}",
            f"Stage: {', '.join(change.get('stages', [])) or 'not set'}",
            f"Rule: {change.get('rule') or 'not set'}",
            f"Domain: {change.get('recognition_domain') or 'not set'}",
            f"Source span: {change.get('source_start')}:{change.get('source_end')}",
            f"Output span: {change.get('output_start')}:{change.get('output_end')}",
            f"Raw SSMD span: {raw_span}",
            f"Mapping: {mapping_status}",
            f"Provenance: {provenance}",
            f"Analysis ID: {context['analysis_id']}",
            f"Content fingerprint: {context['content_fingerprint']}",
        ]
    )
    if "bug_report" in context:
        lines.extend(
            ["", "Bug report:", json.dumps(context["bug_report"], ensure_ascii=False, indent=2)]
        )
    return "\n".join(lines) + "\n"

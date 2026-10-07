"""Shared exact prepared-TXT projection for preview, reports, and export."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ttsready import PreparedUnit, split_prepared_text

from ..errors import ProjectionError
from .models import ProjectionStats, SsmdAnalysis, SsmdTextContext, SsmdUnitLocator

OUTPUT_LAYOUT = "paragraphs-blank-line-separated"


@dataclass(frozen=True, slots=True)
class ProjectedItem:
    """One title/paragraph projection item and its optional pure split parts."""

    context_id: str
    section_id: str
    paragraph_index: int
    is_title: bool
    source_text: str
    prepared_text: str
    parts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectedText:
    """Prepared plain text and the exact statistics shared by reports and TXT."""

    text: str
    items: tuple[ProjectedItem, ...]
    stats: ProjectionStats


def _prepare_context(
    analysis: SsmdAnalysis,
    context: SsmdTextContext,
    prepared_units: dict[str, PreparedUnit],
    *,
    max_paragraph_chars: int | None,
) -> ProjectedItem:
    units: list[tuple[SsmdUnitLocator, PreparedUnit]] = []
    for unit_id in context.unit_ids:
        prepared = prepared_units.get(unit_id)
        locator = analysis.unit_locators.get(unit_id)
        if prepared is None or locator is None:
            raise ProjectionError(f"context {context.id} references missing unit {unit_id}")
        units.append((locator, prepared))

    if context.is_title:
        if len(units) > 1:
            raise ProjectionError(f"title context {context.id} has multiple prepared units")
        if units and (not units[0][0].is_title or units[0][0].section_id != context.section_id):
            raise ProjectionError(f"title context {context.id} has an invalid unit locator")
        if units and units[0][1].source_text != context.source_text:
            raise ProjectionError(f"prepared title {context.id} differs from its source text")
        prepared_text = units[0][1].spoken_text if units else context.source_text
        split_language = units[0][1].language if units else None
    else:
        if context.clean_start is None or context.clean_end is None:
            raise ProjectionError(f"paragraph context {context.id} is missing clean-text bounds")
        if context.clean_end - context.clean_start != len(context.source_text):
            raise ProjectionError(
                f"paragraph context {context.id} has inconsistent clean-text bounds"
            )
        fragments: list[str] = []
        cursor = 0
        prepared_languages: list[str] = []
        for locator, prepared in sorted(
            units,
            key=lambda pair: pair[0].clean_start if pair[0].clean_start is not None else -1,
        ):
            if (
                locator.clean_start is None
                or locator.clean_end is None
                or locator.section_id != context.section_id
                or locator.paragraph_index != context.paragraph_index
                or locator.is_title
            ):
                raise ProjectionError(f"unit {locator.unit_id} has an invalid paragraph locator")
            local_start = locator.clean_start - context.clean_start
            local_end = locator.clean_end - context.clean_start
            if local_start < cursor or local_end > len(context.source_text):
                raise ProjectionError(
                    f"prepared unit {locator.unit_id} overlaps or exceeds its context"
                )
            if context.source_text[local_start:local_end] != prepared.source_text:
                raise ProjectionError(
                    f"prepared unit {locator.unit_id} differs from its SSMD text slice"
                )
            fragments.extend((context.source_text[cursor:local_start], prepared.spoken_text))
            cursor = local_end
            prepared_languages.append(prepared.language)
        fragments.append(context.source_text[cursor:])
        prepared_text = "".join(fragments)
        split_language = prepared_languages[0] if prepared_languages else None

    parts = (prepared_text,)
    if (
        max_paragraph_chars is not None
        and len(prepared_text) > max_paragraph_chars
        and split_language is not None
    ):
        chunks = split_prepared_text(
            prepared_text,
            language=split_language,
            max_chars=max_paragraph_chars,
        )
        parts = tuple(chunk.text for chunk in chunks)
        if "".join(parts) != prepared_text:
            raise ProjectionError(f"sentence splitter did not preserve context {context.id}")

    return ProjectedItem(
        context_id=context.id,
        section_id=context.section_id,
        paragraph_index=context.paragraph_index,
        is_title=context.is_title,
        source_text=context.source_text,
        prepared_text=prepared_text,
        parts=parts,
    )


def project_txt(
    analysis: SsmdAnalysis,
    *,
    max_paragraph_chars: int | None = 1000,
    include_titles: bool = True,
) -> ProjectedText:
    """Project analyzed contexts without SSMD syntax or provider-specific metadata."""
    if max_paragraph_chars is not None and max_paragraph_chars < 1:
        raise ValueError("max_paragraph_chars must be at least 1 or None")

    prepared_units = {unit.unit_id: unit for unit in analysis.preparation.units}
    items = tuple(
        _prepare_context(
            analysis,
            context,
            prepared_units,
            max_paragraph_chars=max_paragraph_chars,
        )
        for context in analysis.contexts
        if include_titles or not context.is_title
    )
    output_parts = tuple(part for item in items for part in item.parts if part)
    text = "\n\n".join(output_parts)
    split_items = sum(len(item.parts) > 1 for item in items)
    stats = ProjectionStats(
        source_prepared_items=len(items),
        split_source_items=split_items,
        added_split_parts=sum(max(0, len(item.parts) - 1) for item in items),
        max_prepared_paragraph_chars=max((len(item.prepared_text) for item in items), default=0),
        output_chars=len(text),
        output_lines=len(text.splitlines()),
        output_files=0,
        output_layout=OUTPUT_LAYOUT,
        prepared_output_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    return ProjectedText(text=text, items=items, stats=stats)

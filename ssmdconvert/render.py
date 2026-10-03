from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ssmd import lint, parse_structure, serialize_front_matter

from .models import Document


def validate_ssmd_document(ssmd: str) -> None:
    structure = parse_structure(ssmd, dialect="0.9")
    errors = [
        issue
        for issue in lint(ssmd, profile="ssmd-core", dialect="0.9")
        if issue.severity == "error"
    ]
    if errors:
        messages = "; ".join(issue.message for issue in errors[:5])
        raise ValueError(f"Generated SSMD failed validation: {messages}")
    if structure.header.get("ssmd_version") != "0.9":
        raise ValueError("Generated SSMD did not retain ssmd_version 0.9")


def render_document(document: Document) -> str:
    header = dict(document.metadata)
    header["ssmd_version"] = "0.9"
    body = "\n\n".join(
        section.markdown.strip() for section in document.sections if section.markdown.strip()
    )
    body = body.rstrip() + "\n" if body else ""
    result = serialize_front_matter(header, body)
    validate_ssmd_document(result)
    return result


def render_standalone_chapter(
    title: str,
    markdown: str,
    metadata: Mapping[str, Any],
) -> str:
    header: dict[str, Any] = {"ssmd_version": "0.9", "title": title}
    if metadata.get("language"):
        header["language"] = metadata["language"]
    authors = metadata.get("authors")
    if authors:
        header["author"] = authors[0]
    body = markdown.rstrip() + "\n" if markdown else ""
    if metadata.get("sequence_fallback_mode") is not None:
        header["sequence_fallback_mode"] = metadata["sequence_fallback_mode"]
    result = serialize_front_matter(header, body)
    validate_ssmd_document(result)
    return result

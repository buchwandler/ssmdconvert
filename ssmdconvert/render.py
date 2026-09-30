from __future__ import annotations

from ssmd import lint, parse_structure, serialize_front_matter

from .models import Document


def render_document(document: Document) -> str:
    header = dict(document.metadata)
    header["ssmd_version"] = "0.9"
    body = "\n\n".join(
        section.markdown.strip() for section in document.sections if section.markdown.strip()
    )
    body = body.rstrip() + "\n" if body else ""
    result = serialize_front_matter(header, body)
    structure = parse_structure(result, dialect="0.9")
    errors = [
        issue
        for issue in lint(result, profile="ssmd-core", dialect="0.9")
        if issue.severity == "error"
    ]
    if errors:
        messages = "; ".join(issue.message for issue in errors[:5])
        raise ValueError(f"Generated SSMD failed validation: {messages}")
    if structure.header.get("ssmd_version") != "0.9":
        raise ValueError("Generated SSMD did not retain ssmd_version 0.9")
    return result

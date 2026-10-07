"""Deterministic SSMD application fingerprints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..errors import AnalysisError


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 digest of exact source bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file incrementally without retaining a second full source copy."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AnalysisError(f"could not hash source file {path}: {exc}") from exc
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON-compatible fingerprint input canonically and strictly."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AnalysisError(f"analysis fingerprint input is not valid JSON data: {exc}") from exc


def content_fingerprint(sections: Sequence[tuple[str, str]], metadata: Mapping[str, Any]) -> str:
    """Fingerprint ordered current chapter bytes and stored source metadata."""
    payload = {
        "schema": "ssmdconvert.content.v1",
        "sections": [
            {"section_id": section_id, "chapter_sha256": chapter_sha256}
            for section_id, chapter_sha256 in sections
        ],
        "metadata": dict(metadata),
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def ssmd_analysis_id(
    *,
    source_content_fingerprint: str,
    selected_sections: Sequence[Mapping[str, str]],
    options: Mapping[str, Any],
    profile_fingerprint: str,
    override_fingerprint: str,
    runtime_fingerprint: str,
) -> str:
    """Identify app-level analysis inputs without depending on their filesystem path."""
    payload = {
        "schema": "ssmdconvert.analysis.v1",
        "source_content_fingerprint": source_content_fingerprint,
        "selected_sections": [dict(section) for section in selected_sections],
        "options": dict(options),
        "profile_fingerprint": profile_fingerprint,
        "override_fingerprint": override_fingerprint,
        "runtime_fingerprint": runtime_fingerprint,
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:20]
    return f"ana:v1:{digest}"


def chapter_analysis_key(payload: Mapping[str, Any]) -> str:
    """Hash the complete normalized inputs for an immutable section preparation."""
    return hashlib.sha256(canonical_json_bytes(dict(payload))).hexdigest()

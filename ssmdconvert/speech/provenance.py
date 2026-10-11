"""Portable runtime provenance for SSMD speech-freeze results."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

from ..analysis.models import SsmdAnalysis

SpeechProvenanceStatus = Literal["complete", "incomplete"]


def build_speech_provenance(
    analysis: SsmdAnalysis,
    *,
    status: SpeechProvenanceStatus = "complete",
    source_sha256: str | None = None,
) -> dict[str, Any]:
    """Capture the exact preparation/runtime evidence used for automatic SSMD aliases."""
    try:
        ttsready_version = version("ttsready")
        spokenform_version = version("spokenform")
    except PackageNotFoundError as exc:
        raise ValueError(f"cannot record speech runtime version: {exc}") from exc

    preparation = analysis.preparation
    return {
        "status": status,
        "owner": "ssmdconvert",
        "engine": "ttsready",
        "source_sha256": source_sha256 or analysis.source.source_sha256,
        "ttsready_version": ttsready_version,
        "spokenform_version": spokenform_version,
        "profile_fingerprint": preparation.profile_fingerprint,
        "override_fingerprint": preparation.override_fingerprint,
        "runtime_fingerprint": preparation.runtime_fingerprint,
        "prepared_fingerprint": preparation.prepared_fingerprint,
    }


def preserved_speech_provenance(source_sha256: str) -> dict[str, str]:
    """Describe structural-only output without implying a preparation pass occurred."""
    return {
        "status": "preserved",
        "owner": "ssmdconvert",
        "source_sha256": source_sha256,
    }

"""SSMD mapping, audit, and materialization workflows."""

from __future__ import annotations

from typing import Any

__all__ = [
    "AnalysisMaterialization",
    "MaterializationResult",
    "SsmdMappedChange",
    "audit_ssmd",
    "map_analysis_changes",
    "materialize_analysis",
    "materialize_substitutions",
    "SpeechInventory",
    "SpeechInventoryCandidate",
    "SpeechInventoryOccurrence",
    "SpeechInventoryOptions",
    "SpeechReplacementProfile",
    "effective_replacements",
    "inventory_loaded_source",
    "load_speech_profile",
    "parse_speech_profile",
    "speech_profile_fingerprint",
    "empty_speech_profile",
    "render_speech_profile",
    "write_speech_profile",
    "with_speech_replacement",
    "without_speech_replacement",
]


def __getattr__(name: str) -> Any:
    if name == "AnalysisMaterialization" or name == "materialize_analysis":
        from .workflows import AnalysisMaterialization, materialize_analysis

        return {
            "AnalysisMaterialization": AnalysisMaterialization,
            "materialize_analysis": materialize_analysis,
        }[name]
    if name == "MaterializationResult" or name == "materialize_substitutions":
        from .materialize import MaterializationResult, materialize_substitutions

        return {
            "MaterializationResult": MaterializationResult,
            "materialize_substitutions": materialize_substitutions,
        }[name]
    if name == "SsmdMappedChange":
        from .models import SsmdMappedChange

        return SsmdMappedChange
    if name == "audit_ssmd":
        from .audit import audit_ssmd

        return audit_ssmd
    if name == "map_analysis_changes":
        from .mapping import map_analysis_changes

        return map_analysis_changes
    if name in {
        "SpeechInventory",
        "SpeechInventoryCandidate",
        "SpeechInventoryOccurrence",
        "SpeechInventoryOptions",
        "inventory_loaded_source",
    }:
        from . import inventory

        return getattr(inventory, name)
    if name in {
        "SpeechReplacementProfile",
        "effective_replacements",
        "load_speech_profile",
        "parse_speech_profile",
        "empty_speech_profile",
        "render_speech_profile",
        "write_speech_profile",
        "with_speech_replacement",
        "without_speech_replacement",
        "speech_profile_fingerprint",
    }:
        from . import profile

        return getattr(profile, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

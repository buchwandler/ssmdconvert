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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Portable metadata loading and precedence for SSMD conversions."""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from .policy import (
    DEFAULT_SEQUENCE_FALLBACK_MODE,
    SequenceFallbackMode,
    validate_sequence_fallback_mode,
)

PORTABLE_SSMD_METADATA_KEYS = frozenset(
    {
        "language",
        "sequence_fallback_mode",
        "voice_bindings",
        "voice_defaults",
        "pause_defaults",
        "prosody_transitions",
        "language_detection",
        "requires",
    }
)

BIBLIOGRAPHIC_METADATA_KEYS = frozenset(
    {
        "title",
        "authors",
        "publisher",
        "identifier",
    }
)

RESERVED_METADATA_KEYS = frozenset({"ssmd_version"})
_SUPPORTED_METADATA_KEYS = PORTABLE_SSMD_METADATA_KEYS | BIBLIOGRAPHIC_METADATA_KEYS


def _plain_json_value(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"metadata value {path} must not be NaN or Infinity")
        return value
    if isinstance(value, list):
        return [_plain_json_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        plain: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"metadata mapping keys at {path} must be strings")
            plain[key] = _plain_json_value(item, f"{path}.{key}")
        return plain
    raise ValueError(f"metadata value {path} is not JSON-compatible ({type(value).__name__})")


def _validated_metadata_mapping(value: Mapping[Any, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("metadata file top-level keys must be strings")
        if key in RESERVED_METADATA_KEYS:
            raise ValueError(f"metadata key {key!r} is reserved and cannot be overridden")
        if key not in _SUPPORTED_METADATA_KEYS:
            raise ValueError(f"unsupported metadata key: {key!r}")
        result[key] = _plain_json_value(item, key)
    return result


def load_metadata_file(path: str | Path) -> dict[str, Any]:
    """Load supported JSON-compatible metadata from a UTF-8 YAML mapping."""
    metadata_path = Path(path)
    try:
        text = metadata_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"metadata file is not valid UTF-8: {metadata_path}") from exc
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML metadata file {metadata_path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"metadata file must contain a YAML mapping: {metadata_path}")
    return _validated_metadata_mapping(value)


def merge_document_metadata(
    source_metadata: Mapping[str, Any],
    *,
    metadata_overrides: Mapping[str, Any] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    language: str | None = None,
    sequence_fallback_mode: SequenceFallbackMode = DEFAULT_SEQUENCE_FALLBACK_MODE,
) -> dict[str, Any]:
    """Merge source, file, and explicit CLI metadata without mutating the source."""
    metadata = dict(source_metadata)
    if metadata_overrides is not None:
        metadata.update(_validated_metadata_mapping(metadata_overrides))
    if cli_overrides is not None:
        metadata.update(cli_overrides)
    if language is not None:
        metadata["language"] = language
    metadata["sequence_fallback_mode"] = validate_sequence_fallback_mode(sequence_fallback_mode)
    return metadata

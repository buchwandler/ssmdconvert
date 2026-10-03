from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ssmdconvert.metadata import (
    BIBLIOGRAPHIC_METADATA_KEYS,
    PORTABLE_SSMD_METADATA_KEYS,
    load_metadata_file,
    merge_document_metadata,
)


def test_supported_metadata_keys_cover_portable_and_bibliographic_fields() -> None:
    assert PORTABLE_SSMD_METADATA_KEYS == {
        "language",
        "sequence_fallback_mode",
        "voice_bindings",
        "voice_defaults",
        "pause_defaults",
        "prosody_transitions",
        "language_detection",
        "requires",
    }
    assert BIBLIOGRAPHIC_METADATA_KEYS == {
        "title",
        "authors",
        "publisher",
        "identifier",
    }


def test_load_metadata_file_normalizes_nested_json_values(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yaml"
    path.write_text(
        """\
        language: en-US
        title: Example
        authors:
          - Ada Author
        voice_defaults:
          narrator:
            voice: voice-1
            rate: 1.1
            enabled: true
        requires:
          - extension.example
        """,
        encoding="utf-8",
    )

    metadata = load_metadata_file(path)

    assert metadata == {
        "language": "en-US",
        "title": "Example",
        "authors": ["Ada Author"],
        "voice_defaults": {"narrator": {"voice": "voice-1", "rate": 1.1, "enabled": True}},
        "requires": ["extension.example"],
    }
    json.dumps(metadata, allow_nan=False)


def test_load_metadata_file_rejects_invalid_content(tmp_path: Path) -> None:
    invalid_content = [
        ("- language", "YAML mapping"),
        ("language: [", "invalid YAML"),
        ("unknown_field: true", "unsupported metadata key"),
        ("ssmd_version: '0.9'", "reserved"),
        ("7: invalid-key", "top-level keys must be strings"),
        ("voice_defaults:\n  7: invalid-key", "mapping keys.*must be strings"),
        ("voice_defaults: .nan", "NaN or Infinity"),
        ("voice_defaults: .inf", "NaN or Infinity"),
        ("voice_defaults: 2026-10-03", "not JSON-compatible"),
    ]
    path = tmp_path / "metadata.yaml"
    for text, message in invalid_content:
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            load_metadata_file(path)


def test_load_metadata_file_requires_utf8(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yaml"
    path.write_bytes(b"title: \xff")

    with pytest.raises(ValueError, match="UTF-8"):
        load_metadata_file(path)


def test_merge_document_metadata_uses_source_file_cli_precedence_without_mutation() -> None:
    source: dict[str, Any] = {
        "title": "Source title",
        "language": "en-US",
        "sequence_fallback_mode": "spell",
        "existing_extension": {"preserved": True},
    }
    file_overrides = {
        "title": "File title",
        "language": "fr-FR",
        "sequence_fallback_mode": "spell",
        "voice_defaults": {"narrator": "file-voice"},
    }

    result = merge_document_metadata(
        source,
        metadata_overrides=file_overrides,
        cli_overrides={"title": "CLI title"},
        language="de-DE",
        sequence_fallback_mode="preserve",
    )

    assert result == {
        "title": "CLI title",
        "language": "de-DE",
        "sequence_fallback_mode": "preserve",
        "existing_extension": {"preserved": True},
        "voice_defaults": {"narrator": "file-voice"},
    }
    assert source == {
        "title": "Source title",
        "language": "en-US",
        "sequence_fallback_mode": "spell",
        "existing_extension": {"preserved": True},
    }


def test_merge_document_metadata_keeps_file_language_without_cli_override() -> None:
    result = merge_document_metadata(
        {"language": "en-US"},
        metadata_overrides={"language": "fr-FR"},
        sequence_fallback_mode="spell",
    )

    assert result == {"language": "fr-FR", "sequence_fallback_mode": "spell"}


def test_merge_document_metadata_rejects_invalid_effective_sequence_mode() -> None:
    with pytest.raises(ValueError, match="sequence_fallback_mode"):
        merge_document_metadata({}, sequence_fallback_mode="invalid")  # type: ignore[arg-type]

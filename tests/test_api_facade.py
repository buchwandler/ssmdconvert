from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from epub_support import make_epub
from ssmd import parse_structure

import ssmdconvert
from ssmdconvert import (
    BookConversionOptions,
    BookConversionResult,
    DocumentConversionOptions,
    SpeechOptions,
    convert_book,
    convert_content,
    convert_document,
    inspect_document,
)
from ssmdconvert.speech.failures import SpeechFreezeFailure


def test_document_facade_uses_immutable_options(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("Hello.", encoding="utf-8")
    metadata = {"voice_defaults": {"narrator": {"rate": "slow"}}}
    options = DocumentConversionOptions(language="en-US", metadata_overrides=metadata)
    metadata["voice_defaults"]["narrator"]["rate"] = "fast"

    result = convert_document(source, options=options)
    header = parse_structure(result.ssmd, dialect="0.9").header

    assert header["language"] == "en-US"
    assert header["voice_defaults"]["narrator"]["rate"] == "slow"
    with pytest.raises(TypeError):
        options.metadata_overrides["voice_defaults"]["narrator"]["rate"] = "fast"
    assert "Hello." in inspect_document(source).sections[0].markdown


def test_convert_content_accepts_the_same_options_contract() -> None:
    result = convert_content(
        "Hello.",
        input_format="text",
        options=DocumentConversionOptions(
            title="Notes",
            language="fr-FR",
            metadata_overrides={"voice_defaults": {"narrator": {"rate": "slow"}}},
        ),
    )
    header = parse_structure(result.ssmd, dialect="0.9").header
    assert header["title"] == "Notes"
    assert header["language"] == "fr-FR"
    assert header["voice_defaults"]["narrator"]["rate"] == "slow"


def test_options_reject_invalid_values_and_unknown_fields() -> None:
    with pytest.raises(ValueError, match="spacy"):
        SpeechOptions(spacy=cast(Any, "download"))
    with pytest.raises(ValueError, match="max_paragraph_chars"):
        from ssmdconvert import TextProjectionOptions

        TextProjectionOptions(max_paragraph_chars=0)
    with pytest.raises(TypeError):
        SpeechOptions(**cast(Any, {"unknown": True}))
    with pytest.raises(TypeError, match="JSON-compatible"):
        DocumentConversionOptions(metadata_overrides={"title": object()})


def test_book_facade_returns_preserved_result_without_loading_spacy(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source, language=None, chapter_language=None)

    result = convert_book(
        source,
        options=BookConversionOptions(speech=SpeechOptions(mode="preserve", spacy="sm")),
    )

    assert isinstance(result, BookConversionResult)
    assert result.speech.status == "preserved"
    assert result.speech.summary is None
    assert result.speech.report["format"] == "ssmdconvert-speech-freeze-report"
    assert result.speech.report["complete"] is False


def test_book_facade_returns_freeze_evidence_and_immutable_report(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)

    structural = convert_book(
        source,
        options=BookConversionOptions(speech=SpeechOptions(mode="preserve")),
    )
    result = convert_book(source, options=BookConversionOptions())

    assert result.speech.status == "complete"
    assert result.speech.summary is not None and result.speech.summary.complete
    assert result.speech.report["status"] == "complete"
    assert isinstance(result.speech.report, Mapping)
    assert json.loads(json.dumps(result.speech.to_dict()))["complete"] is True
    with pytest.raises(TypeError):
        cast(Any, result.speech.report)["status"] = "preserved"
    for before, after in zip(structural.book.chapters, result.book.chapters, strict=True):
        assert (
            parse_structure(before.ssmd, dialect="0.9").clean_text
            == parse_structure(after.ssmd, dialect="0.9").clean_text
        )


def test_failed_freeze_exposes_structured_partial_report(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source, language=None, chapter_language=None)

    with pytest.raises(SpeechFreezeFailure) as caught:
        convert_book(source)

    assert caught.value.report["status"] == "incomplete"
    assert caught.value.report["complete"] is False
    assert caught.value.report["failure"]
    assert caught.value.summary.unresolved >= 0


def test_public_api_is_explicit_and_does_not_retain_ambiguous_convert_alias() -> None:
    assert "convert_document" in ssmdconvert.__all__
    assert "convert" not in ssmdconvert.__all__
    assert ssmdconvert.convert_document is convert_document


def test_kind_neutral_bundle_api_is_public_and_replaces_split_storage_exports() -> None:
    neutral_names = (
        "BundleConversionResult",
        "BundleInspection",
        "BundleWorkspace",
        "LoadedBundle",
        "BundleKind",
        "convert_bundle",
        "inspect_bundle_source",
        "load_bundle",
        "load_bundle_workspace",
        "pack_bundle",
        "refresh_bundle_workspace",
        "validate_bundle",
        "write_bundle",
    )
    assert set(neutral_names) <= set(ssmdconvert.__all__)
    assert all(getattr(ssmdconvert, name) is not None for name in neutral_names)

    removed_names = (
        "write_book_bundle",
        "load_book_bundle",
        "load_book_workspace",
        "refresh_book_workspace",
        "validate_book_bundle",
        "write_document_bundle",
        "load_document_bundle",
        "load_document_workspace",
        "refresh_document_workspace",
        "validate_document_bundle",
    )
    assert all(not hasattr(ssmdconvert, name) for name in removed_names)

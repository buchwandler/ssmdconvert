from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
import ttsready
from epub_support import make_epub
from typer.testing import CliRunner

from ssmdconvert.analysis.source import load_ssmd_source
from ssmdconvert.api import inventory_speech
from ssmdconvert.bundle import convert_bundle, pack_bundle
from ssmdconvert.cli import app
from ssmdconvert.linguistics import LinguisticResourcePool
from ssmdconvert.speech.inventory import inventory_loaded_source
from ssmdconvert.speech.profile import effective_replacements, parse_speech_profile


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "inventory.ssmd"
    path.write_text(
        f'---\nssmd_version: "0.9"\nlanguage: en-US\n---\n{body}\n',
        encoding="utf-8",
    )
    return path


def test_inventory_detects_orthographic_signals_and_existing_subs(tmp_path: Path) -> None:
    source_path = _source(
        tmp_path,
        "ART B-E SecUnit MotilitySys targetSystem screen/ID X12 A-17 R&D.\n\n"
        '[ART]{sub="A R T"} and [5 kg]{sub="five kilograms"}. Hello there.',
    )
    profile = parse_speech_profile(
        """schema = "ssmdconvert-speech-profile"
version = 1
[replacements]
"ART" = "art"
"B-E" = "B E"
"""
    )

    inventory = inventory_loaded_source(
        load_ssmd_source(source_path),
        pronunciations=effective_replacements(profile),
        max_contexts=1,
    )
    candidates = {candidate.surface: candidate for candidate in inventory.candidates}

    for surface in (
        "ART",
        "B-E",
        "SecUnit",
        "MotilitySys",
        "targetSystem",
        "screen/ID",
        "ID",
        "X12",
        "A-17",
        "R&D",
    ):
        assert surface in candidates
    assert "Hello" not in candidates
    assert candidates["ART"].count == 2
    assert candidates["ART"].profile_replacement == "art"
    assert candidates["ART"].profile_shadowed is True
    assert candidates["ART"].existing_spoken_forms == ("A R T",)
    assert "existing-sub" in candidates["ART"].reasons
    assert candidates["B-E"].profile_replacement == "B E"
    assert candidates["5 kg"].existing_spoken_forms == ("five kilograms",)
    assert candidates["5 kg"].reasons == ("existing-sub",)
    assert len(candidates["ART"].occurrences) == 1
    assert inventory.schema == "ssmdconvert.speech-inventory"
    assert inventory.version == 1
    assert inventory.candidates[0].surface == "ART"


def test_inventory_is_deterministic_and_bounds_contexts(tmp_path: Path) -> None:
    source_path = _source(tmp_path, "ART in one.\n\nART in two.\n\nART in three.")
    loaded = load_ssmd_source(source_path)

    first = inventory_loaded_source(loaded, max_contexts=2)
    second = inventory_loaded_source(loaded, max_contexts=2)
    candidate = next(item for item in first.candidates if item.surface == "ART")

    assert first == second
    assert candidate.count == 3
    assert len(candidate.occurrences) == 2
    assert [item.paragraph_index for item in candidate.occurrences] == [1, 2]


def test_inventory_can_exclude_existing_annotations_and_select_chapters(tmp_path: Path) -> None:
    source_path = _source(
        tmp_path,
        '[NASA]{sub="N A S A"} and [5 kg]{sub="five kilograms"} '
        '[screen/ID]{sub="screen identity"}.',
    )
    loaded = load_ssmd_source(source_path)

    included = inventory_loaded_source(loaded, pronunciations={"ID": "eye dee"})
    excluded = inventory_loaded_source(loaded, include_existing=False)
    included_candidates = {candidate.surface: candidate for candidate in included.candidates}
    excluded_candidates = {candidate.surface: candidate for candidate in excluded.candidates}
    assert included_candidates["NASA"].existing_spoken_forms == ("N A S A",)
    assert "existing-sub" in included_candidates["5 kg"].reasons
    assert included_candidates["ID"].existing_spoken_forms == ("screen identity",)
    assert included_candidates["ID"].profile_shadowed is True
    assert "existing-sub" not in excluded_candidates["ID"].reasons
    assert "5 kg" not in excluded_candidates
    assert "existing-sub" not in excluded_candidates["NASA"].reasons
    assert inventory_loaded_source(loaded, chapters="1").chapters == ("document-0001",)


def test_inventory_options_validate_context_limit_and_freeze_replacements() -> None:
    from ssmdconvert.speech.inventory import SpeechInventoryOptions

    with pytest.raises(ValueError, match="at least 0"):
        SpeechInventoryOptions(max_contexts=-1)
    with pytest.raises(TypeError, match="integer"):
        SpeechInventoryOptions(max_contexts=True)
    options = SpeechInventoryOptions(pronunciations={"ART": "art"})
    with pytest.raises(TypeError):
        cast(dict[str, str], options.pronunciations)["B-E"] = "B E"


def test_inventory_optional_spacy_metadata_uses_local_provider_interface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = _source(tmp_path, "SecUnit moved.")
    monkeypatch.setattr(
        LinguisticResourcePool,
        "resolve",
        lambda self, language, config=None, **kwargs: object(),
    )

    def analyze_text(self, text: str, selection: object, **kwargs: object):
        start = text.index("SecUnit")
        return (
            ttsready.LinguisticToken(
                start=start,
                end=start + len("SecUnit"),
                text="SecUnit",
                pos="PROPN",
                lemma="secunit",
                language="en",
            ),
        )

    monkeypatch.setattr(LinguisticResourcePool, "analyze_text", analyze_text)
    inventory = inventory_loaded_source(load_ssmd_source(source_path), spacy="sm")
    candidate = next(item for item in inventory.candidates if item.surface == "SecUnit")

    assert candidate.occurrences[0].pos == "PROPN"
    assert candidate.occurrences[0].proper_noun is True
    assert candidate.occurrences[0].lemma == "secunit"


def test_inventory_api_supports_single_documents_epub_and_bundles(tmp_path: Path) -> None:
    markdown = tmp_path / "story.md"
    markdown.write_text("# Story\n\nART and B-E appear here.\n", encoding="utf-8")
    markdown_inventory = inventory_speech(markdown)
    assert {item.surface for item in markdown_inventory.candidates} >= {"ART", "B-E"}
    assert not (tmp_path / "story.ssmd-bundle").exists()

    epub_path = tmp_path / "book.epub"
    make_epub(epub_path, chapter_one_suffix=" ART B-E.")
    epub_bytes = epub_path.read_bytes()
    epub_inventory = inventory_speech(epub_path)
    assert {item.surface for item in epub_inventory.candidates} >= {"ART", "B-E"}
    assert epub_path.read_bytes() == epub_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "book.epub",
        "story.md",
    ]


def test_inventory_api_reads_canonical_bundle_workspace(tmp_path: Path) -> None:
    source_path = _source(tmp_path, "ART is in the canonical bundle.")
    bundle_path = tmp_path / "story.ssmd-bundle"
    converted = convert_bundle(source_path, output=bundle_path)
    assert converted.output == bundle_path

    inventory = inventory_speech(bundle_path)

    assert inventory.candidates[0].surface == "ART"
    assert inventory.source == str(bundle_path)

    inside_workspace = CliRunner().invoke(
        app,
        [
            "speech",
            "inventory",
            str(bundle_path),
            "--format",
            "json",
            "--output",
            str(bundle_path / "inventory.json"),
        ],
    )
    assert inside_workspace.exit_code == 1
    assert not (bundle_path / "inventory.json").exists()

    archive_path = tmp_path / "story.ssmd-bundle.zip"
    pack_bundle(bundle_path, archive_path)
    archived_inventory = inventory_speech(archive_path)
    assert archived_inventory.candidates[0].surface == "ART"


def test_speech_inventory_cli_renders_json_table_and_profile_template(tmp_path: Path) -> None:
    source = _source(tmp_path, "ART met B-E. SecUnit moved.")
    profile_path = tmp_path / "speech.toml"
    profile_path.write_text(
        """schema = "ssmdconvert-speech-profile"
version = 1
[replacements]
"ART" = "art"
""",
        encoding="utf-8",
    )
    runner = CliRunner()

    json_result = runner.invoke(
        app,
        [
            "speech",
            "inventory",
            str(source),
            "--format",
            "json",
            "--speech-profile",
            str(profile_path),
        ],
    )
    assert json_result.exit_code == 0, json_result.output
    payload = json.loads(json_result.output)
    assert payload["schema"] == "ssmdconvert.speech-inventory"
    assert payload["version"] == 1
    assert payload["speech_profile"]["schema"] == "ssmdconvert-speech-profile"
    assert len(payload["speech_profile"]["fingerprint"]) == 64
    art = next(item for item in payload["candidates"] if item["surface"] == "ART")
    assert art["profile_replacement"] == "art"

    table_result = runner.invoke(
        app,
        ["speech", "inventory", str(source), "--speech-profile", str(profile_path)],
    )
    assert table_result.exit_code == 0, table_result.output
    assert "Surface" in table_result.output
    assert "Speech profile:" in table_result.output
    assert "SecUnit" in table_result.output

    toml_result = runner.invoke(
        app,
        [
            "speech",
            "inventory",
            str(source),
            "--format",
            "toml",
            "--speech-profile",
            str(profile_path),
        ],
    )
    assert toml_result.exit_code == 0, toml_result.output
    generated = parse_speech_profile(toml_result.output)
    assert dict(generated.replacements) == {"ART": "art"}
    assert '# "B-E" = ""' in toml_result.output
    assert "# Profile fingerprint:" in toml_result.output
    assert source.read_text(encoding="utf-8").endswith("ART met B-E. SecUnit moved.\n")

    output = tmp_path / "inventory.json"
    written = runner.invoke(
        app,
        ["speech", "inventory", str(source), "--format", "json", "--output", str(output)],
    )
    assert written.exit_code == 0, written.output
    first_bytes = output.read_bytes()
    refused = runner.invoke(
        app,
        ["speech", "inventory", str(source), "--format", "json", "--output", str(output)],
    )
    assert refused.exit_code == 1
    assert output.read_bytes() == first_bytes
    forced = runner.invoke(
        app,
        [
            "speech",
            "inventory",
            str(source),
            "--format",
            "json",
            "--output",
            str(output),
            "--force",
        ],
    )
    assert forced.exit_code == 0, forced.output
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == (
        "ssmdconvert.speech-inventory"
    )


def test_inventory_and_profile_models_are_exported_from_public_facades() -> None:
    from ssmdconvert import (
        SpeechInventory,
        SpeechInventoryOptions,
        SpeechReplacementProfile,
    )
    from ssmdconvert import inventory_speech as package_inventory_speech
    from ssmdconvert.speech import SpeechInventory as SpeechPackageInventory
    from ssmdconvert.speech import SpeechReplacementProfile as SpeechPackageProfile

    assert SpeechInventory is SpeechPackageInventory
    assert SpeechReplacementProfile is SpeechPackageProfile
    assert SpeechInventoryOptions().max_contexts == 2
    assert package_inventory_speech is inventory_speech

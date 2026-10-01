from pathlib import Path

import pytest

from ssmdconvert import Converter, SpeechPreparationOptions, convert
from ssmdconvert.errors import UnsupportedInputError


def test_convenience_convert(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("Hello", encoding="utf-8")
    assert "Hello" in convert(source).ssmd


def test_unsupported_suffix_is_clear(tmp_path: Path) -> None:
    source = tmp_path / "a.xyz"
    source.write_text("Hello", encoding="utf-8")
    with pytest.raises(UnsupportedInputError):
        Converter().convert(source)


def test_converter_speech_modes_are_opt_in_and_keep_document_source(tmp_path: Path) -> None:
    source = tmp_path / "speech.ssmd"
    source.write_text(
        '---\nssmd_version: "0.9"\nlanguage: en\n---\nH2O has 5 kg.\n',
        encoding="utf-8",
    )
    converter = Converter()
    default = converter.convert(source)
    audit = converter.convert(
        source,
        speech_options=SpeechPreparationOptions(mode="audit"),
    )
    annotated = converter.convert(
        source,
        speech_options=SpeechPreparationOptions(
            mode="annotate",
            pronunciations={"H2O": "water"},
        ),
    )

    assert default.speech_report is None
    assert audit.ssmd == default.ssmd
    assert audit.speech_report is not None
    assert audit.speech_report.changes
    assert '[H2O]{sub="water"}' in annotated.ssmd
    assert '[5 kg]{sub="five kilograms"}' in annotated.ssmd
    assert "H2O has 5 kg." in annotated.document.sections[0].markdown
    assert annotated.speech_report is not None
    assert all(change.status == "applied" for change in annotated.speech_report.changes)


def test_converter_strict_speech_rejects_replacement_character(tmp_path: Path) -> None:
    source = tmp_path / "broken.ssmd"
    source.write_text(
        '---\nssmd_version: "0.9"\nlanguage: en\n---\ncaf�.\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Speech QC strict mode failed"):
        Converter().convert(
            source,
            speech_options=SpeechPreparationOptions(mode="audit", strict=True),
        )


def test_converter_annotation_requires_an_effective_language(tmp_path: Path) -> None:
    source = tmp_path / "plain.txt"
    source.write_text("H2O.", encoding="utf-8")

    with pytest.raises(ValueError, match="speech annotation requires --language"):
        Converter().convert(
            source,
            speech_options=SpeechPreparationOptions(mode="annotate"),
        )

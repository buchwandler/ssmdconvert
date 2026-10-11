from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from ssmd import ParseStructureResult, TextSpan, parse_structure
from ttsready import SpokenChange

from ssmdconvert.analysis.models import LoadedSsmdSection, LoadedSsmdSource
from ssmdconvert.analysis.prepare import analyze_ssmd_source
from ssmdconvert.errors import MappingError, MaterializationError
from ssmdconvert.speech.mapping import map_analysis_changes, source_range_for_clean_span
from ssmdconvert.speech.materialize import materialize_substitutions
from ssmdconvert.speech.workflows import materialize_analysis


def _document(body: str) -> str:
    return f'---\nssmd_version: "0.9"\nlanguage: en-US\ntitle: "Sample"\n---\n{body}\n'


def _structure(source: str) -> ParseStructureResult:
    return parse_structure(source, dialect="0.9", normalize=False)


def test_parser_owned_span_maps_plain_leaf_and_repeated_word_by_coordinates() -> None:
    source = _document("repeat, then repeat.")
    structure = _structure(source)
    second = structure.clean_text.rindex("repeat")

    raw_range = source_range_for_clean_span(
        source,
        structure,
        second,
        second + len("repeat"),
        expected_text="repeat",
    )

    assert raw_range is not None
    assert source[raw_range[0] : raw_range[1]] == "repeat"
    assert raw_range[0] == source.rindex("repeat")


def test_annotation_adjacent_and_multiple_text_leaves_map_exactly() -> None:
    source = _document('Before [AWS]{sub="Amazon Web Services"} after [N]{sub="number"}.')
    structure = _structure(source)

    first = source_range_for_clean_span(source, structure, 0, 7, expected_text="Before ")
    middle_start = structure.clean_text.index(" after")
    middle = source_range_for_clean_span(
        source,
        structure,
        middle_start,
        middle_start + len(" after"),
        expected_text=" after",
    )
    last_start = structure.clean_text.index("N.")
    final = source_range_for_clean_span(
        source,
        structure,
        last_start,
        last_start + 1,
        expected_text="N",
    )

    assert first is not None and source[first[0] : first[1]] == "Before "
    assert middle is not None and source[middle[0] : middle[1]] == " after"
    assert final is not None and source[final[0] : final[1]] == "N"


def test_escaped_leaf_and_normalized_whitespace_fail_closed() -> None:
    source = _document(r"Use \*5 kg\* and 5 kg.")
    structure = _structure(source)
    first = structure.clean_text.index("5 kg")
    assert (
        source_range_for_clean_span(source, structure, first, first + 4, expected_text="5 kg")
        is None
    )

    normalized = ParseStructureResult(
        clean_text="A B",
        text_spans=(TextSpan(0, 3, 0, 4),),
    )
    assert source_range_for_clean_span("A  B", normalized, 0, 3, expected_text="A B") is None


def test_cross_leaf_change_and_wrong_expected_source_are_unmappable() -> None:
    source = _document('Before [AWS]{sub="Amazon Web Services"} after.')
    structure = _structure(source)
    start = structure.clean_text.index("Before")
    end = structure.clean_text.index("after") + len("after")

    assert (
        source_range_for_clean_span(
            source,
            structure,
            start,
            end,
            expected_text=structure.clean_text[start:end],
        )
        is None
    )
    assert (
        source_range_for_clean_span(
            source,
            structure,
            start,
            start + len("Before"),
            expected_text="Wrong!",
        )
        is None
    )


def test_analysis_mapping_preserves_generic_change_identity_and_exact_raw_slices(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "speech.ssmd"
    source_path.write_text(_document("Dr. Smith has 5 kg."), encoding="utf-8")
    analysis = analyze_ssmd_source(source_path)

    mapped = map_analysis_changes(analysis)

    assert mapped
    for item in mapped:
        assert item.change.id.startswith("chg:v1:")
        assert item.change.unit_id.startswith("unit:v1:")
        if item.mapping_status == "exact":
            assert item.raw_source_start is not None and item.raw_source_end is not None
            section = next(
                section for section in analysis.sections if section.id == item.section_id
            )
            assert section.ssmd[item.raw_source_start : item.raw_source_end] == item.change.source


def test_materialization_preserves_visible_text_and_is_idempotent(tmp_path: Path) -> None:
    source_path = tmp_path / "speech.ssmd"
    source = _document("Dr. Smith has 5 kg.")
    source_path.write_text(source, encoding="utf-8")
    analysis = analyze_ssmd_source(source_path)
    mapped = map_analysis_changes(analysis)
    section = analysis.sections[0]
    result = materialize_substitutions(
        section.ssmd,
        analysis.structures[section.id],
        (item for item in mapped if item.section_id == section.id),
    )

    before = _structure(section.ssmd)
    after = _structure(result.ssmd)
    assert result.ssmd != section.ssmd
    assert after.clean_text == before.clean_text
    before_sub_count = sum("sub" in annotation.attrs for annotation in before.annotations)
    after_sub_count = sum("sub" in annotation.attrs for annotation in after.annotations)
    applied_count = sum(item.materialization_status == "applied" for item in result.changes)
    assert after_sub_count - before_sub_count == applied_count
    assert all(
        item.materialization_status == "applied"
        for item in result.changes
        if item.mapping_status == "exact" and item.reason is None
    )

    second_path = tmp_path / "frozen.ssmd"
    second_path.write_text(result.ssmd, encoding="utf-8")
    second_analysis = analyze_ssmd_source(second_path)
    second_mapped = map_analysis_changes(second_analysis)
    second = materialize_substitutions(
        second_analysis.sections[0].ssmd,
        second_analysis.structures[section.id],
        second_mapped,
    )
    assert second.ssmd == result.ssmd


def test_materialization_rejects_unmappable_overlapping_and_stale_ranges(tmp_path: Path) -> None:
    path = tmp_path / "speech.ssmd"
    path.write_text(_document("Dr. Smith has 5 kg."), encoding="utf-8")
    analysis = analyze_ssmd_source(path)
    mapped = map_analysis_changes(analysis)
    section = analysis.sections[0]
    structure = analysis.structures[section.id]
    available = next(item for item in mapped if item.mapping_status == "exact")

    unsafe = replace(
        available,
        mapping_status="unmappable",
        materialization_status="unresolved",
        raw_source_start=None,
        raw_source_end=None,
        reason="test source mismatch",
    )
    with pytest.raises(MaterializationError, match="test source mismatch"):
        materialize_substitutions(section.ssmd, structure, (unsafe,))

    second = replace(
        available,
        change=replace(available.change, id="second-change"),
        raw_source_start=available.raw_source_start,
        raw_source_end=available.raw_source_end,
    )
    with pytest.raises(MaterializationError, match="overlap"):
        materialize_substitutions(section.ssmd, structure, (available, second))

    stale = replace(available, raw_source_start=0, raw_source_end=1)
    with pytest.raises(MappingError, match="source changed"):
        materialize_substitutions(section.ssmd, structure, (stale,))


def test_mapping_classifies_every_overlapping_change_as_unresolved(tmp_path: Path) -> None:
    path = tmp_path / "overlap.ssmd"
    path.write_text(_document("Measure 5 kg."), encoding="utf-8")
    analysis = analyze_ssmd_source(path)
    mapped = map_analysis_changes(analysis)
    candidate = next(item for item in mapped if item.mapping_status == "exact")
    duplicate = replace(candidate.change, id="chg:test-overlap")
    analysis = replace(
        analysis,
        preparation=replace(analysis.preparation, changes=(candidate.change, duplicate)),
    )

    conflicts = map_analysis_changes(analysis)

    assert len(conflicts) == 2
    assert all(item.final_disposition == "unresolved" for item in conflicts)
    assert all(item.reason and "overlap" in item.reason for item in conflicts)
    with pytest.raises(MaterializationError, match="overlap"):
        materialize_analysis(analysis)


def test_unrepresentable_replacement_is_classified_unresolved(tmp_path: Path) -> None:
    path = tmp_path / "unrepresentable.ssmd"
    path.write_text(_document("Measure 5 kg."), encoding="utf-8")
    analysis = analyze_ssmd_source(path)
    mapped = map_analysis_changes(analysis)
    candidate = next(item for item in mapped if item.mapping_status == "exact")
    invalid = replace(candidate.change, replacement="spoken\non two lines")
    analysis = replace(
        analysis,
        preparation=replace(analysis.preparation, changes=(invalid,)),
    )

    unresolved = map_analysis_changes(analysis)[0]

    assert unresolved.final_disposition == "unresolved"
    assert unresolved.reason is not None and "line breaks" in unresolved.reason
    with pytest.raises(MaterializationError, match="line breaks"):
        materialize_analysis(analysis)


def test_existing_author_sub_is_never_materialized_again(tmp_path: Path) -> None:
    source = _document('[AWS]{sub="Amazon Web Services"}.')
    path = tmp_path / "author.ssmd"
    path.write_text(source, encoding="utf-8")
    analysis = analyze_ssmd_source(path)

    mapped = map_analysis_changes(analysis)
    authoritative = next(item for item in mapped if item.change.source == "AWS")
    result = materialize_substitutions(
        analysis.sections[0].ssmd,
        analysis.structures[analysis.sections[0].id],
        mapped,
    )

    assert authoritative.materialization_status == "already-authoritative"
    assert result.ssmd == analysis.sections[0].ssmd
    assert result.ssmd.count("{sub=") == 1




def test_different_author_sub_remains_the_final_authority(tmp_path: Path) -> None:
    source = _document('[5 kg]{sub="five kilos"}.')
    path = tmp_path / "manual.ssmd"
    path.write_text(source, encoding="utf-8")
    analysis = analyze_ssmd_source(path)

    mapped = map_analysis_changes(analysis)
    author_change = next(item for item in mapped if item.change.source == "5 kg")
    result = materialize_substitutions(
        analysis.sections[0].ssmd,
        analysis.structures[analysis.sections[0].id],
        mapped,
    )

    assert author_change.change.replacement == "five kilos"
    assert author_change.final_disposition == "already-authoritative"
    assert result.ssmd == source
    assert result.changes[0].final_disposition == "already-authoritative"


@pytest.mark.parametrize(
    "attribute",
    ['as="digits"', 'say-as="digits"', 'phoneme="F A I V"'],
)
def test_author_owned_speech_attributes_receive_explicit_disposition(
    tmp_path: Path, attribute: str
) -> None:
    source = _document(f"[5]{{{attribute}}}.")
    path = tmp_path / "protected.ssmd"
    loaded = LoadedSsmdSource(
        path=path,
        kind="ssmd",
        input_format="ssmd",
        title=None,
        metadata={"language": "en-US"},
        sections=(
            LoadedSsmdSection(
                id="document-0001",
                index=1,
                title=None,
                level=1,
                ssmd=source,
            ),
        ),
        source_sha256="0" * 64,
        content_fingerprint="1" * 64,
        workspace_type="standalone",
        workspace_status="valid",
    )
    analysis = analyze_ssmd_source(loaded, include_titles=False)
    prepared_unit = next(unit for unit in analysis.preparation.units if unit.role == "prose")
    injected = SpokenChange(
        id="chg:test-author-owned",
        unit_id=prepared_unit.unit_id,
        source_start=0,
        source_end=1,
        output_start=0,
        output_end=4,
        source="5",
        replacement="five",
        stages=("test",),
        kind="test",
        rule="test",
        recognition_domain=None,
        provenance={"origin": "test"},
        language="en-US",
    )
    analysis = replace(
        analysis,
        preparation=replace(analysis.preparation, changes=(injected,)),
    )

    mapped = map_analysis_changes(analysis)
    result = materialize_analysis(analysis)

    assert len(mapped) == 1
    assert mapped[0].mapping_status == "protected"
    assert mapped[0].final_disposition == "author-owned"
    assert result.section_ssmd[analysis.sections[0].id] == source
    assert result.changes[0].materialization_status == "author-owned"
    assert result.summary.author_owned == 1
    assert result.summary.complete

def test_escaped_automatic_change_remains_reportable_but_cannot_be_written(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "escaped.ssmd"
    source_path.write_text(_document(r"Use \*5 kg\*."), encoding="utf-8")
    analysis = analyze_ssmd_source(source_path)

    mapped = map_analysis_changes(analysis)
    escaped_change = mapped[0]

    assert escaped_change.mapping_status == "unmappable"
    assert escaped_change.materialization_status == "unresolved"
    assert escaped_change.final_disposition == "unresolved"
    with pytest.raises(MaterializationError, match="cannot safely materialize"):
        materialize_substitutions(
            analysis.sections[0].ssmd,
            analysis.structures[analysis.sections[0].id],
            mapped,
        )


def test_synthetic_title_changes_have_no_fabricated_source_offsets(tmp_path: Path) -> None:
    source = '---\nssmd_version: "0.9"\nlanguage: en-US\ntitle: "Dr. Sample"\n---\nBody text.\n'
    path = tmp_path / "title.ssmd"
    path.write_text(source, encoding="utf-8")

    analysis = analyze_ssmd_source(path)
    mapped = map_analysis_changes(analysis)
    title_changes = [item for item in mapped if item.is_title]

    assert title_changes
    assert all(item.mapping_status == "synthetic" for item in title_changes)
    assert all(item.final_disposition == "unresolved" for item in title_changes)
    assert all(
        item.raw_source_start is None and item.raw_source_end is None for item in title_changes
    )


def test_materialization_uses_existing_ssmd_attribute_escaping(tmp_path: Path) -> None:
    source_path = tmp_path / "escaping.ssmd"
    source = _document("Measure 5 kg.")
    source_path.write_text(source, encoding="utf-8")
    analysis = analyze_ssmd_source(source_path)
    mapped = map_analysis_changes(analysis)
    target = next(item for item in mapped if item.change.source == "5 kg")
    custom = replace(
        target,
        change=replace(target.change, replacement='say "five" [kg] {unit} \\'),
    )
    section = analysis.sections[0]

    result = materialize_substitutions(
        section.ssmd,
        analysis.structures[section.id],
        (custom,),
    )

    assert r'[5 kg]{sub="say \"five\" \[kg\] \{unit\} \\"}' in result.ssmd
    assert _structure(result.ssmd).clean_text == _structure(source).clean_text

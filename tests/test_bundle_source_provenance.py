from __future__ import annotations

from pathlib import Path

import ssmdconvert


def test_inspect_bundle_source_provenance_matches_and_detects_changed_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "story.md"
    source.write_text("# Story\n\nOriginal text.\n", encoding="utf-8")
    bundle = tmp_path / "story.ssmd-bundle"
    ssmdconvert.convert_bundle(source, output=bundle)

    matching = ssmdconvert.inspect_bundle_source_provenance(source, bundle)
    assert matching.state == "match"
    assert matching.matches is True
    assert matching.source_sha256_matches is True
    assert matching.replacement_safe is True

    source.write_text("# Story\n\nChanged text.\n", encoding="utf-8")
    stale = ssmdconvert.inspect_bundle_source_provenance(source, bundle)
    assert stale.state == "stale"
    assert stale.matches is False
    assert stale.source_sha256_matches is False
    assert stale.replacement_safe is True


def test_source_provenance_does_not_certify_replacement_of_edited_bundle(
    tmp_path: Path,
) -> None:
    source = tmp_path / "story.md"
    source.write_text("# Story\n\nOriginal text.\n", encoding="utf-8")
    bundle = tmp_path / "story.ssmd-bundle"
    ssmdconvert.convert_bundle(source, output=bundle)

    workspace = ssmdconvert.load_bundle_workspace(bundle)
    document_path = bundle / workspace.value.status.path
    document_path.write_text('---\nssmd_version: "0.9"\n---\n\nEdited.\n', encoding="utf-8")

    inspection = ssmdconvert.inspect_bundle_source_provenance(source, bundle)
    assert inspection.state == "stale"
    assert inspection.replacement_safe is False
    assert "user-edited" in (inspection.reason or "")

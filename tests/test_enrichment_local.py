import pytest
from ssmd import to_text

from ssmdconvert.enrich import enrich_ssmd


def test_speaker_enrichment_requires_cloud_only_for_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = '---\nssmd_version: "0.9"\ntitle: Demo\n---\nAlice said, “Hello.”\n'

    def fail(*args, **kwargs):
        raise AssertionError("JEV should not be called for explicit attribution")

    monkeypatch.setattr("ssmdconvert.enrich.pipeline.attribute_turn", fail)
    result = enrich_ssmd(source, speakers_enabled=True)
    assert '[“Hello.”]{voice="alice"}' in result.ssmd
    assert ':::{voice="narrator"}' in result.ssmd
    assert to_text(result.ssmd) == to_text(source)

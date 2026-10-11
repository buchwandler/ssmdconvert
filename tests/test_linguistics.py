from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
import ttsready

from ssmdconvert.errors import LinguisticsError
from ssmdconvert.linguistics import (
    LinguisticResourcePool,
    LinguisticsConfig,
    model_name,
    normalize_language,
)


def _fake_spacy(monkeypatch, installed: tuple[str, ...], *, load_error: Exception | None = None):
    load_calls: list[str] = []
    download_calls: list[str] = []

    def load(name: str):
        load_calls.append(name)
        if load_error is not None:
            raise load_error

        def pipeline(text: str):
            token_text = text.split()[0]
            return (
                SimpleNamespace(
                    idx=0,
                    text=token_text,
                    pos_="NOUN",
                    tag_="NN",
                    lemma_=token_text.lower(),
                ),
            )

        return pipeline

    def download(name: str):
        download_calls.append(name)
        raise AssertionError("conversion must not download models")

    module = SimpleNamespace(
        util=SimpleNamespace(get_installed_models=lambda: installed),
        load=load,
        download=download,
    )
    monkeypatch.setitem(sys.modules, "spacy", module)
    versions = {"spacy": "3.8.0", **{name: "3.8.0" for name in installed}}
    monkeypatch.setattr(
        "ssmdconvert.linguistics.version",
        lambda name: versions.get(name, "unknown"),
    )
    return load_calls, download_calls


def test_default_off_policy_does_not_import_spacy(monkeypatch):
    def fail_import(_name: str):
        raise AssertionError("off policy must not import spaCy")

    monkeypatch.setattr("ssmdconvert.linguistics.importlib.import_module", fail_import)
    selection = LinguisticResourcePool().resolve("en-US")

    assert selection.policy == "off"
    assert selection.provider == "none"
    assert selection.model is None
    assert selection.cache_identity() == {
        "policy": "off",
        "provider": "none",
        "language": "en-US",
    }


@pytest.mark.parametrize(
    ("language", "tier", "expected"),
    (
        ("en-US", "sm", "en_core_web_sm"),
        ("zh-CN", "trf", "zh_core_web_trf"),
        ("fr_FR", "md", "fr_core_news_md"),
        ("de-DE", "lg", "de_core_news_lg"),
    ),
)
def test_model_names_normalize_language_and_resolve_supported_tiers(language, tier, expected):
    assert model_name(language, tier) == expected
    assert normalize_language(language) == expected.split("_", 1)[0]


@pytest.mark.parametrize("tier", ("sm", "md", "lg", "trf"))
def test_explicit_policy_requires_and_selects_its_local_model(monkeypatch, tier):
    expected = model_name("en-US", tier)
    _fake_spacy(monkeypatch, (expected,))

    selection = LinguisticResourcePool().resolve("en-US", LinguisticsConfig(tier))

    assert selection.provider == "spacy"
    assert selection.model == expected
    assert selection.spacy_version == "3.8.0"
    assert selection.model_version == "3.8.0"


def test_auto_prefers_smallest_installed_tier_and_never_downloads(monkeypatch):
    installed = tuple(model_name("en-US", tier) for tier in ("lg", "md", "trf", "sm"))
    _load_calls, download_calls = _fake_spacy(monkeypatch, installed)

    selection = LinguisticResourcePool().resolve("en-US", LinguisticsConfig("auto"))

    assert selection.model == "en_core_web_sm"
    assert selection.cache_identity() == {
        "policy": "auto",
        "provider": "spacy",
        "language": "en-US",
        "model": "en_core_web_sm",
        "spacy_version": "3.8.0",
        "model_version": "3.8.0",
    }
    assert download_calls == []


def test_auto_falls_back_when_spacy_or_compatible_local_model_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "spacy", None)
    pool = LinguisticResourcePool()
    no_package = pool.resolve("en-US", LinguisticsConfig("auto"))
    assert no_package.provider == "none"
    assert no_package.fallback_reason == "spaCy package is not installed"
    assert pool.analyze_text("text", no_package) == ()

    _fake_spacy(monkeypatch, ("fr_core_news_sm",))
    no_language_model = LinguisticResourcePool().resolve("en-US", LinguisticsConfig("auto"))
    assert no_language_model.provider == "none"
    assert "no compatible local spaCy model" in (no_language_model.fallback_reason or "")


def test_explicit_missing_model_has_actionable_local_install_error(monkeypatch):
    _fake_spacy(monkeypatch, ())

    with pytest.raises(LinguisticsError, match="en_core_web_sm.*not installed") as caught:
        LinguisticResourcePool().resolve("en-US", LinguisticsConfig("sm"))

    assert "never downloads" in str(caught.value)
    assert "--spacy auto/off" in str(caught.value)


def test_resource_pool_loads_each_model_once_and_returns_only_neutral_tokens(monkeypatch):
    _load_calls, download_calls = _fake_spacy(
        monkeypatch,
        ("en_core_web_sm", "fr_core_news_sm"),
    )
    pool = LinguisticResourcePool()
    english = pool.resolve("en-US", LinguisticsConfig("auto"))
    french = pool.resolve("fr-FR", LinguisticsConfig("auto"))

    first = pool.analyze_text("Hello there", english)
    second = pool.analyze_text("Hello again", english)
    french_tokens = pool.analyze_text("bonjour monde", french)

    assert _load_calls == ["en_core_web_sm", "fr_core_news_sm"]
    assert download_calls == []
    assert first == second
    assert first == (ttsready.LinguisticToken(0, 5, "Hello", "NOUN", "NN", "hello", "en-US"),)
    assert french_tokens[0].language == "fr-FR"
    assert all(isinstance(token, ttsready.LinguisticToken) for token in (*first, *french_tokens))
    assert not any(hasattr(token, "pipe") or hasattr(token, "vocab") for token in first)


def test_spacy_loading_errors_are_domain_errors_and_pool_can_be_cleared(monkeypatch):
    _load_calls, _download_calls = _fake_spacy(
        monkeypatch,
        ("en_core_web_sm",),
        load_error=OSError("broken package"),
    )
    pool = LinguisticResourcePool()
    selection = pool.resolve("en-US", LinguisticsConfig("sm"))

    with pytest.raises(LinguisticsError, match="could not load locally installed.*broken package"):
        pool.analyze_text("Hello", selection)

    pool.clear()
    assert pool._pipelines == {}
    assert pool._spacy is None


def test_unknown_model_distribution_version_uses_loaded_metadata_without_analysis(monkeypatch):
    load_calls = []
    analyze_calls = []

    class Pipeline:
        meta = {"version": "2.4.1"}

        def __call__(self, text):
            analyze_calls.append(text)
            return ()

    pipeline = Pipeline()
    fake_spacy = SimpleNamespace(
        util=SimpleNamespace(get_installed_models=lambda: ("en_core_web_sm",)),
        load=lambda name: load_calls.append(name) or pipeline,
    )
    monkeypatch.setitem(sys.modules, "spacy", fake_spacy)
    monkeypatch.setattr("ssmdconvert.linguistics.version", lambda _name: "unknown")
    pool = LinguisticResourcePool()

    selection = pool.resolve("en-US", LinguisticsConfig("sm"))

    assert selection.model_version == "2.4.1"
    assert load_calls == ["en_core_web_sm"]
    assert analyze_calls == []
    pool.analyze_text("hello", selection)
    assert load_calls == ["en_core_web_sm"]
    assert analyze_calls == ["hello"]

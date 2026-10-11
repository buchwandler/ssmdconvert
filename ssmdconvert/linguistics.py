"""Caller-owned spaCy policy, local model resolution, and neutral token hints."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from ttsready import LinguisticToken

from .errors import LinguisticsError
from .progress import ProgressCallback, emit_progress

SpacyPolicy = Literal["off", "auto", "sm", "md", "lg", "trf"]
_AUTO_TIERS: tuple[Literal["sm", "md", "lg", "trf"], ...] = ("sm", "md", "lg", "trf")
_VALID_POLICIES = frozenset({"off", "auto", "sm", "md", "lg", "trf"})


@dataclass(frozen=True, slots=True)
class LinguisticsConfig:
    """Application-owned linguistic provider policy; deterministic by default."""

    spacy: SpacyPolicy = "off"

    def __post_init__(self) -> None:
        if self.spacy not in _VALID_POLICIES:
            raise ValueError("spacy must be one of: off, auto, sm, md, lg, trf")


@dataclass(frozen=True, slots=True)
class LinguisticModelSelection:
    """Resolved, cache-safe identity for one effective language."""

    policy: SpacyPolicy
    provider: Literal["none", "spacy"]
    language: str
    model: str | None = None
    spacy_version: str | None = None
    model_version: str | None = None
    fallback_reason: str | None = None

    def cache_identity(self) -> dict[str, str]:
        """Return canonical primitive values suitable for an analysis cache key."""
        identity = {
            "policy": self.policy,
            "provider": self.provider,
            "language": self.language,
        }
        if self.model is not None:
            identity["model"] = self.model
            identity["spacy_version"] = self.spacy_version or "unknown"
            identity["model_version"] = self.model_version or "unknown"
        return identity


def normalize_language(language: str) -> str:
    """Reduce a BCP 47 or underscore language tag to its primary subtag."""
    if not isinstance(language, str) or not language.strip():
        raise ValueError("language must be a non-empty language tag")
    primary = language.strip().replace("_", "-").split("-", 1)[0].lower()
    if not primary.isalpha():
        raise ValueError(f"language tag has no valid primary language subtag: {language!r}")
    return primary


def model_name(language: str, tier: Literal["sm", "md", "lg", "trf"]) -> str:
    """Resolve the standard spaCy package name for a language and model tier."""
    primary = normalize_language(language)
    family = "web" if primary in {"en", "zh"} else "news"
    return f"{primary}_core_{family}_{tier}"


def _distribution_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unknown"


def _missing_spacy_message(policy: SpacyPolicy) -> str:
    return (
        f"spaCy is required for --spacy {policy}. Install 'ssmdconvert[spacy]' and the requested "
        "local language model; SSMDConvert never downloads spaCy or models during conversion."
    )


class LinguisticResourcePool:
    """Lazily inspect spaCy and cache loaded pipelines by exact model name."""

    def __init__(self) -> None:
        self._spacy: Any | None = None
        self._spacy_unavailable = False
        self._pipelines: dict[str, Any] = {}

    def clear(self) -> None:
        """Forget provider and pipeline references, primarily for isolated tests."""
        self._spacy = None
        self._spacy_unavailable = False
        self._pipelines.clear()

    def _module(self, policy: SpacyPolicy) -> Any | None:
        if self._spacy_unavailable:
            if policy == "auto":
                return None
            raise LinguisticsError(_missing_spacy_message(policy))
        if self._spacy is not None:
            return self._spacy
        try:
            self._spacy = importlib.import_module("spacy")
        except (ImportError, ModuleNotFoundError) as exc:
            self._spacy_unavailable = True
            if policy == "auto":
                return None
            raise LinguisticsError(_missing_spacy_message(policy)) from exc
        return self._spacy

    def resolve(
        self,
        language: str,
        config: LinguisticsConfig | None = None,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> LinguisticModelSelection:
        """Resolve local model identity without running NLP over any input text."""
        selected_config = config or LinguisticsConfig()
        if not isinstance(selected_config, LinguisticsConfig):
            raise TypeError("config must be a LinguisticsConfig")
        if not isinstance(language, str) or not language.strip():
            raise ValueError("language must be a non-empty language tag")
        policy = selected_config.spacy
        if policy == "off":
            return LinguisticModelSelection(policy, "none", language)

        spacy = self._module(policy)
        if spacy is None:
            return LinguisticModelSelection(
                policy,
                "none",
                language,
                fallback_reason="spaCy package is not installed",
            )

        try:
            installed = set(spacy.util.get_installed_models())
        except Exception as exc:
            if policy == "auto":
                return LinguisticModelSelection(
                    policy,
                    "none",
                    language,
                    fallback_reason=f"could not inspect local spaCy models: {exc}",
                )
            raise LinguisticsError(
                f"could not inspect locally installed spaCy models: {exc}"
            ) from exc

        if policy == "auto":
            selected_model = next(
                (
                    candidate
                    for tier in _AUTO_TIERS
                    if (candidate := model_name(language, tier)) in installed
                ),
                None,
            )
            if selected_model is None:
                return LinguisticModelSelection(
                    policy,
                    "none",
                    language,
                    fallback_reason=f"no compatible local spaCy model is installed for {language}",
                )
        else:
            selected_model = model_name(language, policy)
            if selected_model not in installed:
                raise LinguisticsError(
                    f"spaCy model {selected_model!r} is required for language {language} but is "
                    "not installed. Install that local model or use --spacy auto/off; "
                    "SSMDConvert never downloads models during conversion."
                )

        spacy_version = _distribution_version("spacy")
        if spacy_version == "unknown":
            module_version = getattr(spacy, "__version__", None)
            if module_version:
                spacy_version = str(module_version)
        selection = LinguisticModelSelection(
            policy=policy,
            provider="spacy",
            language=language,
            model=selected_model,
            spacy_version=spacy_version,
            model_version=_distribution_version(selected_model),
        )
        if selection.model_version == "unknown":
            pipeline = self.load(selection, on_progress=on_progress)
            metadata = getattr(pipeline, "meta", {})
            if isinstance(metadata, Mapping) and metadata.get("version"):
                selection = replace(selection, model_version=str(metadata["version"]))
        return selection

    def load(
        self,
        selection: LinguisticModelSelection,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> Any | None:
        """Load a resolved local model once and reuse it by exact package name."""
        if selection.provider == "none" or selection.model is None:
            return None
        pipeline = self._pipelines.get(selection.model)
        if pipeline is not None:
            return pipeline
        spacy = self._module(selection.policy)
        if spacy is None:
            raise LinguisticsError(_missing_spacy_message(selection.policy))
        emit_progress(
            on_progress,
            "model.started",
            "linguistics.model",
            language=selection.language,
            provider="spacy",
            model=selection.model,
        )
        try:
            pipeline = spacy.load(selection.model)
        except Exception as exc:
            raise LinguisticsError(
                f"could not load locally installed spaCy model {selection.model!r}: {exc}. "
                "Check the local model installation; SSMDConvert will not download it."
            ) from exc
        self._pipelines[selection.model] = pipeline
        emit_progress(
            on_progress,
            "model.completed",
            "linguistics.model",
            language=selection.language,
            provider="spacy",
            model=selection.model,
        )
        return pipeline

    def analyze_text(
        self,
        text: str,
        selection: LinguisticModelSelection,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> tuple[LinguisticToken, ...]:
        """Return provider-neutral token facts at offsets into the exact input text."""
        if not isinstance(text, str):
            raise TypeError("linguistic analysis text must be a string")
        pipeline = self.load(selection, on_progress=on_progress)
        if pipeline is None:
            return ()
        try:
            from ttsready import LinguisticToken

            document = pipeline(text)
            return tuple(
                LinguisticToken(
                    start=int(token.idx),
                    end=int(token.idx + len(token.text)),
                    text=str(token.text),
                    pos=getattr(token, "pos_", None) or None,
                    tag=getattr(token, "tag_", None) or None,
                    lemma=getattr(token, "lemma_", None) or None,
                    language=selection.language,
                )
                for token in document
            )
        except Exception as exc:
            raise LinguisticsError(
                f"spaCy model {selection.model!r} could not analyze text for "
                f"{selection.language}: {exc}"
            ) from exc


__all__ = [
    "LinguisticModelSelection",
    "LinguisticResourcePool",
    "LinguisticsConfig",
    "SpacyPolicy",
    "model_name",
    "normalize_language",
]

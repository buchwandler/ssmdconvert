"""Optional JEV-backed semantic enrichment.

Imports of pyjev and sfxrender are intentionally lazy. Core conversion remains local.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import MissingDependencyError
from .base import EnrichmentDecision
from .speakers import DialogueTurn, Speaker


@dataclass(frozen=True, slots=True)
class VoiceCandidate:
    id: str
    text: str


def _jev_modules() -> tuple[Any, Any, Any]:
    try:
        from pyjev import Jev
        from pyjev.recipes.find import Candidate, find
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise MissingDependencyError(
            "JEV enrichment requires: pip install 'ssmdconvert[jev]'"
        ) from exc
    return Jev, Candidate, find


def attribute_turn(
    turn: DialogueTurn,
    speakers: list[Speaker],
    *,
    model: str | None = None,
    min_probability: float = 0.55,
) -> tuple[str | None, EnrichmentDecision]:
    Jev, Candidate, find = _jev_modules()
    available = [speaker for speaker in speakers if speaker.id != "narrator"]
    if not available:
        return None, EnrichmentDecision(
            "speaker", turn.id, None, 0.0, detail={"verdict": "no_candidates"}
        )
    candidates = [
        Candidate(
            id=speaker.id,
            text=f"Speaker: {speaker.name}. Evidence: {'; '.join(speaker.evidence) or 'none'}.",
        )
        for speaker in available
    ]
    query = (
        "Identify who speaks this quoted dialogue using only the supplied cast. "
        "If the context does not support any supplied speaker, do not force a match.\n"
        f"Quote: {turn.quote}\nContext: {turn.context}"
    )
    with Jev(model=model) as jev:
        result = find(jev, query, candidates, top_k=min(5, len(candidates)), model=model)
    top = result.hits[0] if result.hits else None
    selected = None
    confidence = top.probability if top is not None else 0.0
    if result.exists_verdict == "answered" and top is not None and confidence >= min_probability:
        selected = top.id
    decision = result.decision
    return selected, EnrichmentDecision(
        kind="speaker",
        target=turn.id,
        value=selected,
        confidence=confidence,
        request_id=decision.request_id,
        model=decision.model,
        detail=result.to_dict(),
    )


def choose_voice(
    speaker: Speaker,
    voices: list[VoiceCandidate],
    *,
    model: str | None = None,
    min_probability: float = 0.50,
) -> tuple[str | None, EnrichmentDecision]:
    Jev, Candidate, find = _jev_modules()
    if not voices:
        return None, EnrichmentDecision("voice", speaker.id, None, 0.0)
    if len(voices) > 254:
        raise ValueError("JEV voice casting supports at most 254 candidates per request")
    mapped = {f"v{index:04d}": item for index, item in enumerate(voices, start=1)}
    candidates = [
        Candidate(id=internal_id, text=f"Provider voice ID: {item.id}. {item.text}")
        for internal_id, item in mapped.items()
    ]
    query = (
        f"Choose the best audiobook TTS voice for speaker {speaker.name}. "
        f"Evidence: {'; '.join(speaker.evidence) or 'none'}. "
        "Choose only from the supplied finite inventory."
    )
    with Jev(model=model) as jev:
        result = find(jev, query, candidates, top_k=min(5, len(candidates)), model=model)
    top = result.hits[0] if result.hits else None
    selected = None
    confidence = top.probability if top is not None else 0.0
    if result.exists_verdict == "answered" and top is not None and confidence >= min_probability:
        selected = mapped[top.id].id
    decision = result.decision
    return selected, EnrichmentDecision(
        kind="voice",
        target=speaker.id,
        value=selected,
        confidence=confidence,
        request_id=decision.request_id,
        model=decision.model,
        detail=result.to_dict(),
    )


def sfx_catalog_candidates() -> tuple[list[Any], dict[str, dict[str, Any]]]:
    Jev, Candidate, _find = _jev_modules()
    del Jev, _find
    try:
        from sfxrender import llm_catalog
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise MissingDependencyError(
            "SFX enrichment requires: pip install 'ssmdconvert[jev,sfx]'"
        ) from exc
    manifest = llm_catalog()
    effects = dict(manifest.get("effects", {}))
    candidates = []
    for effect_id, descriptor in sorted(effects.items()):
        llm = descriptor.get("llm", {})
        use_when = "; ".join(llm.get("use_when", []))
        avoid_when = "; ".join(llm.get("avoid_when", []))
        candidates.append(
            Candidate(
                id=effect_id,
                text=(
                    f"Effect: {effect_id}. {descriptor.get('description', '')} "
                    f"Use when: {use_when or 'unspecified'}. "
                    f"Avoid when: {avoid_when or 'unspecified'}."
                ),
            )
        )
    return candidates, effects


def choose_sfx(
    paragraph: str,
    *,
    model: str | None = None,
    min_probability: float = 0.62,
) -> tuple[str | None, str | None, EnrichmentDecision]:
    Jev, _Candidate, find = _jev_modules()
    candidates, effects = sfx_catalog_candidates()
    if not candidates:
        return None, None, EnrichmentDecision("sfx", paragraph[:80], None, 0.0)
    query = (
        "For an enhanced audiobook, choose a foreground sound effect only if the prose "
        "explicitly or strongly implies an audible event that materially supports the scene. "
        "Prefer no candidate over decorative over-sonification. "
        "Choose only from the supplied catalog.\n"
        f"Prose: {paragraph}"
    )
    with Jev(model=model) as jev:
        result = find(jev, query, candidates, top_k=min(5, len(candidates)), model=model)
    top = result.hits[0] if result.hits else None
    selected = None
    uri = None
    confidence = top.probability if top is not None else 0.0
    if result.exists_verdict == "answered" and top is not None and confidence >= min_probability:
        examples = effects[top.id].get("llm", {}).get("examples", [])
        if examples:
            selected = top.id
            uri = str(examples[0])
            try:
                from sfxrender import SFXRenderer

                SFXRenderer().validate_uri(uri)
            except ImportError as exc:  # pragma: no cover
                raise MissingDependencyError(
                    "SFX enrichment requires: pip install 'ssmdconvert[jev,sfx]'"
                ) from exc
    decision = result.decision
    return (
        selected,
        uri,
        EnrichmentDecision(
            kind="sfx",
            target=paragraph[:120],
            value=uri,
            confidence=confidence,
            request_id=decision.request_id,
            model=decision.model,
            detail=result.to_dict(),
        ),
    )

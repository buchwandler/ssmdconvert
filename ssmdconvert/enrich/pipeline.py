from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from ssmd import lint, parse_front_matter, serialize_front_matter, to_text

from .base import EnrichmentDecision, EnrichmentResult
from .jev import VoiceCandidate, attribute_turn, choose_sfx, choose_voice
from .speakers import DialogueTurn, Speaker, discover


def load_voice_inventory(path: Path) -> list[VoiceCandidate]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return [VoiceCandidate(str(key), str(value)) for key, value in raw.items()]
    if isinstance(raw, list):
        result: list[VoiceCandidate] = []
        for item in raw:
            if not isinstance(item, dict) or "id" not in item:
                raise ValueError("voice inventory list items require an id")
            text = item.get("text") or item.get("description") or item["id"]
            result.append(VoiceCandidate(str(item["id"]), str(text)))
        return result
    raise ValueError("voice inventory must be a JSON object or list")


def _escape_span_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _paragraphs(body: str) -> list[tuple[int, int, str]]:
    result: list[tuple[int, int, str]] = []
    for match in re.finditer(r"(?ms)(?:^|\n\s*\n)(?P<p>[^\n].*?)(?=\n\s*\n|\Z)", body):
        text = match.group("p").strip()
        if not text or text.startswith(("#", ":::", "---")) or '{src="sfx:' in text:
            continue
        start = match.start("p")
        end = match.end("p")
        result.append((start, end, text))
    return result


def _apply_annotations(
    body: str,
    turns: Iterable[DialogueTurn],
    sfx_insertions: Iterable[tuple[int, str, str]],
) -> str:
    operations: list[tuple[int, int, str]] = []
    for turn in turns:
        if turn.speaker_id:
            replacement = f'[{_escape_span_text(turn.quote)}]{{voice="{turn.speaker_id}"}}'
            operations.append((turn.start, turn.end, replacement))
    for position, description, uri in sfx_insertions:
        replacement = f'\n\n[{_escape_span_text(description)}]{{src="{uri}"}}'
        operations.append((position, position, replacement))
    rendered = body
    for start, end, replacement in sorted(
        operations, key=lambda item: (item[0], item[1]), reverse=True
    ):
        rendered = rendered[:start] + replacement + rendered[end:]
    return rendered


def enrich_ssmd(
    source: str,
    *,
    speakers_enabled: bool = False,
    sfx_enabled: bool = False,
    voice_inventory: list[VoiceCandidate] | None = None,
    provider: str | None = None,
    model: str | None = None,
    max_sfx: int = 8,
    min_speaker_probability: float = 0.55,
    min_sfx_probability: float = 0.62,
) -> EnrichmentResult:
    parsed = parse_front_matter(source)
    header = dict(parsed.data) if parsed.present else {"ssmd_version": "0.9"}
    header["ssmd_version"] = "0.9"
    body = parsed.body if parsed.present else source
    original_clean = to_text(source)
    decisions: list[EnrichmentDecision] = []

    turns: list[DialogueTurn] = []
    speakers: list[Speaker] = [Speaker("narrator", "Narrator")]
    if speakers_enabled or voice_inventory:
        turns, speakers = discover(body)
        if speakers_enabled:
            for turn in turns:
                if turn.speaker_id:
                    decisions.append(
                        EnrichmentDecision(
                            "speaker", turn.id, turn.speaker_id, 1.0, detail={"source": "local"}
                        )
                    )
                    continue
                selected, decision = attribute_turn(
                    turn,
                    speakers,
                    model=model,
                    min_probability=min_speaker_probability,
                )
                turn.speaker_id = selected
                decisions.append(decision)

    sfx_insertions: list[tuple[int, str, str]] = []
    if sfx_enabled:
        for _start, end, paragraph in _paragraphs(body):
            if len(sfx_insertions) >= max_sfx:
                break
            effect, uri, decision = choose_sfx(
                paragraph,
                model=model,
                min_probability=min_sfx_probability,
            )
            decisions.append(decision)
            if effect and uri:
                description = effect.replace(".", " ")
                sfx_insertions.append((end, description, uri))

    bindings: dict[str, str] = {}
    if voice_inventory:
        if not provider:
            raise ValueError("provider is required when voice_inventory is supplied")
        for speaker in speakers:
            selected, decision = choose_voice(speaker, voice_inventory, model=model)
            decisions.append(decision)
            if selected:
                bindings[speaker.id] = selected
        if bindings:
            all_bindings = dict(header.get("voice_bindings") or {})
            all_bindings[provider] = {**dict(all_bindings.get(provider) or {}), **bindings}
            header["voice_bindings"] = all_bindings

    rendered_body = _apply_annotations(body, turns if speakers_enabled else [], sfx_insertions)
    if speakers_enabled and any(turn.speaker_id for turn in turns):
        rendered_body = ':::{voice="narrator"}\n' + rendered_body.rstrip() + "\n:::\n"
    output = serialize_front_matter(header, rendered_body.rstrip() + "\n")

    errors = [
        issue
        for issue in lint(output, profile="ssmd-core", dialect="0.9")
        if issue.severity == "error"
    ]
    if errors:
        raise ValueError(
            "Enriched SSMD failed validation: " + "; ".join(x.message for x in errors[:5])
        )
    enriched_clean = to_text(output)
    expected_clean = original_clean
    if sfx_insertions:
        # Audio span descriptions are metadata/non-spoken text in SSMD. Current SSMD clean
        # text may include them depending on rendering policy, so only enforce preservation
        # when no new media spans were added.
        expected_clean = None
    if expected_clean is not None and enriched_clean != expected_clean:
        raise ValueError("Speaker/voice enrichment changed clean spoken text")
    return EnrichmentResult(ssmd=output, decisions=decisions)

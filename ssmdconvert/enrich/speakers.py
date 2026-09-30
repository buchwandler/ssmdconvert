from __future__ import annotations

import re
from dataclasses import dataclass, field

_QUOTE_RE = re.compile(r"(?P<curly>“[^”\n]+”)|(?P<straight>\"[^\"\n\r]+\")")
_NAME = r"[A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ'’-]*(?:[ \t]+[A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ'’-]*){0,2}"
_VERB = r"said|asked|replied|answered|whispered|shouted|cried|murmured|called|added|continued"
_BEFORE_RE = re.compile(rf"(?P<name>{_NAME})\s+(?:{_VERB})[^.!?\n]{{0,80}}$", re.IGNORECASE)
_AFTER_RE = re.compile(rf"^[\s,;:—–-]*(?P<name>{_NAME})\s+(?:{_VERB})\b", re.IGNORECASE)
_PRONOUNS = {"he", "she", "they", "i", "we", "you", "it"}


@dataclass(slots=True)
class Speaker:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DialogueTurn:
    id: str
    start: int
    end: int
    quote: str
    context: str
    local_hint: str | None = None
    speaker_id: str | None = None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "speaker"


def _hint(text: str, start: int, end: int) -> str | None:
    before = text[max(0, start - 140) : start]
    after = text[end : min(len(text), end + 140)]
    match = _BEFORE_RE.search(before) or _AFTER_RE.search(after)
    if not match:
        return None
    name = match.group("name").strip()
    return None if name.casefold() in _PRONOUNS else name


def discover(text: str, *, context_chars: int = 260) -> tuple[list[DialogueTurn], list[Speaker]]:
    turns: list[DialogueTurn] = []
    names: dict[str, Speaker] = {}
    used: set[str] = {"narrator"}
    for index, match in enumerate(_QUOTE_RE.finditer(text), start=1):
        hint = _hint(text, match.start(), match.end())
        turn = DialogueTurn(
            id=f"turn-{index:04d}",
            start=match.start(),
            end=match.end(),
            quote=match.group(0),
            context=text[
                max(0, match.start() - context_chars) : min(len(text), match.end() + context_chars)
            ].strip(),
            local_hint=hint,
        )
        turns.append(turn)
        if hint:
            key = hint.casefold()
            if key not in names:
                base = _slug(hint)
                candidate = base
                suffix = 2
                while candidate in used:
                    candidate = f"{base}-{suffix}"
                    suffix += 1
                used.add(candidate)
                names[key] = Speaker(candidate, hint, evidence=["explicit dialogue attribution"])
            turn.speaker_id = names[key].id
    speakers = [Speaker("narrator", "Narrator", evidence=["default narration role"])]
    speakers.extend(sorted(names.values(), key=lambda item: item.id))
    return turns, speakers

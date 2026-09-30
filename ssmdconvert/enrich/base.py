from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class EnrichmentDecision:
    kind: str
    target: str
    value: str | None
    confidence: float | None = None
    request_id: str | None = None
    model: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EnrichmentResult:
    ssmd: str
    decisions: list[EnrichmentDecision] = field(default_factory=list)

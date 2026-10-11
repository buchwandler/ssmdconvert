"""Typed, provider-neutral progress events for synchronous SSMDConvert APIs."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

ProgressKind = Literal[
    "phase.started",
    "phase.completed",
    "chapter.started",
    "chapter.completed",
    "unit.started",
    "unit.completed",
    "model.started",
    "model.completed",
    "cache.hit",
    "cache.miss",
]
ProgressCallback = Callable[["ProgressEvent"], None]


class ProgressCallbackFailure(Exception):
    """Internal transport so application error wrappers can re-raise observer failures."""

    def __init__(self, original: BaseException) -> None:
        self.original = original
        super().__init__(str(original))


_PROGRESS_KINDS = frozenset(
    {
        "phase.started",
        "phase.completed",
        "chapter.started",
        "chapter.completed",
        "unit.started",
        "unit.completed",
        "model.started",
        "model.completed",
        "cache.hit",
        "cache.miss",
    }
)


def _freeze_json(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} must contain only finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError(f"{name} object keys must be strings")
        return MappingProxyType({key: _freeze_json(item, name) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, name) for item in value)
    raise TypeError(f"{name} must contain only JSON-safe values")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Immutable progress observation containing only provider-neutral, JSON-safe data."""

    kind: ProgressKind
    phase: str
    completed: int | None = None
    total: int | None = None
    chapter_id: str | None = None
    source_number: int | None = None
    title: str | None = None
    unit_id: str | None = None
    language: str | None = None
    provider: str | None = None
    model: str | None = None
    message: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in _PROGRESS_KINDS:
            raise ValueError(f"unsupported progress event kind: {self.kind!r}")
        if not isinstance(self.phase, str) or not self.phase.strip():
            raise ValueError("progress phase must be a non-empty string")
        if self.completed is not None and (
            isinstance(self.completed, bool)
            or not isinstance(self.completed, int)
            or self.completed < 0
        ):
            raise ValueError("progress completed must be a non-negative integer or None")
        if self.total is not None and (
            isinstance(self.total, bool) or not isinstance(self.total, int) or self.total < 0
        ):
            raise ValueError("progress total must be a non-negative integer or None")
        if self.completed is not None and self.total is not None and self.completed > self.total:
            raise ValueError("progress completed cannot exceed total")
        if not isinstance(self.details, Mapping):
            raise TypeError("progress details must be a mapping")
        object.__setattr__(self, "details", _freeze_json(self.details, "progress details"))

    def to_dict(self) -> dict[str, Any]:
        """Return a plain JSON-serializable representation."""
        return {
            "kind": self.kind,
            "phase": self.phase,
            "completed": self.completed,
            "total": self.total,
            "chapter_id": self.chapter_id,
            "source_number": self.source_number,
            "title": self.title,
            "unit_id": self.unit_id,
            "language": self.language,
            "provider": self.provider,
            "model": self.model,
            "message": self.message,
            "details": _thaw_json(self.details),
        }


def emit_progress(
    callback: ProgressCallback | None,
    kind: ProgressKind,
    phase: str,
    **values: Any,
) -> None:
    """Synchronously notify a caller; callback exceptions intentionally propagate."""
    if callback is not None:
        callback(ProgressEvent(kind=kind, phase=phase, **values))

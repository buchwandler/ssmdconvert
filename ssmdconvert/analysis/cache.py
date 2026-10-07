"""Versioned JSON analysis and per-chapter caches owned by ssmdconvert."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import ttsready
from ttsready import PreparationResult, PreparationStats, SpeechOverride

from ..errors import AnalysisCacheError, AnalysisError, ContextLookupError
from .fingerprints import (
    canonical_json_bytes,
    chapter_analysis_key,
    sha256_bytes,
    ssmd_analysis_id,
)
from .models import LoadedSsmdSource, SsmdAnalysis, SsmdAnalysisReport, select_sections
from .prepare import (
    _pronunciation_overrides,
    _stored_sequence_fallback,
    analyze_ssmd_source,
)
from .projection import ProjectedText, project_txt
from .reporting import build_analysis_report, report_to_dict
from .serialization import json_bytes, parse_json_bytes, to_json_value
from .source import load_ssmd_source
from .units import extract_units

ANALYSIS_SCHEMA = "ssmdconvert.analysis.v1"
CHAPTER_SCHEMA = "ssmdconvert.chapter-analysis.v1"
INDEX_SCHEMA = "ssmdconvert.analysis-index.v1"
_ANALYSIS_ID = re.compile(r"ana:v1:[0-9a-f]{20}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_INDEX_BYTES = 2 * 1024 * 1024
_MAX_CHAPTER_CACHE_BYTES = 64 * 1024 * 1024
_MAX_SNAPSHOT_BYTES = 128 * 1024 * 1024
_MAX_SNAPSHOTS_PER_SOURCE = 50


def default_cache_root() -> Path:
    """Return the platform cache location scoped to ssmdconvert."""
    if os.environ.get("XDG_CACHE_HOME"):
        base = Path(os.environ["XDG_CACHE_HOME"]).expanduser()
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Cache"
    else:
        base = Path.home() / ".cache"
    return base / "ssmdconvert"


def _source_path(source: str | Path) -> Path:
    try:
        return Path(source).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AnalysisCacheError(f"cannot resolve analysis source {source}: {exc}") from exc


def _below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _write_atomic(path: Path, data: bytes, *, root: Path) -> None:
    try:
        root.mkdir(parents=True, exist_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        resolved_root = root.resolve(strict=True)
        resolved_parent = path.parent.resolve(strict=True)
        if not _below(resolved_parent, resolved_root):
            raise AnalysisCacheError(f"cache path escapes the cache root: {path}")
        if path.is_symlink():
            raise AnalysisCacheError(f"cache record must not be a symbolic link: {path}")
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=resolved_parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            if hasattr(os, "O_DIRECTORY"):
                directory_fd = os.open(resolved_parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)
    except AnalysisCacheError:
        raise
    except OSError as exc:
        raise AnalysisCacheError(f"could not write analysis cache record {path}: {exc}") from exc


def _read_json(path: Path, *, root: Path, max_bytes: int) -> Any:
    if path.is_symlink():
        raise AnalysisCacheError(f"cache record must not be a symbolic link: {path}")
    try:
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        if not _below(resolved, resolved_root) or not resolved.is_file():
            raise AnalysisCacheError(f"invalid cache record path: {path}")
        size = resolved.stat().st_size
        if size > max_bytes:
            raise AnalysisCacheError(f"cache record exceeds the {max_bytes}-byte limit: {path}")
        data = resolved.read_bytes()
        if len(data) > max_bytes:
            raise AnalysisCacheError(f"cache record exceeds the {max_bytes}-byte limit: {path}")
    except AnalysisCacheError:
        raise
    except OSError as exc:
        raise AnalysisCacheError(f"could not read analysis cache record {path}: {exc}") from exc
    return parse_json_bytes(data, display=str(path))


def _analysis_id_path(value: str) -> str:
    if _ANALYSIS_ID.fullmatch(value) is None:
        raise AnalysisCacheError(f"invalid analysis ID in cache index: {value!r}")
    return value.rsplit(":", 1)[-1]


def _validate_snapshot(value: Any, *, analysis_id: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != ANALYSIS_SCHEMA:
        raise AnalysisCacheError("unsupported or malformed ssmdconvert analysis snapshot schema")
    current_id = value.get("analysis_id")
    if not isinstance(current_id, str) or _ANALYSIS_ID.fullmatch(current_id) is None:
        raise AnalysisCacheError("analysis snapshot has an invalid analysis_id")
    if analysis_id is not None and current_id != analysis_id:
        raise AnalysisCacheError("analysis snapshot ID does not match its cache path")
    digest = value.get("snapshot_sha256")
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise AnalysisCacheError("analysis snapshot is missing a valid snapshot checksum")
    unhashed = dict(value)
    unhashed.pop("snapshot_sha256", None)
    try:
        expected_digest = hashlib.sha256(canonical_json_bytes(unhashed)).hexdigest()
    except Exception as exc:
        raise AnalysisCacheError(f"analysis snapshot cannot be fingerprinted: {exc}") from exc
    if digest != expected_digest:
        raise AnalysisCacheError("analysis snapshot checksum does not match its content")

    source = value.get("source")
    if (
        not isinstance(source, dict)
        or not isinstance(source.get("path"), str)
        or not isinstance(source.get("source_sha256"), str)
        or _SHA256.fullmatch(source["source_sha256"]) is None
        or not isinstance(source.get("content_fingerprint"), str)
        or _SHA256.fullmatch(source["content_fingerprint"]) is None
    ):
        raise AnalysisCacheError("analysis snapshot is missing a valid source identity")
    selected = source.get("selected_sections")
    if not isinstance(selected, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("sha256"), str)
        or _SHA256.fullmatch(item["sha256"]) is None
        for item in selected
    ):
        raise AnalysisCacheError("analysis snapshot has invalid selected section hashes")
    section_ids = [item["id"] for item in selected]
    if len(section_ids) != len(set(section_ids)):
        raise AnalysisCacheError("analysis snapshot contains duplicate selected section IDs")

    options = value.get("options")
    preparation = value.get("preparation")
    app = value.get("app")
    if (
        not isinstance(options, dict)
        or not isinstance(preparation, dict)
        or not isinstance(app, dict)
    ):
        raise AnalysisCacheError("analysis snapshot is missing options, preparation, or app data")
    try:
        preparation_result = ttsready.result_from_dict(preparation)
    except Exception as exc:
        raise AnalysisCacheError(
            f"analysis snapshot has an invalid ttsready result: {exc}"
        ) from exc
    try:
        expected_id = ssmd_analysis_id(
            source_content_fingerprint=source["content_fingerprint"],
            selected_sections=selected,
            options=options,
            profile_fingerprint=preparation_result.profile_fingerprint,
            override_fingerprint=preparation_result.override_fingerprint,
            runtime_fingerprint=preparation_result.runtime_fingerprint,
        )
    except Exception as exc:
        raise AnalysisCacheError(f"analysis snapshot has invalid semantic inputs: {exc}") from exc
    if current_id != expected_id:
        raise AnalysisCacheError("analysis snapshot ID does not match its semantic inputs")

    list_fields = ("contexts", "mapped_changes", "section_stats", "issues", "projection_items")
    object_fields = ("unit_locators", "unit_contexts", "projection", "report", "chapter_cache_keys")
    if any(not isinstance(app.get(key), list) for key in list_fields):
        raise AnalysisCacheError("analysis snapshot app data contains a non-array field")
    if any(not isinstance(app.get(key), dict) for key in object_fields):
        raise AnalysisCacheError("analysis snapshot app data contains a non-object field")

    contexts = app["contexts"]
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("section_id"), str)
        or item.get("section_id") not in section_ids
        or not isinstance(item.get("source_text"), str)
        or not isinstance(item.get("is_title"), bool)
        or not isinstance(item.get("paragraph_index"), int)
        or isinstance(item.get("paragraph_index"), bool)
        or not isinstance(item.get("unit_ids"), list)
        or any(not isinstance(unit_id, str) for unit_id in item["unit_ids"])
        for item in contexts
    ):
        raise AnalysisCacheError("analysis snapshot contains malformed app contexts")
    context_ids = [item["id"] for item in contexts]
    if len(context_ids) != len(set(context_ids)):
        raise AnalysisCacheError("analysis snapshot contains duplicate context IDs")
    context_units = {item["id"]: set(item["unit_ids"]) for item in contexts}

    unit_locators = app["unit_locators"]
    unit_contexts = app["unit_contexts"]
    prepared_unit_ids = {unit.unit_id for unit in preparation_result.units}
    if set(unit_locators) != prepared_unit_ids or set(unit_contexts) != prepared_unit_ids:
        raise AnalysisCacheError("analysis snapshot unit locators do not match prepared units")
    for unit_id, locator in unit_locators.items():
        if (
            not isinstance(locator, dict)
            or not isinstance(locator.get("section_id"), str)
            or locator["section_id"] not in section_ids
            or not isinstance(locator.get("language"), str)
        ):
            raise AnalysisCacheError(f"analysis snapshot has an invalid locator for {unit_id}")
        context_id = unit_contexts[unit_id]
        if not isinstance(context_id, str) or context_id not in context_units:
            raise AnalysisCacheError(f"analysis snapshot has an invalid context link for {unit_id}")
        if unit_id not in context_units[context_id]:
            raise AnalysisCacheError(f"analysis snapshot context {context_id} omits unit {unit_id}")
    if any(unit_id not in unit_locators for context in contexts for unit_id in context["unit_ids"]):
        raise AnalysisCacheError("analysis snapshot context references an unknown unit")

    section_stats = app["section_stats"]
    if any(
        (
            not isinstance(item, dict)
            or item.get("section_id") not in section_ids
            or not isinstance(item.get("index"), int)
            or isinstance(item.get("index"), bool)
            or item.get("title") is not None
            and not isinstance(item.get("title"), str)
        )
        for item in section_stats
    ):
        raise AnalysisCacheError("analysis snapshot contains invalid section statistics")
    if [item["section_id"] for item in section_stats] != section_ids:
        raise AnalysisCacheError("analysis snapshot section statistics do not match its selection")
    if set(app["chapter_cache_keys"]) != set(section_ids) or any(
        not isinstance(key, str) or _SHA256.fullmatch(key) is None
        for key in app["chapter_cache_keys"].values()
    ):
        raise AnalysisCacheError("analysis snapshot chapter cache keys do not match its selection")

    generic_change_ids = [item.id for item in preparation_result.changes]
    mapped_changes = app["mapped_changes"]
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("unit_id"), str)
        or item.get("unit_id") not in prepared_unit_ids
        or item.get("section_id") not in section_ids
        or not isinstance(item.get("source"), str)
        or not isinstance(item.get("replacement"), str)
        or not isinstance(item.get("stages"), list)
        or any(not isinstance(stage, str) for stage in item["stages"])
        or not isinstance(item.get("provenance"), dict)
        or not isinstance(item.get("ssmd"), dict)
        for item in mapped_changes
    ):
        raise AnalysisCacheError("analysis snapshot contains malformed mapped changes")
    if [item["id"] for item in mapped_changes] != generic_change_ids:
        raise AnalysisCacheError("analysis snapshot mapped changes do not match ttsready changes")
    if any(not isinstance(issue, dict) for issue in app["issues"]):
        raise AnalysisCacheError("analysis snapshot contains malformed issues")

    projected_parts: list[str] = []
    for item in app["projection_items"]:
        if (
            not isinstance(item, dict)
            or item.get("context_id") not in context_ids
            or item.get("section_id") not in section_ids
            or not isinstance(item.get("prepared_text"), str)
            or not isinstance(item.get("parts"), list)
            or any(not isinstance(part, str) for part in item["parts"])
            or "".join(item["parts"]) != item["prepared_text"]
        ):
            raise AnalysisCacheError("analysis snapshot contains malformed projected text")
        projected_parts.extend(part for part in item["parts"] if part)
    projected_text = "\n\n".join(projected_parts)
    projected_hash = hashlib.sha256(projected_text.encode("utf-8")).hexdigest()
    projection = app["projection"]
    if (
        projection.get("prepared_output_sha256") != projected_hash
        or projection.get("output_chars") != len(projected_text)
        or projection.get("output_lines") != len(projected_text.splitlines())
    ):
        raise AnalysisCacheError(
            "analysis snapshot projection statistics do not match projected text"
        )
    report = app["report"]
    reproducibility = report.get("reproducibility")
    report_source = report.get("source")
    if (
        not isinstance(reproducibility, dict)
        or reproducibility.get("prepared_output_sha256") != projected_hash
        or reproducibility.get("analysis_id") != current_id
        or not isinstance(report_source, dict)
        or report_source.get("content_fingerprint") != source["content_fingerprint"]
    ):
        raise AnalysisCacheError(
            "analysis report identity or projection hash does not match its snapshot"
        )
    return value


@dataclass(frozen=True, slots=True)
class CachedAnalysis:
    analysis: SsmdAnalysis
    projection: ProjectedText
    report: SsmdAnalysisReport
    analysis_id: str
    chapter_cache_hits: int
    chapter_cache_misses: int


class AnalysisCache:
    """Safe cache storage with immutable chapter results and source indexes."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or default_cache_root()).expanduser().resolve()

    def _chapter_path(self, key: str) -> Path:
        if _SHA256.fullmatch(key) is None:
            raise AnalysisCacheError("invalid chapter cache key")
        return self.root / "chapters" / f"{key}.json"

    def get_chapter(
        self,
        key: str,
        *,
        section_id: str,
        unit_ids: tuple[str, ...],
        profile_fingerprint: str,
        override_fingerprint: str,
        runtime_fingerprint: str,
    ) -> PreparationResult | None:
        path = self._chapter_path(key)
        if not path.exists() and not path.is_symlink():
            return None
        record = _read_json(path, root=self.root, max_bytes=_MAX_CHAPTER_CACHE_BYTES)
        if isinstance(record, dict):
            record_hash = record.get("record_sha256")
            unhashed = dict(record)
            unhashed.pop("record_sha256", None)
            if (
                not isinstance(record_hash, str)
                or record_hash != hashlib.sha256(canonical_json_bytes(unhashed)).hexdigest()
            ):
                raise AnalysisCacheError(f"chapter analysis checksum does not match: {path}")
        if (
            not isinstance(record, dict)
            or record.get("schema") != CHAPTER_SCHEMA
            or record.get("cache_key") != key
            or record.get("section_id") != section_id
            or not isinstance(record.get("preparation"), dict)
        ):
            raise AnalysisCacheError(f"malformed chapter analysis record: {path}")
        try:
            result = ttsready.result_from_dict(record["preparation"])
        except Exception as exc:
            raise AnalysisCacheError(
                f"invalid ttsready result in chapter cache {path}: {exc}"
            ) from exc
        if tuple(unit.unit_id for unit in result.units) != unit_ids:
            raise AnalysisCacheError(
                f"chapter cache units do not match current section {section_id}"
            )
        if result.profile_fingerprint != profile_fingerprint:
            raise AnalysisCacheError(f"chapter cache profile is stale for {section_id}")
        if result.override_fingerprint != override_fingerprint:
            raise AnalysisCacheError(f"chapter cache overrides are stale for {section_id}")
        if result.runtime_fingerprint != runtime_fingerprint:
            raise AnalysisCacheError(f"chapter cache runtime is stale for {section_id}")
        return result

    def put_chapter(self, key: str, section_id: str, result: PreparationResult) -> None:
        record = {
            "schema": CHAPTER_SCHEMA,
            "cache_key": key,
            "section_id": section_id,
            "preparation": ttsready.result_to_dict(result),
        }
        record["record_sha256"] = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
        data = json_bytes(record)
        if len(data) > _MAX_CHAPTER_CACHE_BYTES:
            raise AnalysisCacheError("chapter analysis result exceeds the cache size limit")
        _write_atomic(self._chapter_path(key), data, root=self.root)

    def _snapshot_path(self, analysis_id: str, source_path: Path) -> Path:
        identity = _analysis_id_path(analysis_id)
        path_digest = sha256_bytes(str(source_path).encode("utf-8"))
        return self.root / "analyses" / f"{identity}-{path_digest}.json"

    def _index_path(self, source_path: Path) -> Path:
        path_hash = sha256_bytes(str(source_path).encode("utf-8"))
        return self.root / "index" / f"{path_hash}.json"

    def _read_index(self, source_path: Path) -> list[str]:
        path = self._index_path(source_path)
        if not path.exists() and not path.is_symlink():
            return []
        value = _read_json(path, root=self.root, max_bytes=_MAX_INDEX_BYTES)
        if (
            not isinstance(value, dict)
            or value.get("schema") != INDEX_SCHEMA
            or value.get("source_path") != str(source_path)
            or not isinstance(value.get("analysis_ids"), list)
        ):
            raise AnalysisCacheError(f"malformed analysis index: {path}")
        ids = value["analysis_ids"]
        if (
            len(ids) > _MAX_SNAPSHOTS_PER_SOURCE
            or any(
                not isinstance(item, str) or _ANALYSIS_ID.fullmatch(item) is None for item in ids
            )
            or len(ids) != len(set(ids))
        ):
            raise AnalysisCacheError(f"analysis index contains invalid analysis IDs: {path}")
        return ids

    def save_snapshot(self, source_path: str | Path, snapshot: dict[str, Any]) -> None:
        canonical_source = _source_path(source_path)
        snapshot_value = dict(snapshot)
        snapshot_value["schema"] = ANALYSIS_SCHEMA
        analysis_id = snapshot_value.get("analysis_id")
        _analysis_id_path(analysis_id if isinstance(analysis_id, str) else "")
        source = snapshot_value.get("source")
        if not isinstance(source, dict):
            raise AnalysisCacheError("analysis snapshot is missing its source object")
        snapshot_value["analysis_id"] = analysis_id
        source["path"] = str(canonical_source)
        snapshot_value.pop("snapshot_sha256", None)
        snapshot_value["snapshot_sha256"] = hashlib.sha256(
            canonical_json_bytes(snapshot_value)
        ).hexdigest()
        _validate_snapshot(snapshot_value)
        raw = json_bytes(snapshot_value)
        if len(raw) > _MAX_SNAPSHOT_BYTES:
            raise AnalysisCacheError("analysis snapshot exceeds the cache size limit")
        analysis_id = snapshot_value["analysis_id"]
        path = self._snapshot_path(analysis_id, canonical_source)
        _write_atomic(path, raw, root=self.root)
        ids = self._read_index(canonical_source)
        ids = [analysis_id, *(item for item in ids if item != analysis_id)][
            :_MAX_SNAPSHOTS_PER_SOURCE
        ]
        index = {
            "schema": INDEX_SCHEMA,
            "source_path": str(canonical_source),
            "analysis_ids": ids,
        }
        _write_atomic(self._index_path(canonical_source), json_bytes(index), root=self.root)

    def load_snapshot(self, analysis_id: str, source_path: str | Path) -> dict[str, Any]:
        canonical_source = _source_path(source_path)
        path = self._snapshot_path(analysis_id, canonical_source)
        value = _read_json(path, root=self.root, max_bytes=_MAX_SNAPSHOT_BYTES)
        return _validate_snapshot(value, analysis_id=analysis_id)

    def snapshots_for_source(self, source_path: str | Path) -> tuple[dict[str, Any], ...]:
        canonical_source = _source_path(source_path)
        results = []
        for analysis_id in self._read_index(canonical_source):
            snapshot = self.load_snapshot(analysis_id, canonical_source)
            if snapshot["source"]["path"] != str(canonical_source):
                raise AnalysisCacheError("analysis index points to a different source path")
            results.append(snapshot)
        return tuple(results)

    def find_change(
        self, source_path: str | Path, change_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        snapshots = self.snapshots_for_source(source_path)
        if not snapshots:
            raise ContextLookupError(
                f"No cached analysis is available for {source_path}. "
                f"Run `ssmdconvert report {source_path}` first."
            )
        for snapshot in snapshots:
            changes = snapshot["app"]["mapped_changes"]
            for change in changes:
                if isinstance(change, dict) and change.get("id") == change_id:
                    return snapshot, change
        raise ContextLookupError(
            f"No cached analysis contains change ID {change_id!r}. "
            f"Run `ssmdconvert report {source_path}` first."
        )


def _ssmd_version() -> str:
    try:
        return importlib.metadata.version("ssmd")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _section_overrides(
    overrides: tuple[SpeechOverride, ...],
    unit_ids: set[str],
) -> tuple[SpeechOverride, ...]:
    return tuple(
        item for item in overrides if item.scope.kind == "all" or item.scope.unit_id in unit_ids
    )


def _chapter_cache_payload(
    section_id: str,
    chapter_sha256: str,
    units: tuple[Any, ...],
    overrides: tuple[SpeechOverride, ...],
    *,
    profile_fingerprint: str,
    runtime_fingerprint: str,
    include_titles: bool,
    max_paragraph_chars: int | None,
    requested_language: str | None,
    fallback_language: str | None,
    sequence_fallback_mode: str,
) -> dict[str, Any]:
    unit_ids = {unit.id for unit in units}
    protected = [
        {
            "unit_id": unit.id,
            "spans": [
                {"start": span.start, "end": span.end, "reason": span.reason}
                for span in unit.protected_spans
            ],
        }
        for unit in units
    ]
    return {
        "schema": CHAPTER_SCHEMA,
        "section_id": section_id,
        "chapter_sha256": chapter_sha256,
        "effective_language_run_map": [
            {
                "unit_id": unit.id,
                "language": unit.language,
                "role": unit.role,
                "text_sha256": sha256_bytes(unit.text.encode("utf-8")),
            }
            for unit in units
        ],
        "protected_span_digest": sha256_bytes(canonical_json_bytes(protected)),
        "override_fingerprint": ttsready.override_fingerprint(overrides),
        "profile_fingerprint": profile_fingerprint,
        "runtime_fingerprint": runtime_fingerprint,
        "ssmd_version": _ssmd_version(),
        "analysis_schema": ANALYSIS_SCHEMA,
        "projection_options": {
            "include_titles": include_titles,
            "max_paragraph_chars": max_paragraph_chars,
        },
        "requested_language": requested_language,
        "fallback_language": fallback_language,
        "sequence_fallback_mode": sequence_fallback_mode,
        "unit_ids": sorted(unit_ids),
    }


def _combine_preparations(
    results: tuple[PreparationResult, ...],
    *,
    profile_fingerprint: str,
    override_fingerprint: str,
    runtime_fingerprint: str,
) -> PreparationResult:
    units = tuple(unit for result in results for unit in result.units)
    unit_ids = [unit.unit_id for unit in units]
    if len(unit_ids) != len(set(unit_ids)):
        raise AnalysisError("per-section ttsready results contain duplicate unit IDs")
    changes = tuple(change for result in results for change in result.changes)
    issues = tuple(issue for result in results for issue in result.issues)
    stage_edits: Counter[str] = Counter()
    rules: Counter[str] = Counter()
    recognition_domains: Counter[str] = Counter()
    for result in results:
        stage_edits.update(result.stats.stage_edits)
        rules.update(result.stats.rules)
        recognition_domains.update(result.stats.recognition_domains)
    stats = PreparationStats(
        units_processed=sum(result.stats.units_processed for result in results),
        units_changed=sum(result.stats.units_changed for result in results),
        changes=sum(result.stats.changes for result in results),
        stage_edits=stage_edits,
        rules=rules,
        recognition_domains=recognition_domains,
        structured_numeric_edits=sum(result.stats.structured_numeric_edits for result in results),
        source_digit_replacements=sum(result.stats.source_digit_replacements for result in results),
        warning_count=sum(result.stats.warning_count for result in results),
        error_count=sum(result.stats.error_count for result in results),
    )
    return PreparationResult(
        units=units,
        changes=changes,
        issues=issues,
        stats=stats,
        profile_fingerprint=profile_fingerprint,
        override_fingerprint=override_fingerprint,
        runtime_fingerprint=runtime_fingerprint,
        prepared_fingerprint=ttsready.prepared_fingerprint(units),
    )


def _make_snapshot(
    analysis: SsmdAnalysis,
    projection: ProjectedText,
    report: SsmdAnalysisReport,
    *,
    analysis_id: str,
    analysis_options: dict[str, Any],
    chapter_keys: dict[str, str],
) -> dict[str, Any]:
    prepared_by_id = {unit.unit_id: unit for unit in analysis.preparation.units}
    unit_contexts = {
        unit_id: context.id for context in analysis.contexts for unit_id in context.unit_ids
    }
    unit_locators = {}
    for unit_id, locator in analysis.unit_locators.items():
        prepared = prepared_by_id.get(unit_id)
        context_id = unit_contexts.get(unit_id)
        if prepared is None or context_id is None:
            raise AnalysisError(f"analysis unit {unit_id!r} is missing cached app context")
        unit_locators[unit_id] = {
            **to_json_value(locator),
            "language": prepared.language,
            "context_id": context_id,
        }
    return {
        "schema": ANALYSIS_SCHEMA,
        "analysis_id": analysis_id,
        "source": {
            "path": str(analysis.source.path.resolve()),
            "kind": analysis.source.kind,
            "input_format": analysis.source.input_format,
            "source_sha256": analysis.source.source_sha256,
            "content_fingerprint": analysis.source.content_fingerprint,
            "selected_sections": [
                {
                    "id": section.id,
                    "sha256": section.chapter_sha256 or sha256_bytes(section.ssmd.encode("utf-8")),
                }
                for section in analysis.sections
            ],
        },
        "options": analysis_options,
        "preparation": ttsready.result_to_dict(analysis.preparation),
        "app": {
            "contexts": to_json_value(analysis.contexts),
            "unit_locators": unit_locators,
            "unit_contexts": unit_contexts,
            "mapped_changes": report_to_dict(report)["changes"],
            "section_stats": to_json_value(report.sections),
            "projection": to_json_value(projection.stats),
            "projection_items": to_json_value(projection.items),
            "issues": to_json_value(report.issues),
            "report": report_to_dict(report),
            "chapter_cache_keys": chapter_keys,
        },
    }


def analyze_with_cache(
    source: str | Path | LoadedSsmdSource,
    *,
    chapters: str | None = "all",
    language: str | None = None,
    fallback_language: str | None = None,
    sequence_fallback_mode: str | None = None,
    include_titles: bool = True,
    max_paragraph_chars: int | None = 1000,
    profile: ttsready.PreparationProfile | None = None,
    overrides: tuple[SpeechOverride, ...] = (),
    pronunciations: dict[str, str] | None = None,
    cache: AnalysisCache | None = None,
    refresh: bool = False,
) -> CachedAnalysis:
    """Analyze selected SSMD chapters while reusing validated immutable preparations."""
    if max_paragraph_chars is not None and max_paragraph_chars < 1:
        raise ValueError("max_paragraph_chars must be at least 1 or None")
    active_cache = cache or AnalysisCache()
    loaded = source if isinstance(source, LoadedSsmdSource) else load_ssmd_source(source)
    selected = select_sections(loaded, chapters)
    extracted = extract_units(
        loaded,
        selected,
        language=language,
        fallback_language=fallback_language,
        include_titles=include_titles,
    )
    _stored, effective_fallback, _fallback_issues = _stored_sequence_fallback(
        extracted,
        loaded,
        requested=sequence_fallback_mode,
    )
    active_profile = replace(
        profile or ttsready.PreparationProfile(),
        sequence_fallback_mode=effective_fallback,
    )
    all_overrides = (
        *extracted.overrides,
        *overrides,
        *_pronunciation_overrides(pronunciations or {}),
    )
    profile_hash = ttsready.profile_fingerprint(active_profile)
    runtime_hash = ttsready.runtime_fingerprint()
    overall_override_hash = ttsready.override_fingerprint(all_overrides)
    unit_metadata = {unit.id: unit.metadata for unit in extracted.units}
    results: list[PreparationResult] = []
    cache_keys: dict[str, str] = {}
    hits = 0
    misses = 0
    for section in selected:
        section_units = tuple(
            unit
            for unit in extracted.units
            if unit_metadata[unit.id].get("section_id") == section.id
        )
        unit_ids = {unit.id for unit in section_units}
        section_overrides = _section_overrides(tuple(all_overrides), unit_ids)
        chapter_hash = section.chapter_sha256 or sha256_bytes(section.ssmd.encode("utf-8"))
        payload = _chapter_cache_payload(
            section.id,
            chapter_hash,
            section_units,
            section_overrides,
            profile_fingerprint=profile_hash,
            runtime_fingerprint=runtime_hash,
            include_titles=include_titles,
            max_paragraph_chars=max_paragraph_chars,
            requested_language=language,
            fallback_language=fallback_language,
            sequence_fallback_mode=effective_fallback,
        )
        key = chapter_analysis_key(payload)
        cache_keys[section.id] = key
        result = (
            None
            if refresh
            else active_cache.get_chapter(
                key,
                section_id=section.id,
                unit_ids=tuple(unit.id for unit in section_units),
                profile_fingerprint=profile_hash,
                override_fingerprint=payload["override_fingerprint"],
                runtime_fingerprint=runtime_hash,
            )
        )
        if result is None:
            misses += 1
            try:
                result = ttsready.prepare_units(
                    section_units,
                    overrides=section_overrides,
                    profile=active_profile,
                    strict=False,
                )
            except Exception as exc:
                raise AnalysisError(
                    f"ttsready could not prepare section {section.id}: {exc}"
                ) from exc
            active_cache.put_chapter(key, section.id, result)
        else:
            hits += 1
        results.append(result)

    preparation = _combine_preparations(
        tuple(results),
        profile_fingerprint=profile_hash,
        override_fingerprint=overall_override_hash,
        runtime_fingerprint=runtime_hash,
    )
    analysis = analyze_ssmd_source(
        loaded,
        chapters=chapters,
        language=language,
        fallback_language=fallback_language,
        sequence_fallback_mode=sequence_fallback_mode,
        include_titles=include_titles,
        profile=active_profile,
        overrides=overrides,
        pronunciations=pronunciations,
        unit_extraction=extracted,
        prepared_result=preparation,
    )
    projection = project_txt(
        analysis,
        max_paragraph_chars=max_paragraph_chars,
        include_titles=include_titles,
    )
    selected_hashes = [
        {
            "id": section.id,
            "sha256": section.chapter_sha256 or sha256_bytes(section.ssmd.encode("utf-8")),
        }
        for section in selected
    ]
    analysis_options = {
        "requested_language": language,
        "fallback_language": fallback_language,
        "requested_sequence_fallback": sequence_fallback_mode,
        "effective_sequence_fallback": effective_fallback,
        "include_titles": include_titles,
        "max_paragraph_chars": max_paragraph_chars,
    }
    analysis_id = ssmd_analysis_id(
        source_content_fingerprint=loaded.content_fingerprint,
        selected_sections=selected_hashes,
        options=analysis_options,
        profile_fingerprint=preparation.profile_fingerprint,
        override_fingerprint=preparation.override_fingerprint,
        runtime_fingerprint=preparation.runtime_fingerprint,
    )
    report = build_analysis_report(
        analysis,
        projection,
        analysis_id=analysis_id,
        include_titles=include_titles,
        max_paragraph_chars=max_paragraph_chars,
    )
    snapshot = _make_snapshot(
        analysis,
        projection,
        report,
        analysis_id=analysis_id,
        analysis_options=analysis_options,
        chapter_keys=cache_keys,
    )
    active_cache.save_snapshot(loaded.path, snapshot)
    return CachedAnalysis(
        analysis=analysis,
        projection=projection,
        report=report,
        analysis_id=analysis_id,
        chapter_cache_hits=hits,
        chapter_cache_misses=misses,
    )

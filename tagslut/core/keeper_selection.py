"""Keeper selection logic for duplicate groups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from tagslut.storage.models import AudioFile, DuplicateGroup, Decision
from tagslut.zones import (
    Zone,
    ZoneManager,
    coerce_zone,
)


@dataclass(frozen=True)
class KeeperScore:
    zone: Optional[Zone]
    zone_priority: int
    path_priority: int
    integrity_ok: bool
    sample_rate: int
    bit_depth: int
    bitrate: int
    quality_score: float
    metadata_score: int
    size: int
    path_length: int
    weird_chars: int
    sort_key: tuple  # type: ignore  # TODO: mypy-strict


@dataclass(frozen=True)
class KeeperSelectionResult:
    group_id: str
    keeper: Optional[AudioFile]
    decisions: List[Decision]
    explanations: List[str]


def select_keeper_for_group(
    group: DuplicateGroup,
    zone_manager: Optional[ZoneManager] = None,
    *,
    use_metadata_tiebreaker: bool = False,
    metadata_fields: Sequence[str] = ("artist", "album", "title"),
) -> KeeperSelectionResult:
    if not group.files:
        return KeeperSelectionResult(group_id=group.group_id, keeper=None, decisions=[], explanations=[])

    zm = zone_manager
    use_zone_priority = True
    if zm is not None:
        use_zone_priority = zm.has_library_zones()

    quality_scores = _compute_quality_scores(group.files)
    scored: list[tuple[AudioFile, KeeperScore]] = []

    for file in group.files:
        score = _score_file(
            file,
            zm,
            quality_scores,
            use_zone_priority,
            use_metadata_tiebreaker,
            metadata_fields,
        )
        scored.append((file, score))

    scored.sort(key=lambda item: item[1].sort_key)
    keeper_file, keeper_score = scored[0]

    decisions: list[Decision] = []
    explanations: list[str] = []

    for file, score in scored:
        if file.path == keeper_file.path:
            action = "KEEP"
            confidence = "HIGH"
            reason = _keeper_reason(score, use_zone_priority)
        else:
            action = "DROP"
            confidence = "MEDIUM"
            reason = _reject_reason(score, keeper_score, use_zone_priority)

        evidence = {
            "zone": (score.zone.value if score.zone else None),
            "zone_priority": score.zone_priority,
            "path_priority": score.path_priority,
            "quality_score": score.quality_score,
            "integrity_ok": score.integrity_ok,
            "sample_rate": score.sample_rate,
            "bit_depth": score.bit_depth,
            "bitrate": score.bitrate,
            "metadata_score": score.metadata_score,
            "size": score.size,
            "path_hygiene": {
                "length": score.path_length,
                "weird_chars": score.weird_chars,
            },
            "use_zone_priority": use_zone_priority,
        }

        decisions.append(
            Decision(
                file=file,
                action=action,  # type: ignore  # TODO: mypy-strict
                reason=reason,
                confidence=confidence,  # type: ignore  # TODO: mypy-strict
                evidence=evidence,
            )
        )

        explanations.append(
            _format_explanation_line(
                file=file,
                score=score,
                is_keeper=(file.path == keeper_file.path),
                reason=reason if file.path != keeper_file.path else None,
            )
        )

    return KeeperSelectionResult(
        group_id=group.group_id,
        keeper=keeper_file,
        decisions=decisions,
        explanations=explanations,
    )


def _score_file(
    file: AudioFile,
    zone_manager: Optional[ZoneManager],
    quality_scores: dict[str, float],
    use_zone_priority: bool,
    use_metadata_tiebreaker: bool,
    metadata_fields: Sequence[str],
) -> KeeperScore:
    zone = coerce_zone(file.zone)
    zone_priority = 0
    path_priority = 0
    if use_zone_priority and zone_manager is not None:
        zone_priority = zone_manager.zone_priority(zone)
        path_priority = zone_manager.path_priority(file.path)
    elif use_zone_priority:
        zone_priority = 1000
        path_priority = 1000

    integrity_ok = _is_integrity_ok(file)
    sample_rate = int(file.sample_rate or 0)
    bit_depth = int(file.bit_depth or 0)
    bitrate = int(file.bitrate or 0)
    quality_score = quality_scores.get(str(file.path), 0.0)
    metadata_score = _metadata_score(file, metadata_fields) if use_metadata_tiebreaker else 0
    size = int(file.size or 0)

    path_str = str(file.path)
    path_length = len(path_str)
    weird_chars = _count_weird_chars(path_str)

    hygiene_key = (path_length, weird_chars)

    if use_zone_priority:
        sort_key = (
            zone_priority,
            path_priority,
            -quality_score,
            -metadata_score,
            -size,
            hygiene_key,
            path_str,
        )
    else:
        sort_key = (  # type: ignore  # TODO: mypy-strict
            -quality_score,
            -metadata_score,
            -size,
            hygiene_key,
            path_str,
        )

    return KeeperScore(
        zone=zone,
        zone_priority=zone_priority,
        path_priority=path_priority,
        integrity_ok=integrity_ok,
        sample_rate=sample_rate,
        bit_depth=bit_depth,
        bitrate=bitrate,
        quality_score=quality_score,
        metadata_score=metadata_score,
        size=size,
        path_length=path_length,
        weird_chars=weird_chars,
        sort_key=sort_key,
    )


def _compute_quality_scores(files: Iterable[AudioFile]) -> dict[str, float]:
    samples = [int(f.sample_rate or 0) for f in files]
    bits = [int(f.bit_depth or 0) for f in files]
    rates = [int(f.bitrate or 0) for f in files]

    def normalize(value: int, min_val: int, max_val: int) -> float:
        if max_val <= 0:
            return 0.0
        if max_val == min_val:
            return 1.0
        return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))

    min_sr, max_sr = (min(samples), max(samples)) if samples else (0, 0)
    min_bd, max_bd = (min(bits), max(bits)) if bits else (0, 0)
    min_br, max_br = (min(rates), max(rates)) if rates else (0, 0)

    scores: dict[str, float] = {}
    for file in files:
        integrity_score = _integrity_score(file)
        sr_score = normalize(int(file.sample_rate or 0), min_sr, max_sr)
        bd_score = normalize(int(file.bit_depth or 0), min_bd, max_bd)
        br_score = normalize(int(file.bitrate or 0), min_br, max_br)

        # Weighted average (integrity has the strongest weight)
        quality_score = (
            0.4 * integrity_score +
            0.2 * sr_score +
            0.2 * bd_score +
            0.2 * br_score
        )
        scores[str(file.path)] = round(quality_score * 100, 2)

    return scores


def _integrity_score(file: AudioFile) -> float:
    if file.integrity_state == "valid":
        return 1.0
    if file.flac_ok is True:
        return 0.9
    if file.integrity_state == "recoverable":
        return 0.4
    return 0.0


def _is_integrity_ok(file: AudioFile) -> bool:
    return _integrity_score(file) >= 0.9


def _count_weird_chars(path_str: str) -> int:
    allowed = set("/._- ")
    count = 0
    for ch in path_str:
        if ch.isalnum() or ch in allowed:
            continue
        count += 1
    return count


def _metadata_score(file: AudioFile, fields: Sequence[str]) -> int:
    score = 0
    metadata = file.metadata or {}
    for field in fields:
        value = metadata.get(field)
        if value:
            score += 1
    return score


def _keeper_reason(score: KeeperScore, use_zone_priority: bool) -> str:
    if use_zone_priority:
        return "Best candidate based on zone, path priority, quality, and size."
    return "Best candidate based on quality, size, and path hygiene."


def _reject_reason(score: KeeperScore, keeper_score: KeeperScore, use_zone_priority: bool) -> str:
    if use_zone_priority and score.zone_priority != keeper_score.zone_priority:
        return f"Lower zone priority ({score.zone or 'unknown'} vs {keeper_score.zone or 'unknown'})"
    if use_zone_priority and score.path_priority != keeper_score.path_priority:
        return "Lower path priority within zone"
    if score.quality_score != keeper_score.quality_score:
        return f"Lower audio quality ({score.quality_score:.1f} vs {keeper_score.quality_score:.1f})"
    if score.size != keeper_score.size:
        return "Smaller file size"
    if score.path_length != keeper_score.path_length:
        return "Less clean path"
    return "Lower overall score"


def _format_explanation_line(
    *,
    file: AudioFile,
    score: KeeperScore,
    is_keeper: bool,
    reason: str | None,
) -> str:
    label = "KEEPER" if is_keeper else "REJECT"
    zone_label = score.zone.value if score.zone else "unknown"
    size_mib = score.size / (1024 * 1024) if score.size else 0.0
    line = (
        f"{label}: {file.path}  "
        f"Zone: {zone_label} (prio={score.zone_priority})  "
        f"Path priority: {score.path_priority}  "
        f"Quality: {score.quality_score:.1f}  "
        f"Size: {size_mib:.1f} MiB"
    )
    if reason:
        line = f"{line}  Reason: {reason}"
    return line

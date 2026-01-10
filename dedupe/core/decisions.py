import logging
import re
from typing import Iterable, List, Literal, Sequence, Tuple
from dedupe.storage.models import AudioFile, DuplicateGroup, Decision

logger = logging.getLogger("dedupe")

# Configuration for zone priority (lower index = higher priority)
DEFAULT_ZONE_PRIORITY = ["accepted", "staging"]
DecisionAction = Literal["KEEP", "DROP", "REVIEW"]
DecisionConfidence = Literal["HIGH", "MEDIUM", "LOW"]

def _normalize_meta(value: str | Iterable[str] | None) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        value = " ".join(filter(None, (str(item) for item in value)))
    cleaned = re.sub(r"\s+", " ", str(value)).strip().casefold()
    return cleaned

def _meta_score(file: AudioFile, fields: Iterable[str]) -> int:
    score = 0
    for key in fields:
        value = file.metadata.get(key, "") if file.metadata else ""
        if _normalize_meta(value):
            score += 1
    return score

def get_zone_priority(file: AudioFile, priorities: Sequence[str]) -> int:
    """Returns a sortable priority index for a file zone."""
    if file.zone and file.zone in priorities:
        return priorities.index(file.zone)
    path_str = str(file.path)
    if "20_ACCEPTED" in path_str:
        return priorities.index("accepted") if "accepted" in priorities else 999
    if "10_STAGING" in path_str:
        return priorities.index("staging") if "staging" in priorities else 999
    return 999

def assess_duplicate_group(
    group: DuplicateGroup,
    priority_order: List[str] | None = None,
    *,
    use_metadata_tiebreaker: bool = False,
    metadata_fields: Iterable[str] = ("artist", "album", "title"),
) -> List[Decision]:
    """
    Analyzes a group of duplicates and returns a decision for each file.
    """
    if not group.files:
        return []

    priorities = priority_order or DEFAULT_ZONE_PRIORITY
    group_zones = {f.zone for f in group.files if f.zone}
    has_accepted = "accepted" in group_zones
    has_staging = "staging" in group_zones

    def base_key(f: AudioFile) -> tuple[int, ...]:
        # 1. Integrity
        integrity_ok = f.integrity_state == "valid" if f.integrity_state else f.flac_ok
        score_integrity = 1 if integrity_ok else 0
        # 2. Zone priority
        score_priority = -get_zone_priority(f, priorities)
        # 3. Technical Quality
        score_quality = (f.sample_rate, f.bit_depth, f.bitrate)
        # 4. Path preference (Shorter path usually means less nested/cluttered)
        score_path_len = -len(str(f.path))
        return (
            score_integrity,
            score_priority,
            *score_quality,
            score_path_len,
        )

    def sort_key(f: AudioFile) -> tuple[int, ...]:
        key = base_key(f)
        if use_metadata_tiebreaker:
            return key + (_meta_score(f, metadata_fields),)
        return key

    # Sort descending (best first)
    sorted_files = sorted(group.files, key=sort_key, reverse=True)
    best_file = sorted_files[0]

    # Conflict labeling
    checksums = {f.checksum for f in group.files if f.checksum and f.checksum != "NOT_SCANNED"}
    has_unknown = any(not f.checksum or f.checksum == "NOT_SCANNED" for f in group.files)
    if checksums and len(checksums) == 1:
        conflict_label = "BIT_IDENTICAL"
    elif has_unknown:
        conflict_label = "UNKNOWN_NOT_SCANNED"
    else:
        conflict_label = "ACOUSTIC_MATCH_BIT_DIFF"

    used_meta_tiebreaker = False
    if use_metadata_tiebreaker:
        best_base = base_key(best_file)
        tied = [f for f in group.files if base_key(f) == best_base]
        if len(tied) > 1:
            best_score = _meta_score(best_file, metadata_fields)
            if any(_meta_score(f, metadata_fields) < best_score for f in tied):
                used_meta_tiebreaker = True

    decisions: list[Decision] = []

    for f in sorted_files:
        action: DecisionAction = "REVIEW"
        confidence: DecisionConfidence = "MEDIUM"

        # Base reason from zones
        if has_accepted and has_staging:
            reason = "Duplicate spans staging and accepted; review before promotion."
        elif group_zones == {"accepted"}:
            reason = "Duplicate inside accepted zone; policy violation for curator review."
            confidence = "HIGH"
        elif group_zones == {"staging"}:
            reason = "Duplicate inside staging; curator review recommended."
        else:
            reason = "Duplicate detected; curator review recommended."

        # Risk Profile / Delta Summary
        delta: dict[str, float] = {}
        if f.path != best_file.path:
            if f.duration != best_file.duration:
                delta["duration_diff"] = float(f.duration - best_file.duration)
            if f.bitrate != best_file.bitrate:
                delta["bitrate_diff"] = float(f.bitrate - best_file.bitrate)
            if f.sample_rate != best_file.sample_rate:
                delta["sample_rate_diff"] = float(f.sample_rate - best_file.sample_rate)
            if f.bit_depth != best_file.bit_depth:
                delta["bit_depth_diff"] = float(f.bit_depth - best_file.bit_depth)

        decisions.append(Decision(
            file=f,
            action=action,
            reason=reason,
            confidence=confidence,
            evidence={
                "group_source": group.source,
                "rank_index": sorted_files.index(f),
                "preferred": f.path == best_file.path,
                "zone": f.zone,
                "integrity_state": f.integrity_state,
                "risk_delta": delta,
                "conflict_label": conflict_label,
                "used_meta_tiebreaker": used_meta_tiebreaker if f.path == best_file.path else False,
            }
        ))

    return decisions

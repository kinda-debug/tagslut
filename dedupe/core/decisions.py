import logging
from typing import List
from dedupe.storage.models import AudioFile, DuplicateGroup, Decision

logger = logging.getLogger("dedupe")

# Configuration for zone priority (lower index = higher priority)
DEFAULT_ZONE_PRIORITY = ["accepted", "staging"]

def get_zone_priority(file: AudioFile, priorities: List[str]) -> int:
    """Returns a sortable priority index for a file zone."""
    if file.zone and file.zone in priorities:
        return priorities.index(file.zone)
    path_str = str(file.path)
    if "20_ACCEPTED" in path_str:
        return priorities.index("accepted") if "accepted" in priorities else 999
    if "10_STAGING" in path_str:
        return priorities.index("staging") if "staging" in priorities else 999
    return 999

def assess_duplicate_group(group: DuplicateGroup, priority_order: List[str] | None = None) -> List[Decision]:
    """
    Analyzes a group of duplicates and returns a decision for each file.
    """
    if not group.files:
        return []

    priorities = priority_order or DEFAULT_ZONE_PRIORITY
    group_zones = {f.zone for f in group.files if f.zone}
    has_accepted = "accepted" in group_zones
    has_staging = "staging" in group_zones

    def sort_key(f: AudioFile):
        # 1. Integrity
        integrity_ok = f.integrity_state == "valid" if f.integrity_state else f.flac_ok
        score_integrity = 1 if integrity_ok else 0
        # 2. Zone priority
        score_priority = -get_zone_priority(f, priorities)
        # 3. Technical Quality
        score_tech = (f.sample_rate, f.bit_depth, f.bitrate)
        # 4. Path preference (Shorter path usually means less nested/cluttered)
        score_path_len = -len(str(f.path))
        # 5. Metadata tie-breaker (Tertiary)
        # Normalize artist/album for comparison if available
        score_meta = 0
        artist = f.metadata.get("artist", "")
        album = f.metadata.get("album", "")
        if artist or album:
            # We don't have a reference here, so we just use the existence of metadata as a tiny boost
            # in a real tie-breaker we'd compare against a target, but here we can just say
            # "having metadata is better than not having it"
            score_meta = 1

        return (score_integrity, score_priority, score_tech, score_path_len, score_meta)

    # Sort descending (best first)
    sorted_files = sorted(group.files, key=sort_key, reverse=True)
    best_file = sorted_files[0]

    # Conflict labeling: Bit-diff matches
    is_bit_diff = False
    if group.source == "checksum":
        # If it's a checksum match, they are bit-identical by definition
        is_bit_diff = False
    else:
        # If matched via acoustid or other means, check if checksums differ
        checksums = {f.checksum for f in group.files if f.checksum and f.checksum != "NOT_SCANNED"}
        if len(checksums) > 1:
            is_bit_diff = True

    decisions = []

    for f in sorted_files:
        action = "REVIEW"
        confidence = "MEDIUM"

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
        delta = {}
        if f.path != best_file.path:
            if f.duration != best_file.duration:
                delta["duration_diff"] = f.duration - best_file.duration
            if f.bitrate != best_file.bitrate:
                delta["bitrate_diff"] = f.bitrate - best_file.bitrate
            if f.sample_rate != best_file.sample_rate:
                delta["sample_rate_diff"] = f.sample_rate - best_file.sample_rate
            if f.bit_depth != best_file.bit_depth:
                delta["bit_depth_diff"] = f.bit_depth - best_file.bit_depth

        conflict_label = None
        used_meta_tiebreaker = False
        if is_bit_diff:
            conflict_label = "[ACOUSTIC_MATCH | BIT_DIFF]"

        # Check if metadata tie-breaker was actually needed
        # (This is a bit simplified, but checks if it's the preferred file and has metadata)
        if f.path == best_file.path and (f.metadata.get("artist") or f.metadata.get("album")):
             # Find if there was a technical tie with any other file
             for other in sorted_files:
                 if other.path == f.path: continue
                 # Compare only tech scores
                 if (other.integrity_state == f.integrity_state and
                     other.sample_rate == f.sample_rate and
                     other.bit_depth == f.bit_depth and
                     other.bitrate == f.bitrate and
                     len(str(other.path)) == len(str(f.path))):
                     used_meta_tiebreaker = True
                     break

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
                "used_meta_tiebreaker": used_meta_tiebreaker,
            }
        ))

    return decisions

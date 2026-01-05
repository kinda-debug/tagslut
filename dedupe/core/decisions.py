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
        
        return (score_integrity, score_priority, score_tech, score_path_len)

    # Sort descending (best first)
    sorted_files = sorted(group.files, key=sort_key, reverse=True)
    best_file = sorted_files[0]
    
    decisions = []
    
    for f in sorted_files:
        action = "REVIEW"
        confidence = "MEDIUM"
        if has_accepted and has_staging:
            reason = "Duplicate spans staging and accepted; review before promotion."
        elif group_zones == {"accepted"}:
            reason = "Duplicate inside accepted zone; policy violation for curator review."
            confidence = "HIGH"
        elif group_zones == {"staging"}:
            reason = "Duplicate inside staging; curator review recommended."
        else:
            reason = "Duplicate detected; curator review recommended."

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
            }
        ))
        
    return decisions

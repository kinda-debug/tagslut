import logging
from typing import List, Tuple, Optional
from dedupe.storage.models import AudioFile, DuplicateGroup, Decision

logger = logging.getLogger("dedupe")

# Configuration for library priority (lower index = higher priority)
DEFAULT_PRIORITY = ["dotad", "sad", "bad"]

def get_library_priority(path: str, priorities: List[str]) -> int:
    """Returns a sortable priority index for a file path."""
    path_str = str(path)
    for i, keyword in enumerate(priorities):
        if keyword in path_str:
            return i
    return 999  # No match (lowest priority)

def get_file_priority(file: AudioFile, priorities: List[str]) -> int:
    """Returns a sortable priority index for an AudioFile."""
    if getattr(file, "library", None):
        try:
            return priorities.index(str(file.library))
        except ValueError:
            return 999
    return get_library_priority(str(file.path), priorities)

def assess_duplicate_group(group: DuplicateGroup, priority_order: List[str] = None) -> List[Decision]:
    """
    Analyzes a group of duplicates and returns a decision for each file.
    """
    if not group.files:
        return []

    priorities = priority_order or DEFAULT_PRIORITY
    
    def sort_key(f: AudioFile):
        # 1. Integrity 
        score_integrity = 1 if f.flac_ok else 0
        # 2. Priority 
        score_priority = -get_file_priority(f, priorities)
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
        if f.path == best_file.path:
            # The Winner
            action = "KEEP"
            reason = "Best match based on integrity, library priority, and quality."
            confidence = "HIGH"
            
            # Downgrade confidence if integrity is bad even for the winner
            if not f.flac_ok:
                action = "REVIEW"
                reason = "Best file available, but failed integrity check."
                confidence = "LOW"
                
        else:
            # The Losers
            action = "DROP"
            confidence = "HIGH"
            reason = f"Duplicate of {best_file.path.name}"

        decisions.append(Decision(
            file=f,
            action=action,
            reason=reason,
            confidence=confidence,
            evidence={
                "group_source": group.source, 
                "rank_index": sorted_files.index(f)
            }
        ))
        
    return decisions

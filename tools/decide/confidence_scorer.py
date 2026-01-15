"""Confidence scoring for deduplication decisions."""

from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum


class Zone(Enum):
    """File zone classification."""
    QUARANTINE = 0.0
    REVIEW = 0.5
    LIBRARY = 1.0


@dataclass
class ConfidenceScore:
    """Confidence score for a decision."""
    file_id: str
    decision: str  # KEEP or DROP
    confidence: float  # 0.0-1.0
    zone: Optional[Zone] = None
    flac_ok: bool = True
    requires_review: bool = False


class ConfidenceScorer:
    """Score decisions based on evidence."""
    
    CONFIDENCE_THRESHOLD_MANUAL_REVIEW = 0.7
    
    @staticmethod
    def score_decision(
        file_id: str,
        decision: str,
        zone: Optional[str] = None,
        flac_ok: bool = True,
        integrity_ok: bool = True,
    ) -> ConfidenceScore:
        """Score a KEEP/DROP decision."""
        # Base confidence from FLAC integrity
        confidence = 0.9 if flac_ok else 0.4
        
        # Adjust by zone
        if zone == "QUARANTINE":
            confidence *= 0.6
        elif zone == "REVIEW":
            confidence *= 0.8
        elif zone == "LIBRARY":
            confidence *= 1.0
        
        # Clamp to 0-1
        confidence = max(0.0, min(1.0, confidence))
        
        requires_review = confidence < ConfidenceScorer.CONFIDENCE_THRESHOLD_MANUAL_REVIEW
        
        return ConfidenceScore(
            file_id=file_id,
            decision=decision,
            confidence=confidence,
            zone=zone,
            flac_ok=flac_ok,
            requires_review=requires_review,
        )
    
    @staticmethod
    def get_low_confidence_decisions(scores: List[ConfidenceScore]) -> List[ConfidenceScore]:
        """Filter low-confidence decisions."""
        return [s for s in scores if s.requires_review]

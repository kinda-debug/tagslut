"""Confidence scoring for deduplication results.

Implements Item 6: Confidence < 0.7 flagged for review - provides scoring
mechanisms to assess deduplication confidence and flag low-confidence results.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ConfidenceLevel(Enum):
    """Deduplication confidence levels."""
    VERY_LOW = (0.0, 0.3)
    LOW = (0.3, 0.6)
    MEDIUM = (0.6, 0.8)
    HIGH = (0.8, 0.95)
    VERY_HIGH = (0.95, 1.0)


@dataclass
class ConfidenceScore:
    """Represents a confidence score for a deduplication match."""
    record_id_1: str
    record_id_2: str
    score: float  # 0.0 to 1.0
    factors: Dict[str, float] = field(default_factory=dict)
    flagged_for_review: bool = field(init=False)
    confidence_level: ConfidenceLevel = field(init=False)
    reason: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Calculate confidence level and flag status after initialization."""
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got {self.score}")
        
        # Determine confidence level
        for level in ConfidenceLevel:
            min_val, max_val = level.value
            if min_val <= self.score < max_val:
                self.confidence_level = level
                break
        else:
            # For score = 1.0, assign VERY_HIGH
            self.confidence_level = ConfidenceLevel.VERY_HIGH
        
        # Flag if score < 0.7
        self.flagged_for_review = self.score < 0.7
        
        if self.flagged_for_review and not self.reason:
            self.reason = f"Low confidence score: {self.score:.2%}"
    
    def __str__(self) -> str:
        """Human-readable string representation."""
        flag = "[REVIEW]" if self.flagged_for_review else "[OK]"
        return (
            f"{flag} {self.record_id_1} <-> {self.record_id_2}: "
            f"{self.score:.2%} ({self.confidence_level.name})"
        )


class ConfidenceScorer:
    """Score and manage deduplication confidence."""
    
    def __init__(self, threshold: float = 0.7):
        """Initialize scorer with confidence threshold.
        
        Args:
            threshold: Confidence threshold below which records are flagged for review
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"Threshold must be between 0.0 and 1.0, got {threshold}")
        
        self.threshold = threshold
        self.scores: List[ConfidenceScore] = []
        self.flagged_scores: List[ConfidenceScore] = []
    
    def add_score(self, record_id_1: str, record_id_2: str, score: float, 
                  factors: Optional[Dict[str, float]] = None,
                  reason: Optional[str] = None) -> ConfidenceScore:
        """Add a confidence score.
        
        Args:
            record_id_1: First record ID
            record_id_2: Second record ID  
            score: Confidence score (0.0-1.0)
            factors: Dictionary of contributing factors and their weights
            reason: Optional reason for low confidence
        
        Returns:
            ConfidenceScore object
        """
        confidence = ConfidenceScore(
            record_id_1=record_id_1,
            record_id_2=record_id_2,
            score=score,
            factors=factors or {},
            reason=reason
        )
        
        self.scores.append(confidence)
        
        if confidence.flagged_for_review:
            self.flagged_scores.append(confidence)
            logger.warning(f"Low confidence match flagged for review: {confidence}")
        
        return confidence
    
    def get_flagged_matches(self) -> List[ConfidenceScore]:
        """Get all matches flagged for review (score < threshold)."""
        return [s for s in self.scores if s.score < self.threshold]
    
    def get_high_confidence(self) -> List[ConfidenceScore]:
        """Get all high-confidence matches (score >= threshold)."""
        return [s for s in self.scores if s.score >= self.threshold]
    
    def get_statistics(self) -> Dict[str, any]:
        """Get statistics about confidence scores."""
        if not self.scores:
            return {
                "total_scores": 0,
                "average_confidence": 0.0,
                "flagged_count": 0,
                "flagged_percent": 0.0,
                "min_score": 0.0,
                "max_score": 0.0
            }
        
        flagged = self.get_flagged_matches()
        scores_only = [s.score for s in self.scores]
        
        return {
            "total_scores": len(self.scores),
            "average_confidence": sum(scores_only) / len(scores_only),
            "flagged_count": len(flagged),
            "flagged_percent": len(flagged) / len(self.scores) * 100,
            "min_score": min(scores_only),
            "max_score": max(scores_only),
            "by_level": self._count_by_level()
        }
    
    def _count_by_level(self) -> Dict[str, int]:
        """Count scores by confidence level."""
        counts = {level.name: 0 for level in ConfidenceLevel}
        
        for score in self.scores:
            counts[score.confidence_level.name] += 1
        
        return counts
    
    def export_flagged_csv(self) -> str:
        """Export flagged matches as CSV."""
        lines = ["record_id_1,record_id_2,score,reason"]
        
        for score in self.get_flagged_matches():
            reason = score.reason or ""
            lines.append(f"{score.record_id_1},{score.record_id_2},{score.score:.4f},\"{reason}\"")
        
        return "\n".join(lines)
    
    def validate_all_reviewed(self) -> bool:
        """Validate that all low-confidence matches have been reviewed.
        
        Returns:
            False if any flagged matches remain unreviewed
        """
        return len(self.get_flagged_matches()) == 0
    
    def get_review_summary(self) -> str:
        """Generate human-readable review summary."""
        stats = self.get_statistics()
        flagged = self.get_flagged_matches()
        
        summary = [
            f"Confidence Score Summary:",
            f"  Total Matches: {stats['total_scores']}",
            f"  Average Confidence: {stats['average_confidence']:.2%}",
            f"  Flagged for Review: {stats['flagged_count']} ({stats['flagged_percent']:.1f}%)",
            f"  Score Range: {stats['min_score']:.2%} - {stats['max_score']:.2%}",
            f"",
            f"Flagged Matches (Need Review):"
        ]
        
        if flagged:
            for score in sorted(flagged, key=lambda s: s.score):
                summary.append(f"  - {score}")
        else:
            summary.append("  None - all matches approved!")
        
        return "\n".join(summary)

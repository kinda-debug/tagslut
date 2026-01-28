"""Stratified sampling for validation."""

import random
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class Sample:
    """Sample item for manual review."""
    file_id: str
    decision: str
    confidence: float
    bin: str  # confidence bin


class ValidationSampler:
    """Stratified sampling across confidence bins."""
    
    CONFIDENCE_BINS = [
        (0.0, 0.3, 'low'),
        (0.3, 0.6, 'medium'),
        (0.6, 0.8, 'high'),
        (0.8, 1.0, 'very_high'),
    ]
    
    @staticmethod
    def get_bin(confidence: float) -> str:
        """Get confidence bin for score."""
        for low, high, bin_name in ValidationSampler.CONFIDENCE_BINS:
            if low <= confidence < high:
                return bin_name
        return 'very_high'
    
    @staticmethod
    def stratified_sample(scores: List[Dict], sample_rate: float = 0.1) -> List[Sample]:
        """Sample from decisions stratified by confidence."""
        # Group by bin
        bins: Dict[str, List] = {}
        for score in scores:
            confidence = score.get('confidence', 0.5)
            bin_name = ValidationSampler.get_bin(confidence)
            if bin_name not in bins:
                bins[bin_name] = []
            bins[bin_name].append(score)
        
        # Sample from each bin
        samples = []
        for bin_name, items in bins.items():
            sample_count = max(1, int(len(items) * sample_rate))
            bin_samples = random.sample(items, min(sample_count, len(items)))
            for item in bin_samples:
                samples.append(Sample(
                    file_id=item.get('file_id'),
                    decision=item.get('decision'),
                    confidence=item.get('confidence', 0.5),
                    bin=bin_name,
                ))
        
        return samples

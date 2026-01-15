"""Filter and exclude AppleDouble resource forks from recommendations.

Implements Item 8: No AppleDouble files in recommendations
"""
import re
from typing import List, Dict, Tuple
from dataclasses import dataclass

APPLEDOUBLE_PATTERNS = [
    r'^\._.*',  # macOS resource fork prefix
    r'.*/\._.*',  # nested resource fork
    r'\.DS_Store$',  # macOS directory index
]

@dataclass
class AppleDoubleEntry:
    path: str
    is_appledouble: bool
    reason: str = ""

class AppleDoubleFilter:
    """Filter AppleDouble files from deduplication results."""
    
    def __init__(self):
        self.compiled_patterns = [re.compile(p) for p in APPLEDOUBLE_PATTERNS]
        self.filtered_count = 0
        self.appledouble_files: List[str] = []
    
    def is_appledouble(self, file_path: str) -> Tuple[bool, str]:
        """Check if file is AppleDouble resource fork."""
        for pattern in self.compiled_patterns:
            if pattern.search(file_path):
                return True, f"Matches pattern: {pattern.pattern}"
        return False, ""
    
    def filter_recommendations(self, recommendations: List[Dict]) -> List[Dict]:
        """Filter out AppleDouble files from recommendations."""
        filtered = []
        
        for rec in recommendations:
            file1 = rec.get('file1', '')
            file2 = rec.get('file2', '')
            
            is_ad1, reason1 = self.is_appledouble(file1)
            is_ad2, reason2 = self.is_appledouble(file2)
            
            if is_ad1 or is_ad2:
                self.filtered_count += 1
                if is_ad1:
                    self.appledouble_files.append(file1)
                if is_ad2:
                    self.appledouble_files.append(file2)
            else:
                filtered.append(rec)
        
        return filtered
    
    def get_stats(self) -> Dict:
        return {
            "filtered_count": self.filtered_count,
            "appledouble_files_found": len(set(self.appledouble_files))
        }

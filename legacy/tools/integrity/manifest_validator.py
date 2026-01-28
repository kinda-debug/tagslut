"""Manifest validation for artifact integrity.

Implements Item 7: Manifest verified for all artifacts - ensures all
artifacts have valid manifests with checksums and metadata.
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from pathlib import Path
from enum import Enum
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ManifestStatus(Enum):
    """Status of manifest validation."""
    VALID = "valid"
    MISSING = "missing"
    CORRUPTED = "corrupted"
    INCOMPLETE = "incomplete"
    UNVERIFIED = "unverified"


@dataclass
class ChecksumEntry:
    """Represents a file checksum entry in manifest."""
    filename: str
    hash_algorithm: str  # e.g., 'sha256', 'md5'
    hash_value: str
    file_size: int
    last_modified: str
    
    def __str__(self) -> str:
        return f"{self.filename}: {self.hash_algorithm}={self.hash_value} ({self.file_size} bytes)"


@dataclass
class ManifestEntry:
    """Represents a manifest entry for an artifact."""
    artifact_id: str
    artifact_path: str
    created_timestamp: str
    checksums: List[ChecksumEntry]
    metadata: Dict[str, Any]
    status: ManifestStatus = ManifestStatus.UNVERIFIED
    verification_errors: List[str] = None
    
    def __post_init__(self) -> None:
        if self.verification_errors is None:
            self.verification_errors = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "artifact_id": self.artifact_id,
            "artifact_path": self.artifact_path,
            "created_timestamp": self.created_timestamp,
            "checksums": [asdict(c) for c in self.checksums],
            "metadata": self.metadata,
            "status": self.status.value,
            "verification_errors": self.verification_errors
        }


class ManifestValidator:
    """Validate and manage artifact manifests."""
    
    def __init__(self, hash_algorithm: str = "sha256"):
        """Initialize validator with hash algorithm.
        
        Args:
            hash_algorithm: Hash algorithm to use (sha256, md5, etc.)
        """
        self.hash_algorithm = hash_algorithm
        self.manifests: Dict[str, ManifestEntry] = {}
        self.validation_results: List[ManifestEntry] = []
    
    def compute_file_hash(self, file_path: str) -> str:
        """Compute hash of a file.
        
        Args:
            file_path: Path to file
        
        Returns:
            Hex digest of file hash
        """
        hash_obj = hashlib.new(self.hash_algorithm)
        
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        except Exception as e:
            logger.error(f"Failed to compute hash for {file_path}: {e}")
            raise
    
    def create_manifest(self, artifact_id: str, artifact_path: str, 
                       files_to_include: List[str],
                       metadata: Optional[Dict[str, Any]] = None) -> ManifestEntry:
        """Create a manifest for an artifact.
        
        Args:
            artifact_id: Unique identifier for artifact
            artifact_path: Path to artifact directory
            files_to_include: List of files to include in manifest
            metadata: Optional metadata dictionary
        
        Returns:
            ManifestEntry
        """
        checksums: List[ChecksumEntry] = []
        
        for file_path in files_to_include:
            try:
                full_path = Path(artifact_path) / file_path
                file_size = full_path.stat().st_size
                mod_time = datetime.fromtimestamp(full_path.stat().st_mtime).isoformat()
                hash_value = self.compute_file_hash(str(full_path))
                
                checksum = ChecksumEntry(
                    filename=file_path,
                    hash_algorithm=self.hash_algorithm,
                    hash_value=hash_value,
                    file_size=file_size,
                    last_modified=mod_time
                )
                checksums.append(checksum)
            except Exception as e:
                logger.warning(f"Failed to create checksum for {file_path}: {e}")
        
        manifest = ManifestEntry(
            artifact_id=artifact_id,
            artifact_path=artifact_path,
            created_timestamp=datetime.now().isoformat(),
            checksums=checksums,
            metadata=metadata or {},
            status=ManifestStatus.VALID if checksums else ManifestStatus.INCOMPLETE
        )
        
        self.manifests[artifact_id] = manifest
        return manifest
    
    def verify_manifest(self, artifact_id: str, artifact_path: str) -> ManifestEntry:
        """Verify an artifact's manifest integrity.
        
        Args:
            artifact_id: Artifact identifier
            artifact_path: Path to artifact directory
        
        Returns:
            Verified ManifestEntry
        """
        if artifact_id not in self.manifests:
            logger.error(f"No manifest found for artifact {artifact_id}")
            return ManifestEntry(
                artifact_id=artifact_id,
                artifact_path=artifact_path,
                created_timestamp=datetime.now().isoformat(),
                checksums=[],
                metadata={},
                status=ManifestStatus.MISSING,
                verification_errors=["Manifest not found"]
            )
        
        manifest = self.manifests[artifact_id]
        errors: List[str] = []
        
        # Verify each file in manifest
        for checksum_entry in manifest.checksums:
            try:
                full_path = Path(artifact_path) / checksum_entry.filename
                
                if not full_path.exists():
                    errors.append(f"File not found: {checksum_entry.filename}")
                    continue
                
                # Recompute hash and compare
                current_hash = self.compute_file_hash(str(full_path))
                if current_hash != checksum_entry.hash_value:
                    errors.append(f"Checksum mismatch for {checksum_entry.filename}")
            
            except Exception as e:
                errors.append(f"Error verifying {checksum_entry.filename}: {str(e)}")
        
        # Update manifest status
        if errors:
            manifest.status = ManifestStatus.CORRUPTED if len(errors) == len(manifest.checksums) else ManifestStatus.INCOMPLETE
        else:
            manifest.status = ManifestStatus.VALID
        
        manifest.verification_errors = errors
        self.validation_results.append(manifest)
        
        return manifest
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """Get summary of all validations."""
        total = len(self.validation_results)
        valid = sum(1 for m in self.validation_results if m.status == ManifestStatus.VALID)
        
        return {
            "total_validated": total,
            "valid_count": valid,
            "invalid_count": total - valid,
            "success_rate": (valid / total * 100) if total > 0 else 0,
            "status_distribution": self._count_by_status()
        }
    
    def _count_by_status(self) -> Dict[str, int]:
        """Count manifests by status."""
        counts = {status.value: 0 for status in ManifestStatus}
        
        for manifest in self.validation_results:
            counts[manifest.status.value] += 1
        
        return counts
    
    def export_manifests(self, output_path: str) -> None:
        """Export all manifests to JSON file.
        
        Args:
            output_path: Path to output JSON file
        """
        manifests_data = [
            m.to_dict() for m in self.manifests.values()
        ]
        
        with open(output_path, 'w') as f:
            json.dump(manifests_data, f, indent=2)
        
        logger.info(f"Exported {len(manifests_data)} manifests to {output_path}")
    
    def validate_all_artifacts(self) -> bool:
        """Validate that all artifacts have valid manifests.
        
        Returns:
            True if all artifacts are valid, False otherwise
        """
        if not self.validation_results:
            return False
        
        return all(m.status == ManifestStatus.VALID for m in self.validation_results)

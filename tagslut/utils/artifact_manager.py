"""Artifact lifecycle management and versioning."""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class ArtifactManager:
    """Manage artifact versioning and manifest."""

    def __init__(self, artifacts_dir: str):
        self.artifacts_dir = Path(artifacts_dir)
        self.manifest_file = self.artifacts_dir / "MANIFEST.json"

    def create_snapshot(self, operation: str, files: List[str]) -> str:
        """Create timestamped snapshot."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"{operation}_SNAPSHOT_{timestamp}"
        snapshot_dir = self.artifacts_dir / snapshot_name
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        return snapshot_name

    def compute_checksum(self, file_path: str) -> str:
        """Compute SHA-256 checksum."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def create_manifest(self, artifact_files: List[str]) -> Dict:  # type: ignore  # TODO: mypy-strict
        """Create manifest for artifacts."""
        manifest = {
            "timestamp": datetime.utcnow().isoformat(),
            "artifact_count": len(artifact_files),
            "artifacts": []
        }

        for file_path in artifact_files:
            try:
                checksum = self.compute_checksum(file_path)
                manifest["artifacts"].append({  # type: ignore  # TODO: mypy-strict
                    "path": file_path,
                    "checksum": checksum,
                    "size": os.path.getsize(file_path),
                })
            except (IOError, OSError) as e:
                print(f"Failed to checksum {file_path}: {e}")

        return manifest

    def save_manifest(self, manifest: Dict) -> None:  # type: ignore  # TODO: mypy-strict
        """Save manifest as JSON."""
        with open(self.manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)

    def verify_manifest(self) -> bool:
        """Verify all artifacts match checksums."""
        if not self.manifest_file.exists():
            return False

        with open(self.manifest_file, 'r') as f:
            manifest = json.load(f)

        for artifact in manifest.get("artifacts", []):
            if not os.path.exists(artifact["path"]):
                return False
            current_checksum = self.compute_checksum(artifact["path"])
            if current_checksum != artifact["checksum"]:
                return False

        return True

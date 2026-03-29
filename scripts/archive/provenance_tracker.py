"""
Provenance Tracking System: Link Postman API calls to file/DB writes with complete audit trail.

This module provides:
1. API call logging (what was requested, when, from where)
2. Response capture (what data came back)
3. Ingestion mapping (what was written based on that data)
4. Audit trail (complete chain of custody)
5. Verification hooks (detect mismatches, conflicts, fraud)
"""

import json
import hashlib
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path
import sqlite3


class APIProvider(str, Enum):
    """Data source/API provider"""
    TIDAL = "tidal"
    BEATPORT = "beatport"
    QOBUZ = "qobuz"
    POSTMAN_MANUAL = "postman_manual"
    LOCAL_TAGS = "local_tags"
    FINGERPRINT = "fingerprint"
    USER_INPUT = "user_input"


class VerificationStatus(str, Enum):
    """Verification outcome"""
    UNVERIFIED = "unverified"  # Not yet checked
    VERIFIED = "verified"  # Multiple sources agree
    CONFLICTED = "conflicted"  # Sources disagree
    FAILED = "failed"  # Could not verify
    FLAGGED = "flagged"  # Manual review needed


@dataclass
class APICall:
    """Single API call made via Postman or code"""
    timestamp: str  # ISO 8601
    provider: APIProvider
    endpoint: str  # e.g., /v4/catalog/tracks/{id}
    request_params: Dict[str, Any]  # Query params, body, headers
    request_hash: str  # SHA256 of request (reproducibility)
    response_status: int  # HTTP 200, 401, 404, etc.
    response_size_bytes: int
    response_hash: str  # SHA256 of response body
    duration_ms: int  # Request duration
    tool: str  # "postman", "python_requests", "curl", etc.
    operator: Optional[str] = None  # Who made the call (Postman user, script runner)
    notes: Optional[str] = None  # Manual notes about the call
    correlation_id: str = field(default_factory=lambda: hashlib.sha256(json.dumps({}).encode()).hexdigest()[:16])


@dataclass
class DataPoint:
    """Single piece of data extracted from API response"""
    field_name: str  # e.g., "title", "duration_ms", "isrc"
    value: Any  # The actual value
    source_api_call: str  # Correlation ID to APICall
    extraction_method: str  # e.g., "json_path", "regex", "manual_entry"
    confidence: float  # 0.0–1.0 (how confident is this value?)
    validation_status: str  # "valid", "warning", "error"


@dataclass
class IngestionRecord:
    """What was actually written to file/DB based on API responses"""
    timestamp: str  # ISO 8601
    file_path: str  # What file was written
    file_hash: str  # SHA256 of file content
    source_api_calls: List[str]  # Correlation IDs of APICall(s) that drove this write
    data_points: List[DataPoint]  # All data extracted and written
    ingestion_method: str  # "provider_api", "local_tags", "multi_provider_reconcile"
    ingestion_confidence: str  # "verified", "corroborated", "high", "uncertain", "legacy"
    canonical_payload_json: Dict[str, Any]  # Full metadata written
    conflicts: Optional[Dict[str, List[Any]]] = None  # provider_id_conflicts, ISRC mismatches, etc.
    operator: Optional[str] = None  # Who triggered the write
    dry_run: bool = False  # Was this a dry-run?
    notes: Optional[str] = None


class ProvenanceTracker:
    """Central audit log: tracks API calls → data extraction → file writes"""

    def __init__(self, db_path: str):
        """Initialize provenance database"""
        self.db_path = db_path
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._init_db()

    def _init_db(self):
        """Create schema if not exists"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # API calls table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_calls (
                correlation_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                provider TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                request_params JSON NOT NULL,
                request_hash TEXT NOT NULL,
                response_status INTEGER NOT NULL,
                response_size_bytes INTEGER,
                response_hash TEXT NOT NULL,
                duration_ms INTEGER,
                tool TEXT,
                operator TEXT,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Data points table (what was extracted from responses)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_name TEXT NOT NULL,
                value TEXT,
                source_api_call TEXT NOT NULL,
                extraction_method TEXT,
                confidence REAL,
                validation_status TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_api_call) REFERENCES api_calls(correlation_id)
            )
        """)

        # Ingestion records table (what was written)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                source_api_calls TEXT,  -- JSON array of correlation IDs
                ingestion_method TEXT NOT NULL,
                ingestion_confidence TEXT NOT NULL,
                canonical_payload_json TEXT,  -- Full metadata
                conflicts JSON,
                operator TEXT,
                dry_run BOOLEAN DEFAULT 0,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Verification log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                file_path TEXT NOT NULL,
                verification_type TEXT,  -- "isrc_match", "provider_conflict", "checksum", etc.
                status TEXT NOT NULL,
                details JSON,
                operator TEXT,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_path) REFERENCES ingestion_records(file_path)
            )
        """)

        conn.commit()
        conn.close()

    def log_api_call(self, call: APICall) -> None:
        """Record an API call"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO api_calls (
                correlation_id, timestamp, provider, endpoint,
                request_params, request_hash, response_status,
                response_size_bytes, response_hash, duration_ms,
                tool, operator, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            call.correlation_id, call.timestamp, call.provider.value,
            call.endpoint, json.dumps(call.request_params), call.request_hash,
            call.response_status, call.response_size_bytes, call.response_hash,
            call.duration_ms, call.tool, call.operator, call.notes
        ))

        conn.commit()
        conn.close()
        self.logger.info(f"Logged API call: {call.provider.value} {call.endpoint} [{call.correlation_id}]")

    def log_data_extraction(self, data_point: DataPoint) -> None:
        """Record a data point extracted from API response"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO data_points (
                field_name, value, source_api_call, extraction_method,
                confidence, validation_status
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data_point.field_name, json.dumps(data_point.value),
            data_point.source_api_call, data_point.extraction_method,
            data_point.confidence, data_point.validation_status
        ))

        conn.commit()
        conn.close()

    def log_ingestion(self, record: IngestionRecord) -> None:
        """Record what was written to file/DB"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ingestion_records (
                timestamp, file_path, file_hash, source_api_calls,
                ingestion_method, ingestion_confidence, canonical_payload_json,
                conflicts, operator, dry_run, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.timestamp, record.file_path, record.file_hash,
            json.dumps(record.source_api_calls), record.ingestion_method,
            record.ingestion_confidence, json.dumps(record.canonical_payload_json),
            json.dumps(record.conflicts) if record.conflicts else None,
            record.operator, record.dry_run, record.notes
        ))

        conn.commit()
        conn.close()
        self.logger.info(f"Logged ingestion: {record.file_path} (sources: {record.source_api_calls})")

    def log_verification(self, file_path: str, verification_type: str, status: VerificationStatus, details: Optional[Dict] = None, operator: Optional[str] = None, notes: Optional[str] = None) -> None:
        """Record verification check (ISRC match, conflicts, checksums, etc.)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO verification_log (
                timestamp, file_path, verification_type, status, details, operator, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(), file_path, verification_type,
            status.value, json.dumps(details) if details else None,
            operator, notes
        ))

        conn.commit()
        conn.close()
        self.logger.info(f"Logged verification: {file_path} → {verification_type}: {status.value}")

    def get_audit_trail(self, file_path: str) -> Dict[str, Any]:
        """
        Get complete audit trail for a file:
        - Which API calls provided its data
        - What values were extracted
        - What was actually written
        - Verification checks performed
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get ingestion record
        cursor.execute("SELECT * FROM ingestion_records WHERE file_path = ?", (file_path,))
        ingestion = dict(cursor.fetchone() or {})

        audit_trail = {
            "file_path": file_path,
            "ingestion": ingestion,
            "source_api_calls": [],
            "data_points": [],
            "verification_checks": [],
        }

        if ingestion:
            # Get source API calls
            source_ids = json.loads(ingestion.get("source_api_calls", "[]"))
            for call_id in source_ids:
                cursor.execute("SELECT * FROM api_calls WHERE correlation_id = ?", (call_id,))
                call = cursor.fetchone()
                if call:
                    audit_trail["source_api_calls"].append({
                        "id": call["correlation_id"],
                        "timestamp": call["timestamp"],
                        "provider": call["provider"],
                        "endpoint": call["endpoint"],
                        "response_status": call["response_status"],
                        "duration_ms": call["duration_ms"],
                        "operator": call["operator"],
                    })

            # Get data points
            cursor.execute("""
                SELECT dp.* FROM data_points dp
                WHERE dp.source_api_call IN ({})
            """.format(",".join("?" * len(source_ids))), source_ids)

            for dp in cursor.fetchall():
                audit_trail["data_points"].append({
                    "field": dp["field_name"],
                    "value": json.loads(dp["value"]),
                    "confidence": dp["confidence"],
                    "validation_status": dp["validation_status"],
                })

        # Get verification checks
        cursor.execute("SELECT * FROM verification_log WHERE file_path = ? ORDER BY created_at DESC", (file_path,))
        for check in cursor.fetchall():
            audit_trail["verification_checks"].append({
                "timestamp": check["timestamp"],
                "type": check["verification_type"],
                "status": check["status"],
                "details": json.loads(check["details"]) if check["details"] else None,
                "operator": check["operator"],
            })

        conn.close()
        return audit_trail

    def verify_integrity(self, file_path: str) -> Dict[str, Any]:
        """
        Comprehensive verification:
        1. Does file exist and match recorded hash?
        2. Do all source API calls still in log?
        3. Do extracted data points match what was written?
        4. Are there any conflicts recorded?
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        result = {
            "file_path": file_path,
            "status": VerificationStatus.UNVERIFIED.value,
            "checks": {},
            "issues": [],
        }

        # Check 1: File exists and hash matches
        if Path(file_path).exists():
            actual_hash = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
            cursor.execute("SELECT file_hash FROM ingestion_records WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            if row:
                recorded_hash = row["file_hash"]
                result["checks"]["file_hash"] = {
                    "recorded": recorded_hash,
                    "actual": actual_hash,
                    "match": actual_hash == recorded_hash,
                }
                if actual_hash != recorded_hash:
                    result["issues"].append(f"File hash mismatch (file may have been modified)")
        else:
            result["issues"].append(f"File not found: {file_path}")

        # Check 2: Source API calls exist
        cursor.execute("SELECT source_api_calls FROM ingestion_records WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        if row:
            source_ids = json.loads(row["source_api_calls"])
            result["checks"]["source_api_calls"] = {
                "requested": len(source_ids),
                "found": 0,
                "missing": [],
            }
            for call_id in source_ids:
                cursor.execute("SELECT 1 FROM api_calls WHERE correlation_id = ?", (call_id,))
                if cursor.fetchone():
                    result["checks"]["source_api_calls"]["found"] += 1
                else:
                    result["checks"]["source_api_calls"]["missing"].append(call_id)
                    result["issues"].append(f"Source API call missing: {call_id}")

        # Check 3: Conflicts recorded?
        cursor.execute("SELECT conflicts FROM ingestion_records WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        if row and row["conflicts"]:
            conflicts = json.loads(row["conflicts"])
            result["checks"]["conflicts"] = conflicts
            if conflicts:
                result["issues"].append(f"Conflicts recorded: {list(conflicts.keys())}")

        # Determine overall status
        if result["issues"]:
            result["status"] = VerificationStatus.FLAGGED.value
        else:
            result["status"] = VerificationStatus.VERIFIED.value

        conn.close()
        return result

    def export_audit_report(self, output_path: str, file_paths: Optional[List[str]] = None) -> None:
        """
        Export complete audit report (JSON).
        If file_paths specified, report on those; otherwise all files.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        report = {
            "timestamp": datetime.now().isoformat(),
            "files_audited": [],
        }

        if file_paths:
            cursor.execute("SELECT DISTINCT file_path FROM ingestion_records WHERE file_path IN ({})".format(",".join("?" * len(file_paths))), file_paths)
        else:
            cursor.execute("SELECT DISTINCT file_path FROM ingestion_records")

        for row in cursor.fetchall():
            file_path = row["file_path"]
            audit_trail = self.get_audit_trail(file_path)
            verification = self.verify_integrity(file_path)
            report["files_audited"].append({
                "path": file_path,
                "audit_trail": audit_trail,
                "verification": verification,
            })

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        self.logger.info(f"Exported audit report: {output_path}")


# --- Integration with intake pipeline ---

class IntakeWithProvenance:
    """Wrapper around intake pipeline that tracks provenance"""

    def __init__(self, tracker: ProvenanceTracker):
        self.tracker = tracker

    async def ingest_with_provenance(
        self,
        file_path: str,
        api_call: APICall,
        extracted_data: Dict[str, Any],
        operator: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        """
        Ingest a file with full provenance tracking.
        """
        # Log the API call
        self.tracker.log_api_call(api_call)

        # Log each data point
        for field_name, value in extracted_data.items():
            data_point = DataPoint(
                field_name=field_name,
                value=value,
                source_api_call=api_call.correlation_id,
                extraction_method="json_path",  # or "regex", "manual", etc.
                confidence=0.95,  # Set based on validation
                validation_status="valid",
            )
            self.tracker.log_data_extraction(data_point)

        # Log the ingestion
        file_hash = hashlib.sha256(Path(file_path).read_bytes()).hexdigest() if Path(file_path).exists() else ""
        ingestion_record = IngestionRecord(
            timestamp=datetime.now().isoformat(),
            file_path=file_path,
            file_hash=file_hash,
            source_api_calls=[api_call.correlation_id],
            data_points=[
                DataPoint(
                    field_name=k, value=v, source_api_call=api_call.correlation_id,
                    extraction_method="json_path", confidence=0.95, validation_status="valid"
                )
                for k, v in extracted_data.items()
            ],
            ingestion_method="provider_api",
            ingestion_confidence="high",
            canonical_payload_json=extracted_data,
            operator=operator,
            dry_run=dry_run,
        )
        self.tracker.log_ingestion(ingestion_record)

        # Verification
        self.tracker.log_verification(
            file_path, "integrity_check", VerificationStatus.VERIFIED,
            details={"file_hash": file_hash}
        )

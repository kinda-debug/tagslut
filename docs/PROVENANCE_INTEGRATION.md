# Provenance Tracking System — Integration Guide

## Problem Statement

**Current state:**
- Postman makes API calls (Tidal, Beatport, Qobuz)
- Data comes back
- But there's **no link** between what Postman received and what got written to files/DB
- No audit trail
- No way to verify: "Who tagged this? When? From which API?"

**Risk:**
- Silent data corruption undetected
- API responses lost (can't re-verify)
- Provider ID conflicts not flagged
- ISRC mismatches buried
- No chain of custody

---

## Solution: Provenance Tracker

A central audit log that records:

### Layer 1: API Calls (Postman Input)
```
Timestamp: 2026-03-27T12:34:56Z
Provider: beatport
Endpoint: /v4/catalog/tracks/{id}
Request: {params: {...}, headers: {...}}
Response: 200 OK, 2.3 KB
Duration: 145ms
Hash: a3f1e8d2...  (SHA256 of response body)
Operator: georgeskhawam (Postman user)
Correlation ID: 6f7a9b2c  (unique tracking ID)
```

### Layer 2: Data Extraction
```
Source API Call: 6f7a9b2c
Field: "title"
Value: "Some Track"
Extraction Method: json_path ($.track.name)
Confidence: 0.99
Validation: VALID
```

### Layer 3: Ingestion (What Got Written)
```
Timestamp: 2026-03-27T12:34:58Z
File Path: /Volumes/MUSIC/MASTER_LIBRARY/.../track.flac
File Hash: 7e2f5d9a...
Source API Calls: [6f7a9b2c]  (linked back to Layer 1)
Ingestion Method: provider_api (beatport)
Confidence: verified (multiple sources agree)
Canonical Data: {title, artist, duration_ms, ...}
Conflicts: {provider_ids: ["beatport_123", "tidal_456"]}  (flagged, not hidden)
Operator: georgeskhawam
```

### Layer 4: Verification
```
File Path: /Volumes/MUSIC/.../track.flac
Check 1: File exists? YES
Check 2: Hash match? YES (7e2f5d9a... == recorded)
Check 3: Source API calls in log? YES (6f7a9b2c found)
Check 4: Conflicts recorded? YES (flagged for review)
Status: VERIFIED (but with flagged conflicts)
```

---

## Architecture

```
Postman (API calls)
    ↓
ProvenanceTracker.log_api_call()
    ↓
API_CALLS table
    ↓ (data extraction)
ProvenanceTracker.log_data_extraction()
    ↓
DATA_POINTS table
    ↓ (ingestion)
IntakeWithProvenance.ingest_with_provenance()
    ↓
INGESTION_RECORDS table
    ↓ (verification)
ProvenanceTracker.verify_integrity()
    ↓
VERIFICATION_LOG table
    ↓ (audit query)
ProvenanceTracker.get_audit_trail()
    ↓
Complete chain of custody (printable/exportable)
```

---

## Usage

### Initialize Tracker

```python
from provenance_tracker import ProvenanceTracker, APICall, APIProvider

tracker = ProvenanceTracker(db_path="/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/provenance.db")
```

### Log API Call (From Postman or Python)

```python
import time

start = time.time()
response = requests.get("https://api.beatport.com/v4/catalog/tracks/12345678")
duration_ms = int((time.time() - start) * 1000)

api_call = APICall(
    timestamp=datetime.now().isoformat(),
    provider=APIProvider.BEATPORT,
    endpoint="/v4/catalog/tracks/12345678",
    request_params={"id": "12345678"},
    request_hash=hashlib.sha256(json.dumps({"id": "12345678"}).encode()).hexdigest(),
    response_status=response.status_code,
    response_size_bytes=len(response.content),
    response_hash=hashlib.sha256(response.content).hexdigest(),
    duration_ms=duration_ms,
    tool="python_requests",
    operator="georgeskhawam",
    notes="Track lookup for DJ pool admission",
)

tracker.log_api_call(api_call)
```

### Log Data Extraction

```python
from provenance_tracker import DataPoint

data_point = DataPoint(
    field_name="title",
    value=response.json()["name"],
    source_api_call=api_call.correlation_id,
    extraction_method="json_path:$.name",
    confidence=0.99,
    validation_status="valid",
)

tracker.log_data_extraction(data_point)
```

### Log Ingestion (File Write)

```python
from provenance_tracker import IngestionRecord
import hashlib

ingestion_record = IngestionRecord(
    timestamp=datetime.now().isoformat(),
    file_path="/Volumes/MUSIC/MASTER_LIBRARY/Artists/Track.flac",
    file_hash=hashlib.sha256(Path("/Volumes/MUSIC/MASTER_LIBRARY/Artists/Track.flac").read_bytes()).hexdigest(),
    source_api_calls=[api_call.correlation_id],
    data_points=[
        DataPoint(
            field_name="title",
            value=response.json()["name"],
            source_api_call=api_call.correlation_id,
            extraction_method="json_path:$.name",
            confidence=0.99,
            validation_status="valid",
        ),
        # ... more data points
    ],
    ingestion_method="provider_api",
    ingestion_confidence="verified",
    canonical_payload_json=response.json(),
    operator="georgeskhawam",
    dry_run=False,
)

tracker.log_ingestion(ingestion_record)
```

### Log Verification Check

```python
from provenance_tracker import VerificationStatus

tracker.log_verification(
    file_path="/Volumes/MUSIC/MASTER_LIBRARY/Artists/Track.flac",
    verification_type="isrc_match",
    status=VerificationStatus.VERIFIED,
    details={"beatport_isrc": "USRC1234567890", "tidal_isrc": "USRC1234567890"},
    operator="georgeskhawam",
    notes="ISRCs match across Beatport and Tidal"
)
```

### Query Audit Trail

```python
audit_trail = tracker.get_audit_trail("/Volumes/MUSIC/MASTER_LIBRARY/Artists/Track.flac")

print(json.dumps(audit_trail, indent=2))
# Output:
# {
#   "file_path": "...",
#   "ingestion": {
#     "timestamp": "2026-03-27T12:34:58Z",
#     "source_api_calls": ["6f7a9b2c"],
#     "ingestion_method": "provider_api",
#     "ingestion_confidence": "verified",
#     ...
#   },
#   "source_api_calls": [
#     {
#       "id": "6f7a9b2c",
#       "timestamp": "2026-03-27T12:34:56Z",
#       "provider": "beatport",
#       "endpoint": "/v4/catalog/tracks/12345678",
#       "response_status": 200,
#       "duration_ms": 145,
#       "operator": "georgeskhawam"
#     }
#   ],
#   "data_points": [
#     {
#       "field": "title",
#       "value": "Some Track",
#       "confidence": 0.99,
#       "validation_status": "valid"
#     },
#     ...
#   ],
#   "verification_checks": [
#     {
#       "timestamp": "2026-03-27T12:35:00Z",
#       "type": "isrc_match",
#       "status": "verified",
#       "details": {...}
#     }
#   ]
# }
```

### Verify Integrity

```python
verification = tracker.verify_integrity("/Volumes/MUSIC/MASTER_LIBRARY/Artists/Track.flac")

print(json.dumps(verification, indent=2))
# Output:
# {
#   "file_path": "...",
#   "status": "verified",  # or "flagged", "conflicted"
#   "checks": {
#     "file_hash": {
#       "recorded": "7e2f5d9a...",
#       "actual": "7e2f5d9a...",
#       "match": true
#     },
#     "source_api_calls": {
#       "requested": 1,
#       "found": 1,
#       "missing": []
#     },
#     "conflicts": {
#       "provider_ids": ["beatport_123", "tidal_456"]
#     }
#   },
#   "issues": []
# }
```

### Export Audit Report

```python
tracker.export_audit_report(
    output_path="/Users/georgeskhawam/Projects/tagslut_db/audit_report_2026-03-27.json",
    file_paths=[
        "/Volumes/MUSIC/MASTER_LIBRARY/Artists/Track1.flac",
        "/Volumes/MUSIC/MASTER_LIBRARY/Artists/Track2.flac",
    ]
)
# Generates comprehensive JSON report with all audit trails + verification checks
```

---

## Integration with Intake Pipeline

### Current (No Provenance)

```python
async def process_tidal_url(url: str):
    track_data = await tidal_api.get_track(url)
    write_to_file(track_data)  # ← No link to API call
    write_to_db(track_data)    # ← No source recorded
```

### With Provenance

```python
async def process_tidal_url(url: str, tracker: ProvenanceTracker, operator: str):
    # Make API call (with timing)
    start = time.time()
    response = await tidal_api.get_track(url)
    duration_ms = int((time.time() - start) * 1000)
    
    # Log the call
    api_call = APICall(
        timestamp=datetime.now().isoformat(),
        provider=APIProvider.TIDAL,
        endpoint=f"/v1/tracks/{track_id}",
        request_params={"id": track_id},
        request_hash=hashlib.sha256(json.dumps({"id": track_id}).encode()).hexdigest(),
        response_status=response.status_code,
        response_size_bytes=len(response.content),
        response_hash=hashlib.sha256(response.content).hexdigest(),
        duration_ms=duration_ms,
        tool="python_aiohttp",
        operator=operator,
    )
    tracker.log_api_call(api_call)
    
    # Extract data
    track_data = response.json()
    for field, value in track_data.items():
        tracker.log_data_extraction(DataPoint(
            field_name=field,
            value=value,
            source_api_call=api_call.correlation_id,
            extraction_method="json_path",
            confidence=0.95,
            validation_status="valid",
        ))
    
    # Write file
    file_path = write_to_file(track_data)
    file_hash = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
    
    # Log ingestion
    tracker.log_ingestion(IngestionRecord(
        timestamp=datetime.now().isoformat(),
        file_path=file_path,
        file_hash=file_hash,
        source_api_calls=[api_call.correlation_id],
        data_points=[...],
        ingestion_method="provider_api",
        ingestion_confidence="high",
        canonical_payload_json=track_data,
        operator=operator,
    ))
    
    # Verify
    tracker.log_verification(
        file_path,
        "integrity_check",
        VerificationStatus.VERIFIED,
        details={"file_hash": file_hash},
    )
```

---

## Postman Integration

### Option 1: Postman → Python Bridge

Create a Postman **post-request script** that sends response to Python logging endpoint:

```javascript
// In Postman's "Tests" tab
const request_body = pm.request.url.query.all().reduce((acc, param) => {
    acc[param.key] = param.value;
    return acc;
}, {});

const api_log = {
    timestamp: new Date().toISOString(),
    provider: "beatport",  // or extract from env
    endpoint: pm.request.url.pathname,
    request_params: request_body,
    request_hash: CryptoJS.SHA256(JSON.stringify(request_body)).toString(),
    response_status: pm.response.code,
    response_size_bytes: pm.response.responseSize,
    response_hash: CryptoJS.SHA256(pm.response.text()).toString(),
    duration_ms: pm.response.responseTime,
    tool: "postman",
    operator: pm.environment.get("POSTMAN_USER"),
};

// Send to Python logging service
pm.sendRequest({
    url: "http://localhost:9999/log-api-call",
    method: "POST",
    header: { "Content-Type": "application/json" },
    body: { mode: "raw", raw: JSON.stringify(api_log) }
}, (err, resp) => {
    if (err) console.log("Logging failed: " + err);
    else console.log("API call logged: " + api_log.provider);
});
```

### Option 2: Export Postman Logs + Import

Export Postman run results:
```bash
newman run tagslut_collection.json -e env.json --reporters json --reporter-json-export run_results.json
```

Parse and import into provenance DB:
```python
import json
from provenance_tracker import ProvenanceTracker, APICall, APIProvider

tracker = ProvenanceTracker(...)

with open("run_results.json") as f:
    results = json.load(f)

for request in results["run"]["executions"]:
    api_call = APICall(
        timestamp=request["timestamp"],
        provider=APIProvider.BEATPORT,  # extract from request name
        endpoint=request["request"]["url"]["pathname"],
        request_params=...,  # extract from request
        request_hash=...,
        response_status=request["response"]["code"],
        response_size_bytes=len(request["response"]["body"]),
        response_hash=...,
        duration_ms=request["response"]["responseTime"],
        tool="newman",
        operator=pm.environment.get("POSTMAN_USER"),
    )
    tracker.log_api_call(api_call)
```

---

## Queries & Reporting

### Find All Files from a Specific API Call

```sql
SELECT DISTINCT ir.file_path
FROM ingestion_records ir
WHERE ir.source_api_calls LIKE '%6f7a9b2c%';
```

### Find Files with Conflicts

```sql
SELECT ir.file_path, ir.conflicts
FROM ingestion_records ir
WHERE ir.conflicts IS NOT NULL
  AND ir.conflicts != 'null';
```

### Find Files Ingested by Specific Operator

```sql
SELECT ir.file_path, ir.timestamp, ir.ingestion_method
FROM ingestion_records ir
WHERE ir.operator = 'georgeskhawam'
  AND date(ir.timestamp) = date('2026-03-27');
```

### Audit Trail for File

```sql
SELECT ac.*, dp.field_name, dp.value
FROM ingestion_records ir
JOIN api_calls ac ON ir.source_api_calls LIKE '%' || ac.correlation_id || '%'
LEFT JOIN data_points dp ON ac.correlation_id = dp.source_api_call
WHERE ir.file_path = '/Volumes/MUSIC/MASTER_LIBRARY/.../track.flac';
```

---

## Database Schema

```sql
api_calls
├─ correlation_id (PK)
├─ timestamp
├─ provider (tidal, beatport, qobuz, etc.)
├─ endpoint
├─ request_params (JSON)
├─ request_hash (SHA256)
├─ response_status (200, 401, 404, etc.)
├─ response_size_bytes
├─ response_hash (SHA256)
├─ duration_ms
├─ tool (postman, python_requests, etc.)
├─ operator (who made the call)
└─ notes

data_points
├─ id (PK)
├─ field_name (title, duration_ms, isrc, etc.)
├─ value (JSON)
├─ source_api_call (FK → api_calls)
├─ extraction_method (json_path, regex, manual)
├─ confidence (0.0–1.0)
└─ validation_status (valid, warning, error)

ingestion_records
├─ id (PK)
├─ timestamp
├─ file_path (UNIQUE)
├─ file_hash (SHA256)
├─ source_api_calls (JSON array of correlation IDs)
├─ ingestion_method (provider_api, local_tags, etc.)
├─ ingestion_confidence (verified, corroborated, high, uncertain, legacy)
├─ canonical_payload_json (all metadata written)
├─ conflicts (JSON: provider_id conflicts, ISRC mismatches, etc.)
├─ operator
├─ dry_run
└─ notes

verification_log
├─ id (PK)
├─ timestamp
├─ file_path (FK → ingestion_records)
├─ verification_type (integrity, isrc_match, provider_conflict, etc.)
├─ status (unverified, verified, conflicted, failed, flagged)
├─ details (JSON)
├─ operator
└─ notes
```

---

## Key Principles

1. **Nothing happens without a log entry**
   - API call? Logged.
   - Data extracted? Logged.
   - File written? Logged.
   - Verification performed? Logged.

2. **Conflicts are recorded, not hidden**
   - ISRC mismatch? Stored in `ingestion_records.conflicts`.
   - Provider ID disagree? Flagged with confidence=uncertain.

3. **Chain of custody is unbroken**
   - Every file points back to source API calls.
   - Every API call has request + response hash.
   - Every data point has extraction method + confidence.

4. **Operator accountability**
   - Who made the API call? Recorded.
   - Who wrote the file? Recorded.
   - Who verified it? Recorded.

5. **Forensics-ready**
   - Can replay any API call (request hash).
   - Can verify response wasn't tampered (response hash).
   - Can audit who did what when.

---

## Testing Checklist

- [ ] API call logging works (Postman + Python)
- [ ] Data point extraction logs confidence + validation
- [ ] Ingestion records link back to API calls
- [ ] File hashes are computed + recorded
- [ ] Conflicts are flagged (not silently resolved)
- [ ] Audit trail is complete (API → data → file → verify)
- [ ] Integrity checks pass (hash match, calls in log, etc.)
- [ ] Operator tracking works
- [ ] Export report generates JSON correctly
- [ ] Queries work (find by API call, by operator, by conflicts)

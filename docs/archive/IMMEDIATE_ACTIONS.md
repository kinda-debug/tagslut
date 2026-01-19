# Immediate Simplification Actions
**Goal:** Start simplifying TODAY without breaking existing functionality

---

## ✅ PHASE 0: IMMEDIATE WINS (Today)

### 1. Create Environment Variable Support

Create `.env.example`:
```bash
# Dedupe Environment Configuration
# Copy to .env and customize for your system

# Database location
DEDUPE_DB=${HOME}/Projects/dedupe_db/EPOCH_20260119/music.db

# Volume paths
LIBRARY_PATH=/Volumes/COMMUNE/M/Library
STAGING_PATH=/Volumes/COMMUNE/M/_staging
SUSPECT_PATH=/Volumes/Vault/Vault
QUARANTINE_PATH=/Volumes/COMMUNE/M/_quarantine
RECOVERY_PATH=/Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY

# Artifacts and logs
DEDUPE_ARTIFACTS=${HOME}/Projects/dedupe/artifacts
DEDUPE_REPORTS=${DEDUPE_ARTIFACTS}/M/03_reports

# Scan settings
SCAN_WORKERS=8
SCAN_PROGRESS_INTERVAL=100
```

### 2. Create Path Resolution Utility

File: `dedupe/utils/env_paths.py`
```python
"""Environment-aware path resolution"""
import os
from pathlib import Path
from typing import Optional

def get_path(env_var: str, default: Optional[str] = None, required: bool = False) -> Path:
    """Get path from environment variable with fallback"""
    value = os.getenv(env_var, default)
    
    if value is None:
        if required:
            raise ValueError(
                f"Required environment variable {env_var} not set. "
                f"Copy .env.example to .env and configure."
            )
        return None
    
    # Expand user home directory and environment variables
    expanded = os.path.expanduser(os.path.expandvars(value))
    return Path(expanded)

# Common paths
def get_db_path() -> Path:
    return get_path("DEDUPE_DB", required=True)

def get_library_path() -> Path:
    return get_path("LIBRARY_PATH", required=True)

def get_staging_path() -> Optional[Path]:
    return get_path("STAGING_PATH")

def get_suspect_path() -> Optional[Path]:
    return get_path("SUSPECT_PATH")

def get_quarantine_path() -> Optional[Path]:
    return get_path("QUARANTINE_PATH")

def get_artifacts_dir() -> Path:
    return get_path("DEDUPE_ARTIFACTS", default="./artifacts")

def get_reports_dir() -> Path:
    return get_path("DEDUPE_REPORTS", default=f"{get_artifacts_dir()}/reports")
```

### 3. Update One Script as Example

Modify `tools/integrity/scan.py` to use env vars:
```python
# Add at top
from dedupe.utils.env_paths import get_db_path, get_reports_dir

# Replace hardcoded default
# OLD: default="/Users/georgeskhawam/Projects/dedupe_db/..."
# NEW: default=str(get_db_path())

# For error log
# OLD: "/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors.log"
# NEW: get_reports_dir() / "scan_errors.log"
```

### 4. Document Current Paths

Create `PATH_INVENTORY.md`:
```markdown
# Hardcoded Path Inventory

## Critical Paths to Replace

1. **Database**: /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-16/music.db
   - Used in: 30+ files
   - Replace with: ${DEDUPE_DB}

2. **Library**: /Volumes/COMMUNE/M/Library
   - Used in: 20+ files  
   - Replace with: ${LIBRARY_PATH}

3. **Artifacts**: /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/
   - Used in: 25+ files
   - Replace with: ${DEDUPE_REPORTS}

... (list all)
```

---

## 📋 PHASE 1: CONSOLIDATE DOCS (This Week)

### Action: Merge Documentation

#### Keep (4 files):
1. **README.md** - Overview & quick start
2. **QUICKSTART.md** - Step-by-step for new users  
3. **GUIDE.md** - Complete reference (merge all operator guides)
4. **CHANGELOG.md** - Version history

#### Archive (move to `docs/archive/`):
- AI_AGENT_HANDOVER_REPORT.md
- DEDUPE PRODUCTION SYSTEM — OPERATIONAL HANDOVER.md
- MODERNIZATION_SUMMARY.md
- docs/IMPLEMENTATION_SUMMARY.md
- docs/PROGRESS_SNAPSHOT.md
- docs/HANDOVER.md

#### Merge into GUIDE.md:
- docs/OPERATOR_GUIDE.md
- docs/OPERATOR_RUNBOOK.md
- docs/OPERATOR_VISUAL_GUIDE.md
- docs/SCAN_TO_REVIEW_WORKFLOW.md
- docs/CLEAN_SCAN_WORKPLAN.md
- docs/SCANNING.md
- docs/TOOLS.md

#### Create New Structure:
```
dedupe/
├── README.md              # Project overview
├── QUICKSTART.md          # Get started in 5 minutes
├── GUIDE.md               # Complete user guide
├── CHANGELOG.md           # Version history
├── COMPLEXITY_AUDIT.md    # This analysis
├── V2_ARCHITECTURE.md     # Future vision
└── docs/
    ├── API.md             # For developers
    ├── CONFIG.md          # Configuration reference
    └── archive/           # Old docs (for reference)
```

### Template for GUIDE.md:
```markdown
# Dedupe Complete Guide

## Table of Contents
1. Installation
2. Configuration
3. Basic Workflow
4. Commands Reference
5. Advanced Usage
6. Troubleshooting
7. FAQ

## 1. Installation
...

## 2. Configuration

### Environment Variables
Create `.env` file:
\`\`\`bash
DEDUPE_DB=/path/to/music.db
LIBRARY_PATH=/path/to/library
...
\`\`\`

### Config File (Optional)
Edit `config.yaml` for advanced settings.

## 3. Basic Workflow

### Step 1: Scan
\`\`\`bash
python tools/integrity/scan.py /path/to/volume --zone suspect
\`\`\`

### Step 2: Recommend
...

(Merge all workflow content here)
```

---

## 🔧 PHASE 2: STANDARDIZE SCRIPTS (Next Week)

### Common Pattern for All Scripts:

```python
#!/usr/bin/env python3
"""
Script name and purpose
"""
import argparse
from pathlib import Path
from dedupe.utils.env_paths import get_db_path, get_reports_dir

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    
    # Use env defaults instead of hardcoded
    parser.add_argument(
        "--db",
        type=Path,
        default=get_db_path(),  # From env
        help="Database path (default: $DEDUPE_DB)"
    )
    
    parser.add_argument(
        "--log",
        type=Path,
        default=get_reports_dir() / "script.log",  # From env
        help="Log file (default: $DEDUPE_REPORTS/script.log)"
    )
    
    args = parser.parse_args()
    # ... rest of script

if __name__ == "__main__":
    main()
```

### Scripts to Update (Priority Order):
1. ✅ `tools/integrity/scan.py` - Most used
2. `tools/decide/recommend.py` - Core workflow
3. `tools/review/apply_removals.py` - Core workflow  
4. `tools/review/promote_by_tags.py` - Recently updated
5. ... (all others)

---

## 🗂️ PHASE 3: CREATE SIMPLE CLI (Week 3)

### Minimal CLI Wrapper

File: `dedupe/cli.py`
```python
"""
Dedupe CLI - Unified interface
Usage: python -m dedupe.cli COMMAND [ARGS...]
"""
import sys
import subprocess
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent / "tools"

COMMANDS = {
    "scan": TOOLS_DIR / "integrity/scan.py",
    "recommend": TOOLS_DIR / "decide/recommend.py",
    "apply": TOOLS_DIR / "review/apply_removals.py",
    "promote": TOOLS_DIR / "review/promote_by_tags.py",
    "doctor": TOOLS_DIR / "db/doctor.py",
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: python -m dedupe.cli COMMAND [ARGS...]")
        print("\nCommands:")
        for cmd in COMMANDS:
            print(f"  {cmd}")
        sys.exit(1)
    
    command = sys.argv[1]
    script = COMMANDS[command]
    args = sys.argv[2:]
    
    # Execute script
    result = subprocess.run([sys.executable, str(script)] + args)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
```

Now users can do:
```bash
python -m dedupe.cli scan /path --zone suspect
python -m dedupe.cli recommend
python -m dedupe.cli apply --plan plan.json
```

---

## 📊 PROGRESS TRACKING

### Metrics to Track

```markdown
| Metric | Before | After Phase 0 | After Phase 1 | After Phase 2 | Target |
|--------|--------|---------------|---------------|---------------|--------|
| Hardcoded paths | 100+ | 100 | 100 | 50 | 0 |
| Doc files | 20 | 20 | 8 | 5 | 4 |
| Executable scripts | 30+ | 30+ | 30+ | 30+ | 1 |
| Config files | 1 (unused) | 2 | 2 | 2 | 1 |
| Entry points | 30+ | 30+ | 30+ | 10 | 1 |
```

---

## ✅ IMMEDIATE TODO LIST

### Today (2 hours):
- [ ] Create `.env.example`
- [ ] Create `dedupe/utils/env_paths.py`
- [ ] Create `PATH_INVENTORY.md`
- [ ] Update `tools/integrity/scan.py` as proof-of-concept

### This Week (1 day):
- [ ] Merge docs into 4 core files
- [ ] Move old docs to `docs/archive/`
- [ ] Update README.md with env var instructions
- [ ] Create GUIDE.md from merged content

### Next Week (2 days):
- [ ] Update all tools to use env_paths
- [ ] Test all updated scripts
- [ ] Update Makefile with env-aware targets

### Week 3 (2 days):
- [ ] Create minimal CLI wrapper
- [ ] Document CLI usage
- [ ] Create migration guide

---

## 🎯 SUCCESS CRITERIA

### Phase 0 Complete When:
- [ ] `.env.example` exists and is documented
- [ ] At least one script uses env vars
- [ ] Path inventory is complete
- [ ] Team can start using .env files

### Phase 1 Complete When:
- [ ] Only 4 main doc files exist
- [ ] Old docs archived (not deleted)
- [ ] README explains env vars
- [ ] GUIDE.md is comprehensive

### Phase 2 Complete When:
- [ ] All scripts use env_paths
- [ ] No script has hardcoded paths
- [ ] All scripts tested
- [ ] Migration guide exists

---

## 🚨 SAFETY CHECKS

Before each change:
1. ✅ Test script still works
2. ✅ Backward compatible (env var is optional)
3. ✅ Error message if env var missing
4. ✅ Document in CHANGELOG

---

## 📞 COMMUNICATION PLAN

### Update README.md:
```markdown
## ⚠️ MIGRATION IN PROGRESS

We're simplifying dedupe! Changes:

1. **Environment Variables** - Create `.env` file (see `.env.example`)
2. **Consolidated Docs** - Check GUIDE.md for everything
3. **Unified CLI** - Coming soon: `dedupe scan` instead of 30+ scripts

Old workflows still work but will show deprecation warnings.
See CHANGELOG.md for details.
```

---

**END OF ACTION PLAN**

Ready to execute Phase 0 immediately!

<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Tagslut Restructuring Plan: Phased Execution Guide

This is an executable refactoring plan with exact commands. Each phase is a standalone script.

***

## Phase 0: Dedupe Eradication (MANDATORY FIRST - 30 min)

**Risk Level:** Safe
**Rollback:** `git reset --hard HEAD` before committing

### Phase 0.1: Remove Entrypoints and Aliases

```bash
#!/bin/bash
# phase0_dedupe_eradication.sh

set -e  # Exit on error

echo "=== Phase 0: Dedupe Eradication ==="

# 1. Remove dedupe alias from pyproject.toml
echo "Removing dedupe entrypoints..."
sed -i.bak '/^dedupe = /d' pyproject.toml

# 2. Delete rebrand test files
echo "Deleting rebrand test files..."
git rm tests/test_tagslut_rebrand_alias.py
git rm tests/test_cli_alias_warning.py
git rm tests/test_cli_transitional_warnings.py

# 3. Search for all "dedupe" references
echo "Searching for dedupe references..."
grep -r "dedupe" --exclude-dir=.git --exclude-dir=.venv --exclude="*.pyc" --exclude="poetry.lock" . > /tmp/dedupe_refs.txt || true
echo "Found $(wc -l < /tmp/dedupe_refs.txt) references. Review /tmp/dedupe_refs.txt"

# 4. Remove deprecation warning code from CLI
echo "Searching for deprecation warnings in CLI..."
grep -n "deprecat" tagslut/cli/*.py tagslut/cli/commands/*.py || true

# 5. Check for dedupe folders
echo "Checking for dedupe folders..."
find . -type d -name "*dedupe*" -not -path "./.git/*" -not -path "./.venv/*" || echo "No dedupe folders found"

# 6. Clean documentation
echo "Checking documentation for dedupe references..."
grep -r "dedupe" docs/ README.md CHANGELOG.md 2>/dev/null || echo "No docs files with dedupe found"

echo ""
echo "MANUAL TASKS:"
echo "1. Review /tmp/dedupe_refs.txt and manually remove/replace remaining references"
echo "2. Check CHANGELOG.md and remove dedupe migration guidance"
echo "3. Remove any deprecation warning logic from tagslut/cli/main.py"
echo "4. Search for 'compatibility alias' and remove those comments"
```


### Phase 0.2: Manual Code Changes Checklist

```bash
# Search for specific patterns that need manual review
echo "=== Manual Review Required ==="

# Find alias-related code
rg "alias|deprecated|compatibility" tagslut/cli/ -n

# Find any conditional logic handling "dedupe"
rg 'if.*dedupe|dedupe.*if' tagslut/ -n

# Find comments mentioning dedupe
rg '#+.*dedupe' tagslut/ -n

# Find docstrings mentioning dedupe
rg '""".*dedupe|dedupe.*"""' tagslut/ -n
```


### Phase 0.3: Verification

```bash
#!/bin/bash
# verify_phase0.sh

echo "=== Verifying Phase 0 ==="

# No dedupe entrypoint in pyproject.toml
if grep -q "^dedupe = " pyproject.toml; then
    echo "❌ FAIL: dedupe entrypoint still exists in pyproject.toml"
    exit 1
else
    echo "✅ PASS: dedupe entrypoint removed"
fi

# No rebrand test files
if [ -f "tests/test_tagslut_rebrand_alias.py" ] || [ -f "tests/test_cli_alias_warning.py" ]; then
    echo "❌ FAIL: Rebrand test files still exist"
    exit 1
else
    echo "✅ PASS: Rebrand test files deleted"
fi

# Count remaining dedupe references (excluding binary/lock files)
DEDUPE_COUNT=$(grep -r "dedupe" --exclude-dir=.git --exclude-dir=.venv --exclude="*.pyc" --exclude="poetry.lock" . 2>/dev/null | wc -l)
echo "Remaining 'dedupe' references: $DEDUPE_COUNT"
if [ "$DEDUPE_COUNT" -gt 10 ]; then
    echo "⚠️  WARNING: Many dedupe references remain. Review manually."
else
    echo "✅ PASS: Minimal dedupe references remain"
fi

# Test that CLI still works
poetry run tagslut --help > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ PASS: tagslut CLI works"
else
    echo "❌ FAIL: tagslut CLI broken"
    exit 1
fi

# Test that dedupe command is gone
poetry run dedupe --help > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "✅ PASS: dedupe command no longer exists"
else
    echo "❌ FAIL: dedupe command still works (should be removed)"
    exit 1
fi

echo ""
echo "Phase 0 verification complete!"
```


***

## Phase 1: Quick Wins (30 min)

**Risk Level:** Safe
**Rollback:** `git reset --hard <commit-before-phase1>`

```bash
#!/bin/bash
# phase1_quick_wins.sh

set -e

echo "=== Phase 1: Quick Wins ==="

# 1. Move integrity_scanner.py to core/scanner.py
echo "Moving integrity_scanner.py..."
git mv tagslut/integrity_scanner.py tagslut/core/scanner.py

# Update imports in any files that reference it
echo "Finding imports of integrity_scanner..."
grep -rl "from tagslut import integrity_scanner" tagslut/ tests/ scripts/ || echo "None found"
grep -rl "from tagslut.integrity_scanner import" tagslut/ tests/ scripts/ > /tmp/integrity_imports.txt || true

if [ -s /tmp/integrity_imports.txt ]; then
    echo "Files with integrity_scanner imports:"
    cat /tmp/integrity_imports.txt
    echo "Update these files: s/from tagslut.integrity_scanner/from tagslut.core.scanner/g"
fi

# 2. Delete tagslut/legacy/ (importable legacy is a lie)
echo "Deleting tagslut/legacy/..."
git rm -rf tagslut/legacy/

# Check if tests reference it
grep -r "from tagslut.legacy" tests/ || echo "No test imports of tagslut.legacy"

# 3. Remove [tool.poetry.dependencies] duplicate from pyproject.toml
echo "Removing [tool.poetry.dependencies] section..."
python3 << 'PYTHON'
with open('pyproject.toml', 'r') as f:
    lines = f.readlines()

# Find [tool.poetry.dependencies] and remove until next section
in_poetry_deps = False
filtered = []
for line in lines:
    if line.strip() == '[tool.poetry.dependencies]':
        in_poetry_deps = True
        continue
    if in_poetry_deps and line.startswith('[') and 'poetry.dependencies' not in line:
        in_poetry_deps = False
    if not in_poetry_deps:
        filtered.append(line)

with open('pyproject.toml', 'w') as f:
    f.writelines(filtered)

print("Removed [tool.poetry.dependencies] section")
PYTHON

# Also remove [tool.poetry.scripts] (duplicate of [project.scripts])
echo "Removing [tool.poetry.scripts] section..."
python3 << 'PYTHON'
with open('pyproject.toml', 'r') as f:
    lines = f.readlines()

in_poetry_scripts = False
filtered = []
for line in lines:
    if line.strip() == '[tool.poetry.scripts]':
        in_poetry_scripts = True
        continue
    if in_poetry_scripts and line.startswith('[') and 'poetry.scripts' not in line:
        in_poetry_scripts = False
    if not in_poetry_scripts:
        filtered.append(line)

with open('pyproject.toml', 'w') as f:
    f.writelines(filtered)

print("Removed [tool.poetry.scripts] section")
PYTHON

# 4. Rename phase-numbered tests
echo "Renaming phase-numbered test files..."
git mv tests/test_v3_phase1_helpers.py tests/test_v3_identity_helpers.py
git mv tests/test_v3_phase1_scripts.py tests/test_v3_identity_scripts.py
git mv tests/test_phase2_policy_decide.py tests/test_policy_decision_engine.py
git mv tests/test_exec_engine_phase3.py tests/test_exec_engine_operations.py
git mv tests/test_exec_receipts_phase3.py tests/test_exec_receipt_tracking.py
git mv tests/test_phase4_cli_surface.py tests/test_cli_command_interface.py
git mv tests/test_move_from_plan_phase3_contract.py tests/test_move_from_plan_contract.py
git mv tests/test_quarantine_from_plan_phase3_contract.py tests/test_quarantine_from_plan_contract.py

# 5. Add architecture doc to cli/main.py
echo "Adding architecture comment to cli/main.py..."
python3 << 'PYTHON'
header = '''"""
CLI Entry Point for Tagslut

ARCHITECTURE INTENT:
This file should contain ONLY:
- Top-level Click group registration
- Command group imports from tagslut.cli.commands.*
- Global Click options/context setup

All command implementations belong in tagslut/cli/commands/*.py
Target size: < 500 bytes

Current state: 113KB god file (MIGRATION IN PROGRESS)
Target: Extract all command decorators to commands/ subdirectory
"""

'''

with open('tagslut/cli/main.py', 'r') as f:
    content = f.read()

# Only add header if not present
if 'ARCHITECTURE INTENT:' not in content:
    with open('tagslut/cli/main.py', 'w') as f:
        f.write(header + content)
    print("Added architecture comment to cli/main.py")
else:
    print("Architecture comment already exists")
PYTHON

echo ""
echo "Phase 1 complete!"
echo "Run verify_phase1.sh to validate"
```


### Phase 1 Verification

```bash
#!/bin/bash
# verify_phase1.sh

echo "=== Verifying Phase 1 ==="

# 1. integrity_scanner moved
if [ ! -f "tagslut/integrity_scanner.py" ] && [ -f "tagslut/core/scanner.py" ]; then
    echo "✅ PASS: integrity_scanner.py moved to core/scanner.py"
else
    echo "❌ FAIL: integrity_scanner move incomplete"
    exit 1
fi

# 2. legacy deleted
if [ ! -d "tagslut/legacy" ]; then
    echo "✅ PASS: tagslut/legacy/ deleted"
else
    echo "❌ FAIL: tagslut/legacy/ still exists"
    exit 1
fi

# 3. No [tool.poetry.dependencies] in pyproject.toml
if ! grep -q '\[tool.poetry.dependencies\]' pyproject.toml; then
    echo "✅ PASS: [tool.poetry.dependencies] removed"
else
    echo "❌ FAIL: [tool.poetry.dependencies] still exists"
    exit 1
fi

# 4. Phase-numbered tests renamed
PHASE_TESTS=$(find tests/ -name "*phase*.py" | wc -l)
if [ "$PHASE_TESTS" -eq 0 ]; then
    echo "✅ PASS: All phase-numbered tests renamed"
else
    echo "⚠️  WARNING: $PHASE_TESTS phase-numbered tests remain"
    find tests/ -name "*phase*.py"
fi

# 5. Architecture comment in cli/main.py
if grep -q "ARCHITECTURE INTENT:" tagslut/cli/main.py; then
    echo "✅ PASS: Architecture comment added to cli/main.py"
else
    echo "❌ FAIL: Architecture comment missing"
    exit 1
fi

# 6. Tests still pass
poetry run pytest tests/ -x -q
if [ $? -eq 0 ]; then
    echo "✅ PASS: All tests pass"
else
    echo "❌ FAIL: Tests broken"
    exit 1
fi

echo ""
echo "Phase 1 verification complete!"
```


***

## Phase 2: CLI Evacuation (2-3 hours)

**Risk Level:** Moderate
**Rollback:** `git reset --hard <commit-before-phase2>`

This phase requires extracting all command definitions from `cli/main.py` into `cli/commands/*.py`.

### Phase 2.1: Analysis Script

```bash
#!/bin/bash
# phase2_analyze_cli.sh

echo "=== Phase 2: Analyzing cli/main.py ==="

# Count @click.command decorators
COMMAND_COUNT=$(grep -c "@.*\.command(" tagslut/cli/main.py)
echo "Commands in main.py: $COMMAND_COUNT"

# List all @click.command definitions
echo ""
echo "Command definitions found:"
grep -n "@.*\.command(\|^def " tagslut/cli/main.py | grep -B1 "^def " | grep "@" | awk '{print $1, $2}'

# Calculate size
SIZE=$(wc -c < tagslut/cli/main.py)
echo ""
echo "Current size: $SIZE bytes (113KB)"
echo "Target size: < 500 bytes"
echo "Reduction needed: $(($SIZE - 500)) bytes (~99.5%)"

# Show existing command files
echo ""
echo "Existing command modules:"
ls -lh tagslut/cli/commands/*.py | grep -v __pycache__ | awk '{print $9, $5}'
```


### Phase 2.2: Extract Commands (Manual Template)

Since `cli/main.py` is 113KB, this requires careful extraction. Here's the systematic approach:

```bash
#!/bin/bash
# phase2_extract_commands.sh

echo "=== Phase 2.2: Command Extraction ==="
echo "This is a MANUAL process. Follow these steps:"
echo ""

cat << 'TEMPLATE'
For EACH command definition in tagslut/cli/main.py:

1. Identify command block:
   - Starts with @click.command() or @<group>.command()
   - Ends at next @command or end of function

2. Create/update file in tagslut/cli/commands/<command_name>.py:
   
   ```python
   import click
   from tagslut.cli.runtime import pass_runtime
   # ... other imports as needed
   
   @click.command()
   @click.option(...)  # copy all options
   @pass_runtime
   def command_name(ctx, option1, option2):
       """Docstring from original."""
       # Copy function body exactly
```

3. In tagslut/cli/main.py, replace command definition with import:

```python
from tagslut.cli.commands.command_name import command_name
cli.add_command(command_name)
```

4. Update tests to import from new location
5. Verify: poetry run tagslut command_name --help

EXISTING COMMAND MODULES (already extracted):

- auth.py (1.4KB)
- decide.py (3.8KB)
- execute.py (1.2KB)
- index.py (2.0KB)
- intake.py (0.8KB)
- report.py (2.1KB)
- verify.py (3.0KB)

These are SMALL and COMPLETE. All other commands are still in main.py.

PRIORITY EXTRACTION ORDER:

1. scan/index commands (most used)
2. decide commands
3. exec commands
4. report/verify commands
5. utility commands
TEMPLATE

# Generate extraction template for a single command

cat << 'EXTRACTOR'

# Helper: Extract a single command

function extract_command() {
CMD_NAME=\$1
echo "Extracting \$CMD_NAME..."

    # This is pseudocode - actual extraction requires parsing
    # 1. Find command in main.py
    # 2. Copy to commands/$CMD_NAME.py
    # 3. Add imports
    # 4. Replace in main.py with import + add_command
    
    echo "⚠️  Manual extraction required for: $CMD_NAME"
    }

EXTRACTOR

echo ""
echo "AUTOMATION NOTE:"
echo "Full automation of this phase requires an AST parser (libcst/rope)."
echo "For now, extract commands manually following the template above."
echo ""
echo "After each extraction:"
echo "  poetry run pytest tests/ -k test_cli -x"
echo "  poetry run tagslut <extracted-command> --help"

```

### Phase 2.3: Final CLI Structure

```python
# TARGET: tagslut/cli/main.py (< 500 bytes)

"""
CLI Entry Point for Tagslut

All command implementations are in tagslut.cli.commands.*
This file only contains group registration.
"""

import click
from tagslut.cli.commands import (
    auth, decide, execute, index, intake, report, verify,
    # ... import all command modules
)

@click.group()
@click.version_option()
@click.pass_context
def cli(ctx):
    """Tagslut: Music library deduplication toolkit."""
    pass

# Register all commands
cli.add_command(auth.auth)
cli.add_command(decide.decide)
cli.add_command(execute.execute)
cli.add_command(index.index)
cli.add_command(intake.intake)
cli.add_command(report.report)
cli.add_command(verify.verify)
# ... add all extracted commands

if __name__ == '__main__':
    cli()
```


### Phase 2 Verification

```bash
#!/bin/bash
# verify_phase2.sh

echo "=== Verifying Phase 2 ==="

# Check main.py size
MAIN_SIZE=$(wc -c < tagslut/cli/main.py)
echo "cli/main.py size: $MAIN_SIZE bytes"

if [ "$MAIN_SIZE" -lt 1000 ]; then
    echo "✅ PASS: cli/main.py is small (< 1KB)"
elif [ "$MAIN_SIZE" -lt 5000 ]; then
    echo "⚠️  WARNING: cli/main.py is $MAIN_SIZE bytes (target < 500)"
else
    echo "❌ FAIL: cli/main.py is still $MAIN_SIZE bytes"
    exit 1
fi

# Check that no @command decorators remain in main.py
CMD_IN_MAIN=$(grep -c "@.*\.command(" tagslut/cli/main.py || echo 0)
if [ "$CMD_IN_MAIN" -eq 0 ]; then
    echo "✅ PASS: No command definitions in main.py"
else
    echo "❌ FAIL: $CMD_IN_MAIN command definitions still in main.py"
    exit 1
fi

# Verify all commands still work
echo "Testing CLI commands..."
poetry run tagslut --help > /dev/null || exit 1
poetry run tagslut index --help > /dev/null || exit 1
poetry run tagslut decide --help > /dev/null || exit 1
poetry run tagslut execute --help > /dev/null || exit 1

echo "✅ PASS: CLI commands functional"

# Run CLI tests
poetry run pytest tests/ -k "test_cli" -x
if [ $? -eq 0 ]; then
    echo "✅ PASS: CLI tests pass"
else
    echo "❌ FAIL: CLI tests broken"
    exit 1
fi

echo ""
echo "Phase 2 verification complete!"
```


***

## Phase 3: Decision Logic Consolidation (1-2 hours)

**Risk Level:** Moderate
**Rollback:** `git reset --hard <commit-before-phase3>`

```bash
#!/bin/bash
# phase3_consolidate_decisions.sh

set -e

echo "=== Phase 3: Decision Logic Consolidation ==="

# 1. Analyze the three decision files
echo "Analyzing decision logic..."
echo "core/decisions.py: $(wc -l < tagslut/core/decisions.py) lines"
echo "decide/planner.py: $(wc -l < tagslut/decide/planner.py) lines"
echo "cli/commands/decide.py: $(wc -l < tagslut/cli/commands/decide.py) lines"

# 2. Find what core/decisions.py exports
echo ""
echo "core/decisions.py exports:"
grep "^def \|^class " tagslut/core/decisions.py | awk '{print "  - " $2}' | sed 's/(.*//'

# 3. Find imports of core/decisions
echo ""
echo "Files importing core/decisions:"
grep -r "from tagslut.core.decisions import\|from tagslut.core import decisions" tagslut/ tests/ --exclude-dir=__pycache__ || echo "  None"

# 4. Create backup
cp tagslut/core/decisions.py tagslut/core/decisions.py.backup
cp tagslut/decide/planner.py tagslut/decide/planner.py.backup

# 5. Merge strategy
cat << 'STRATEGY'

CONSOLIDATION STRATEGY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEEP:  tagslut/decide/planner.py (7,920 bytes)
       - Primary decision engine
       - Contains plan generation logic
       
MERGE: tagslut/core/decisions.py (1,405 bytes) → decide/planner.py
       - Decision enums/dataclasses
       - Helper functions
       
KEEP:  tagslut/cli/commands/decide.py (thin wrapper)
       - CLI interface only
       - Calls decide/planner.py

BOUNDARY:
  decide/        = Decision logic, plan generation, policy evaluation
  cli/commands/  = Argument parsing, output formatting, CLI UX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MANUAL STEPS:
1. Review core/decisions.py exports
2. Copy non-duplicate code to decide/planner.py
3. Update all imports:
     from tagslut.core.decisions import X
     →
     from tagslut.decide.planner import X
4. Delete tagslut/core/decisions.py
5. Run tests

STRATEGY

echo ""
echo "Backup created: *.backup files"
echo "Follow MANUAL STEPS above to consolidate"
echo ""
echo "After manual merge, run:"
echo "  bash verify_phase3.sh"
```


### Phase 3 Verification

```bash
#!/bin/bash
# verify_phase3.sh

echo "=== Verifying Phase 3 ==="

# 1. core/decisions.py should be deleted
if [ ! -f "tagslut/core/decisions.py" ]; then
    echo "✅ PASS: core/decisions.py deleted"
else
    echo "❌ FAIL: core/decisions.py still exists"
    exit 1
fi

# 2. No imports of core.decisions remain
IMPORTS=$(grep -r "from tagslut.core.decisions import\|from tagslut.core import decisions" tagslut/ tests/ --exclude-dir=__pycache__ 2>/dev/null | wc -l)
if [ "$IMPORTS" -eq 0 ]; then
    echo "✅ PASS: No imports of core.decisions"
else
    echo "❌ FAIL: $IMPORTS imports of core.decisions remain"
    grep -rn "from tagslut.core.decisions import\|from tagslut.core import decisions" tagslut/ tests/ --exclude-dir=__pycache__
    exit 1
fi

# 3. decide/planner.py is the canonical source
if [ -f "tagslut/decide/planner.py" ]; then
    echo "✅ PASS: decide/planner.py exists"
else
    echo "❌ FAIL: decide/planner.py missing"
    exit 1
fi

# 4. CLI command still thin
DECIDE_CMD_SIZE=$(wc -c < tagslut/cli/commands/decide.py)
if [ "$DECIDE_CMD_SIZE" -lt 5000 ]; then
    echo "✅ PASS: cli/commands/decide.py is thin ($DECIDE_CMD_SIZE bytes)"
else
    echo "⚠️  WARNING: cli/commands/decide.py is $DECIDE_CMD_SIZE bytes (review for bloat)"
fi

# 5. Tests pass
poetry run pytest tests/ -k "decide" -x
if [ $? -eq 0 ]; then
    echo "✅ PASS: Decision tests pass"
else
    echo "❌ FAIL: Decision tests broken"
    exit 1
fi

echo ""
echo "Phase 3 verification complete!"
```


***

## Phase 4: Architecture Foundations (2-3 hours)

**Risk Level:** Moderate to High
**Rollback:** `git reset --hard <commit-before-phase4>`

```bash
#!/bin/bash
# phase4_architecture_foundations.sh

set -e

echo "=== Phase 4: Architecture Foundations ==="

# ============================================
# 4.1: Create zones/ module
# ============================================
echo "Creating tagslut/zones/ module..."
mkdir -p tagslut/zones
touch tagslut/zones/__init__.py

cat > tagslut/zones/__init__.py << 'INIT'
"""
Zone Management System

Zones represent different quality/purpose tiers in the library:
- master: Pristine, lossless, tagged
- working: DJ-ready, lossy but tagged
- staging: Incoming, needs processing
- quarantine: Problematic files
"""

from tagslut.zones.assignment import assign_zone, get_zone_path

__all__ = ['assign_zone', 'get_zone_path']
INIT

# Move zone_assignment.py to zones/
git mv tagslut/core/zone_assignment.py tagslut/zones/assignment.py

# Create base.py for zone definitions
cat > tagslut/zones/base.py << 'BASE'
"""Zone definitions and base types."""

from enum import Enum
from typing import NamedTuple

class Zone(Enum):
    """Library quality zones."""
    MASTER = "master"
    WORKING = "working"
    STAGING = "staging"
    QUARANTINE = "quarantine"

class ZoneConfig(NamedTuple):
    """Configuration for a zone."""
    name: str
    path: str
    description: str
    auto_assign: bool = False

# Zone registry would go here in future
BASE

git add tagslut/zones/base.py

# Update imports
echo "Updating zone imports..."
grep -rl "from tagslut.core.zone_assignment import\|from tagslut.core import zone_assignment" tagslut/ tests/ --exclude-dir=__pycache__ > /tmp/zone_imports.txt || true

if [ -s /tmp/zone_imports.txt ]; then
    echo "Files needing zone import updates:"
    cat /tmp/zone_imports.txt
    echo "Update: s/tagslut.core.zone_assignment/tagslut.zones.assignment/g"
fi

# ============================================
# 4.2: Resolve migrations duplication
# ============================================
echo ""
echo "Resolving migrations duplication..."

if [ -d "tagslut/migrations" ] && [ -d "tagslut/storage/migrations" ]; then
    echo "Both migration directories exist:"
    echo "  tagslut/migrations: $(ls tagslut/migrations | wc -l) files"
    echo "  tagslut/storage/migrations: $(ls tagslut/storage/migrations 2>/dev/null | wc -l) files"
    
    echo ""
    echo "DECISION: Keep tagslut/storage/migrations (coupled to storage layer)"
    echo "          Delete tagslut/migrations (orphaned)"
    
    git rm -rf tagslut/migrations/
    
    # Update any imports
    grep -r "from tagslut.migrations import" tagslut/ tests/ --exclude-dir=__pycache__ || echo "No orphaned migration imports"
fi

# ============================================
# 4.3: Remove Flask or document it
# ============================================
echo ""
echo "Checking Flask usage..."

FLASK_IMPORTS=$(grep -r "import flask\|from flask import" tagslut/ --exclude-dir=__pycache__ 2>/dev/null | wc -l)

if [ "$FLASK_IMPORTS" -eq 0 ]; then
    echo "Flask is UNUSED in codebase"
    echo "Remove from pyproject.toml:"
    echo '  sed -i "/flask/d" pyproject.toml'
    echo ""
    read -p "Remove Flask dependency? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sed -i.bak '/flask/d' pyproject.toml
        echo "Flask removed from pyproject.toml"
    fi
else
    echo "Flask IS USED ($FLASK_IMPORTS imports found)"
    echo "Files using Flask:"
    grep -rl "import flask\|from flask import" tagslut/ --exclude-dir=__pycache__
    echo ""
    echo "MANUAL TASK: Document Flask usage in README.md or remove code"
fi

# ============================================
# 4.4: Choose Click vs Typer
# ============================================
echo ""
echo "Checking Click vs Typer usage..."

CLICK_USAGE=$(grep -r "@click\." tagslut/ --exclude-dir=__pycache__ 2>/dev/null | wc -l)
TYPER_USAGE=$(grep -r "import typer\|from typer import" tagslut/ --exclude-dir=__pycache__ 2>/dev/null | wc -l)

echo "Click usage: $CLICK_USAGE occurrences"
echo "Typer usage: $TYPER_USAGE occurrences"

if [ "$TYPER_USAGE" -eq 0 ]; then
    echo "Typer is UNUSED - removing..."
    sed -i.bak '/typer/d' pyproject.toml
    echo "✅ Typer removed from pyproject.toml"
else
    echo "⚠️  Typer IS USED ($TYPER_USAGE imports)"
    echo "MANUAL DECISION REQUIRED:"
    echo "  Option 1: Migrate Typer commands to Click"
    echo "  Option 2: Migrate Click commands to Typer"
    echo "  Option 3: Keep both (NOT RECOMMENDED)"
fi

# ============================================
# 4.5: Consolidate tools/ directories
# ============================================
echo ""
echo "Resolving tools/ directory collision..."

echo "Current tools directories:"
ls -ld */tools/ 2>/dev/null | awk '{print "  " $9}'
ls -ld tagslut/tools/ 2>/dev/null | awk '{print "  " $9}'
ls -ld tests/tools/ 2>/dev/null | awk '{print "  " $9}'

cat << 'TOOLS_PLAN'

TOOLS DIRECTORY PLAN:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
/tools/            → Rename to /bin/ (repo-level scripts)
tagslut/tools/     → Rename to tagslut/integrations/ (library code)
tests/tools/       → Delete if empty, else rename to tests/integration/

REASONING:
- /tools/ → /bin/: Standard Unix convention for executable scripts
- tagslut/tools/ → tagslut/integrations/: Clearer purpose (external tool integration)
- tests/tools/ → tests/integration/: Matches renamed module

EXECUTE:
  git mv tools bin
  git mv tagslut/tools tagslut/integrations
  # Update all imports: s/tagslut.tools/tagslut.integrations/g
  # Update README.md: s/tools\/get/bin\/get/g
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOOLS_PLAN

read -p "Execute tools/ consolidation? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Rename repo-level tools to bin
    if [ -d "tools" ]; then
        git mv tools bin
        echo "✅ Renamed /tools/ → /bin/"
        
        # Update README
        sed -i 's/tools\/get/bin\/get/g' README.md
    fi
    
    # Rename package-level tools to integrations
    if [ -d "tagslut/tools" ]; then
        git mv tagslut/tools tagslut/integrations
        echo "✅ Renamed tagslut/tools/ → tagslut/integrations/"
        
        # Find import updates needed
        grep -rl "from tagslut.tools import\|from tagslut import tools" tagslut/ tests/ scripts/ --exclude-dir=__pycache__ > /tmp/tools_imports.txt || true
        if [ -s /tmp/tools_imports.txt ]; then
            echo "Update these imports: s/tagslut.tools/tagslut.integrations/g"
            cat /tmp/tools_imports.txt
        fi
    fi
    
    # Handle tests/tools
    if [ -d "tests/tools" ]; then
        TOOLS_TEST_COUNT=$(find tests/tools -name "*.py" ! -name "__init__.py" | wc -l)
        if [ "$TOOLS_TEST_COUNT" -eq 0 ]; then
            git rm -rf tests/tools
            echo "✅ Deleted empty tests/tools/"
        else
            git mv tests/tools tests/integration
            echo "✅ Renamed tests/tools/ → tests/integration/"
        fi
    fi
fi

echo ""
echo "Phase 4 complete!"
echo "Run verify_phase4.sh to validate"
```


### Phase 4 Verification

```bash
#!/bin/bash
# verify_phase4.sh

echo "=== Verifying Phase 4 ==="

# 1. Zones module created
if [ -d "tagslut/zones" ] && [ -f "tagslut/zones/__init__.py" ] && [ -f "tagslut/zones/base.py" ]; then
    echo "✅ PASS: tagslut/zones/ module created"
else
    echo "❌ FAIL: tagslut/zones/ incomplete"
    exit 1
fi

# 2. core/zone_assignment.py moved
if [ ! -f "tagslut/core/zone_assignment.py" ] && [ -f "tagslut/zones/assignment.py" ]; then
    echo "✅ PASS: zone_assignment.py moved to zones/"
else
    echo "❌ FAIL: zone_assignment.py not moved"
    exit 1
fi

# 3. No duplicate migrations
if [ ! -d "tagslut/migrations" ]; then
    echo "✅ PASS: tagslut/migrations/ removed"
else
    echo "❌ FAIL: tagslut/migrations/ still exists"
    exit 1
fi

if [ -d "tagslut/storage/migrations" ]; then
    echo "✅ PASS: tagslut/storage/migrations/ kept"
else
    echo "⚠️  WARNING: tagslut/storage/migrations/ missing"
fi

# 4. Flask removed or documented
FLASK_IN_DEPS=$(grep -c "flask" pyproject.toml || echo 0)
FLASK_IN_CODE=$(grep -r "import flask\|from flask import" tagslut/ --exclude-dir=__pycache__ 2>/dev/null | wc -l)

if [ "$FLASK_IN_DEPS" -eq 0 ]; then
    echo "✅ PASS: Flask removed from dependencies"
elif [ "$FLASK_IN_CODE" -gt 0 ]; then
    echo "✅ PASS: Flask documented/used ($FLASK_IN_CODE usages)"
else
    echo "⚠️  WARNING: Flask in deps but unused"
fi

# 5. Typer removed or documented
TYPER_IN_DEPS=$(grep -c "typer" pyproject.toml || echo 0)
TYPER_IN_CODE=$(grep -r "import typer\|from typer import" tagslut/ --exclude-dir=__pycache__ 2>/dev/null | wc -l)

if [ "$TYPER_IN_DEPS" -eq 0 ] || [ "$TYPER_IN_CODE" -gt 0 ]; then
    echo "✅ PASS: Typer resolved"
else
    echo "⚠️  WARNING: Typer in deps but unused"
fi

# 6. Tools directories consolidated
TOOLS_COUNT=$(find . -type d -name "tools" -not -path "./.git/*" -not -path "./.venv/*" | wc -l)
if [ "$TOOLS_COUNT" -le 1 ]; then
    echo "✅ PASS: Tools directories consolidated"
else
    echo "⚠️  WARNING: $TOOLS_COUNT 'tools' directories still exist"
    find . -type d -name "tools" -not -path "./.git/*" -not -path "./.venv/*"
fi

# 7. Tests still pass
poetry run pytest tests/ -x -q
if [ $? -eq 0 ]; then
    echo "✅ PASS: All tests pass"
else
    echo "❌ FAIL: Tests broken"
    exit 1
fi

echo ""
echo "Phase 4 verification complete!"
```


***

## Phase 5: Scripts Promotion (1-2 hours)

**Risk Level:** Safe
**Rollback:** `git reset --hard <commit-before-phase5>`

```bash
#!/bin/bash
# phase5_scripts_promotion.sh

set -e

echo "=== Phase 5: Scripts Promotion ==="

# Identify large scripts
echo "Large scripts (> 10KB) suitable for promotion:"
find scripts/ -name "*.py" -size +10k -exec ls -lh {} \; | awk '{print $5 "\t" $9}'

# Create extraction plan
cat << 'EXTRACTION_PLAN'

SCRIPTS TO PROMOTE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. reassess_playlist_duration_unknowns_tokenless.py (38 KB)
   → tagslut/metadata/playlist_duration_resolver.py
   → Keep scripts/reassess_playlist_duration_unknowns_tokenless.py as thin CLI wrapper

2. extract_tracklists_from_links.py (30 KB)
   → tagslut/metadata/tracklist_extractor.py
   → Keep scripts/extract_tracklists_from_links.py as thin CLI wrapper

3. dj_yes_transcode.py (20 KB)
   → tagslut/transcoding/dj_transcode.py
   → scripts/dj_yes_transcode.py becomes CLI wrapper

4. build_duration_refs_from_isrc_providers.py (14 KB)
   → tagslut/metadata/duration_reference_builder.py
   → Keep scripts/ version as wrapper

EXTRACTION PATTERN:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OLD (scripts/example.py):
  #!/usr/bin/env python3
  import sys
  # 500 lines of business logic
  def main():
      # CLI arg parsing
      # Business logic
  if __name__ == '__main__':
      main()

NEW STRUCTURE:

tagslut/module/feature.py:
  """Business logic only, zero CLI concerns."""
  def process_data(input_path, options):
      # Core logic extracted
      return result

scripts/example.py:
  #!/usr/bin/env python3
  """Thin CLI wrapper for tagslut.module.feature."""
  import click
  from tagslut.module.feature import process_data
  
  @click.command()
  @click.argument('input_path')
  def main(input_path):
      result = process_data(input_path, {})
      print(result)
  
  if __name__ == '__main__':
      main()

EXTRACTION_PLAN

# Create transcoding module if needed
if [ ! -d "tagslut/transcoding" ]; then
    echo "Creating tagslut/transcoding/ module..."
    mkdir -p tagslut/transcoding
    touch tagslut/transcoding/__init__.py
fi

# Example: Extract one script (manual process)
cat << 'EXAMPLE'

EXAMPLE EXTRACTION (reassess_playlist_duration_unknowns_tokenless.py):

1. Create tagslut/metadata/playlist_duration_resolver.py
2. Extract all functions/classes except main() and CLI parsing
3. Make functions pure: take parameters, return results (no sys.exit, no print)
4. Move script-specific imports into tagslut module
5. Rewrite scripts/ version:

   #!/usr/bin/env python3
   """CLI wrapper for playlist duration resolution."""
   import click
   from pathlib import Path
   from tagslut.metadata.playlist_duration_resolver import (
       resolve_durations,
       DurationResolverConfig
   )
   
   @click.command()
   @click.argument('playlist_file', type=click.Path(exists=True))
   @click.option('--tokenless', is_flag=True)
   def main(playlist_file, tokenless):
       """Resolve unknown durations in playlist."""
       config = DurationResolverConfig(tokenless=tokenless)
       result = resolve_durations(Path(playlist_file), config)
       click.echo(f"Resolved: {result.resolved_count}")
       click.echo(f"Failed: {result.failed_count}")
   
   if __name__ == '__main__':
       main()

6. Create tests/metadata/test_playlist_duration_resolver.py
7. Test library code independently of CLI

EXAMPLE

echo ""
echo "MANUAL EXTRACTION REQUIRED"
echo "Follow the pattern above for each large script"
echo ""
echo "After each extraction:"
echo "  1. Create library module with business logic"
echo "  2. Create tests for library module"
echo "  3. Rewrite script as thin wrapper"
echo "  4. Verify: python scripts/<name>.py <args>"
echo "  5. Verify: poetry run pytest tests/metadata/test_<name>.py"
```


### Phase 5 Verification

```bash
#!/bin/bash
# verify_phase5.sh

echo "=== Verifying Phase 5 ==="

# Check new modules created
echo "New library modules:"
if [ -d "tagslut/transcoding" ]; then
    echo "  ✅ tagslut/transcoding/"
fi

METADATA_MODULES=$(find tagslut/metadata -name "*.py" ! -name "__init__.py" | wc -l)
echo "  tagslut/metadata/: $METADATA_MODULES modules"

# Check that scripts are now thin
echo ""
echo "Scripts analysis (should be < 5KB after extraction):"
for script in scripts/dj_yes_transcode.py scripts/reassess_playlist_duration_unknowns_tokenless.py scripts/extract_tracklists_from_links.py; do
    if [ -f "$script" ]; then
        SIZE=$(wc -c < "$script")
        SIZE_KB=$((SIZE / 1024))
        if [ "$SIZE" -lt 5120 ]; then
            echo "  ✅ $script: ${SIZE_KB}KB (thin wrapper)"
        else
            echo "  ⚠️  $script: ${SIZE_KB}KB (still large)"
        fi
    fi
done

# Check that new library code has tests
echo ""
echo "Test coverage for promoted code:"
if [ -d "tests/metadata" ]; then
    TEST_COUNT=$(find tests/metadata -name "test_*.py" | wc -l)
    echo "  tests/metadata/: $TEST_COUNT test files"
fi

if [ -d "tests/transcoding" ]; then
    TEST_COUNT=$(find tests/transcoding -name "test_*.py" | wc -l)
    echo "  tests/transcoding/: $TEST_COUNT test files"
fi

# Run all tests
poetry run pytest tests/ -x -q
if [ $? -eq 0 ]; then
    echo "✅ PASS: All tests pass"
else
    echo "❌ FAIL: Tests broken"
    exit 1
fi

echo ""
echo "Phase 5 verification complete!"
```


***

## Phase 6: Provider/Plugin System (Design Only)

**Risk Level:** N/A (Design documentation only)
**Implementation:** Future work

```bash
#!/bin/bash
# phase6_provider_system_design.sh

cat << 'DESIGN'
=== Phase 6: Provider/Plugin System (Design) ===

CURRENT STATE:
- Beatport/Tidal/Deezer logic hardcoded throughout codebase
- No abstraction layer for music service providers
- Adding new provider requires changes across multiple files

TARGET ARCHITECTURE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

tagslut/providers/
├── __init__.py           # Registry and discovery
├── base.py               # Abstract BaseProvider
├── beatport.py           # Beatport implementation
├── tidal.py              # Tidal implementation
├── deezer.py             # Deezer implementation
└── registry.py           # Provider registration system

PROVIDER INTERFACE:

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pydantic import BaseModel

class TrackMetadata(BaseModel):
    """Normalized track metadata."""
    isrc: str
    title: str
    artist: str
    duration_ms: int
    # ... standard fields

class BaseProvider(ABC):
    """Abstract music service provider."""
    
    @abstractmethod
    def name(self) -> str:
        """Provider name (beatport, tidal, deezer)."""
        pass
    
    @abstractmethod
    def requires_auth(self) -> bool:
        """Whether provider needs authentication."""
        pass
    
    @abstractmethod
    async def search_by_isrc(self, isrc: str) -> Optional[TrackMetadata]:
        """Look up track by ISRC."""
        pass
    
    @abstractmethod
    async def search_by_metadata(self, artist: str, title: str) -> list[TrackMetadata]:
        """Search by artist/title."""
        pass
    
    @abstractmethod
    def rate_limit_delay(self) -> float:
        """Delay between requests (seconds)."""
        pass

REGISTRY PATTERN:

# tagslut/providers/registry.py
_providers: Dict[str, type[BaseProvider]] = {}

def register(name: str):
    """Decorator to register a provider."""
    def decorator(cls):
        _providers[name] = cls
        return cls
    return decorator

def get_provider(name: str) -> BaseProvider:
    """Get provider instance by name."""
    if name not in _providers:
        raise ValueError(f"Unknown provider: {name}")
    return _providers[name]()

def list_providers() -> list[str]:
    """List all registered providers."""
    return list(_providers.keys())

# tagslut/providers/beatport.py
from tagslut.providers.base import BaseProvider
from tagslut.providers.registry import register

@register('beatport')
class BeatportProvider(BaseProvider):
    def name(self) -> str:
        return 'beatport'
    
    async def search_by_isrc(self, isrc: str) -> Optional[TrackMetadata]:
        # Implementation
        pass

USAGE:

from tagslut.providers.registry import get_provider

provider = get_provider('beatport')
track = await provider.search_by_isrc('USRC12345678')

MIGRATION STRATEGY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase 6.1: Create provider infrastructure
  - Create tagslut/providers/ module
  - Define BaseProvider abstract class
  - Implement registry system
  - Write tests for registry

Phase 6.2: Extract Beatport provider
  - Find all Beatport-specific code
  - Implement BeatportProvider
  - Register provider
  - Migrate calling code to use registry

Phase 6.3: Extract Tidal provider
  - Same pattern as Beatport

Phase 6.4: Extract Deezer provider
  - Same pattern as Beatport

Phase 6.5: Add provider CLI
  - tagslut providers list
  - tagslut providers test <name>
  - tagslut providers search <name> <isrc>

BENEFITS:
✅ New providers added without touching existing code
✅ Providers can be tested in isolation
✅ Provider-specific logic centralized
✅ Easy to add rate limiting, caching, auth per provider
✅ CLI can dynamically discover providers

DESIGN

cat > docs/PROVIDER_SYSTEM_DESIGN.md << 'DOC'
# Provider System Design

## Overview

A plugin architecture for music service integrations (Beatport, Tidal, Deezer, etc.).

## Goals

1. **Extensibility**: Add new providers without modifying core code
2. **Testability**: Each provider can be tested in isolation
3. **Consistency**: All providers implement the same interface
4. **Discoverability**: CLI can list and test providers dynamically

## Architecture

See phase6_provider_system_design.sh for full specification.

## Implementation Status

- [ ] Phase 6.1: Provider infrastructure
- [ ] Phase 6.2: Beatport provider
- [ ] Phase 6.3: Tidal provider
- [ ] Phase 6.4: Deezer provider
- [ ] Phase 6.5: Provider CLI commands

## Timeline

Target: Q3 2026 (after Phases 0-5 complete)
DOC

echo "Provider system design written to docs/PROVIDER_SYSTEM_DESIGN.md"
```


***

## Complete Execution Order

```bash
#!/bin/bash
# execute_all_phases.sh

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        TAGSLUT RESTRUCTURING - COMPLETE EXECUTION         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Phase 0: MANDATORY FIRST
echo "➤ PHASE 0: Dedupe Eradication (MANDATORY FIRST)"
bash phase0_dedupe_eradication.sh
bash verify_phase0.sh
git add -A
git commit -m "Phase 0: Complete dedupe eradication"
echo "✅ Phase 0 complete"
echo ""

# Phase 1: Quick wins
echo "➤ PHASE 1: Quick Wins"
bash phase1_quick_wins.sh
bash verify_phase1.sh
git add -A
git commit -m "Phase 1: Quick structural wins"
echo "✅ Phase 1 complete"
echo ""

# Phase 2: CLI evacuation (manual-heavy)
echo "➤ PHASE 2: CLI Evacuation (MANUAL INTENSIVE)"
echo "⚠️  This phase requires manual extraction"
bash phase2_analyze_cli.sh
echo "Follow phase2_extract_commands.sh instructions"
echo "After manual extraction, run verify_phase2.sh"
read -p "Press Enter when Phase 2 manual work is complete..."
bash verify_phase2.sh
git add -A
git commit -m "Phase 2: CLI command evacuation to commands/"
echo "✅ Phase 2 complete"
echo ""

# Phase 3: Decision consolidation
echo "➤ PHASE 3: Decision Logic Consolidation"
bash phase3_consolidate_decisions.sh
echo "Follow manual merge instructions"
read -p "Press Enter when Phase 3 manual work is complete..."
bash verify_phase3.sh
git add -A
git commit -m "Phase 3: Consolidate decision logic"
echo "✅ Phase 3 complete"
echo ""

# Phase 4: Architecture foundations
echo "➤ PHASE 4: Architecture Foundations"
bash phase4_architecture_foundations.sh
bash verify_phase4.sh
git add -A
git commit -m "Phase 4: Architecture foundations (zones, tools, migrations)"
echo "✅ Phase 4 complete"
echo ""

# Phase 5: Scripts promotion
echo "➤ PHASE 5: Scripts Promotion"
bash phase5_scripts_promotion.sh
echo "Follow manual extraction pattern"
read -p "Press Enter when Phase 5 manual work is complete..."
bash verify_phase5.sh
git add -A
git commit -m "Phase 5: Promote scripts to library modules"
echo "✅ Phase 5 complete"
echo ""

# Phase 6: Design only
echo "➤ PHASE 6: Provider System Design (Documentation Only)"
bash phase6_provider_system_design.sh
git add docs/PROVIDER_SYSTEM_DESIGN.md
git commit -m "Phase 6: Provider system design documentation"
echo "✅ Phase 6 complete"
echo ""

echo "╔════════════════════════════════════════════════════════════╗"
echo "║              ALL PHASES COMPLETE                           ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Final verification:"
poetry run pytest tests/ -x
poetry run tagslut --help
echo ""
echo "Repository restructuring complete! 🎉"
```


***

## Summary: What Gets Fixed

| Issue | Phase | Solution |
| :-- | :-- | :-- |
| `dedupe` legacy naming | 0 | Complete eradication — remove entrypoints, tests, warnings |
| `cli/main.py` (113KB) | 2 | Extract to `commands/*.py`, target < 500 bytes |
| `integrity_scanner.py` floating | 1 | Move to `core/scanner.py` |
| Three-way `tools/` collision | 4 | `/tools/` → `/bin/`, `tagslut/tools/` → `tagslut/integrations/` |
| Decision logic split | 3 | Consolidate into `decide/planner.py` |
| Duplicate migrations | 4 | Delete `tagslut/migrations/`, keep `storage/migrations/` |
| No zones module | 4 | Create `tagslut/zones/` with `base.py` + `assignment.py` |
| Dual pyproject.toml deps | 1 | Remove `[tool.poetry.dependencies]` block |
| Mixed Click/Typer | 4 | Remove Typer (unused) |
| Vestigial Flask | 4 | Remove or document (likely unused) |
| Large scripts | 5 | Extract to library modules, make scripts thin wrappers |
| Phase-numbered tests | 1 | Rename to describe functionality |
| Legacy importable | 1 | Delete `tagslut/legacy/` |

**Total Estimated Time:** 7-10 hours (Phases 0-5)
**Phases 2, 3, 5 require manual code work** — automation is limited to setup/verification.


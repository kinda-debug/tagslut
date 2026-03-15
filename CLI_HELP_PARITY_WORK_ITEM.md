# CLI Help Text Parity Gap — Work Item

**Date:** March 15, 2026  
**Source:** Prompt 2 audit (Codex CLI help verification)  
**Status:** Ready for implementation  
**Priority:** High (Task 1.4 in Phase 1 closure)

---

## Current State (Verified)

### tools/get --help ✅ CORRECT
- `--dj` clearly marked as `[LEGACY] deprecated`
- References 4-stage pipeline and docs/DJ_WORKFLOW.md
- **No action needed**

### tagslut mp3 --help ⚠️ INCOMPLETE
- Commands present: `build`, `reconcile` ✓
- Missing: Stage context, pipeline sequencing
- Current text: "Build and reconcile MP3 derivative assets."
- Problem: Doesn't explain this is **Stage 1 of the DJ 4-stage pipeline**

### tagslut dj --help ⚠️ INCOMPLETE
- Subcommands present: `admit`, `backfill`, `validate`, `xml` ✓
- Missing: Stage numbers, pipeline flow
- Problem: Doesn't explain this is **Stages 2–4 of the DJ 4-stage pipeline**

---

## Gap Analysis

### Gap 1: Stage Context Missing from mp3 Help

**README.md says:**
```
Stage 1: tagslut mp3 reconcile --db <DB> --mp3-root <DJ_ROOT> --execute
  — Establish durable MP3 asset state
```

**Current help says:**
```
Build and reconcile MP3 derivative assets.
```

**Operator Experience:**
- User runs `tagslut mp3 --help`
- Sees commands but no context
- Doesn't know this is Stage 1 of a 4-stage workflow
- May use it incorrectly or skip it

---

### Gap 2: Stage Sequencing Missing from dj Help

**README.md says:**
```
Stage 2: tagslut dj backfill   --db <DB>
Stage 3: tagslut dj validate   --db <DB>
Stage 4: tagslut dj xml emit   --db <DB> --out rekordbox.xml
         tagslut dj xml patch  --db <DB> --out rekordbox_v2.xml
```

**Current help says:**
```
admit
backfill
validate
xml
```

**Operator Experience:**
- User sees 4 subcommands
- Doesn't know correct execution order
- Doesn't know which are required vs optional
- May guess wrong sequence

---

### Gap 3: No Cross-Reference Between mp3 and dj

**README describes:**
```
mp3 → dj → xml
```

**Help text:**
- `tagslut mp3` doesn't mention "next step is dj"
- `tagslut dj` doesn't mention "prerequisite is mp3"

**Operator Experience:**
- May skip mp3 stage
- May run dj stages without mp3 state
- Silent failures

---

## Required Changes

### Change 1: Update `tagslut mp3` Help Text

**Location:** tagslut/cli/commands/mp3.py (or similar)

**Current:**
```python
help="Build and reconcile MP3 derivative assets."
```

**Replace with:**
```python
help="""
Build and reconcile MP3 derivative assets.

Part of the 4-stage DJ pipeline:
  Stage 1 (mp3):  register/reconcile MP3 derivatives
  Stage 2 (dj):   admit tracks to DJ library
  Stage 3 (dj):   validate DJ library state
  Stage 4 (dj):   emit or patch Rekordbox XML

See: tagslut dj --help (Stages 2–4)
Docs: docs/DJ_WORKFLOW.md
"""
```

**Also add to subcommand help:**

Under `build` subcommand:
```python
help="Build (transcode) MP3s from canonical FLAC masters. Stage 1a of DJ pipeline."
```

Under `reconcile` subcommand:
```python
help="Reconcile existing MP3 directory with database. Stage 1b of DJ pipeline. Prerequisite: Stage 2 (dj backfill)."
```

---

### Change 2: Update `tagslut dj` Help Text

**Location:** tagslut/cli/commands/dj.py (or similar)

**Current:**
```python
help="DJ library operations."
```

**Replace with:**
```python
help="""
DJ library operations (Stages 2–4 of the 4-stage pipeline).

Stages:
  Stage 2: admit   → Select tracks for DJ library
           backfill → Auto-admit verified MP3s
           validate → Verify DJ library state
  Stage 3: xml emit → Generate Rekordbox XML
           xml patch → Update prior XML after changes

Prerequisite: Stage 1 (tagslut mp3 reconcile)

See: docs/DJ_WORKFLOW.md
"""
```

**Also add to subcommand help:**

Under `admit` subcommand:
```python
help="Admit individual track to DJ library. Stage 2a."
```

Under `backfill` subcommand:
```python
help="Auto-admit all verified MP3s to DJ library. Stage 2b (idempotent)."
```

Under `validate` subcommand:
```python
help="Validate DJ library state (files, metadata, consistency). Stage 2c."
```

Under `xml` subcommand:
```python
help="Emit or patch Rekordbox XML. Stage 4. Requires: dj backfill + dj validate."
```

---

### Change 3: Add Example to Both

**In `tagslut mp3` help:**
```python
epilog="""
Examples:
  # Reconcile existing MP3 directory
  tagslut mp3 reconcile --db music_v3.db --mp3-root /path/to/dj_root

  # Build from FLAC masters
  tagslut mp3 build --db music_v3.db --master-root /path/to/flacs --dj-root /path/to/mp3s

Next: tagslut dj --help (Stages 2–4)
"""
```

**In `tagslut dj` help:**
```python
epilog="""
Example workflow:
  1. tagslut mp3 reconcile --db music_v3.db --mp3-root /path/to/dj_root
  2. tagslut dj backfill --db music_v3.db
  3. tagslut dj validate --db music_v3.db
  4. tagslut dj xml emit --db music_v3.db --out rekordbox.xml

Docs: docs/DJ_WORKFLOW.md
"""
```

---

## Verification Checklist

After implementing changes, verify:

```bash
# 1. Check help text includes stage context
tagslut mp3 --help | grep -i "stage"
tagslut dj --help | grep -i "stage"

# 2. Check cross-references work
tools/get --help | grep "DJ_WORKFLOW"
tagslut mp3 --help | grep "dj backfill"
tagslut dj --help | grep "mp3 reconcile"

# 3. Check examples are present
tagslut mp3 --help | grep -A3 "Examples"
tagslut dj --help | grep -A5 "Example"

# 4. Run actual help and verify readability
tagslut mp3 --help
tagslut dj --help
```

All checks should pass.

---

## Implementation Notes

- **No code logic changes** — only help text strings
- **Safe to do first** — impacts documentation only, not runtime behavior
- **PR scope:** single commit, isolated to CLI help strings
- **Review:** read help output in terminal, verify readability
- **Backward compatible:** existing operators see better docs, no behavior change

---

## Success Criteria

✅ `tagslut mp3 --help` mentions "Stage 1" and references `tagslut dj`  
✅ `tagslut dj --help` mentions "Stages 2–4" and references `tagslut mp3`  
✅ Both include example commands from docs/DJ_WORKFLOW.md  
✅ Cross-references are bidirectional (mp3 → dj, dj → mp3)  
✅ No operator confusion about pipeline flow  

---

## Ready for Codex

This is ready to hand to Codex as a focused task:

```
See: .codex/CODEX_PROMPTS.md Prompt 6 (Update CLI Help Text)

This work item provides exact file locations and text replacements.
Implement as single PR.
```

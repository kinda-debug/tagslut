# Codex prompt — repo root cleanup

Work from repo root. Do not recreate existing files.
Read `.git/logs/HEAD` (offset: -30) before starting.

## Goal

Remove all clutter from the repo root. After this task, root contains only:
standard Python project files, documentation, tooling config, and legitimate
first-class directories. Every other file is moved, archived, or deleted per
the instructions below.

---

## Step 1 — Verify repo state

Read `.git/logs/HEAD` (last 20 lines). Confirm branch is `dev`. If not, stop.

---

## Step 2 — Ensure target directories exist

Create if missing (do not empty if they already exist):
- `data/`
- `scripts/rekordbox/`
- `config/beets/`

---

## Step 3 — Move standalone scripts to `scripts/`

Move these files. Use `git mv` for tracked files. Skip any that do not exist.

```
audit_and_dedupe_pool.py         → scripts/
audit_xml.py                     → scripts/
build_rekordbox_xml_from_pool.py → scripts/rekordbox/
dedupe_against_pool.py           → scripts/
filter_spotify_against_db.py     → scripts/
rebuild_pool_library.py          → scripts/
rewrite_rekordbox_db_paths.py    → scripts/rekordbox/
rewrite_rekordbox_xml_paths.py   → scripts/rekordbox/
scrub_mp3_tags_keep_only.py      → scripts/
tree_rbx.js                      → scripts/rekordbox/
env_exports.sh                   → scripts/
make_bundle.sh                   → scripts/
sync_tokens_to_postman_env.sh    → scripts/
tagslut-supabase-check.sh        → scripts/
tagslut_rls_apply.sh             → scripts/
```

---

## Step 4 — Move `script.py` → `.github/prompts/`

`script.py` is a Codex prompt generator script. Read its content, then:
1. Extract the string passed to `dedent(...)` — that is the prompt body.
2. Write it to `.github/prompts/dj-seed-from-tree-rbx.md`.
3. `git rm script.py`

If the destination file already exists, skip extraction and just `git rm script.py`.

---

## Step 5 — Move the loose prompt file

```
"Implement an operator-authorized clean lossy pool builder for Rekordbox.md"
  → .github/prompts/clean-lossy-pool-builder.md
```

Use `git mv`. Rename: replace spaces with hyphens, lowercase.

---

## Step 6 — Move data files to `data/`

Use `git mv` for tracked files. Skip any that do not exist.

```
DJSSD.json                  → data/
DJUSB.json                  → data/
djusbinventory.json         → data/
Indie_spotify.json          → data/
Indie_spotify.removed.json  → data/
removed.json                → data/
"Untitled Playlist.m3u8"    → data/
```

---

## Step 7 — Move rekordbox output files to `artifacts/`

Use `git mv` for tracked files. Skip any that do not exist.

```
clean.json                                → artifacts/
pool_duplicates.jsonl                     → artifacts/
pool_invalid_files.jsonl                  → artifacts/
dedupe_against_pool_manifest.jsonl        → artifacts/
rekordbox_pool_healthy.xml                → artifacts/
rekordbox_pool_relinked_v2.xml            → artifacts/
rekordbox_pool_relinked_v3.xml            → artifacts/
rekordbox_pool_relinked_v3.unresolved.txt → artifacts/
log.txt                                   → artifacts/
logsspotiflac.rtf                         → artifacts/
onetaggeroutput.txt                       → artifacts/
WEIRD.m3u8                                → artifacts/
"files to move.m3u8"                      → artifacts/
```

Note on `WEIRD.m3u8`: 229-line file where every entry is the identical corrupt
path (`/Volumes/MUSIC/POOL_LIBRARY/WhoMadeWho/...` repeated). Broken diagnostic
output from a dedup/path-rewrite run, not an intentional playlist. Safe to archive.

---

## Step 8 — Move config directories

```
beets-flask-config/  →  config/beets/
```

If `config/beets/` already has content, merge: move all files from
`beets-flask-config/` into `config/beets/`, then `git rm -r beets-flask-config/`.
Otherwise `git mv beets-flask-config config/beets`.

---

## Step 9 — Merge `postman_README.md`

Check `postman/README.md`:
- Does not exist: `git mv postman_README.md postman/README.md`
- Exists: read `postman_README.md`, append its content to `postman/README.md`
  with a `\n---\n` separator, then `git rm postman_README.md`.

---

## Step 10 — Delete garbage files

These have no repo value. Check each exists before deleting.

```
flac.txt    — terminal session dump. git rm if tracked; rm if not.
```

For these, check if tracked before acting:
```
__pycache__/  — git rm -r if tracked; ignore if untracked (already gitignored)
.DS_Store     — git rm --cached if tracked; otherwise ignore
```

For `dist/`: do NOT delete. Check `.gitignore`. If `dist/` is already listed,
leave it. If not, add `dist/` as a new line in `.gitignore`.

---

## Step 11 — Handle nested git repos (PRINT WARNING, do not act)

The following contain their own `.git/` or are unaffiliated staging dirs.
Do not `git mv`, `git rm`, or touch them. Print this warning and move on:

```
WARNING: manual action required for these root items — not touched by this task:
  SpotiFLAC-Module-Version/  — nested git repo, re-home to ~/Projects/
  Qobuz-AppID-Secret-Tool/   — nested git repo, re-home to ~/Projects/
  tt/                        — tiddl staging dir, re-home outside repo
```

---

## Step 12 — Ambiguous playlist files

Both playlist files at root are corrupt/stale artifacts. Move to `artifacts/`
along with the Step 7 rekordbox outputs (already listed above).

---

## Step 13 — START_HERE files (PRINT ONLY)

Print:

```
NOTE: START_HERE.md and START_HERE.sh exist at root.
  If content duplicates README.md / Makefile, delete manually.
  Not acted on by this task.
```

---

## Step 14 — Update `.gitignore`

Ensure these patterns exist in `.gitignore`. Append any that are missing:

```
dist/
__pycache__/
*.pyc
.DS_Store
tag_hoard_out/
output/
diagnostics/
```

---

## Step 15 — Commit

```bash
git add -A
git commit -m "chore(root): relocate stray scripts, data, and prompts to canonical dirs"
```

---

## Step 16 — Verification

Run and print the output:

```bash
ls -1 *.py *.js *.sh *.json *.jsonl *.xml *.txt *.rtf *.m3u8 2>/dev/null \
  | grep -Ev '^(pyproject\.toml|poetry\.lock|uv\.lock)$'
```

Expected: empty or only the two ambiguous `.m3u8` files and `START_HERE.*`.
If any unexpected files remain, list them explicitly. Do not proceed further.

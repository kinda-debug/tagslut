# Codex Prompt: Sync docs/SCRIPT_SURFACE.md to live CLI tree

**Repo**: `kinda-debug/tagslut` | **Branch**: `dev`
**Save to**: `.github/prompts/sc-02-sync-script-surface.md`

---

## Context

`docs/SCRIPT_SURFACE.md` was last synced 2026-03-09. The live CLI tree has
grown significantly since then. The following command groups are registered in
`tagslut/cli/main.py` but are entirely absent from `SCRIPT_SURFACE.md`:

- `ops` (`run-move-plan`, `plan-dj-library-normalize`, `relink-dj-pool`,
  `writeback-canonical`)
- `provider` (`provider status`)
- `postman` (`postman ingest`)
- `library` (`library import-rekordbox`)
- `lexicon` (`lexicon import`, `lexicon import-playlists`)
- `master` (`master scan`)
- `v3` (`v3 migrate`, `v3 provenance show`)

Additionally, the doc describes `tools/get-sync` as "deprecated compatibility
alias for `tools/get`" — but `tools/get-sync` does not exist and was never
created. This entry should be removed.

The doc also still lists `ts-get`, `ts-enrich`, `ts-auth` shell functions as
primary entry points, but `tagslut get`, `tagslut auth`, and
`tagslut index enrich` are now the canonical surface.

---

## Grounding pass (stop and report if any fail)

1. Read `docs/SCRIPT_SURFACE.md` in full — confirm it does not already
   document `ops`, `provider`, `postman`, `library`, `lexicon`, `master`, `v3`.
2. Read `tagslut/cli/main.py` in full — confirm those seven groups are
   registered there.
3. Read `tagslut/cli/commands/ops.py` — extract command names and help strings
   for the `ops` group.
4. Read `tagslut/cli/commands/provider.py` — extract command names.
5. Read `tagslut/cli/commands/v3.py` — extract command names.
6. Read `tagslut/cli/commands/library.py` — extract command names.
7. Read `tagslut/cli/commands/lexicon.py` — extract command names.
8. Read `tagslut/cli/commands/master.py` — extract command names.
9. Read `tagslut/cli/commands/postman.py` — extract command names.
10. Confirm `tools/get-sync` does NOT exist.

If any grounding step fails, stop and report.

---

## Task

Edit `docs/SCRIPT_SURFACE.md` to:

### 1. Add missing command groups to the "Canonical Entry Points" section

Append entries 14–20 (renumber as needed) for:

- `tagslut ops ...` — internal operator utilities (move-plan execution, DJ
  library normalization, pool relinking, canonical writeback). Not
  operator-facing for normal download/intake workflows.
- `tagslut provider status` — check authentication and availability status
  for all configured metadata providers.
- `tagslut postman ingest` — import Postman collection data.
- `tagslut library import-rekordbox` — import a Rekordbox XML file into the
  library database.
- `tagslut lexicon import` / `tagslut lexicon import-playlists` — import
  Lexicon DJ data.
- `tagslut master scan` — scan the MASTER_LIBRARY root and register files.
- `tagslut v3 migrate` / `tagslut v3 provenance show` — database migration
  utilities and provenance inspection. Operator/maintenance use only.

Use the same format as existing entries: numbered, one-line `Role:`, then
bullet points for subcommands where relevant. Extract the actual subcommand
names from the grounding reads.

### 2. Remove the `tools/get-sync` entry

Under "Operational Wrappers (Active)", item 4 (`tools/get-sync`) should be
removed entirely. It is referenced nowhere and never existed as a file.

### 3. Update the `ts-get` / `ts-enrich` / `ts-auth` note

These shell functions still exist and are still valid shortcuts, but the doc
should make clear they wrap the canonical CLI. Update the relevant entries to
add a note: "Wraps `tagslut get` / `tagslut auth` / `tagslut index enrich`;
exists for operator convenience."

### 4. Update the sync datestamp in the comment at the top

Change `Synced 2026-03-09` to `Synced 2026-04-15`.

---

## Constraints

- Do not recreate any existing file.
- Do not rewrite sections that are already accurate.
- Edit in place using targeted `str_replace` / `edit_block` operations.
- Do not run any tests — this is a docs-only change.
- Verify each edit by reading the modified section back immediately after
  writing.

---

## Commit

```
docs(script-surface): sync to live CLI tree, add ops/provider/v3/library/lexicon/master/postman, remove phantom get-sync
```

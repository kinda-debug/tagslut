# feat-beets-sidecar — implement Beets sidecar package on branch feat/beets-sidecar

## Do not implement on dev

All work in this prompt must happen on a new branch:

```bash
cd /Users/georgeskhawam/Projects/tagslut
git checkout dev
git pull origin dev
git checkout -b feat/beets-sidecar
```

Do not merge or push to dev. Leave the branch for operator review.

---

## Context

The Beets sidecar research is complete. Three deliverable files exist in the repo
but are in an inconsistent state:

- `beets-flask-config/beets/beets_config.yaml` — old misnamed copy (delete)
- `beets-flask-config/beets/config.yaml` — correct location for the live config
- `docs/beets/BEETS_SIDECAR_PACKAGE.md` — correct location ✓
- `docs/beets/BEETS_CUSTOM_PLUGIN_STUBS.md` — correct location ✓
- `docs/beets/beets_config.yaml` — old misnamed copy in wrong dir (delete)

The `config.yaml` also has two known defects to fix before committing.

---

## Step 1 — Clean up misnamed duplicates

```bash
rm beets-flask-config/beets/beets_config.yaml
rm docs/beets/beets_config.yaml
```

Verify:

```bash
ls beets-flask-config/beets/
ls docs/beets/
```

Expected state after cleanup:
- `beets-flask-config/beets/config.yaml` — exists
- `beets-flask-config/beets/BEETS_CUSTOM_PLUGIN_STUBS.md` — may or may not exist (do not create)
- `docs/beets/BEETS_SIDECAR_PACKAGE.md` — exists
- `docs/beets/BEETS_CUSTOM_PLUGIN_STUBS.md` — exists

---

## Step 2 — Fix two defects in config.yaml

Edit `beets-flask-config/beets/config.yaml` with targeted changes only.
Do not rewrite the file. Make exactly these two edits:

### Fix 1 — Remove `amazon` from fetchart sources

Find:

```yaml
  sources:
    - filesystem
    - coverart
    - itunes
    - amazon
```

Replace with:

```yaml
  sources:
    - filesystem
    - coverart
    - itunes
```

### Fix 2 — Remove replaygain fields from zero plugin

Find the `zero:` block fields list. Remove these three lines:

```yaml
    - replaygain_track_gain
    - replaygain_track_peak
    - replaygain_album_gain
    - replaygain_album_peak
```

The zero fields list should contain only:

```yaml
  fields:
    - acoustid_id
    - encoder
    - encodedby
```

Rationale: in sidecar mode with `write: no`, zeroing replaygain in the DB but not
in files creates a divergence. These fields are managed by the `replaygain` plugin
directly when enabled.

---

## Step 3 — Install beets and the required plugins

Install into the project's Poetry environment:

```bash
cd /Users/georgeskhawam/Projects/tagslut
poetry add --group dev beets beets-beatport4 beetcamp
```

If Poetry is unavailable in the Codex environment, use pip with the venv:

```bash
.venv/bin/pip install beets beets-beatport4 beetcamp
```

Do not add `beets-xtractor` — it requires Essentia which is not available.

---

## Step 4 — Verify beets loads the config without errors

```bash
cd /Users/georgeskhawam/Projects/tagslut
BEETSDIR=beets-flask-config/beets poetry run beet version 2>&1
```

Expected: prints beets version and lists loaded plugins including `beatport4`,
`fetchart`, `embedart`, `zero`, `types`.

If any plugin fails to import, report the error and stop. Do not attempt to fix
plugin import errors by modifying the plugin source.

---

## Step 5 — Add pyproject.toml optional dependency group entry

Add `beets` as an optional dev dependency comment in `pyproject.toml` so it is
documented but not required for core tagslut usage. Only add if not already present.

Check first:

```bash
grep -n "beets" pyproject.toml
```

If absent, add under `[tool.poetry.group.dev.dependencies]`:

```toml
# Beets sidecar (optional, for browse/query layer)
beets = { version = ">=2.0", optional = true }
beets-beatport4 = { version = "*", optional = true }
beetcamp = { version = "*", optional = true }
```

---

## Step 6 — Commit

One commit per logical step:

```bash
git add beets-flask-config/ docs/beets/
git commit -m "chore(beets): clean up misnamed config duplicates"

git add beets-flask-config/beets/config.yaml
git commit -m "fix(beets): remove amazon from fetchart sources and replaygain from zero fields"

git add pyproject.toml poetry.lock
git commit -m "chore(deps): add beets sidecar plugins as optional dev dependencies"
```

---

## Constraints

- Do not merge to dev or main
- Do not modify any tagslut source files (`tagslut/`, `tests/`, `tools/`)
- Do not modify the DB or any volume paths
- Do not run the full test suite
- If `beet version` fails due to a missing system dependency (e.g. ffmpeg),
  note it in the commit message but do not block the commit
- Scope is strictly: config cleanup, two config fixes, dependency install,
  beet version check, pyproject update

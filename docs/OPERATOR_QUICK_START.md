# Operator Quick Start

## Daily Startup

Every time you work on tagslut, run this ONE command:

```bash
cd /Users/georgeskhawam/Projects/tagslut
source START_HERE.sh
```

This script:
- ✅ Activates Python virtual environment
- ✅ Loads all credentials from env_exports.sh
- ✅ Sets up core paths (TAGSLUT_DB, MASTER_LIBRARY, DJ_LIBRARY)
- ✅ Verifies database and volumes
- ✅ Shows you copy-paste ready commands

## Optional: Shell Alias

Add to your `~/.zshrc`:

```bash
alias tagslut-start="cd /Users/georgeskhawam/Projects/tagslut && source START_HERE.sh"
```

Then just run:

```bash
tagslut-start
```

## Common Commands After Startup

**Download a release:**

```bash
tools/get <beatport-or-tidal-url>
```

**Build DJ library:**

```bash
poetry run tagslut mp3 build --db "$TAGSLUT_DB" --dj-root "$DJ_LIBRARY" --execute
poetry run tagslut dj backfill --db "$TAGSLUT_DB"
poetry run tagslut dj validate --db "$TAGSLUT_DB"
poetry run tagslut dj xml emit --db "$TAGSLUT_DB" --out /Volumes/MUSIC/rekordbox_new.xml
```

**Check library stats:**

```bash
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*) FROM track_identity;"
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*) FROM mp3_asset;"
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*) FROM dj_admission;"
```

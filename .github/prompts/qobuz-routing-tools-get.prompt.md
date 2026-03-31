# Add Qobuz routing to tools/get

**COMMIT ALL CHANGES BEFORE EXITING. If you do not commit, the work is lost.**

**CRITICAL**: Only modify `tools/get`. Do not touch any Python files, migrations,
or other scripts.

---

## Goal

Add `qobuz.com` and `play.qobuz.com` URL routing to `tools/get`. When a Qobuz URL
is passed, the script should:

1. Call `rip url <url>` to download to `/Volumes/MUSIC/mdl/StreamripDownloads/`
2. Call `tagslut index register /Volumes/MUSIC/mdl/StreamripDownloads --source qobuz --execute`
3. Optionally run enrich if `--enrich` mode is active

---

## Changes

### 1. Add qobuz.com to the URL pattern matcher

Find the `while` loop that matches URLs against domain patterns:

```bash
http://*|https://*|*tidal.com*|*beatport.com*|*deezer.com*)
```

Add `*qobuz.com*` to the pattern:

```bash
http://*|https://*|*tidal.com*|*beatport.com*|*deezer.com*|*qobuz.com*)
```

### 2. Add Qobuz domain handler

After the `beatport.com` routing block and before the final fallback, add:

```bash
# Route Qobuz URLs to streamrip
if [[ "$URL" == *"qobuz.com"* ]]; then
    STREAMRIP_CMD="rip"
    if ! command -v "$STREAMRIP_CMD" >/dev/null 2>&1; then
        echo "Error: streamrip (rip) not found. Install with: pip install streamrip" >&2
        exit 1
    fi

    cd "$REPO_ROOT"
    echo "Downloading via streamrip: $URL"
    "$STREAMRIP_CMD" url "$URL"

    STREAMRIP_EXIT=$?
    if [[ $STREAMRIP_EXIT -ne 0 ]]; then
        echo "Error: streamrip exited with code $STREAMRIP_EXIT" >&2
        exit $STREAMRIP_EXIT
    fi

    STREAMRIP_ROOT="/Volumes/MUSIC/mdl/StreamripDownloads"
    echo "Registering downloads..."
    poetry run python -m tagslut index register "$STREAMRIP_ROOT" --source qobuz --execute

    if [[ "$MODE" == "enrich" ]]; then
        echo "Enriching..."
        poetry run python -m tagslut index enrich \
            --db "$TAGSLUT_DB" \
            --path "${STREAMRIP_ROOT}/%" \
            --zones staging \
            --execute
    fi

    exit 0
fi
```

### 3. Update the usage() function

Add Qobuz to the routing roots section:

```
  qobuz.com   → streamrip (rip url) + auto-register
```

And add to the supported domains list in the error message at the bottom of the
unrecognized domain block:

```
Supported domains: tidal.com, beatport.com, deezer.com, qobuz.com
```

---

## Verification

```bash
# Should show download starting (don't need to complete)
tools/get https://play.qobuz.com/album/j0x0ilcsey5k5 --dry-run 2>&1 | head -5
# Should route correctly
bash -n tools/get && echo "syntax ok"
```

---

## Commit message

```
feat(tools): add Qobuz URL routing via streamrip in tools/get
```

# Playlist Sync Tool

**Quick one-step tool to download a playlist, skip existing tracks, and generate M3U.**

## Usage

```bash
# Basic usage
tools/playlist-sync https://www.beatport.com/playlist/xyz/123456

# With custom M3U output
tools/playlist-sync https://www.beatport.com/playlist/xyz/123456 --output my-playlist.m3u

# With custom database
tools/playlist-sync https://tidal.com/browse/playlist/abc --db ~/my-music.db --output playlist.m3u
```

## What It Does

1. **Downloads playlist** using `tools/get`
   - Beatport → `~/Downloads/bpdl/`
   - Tidal → `~/Downloads/tiddl/`

2. **Checks database** for existing tracks
   - Computes SHA256 for each file
   - Identifies duplicates (already in library)
   - Skips downloading those again

3. **Registers new files** in inventory
   - Tracks download source (bpdl/tidal)
   - Records download date
   - Stores original path

4. **Generates M3U** with all tracks
   - Includes metadata (artist, title, duration)
   - Ready to import into Roon, Serato, Rekordbox, etc.

## Example Output

```
======================================================================
PLAYLIST SYNC
======================================================================
Source: BPDL
Database: /Users/you/.config/dedupe/music.db

📥 Downloading bpdl playlist...
✓ Playlist downloaded

🔎 Scanning /Users/you/Downloads/bpdl...
✓ Found 25 tracks

🔍 Checking for duplicates...
  [1/25] ⏭  Track 1.flac (already exists)
  [2/25] ✓ Track 2.flac (new)
  [3/25] ✓ Track 3.flac (new)
  ...

======================================================================
SUMMARY
======================================================================
Total tracks:     25
New:              15
Already exist:    10

📝 Registering 15 new files...
✓ Registered 15 files
  Registered: 15

📋 Generating M3U playlist...
✓ Created: /Users/you/playlist-20260203-120000.m3u
  25 tracks

======================================================================
✅ DONE
======================================================================

M3U file ready: /Users/you/playlist-20260203-120000.m3u
Import into Roon or your DJ software
```

## Options

| Option | Description |
|--------|-------------|
| `URL` | Beatport or Tidal playlist/album URL (required) |
| `--output FILE` | Output M3U filename (default: `playlist-TIMESTAMP.m3u`) |
| `--db PATH` | Custom database path (default: `$DEDUPE_DB` or `~/.config/dedupe/music.db`) |

## Supported URLs

**Beatport**:
- Playlists: `https://www.beatport.com/playlist/name/123456`
- Albums: `https://www.beatport.com/release/name/123456`
- Tracks: `https://www.beatport.com/track/name/123456`
- Charts: `https://www.beatport.com/chart/name/123456`

**Tidal**:
- Playlists: `https://tidal.com/browse/playlist/abc123`
- Albums: `https://tidal.com/browse/album/def456`
- Artists: `https://tidal.com/browse/artist/ghi789`

## Workflow

### Typical Usage

```bash
# 1. Sync a Beatport playlist
tools/playlist-sync https://www.beatport.com/playlist/summer-hits/789123

# 2. Opens M3U automatically in your DJ software
# (Or copy the .m3u file to your Roon/Rekordbox/Serato library)

# 3. All new tracks already in database
# (No need to re-register, already done!)
```

### Multi-Playlist Sync

```bash
# Download and sync multiple playlists
tools/playlist-sync https://www.beatport.com/playlist/house/111 --output house.m3u
tools/playlist-sync https://www.beatport.com/playlist/techno/222 --output techno.m3u
tools/playlist-sync https://tidal.com/browse/playlist/ambient/333 --output ambient.m3u

# All tracks registered, all M3Us ready
```

### Integration with Roon

```bash
# 1. Sync playlist
tools/playlist-sync https://www.beatport.com/playlist/xyz/123

# 2. Import M3U into Roon
# Roon → Library → Playlists → Import → playlist-TIMESTAMP.m3u

# 3. Roon automatically finds the tracks (by path in database)
```

## How It Avoids Re-Downloads

The tool uses **SHA256 checksums** to detect duplicates:

```
1. Compute SHA256 for each downloaded file
2. Query database: "Does this SHA256 already exist?"
3. If YES → Skip (file already in library)
4. If NO → Register as new

Result: Never download the same file twice
```

This is **smarter than filename matching** because:
- Handles the same song in different mixes
- Detects bitrate/format changes
- Works across multiple download sources

## Advanced Usage

### Dry-Run (Check Without Downloading)

```bash
# Just check, don't download
dedupe mgmt check ~/Downloads/bpdl --source bpdl

# See what's unique vs. duplicate
```

### Use Custom Database Per Project

```bash
# Project A
tools/playlist-sync https://www.beatport.com/playlist/set-a/123 \
  --db ~/dj-sets/set-a.db \
  --output set-a.m3u

# Project B (separate library)
tools/playlist-sync https://www.beatport.com/playlist/set-b/456 \
  --db ~/dj-sets/set-b.db \
  --output set-b.m3u
```

## Performance

| Task | Time |
|------|------|
| Download 25-track playlist | ~30s (depends on connection) |
| Check for duplicates | ~100ms |
| Register new files | ~500ms (50 new tracks) |
| Generate M3U | ~500ms |
| **Total** | ~31 seconds |

## Troubleshooting

### "No FLAC files found"
The download may have failed. Check:
```bash
# Verify download directory exists
ls ~/Downloads/bpdl/  # for Beatport
ls ~/Downloads/tiddl/  # for Tidal

# If empty, try downloading manually first
tools/get <URL>
```

### "Database not found"
Set the `$DEDUPE_DB` environment variable:
```bash
export DEDUPE_DB=/path/to/music.db
tools/playlist-sync <URL>
```

### "Connection error"
Check your internet connection and try again:
```bash
tools/playlist-sync <URL> --output my-playlist.m3u
```

## What's Next?

After syncing:
1. ✅ Files downloaded
2. ✅ Duplicates skipped
3. ✅ New tracks registered
4. ✅ M3U generated

**Ready to**:
- Import M3U into DJ software (Rekordbox, Serato, Traktor)
- Import into Roon for discovery
- Move files to canonical library (`dedupe recovery --move`, Phase 2)
- Tag files with Yate for detailed metadata

## One-Liner

```bash
tools/playlist-sync https://www.beatport.com/playlist/your-playlist/12345 && \
  open playlist-*.m3u  # macOS: opens in DJ software
```

Linux/Windows:
```bash
tools/playlist-sync https://www.beatport.com/playlist/your-playlist/12345 && \
  cat playlist-*.m3u  # shows the M3U path
```

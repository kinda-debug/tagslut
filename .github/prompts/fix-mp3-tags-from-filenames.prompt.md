# fix-mp3-tags-from-filenames — Write missing ID3 tags to DJ_LIBRARY MP3s from filename

## Do not recreate existing files. Do not modify files not listed in scope.
## Do not touch any migration, schema, CLI registration, or enrichment code.

---

## Context

`/Volumes/MUSIC/DJ_LIBRARY` contains ~2,004 MP3 files. ~1,473 have no readable
ID3 tags (artist/title both missing) but the filename encodes full metadata.

Two filename schemas are present:

**Schema A — tiddl** (~1,304 files):
`Artist – (Year) Album – NN Title.mp3`
Examples:
  `Kölsch – (2025) KINEMA – 02 Nacht Und Träume.mp3`
  `The Magician, Lindstrøm – (2025) Sirius Syntoms – 01 Sirius Syntoms.mp3`
  `Kölsch – (2015) 1983 – 09 Die Anderen.mp3`

Parse with:
```python
re.match(
    r'^(?P<artist>.+?) – \((?P<year>\d{4})\) (?P<album>.+?) – (?P<track>\d+) (?P<title>.+)$',
    stem
)
```

**Schema B — flat** (~169 files):
`Artist - Title.mp3` or `Artist - Title (BPM).mp3`
Examples:
  `Juana Molina - intringulado.mp3`
  `New Order - Blue Monday (2011 Total Version) (130).mp3`

Parse with:
```python
re.match(r'^(?P<artist>.+?) - (?P<title>.+)$', stem)
```
Strip trailing ` (NNN)` BPM suffix from title if present:
```python
re.sub(r'\s*\(\d{2,3}\)\s*$', '', title)
```

---

## Scope

### New file: `tagslut/exec/fix_mp3_tags_from_filenames.py`

Standalone script (also `python -m tagslut.exec.fix_mp3_tags_from_filenames`).

CLI:
```
  --root PATH     directory to scan recursively (default: /Volumes/MUSIC/DJ_LIBRARY)
  --execute       actually write tags (default: dry-run)
  --verbose       print one line per file
```

Implementation:

1. Walk `--root` recursively for `*.mp3` files (case-insensitive).
2. For each file, read existing ID3 tags using `mutagen.id3.ID3`.
3. Skip the file if BOTH `TPE1` (artist) AND `TIT2` (title) are already non-empty.
4. Try Schema A regex on `Path(f).stem`. If match:
   - artist = match['artist']
   - title  = match['title']
   - album  = match['album']
   - year   = match['year']
   - track  = match['track'] (integer string)
5. Else try Schema B regex. If match:
   - artist = match['artist']
   - title  = match['title'].strip(), with BPM suffix stripped
   - album  = None
   - year   = None
   - track  = None
6. If neither schema matches: log as unparseable, skip.
7. In `--execute` mode: write tags using `mutagen.id3`:
   - TPE1 (artist), TIT2 (title) — always
   - TALB (album) — if parsed
   - TDRC (year) — if parsed
   - TRCK (track number) — if parsed
   - Use `mutagen.id3.ID3()` with `v2_version=3` for compatibility.
   - Call `tags.save()` after writing.
8. Print summary: scanned, already tagged (skipped), schema A fixed,
   schema B fixed, unparseable (skipped).

Use `mutagen.id3.ID3` with `ID3NoHeaderError` handling (create tags if missing):
```python
try:
    tags = mutagen.id3.ID3(path)
except mutagen.id3.ID3NoHeaderError:
    tags = mutagen.id3.ID3()
```

---

## Tests

Add `tests/exec/test_fix_mp3_tags_from_filenames.py`:

- Test: tiddl-schema filename → correct artist, title, album, year, track parsed
- Test: flat-schema filename → correct artist and title, BPM suffix stripped
- Test: file already has both artist+title tags → skipped
- Test: dry-run does not write any tags
- Test: unparseable filename → skipped, counted in summary
- Mock `mutagen.id3.ID3` and `mutagen.id3.ID3NoHeaderError`

Run: `poetry run pytest tests/exec/test_fix_mp3_tags_from_filenames.py -v`

---

## Commit

```
git add -A
git commit -m "feat(exec): add fix_mp3_tags_from_filenames — write ID3 tags from tiddl/flat filename schemas"
```

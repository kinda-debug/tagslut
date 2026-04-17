# Download Strategy: Best-Available-Source

<!-- Status: Active. Supersedes the TIDAL-First document from 2026-03-21. -->
<!-- Last updated: 2026-03-29 -->
<!-- Owner: operator -->

---

## Core philosophy

**Audio source and metadata authority are independent decisions.**

The primary audio source is the best source that has the track. For most electronic
music this is TIDAL (via tiddl). For tracks exclusive to Beatport — white-label,
promo, label exclusives — Beatport is the only viable source. These situations are
permanent exceptions, not failures to recover from.

Downstream DJ lineage is lossless-first: canonical lossless audio stays canonical,
while high-quality lossy audio is preserved as provisional and can be superseded
later without losing provenance.

**Beatport remains the metadata authority for DJ-critical tags** (BPM, key, genre,
label, catalog number) regardless of where audio was acquired.

Note: TIDAL v2 now returns `bpm`, `key`, `keyScale`, and `toneTags` natively for
many tracks. Where TIDAL provides these fields, they are used as the primary source.
Beatport remains the authority for tracks where TIDAL returns null or sparse values
and for genre/label/catalog, which TIDAL does not model to the same depth.

---

## Source selection matrix

| Track situation | Audio source | Metadata source | `ingestion_method` |
|---|---|---|---|
| On TIDAL + Beatport | TIDAL (tiddl) | TIDAL for bpm/key/tone; Beatport for genre/label/catalog | `provider_api` |
| On TIDAL only | TIDAL (tiddl) | TIDAL only; flag missing DJ tags | `provider_api` |
| On Beatport only | Beatport download | Beatport native, no TIDAL enrichment needed | `provider_api` |
| Neither (manual) | Operator-provided file | Manual tag review required | `manual_import` |

`canonical_source` on `track_identity` records which provider delivered the audio.

---

## Acquisition paths

### Path A — TIDAL acquisition (primary)

Triggered by any TIDAL URL or when ISRC resolves to a TIDAL match.

```
tools/get-intake <tidal_url_or_isrc>
  → tools/tiddl (external wrapper → tiddl)
  → FLAC lands in $STAGING_ROOT/tidal/
  → tagslut intake → enrich (Beatport + TIDAL v2)
```

Resulting file: FLAC at max quality (24-bit where available).

### Path B — Beatport acquisition (Beatport-only tracks)

Triggered explicitly by operator when a track is confirmed absent from TIDAL.
Not an automatic fallback — operator intent required.

```
tagslut download route <beatport_url>     ← thin Python helper (§23 Prompt 7)
  → BeatportDownloadProvider (purchase-download workflow)
  → MP3 or WAV lands in $STAGING_ROOT/beatport/
  → tagslut intake → enrich (Beatport native, skip TIDAL enrichment)
```

`asset_file.download_source = 'beatport'`
`track_identity.canonical_source = 'beatport'`
`ingestion_confidence = 'high'` (single provider; no cross-verification possible)

Beatport downloads are enabled only when `providers.beatport.download_enabled = true`
in `~/.config/tagslut/providers.toml`. Default is `false`. Operator must explicitly
enable for each session or permanently in config.

### Path C — ISRC-driven source selection

When operator provides a Beatport URL but wants TIDAL audio:

```
tagslut intake url <beatport_url>
  → extract ISRC from Beatport API
  → attempt TIDAL ISRC match
  → if match: Path A (TIDAL download)
  → if no match: flag, operator decides (Path B or hold)
```

No automatic silent fallback. The flag is explicit and visible in intake output.

---

## Fallback policy

### FALLBACK_ENABLED

`FALLBACK_ENABLED = true` is now a valid operator configuration for Beatport-only tracks.
The prior setting of `false` was a hold-over from when Beatport downloads were entirely
retired. Beatport downloads were retired as an **automatic** fallback; they are still
available as an **explicit** acquisition path.

Enabling `providers.beatport.download_enabled = true` in `providers.toml` is equivalent
to `FALLBACK_ENABLED = true` for the download role. The shell env var is retired;
use providers.toml.

### No-match handling

```
1. Attempt TIDAL ISRC match
2. If no match → log visible warning, surface in intake summary
3. Operator chooses:
   a. Enable Beatport download for this track explicitly
   b. Hold — track is queued for future TIDAL availability
   c. Manual exception — operator-provided file via Path manual
4. Do NOT silently proceed with no source
```

---

## Tool roles

| Tool | Role | Download | Metadata |
|---|---|---|---|
| **tiddl** (via `tools/tiddl`) | TIDAL acquisition | ✅ primary | ✅ FLAC tags at download |
| **Beatport API** | Metadata, ISRC lookup | ❌ never for metadata role | ✅ BPM/key/genre/label/catalog |
| **BeatportDownloadProvider** | Beatport purchase-download | ✅ explicit only | N/A |
| **tagslut** | Orchestration, DB, enrichment | — | ✅ enrichment pass |

## beatportdl

beatportdl is the download tool for Beatport-only tracks. It is not retired.
Use `ts-get <beatport_url>` to route Beatport URLs through beatportdl automatically.
beatportdl's credentials file is at `~/Projects/beatportdl/beatportdl-credentials.json`
and is synced into tagslut's `tokens.json` by `ts-auth beatport`.

The prior note about beatportdl being "permanently retired" applied only to the
automatic TIDAL→Beatport fallback within tools/get-intake. beatportdl as an explicit
acquisition tool remains active.

---

## Metadata enrichment pass

Regardless of acquisition path, every intake track goes through an enrichment pass:

```
tagslut index enrich --providers tidal,beatport
```

TIDAL enrichment writes: bpm (where non-null), key/keyScale/toneTags, isrc confirmation.
Beatport enrichment writes: bpm (authoritative where TIDAL null), key (Camelot+traditional),
genre, label, catalog number, release date.

Fields missing after both providers: flag in enrichment summary, do not block intake.

---

## Provenance rules

| Acquisition path | `ingestion_method` | `ingestion_confidence` |
|---|---|---|
| TIDAL + Beatport both confirm ISRC | `provider_api` | `verified` |
| TIDAL only (no Beatport match) | `provider_api` | `high` |
| Beatport only | `provider_api` | `high` |
| Manual import | `manual_import` | `uncertain` |

Full spec: `docs/INGESTION_PROVENANCE.md`

---

## ISRC conflict handling

When TIDAL and Beatport return different ISRCs for the same track:

```
1. Trust TIDAL ISRC (it is the audio source for Path A)
2. Log Beatport ISRC discrepancy at WARNING level
3. Store both in track_identity.canonical_payload_json.provider_id_conflicts
4. Set ingestion_confidence = 'uncertain'
5. Flag for manual review — do not promote to 'high' until resolved
```

---

## Configuration reference

### providers.toml (active config file)

```toml
[providers.tidal]
metadata_enabled = true
download_enabled = true   # routes to tools/tiddl wrapper
trust = "dj_primary"

[providers.beatport]
metadata_enabled = true
download_enabled = false  # set true to enable Beatport purchase-download
trust = "dj_primary"

[providers.qobuz]
metadata_enabled = true
download_enabled = false
trust = "secondary"
```

### Legacy env vars (retired)

```bash
# These are retired. Use providers.toml instead.
# PRIMARY_SOURCE="tidal"       → providers.tidal.download_enabled = true
# METADATA_AUTHORITY="beatport"→ providers.beatport.metadata_enabled = true
# FALLBACK_ENABLED=false       → providers.beatport.download_enabled = false|true
```

---

## Existing Beatport downloads (migration note)

Files in `/Volumes/MUSIC/mdl/bpdl` from the retired `beatportdl` workflow:

- Read-only reference. Do not delete.
- New acquisitions go through Path A or Path B above, never through bpdl.
- Deduplication: ISRC-based. Prefer TIDAL source where both exist.
- These files may lack full provenance — treat as `ingestion_method = 'manual_import'`
  if re-ingested.


## Download strategy (critical — never violate)

TIDAL is the primary audio source. Beatport is the metadata authority.

**Download path:**
  User provides URL → Extract ISRC → Download from TIDAL (tiddl) → Enrich with Beatport metadata

**Tool roles:**
  - tiddl: PRIMARY audio downloads (always)
  - beatportdl: Token provider for Beatport API access (metadata only, NEVER for downloads)
  - Beatport API: Metadata enrichment (BPM, key, genre, catalog numbers)
  - tagslut: Workflow orchestration, DB management

**Edge case handling:**
  - Beatport link + no TIDAL match → Flag for manual review, do NOT auto-download from Beatport
  - TIDAL link → Download directly, attempt Beatport enrichment via ISRC lookup
  - ISRC conflict → Trust TIDAL ISRC (it's the audio source), log discrepancy

**Volume layout:**
  - /Volumes/MUSIC/staging/tidal → Primary staging (TIDAL downloads)
  - /Volumes/MUSIC/staging/bpdl → Reference only (legacy Beatport downloads, read-only)
  - /Volumes/MUSIC/MASTER_LIBRARY → Final deduplicated library

**Never:**
  - Download audio from Beatport unless explicitly overridden by operator
  - Trust Beatport ISRC over TIDAL ISRC when both present
  - Auto-fallback to Beatport downloads when TIDAL unavailable


"""Quick smoke test for TIDAL and Beatport providers."""
from tagslut.metadata.auth import TokenManager
from tagslut.metadata.providers.tidal import TidalProvider
from tagslut.metadata.providers.beatport import BeatportProvider

TEST_ISRC = "GBUM71029604"  # Adele – Rolling in the Deep

tm = TokenManager()

print("=== TIDAL ===")
with TidalProvider(token_manager=tm) as tidal:
    results = tidal.search_by_isrc(TEST_ISRC, limit=3)
    if results:
        for t in results:
            print(f"  [{t.match_confidence.name}] {t.artist} – {t.title}  id={t.service_track_id}  isrc={t.isrc}")
    else:
        print("  no results — trying text search")
        results = tidal.search("Adele Rolling in the Deep", limit=3)
        for t in results:
            print(f"  [{t.match_confidence.name}] {t.artist} – {t.title}  id={t.service_track_id}")

print()
print("=== BEATPORT ===")
with BeatportProvider(token_manager=tm) as bp:
    results = bp.search_by_isrc(TEST_ISRC)
    if results:
        for t in results:
            print(f"  [{t.match_confidence.name}] {t.artist} – {t.title}  id={t.service_track_id}  isrc={t.isrc}")
    else:
        print("  no results for ISRC — trying text search")
        results = bp.search("Adele Rolling in the Deep", limit=3)
        for t in results:
            print(f"  [{t.match_confidence.name}] {t.artist} – {t.title}  id={t.service_track_id}")

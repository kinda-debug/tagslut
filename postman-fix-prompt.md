Repo    : kinda-debug/tagslut
Branch  : dev
Working : ~/Projects/tagslut

══════════════════════════════════════════════════════
CONFIRMED FILE TREE — POSTMAN LAYER 
══════════════════════════════════════════════════════

postman/
├── collections/
│   └── tagslut - API/
│       ├── Auth/
│       │   ├── Get Token (Client Credentials).request.yaml
│       │   └── Introspect Token.request.yaml
│       ├── Catalog/
│       │   ├── ISRC Store Lookup (path-based) [Phase 3d].request.yaml
│       │   ├── Release by ID.request.yaml
│       │   ├── Release Tracks.request.yaml
│       │   ├── Track by ID.request.yaml
│       │   └── Tracks by ISRC (query param).request.yaml
│       ├── Identity Verification/
│       │   ├── 5a - Beatport ISRC Lookup.request.yaml
│       │   ├── 5b - TIDAL ISRC Cross-Check.request.yaml   ← MUST CHANGE
│       │   └── 5c - Spotify ISRC Cross-Check.request.yaml
│       ├── My Library/
│       │   ├── My Account.request.yaml
│       │   └── My Beatport Tracks.request.yaml
│       ├── Search/
│       │   └── Search Tracks by Text.request.yaml
│       ├── Validation Run/
│       │   ├── 6a - Resolve TIDAL Album to ISRC.request.yaml  ← MUST CHANGE
│       │   ├── 6b - Track by ID (Validation).request.yaml
│       │   └── 6c - Run Notes.request.yaml
│       └── insomnia-export.1774520966035/       ← ARCHIVE — DO NOT EDIT (contains beatport-api-oas.json, openapi_beatport.json, tidal-api-oas.json)
│           ├── env-merged.yaml
│           ├── tagslut - API.postman_collection-2.json
│           ├── tagslut - API.postman_collection-3.json
│           ├── tagslut - API.postman_collection.json
│           ├── tagslut---API-merged.yaml
│           ├── tagslut---API-wrk_5ff8f93c853b41a9bd49d10a4af8f7c1.yaml
│           ├── tagslut---API-wrk_f49d23a4ef7d4d89b46f3f79f69dbd6b.yaml
│           ├── TIDAL-API-1.4.8-wrk_957e55c6bbc54239bfc63a150db0d98b.yaml
│           └── tidal-api-oas.json
└── environments/
    ├── env.environment.yaml                      ← READ ONLY — do not change
    ├── tagslut.environment.yaml                  ← REPAIR THIS
    └── tagslut.environment.yaml.patch.md         ← FOLD INTO ABOVE, THEN DELETE

insomnia-export.1774520966035/ is an archive directory. Do NOT edit any file
inside it. The .json exports inside it are snapshots only. All changes must be
made to the YAML request files and environment files listed above.

══════════════════════════════════════════════════════
NOTE — MISPLACED PROMPT FILE
══════════════════════════════════════════════════════

A file postman/postman-fix-prompt.md was written to the repo by a previous
operation. Before starting this task:

  mv postman/postman-fix-prompt.md ~/Desktop/postman-fix-prompt.md
  # or: echo 'postman/postman-fix-prompt.md' >> .gitignore

Do NOT commit it. It is a scratch artifact, not part of the Postman source.


══════════════════════════════════════════════════════
TASK 1 — REPAIR postman/environments/tagslut.environment.yaml
══════════════════════════════════════════════════════

The file is currently malformed and/or has duplicate keys.

Steps:
1. Read the current tagslut.environment.yaml. Fix all YAML syntax errors.
   Remove duplicate keys — keep only the first occurrence of each key.
2. Read tagslut.environment.yaml.patch.md. Identify any variable declarations
   it specifies that are NOT already in tagslut.environment.yaml.
   Merge those variables into tagslut.environment.yaml.
3. Delete tagslut.environment.yaml.patch.md after folding its contents.
4. Ensure the final file contains exactly one entry for each of these keys,
   in this order, with initialValue: '' for any that have no current value:

   base_url
   beatport_client_id
   beatport_client_secret
   beatport_access_token
   beatport_token_expires_at
   beatport_last_isrc
   beatport_last_track_id         ← add if missing; scripts write it
   beatport_verified_id
   beatport_verified_isrc
   beatport_test_isrc
   beatport_test_track_id
   beatport_test_release_id
   beatport_search_query
   tidal_access_token
   tidal_seed_track_id
   tidal_seed_isrc
   spotify_access_token
   spotify_verified_id

Rules:
- All configuration variables (base_url, beatport_client_id, etc.)
  have their value supplied by the operator — leave current values intact.
- All runtime/chained variables (beatport_last_isrc, beatport_verified_id,
  tidal_seed_isrc, etc.) start as empty string.
- tidal_access_token must be present with initialValue: '' — it is set
  manually by the operator before running TIDAL steps.
- Do NOT add any filesystem paths (TAGSLUT_DB, VOLUME_STAGING, DJ_LIBRARY,
  etc.) — those belong in env.environment.yaml only.

Verification:
  python3 -c "import yaml; yaml.safe_load(open('postman/environments/tagslut.environment.yaml'))"
  Must succeed with no errors and print nothing.

══════════════════════════════════════════════════════
TASK 2 — FIX 5b - TIDAL ISRC Cross-Check.request.yaml
══════════════════════════════════════════════════════

File:
  postman/collections/tagslut - API/Identity Verification/5b - TIDAL ISRC Cross-Check.request.yaml

CURRENT STATE (confirmed from both JSON exports):
  URL   : https://api.tidal.com/v1/tracks?isrc={{beatport_verified_isrc}}&countryCode=US
  Script: parses json.items[] → items[0].isrc (v1 flat shape)
          reads id, title, duration, explicit, audioQuality, version from items[0] directly

REQUIRED CHANGES:

  URL change:
    FROM:  https://api.tidal.com/v1/tracks
    TO:    https://openapi.tidal.com/v2/tracks
    Params:
      filter[isrc] = {{beatport_verified_isrc}}
      countryCode  = US
    Auth: Bearer {{tidal_access_token}}  (unchanged)

  Test script — replace the entire exec block with:

    var code = pm.response.code;
    console.log('[5b] Status: ' + code);
    
    if (code !== 200) {
        console.log('[5b] TIDAL request FAILED — body: ' +
            pm.response.text().substring(0, 300));
        return;
    }
    
    var json  = pm.response.json();
    var items = (json.data && Array.isArray(json.data)) ? json.data : [];
    
    if (!items.length) {
        console.log('[5b] WARNING: TIDAL returned 0 results for ISRC ' +
            pm.environment.get('beatport_verified_isrc'));
        return;
    }
    
    var attr        = items[0].attributes || {};
    var tidalIsrc   = attr.isrc;
    var beatportIsrc = pm.environment.get('beatport_verified_isrc');
    
    console.log('[5b] beatport_isrc : ' + beatportIsrc);
    console.log('[5b] tidal_isrc    : ' + tidalIsrc);
    
    if (tidalIsrc === beatportIsrc) {
        console.log('[5b] CORROBORATED — both providers agree: ' + beatportIsrc);
    } else {
        console.log('[5b] CONFLICT — beatport_isrc: ' + beatportIsrc +
                    ' | tidal_isrc: ' + tidalIsrc);
    }
    
    // Log TIDAL v2 enrichment fields available for provenance
    var enrichment = ['bpm', 'key', 'keyScale', 'toneTags', 'popularity',
                      'title', 'version', 'explicit', 'mediaTags', 'duration'];
    var found = [];
    enrichment.forEach(function(f) {
        if (attr[f] !== null && attr[f] !== undefined) {
            found.push(f + '=' + JSON.stringify(attr[f]).substring(0, 40));
        }
    });
    if (found.length) {
        console.log('[5b] TIDAL v2 enrichment fields: ' + found.join(', '));
    }

  Pre-request script — add to the Identity Verification folder-level
  prerequest (or to 5b directly if the folder has no prerequest):

    // TIDAL token guard — warn only, do not block
    if (!pm.environment.get('tidal_access_token')) {
        console.warn('[tidal-guard] tidal_access_token is not set. ' +
            'TIDAL requests will fail. Set it manually in the environment.');
    }

  This guard must NOT affect Beatport or Spotify requests.
  Add it only at the Identity Verification folder level or as a 5b-specific
  prerequest — do not add it to the collection-level prerequest script.

══════════════════════════════════════════════════════
TASK 3 — FIX 6a - Resolve TIDAL Album to ISRC.request.yaml
══════════════════════════════════════════════════════

File:
  postman/collections/tagslut - API/Validation Run/6a - Resolve TIDAL Album to ISRC.request.yaml

CURRENT STATE (confirmed from both JSON exports):
  URL   : https://api.tidal.com/v1/albums/507881809/tracks?countryCode=US
  Script: parses json.items[] → items[0].isrc, items[0].id (v1 flat shape)
          sets beatport_test_isrc, tidal_seed_track_id, tidal_seed_isrc

REQUIRED CHANGES:

  URL change:
    FROM:  https://api.tidal.com/v1/albums/507881809/tracks
    TO:    https://openapi.tidal.com/v2/albums/507881809
    Params:
      include      = items          (fetches track items as included resources)
      countryCode  = US
    Auth: Bearer {{tidal_access_token}}  (unchanged)

  NOTE: The album ID 507881809 is intentional and hardcoded — do not change it.

  Test script — replace the entire exec block with:

    var code = pm.response.code;
    console.log('[6a] Status: ' + code);
    
    if (code !== 200) {
        console.log('[6a] FAILED — body: ' +
            pm.response.text().substring(0, 400));
        return;
    }
    
    var json     = pm.response.json();
    var included = Array.isArray(json.included) ? json.included : [];
    
    // Collect track resources from included[]
    var tracks = included.filter(function(r) {
        return r.type === 'tracks';
    });
    
    if (!tracks.length) {
        console.log('[6a] WARNING: album 507881809 returned 0 track resources in included[].');
        return;
    }
    
    var firstTrack = tracks[0];
    var attr       = firstTrack.attributes || {};
    var tid        = firstTrack.id;
    var isrc       = attr.isrc;
    
    if (!isrc) {
        console.log('[6a] WARNING: first track has no isrc in attributes. ' +
            'Keys: ' + Object.keys(attr).join(', '));
        return;
    }
    
    pm.environment.set('beatport_test_isrc',  isrc);
    pm.environment.set('tidal_seed_track_id', String(tid));
    pm.environment.set('tidal_seed_isrc',     isrc);
    
    var artistName = (attr.artists && attr.artists[0] && attr.artists[0].name)
        ? attr.artists[0].name : '?';
    
    console.log('[6a] Seed track: ' + (attr.title || '?') +
        ' by ' + artistName);
    console.log('[6a] tidal_track_id   : ' + tid);
    console.log('[6a] beatport_test_isrc: ' + isrc);
    console.log('[6a] tidal_seed_isrc  : ' + isrc);
    console.log('[6a] Total tracks in included[]: ' + tracks.length);

══════════════════════════════════════════════════════
DO NOT TOUCH
══════════════════════════════════════════════════════

- postman/environments/env.environment.yaml  — read-only, never modify
- postman/collections/tagslut - API/insomnia-export.1774520966035/ — archive, never modify
- Any file not listed in Tasks 1–3 above
- Collection-level prerequest script (token-guard block) — already correct, leave it
- 5a, 5c, 6b, 6c — no changes needed
- Python application code (tagslut/, scripts/, tools/) — out of scope for this task
- Any docs/ file — out of scope for this task

══════════════════════════════════════════════════════
VERIFICATION
══════════════════════════════════════════════════════

After completing all three tasks, run these checks and confirm each passes:

1. YAML validity — both environment files must parse:
   python3 -c "
   import yaml, pathlib
   for p in [
       'postman/environments/tagslut.environment.yaml',
       'postman/environments/env.environment.yaml',
   ]:
       yaml.safe_load(pathlib.Path(p).read_text())
       print('OK:', p)
   "

2. No duplicate keys in runnable env:
   python3 -c "
   import yaml, pathlib, collections
   raw = yaml.safe_load(pathlib.Path('postman/environments/tagslut.environment.yaml').read_text())
   # Postman YAML format: list of {key, value, ...} dicts
   values = raw.get('values', [])
   keys = [v['key'] for v in values]
   dupes = [k for k, n in collections.Counter(keys).items() if n > 1]
   print('Duplicates:', dupes or 'none')
   "

3. No v1 TIDAL URLs remain in the canonical YAML collection:
   grep -r 'api.tidal.com/v1' 'postman/collections/tagslut - API/'
   Must return zero results.

4. patch.md must no longer exist:
   test ! -f postman/environments/tagslut.environment.yaml.patch.md && echo 'OK: patch file gone'

5. All required env keys are present:
   python3 -c "
   import yaml, pathlib
   raw = yaml.safe_load(pathlib.Path('postman/environments/tagslut.environment.yaml').read_text())
   present = {v['key'] for v in raw.get('values', [])}
   required = {
       'base_url','beatport_client_id','beatport_client_secret',
       'beatport_access_token','beatport_token_expires_at',
       'beatport_last_isrc','beatport_last_track_id',
       'beatport_verified_id','beatport_verified_isrc',
       'beatport_test_isrc','beatport_test_track_id','beatport_test_release_id',
       'beatport_search_query','tidal_access_token',
       'tidal_seed_track_id','tidal_seed_isrc',
       'spotify_access_token','spotify_verified_id',
   }
   missing = required - present
   print('Missing keys:', missing or 'none')
   "

══════════════════════════════════════════════════════
COMMIT MESSAGE
══════════════════════════════════════════════════════

fix(postman): migrate 5b+6a to TIDAL v2 JSONAPI, repair runnable env, delete patch.md
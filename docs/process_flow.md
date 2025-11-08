# Process flow

## Synchronisation (`dedupe sync`)

```
+-------------+       +-----------------+       +------------------------+
| DEDUPE_DIR |  -->  | gather metadata  |  -->  | pick preferred version |
+-------------+       +-----------------+       +------------------------+
                                              | library <= healthiest |
                                              +-----------+------------+
                                                          |
                                                          v
                                        +------------------------------------+
                                        | move/delete/swap + prune empties   |
                                        +------------------------------------+
```

1. Discover the dedupe directory via `DEDUPE_DIR.txt` (or explicit `--dedupe-root`).
2. Gather metadata/health information for both staged and library copies.
3. Choose the healthiest candidate, preferring size and modification time when
   health scores tie.
4. Apply filesystem changes (move, delete, or swap) and prune empty directories.
5. Optional: verify playback health across the entire library.

## Quarantine analysis

```
quarantine analyse  -> detailed ffprobe + PCM hash + Chromaprint
quarantine scan     -> lightweight duration + size inventory
quarantine length   -> reported vs decoded duration diff
```

All commands share CSV writers so downstream tools can consume consistent
schemas.

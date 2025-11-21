#!/bin/bash
set -euo pipefail

LIB_DB="artifacts/db/library.db"
REC_DB="artifacts/db/recovered.db"
MATCHES="artifacts/reports/matches.csv"
OUT="artifacts/reports/matches_upgrade_candidates.csv"

echo "[1/3] Importing matches.csv into temporary SQLite table..."
sqlite3 "$LIB_DB" <<SQL
DROP TABLE IF EXISTS matches;
CREATE TABLE matches (
    library_path TEXT,
    recovered_path TEXT,
    similarity REAL,
    reason TEXT
);
.mode csv
.import $MATCHES matches
SQL

echo "[2/3] Attaching recovered.db and generating upgrade candidates..."
sqlite3 "$LIB_DB" <<SQL
ATTACH DATABASE '$REC_DB' AS rdb;

.output $OUT
.mode csv
.headers on

SELECT
    m.library_path,
    m.recovered_path,
    m.similarity,
    l.size_bytes AS library_size,
    r.size_bytes AS recovered_size,
    (r.size_bytes - l.size_bytes) AS size_delta
FROM matches AS m
LEFT JOIN library_files AS l
    ON l.path = m.library_path
LEFT JOIN rdb.recovered_files AS r
    ON r.source_path = m.recovered_path
WHERE
    r.size_bytes IS NOT NULL
    AND l.size_bytes IS NOT NULL
    AND r.size_bytes > l.size_bytes
    AND m.similarity >= 0.80
ORDER BY size_delta DESC;

.output stdout
DETACH DATABASE rdb;
SQL

echo "[3/3] Done."
echo "Created: $OUT"

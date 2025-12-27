-- Restrict to NEW_LIBRARY/MUSIC and exclude obviously bad roots
DROP TABLE IF EXISTS best_copy_candidates;
CREATE TEMP TABLE best_copy_candidates AS
SELECT
    path,
    COALESCE(duration, 0) AS duration,
    LOWER(path) AS path_lc
FROM library_files
WHERE path LIKE '/Volumes/dotad/NEW_LIBRARY/MUSIC/%'
  AND path NOT LIKE '%/_quarantine_bad_flacs/%'
  AND path NOT LIKE '%/_quarantine_bad_mp3s/%'
  AND path NOT LIKE '%/Quarantine/%'
  AND path NOT LIKE '%/Garbage/%';

-- Group key: filename (everything after last "/")
DROP TABLE IF EXISTS best_copy_groups;
CREATE TEMP TABLE best_copy_groups AS
SELECT
    path,
    duration,
    -- filename only, lowercased
    LOWER(
      CASE
        WHEN instr(path_lc, '/') > 0 THEN
          substr(path_lc, length(path_lc) - instr(reverse(path_lc), '/') + 2)
        ELSE path_lc
      END
    ) AS base_name,
    CASE
      WHEN path LIKE '%/MUSIC/REPAIRED/%' THEN 3
      WHEN path LIKE '%/MUSIC/%' THEN 2
      ELSE 1
    END AS path_score
FROM best_copy_candidates;

-- Rank within each base_name: higher path_score, then longer duration
DROP TABLE IF EXISTS best_copy_ranked;
CREATE TEMP TABLE best_copy_ranked AS
SELECT
    base_name,
    path,
    duration,
    path_score,
    ROW_NUMBER() OVER (
      PARTITION BY base_name
      ORDER BY path_score DESC,
               duration DESC,
               path ASC
    ) AS rn
FROM best_copy_groups;

.headers on
.mode csv
.once artifacts/reports/best_copy_decisions.csv
SELECT
    base_name,
    path,
    duration,
    path_score,
    CASE
      WHEN rn = 1 THEN 'keep'
      ELSE 'move'
    END AS decision
FROM best_copy_ranked
ORDER BY base_name, decision DESC, path_score DESC, duration DESC, path ASC;

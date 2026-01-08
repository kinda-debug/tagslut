WITH RECURSIVE
split(path, idx, rest, comp, depth) AS (
  SELECT
    path,
    1 AS idx,
    CASE
      WHEN instr(path, '/') = 0 THEN ''
      ELSE substr(path, instr(path, '/') + 1)
    END AS rest,
    CASE
      WHEN instr(path, '/') = 0 THEN path
      ELSE substr(path, 1, instr(path, '/') - 1)
    END AS comp,
    (LENGTH(path) - LENGTH(REPLACE(path, '/', ''))) + 1 AS depth
  FROM files
  UNION ALL
  SELECT
    path,
    idx + 1,
    CASE
      WHEN instr(rest, '/') = 0 THEN ''
      ELSE substr(rest, instr(rest, '/') + 1)
    END AS rest,
    CASE
      WHEN instr(rest, '/') = 0 THEN rest
      ELSE substr(rest, 1, instr(rest, '/') - 1)
    END AS comp,
    depth
  FROM split
  WHERE rest != ''
)
SELECT
  path,
  depth,
  MAX(CASE WHEN idx = 1 THEN comp END) AS col_01,
  MAX(CASE WHEN idx = 2 THEN comp END) AS col_02,
  MAX(CASE WHEN idx = 3 THEN comp END) AS col_03,
  MAX(CASE WHEN idx = 4 THEN comp END) AS col_04,
  MAX(CASE WHEN idx = 5 THEN comp END) AS col_05,
  MAX(CASE WHEN idx = 6 THEN comp END) AS col_06,
  MAX(CASE WHEN idx = 7 THEN comp END) AS col_07,
  MAX(CASE WHEN idx = 8 THEN comp END) AS col_08,
  MAX(CASE WHEN idx = 9 THEN comp END) AS col_09,
  MAX(CASE WHEN idx = 10 THEN comp END) AS col_10,
  MAX(CASE WHEN idx = 11 THEN comp END) AS col_11,
  MAX(CASE WHEN idx = 12 THEN comp END) AS col_12,
  MAX(CASE WHEN idx = 13 THEN comp END) AS col_13,
  MAX(CASE WHEN idx = 14 THEN comp END) AS col_14,
  MAX(CASE WHEN idx = 15 THEN comp END) AS col_15,
  MAX(CASE WHEN idx = 16 THEN comp END) AS col_16,
  MAX(CASE WHEN idx = 17 THEN comp END) AS col_17,
  MAX(CASE WHEN idx = 18 THEN comp END) AS col_18,
  MAX(CASE WHEN idx = 19 THEN comp END) AS col_19,
  MAX(CASE WHEN idx = 20 THEN comp END) AS col_20,
  MAX(CASE WHEN idx = 21 THEN comp END) AS col_21
FROM split
GROUP BY path, depth
ORDER BY path;

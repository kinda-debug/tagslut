"""
Filter expression parser for gig set queries.

Converts a filter expression string into a safe parameterised SQL
WHERE clause for use against the `files` table.

Example:
    expr = "genre:techno bpm:128-145 dj_flag:true quality_rank:<=4"
    clause, params = parse_filter(expr)
    # clause = "canonical_genre = ? AND canonical_bpm BETWEEN ? AND ? AND is_dj_material = ? AND quality_rank <= ?"
    # params = ("techno", 128, 145, 1, 4)
"""

import re

FILTER_COLUMN_MAP = {
    "genre": "canonical_genre",
    "bpm": "canonical_bpm",
    "key": "canonical_key",
    "dj_flag": "is_dj_material",
    "label": "canonical_label",
    "source": "download_source",
    "added": "download_date",
    "quality_rank": "quality_rank",
}


class FilterParseError(ValueError):
    pass


def parse_filter(expr: str) -> tuple[str, list]:  # type: ignore  # TODO: mypy-strict
    """
    Parse a filter expression string into a (WHERE clause, params) tuple.
    Both can be passed directly to sqlite3 execute().

    Returns ("1=1", []) for an empty expression (match all).
    """
    if not expr or not expr.strip():
        return "1=1", []

    clauses = []
    params: list = []  # type: ignore  # TODO: mypy-strict

    for token in expr.strip().split():
        if ":" not in token:
            raise FilterParseError(f"Invalid filter token (missing colon): {token!r}")
        key, value = token.split(":", 1)
        key = key.lower()

        if key not in FILTER_COLUMN_MAP:
            raise FilterParseError(f"Unknown filter key: {key!r}. Valid: {list(FILTER_COLUMN_MAP)}")

        col = FILTER_COLUMN_MAP[key]

        range_match = re.fullmatch(r"([\d.]+)-([\d.]+)", value)
        if range_match:
            clauses.append(f"{col} BETWEEN ? AND ?")
            params.extend([float(range_match.group(1)), float(range_match.group(2))])
            continue

        cmp_match = re.fullmatch(r"(<=|>=|<|>|=)([\d.]+)", value)
        if cmp_match:
            op, val = cmp_match.group(1), cmp_match.group(2)
            clauses.append(f"{col} {op} ?")
            params.append(float(val))
            continue

        if value.lower() in ("true", "1", "yes"):
            clauses.append(f"{col} = ?")
            params.append(1)
            continue
        if value.lower() in ("false", "0", "no"):
            clauses.append(f"{col} = ?")
            params.append(0)
            continue

        if "," in value:
            values = value.split(",")
            placeholders = ",".join(["?"] * len(values))
            clauses.append(f"{col} IN ({placeholders})")
            params.extend(values)
            continue

        date_match = re.fullmatch(r"(<=|>=|<|>)?(.+)", value)
        if date_match and date_match.group(1):
            clauses.append(f"{col} {date_match.group(1)} ?")
            params.append(date_match.group(2))
            continue

        clauses.append(f"{col} = ?")
        params.append(value)

    return " AND ".join(clauses) if clauses else "1=1", params

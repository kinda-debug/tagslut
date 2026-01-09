# Tools (Operator CLIs)

These are the only tools you need day-to-day.

## Scan

```bash
python3 tools/integrity/scan.py /path/to/root
```

## Recommend (Read-Only)

```bash
python3 tools/decide/recommend.py --db "$DEDUPE_DB" --output plan.json
```

## Apply (Only When Approved)

```bash
python3 tools/decide/apply.py --db "$DEDUPE_DB" --plan plan.json
```

## DB Health

```bash
python3 tools/db/doctor.py --db "$DEDUPE_DB"
```

## DB Compare

```bash
python3 tools/compare_dbs.py --a /path/to/a.db --b /path/to/b.db
```

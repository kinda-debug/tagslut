# cleanup-djpool-home — delete /Users/georgeskhawam/Music/DJPool

## Context

`/Users/georgeskhawam/Music/DJPool` is a 31-file flat MP3 directory that was
used as a manual staging area in a prior workflow. It is not wired to any
tagslut pipeline, not registered in the DB, and not referenced from any M3U
or CLI path. The operator has confirmed these tracks are duplicated elsewhere
and the directory should be deleted entirely.

This is a one-step cleanup. No DB writes, no migrations, no CLI changes.

---

## Task

Delete the directory and its contents:

```bash
rm -rf "/Users/georgeskhawam/Music/DJPool"
```

Confirm deletion:

```bash
test -d "/Users/georgeskhawam/Music/DJPool" && echo "STILL EXISTS" || echo "DELETED OK"
```

If `DELETED OK`, commit:

```
git commit --allow-empty -m "chore(cleanup): delete legacy DJPool staging dir from home"
```

(Empty commit is acceptable — this is a filesystem-only change outside the repo.)

---

## Constraints

- Do not touch any other path under `/Users/georgeskhawam/Music/`
- Do not modify the DB
- Do not create any replacement directory

#!/usr/bin/env python3
import argparse
import os
import sqlite3

def ro_uri(path: str) -> str:
    p = os.path.abspath(os.path.expanduser(path))
    return f"file:{p}?mode=ro&immutable=1"

def connect_ro(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(ro_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    return conn

def tables(conn):
    return [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]

def count(conn, table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.Error:
        return None

def profile(path):
    conn = connect_ro(path)
    try:
        prof = {
            "path": path,
            "tables": tables(conn),
            "files": count(conn, "files"),
            "scan_sessions": count(conn, "scan_sessions"),
            "file_scan_runs": count(conn, "file_scan_runs"),
        }
        return prof
    finally:
        conn.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    args = ap.parse_args()

    a = profile(args.a)
    b = profile(args.b)

    print("=== DB A ===")
    for k, v in a.items():
        print(f"{k}: {v}")

    print("\n=== DB B ===")
    for k, v in b.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()

"""Migrate data from the existing SQLite database to PostgreSQL.

Usage:
    uv run python scripts/migrate_to_postgres.py [--sqlite PATH]

Reads from the SQLite database, writes to the PostgreSQL database
configured via PGH_DATABASE_URL env var (defaults to local docker).
"""

from __future__ import annotations

import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import asyncpg

SQLITE_DEFAULT = Path.home() / "Library/Application Support/pgh-ticket/tickets.db"
PG_DSN = "postgresql://pgh_ticket:pgh_ticket@localhost:5432/pgh_ticket"

TABLES = [
    "tickets",
    "locations",
    "scans",
    "clusters",
    "error_logs",
]


def _parse_date(val: str | None) -> date | None:
    """Parse ISO or M/D/YYYY date string."""
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_dt(val: str | None) -> str:
    """Return ISO timestamp as-is, default to empty string."""
    return val if val else ""


def _lower(val: str | None) -> str:
    return val.lower() if val else ""


def _bool_val(val: Any) -> bool:
    if isinstance(val, int):
        return bool(val)
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes")
    return bool(val)


def _null_to_empty(val: Any) -> str:
    return "" if val is None else str(val)


def read_tickets(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    cur.execute("SELECT * FROM tickets ORDER BY ticket_number")
    cols = [d[0] for d in cur.description]
    rows = []
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        d["issue_date"] = _parse_date(d.get("issue_date"))
        d["due_date"] = _parse_date(d.get("due_date"))
        d["first_seen"] = _parse_dt(d.get("first_seen"))
        d["updated_at"] = _parse_dt(d.get("updated_at"))
        d["status"] = _lower(d.get("status"))
        # Ensure NOT NULL string columns
        for field in ("raw_json", "notes", "vehicle_make", "license_plate",
                       "state", "location", "violation", "officer",
                       "ticket_type", "ticket_key"):
            d[field] = _null_to_empty(d.get(field))
        rows.append(d)
    return rows


def read_locations(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    cur.execute("SELECT * FROM locations ORDER BY raw_location")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def read_scans(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    cur.execute("SELECT * FROM scans ORDER BY id")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def read_clusters(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    cur.execute("SELECT * FROM clusters ORDER BY id")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def read_error_logs(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    cur.execute("SELECT * FROM error_logs ORDER BY id")
    cols = [d[0] for d in cur.description]
    rows = []
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        d["resolved"] = _bool_val(d.get("resolved"))
        rows.append(d)
    return rows


READERS = {
    "tickets": read_tickets,
    "locations": read_locations,
    "scans": read_scans,
    "clusters": read_clusters,
    "error_logs": read_error_logs,
}

TABLE_SCHEMAS = {
    "tickets": """
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_number VARCHAR PRIMARY KEY,
            ticket_key VARCHAR NOT NULL DEFAULT '',
            vehicle_make VARCHAR NOT NULL DEFAULT '',
            license_plate VARCHAR NOT NULL DEFAULT '',
            state VARCHAR NOT NULL DEFAULT '',
            issue_date DATE,
            location VARCHAR NOT NULL DEFAULT '',
            violation VARCHAR NOT NULL DEFAULT '',
            amount_due VARCHAR NOT NULL DEFAULT '',
            due_date DATE,
            officer VARCHAR NOT NULL DEFAULT '',
            notes VARCHAR NOT NULL DEFAULT '',
            status VARCHAR NOT NULL DEFAULT '',
            ticket_type VARCHAR NOT NULL DEFAULT '',
            raw_json TEXT NOT NULL DEFAULT '',
            first_seen VARCHAR NOT NULL DEFAULT '',
            updated_at VARCHAR NOT NULL DEFAULT ''
        )
    """,
    "locations": """
        CREATE TABLE IF NOT EXISTS locations (
            raw_location VARCHAR PRIMARY KEY,
            address VARCHAR NOT NULL DEFAULT '',
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            geocoded_at VARCHAR NOT NULL DEFAULT '',
            ticket_count INTEGER NOT NULL DEFAULT 0
        )
    """,
    "scans": """
        CREATE TABLE IF NOT EXISTS scans (
            id SERIAL PRIMARY KEY,
            range_start INTEGER,
            range_end INTEGER,
            until_date VARCHAR,
            tickets_found INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            duration_s DOUBLE PRECISION DEFAULT 0.0,
            scanned_at VARCHAR DEFAULT ''
        )
    """,
    "clusters": """
        CREATE TABLE IF NOT EXISTS clusters (
            id SERIAL PRIMARY KEY,
            range_start INTEGER NOT NULL,
            range_end INTEGER NOT NULL,
            last_scanned VARCHAR NOT NULL DEFAULT '',
            ticket_count INTEGER NOT NULL DEFAULT 0,
            created_at VARCHAR NOT NULL DEFAULT ''
        )
    """,
    "error_logs": """
        CREATE TABLE IF NOT EXISTS error_logs (
            id SERIAL PRIMARY KEY,
            number VARCHAR NOT NULL,
            command VARCHAR NOT NULL DEFAULT '',
            error_type VARCHAR NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            retries INTEGER NOT NULL DEFAULT 0,
            resolved BOOLEAN NOT NULL DEFAULT FALSE,
            first_seen VARCHAR NOT NULL DEFAULT '',
            last_seen VARCHAR NOT NULL DEFAULT ''
        )
    """,
}


async def insert_data(
    pg: asyncpg.Connection,
    table: str,
    rows: list[dict[str, Any]],
    batch: int = 500,
) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    col_list = ", ".join(cols)
    ph = ", ".join(f"${j+1}" for j in range(len(cols)))
    query = f"INSERT INTO {table} ({col_list}) VALUES ({ph}) ON CONFLICT DO NOTHING"
    total = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        values = [[r[c] for c in cols] for r in chunk]
        await pg.executemany(query, values)
        total += len(chunk)
        print(f"  inserted {total}/{len(rows)} into {table}")
    return total


async def main(sqlite_path: str | None = None) -> None:
    db_path = Path(sqlite_path) if sqlite_path else SQLITE_DEFAULT
    if not db_path.exists():
        print(f"SQLite database not found: {db_path}")
        sys.exit(1)

    print(f"Reading from: {db_path}")
    print(f"Writing to:   {PG_DSN}")

    # Read all data from SQLite
    t0 = time.monotonic()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    all_data: dict[str, list[dict[str, Any]]] = {}
    for table in TABLES:
        rows = READERS[table](cur)
        all_data[table] = rows
        print(f"  read {len(rows)} rows from {table}")

    conn.close()
    read_elapsed = time.monotonic() - t0
    print(f"Read complete ({read_elapsed:.1f}s)")

    # Write to PostgreSQL
    pg = await asyncpg.connect(PG_DSN)

    # Clear existing data
    for table in TABLES:
        await pg.execute(f"DELETE FROM {table}")

    total = 0
    for table in TABLES:
        rows = all_data[table]
        n = await insert_data(pg, table, rows)
        total += n

    await pg.close()
    elapsed = time.monotonic() - t0
    print(f"\nDone. Migrated {total} rows across {len(TABLES)} tables ({elapsed:.1f}s)")


if __name__ == "__main__":
    import asyncio

    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(sqlite_path))

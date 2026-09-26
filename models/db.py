# -*- coding: utf-8 -*-
"""
Storage layer.

Two kinds of data, stored differently on purpose:

1. The scheme catalogue (read-only, rebuilt from data/schemes_data.py on every
   deploy) lives in a small SQLite file. Nothing here is user data, so it is
   fine for it to be rebuilt from scratch whenever the container restarts.

2. User data (accounts and saved case files) lives in an external PostgreSQL
   database when the DATABASE_URL environment variable is set (e.g. a free
   Neon or Supabase database). Hosting platforms like Render wipe the
   container's own disk on every redeploy/restart, so anything written to
   SQLite inside the container would be lost. With no DATABASE_URL (local
   development) user data falls back to the same SQLite file, so the project
   still runs with zero setup.
"""

import json
import logging
import os
import sqlite3

log = logging.getLogger("yojana.db")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "schemes.db")

# Bump whenever the schemes table layout or the scheme data changes shape.
# The app rebuilds the catalogue at startup if the file's version differs.
SCHEMA_VERSION = 2

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USING_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))


# --------------------------------------------------------------------------
# Scheme catalogue (SQLite, read-only at runtime)
# --------------------------------------------------------------------------

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the schemes table and populate it from data/schemes_data.py."""
    import sys
    sys.path.insert(0, BASE_DIR)
    from data.schemes_data import SCHEMES, validate_schemes

    validate_schemes(SCHEMES)  # refuse to build a catalogue with broken data

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS schemes")
    cur.execute("""
        CREATE TABLE schemes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            benefit_summary TEXT,
            min_age INTEGER,
            max_age INTEGER,
            income_max INTEGER,
            gender TEXT,
            occupations TEXT,
            special_categories TEXT,
            employment TEXT,
            states TEXT,
            extra_conditions TEXT,
            required_documents TEXT,
            application_link TEXT
        )
    """)
    for s in SCHEMES:
        cur.execute("""
            INSERT INTO schemes (id, name, category, description, benefit_summary,
                                 min_age, max_age, income_max, gender, occupations,
                                 special_categories, employment, states, extra_conditions,
                                 required_documents, application_link)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            s["id"], s["name"], s["category"], s["description"], s["benefit_summary"],
            s["min_age"], s["max_age"], s["income_max"], s["gender"],
            json.dumps(s["occupations"]), json.dumps(s["special_categories"]),
            json.dumps(s.get("employment", ["ALL"])),
            json.dumps(s["states"]), s["extra_conditions"],
            json.dumps(s["required_documents"]), s["application_link"],
        ))
    cur.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
    conn.commit()
    conn.close()


def ensure_schemes_db():
    """Build the catalogue if it is missing or was built by an older version."""
    current = None
    if os.path.exists(DB_PATH):
        try:
            conn = get_connection()
            current = conn.execute("PRAGMA user_version").fetchone()[0]
            conn.close()
        except sqlite3.Error:
            current = None
    if current != SCHEMA_VERSION:
        init_db()


def row_to_scheme(row):
    """Convert a sqlite Row into a plain dict with JSON fields decoded."""
    d = dict(row)
    for field in ("occupations", "special_categories", "employment", "states", "required_documents"):
        d[field] = json.loads(d[field]) if d.get(field) else ["ALL"]
    return d


def get_all_schemes():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM schemes ORDER BY name").fetchall()
    conn.close()
    return [row_to_scheme(r) for r in rows]


def get_scheme(scheme_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM schemes WHERE id = ?", (scheme_id,)).fetchone()
    conn.close()
    return row_to_scheme(row) if row else None


# --------------------------------------------------------------------------
# User data (PostgreSQL when DATABASE_URL is set, otherwise SQLite)
# --------------------------------------------------------------------------

def get_user_connection():
    """Connection for accounts and case files. Rows support row['column']."""
    if USING_PG:
        import psycopg2
        import psycopg2.extras
        return psycopg2.connect(
            DATABASE_URL, connect_timeout=10,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return get_connection()


def user_sql(sql):
    """Write queries once with '?' placeholders; PostgreSQL needs '%s'."""
    return sql.replace("?", "%s") if USING_PG else sql


_user_tables_ready = False


def ensure_user_tables():
    """
    Create the users / case_files tables if they don't exist yet. Safe to call
    repeatedly and from several worker processes at once. If the database is
    unreachable this raises; callers decide how to degrade (guests keep working
    from their browser session).
    """
    global _user_tables_ready
    if _user_tables_ready:
        return

    conn = get_user_connection()
    try:
        cur = conn.cursor()
        if USING_PG:
            # Serialise table creation across gunicorn workers.
            cur.execute("SELECT pg_advisory_xact_lock(90210)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS case_files (
                    user_id INTEGER PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS case_files (
                    user_id INTEGER PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
        conn.commit()
        _user_tables_ready = True
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialised at {DB_PATH} with {len(get_all_schemes())} schemes.")

# -*- coding: utf-8 -*-
"""SQLite storage for the scheme database. Kept simple and file-based --
no external server needed, easy to inspect, easy to demo."""

import sqlite3
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "schemes.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the schemes table and populate it from data/schemes_data.py."""
    import sys
    sys.path.insert(0, BASE_DIR)
    from data.schemes_data import SCHEMES

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
            states TEXT,
            extra_conditions TEXT,
            required_documents TEXT,
            application_link TEXT
        )
    """)
    for s in SCHEMES:
        cur.execute("""
            INSERT INTO schemes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            s["id"], s["name"], s["category"], s["description"], s["benefit_summary"],
            s["min_age"], s["max_age"], s["income_max"], s["gender"],
            json.dumps(s["occupations"]), json.dumps(s["special_categories"]),
            json.dumps(s["states"]), s["extra_conditions"],
            json.dumps(s["required_documents"]), s["application_link"],
        ))
    conn.commit()
    conn.close()


def row_to_scheme(row):
    """Convert a sqlite Row into a plain dict with JSON fields decoded."""
    d = dict(row)
    for field in ("occupations", "special_categories", "states", "required_documents"):
        d[field] = json.loads(d[field])
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


if __name__ == "__main__":
    init_db()
    print(f"Database initialised at {DB_PATH} with {len(get_all_schemes())} schemes.")

# -*- coding: utf-8 -*-
"""
Persists the Case File for logged-in users so it survives across logins and
devices -- not just the current browser session. Guests (not logged in) still
get the session-based Case File; nothing about the anonymous flow is degraded.

Stored in PostgreSQL when DATABASE_URL is set, otherwise local SQLite.
Only a short progress summary is stored (scheme names, statuses), never an
uploaded document or the extracted name/DOB/address values.
"""

import json
from datetime import datetime
from models.db import get_user_connection, user_sql, ensure_user_tables


def save_case_file(user_id, data):
    ensure_user_tables()
    conn = get_user_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            user_sql(
                """INSERT INTO case_files (user_id, data, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT (user_id) DO UPDATE
                   SET data = excluded.data, updated_at = excluded.updated_at"""
            ),
            (user_id, json.dumps(data), datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def load_case_file(user_id):
    ensure_user_tables()
    conn = get_user_connection()
    try:
        cur = conn.cursor()
        cur.execute(user_sql("SELECT data FROM case_files WHERE user_id = ?"), (user_id,))
        row = cur.fetchone()
    finally:
        conn.close()
    return json.loads(row["data"]) if row else {}

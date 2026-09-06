# -*- coding: utf-8 -*-
"""
Persists the Case File to the database for logged-in users, so it survives
across logins/devices -- not just the current browser session. Guests
(not logged in) still get the session-based Case File as before; nothing
about the anonymous flow is degraded, this is a genuine upgrade layered
on top of it.
"""

import json
from datetime import datetime
from models.db import get_connection


def save_case_file(user_id, data):
    conn = get_connection()
    conn.execute(
        """INSERT INTO case_files (user_id, data, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at""",
        (user_id, json.dumps(data), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def load_case_file(user_id):
    conn = get_connection()
    row = conn.execute("SELECT data FROM case_files WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return json.loads(row["data"]) if row else {}

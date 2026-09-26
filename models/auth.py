# -*- coding: utf-8 -*-
"""
Simple, real authentication -- a users table with hashed passwords (never
stored in plain text). No third-party auth service, no vendor lock-in.

Accounts live in PostgreSQL when DATABASE_URL is set (so they survive Render
redeploys), or in the local SQLite file during development. See models/db.py.
"""

import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from models.db import USING_PG, get_user_connection, user_sql, ensure_user_tables


def init_auth_tables():
    """Kept for backwards compatibility with app.py; creates the tables."""
    ensure_user_tables()


def _is_duplicate_error(exc):
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    if USING_PG:
        import psycopg2
        return isinstance(exc, psycopg2.IntegrityError)
    return False


def create_user(username, password):
    """Returns the new user's id, or None if the username is already taken."""
    ensure_user_tables()
    conn = get_user_connection()
    try:
        cur = conn.cursor()
        sql = "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)"
        params = (username.strip(), generate_password_hash(password), datetime.now().isoformat())
        if USING_PG:
            cur.execute(user_sql(sql + " RETURNING id"), params)
            new_id = cur.fetchone()["id"]
        else:
            cur.execute(sql, params)
            new_id = cur.lastrowid
        conn.commit()
        return new_id
    except Exception as exc:
        conn.rollback()
        if _is_duplicate_error(exc):
            return None
        raise
    finally:
        conn.close()


def verify_login(username, password):
    """Returns the user's row (dict) if credentials are correct, else None."""
    ensure_user_tables()
    conn = get_user_connection()
    try:
        cur = conn.cursor()
        cur.execute(user_sql("SELECT * FROM users WHERE username = ?"), (username.strip(),))
        row = cur.fetchone()
    finally:
        conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None

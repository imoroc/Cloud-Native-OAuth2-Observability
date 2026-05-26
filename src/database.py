"""
database.py — SQLite schema initialization and connection helpers.

All OAuth2 state (clients, authorization codes, tokens) is stored in a
single SQLite database.  Flask's `g` object is used to cache one
connection per request; the connection is closed automatically at
teardown.
"""

import sqlite3
from pathlib import Path

from flask import g

DATABASE_PATH = Path(__file__).parent / "oauth2.db"


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    """Return a per-request database connection (cached on Flask `g`)."""
    if "db" not in g:
        g.db = sqlite3.connect(str(DATABASE_PATH))
        g.db.row_factory = sqlite3.Row          # rows behave like dicts
        g.db.execute("PRAGMA journal_mode=WAL")  # better concurrency
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(_exc=None) -> None:
    """Close the per-request connection (registered as teardown handler)."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Standalone connection (for scripts like seed.py that run outside Flask)
# ---------------------------------------------------------------------------

def get_standalone_db() -> sqlite3.Connection:
    """Return a plain connection — use this outside of a Flask request."""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    client_id       TEXT PRIMARY KEY,
    client_secret_hash TEXT NOT NULL,
    redirect_uris   TEXT NOT NULL DEFAULT '[]',   -- JSON array of allowed URIs
    grant_types     TEXT NOT NULL DEFAULT '[]',   -- JSON array: authorization_code, client_credentials, refresh_token
    client_name     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS authorization_codes (
    code            TEXT PRIMARY KEY,
    client_id       TEXT NOT NULL REFERENCES clients(client_id),
    redirect_uri    TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    scope           TEXT NOT NULL DEFAULT '',
    expires_at      REAL NOT NULL,
    used            INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tokens (
    token           TEXT PRIMARY KEY,
    token_type      TEXT NOT NULL CHECK(token_type IN ('access', 'refresh')),
    client_id       TEXT NOT NULL REFERENCES clients(client_id),
    user_id         TEXT,                          -- NULL for client_credentials
    scope           TEXT NOT NULL DEFAULT '',
    expires_at      REAL NOT NULL,
    revoked         INTEGER NOT NULL DEFAULT 0,
    -- Links an access token back to its refresh token (if any)
    associated_refresh_token TEXT
);
"""


def init_db() -> None:
    """Create tables if they do not already exist."""
    conn = get_standalone_db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()

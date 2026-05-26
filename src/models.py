""" 
models.py — Data-access helpers for clients, authorization codes, and tokens.

Every function receives (or obtains) a database connection and performs
one focused operation.  No HTTP/Flask-specific logic lives here so the
module stays testable in isolation.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Optional

from database import get_db, get_standalone_db


# ---------------------------------------------------------------------------
# Hashing helper (SHA-256 — adequate for a demo; use bcrypt in production)
# ---------------------------------------------------------------------------


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# Clients
# ═══════════════════════════════════════════════════════════════════════════


def create_client(
    client_id: str,
    client_secret: str,
    redirect_uris: list[str],
    grant_types: list[str],
    client_name: str = "",
    *,
    conn=None,
) -> None:
    """Insert a new client.  *conn* allows use outside a Flask request."""
    db = conn or get_db()
    db.execute(
        """
        INSERT OR REPLACE INTO clients
            (client_id, client_secret_hash, redirect_uris, grant_types, client_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            client_id,
            _hash_secret(client_secret),
            json.dumps(redirect_uris),
            json.dumps(grant_types),
            client_name,
        ),
    )
    db.commit()


def get_client(client_id: str, *, conn=None) -> Optional[dict]:
    """Fetch a client by ID.  Returns a plain dict or None."""
    db = conn or get_db()
    row = db.execute(
        "SELECT * FROM clients WHERE client_id = ?", (client_id,)
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["redirect_uris"] = json.loads(data["redirect_uris"])
    data["grant_types"] = json.loads(data["grant_types"])
    return data


def list_clients(*, conn=None) -> list[dict]:
    """Return all registered clients (without secret hashes)."""
    db = conn or get_db()
    rows = db.execute(
        "SELECT client_id, redirect_uris, grant_types, client_name FROM clients"
    ).fetchall()
    clients = []
    for row in rows:
        data = dict(row)
        data["redirect_uris"] = json.loads(data["redirect_uris"])
        data["grant_types"] = json.loads(data["grant_types"])
        clients.append(data)
    return clients


def delete_client(client_id: str, *, conn=None) -> bool:
    """
    Delete a client and all associated authorization codes and tokens.
    Returns True if the client existed, False otherwise.
    """
    db = conn or get_db()
    # Check existence first
    existing = db.execute(
        "SELECT 1 FROM clients WHERE client_id = ?", (client_id,)
    ).fetchone()
    if existing is None:
        return False
    # Delete associated data (tokens, auth codes) then the client
    db.execute("DELETE FROM tokens WHERE client_id = ?", (client_id,))
    db.execute("DELETE FROM authorization_codes WHERE client_id = ?", (client_id,))
    db.execute("DELETE FROM clients WHERE client_id = ?", (client_id,))
    db.commit()
    return True


def verify_client_secret(client_id: str, secret: str) -> bool:
    """Return True if *secret* matches the stored hash for *client_id*."""
    client = get_client(client_id)
    if client is None:
        return False
    return client["client_secret_hash"] == _hash_secret(secret)


# ═══════════════════════════════════════════════════════════════════════════
# Authorization codes
# ═══════════════════════════════════════════════════════════════════════════


def store_authorization_code(
    client_id: str,
    redirect_uri: str,
    user_id: str,
    scope: str,
    ttl: int = 600,
) -> str:
    """
    Generate and persist an authorization code.

    The code is a cryptographically random opaque string.  It expires
    after *ttl* seconds (default 10 minutes, the RFC 6749 maximum).
    Returns the code.
    """
    code = secrets.token_urlsafe(32)
    expires_at = time.time() + ttl
    db = get_db()
    db.execute(
        """
        INSERT INTO authorization_codes
            (code, client_id, redirect_uri, user_id, scope, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (code, client_id, redirect_uri, user_id, scope, expires_at),
    )
    db.commit()
    return code


def consume_authorization_code(code: str) -> Optional[dict]:
    """
    Validate and consume an authorization code (single-use).

    Returns a dict with the code's metadata on success, or None if the
    code is invalid, expired, or already used.
    """
    db = get_db()
    row = db.execute(
        "SELECT * FROM authorization_codes WHERE code = ?", (code,)
    ).fetchone()

    if row is None:
        return None

    data = dict(row)

    # Already used — RFC 6749 §4.1.2 requires single-use codes
    if data["used"]:
        return None

    # Expired
    if time.time() > data["expires_at"]:
        return None

    # Mark as used
    db.execute("UPDATE authorization_codes SET used = 1 WHERE code = ?", (code,))
    db.commit()
    return data


# ═══════════════════════════════════════════════════════════════════════════
# Tokens (access + refresh)
# ═══════════════════════════════════════════════════════════════════════════

_ACCESS_TOKEN_TTL = 3600  # 1 hour
_REFRESH_TOKEN_TTL = 30 * 86400  # 30 days


def issue_token_pair(
    client_id: str,
    scope: str,
    user_id: Optional[str] = None,
    include_refresh: bool = True,
) -> dict:
    """
    Create an access token (and optionally a refresh token) and persist
    both in the database.

    Returns a dict ready to be serialised as the OAuth2 token response:
        {
            "access_token": "...",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "...",
            "refresh_token": "..."   # omitted when include_refresh=False
        }
    """
    access_token = secrets.token_urlsafe(48)
    refresh_token = secrets.token_urlsafe(48) if include_refresh else None
    now = time.time()

    db = get_db()

    # Store refresh token first (if any) so we can reference it
    if refresh_token:
        db.execute(
            """
            INSERT INTO tokens
                (token, token_type, client_id, user_id, scope, expires_at)
            VALUES (?, 'refresh', ?, ?, ?, ?)
            """,
            (refresh_token, client_id, user_id, scope, now + _REFRESH_TOKEN_TTL),
        )

    db.execute(
        """
        INSERT INTO tokens
            (token, token_type, client_id, user_id, scope, expires_at,
             associated_refresh_token)
        VALUES (?, 'access', ?, ?, ?, ?, ?)
        """,
        (
            access_token,
            client_id,
            user_id,
            scope,
            now + _ACCESS_TOKEN_TTL,
            refresh_token,
        ),
    )

    db.commit()

    response = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": _ACCESS_TOKEN_TTL,
        "scope": scope,
    }
    if refresh_token:
        response["refresh_token"] = refresh_token
    return response


def validate_refresh_token(token: str) -> Optional[dict]:
    """
    Look up a refresh token.  Returns its metadata dict if the token
    exists, is not expired, and is not revoked.  Otherwise returns None.
    """
    db = get_db()
    row = db.execute(
        "SELECT * FROM tokens WHERE token = ? AND token_type = 'refresh'",
        (token,),
    ).fetchone()

    if row is None:
        return None

    data = dict(row)

    if data["revoked"]:
        return None
    if time.time() > data["expires_at"]:
        return None

    return data


def revoke_refresh_token(token: str) -> None:
    """Mark a refresh token (and its associated access tokens) as revoked."""
    db = get_db()
    # Revoke the refresh token itself
    db.execute("UPDATE tokens SET revoked = 1 WHERE token = ?", (token,))
    # Revoke any access tokens linked to this refresh token
    db.execute(
        "UPDATE tokens SET revoked = 1 WHERE associated_refresh_token = ?",
        (token,),
    )
    db.commit()

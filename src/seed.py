"""
seed.py — Populate the database with test clients.

Run with:  uv run python seed.py
 
Creates two clients:
  1. "web-app"         — supports authorization_code + refresh_token
  2. "service-account" — supports client_credentials only
"""

import secrets

from database import init_db, get_standalone_db
from models import create_client


def main() -> None:
    # Ensure tables exist
    init_db()

    conn = get_standalone_db()

    # --- Web application client (authorization code flow) ---
    web_secret = secrets.token_urlsafe(32)
    create_client(
        client_id="web-app",
        client_secret=web_secret,
        redirect_uris=["http://localhost:8080/callback"],
        grant_types=["authorization_code", "refresh_token"],
        client_name="Demo Web Application",
        conn=conn,
    )

    # --- Service account client (client credentials flow) ---
    svc_secret = secrets.token_urlsafe(32)
    create_client(
        client_id="service-account",
        client_secret=svc_secret,
        redirect_uris=[],
        grant_types=["client_credentials"],
        client_name="Background Service",
        conn=conn,
    )

    conn.close()

    print("Seeded test clients:\n")
    print(f"  Client: web-app")
    print(f"  Secret: {web_secret}")
    print(f"  Grants: authorization_code, refresh_token")
    print(f"  Redirect URIs: http://localhost:8080/callback")
    print()
    print(f"  Client: service-account")
    print(f"  Secret: {svc_secret}")
    print(f"  Grants: client_credentials")
    print()
    print("Save these secrets — they cannot be recovered from the database.")


if __name__ == "__main__":
    main()

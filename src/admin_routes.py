"""
admin_routes.py — Unprotected admin endpoints for managing OAuth2 clients.
 
Implements:
    GET    /admin/clients            — list all registered clients
    POST   /admin/clients            — register a new client
    DELETE /admin/clients/<client_id> — delete a client and its associated data

These endpoints have NO authentication and are intended for development /
internal use only.  Do NOT expose them in production without adding proper
access controls.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import create_client, delete_client, get_client, list_clients

admin = Blueprint("admin", __name__, url_prefix="/admin")


# ── List all clients ────────────────────────────────────────────────────
@admin.route("/clients", methods=["GET"])
def clients_list():
    """Return every registered client (secrets are never exposed)."""
    clients = list_clients()
    return jsonify(clients), 200


# ── Register a new client ───────────────────────────────────────────────
@admin.route("/clients", methods=["POST"])
def clients_create():
    """
    Create a new OAuth2 client.

    Expected JSON body:
        {
            "client_id":     "my-app",
            "client_secret": "s3cret",
            "redirect_uris": ["http://localhost:3000/callback"],
            "grant_types":   ["authorization_code", "refresh_token"],
            "client_name":   "My Application"       // optional
        }
    """
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "request body must be JSON"}), 400

    # --- Validate required fields -------------------------------------------
    missing = [
        f
        for f in ("client_id", "client_secret", "redirect_uris", "grant_types")
        if f not in data
    ]
    if missing:
        return jsonify({"error": f"missing required fields: {', '.join(missing)}"}), 400

    client_id = data["client_id"]
    if not isinstance(client_id, str) or not client_id.strip():
        return jsonify({"error": "client_id must be a non-empty string"}), 400

    if not isinstance(data["client_secret"], str) or not data["client_secret"]:
        return jsonify({"error": "client_secret must be a non-empty string"}), 400

    if not isinstance(data["redirect_uris"], list):
        return jsonify({"error": "redirect_uris must be a list"}), 400

    if not isinstance(data["grant_types"], list):
        return jsonify({"error": "grant_types must be a list"}), 400

    # Reject duplicates
    if get_client(client_id) is not None:
        return jsonify({"error": f"client '{client_id}' already exists"}), 409

    create_client(
        client_id=client_id,
        client_secret=data["client_secret"],
        redirect_uris=data["redirect_uris"],
        grant_types=data["grant_types"],
        client_name=data.get("client_name", ""),
    )

    return jsonify({"message": f"client '{client_id}' created"}), 201


# ── Delete a client ─────────────────────────────────────────────────────
@admin.route("/clients/<client_id>", methods=["DELETE"])
def clients_delete(client_id: str):
    """Delete a client and all its associated auth codes and tokens."""
    deleted = delete_client(client_id)
    if not deleted:
        return jsonify({"error": f"client '{client_id}' not found"}), 404

    return jsonify({"message": f"client '{client_id}' deleted"}), 200

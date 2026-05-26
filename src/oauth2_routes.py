"""
oauth2_routes.py — Endpoints principales de OAuth2.
 
Implementa:
    GET  /authorize  — Muestra el formulario de login (Authorization Code)
    POST /authorize  — Procesa credenciales del usuario y genera el Code
    POST /token      — Intercambia grants por tokens reales (Tokens endpoint)

Los errores siguen el estándar estricto RFC 6749.
"""

from __future__ import annotations
import base64
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

from flask import Blueprint, current_app, redirect, render_template, request, jsonify

# Importaciones locales de lógica de DB y métricas
from models import (
    get_client, verify_client_secret, store_authorization_code,
    consume_authorization_code, issue_token_pair, validate_refresh_token,
    revoke_refresh_token,
)
from metrics import oauth2_flows_total, oauth2_tokens_issued_total

oauth2 = Blueprint("oauth2", __name__)

# ---------------------------------------------------------------------------
# Helpers de respuesta y seguridad
# ---------------------------------------------------------------------------

def _error_response(error: str, description: str, status: int = 400):
    """Devuelve un error JSON siguiendo RFC 6749"""
    print(f"[OAuth2 Error] {error}: {description} (Status {status})")
    return jsonify({"error": error, "error_description": description}), status

def _redirect_with_error(redirect_uri: str, error: str, description: str, state: str | None):
    """Redirige al cliente añadiendo el error en la query string."""
    params = {"error": error, "error_description": description}
    if state:
        params["state"] = state
    return redirect(_append_query(redirect_uri, params))

def _append_query(url: str, params: dict) -> str:
    """Añade parámetros a una URL de forma segura."""
    parts = list(urlparse(url))
    existing = parse_qs(parts[4])
    existing.update(params)
    parts[4] = urlencode(existing, doseq=True)
    return urlunparse(parts)

def _authenticate_client() -> tuple[str, None] | tuple[None, str]:
    """
    Autentica la Aplicación Cliente (App de terceros).
    Soporta HTTP Basic auth y POST body (RFC 6749).
    """
    # 1. Intentar HTTP Basic (El método preferido y más seguro)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth_header[6:]).decode()
            client_id, client_secret = decoded.split(":", 1)
        except Exception:
            return None, "Cabecera de Authorization malformada"
        if not verify_client_secret(client_id, client_secret):
            return None, "Credenciales de cliente inválidas (Basic)"
        return client_id, None

    # 2. Intentar POST body (Fallback para clientes sencillos)
    client_id = request.form.get("client_id")
    client_secret = request.form.get("client_secret")
    if client_id and client_secret:
        if not verify_client_secret(client_id, client_secret):
            return None, "Credenciales de cliente inválidas (POST)"
        return client_id, None

    return None, "Se requiere autenticación de cliente"


# ═══════════════════════════════════════════════════════════════════════════
# GET /authorize — Pantalla de Login
# ═══════════════════════════════════════════════════════════════════════════

@oauth2.route("/authorize", methods=["GET"])
def authorize_get():
    # Validaciones obligatorias de parámetros
    response_type = request.args.get("response_type")
    client_id = request.args.get("client_id")
    redirect_uri = request.args.get("redirect_uri")
    scope = request.args.get("scope", "")
    state = request.args.get("state")

    if not response_type or response_type != "code":
        return _error_response("unsupported_response_type", "Solo response_type=code está soportado")
    if not client_id:
        return _error_response("invalid_request", "Falta client_id")

    client = get_client(client_id)
    if not client:
        return _error_response("invalid_request", "client_id desconocido")

    if "authorization_code" not in client["grant_types"]:
        return _error_response("unauthorized_client", "Cliente no autorizado para este flujo")

    if not redirect_uri or redirect_uri not in client["redirect_uris"]:
        return _error_response("invalid_request", "redirect_uri inválido o no registrado")

    # Todo correcto: Registramos el inicio del flujo y mostramos formulario
    print(f"[Flujo Autorización] Iniciado por cliente: {client_id}")
    oauth2_flows_total.labels(flow_type='authorization_code', status='started').inc()
    
    return render_template(
        "login_consent.html",
        client_name=client["client_name"] or client_id,
        scope=scope,
        client_id=client_id,
        redirect_uri=redirect_uri,
        response_type=response_type,
        state=state or "",
    )


# ═══════════════════════════════════════════════════════════════════════════
# POST /authorize — Procesa el Login
# ═══════════════════════════════════════════════════════════════════════════

@oauth2.route("/authorize", methods=["POST"])
def authorize_post():
    # Recuperamos parámetros ocultos
    client_id = request.form.get("client_id", "")
    redirect_uri = request.form.get("redirect_uri", "")
    scope = request.form.get("scope", "")
    state = request.form.get("state", "")

    # Re-validar cliente por seguridad
    client = get_client(client_id)
    if client is None or redirect_uri not in (client or {}).get("redirect_uris", []):
        return _error_response("invalid_request", "Cliente o URI inválidos durante POST")

    # Si el usuario pulsó el botón de "Denegar acceso"
    if request.form.get("action") == "deny":
        print(f"[Login] Usuario denegó acceso al cliente: {client_id}")
        return _redirect_with_error(redirect_uri, "access_denied", "Usuario denegó la petición", state)

    # Validar usuario y contraseña del recurso
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    users: dict = current_app.config["USERS"]
    if username not in users or users[username] != password:
        # CONTADOR PROMETHEUS: Fallo de login
        print(f"[Login Fallido] Intento incorrecto para usuario: {username}")
        oauth2_flows_total.labels(flow_type='authorization_code', status='failed').inc()
        
        return render_template(
            "login_consent.html",
            client_name=client["client_name"] or client_id,
            scope=scope,
            client_id=client_id,
            redirect_uri=redirect_uri,
            response_type="code",
            state=state,
            error="Usuario o contraseña incorrectos.",
        ), 401

    # Login correcto: Generamos el 'authorization_code' en base de datos
    code = store_authorization_code(
        client_id=client_id,
        redirect_uri=redirect_uri,
        user_id=username,
        scope=scope,
    )

    # CONTADOR PROMETHEUS: Éxito
    print(f"[Login Exitoso] Code generado para {username}")
    oauth2_flows_total.labels(flow_type='authorization_code', status='success').inc()

    params = {"code": code}
    if state:
        params["state"] = state
    return redirect(_append_query(redirect_uri, params))


# ═══════════════════════════════════════════════════════════════════════════
# POST /token — El cliente intercambia su prueba por un Token real
# ═══════════════════════════════════════════════════════════════════════════

@oauth2.route("/token", methods=["POST"])
def token():
    grant_type = request.form.get("grant_type")

    if not grant_type:
        return _error_response("invalid_request", "Falta grant_type")

    # Delegamos al handler correspondiente según el tipo de flujo
    if grant_type == "authorization_code":
        response = _handle_authorization_code()
    elif grant_type == "client_credentials":
        response = _handle_client_credentials()
    elif grant_type == "refresh_token":
        response = _handle_refresh_token()
    else:
        return _error_response("unsupported_grant_type", f"Grant type '{grant_type}' no soportado")

    # Extraer status code de la respuesta
    status_code = response[1] if isinstance(response, tuple) else getattr(response, 'status_code', 200)

    # CONTADOR PROMETHEUS: Solo contamos tokens emitidos si fue OK (200)
    if status_code == 200:
        print(f"[Token Emitido] Flujo exitoso: {grant_type}")
        oauth2_tokens_issued_total.labels(grant_type=grant_type).inc()

    return response

# ----------- Handlers Internos para /token -----------

def _handle_authorization_code():
    client_id, err = _authenticate_client()
    if err: return _error_response("invalid_client", err, 401)
    
    code_value = request.form.get("code")
    redirect_uri = request.form.get("redirect_uri")
    
    if not code_value or not redirect_uri:
        return _error_response("invalid_request", "Faltan parámetros en authorization_code")

    code_data = consume_authorization_code(code_value)
    if not code_data:
        return _error_response("invalid_grant", "Código expirado, inválido o usado")

    if code_data["redirect_uri"] != redirect_uri or code_data["client_id"] != client_id:
        return _error_response("invalid_grant", "Mismatched client_id o redirect_uri")

    token_response = issue_token_pair(client_id, code_data["scope"], code_data["user_id"], True)
    return jsonify(token_response)

def _handle_client_credentials():
    client_id, err = _authenticate_client()
    if err: return _error_response("invalid_client", err, 401)
    
    client = get_client(client_id)
    if not client or "client_credentials" not in client["grant_types"]:
        return _error_response("unauthorized_client", "No autorizado para client_credentials")

    scope = request.form.get("scope", "")
    # client_credentials nunca debe devolver refresh_token por seguridad
    token_response = issue_token_pair(client_id, scope, None, False)
    return jsonify(token_response)

def _handle_refresh_token():
    client_id, err = _authenticate_client()
    if err: return _error_response("invalid_client", err, 401)

    refresh_token_value = request.form.get("refresh_token")
    if not refresh_token_value: return _error_response("invalid_request", "Falta refresh_token")

    token_data = validate_refresh_token(refresh_token_value)
    if not token_data or token_data["client_id"] != client_id:
        return _error_response("invalid_grant", "Refresh token inválido o de otro cliente")

    # Rotación de tokens, revocamos el viejo y damos uno nuevo
    revoke_refresh_token(refresh_token_value)
    requested_scope = request.form.get("scope", token_data["scope"])
    
    token_response = issue_token_pair(client_id, requested_scope, token_data["user_id"], True)
    return jsonify(token_response)

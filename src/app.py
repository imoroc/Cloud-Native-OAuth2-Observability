"""
app.py — Punto de entrada de la aplicación Flask (Backend OAuth2).

Conecta la base de datos, registra los blueprints de rutas, y levanta
el servidor WSGI inyectando la monitorización de Prometheus.
Ejecutar con:  uv run python app.py
"""

from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app

# Importaciones locales
from database import close_db, init_db
from oauth2_routes import oauth2
from admin_routes import admin
from metrics import setup_metrics

# ---------------------------------------------------------------------------
# Usuarios de prueba
# ---------------------------------------------------------------------------
USERS = {
    "testuser": "testpass",
    "admin": "adminpass",
}

def create_app() -> Flask:
    """Fábrica de la aplicación Flask."""
    app = Flask(__name__)
    app.secret_key = "dev-secret-key-change-in-production"

    # Inyectar los usuarios en la config para que las rutas puedan validarlos
    app.config["USERS"] = USERS

    # Registrar grupos de rutas
    app.register_blueprint(oauth2)
    app.register_blueprint(admin)

    # Ciclo de vida: cerrar conexión DB cuando acaba la petición
    app.teardown_appcontext(close_db)

    # ---------------------------------------------------------
    # MONITOREO DE PROMETHEUS
    # ---------------------------------------------------------
    # 1. Inyectamos el medidor automático de latencia y peticiones
    setup_metrics(app)

    # 2. Usamos DispatcherMiddleware para que el /metrics funcione 
    # por debajo de Flask y no se bloquee.
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
        '/metrics': make_wsgi_app()
    })

    # Asegurarnos de que las tablas SQLite existen al arrancar
    with app.app_context():
        try:
            init_db()
            print("[Base de Datos] Tablas SQLite comprobadas/creadas con éxito.")
        except Exception as e:
            print(f"[ERROR Base de Datos] Fallo al inicializar: {e}")

    return app

if __name__ == "__main__":
    application = create_app()
    
    print("\n" + "="*50)
    print("Servidor OAuth2 en ejecución: http://localhost:5001")
    print("="*50)
    print("Endpoints Disponibles:")
    print("  GET    /authorize          — Flujo Auth Code (navegador)")
    print("  POST   /token              — Emisión de Tokens (API)")
    print("  GET    /admin/clients      — Ver clientes registrados")
    print("  GET    /metrics            — Métricas Prometheus crudas")
    print("="*50 + "\n")
    
    from werkzeug.serving import run_simple
    
    # threaded=True permite atender a Prometheus mientras Locust ataca
    run_simple('0.0.0.0', 5001, application, use_reloader=True, use_debugger=True, threaded=True)

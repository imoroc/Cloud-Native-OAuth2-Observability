""" 
metrics.py — Centralización de métricas de Prometheus.

Este módulo define todas las métricas que serán expuestas en el endpoint /metrics.
"""

from prometheus_client import Counter, Histogram
from flask import request
import time

# ============================================================================
# 1. MÉTRICAS GENERALES HTTP
# ============================================================================

# Cuenta cuántas peticiones llegan, separando por método, ruta y si dan error.
http_requests_total = Counter(
    'http_requests_total',
    'Total de peticiones HTTP procesadas',
    ['method', 'endpoint', 'status_code']
)

# Mide cuanto tardan las peticiones (Vital para calcular el Percentil 95 en Grafana)
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'Latencia de las peticiones HTTP en segundos',
    ['endpoint']
)

# ============================================================================
# 2. MÉTRICAS DE NEGOCIO OAUTH2
# ============================================================================

# Cuenta cuántos flujos de login ocurren (y si tienen éxito o fallan por mala contraseña)
oauth2_flows_total = Counter(
    'oauth2_flows_total',
    'Flujos de autenticación OAuth2',
    ['flow_type', 'status']
)

# Cuenta el ritmo de generación de tokens, separando por el tipo de flujo
oauth2_tokens_issued_total = Counter(
    'oauth2_tokens_issued_total',
    'Tokens de acceso emitidos exitosamente',
    ['grant_type']
)

# ============================================================================
# 3. MIDDLEWARE DE FLASK
# ============================================================================

def setup_metrics(app):
    """
    Inyecta hooks en Flask para medir todas las peticiones HTTP de forma automática.
    De esta forma, no ensuciamos el código de las rutas con contadores manuales.
    """
    print("[Métricas] Middleware de Prometheus inicializado y acoplado a Flask.")

    @app.before_request
    def before_request():
        # Guardamos el momento exacto en el que entra la petición
        request.start_time = time.time()

    @app.after_request
    def after_request(response):
        # 1. Calcular el tiempo que ha tardado en procesarse (Latencia)
        duration = time.time() - getattr(request, 'start_time', time.time())
        
        # 2. Identificar qué ruta se ha visitado
        endpoint = request.endpoint if request.endpoint else request.path

        # 3. Incrementar el contador general de peticiones HTTP
        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code
        ).inc()

        # 4. Guardar el tiempo de respuesta en el Histograma
        http_request_duration_seconds.labels(
            endpoint=endpoint
        ).observe(duration)

        return response

import os
import random
from urllib.parse import urlparse, parse_qs
from locust import FastHttpUser, task, between

# =========================================================================
# LECTOR AUTOMÁTICO DE CREDENCIALES
# =========================================================================
WEB_APP_SECRET = None
SERVICE_ACCOUNT_SECRET = None

try:
    with open("credencialesActuales.txt", "r", encoding="utf-8") as f:
        current_client = None
        for line in f:
            if "Client: web-app" in line:
                current_client = "web-app"
            elif "Client: service-account" in line:
                current_client = "service-account"
            elif "Secret:" in line and current_client:
                secret_val = line.split("Secret:")[1].strip()
                if current_client == "web-app":
                    WEB_APP_SECRET = secret_val
                elif current_client == "service-account":
                    SERVICE_ACCOUNT_SECRET = secret_val
                current_client = None
except FileNotFoundError:
    print("No se encontró credencialesActuales.txt. Locust fallará si no están los secretos")


# =========================================================================
# COMPORTAMIENTO DE LOS USUARIOS VIRTUALES
# =========================================================================
class OAuth2User(FastHttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Comprobación de seguridad y preparación de memoria del usuario."""
        if not SERVICE_ACCOUNT_SECRET or not WEB_APP_SECRET:
            raise RuntimeError(
                "Faltan los secretos. Asegúrate de haber ejecutado:\n"
                "uv run python seed.py > credencialesActuales.txt"
            )
        # Cada usuario virtual tendrá su propia variable para guardar su refresh_token
        self.refresh_token = None


    # =========================================================================
    # FLUJO 1: Authorization Code 
    # =========================================================================
    @task(2)
    def flow_authorization_code(self):
        """Simula a un humano abriendo el navegador, logueándose y obteniendo un token."""
        
        # 1. Carga la página de Login (Suma "started" en Grafana)
        self.client.get(
            "/authorize?response_type=code&client_id=web-app&redirect_uri=http://localhost:8080/callback",
            name="/authorize GET (Cargar formulario)"
        )

        # Simulamos que un 15% de las veces el usuario se equivoca de contraseña
        is_success = random.random() > 0.15 
        password = "testpass" if is_success else "wrong_password"

        # 2. Envía el formulario de login. Desactivamos los redireccionamientos automáticos 
        # (allow_redirects=False) para atrapar el "code" que nos devuelve Flask.
        with self.client.post(
            "/authorize",
            data={
                "client_id": "web-app",
                "redirect_uri": "http://localhost:8080/callback",
                "response_type": "code",
                "username": "testuser",
                "password": password
            },
            name="/authorize POST (Login)",
            allow_redirects=False,
            catch_response=True
        ) as login_response:
            
            # Si se equivocó de contraseña a propósito, Flask devuelve 401.
            if not is_success:
                if login_response.status_code == 401:
                    login_response.success()
                return

            # Si acertó la contraseña, Flask nos devuelve un 302 con la URL de redirección
            if login_response.status_code == 302:
                location = login_response.headers.get("Location", "")
                
                # Extraemos el código de la URL
                parsed_url = urlparse(location)
                query_params = parse_qs(parsed_url.query)
                
                if "code" in query_params:
                    auth_code = query_params["code"][0]
                    login_response.success()
                else:
                    login_response.failure("Falta el código en la URL de redirección")
                    return
            else:
                login_response.failure(f"Se esperaba 302, se obtuvo {login_response.status_code}")
                return

        # 3. Intercambiamos el "code" por el Token real
        with self.client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": "http://localhost:8080/callback",
                "client_id": "web-app",
                "client_secret": WEB_APP_SECRET
            },
            name="/token (Auth Code -> Token)",
            catch_response=True
        ) as token_response:
            if token_response.status_code == 200:
                body = token_response.json()
                if "refresh_token" in body:
                    self.refresh_token = body["refresh_token"] # Lo guardamos para el flujo 3
                token_response.success()
            else:
                token_response.failure("Fallo al canjear el authorization code")


    # =========================================================================
    # FLUJO 2: Client Credentials 
    # =========================================================================
    @task(3)
    def flow_client_credentials(self):
        """Simula una app backend pidiendo acceso directamente."""
        payload = {
            "grant_type": "client_credentials",
            "client_id": "service-account",
            "client_secret": SERVICE_ACCOUNT_SECRET,
            "scope": "read",
        }
        with self.client.post(
            "/token", data=payload, name="/token (Client Credentials)", catch_response=True
        ) as response:
            if response.status_code == 200 and "access_token" in response.text:
                response.success()
            else:
                response.failure(f"Fallo emitiendo token: HTTP {response.status_code}")


    # =========================================================================
    # FLUJO 3: Refresh Token
    # =========================================================================
    @task(1)
    def flow_refresh_token(self):
        """Si el usuario virtual tiene un refresh_token guardado, intenta renovarlo."""
        if not self.refresh_token:
            return # Si aún no tiene uno, ignora esta tarea

        with self.client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": "web-app",
                "client_secret": WEB_APP_SECRET
            },
            name="/token (Refresh Token)",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                body = response.json()
                if "refresh_token" in body:
                    self.refresh_token = body["refresh_token"] # Actualizamos al nuevo token rotado
                response.success()
            else:
                # Si falló, lo borramos de la memoria
                response.failure(f"Fallo al renovar token: HTTP {response.status_code}")
                self.refresh_token = None

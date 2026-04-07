#!/usr/bin/env python3
"""
Setup OAuth simplificado - manejo manual del flujo.
"""

import os
import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/credentials/credentials.json")
TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "/app/credentials/token.json")

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
]

auth_code_global = None
auth_error = None


class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code_global, auth_error

        query = urlparse(self.path).query
        params = parse_qs(query)

        if "code" in params:
            auth_code_global = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1>Autorizacion exitosa!</h1>
                    <p>Podes cerrar esta ventana y volver a la terminal.</p>
                </body>
                </html>
            """
            self.wfile.write(html.encode('utf-8'))
        elif "error" in params:
            auth_error = params.get("error_description", ["Error desconocido"])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(f"<html><body><h1>Error: {auth_error}</h1></body></html>".encode())

    def log_message(self, format, *args):
        pass  # Silenciar logs


def main():
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"❌ No existe {CREDENTIALS_PATH}")
        return

    print("\n" + "="*70)
    print("OAUTH SETUP - Del Castillo Bot")
    print("="*70 + "\n")

    try:
        with open(CREDENTIALS_PATH) as f:
            creds_data = json.load(f)

        print("📋 Credenciales encontradas:")
        print(f"   Client ID: {creds_data.get('client_id', 'N/A')[:30]}...")
        print(f"   Type: {creds_data.get('type', 'unknown')}\n")

        # Crear flow
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_PATH,
            scopes=SCOPES,
            redirect_uri="http://localhost:9090/"
        )

        # Generar URL de autorización
        auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")

        print("🌐 Abriendo navegador para autorización...\n")
        print(f"URL: {auth_url}\n")

        webbrowser.open(auth_url)

        # Esperar por el código
        global auth_code_global
        print("⏳ Esperando autorización (abriendo servidor en :9090)...")

        server = HTTPServer(("0.0.0.0", 9090), OAuthHandler)
        server.handle_request()

        if auth_code_global:
            print(f"✅ Código recibido\n")
            print("⏳ Intercambiando por token...")

            creds = flow.fetch_token(code=auth_code_global)

            os.makedirs(os.path.dirname(TOKEN_PATH) or ".", exist_ok=True)
            with open(TOKEN_PATH, "w") as f:
                json.dump(creds, f, indent=2)

            print(f"✅ Token guardado en {TOKEN_PATH}\n")
            print("🚀 Próximo paso:")
            print("   docker compose down")
            print("   docker compose up\n")

        else:
            print(f"❌ No se recibió código. Error: {auth_error}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

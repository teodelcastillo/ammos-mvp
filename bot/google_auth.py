import os
import json
import base64
import tempfile
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request

CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/credentials/credentials.json")
TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "/app/credentials/token.json")


def _ensure_file_from_env(path: str, env_var: str):
    """Si el archivo no existe pero hay una variable de entorno en base64, lo crea."""
    if not os.path.exists(path):
        encoded = os.getenv(env_var)
        if encoded:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # Add padding if stripped (common when copy-pasting base64)
            encoded += "=" * (4 - len(encoded) % 4)
            with open(path, "w") as f:
                f.write(base64.b64decode(encoded).decode("utf-8"))


# Intentar crear archivos desde variables de entorno si no existen
_ensure_file_from_env(CREDENTIALS_PATH, "GOOGLE_CREDENTIALS_JSON")
_ensure_file_from_env(TOKEN_PATH, "GOOGLE_TOKEN_JSON")

ALL_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_credentials():
    """
    Obtiene credenciales de Google.
    Soporta tanto Service Account como OAuth.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Primero, verificar si existe token.json (OAuth)
    if os.path.exists(TOKEN_PATH):
        try:
            logger.info(f"Cargando token.json desde {TOKEN_PATH}")

            with open(TOKEN_PATH) as f:
                token_data = json.load(f)

            # client_id/client_secret may not be in the token file (requests_oauthlib format)
            # Fall back to credentials.json
            client_id = token_data.get("client_id")
            client_secret = token_data.get("client_secret")
            if (not client_id or not client_secret) and os.path.exists(CREDENTIALS_PATH):
                with open(CREDENTIALS_PATH) as f:
                    creds_data = json.load(f)
                # Support both "installed" (Desktop) and "web" credential formats
                oauth_info = creds_data.get("installed") or creds_data.get("web") or creds_data
                client_id = client_id or oauth_info.get("client_id")
                client_secret = client_secret or oauth_info.get("client_secret")

            creds = Credentials(
                token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=ALL_SCOPES
            )
            logger.info(f"Token cargado. Valid: {creds.valid}, Expired: {creds.expired}")

            # Refrescar si está expirado
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refrescando token...")
                creds.refresh(Request())
                with open(TOKEN_PATH, "w") as f:
                    f.write(creds.to_json())
                logger.info("Token refrescado")

            if creds and creds.valid:
                logger.info("Retornando credenciales OAuth válidas")
                return creds
            else:
                logger.warning(f"Token no válido. Valid={creds.valid}")
        except Exception as e:
            logger.error(f"Error cargando token.json: {e}", exc_info=True)

    # Si no hay token.json válido, intentar Service Account
    if not os.path.exists(CREDENTIALS_PATH):
        raise Exception(
            f"Credenciales no encontradas en {CREDENTIALS_PATH}. "
            "Ejecutá: docker compose run --rm bot python setup_oauth_simple.py"
        )

    # Verificar si es Service Account
    with open(CREDENTIALS_PATH) as f:
        creds_data = json.load(f)

    if creds_data.get("type") == "service_account":
        # Service Account
        return service_account.Credentials.from_service_account_file(
            CREDENTIALS_PATH, scopes=ALL_SCOPES
        )

    # Si es OAuth pero no hay token, pedir que haga setup
    raise Exception(
        "Token de Google no encontrado. "
        "Ejecutá: docker compose run --rm bot python setup_oauth_simple.py"
    )

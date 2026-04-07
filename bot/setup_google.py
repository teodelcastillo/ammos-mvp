"""
Script para autenticarse con Google OAuth.
Ejecutar una sola vez antes de iniciar el bot:

    docker compose run --rm -p 9090:9090 bot python setup_google.py
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow

CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/credentials/credentials.json")
TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "/app/credentials/token.json")

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
]


def main():
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"ERROR: No se encontró {CREDENTIALS_PATH}")
        print()
        print("Pasos para obtener las credenciales:")
        print("1. Ir a https://console.cloud.google.com/")
        print("2. Crear un proyecto (o usar uno existente)")
        print("3. Habilitar Google Calendar API y Google Drive API")
        print("4. Ir a Credenciales > Crear credenciales > ID de cliente OAuth")
        print("5. Tipo: Aplicación de escritorio")
        print("6. Descargar el JSON y guardarlo como credentials/credentials.json")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)

    print("\n" + "="*50)
    print("AUTORIZACIÓN DE GOOGLE")
    print("="*50)
    print("\nSiguiendo estos pasos:")
    print("1. Se abrirá una URL en tu navegador")
    print("2. Loguéate con tu cuenta de Google")
    print("3. Clickeá 'Permitir' para dar acceso a Calendar y Drive")
    print("4. Se mostrará un código de autorización")
    print("5. Cópialo y pégalo aquí en la terminal")
    print("\n" + "="*50 + "\n")

    # run_console() es perfect para Docker - no necesita redirect URI
    # El usuario autoriza en el navegador y luego copia el código
    creds = flow.run_console()

    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())

    print(f"\nToken guardado en {TOKEN_PATH}")
    print("Google Auth configurado correctamente!")


if __name__ == "__main__":
    main()

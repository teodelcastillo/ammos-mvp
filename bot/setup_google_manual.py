#!/usr/bin/env python3
"""
Script manual para obtener el token de Google.
El usuario autoriza en el navegador y copia el código de autorización.
"""

import sys
import os
import json
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
        print(f"ERROR: No existe {CREDENTIALS_PATH}")
        sys.exit(1)

    # Crear el flow
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)

    # Obtener la URL de autorización
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent"
    )

    print("\n" + "="*70)
    print("AUTORIZACIÓN DE GOOGLE - Del Castillo Bot")
    print("="*70)
    print("\n📋 Pasos a seguir:\n")
    print("1️⃣  Abrí esta URL en tu navegador:")
    print(f"\n   {auth_url}\n")
    print("2️⃣  Loguéate con tu cuenta de Google")
    print("3️⃣  Clickeá 'Permitir' para dar acceso a Calendar y Drive")
    print("4️⃣  Serás redirigido a una página con un código")
    print("5️⃣  Cópialo (empieza con '4/' o similar)")
    print("6️⃣  Volvé aquí y pégalo en el siguiente prompt\n")
    print("="*70 + "\n")

    # Pedir el código
    auth_code = input("➡️  Pegá el código de autorización aquí: ").strip()

    if not auth_code:
        print("\n❌ No ingresaste un código")
        sys.exit(1)

    try:
        print("\n⏳ Intercambiando código por token...")
        # Intercambiar el código por el token
        creds = flow.fetch_token(code=auth_code, redirect_uri="http://localhost:9090/")

        # Guardar el token
        os.makedirs(os.path.dirname(TOKEN_PATH) or ".", exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            json.dump(creds, f, indent=2)

        print(f"\n✅ ¡Éxito! Token guardado en: {TOKEN_PATH}")
        print("\n🚀 Próximo paso:")
        print("   docker compose up\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n🔍 Probables causas:")
        print("   • El código es incorrecto o incompleto")
        print("   • El código expiró (válido solo 10 minutos)")
        print("   • El credentials.json no es válido")
        print("   • Falta permisos en Google Cloud\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

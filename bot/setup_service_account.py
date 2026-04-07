#!/usr/bin/env python3
"""
Setup para Service Account (mucho más simple que OAuth).
Solo necesita el JSON descargado de Google Cloud.
"""

import os
import json

CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/credentials/credentials.json")

def main():
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"❌ No existe {CREDENTIALS_PATH}")
        print("\nPasos para configurar:")
        print("1. Ve a https://console.cloud.google.com/iam-admin/serviceaccounts")
        print("2. Clickeá '+ CREATE SERVICE ACCOUNT'")
        print("3. Nombre: delcastillo-bot")
        print("4. Dale rol: Editor (o Calendar + Drive específicos)")
        print("5. En Keys > Add Key > JSON")
        print("6. Renombrá a credentials.json y guardá en credentials/")
        return

    # Verificar que es un valid JSON
    try:
        with open(CREDENTIALS_PATH) as f:
            creds = json.load(f)

        if "type" in creds and creds["type"] == "service_account":
            print("\n✅ Service Account configurada correctamente!")
            print(f"   Email: {creds.get('client_email')}")
            print(f"   Proyecto: {creds.get('project_id')}")
            print("\n🚀 Ya podés ejecutar:")
            print("   docker compose up")
        else:
            print("❌ El archivo no parece ser una Service Account")
    except Exception as e:
        print(f"❌ Error leyendo credentials.json: {e}")

if __name__ == "__main__":
    main()

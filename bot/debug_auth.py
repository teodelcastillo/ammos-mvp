#!/usr/bin/env python3
"""Debug de autenticación con Google"""

import os
import json
from google.oauth2 import service_account

CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/credentials/credentials.json")

def main():
    print("\n🔍 Debug de autenticación Google\n")

    # 1. Verificar que existe el archivo
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"❌ No existe: {CREDENTIALS_PATH}")
        return

    print(f"✅ Archivo encontrado: {CREDENTIALS_PATH}")

    # 2. Leer y verificar el JSON
    try:
        with open(CREDENTIALS_PATH) as f:
            creds_data = json.load(f)
        print("✅ JSON válido")
    except Exception as e:
        print(f"❌ Error leyendo JSON: {e}")
        return

    # 3. Verificar que es Service Account
    if creds_data.get("type") != "service_account":
        print(f"❌ No es Service Account. Type: {creds_data.get('type')}")
        return

    print(f"✅ Es Service Account")
    print(f"   Email: {creds_data.get('client_email')}")
    print(f"   Proyecto: {creds_data.get('project_id')}")

    # 4. Intentar crear credenciales
    try:
        SCOPES = [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_PATH, scopes=SCOPES
        )
        print("✅ Credenciales creadas exitosamente")
    except Exception as e:
        print(f"❌ Error creando credenciales: {e}")
        return

    # 5. Intentar conectar con Google Calendar API
    try:
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds)
        print("✅ Conectado a Google Calendar API")
    except Exception as e:
        print(f"❌ Error conectando a Calendar API: {e}")
        return

    # 6. Intentar listar calendarios
    try:
        result = service.calendarList().list().execute()
        items = result.get("items", [])
        print(f"✅ Calendarios encontrados: {len(items)}")

        if items:
            for cal in items:
                print(f"   - {cal.get('summary')} ({cal.get('id')})")
        else:
            print("   ⚠️  No hay calendarios compartidos con esta Service Account")
            print("\n💡 Solución:")
            print(f"   1. En Google Calendar, abrí el calendario 'Estudio del Castillo abogados'")
            print(f"   2. Clickeá ⋯ (3 puntos) > Settings > Share with specific people")
            print(f"   3. Agregá: {creds_data.get('client_email')}")
            print(f"   4. Dale permisos de 'Editor'")
            print(f"   5. Esperá 2-3 minutos y probá de nuevo")

    except Exception as e:
        print(f"❌ Error listando calendarios: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

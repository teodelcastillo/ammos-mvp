#!/usr/bin/env python3
"""
Lista todos los calendarios disponibles en Google Calendar.
Muestra el ID que necesitas para configurar el bot.
"""

from googleapiclient.discovery import build
from google_auth import get_credentials

def main():
    print("\n📅 Listando calendarios disponibles...\n")

    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    calendars = service.calendarList().list().execute()

    items = calendars.get("items", [])

    if not items:
        print("No calendarios encontrados")
        return

    print("="*70)
    for cal in items:
        cal_id = cal["id"]
        summary = cal.get("summary", "Sin nombre")
        is_primary = cal.get("primary", False)

        primary_text = " [PRINCIPAL]" if is_primary else ""
        print(f"\n📌 {summary}{primary_text}")
        print(f"   ID: {cal_id}")

    print("\n" + "="*70)
    print("\n💡 Para usar un calendario específico, configura en agent.py:")
    print("   calendar_id = 'ID_DEL_CALENDARIO'")
    print("\nEjemplo:")
    print("   calendar_id = 'estudio.delcastillo@gmail.com'")

if __name__ == "__main__":
    main()

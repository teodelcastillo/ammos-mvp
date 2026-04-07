#!/usr/bin/env python3
"""Test para verificar eventos en el calendario"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from google_auth import get_credentials

TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Cordoba")
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")

def main():
    print(f"\n📅 Testeando calendario: {CALENDAR_ID}\n")

    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)

    # Rangos de prueba
    tests = [
        ("Esta semana", now, now + timedelta(days=7)),
        ("Próximos 30 días", now, now + timedelta(days=30)),
        ("Próximos 90 días", now, now + timedelta(days=90)),
        ("Todo este mes", now.replace(day=1), (now + timedelta(days=32)).replace(day=1)),
    ]

    for label, start, end in tests:
        start_str = start.isoformat()
        end_str = end.isoformat()

        print(f"🔍 {label}: {start.date()} a {end.date()}")

        try:
            result = service.events().list(
                calendarId=CALENDAR_ID,
                timeMin=start_str,
                timeMax=end_str,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            items = result.get("items", [])
            print(f"   ✅ Encontrados: {len(items)} eventos")

            for event in items[:3]:  # Mostrar primeros 3
                start_dt = event["start"].get("dateTime", event["start"].get("date"))
                print(f"      • {event.get('summary', 'Sin título')} - {start_dt}")

        except Exception as e:
            print(f"   ❌ Error: {e}")

        print()

if __name__ == "__main__":
    main()

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from google_auth import get_credentials

TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Cordoba")
DEFAULT_CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")

calendar_tools = [
    {
        "name": "calendar_list_events",
        "description": "Lista eventos del calendario de Google en un rango de fechas. Útil para ver vencimientos, reuniones, audiencias, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Fecha/hora de inicio en formato ISO 8601 (ej: 2025-01-15T00:00:00)",
                },
                "end_date": {
                    "type": "string",
                    "description": "Fecha/hora de fin en formato ISO 8601 (ej: 2025-01-22T23:59:59)",
                },
                "calendar_id": {
                    "type": "string",
                    "description": "ID del calendario. Por defecto 'primary'",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo número de eventos a devolver (default 20)",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "calendar_create_event",
        "description": "Crea un nuevo evento en el calendario de Google. Útil para agendar reuniones, audiencias, vencimientos, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Título del evento",
                },
                "start_datetime": {
                    "type": "string",
                    "description": "Fecha y hora de inicio en formato ISO 8601 (ej: 2025-03-10T10:00:00)",
                },
                "end_datetime": {
                    "type": "string",
                    "description": "Fecha y hora de fin en formato ISO 8601 (ej: 2025-03-10T11:00:00)",
                },
                "description": {
                    "type": "string",
                    "description": "Descripción del evento (opcional)",
                },
                "location": {
                    "type": "string",
                    "description": "Ubicación del evento (opcional)",
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de emails de los asistentes (opcional)",
                },
            },
            "required": ["summary", "start_datetime", "end_datetime"],
        },
    },
    {
        "name": "calendar_search_events",
        "description": "Busca eventos en el calendario por texto. Útil para encontrar reuniones o vencimientos específicos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto a buscar en los eventos",
                },
                "start_date": {
                    "type": "string",
                    "description": "Fecha de inicio para la búsqueda (ISO 8601). Por defecto: ahora",
                },
                "end_date": {
                    "type": "string",
                    "description": "Fecha de fin para la búsqueda (ISO 8601). Por defecto: 90 días desde ahora",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "calendar_delete_event",
        "description": "Elimina un evento del calendario por su ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "ID del evento a eliminar",
                },
                "calendar_id": {
                    "type": "string",
                    "description": "ID del calendario. Por defecto 'primary'",
                },
            },
            "required": ["event_id"],
        },
    },
]


def _get_service():
    return build("calendar", "v3", credentials=get_credentials())


def _ensure_tz(dt_str: str) -> str:
    """Append timezone offset if not present."""
    if not dt_str.endswith("Z") and "+" not in dt_str[-6:] and "-" not in dt_str[-6:]:
        return dt_str + "-03:00"
    return dt_str


def _get_all_calendar_ids(service) -> list[str]:
    """Devuelve los IDs de todos los calendarios disponibles en la cuenta."""
    result = service.calendarList().list().execute()
    items = result.get("items", [])
    if items:
        return [cal["id"] for cal in items]
    # Fallback al calendario configurado
    return [DEFAULT_CALENDAR_ID]


async def handle_calendar_tool(name: str, input_data: dict) -> dict:
    try:
        service = _get_service()

        if name == "calendar_list_events":
            return _list_events(service, input_data)
        elif name == "calendar_create_event":
            return _create_event(service, input_data)
        elif name == "calendar_search_events":
            return _search_events(service, input_data)
        elif name == "calendar_delete_event":
            return _delete_event(service, input_data)
        return {"error": f"Tool desconocido: {name}"}
    except Exception as e:
        return {"error": str(e)}


def _list_events(service, data: dict) -> dict:
    max_results = data.get("max_results", 50)
    time_min = _ensure_tz(data["start_date"])
    time_max = _ensure_tz(data["end_date"])

    # Buscar en todos los calendarios disponibles
    calendar_ids = _get_all_calendar_ids(service)

    all_events = []
    for cal_id in calendar_ids:
        try:
            result = (
                service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            for e in result.get("items", []):
                all_events.append({
                    "id": e["id"],
                    "summary": e.get("summary", "Sin título"),
                    "start": e["start"].get("dateTime", e["start"].get("date")),
                    "end": e["end"].get("dateTime", e["end"].get("date")),
                    "description": e.get("description", ""),
                    "location": e.get("location", ""),
                    "calendar_id": cal_id,
                })
        except Exception:
            continue

    # Ordenar por fecha de inicio
    all_events.sort(key=lambda e: e["start"])

    return {"events": all_events, "count": len(all_events)}


def _create_event(service, data: dict) -> dict:
    calendar_id = data.get("calendar_id", DEFAULT_CALENDAR_ID)
    event = {
        "summary": data["summary"],
        "start": {"dateTime": data["start_datetime"], "timeZone": TIMEZONE},
        "end": {"dateTime": data["end_datetime"], "timeZone": TIMEZONE},
    }

    if desc := data.get("description"):
        event["description"] = desc
    if loc := data.get("location"):
        event["location"] = loc
    if attendees := data.get("attendees"):
        event["attendees"] = [{"email": a} for a in attendees]

    created = service.events().insert(calendarId=calendar_id, body=event).execute()
    return {
        "id": created["id"],
        "summary": created["summary"],
        "start": created["start"],
        "end": created["end"],
        "link": created.get("htmlLink", ""),
        "status": "created",
    }


def _search_events(service, data: dict) -> dict:
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)

    start = _ensure_tz(data.get("start_date", now.isoformat()))
    end = _ensure_tz(data.get("end_date", (now + timedelta(days=90)).isoformat()))

    # Buscar en todos los calendarios
    calendar_ids = _get_all_calendar_ids(service)

    all_events = []
    for cal_id in calendar_ids:
        try:
            result = (
                service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=start,
                    timeMax=end,
                    q=data["query"],
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=20,
                )
                .execute()
            )
            for e in result.get("items", []):
                all_events.append({
                    "id": e["id"],
                    "summary": e.get("summary", "Sin título"),
                    "start": e["start"].get("dateTime", e["start"].get("date")),
                    "description": e.get("description", ""),
                    "calendar_id": cal_id,
                })
        except Exception:
            continue

    all_events.sort(key=lambda e: e["start"])
    return {"events": all_events, "count": len(all_events)}


def _delete_event(service, data: dict) -> dict:
    calendar_id = data.get("calendar_id", DEFAULT_CALENDAR_ID)
    service.events().delete(calendarId=calendar_id, eventId=data["event_id"]).execute()
    return {"status": "deleted", "event_id": data["event_id"]}

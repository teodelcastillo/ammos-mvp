import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from google_auth import get_credentials

TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Cordoba")

tasks_tools = [
    {
        "name": "tasks_list",
        "description": "Lista tareas de Google Tasks en un rango de fechas. Útil para ver vencimientos, tareas pendientes, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Fecha de inicio en formato ISO 8601 (ej: 2025-01-15)",
                },
                "end_date": {
                    "type": "string",
                    "description": "Fecha de fin en formato ISO 8601 (ej: 2025-01-22)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo número de tareas a devolver (default 20)",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
]


def _get_service():
    return build("tasks", "v1", credentials=get_credentials())


async def handle_tasks_tool(name: str, input_data: dict) -> dict:
    try:
        service = _get_service()

        if name == "tasks_list":
            return _list_tasks(service, input_data)
        return {"error": f"Tool desconocido: {name}"}
    except Exception as e:
        return {"error": str(e)}


def _list_tasks(service, data: dict) -> dict:
    tz = ZoneInfo(TIMEZONE)
    start_date = datetime.fromisoformat(data["start_date"]).date()
    end_date = datetime.fromisoformat(data["end_date"]).date()
    max_results = data.get("max_results", 20)

    try:
        # Obtener la lista de tareas por defecto
        tasklists = service.tasklists().list().execute()
        tasklist_id = None

        # Buscar lista "@default" o la primera disponible
        for tasklist in tasklists.get("items", []):
            if tasklist["id"] == "@default":
                tasklist_id = tasklist["id"]
                break

        if not tasklist_id and tasklists.get("items"):
            tasklist_id = tasklists["items"][0]["id"]

        if not tasklist_id:
            return {"tasks": [], "count": 0}

        # Obtener tareas
        result = (
            service.tasks()
            .list(tasklist=tasklist_id, maxResults=max_results, showCompleted=False)
            .execute()
        )

        items = result.get("items", [])
        tasks = []

        for task in items:
            due = task.get("due")

            # Parsear fecha de vencimiento si existe
            if due:
                try:
                    due_date = datetime.fromisoformat(due).date() if "T" in due else datetime.fromisoformat(due).date()

                    # Filtrar por rango de fechas
                    if start_date <= due_date <= end_date:
                        tasks.append({
                            "id": task["id"],
                            "title": task.get("title", "Sin título"),
                            "due": due,
                            "status": task.get("status", "needsAction"),
                            "completed": task.get("completed"),
                            "notes": task.get("notes", ""),
                        })
                except:
                    pass

        return {
            "tasks": tasks,
            "count": len(tasks),
        }

    except Exception as e:
        return {"error": f"Error listando tareas: {str(e)}"}

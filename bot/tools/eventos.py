"""
Herramientas para vincular eventos de Google Calendar a casos en la DB.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from db import get_conn, rows_to_list
from tools.calendar import _get_service, _ensure_tz, TIMEZONE

logger = logging.getLogger(__name__)

TIPOS_EVENTO = ["audiencia", "vencimiento", "reunion", "pericia", "mediacion", "otro"]

eventos_tools = [
    {
        "name": "evento_registrar",
        "description": (
            "Crea un evento en Google Calendar Y lo vincula al caso en la base de datos. "
            "Usar cuando el usuario quiere agendar una audiencia, vencimiento, reunión u otro "
            "evento relacionado a un caso específico. Queda registrado en el historial del caso."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caso_id": {
                    "type": "integer",
                    "description": "ID numérico del caso. Si no se conoce, usar caso_busqueda.",
                },
                "caso_busqueda": {
                    "type": "string",
                    "description": "Texto para buscar el caso por nombre/carátula cuando no se conoce el ID. Ej: 'García', 'Municipalidad'.",
                },
                "titulo": {
                    "type": "string",
                    "description": "Título del evento (ej: 'Audiencia de prueba - García c/ López')",
                },
                "fecha": {
                    "type": "string",
                    "description": "Fecha y hora en formato ISO 8601 (ej: 2025-04-15T10:00:00)",
                },
                "fecha_fin": {
                    "type": "string",
                    "description": "Fecha y hora de fin en ISO 8601. Si no se indica, se asume 1 hora después.",
                },
                "tipo": {
                    "type": "string",
                    "enum": TIPOS_EVENTO,
                    "description": "Tipo de evento",
                },
                "notas": {
                    "type": "string",
                    "description": "Notas adicionales sobre el evento (opcional)",
                },
                "ubicacion": {
                    "type": "string",
                    "description": "Ubicación del evento (opcional, ej: 'Juzgado Civil Nro 4')",
                },
            },
            "required": ["titulo", "fecha", "tipo"],
        },
    },
    {
        "name": "caso_historial",
        "description": (
            "Devuelve el historial completo de un caso: eventos vinculados al calendario, "
            "notas de reunión, registros de tiempo y datos del caso. "
            "Usar cuando el usuario pregunta por el historial, antecedentes o actividad de un caso."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caso_id": {"type": "integer", "description": "ID numérico del caso."},
                "caso_busqueda": {"type": "string", "description": "Texto para buscar el caso si no se conoce el ID."},
            },
        },
    },
    {
        "name": "evento_listar_caso",
        "description": "Lista los eventos del calendario vinculados a un caso específico.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caso_id": {"type": "integer", "description": "ID numérico del caso."},
                "caso_busqueda": {"type": "string", "description": "Texto para buscar el caso si no se conoce el ID."},
            },
        },
    },
]


def _resolve_caso(data: dict) -> tuple[int | None, str | None]:
    """
    Resuelve caso_id a partir de data.
    Acepta caso_id directo o busca por caso_busqueda.
    Retorna (caso_id, error_msg).
    """
    if cid := data.get("caso_id"):
        return int(cid), None

    busqueda = (data.get("caso_busqueda") or "").strip()
    if not busqueda:
        return None, "Se requiere caso_id o caso_busqueda para identificar el caso."

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, caratula FROM casos WHERE caratula LIKE ? ORDER BY id LIMIT 5",
            (f"%{busqueda}%",)
        ).fetchall()

    if not rows:
        return None, f"No se encontró ningún caso que coincida con '{busqueda}'."
    if len(rows) > 1:
        opciones = ", ".join(f"#{r[0]} {r[1]}" for r in rows)
        return None, f"Se encontraron varios casos: {opciones}. Indicá el ID exacto."

    return rows[0][0], None


async def handle_eventos_tool(name: str, data: dict) -> dict:
    try:
        caso_id, err = _resolve_caso(data)
        if err:
            return {"error": err}
        data["caso_id"] = caso_id

        if name == "evento_registrar":
            return await _evento_registrar(data)
        elif name == "caso_historial":
            return _caso_historial(data)
        elif name == "evento_listar_caso":
            return _evento_listar_caso(data)
        return {"error": f"Tool desconocido: {name}"}
    except Exception as e:
        logger.exception("Error en tool %s", name)
        return {"error": str(e)}


# ──────────────────────────────────────────────

async def _evento_registrar(data: dict) -> dict:
    from datetime import timedelta

    caso_id = data["caso_id"]
    titulo  = data["titulo"]
    fecha   = data["fecha"]
    tipo    = data.get("tipo", "otro")
    notas   = data.get("notas", "")
    ubicacion = data.get("ubicacion", "")

    # Verificar que el caso existe
    with get_conn() as conn:
        caso = conn.execute(
            "SELECT id, caratula FROM casos WHERE id=?", (caso_id,)
        ).fetchone()
    if not caso:
        return {"error": f"Caso ID {caso_id} no encontrado"}

    # Calcular fecha_fin
    fecha_fin = data.get("fecha_fin")
    if not fecha_fin:
        dt = datetime.fromisoformat(fecha)
        fecha_fin = (dt + timedelta(hours=1)).isoformat()

    # Crear evento en Google Calendar
    service = _get_service()
    from tools.calendar import DEFAULT_CALENDAR_ID
    event_body = {
        "summary": titulo,
        "start": {"dateTime": _ensure_tz(fecha), "timeZone": TIMEZONE},
        "end":   {"dateTime": _ensure_tz(fecha_fin), "timeZone": TIMEZONE},
    }
    if ubicacion:
        event_body["location"] = ubicacion
    if notas:
        event_body["description"] = f"Caso: {caso['caratula']}\n{notas}"
    else:
        event_body["description"] = f"Caso: {caso['caratula']}"

    created = service.events().insert(
        calendarId=DEFAULT_CALENDAR_ID, body=event_body
    ).execute()

    calendar_link = created.get("htmlLink", "")
    event_id      = created.get("id", "")

    # Guardar en eventos_caso
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO eventos_caso
               (caso_id, calendar_event_id, calendar_link, titulo, fecha, tipo, notas)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (caso_id, event_id, calendar_link, titulo, fecha, tipo, notas)
        )

    return {
        "status": "registrado",
        "caso": caso["caratula"],
        "titulo": titulo,
        "fecha": fecha,
        "tipo": tipo,
        "calendar_link": calendar_link,
    }


def _caso_historial(data: dict) -> dict:
    caso_id = data["caso_id"]

    with get_conn() as conn:
        caso = conn.execute("""
            SELECT c.*, cl.nombre AS cliente_nombre
            FROM casos c LEFT JOIN clientes cl ON cl.id=c.cliente_id
            WHERE c.id=?
        """, (caso_id,)).fetchone()

        if not caso:
            return {"error": f"Caso ID {caso_id} no encontrado"}

        eventos = rows_to_list(conn.execute(
            "SELECT * FROM eventos_caso WHERE caso_id=? ORDER BY fecha DESC",
            (caso_id,)
        ).fetchall())

        notas = rows_to_list(conn.execute(
            "SELECT fecha, participantes, contenido, creado_por FROM notas_reunion "
            "WHERE caso_id=? ORDER BY fecha DESC LIMIT 10",
            (caso_id,)
        ).fetchall())

        tiempo = rows_to_list(conn.execute(
            "SELECT abogado, SUM(horas) as total FROM registros_tiempo "
            "WHERE caso_id=? GROUP BY abogado",
            (caso_id,)
        ).fetchall())

        total_horas = conn.execute(
            "SELECT COALESCE(SUM(horas),0) FROM registros_tiempo WHERE caso_id=?",
            (caso_id,)
        ).fetchone()[0]

    return {
        "caso": {
            "id": caso["id"],
            "caratula": caso["caratula"],
            "numero": caso["numero"],
            "cliente": caso["cliente_nombre"],
            "juzgado": caso["juzgado"],
            "estado": caso["estado"],
            "mediacion": bool(caso["mediacion"]),
        },
        "eventos": [
            {
                "titulo": e["titulo"],
                "fecha": e["fecha"],
                "tipo": e["tipo"],
                "notas": e.get("notas"),
                "calendar_link": e.get("calendar_link"),
            }
            for e in eventos
        ],
        "notas": [
            {
                "fecha": n["fecha"],
                "participantes": n.get("participantes"),
                "resumen": (n.get("contenido") or "")[:200],
            }
            for n in notas
        ],
        "tiempo": {
            "total_horas": total_horas,
            "por_abogado": [{"abogado": t["abogado"], "horas": t["total"]} for t in tiempo],
        },
    }


def _evento_listar_caso(data: dict) -> dict:
    caso_id = data["caso_id"]
    with get_conn() as conn:
        eventos = rows_to_list(conn.execute(
            "SELECT * FROM eventos_caso WHERE caso_id=? ORDER BY fecha DESC",
            (caso_id,)
        ).fetchall())
    return {
        "eventos": eventos,
        "count": len(eventos),
    }

"""
Briefing diario automático para Estudio Del Castillo.
Envía un resumen de eventos y casos activos cada mañana por WhatsApp.
También envía un check-in vespertino a las 16hs con los eventos del día.
"""

import logging
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from db import get_conn, rows_to_list
from tools.calendar import _get_service, _get_all_calendar_ids, _ensure_tz

logger = logging.getLogger("briefing")

TIMEZONE = os.getenv("TIMEZONE", "America/Argentina/Cordoba")
WA_BRIDGE_URL = os.getenv("WA_BRIDGE_URL", "http://whatsapp-bridge:8080")

# Chats que reciben el briefing (JIDs separados por coma)
_raw = os.getenv("BRIEFING_CHATS", os.getenv("ALLOWED_CHATS", ""))
BRIEFING_CHATS: list[str] = [j.strip() for j in _raw.split(",") if j.strip()]

DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES_ES = ["", "ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic"]

# ── Helpers compartidos para filtrar/clasificar eventos ──────────────────────

_SKIP_KW = [
    "home office", "vacaciones", "feriado", "feriados",
    "cumpleaños", "birthday", "franco", "licencia", "día libre",
]

_TIPO_ICONS = {
    "audiencia": "⚖️", "vencimiento": "⏰", "reunion": "🤝",
    "pericia": "🔬", "mediacion": "🕊️", "otro": "📌",
}


def _infer_tipo(titulo: str) -> str:
    t = titulo.lower()
    if any(w in t for w in ["audiencia", "vista", "oral"]) or re.search(r"\baud[\s.\-]", t):
        return "audiencia"
    if any(w in t for w in ["vencimiento", "vence", "vto.", "vtto", "plazo", "término", "termino"]):
        return "vencimiento"
    if any(w in t for w in ["mediación", "mediacion"]):
        return "mediacion"
    if any(w in t for w in ["pericia", "perito", "peritos"]):
        return "pericia"
    if any(w in t for w in ["reunión", "reunion", "entrevista"]):
        return "reunion"
    return "otro"


def _es_relevante(titulo: str) -> bool:
    """True si el evento merece un check-in (no es HO/vacaciones y tiene tipo conocido)."""
    t = titulo.lower()
    if any(kw in t for kw in _SKIP_KW):
        return False
    return _infer_tipo(titulo) != "otro"


def _fmt_time(dt_str: str) -> str:
    """Extrae HH:MM de un datetime ISO, o devuelve 'todo el día'."""
    if "T" not in dt_str:
        return "todo el día"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo(TIMEZONE)).strftime("%H:%M")
    except Exception:
        return ""


def _fmt_date_short(dt_str: str) -> str:
    """Devuelve 'Mar 08' a partir de un ISO date/datetime."""
    try:
        date_part = dt_str[:10]
        d = datetime.strptime(date_part, "%Y-%m-%d")
        return f"{DIAS_ES[d.weekday()][:3]} {d.day:02d}"
    except Exception:
        return dt_str[:10]


def _get_events(time_min: str, time_max: str) -> list[dict]:
    service = _get_service()
    calendar_ids = _get_all_calendar_ids(service)
    events = []
    for cal_id in calendar_ids:
        try:
            result = service.events().list(
                calendarId=cal_id,
                timeMin=_ensure_tz(time_min),
                timeMax=_ensure_tz(time_max),
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            for e in result.get("items", []):
                events.append({
                    "summary": e.get("summary", "Sin título"),
                    "start": e["start"].get("dateTime", e["start"].get("date")),
                    "event_id": e.get("id", ""),
                })
        except Exception:
            continue
    events.sort(key=lambda e: e["start"])
    return events


def _get_active_casos() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM casos WHERE estado='activo'").fetchone()[0]


def _build_event_case_index() -> dict[str, str]:
    """Construye un índice {calendar_event_id → caratula} desde eventos_caso."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT ev.calendar_event_id, c.caratula
               FROM eventos_caso ev JOIN casos c ON c.id=ev.caso_id
               WHERE ev.calendar_event_id IS NOT NULL"""
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def _build_message() -> str:
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)

    # Rangos
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end   = now.replace(hour=23, minute=59, second=59, microsecond=0)
    # Resto de semana = mañana hasta el próximo domingo inclusive
    week_start  = today_end + timedelta(seconds=1)
    days_to_sunday = 6 - now.weekday()
    week_end    = (today_start + timedelta(days=days_to_sunday)).replace(hour=23, minute=59, second=59)

    today_events  = _get_events(today_start.isoformat(), today_end.isoformat())
    week_events   = _get_events(week_start.isoformat(), week_end.isoformat()) if days_to_sunday > 0 else []
    casos_activos = _get_active_casos()
    event_case_idx = _build_event_case_index()

    dia_nombre = DIAS_ES[now.weekday()]
    fecha_str  = f"{now.day:02d}/{now.month:02d}/{now.year}"

    lines = [f"*Buenos días! ☀️ {dia_nombre} {fecha_str}*\n"]

    def _fmt_event_line(e: dict, show_date: bool = False) -> str:
        hora = _fmt_time(e["start"])
        caso = event_case_idx.get(e.get("event_id", ""))
        caso_tag = f" _(caso: {caso})_" if caso else ""
        prefix = f"• {_fmt_date_short(e['start'])} {hora} — " if show_date else (
            f"• {hora} — " if hora != "todo el día" else "• "
        )
        return f"{prefix}{e['summary']}{caso_tag}"

    # Eventos de hoy
    lines.append("*📅 Hoy:*")
    if today_events:
        for e in today_events:
            lines.append(_fmt_event_line(e))
    else:
        lines.append("• Sin eventos")

    # Resto de la semana
    if days_to_sunday > 0:
        lines.append("\n*📆 Resto de la semana:*")
        if week_events:
            for e in week_events:
                lines.append(_fmt_event_line(e, show_date=True))
        else:
            lines.append("• Sin eventos")

    # Casos activos
    lines.append(f"\n*⚖️ Casos activos:* {casos_activos}")

    return "\n".join(lines)


async def _send_to_chats(message: str, label: str):
    """Envía un mensaje a todos los BRIEFING_CHATS."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        for jid in BRIEFING_CHATS:
            try:
                await client.post(
                    f"{WA_BRIDGE_URL}/send",
                    json={"chat": jid, "message": message},
                )
                logger.info("%s enviado a %s", label, jid)
            except Exception:
                logger.exception("Error enviando %s a %s", label, jid)


async def send_briefing():
    """Genera y envía el briefing a todos los chats configurados."""
    if not BRIEFING_CHATS:
        logger.warning("BRIEFING_CHATS no configurado, no se envía el briefing")
        return

    logger.info("Generando briefing diario para %d chats", len(BRIEFING_CHATS))
    try:
        message = _build_message()
    except Exception:
        logger.exception("Error generando el briefing")
        return

    await _send_to_chats(message, "Briefing")


# ── Check-in vespertino (16hs) ───────────────────────────────────────────────

def _build_checkin_message() -> str | None:
    """
    Construye el mensaje de check-in de las 16hs.
    Retorna None si no hay eventos relevantes hoy → no se envía nada.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end   = now.replace(hour=23, minute=59, second=59, microsecond=0)

    try:
        today_events = _get_events(today_start.isoformat(), today_end.isoformat())
    except Exception:
        logger.exception("Error obteniendo eventos para check-in")
        return None

    # Solo tipos relevantes
    relevantes = [e for e in today_events if _es_relevante(e["summary"])]
    if not relevantes:
        logger.info("Sin eventos relevantes hoy — no se envía check-in")
        return None

    event_case_idx = _build_event_case_index()

    dia = DIAS_ES[now.weekday()]
    fecha_str = f"{now.day:02d}/{now.month:02d}/{now.year}"

    lines = [f"*📋 Cierre del día — {dia} {fecha_str}*\n"]
    lines.append("Estos eventos figuraban hoy en la agenda:\n")

    for e in relevantes:
        titulo  = e["summary"]
        hora    = _fmt_time(e["start"])
        tipo    = _infer_tipo(titulo)
        icon    = _TIPO_ICONS[tipo]
        caso    = event_case_idx.get(e.get("event_id", ""))
        hora_str = f" — {hora}" if hora and hora != "todo el día" else ""

        if caso:
            lines.append(f"{icon} *{titulo}*{hora_str}")
            lines.append(f"   _↳ causa: {caso}_")
        else:
            lines.append(f"{icon} *{titulo}*{hora_str}")

    lines.append(
        "\n¿Cómo resultó? Para registrarlo:\n"
        "_\"lexia, anotar en [causa]: [resultado]\"_\n"
        "_\"lexia, registrar [audiencia/reunión/...] en [causa] para el [fecha]\"_"
    )

    return "\n".join(lines)


async def send_evening_checkin():
    """Envía el check-in vespertino si hay eventos relevantes hoy."""
    if not BRIEFING_CHATS:
        return
    logger.info("Generando check-in vespertino")
    try:
        message = _build_checkin_message()
    except Exception:
        logger.exception("Error generando check-in vespertino")
        return

    if message:
        await _send_to_chats(message, "Check-in vespertino")

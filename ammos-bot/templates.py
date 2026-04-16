"""Templates de mensajes automáticos y reglas para programarlos.

Para el MVP los templates viven en código (no en BD). Cada uno define:
  - key: identificador estable usado como UNIQUE(reservation_id, template_key)
  - schedule(): cuándo se debería mandar en función de la reserva
  - render(): texto final listo para WhatsApp
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo


@dataclass
class Template:
    key: str
    description: str
    schedule: Callable[[dict, ZoneInfo], datetime | None]
    render: Callable[[dict, dict], str]


def _combine(d, t, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz)


def _parse_date(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if hasattr(value, "year") and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value))


def _parse_time(value: str, fallback: time) -> time:
    try:
        h, m = value.split(":")
        return time(int(h), int(m))
    except Exception:
        return fallback


# ---------- schedule helpers (reciben res_dict con info de property joineada) ----------

def _schedule_confirmation(res: dict, tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def _schedule_checkin(res: dict, tz: ZoneInfo) -> datetime:
    check_in = _parse_date(res["check_in_date"]).date()
    when = _combine(check_in - timedelta(days=1), time(10, 0), tz)
    return when


def _schedule_midstay(res: dict, tz: ZoneInfo) -> datetime | None:
    check_in = _parse_date(res["check_in_date"]).date()
    check_out = _parse_date(res["check_out_date"]).date()
    nights = (check_out - check_in).days
    if nights < 2:
        return None
    return _combine(check_in + timedelta(days=1), time(11, 0), tz)


def _schedule_checkout(res: dict, tz: ZoneInfo) -> datetime:
    check_out = _parse_date(res["check_out_date"]).date()
    return _combine(check_out, time(8, 0), tz)


def _schedule_review(res: dict, tz: ZoneInfo) -> datetime:
    check_out = _parse_date(res["check_out_date"]).date()
    return _combine(check_out, time(18, 0), tz)


# ---------- renderers ----------

def _fmt_date(value) -> str:
    d = _parse_date(value)
    return d.strftime("%d/%m/%Y")


def _render_confirmation(res: dict, prop: dict) -> str:
    return (
        f"¡Hola {res['guest_name']}! 👋\n\n"
        f"Tu reserva en *{prop['name']}* está confirmada ✅\n"
        f"📅 Check-in: {_fmt_date(res['check_in_date'])} "
        f"(a partir de las {prop.get('check_in_time') or '15:00'})\n"
        f"📅 Check-out: {_fmt_date(res['check_out_date'])} "
        f"(hasta las {prop.get('check_out_time') or '11:00'})\n\n"
        "Un día antes te mandamos las instrucciones de ingreso. "
        "Cualquier consulta, respondé por acá. ¡Te esperamos!"
    )


def _render_checkin(res: dict, prop: dict) -> str:
    door = prop.get("door_code") or "te lo enviamos el día del check-in"
    wifi = prop.get("wifi_name") or "—"
    wifi_pw = prop.get("wifi_password") or "—"
    host = prop.get("host_phone") or "—"
    return (
        f"Hola {res['guest_name']}, ¡mañana te esperamos en *{prop['name']}*! 🏡\n\n"
        f"📍 Dirección: {prop.get('address') or 'te la pasamos al confirmar'}\n"
        f"🕒 Check-in: desde las {prop.get('check_in_time') or '15:00'}\n"
        f"🔑 Código de ingreso: *{door}*\n"
        f"📶 WiFi: {wifi} / clave: {wifi_pw}\n"
        f"📞 Contacto emergencias: {host}\n\n"
        "Si vas a llegar a otro horario o necesitás algo, avisanos por este chat."
    )


def _render_midstay(res: dict, prop: dict) -> str:
    return (
        f"Hola {res['guest_name']}, ¿cómo va todo en *{prop['name']}*? 😊\n"
        "Cualquier cosa que necesites (toallas, consultas, algún desperfecto), "
        "avisanos por acá y lo resolvemos."
    )


def _render_checkout(res: dict, prop: dict) -> str:
    return (
        f"¡Hola {res['guest_name']}! Hoy es tu día de check-out 👋\n\n"
        f"🕒 Horario: hasta las {prop.get('check_out_time') or '11:00'}\n"
        "Antes de irte, te pedimos:\n"
        "• Dejar las llaves donde las encontraste\n"
        "• Tirar la basura al contenedor de la calle\n"
        "• Cerrar ventanas y puertas\n\n"
        "¡Gracias por elegirnos! 🙏"
    )


def _render_review(res: dict, prop: dict) -> str:
    return (
        f"{res['guest_name']}, esperamos que la hayas pasado genial en *{prop['name']}* ✨\n\n"
        "¿Nos dejás una reseña? Tu opinión nos ayuda muchísimo. "
        "¡Muchas gracias por la confianza! ⭐⭐⭐⭐⭐"
    )


TEMPLATES: dict[str, Template] = {
    "booking_confirmation": Template(
        key="booking_confirmation",
        description="Confirmación al crear reserva",
        schedule=_schedule_confirmation,
        render=_render_confirmation,
    ),
    "checkin_instructions": Template(
        key="checkin_instructions",
        description="Instrucciones de check-in (1 día antes, 10:00)",
        schedule=_schedule_checkin,
        render=_render_checkin,
    ),
    "mid_stay_check": Template(
        key="mid_stay_check",
        description="Mensaje de control durante la estadía (11:00 del día siguiente al check-in)",
        schedule=_schedule_midstay,
        render=_render_midstay,
    ),
    "check_out_reminder": Template(
        key="check_out_reminder",
        description="Recordatorio el día del check-out (8:00)",
        schedule=_schedule_checkout,
        render=_render_checkout,
    ),
    "review_request": Template(
        key="review_request",
        description="Pedido de reseña (tarde del check-out)",
        schedule=_schedule_review,
        render=_render_review,
    ),
}


def all_templates() -> list[Template]:
    return list(TEMPLATES.values())


def get_template(key: str) -> Template | None:
    return TEMPLATES.get(key)

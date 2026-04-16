"""Claude para respuestas inteligentes con contexto de reserva y propiedad."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic

from config import ANTHROPIC_MODEL, TIMEZONE

logger = logging.getLogger(__name__)

_client = AsyncAnthropic()

_history: dict[str, list[dict]] = defaultdict(list)
_MAX_HISTORY = 5


SYSTEM_PROMPT = """Sos el asistente virtual de AMMOS Vacation Rentals.

Tu rol es ayudar a los huéspedes por WhatsApp con consultas sobre su estadía:
dirección, check-in/out, WiFi, comodidades, reglas de la casa y dudas generales
sobre la propiedad que alquilaron.

Reglas:
- Respondé SIEMPRE en el idioma del huésped (por defecto español).
- Sé breve y cálido: 2 a 4 oraciones, estilo WhatsApp.
- Usá *negrita* con asteriscos y emojis con moderación.
- NO inventes datos: si no está en el contexto, decilo y ofrecé contactar al anfitrión.
- NO prometas reembolsos, descuentos ni cambios de reserva.
- Para problemas graves (caños rotos, cortes de luz, seguridad), pedí que llamen
  al teléfono de contacto del anfitrión incluido en el contexto.
- Fecha y hora actual: {current_time}
"""


def _build_context(reservation: dict, property_: dict) -> dict:
    ctx = {
        "propiedad": {
            "nombre": property_.get("name"),
            "direccion": property_.get("address"),
            "check_in": property_.get("check_in_time"),
            "check_out": property_.get("check_out_time"),
            "wifi": {
                "red": property_.get("wifi_name"),
                "clave": property_.get("wifi_password"),
            },
            "codigo_ingreso": property_.get("door_code"),
            "comodidades": property_.get("amenities"),
            "reglas": property_.get("house_rules"),
            "telefono_anfitrion": property_.get("host_phone"),
            "notas": property_.get("notes"),
        },
        "reserva": {
            "huesped": reservation.get("guest_name"),
            "check_in": str(reservation.get("check_in_date")),
            "check_out": str(reservation.get("check_out_date")),
            "noches": reservation.get("nights"),
            "cantidad_huespedes": reservation.get("num_guests"),
            "idioma": reservation.get("guest_language") or "es",
            "estado": reservation.get("status"),
        },
    }
    return ctx


async def smart_reply(
    message: str,
    reservation: dict,
    property_: dict,
    chat_id: str,
) -> str:
    now = datetime.now(ZoneInfo(TIMEZONE))
    system = SYSTEM_PROMPT.replace("{current_time}", now.strftime("%A %d/%m/%Y %H:%M"))

    context = _build_context(reservation, property_)
    system += "\n\nContexto del huésped y la propiedad:\n" + json.dumps(
        context, indent=2, ensure_ascii=False
    )

    messages = list(_history[chat_id][-_MAX_HISTORY * 2 :])
    messages.append({"role": "user", "content": message})

    resp = await _client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=400,
        system=system,
        messages=messages,
    )

    text = "\n".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    if not text:
        text = "Disculpá, no pude procesar tu mensaje. ¿Podés escribirlo de nuevo?"

    _history[chat_id].append({"role": "user", "content": message})
    _history[chat_id].append({"role": "assistant", "content": text})
    if len(_history[chat_id]) > _MAX_HISTORY * 2:
        _history[chat_id] = _history[chat_id][-_MAX_HISTORY * 2 :]

    return text

"""FastAPI app para el MVP de AMMOS Vacation Rentals."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from admin import router as admin_router
from agent import smart_reply
from config import SCHEDULER_INTERVAL_SEC, TIMEZONE
from db import get_conn, init_db, normalize_phone, row_to_dict
from faq import match_faq
from scheduler import process_due_messages, schedule_reservation_messages
from whatsapp import send_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("ammos-bot")

app = FastAPI(title="AMMOS Vacation Rentals Bot")
app.include_router(admin_router)

_scheduler = AsyncIOScheduler(timezone=TIMEZONE)


@app.on_event("startup")
async def on_startup():
    init_db()
    logger.info("DB inicializada")

    async def job():
        try:
            n = await process_due_messages()
            if n:
                logger.info("Worker envió %d mensajes programados", n)
        except Exception:
            logger.exception("Error en worker de scheduled_messages")

    _scheduler.add_job(job, "interval", seconds=SCHEDULER_INTERVAL_SEC)
    _scheduler.start()
    logger.info("Scheduler iniciado (cada %ss)", SCHEDULER_INTERVAL_SEC)


@app.on_event("shutdown")
async def on_shutdown():
    _scheduler.shutdown(wait=False)


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------- Webhook entrante de WhatsApp (desde el bridge) ----------

@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    data = await request.json()
    asyncio.create_task(_handle_incoming(data))
    return {"status": "received"}


async def _handle_incoming(data: dict):
    chat = data.get("chat") or ""
    sender_name = data.get("sender_name") or "Huésped"
    message = (data.get("message") or "").strip()
    is_group = bool(data.get("is_group"))

    if not message or is_group:
        # Para el MVP ignoramos mensajes de grupos
        return

    phone = normalize_phone(chat)

    with get_conn() as conn:
        res = conn.execute(
            """
            SELECT * FROM reservations
            WHERE guest_phone = ?
            ORDER BY check_in_date DESC
            LIMIT 1
            """,
            (phone,),
        ).fetchone()
        reservation = row_to_dict(res)

        prop = None
        if reservation:
            prop_row = conn.execute(
                "SELECT * FROM properties WHERE id = ?", (reservation["property_id"],)
            ).fetchone()
            prop = row_to_dict(prop_row)

        # Log entrante
        conn.execute(
            """
            INSERT INTO message_logs
              (reservation_id, property_id, chat, guest_phone, direction,
               message_type, content, status)
            VALUES (?, ?, ?, ?, 'in', 'text', ?, 'received')
            """,
            (
                reservation["id"] if reservation else None,
                prop["id"] if prop else None,
                chat, phone, message,
            ),
        )

    if not reservation:
        logger.info("Mensaje sin reserva asociada: %s (%s)", phone, sender_name)
        reply = (
            "¡Hola! Gracias por escribir a AMMOS. No encontramos una reserva "
            "activa asociada a este número. Si ya reservaste, escribinos con "
            "tu nombre y la propiedad para ayudarte."
        )
        await _send_and_log(chat, phone, reply, reservation=None, property_=None,
                            message_type="fallback")
        return

    faq = match_faq(message, reservation["property_id"])
    if faq:
        reply = faq["answer"]
        await _send_and_log(chat, phone, reply, reservation, prop,
                            message_type="faq", template_key=f"faq:{faq['id']}")
        return

    try:
        reply = await smart_reply(message, reservation, prop, chat)
    except Exception:
        logger.exception("Error en smart_reply")
        reply = (
            "Tuve un problema procesando tu mensaje. En breve te responde "
            "alguien del equipo. ¡Gracias por la paciencia!"
        )

    await _send_and_log(chat, phone, reply, reservation, prop, message_type="ai")


async def _send_and_log(
    chat: str,
    phone: str,
    text: str,
    reservation: dict | None,
    property_: dict | None,
    *,
    message_type: str,
    template_key: str | None = None,
):
    result = await send_text(chat, text)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO message_logs
              (reservation_id, property_id, chat, guest_phone, direction,
               message_type, template_key, content, whatsapp_message_id, status, error)
            VALUES (?, ?, ?, ?, 'out', ?, ?, ?, ?, ?, ?)
            """,
            (
                reservation["id"] if reservation else None,
                property_["id"] if property_ else None,
                chat, phone, message_type, template_key, text,
                result.get("message_id"), result.get("status"), result.get("error"),
            ),
        )


# ---------- Webhook simulado de reservaciones (estilo Guestwisely) ----------

class ReservationWebhook(BaseModel):
    event_id: str
    event_type: str = Field(description="reservation_created | reservation_updated | reservation_cancelled")
    source: str = "guestwisely"
    reservation: dict


@app.post("/webhooks/reservations")
async def reservations_webhook(payload: ReservationWebhook):
    """Endpoint para simular el agregador de PMS.

    Espera un payload con una reserva normalizada. Hace deduplicación por
    event_id y upsert por external_id.
    """
    # Deduplicación
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM webhook_events WHERE event_id = ?", (payload.event_id,)
        ).fetchone()
        if existing:
            return {"status": "duplicate", "event_id": payload.event_id}

        conn.execute(
            "INSERT INTO webhook_events (event_id, source, event_type, payload) VALUES (?, ?, ?, ?)",
            (payload.event_id, payload.source, payload.event_type, json.dumps(payload.reservation)),
        )

    data = payload.reservation
    external_id = data.get("external_id") or data.get("id")
    property_external = data.get("property_external_id") or data.get("property_id")
    phone = normalize_phone(data.get("guest_phone", ""))

    try:
        check_in = date.fromisoformat(str(data["check_in_date"]))
        check_out = date.fromisoformat(str(data["check_out_date"]))
    except (KeyError, ValueError) as exc:
        return {"status": "error", "error": f"fechas inválidas: {exc}"}

    nights = (check_out - check_in).days

    with get_conn() as conn:
        prop = conn.execute(
            "SELECT id FROM properties WHERE external_id = ? OR id = ?",
            (str(property_external), property_external if isinstance(property_external, int) else -1),
        ).fetchone()
        if not prop:
            return {"status": "error", "error": f"property {property_external} no encontrada"}

        property_id = prop["id"]

        existing_res = conn.execute(
            "SELECT id FROM reservations WHERE external_id = ?", (external_id,)
        ).fetchone()

        if existing_res:
            conn.execute(
                """
                UPDATE reservations
                SET guest_name=?, guest_phone=?, guest_email=?, check_in_date=?,
                    check_out_date=?, nights=?, num_guests=?, status=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    data.get("guest_name"), phone, data.get("guest_email"),
                    check_in, check_out, nights, data.get("num_guests"),
                    data.get("status", "confirmed"), existing_res["id"],
                ),
            )
            reservation_id = existing_res["id"]
            created = False
        else:
            cur = conn.execute(
                """
                INSERT INTO reservations
                  (external_id, source, property_id, guest_name, guest_phone,
                   guest_email, guest_language, check_in_date, check_out_date,
                   nights, num_guests, status, whatsapp_consent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    external_id, payload.source, property_id,
                    data.get("guest_name"), phone, data.get("guest_email"),
                    data.get("guest_language", "es"), check_in, check_out,
                    nights, data.get("num_guests"),
                    data.get("status", "confirmed"),
                    1 if data.get("whatsapp_consent", True) else 0,
                ),
            )
            reservation_id = cur.lastrowid
            created = True

    scheduled = schedule_reservation_messages(reservation_id) if payload.event_type != "reservation_cancelled" else []

    if payload.event_type == "reservation_cancelled":
        with get_conn() as conn:
            conn.execute(
                "UPDATE reservations SET status='cancelled' WHERE id=?",
                (reservation_id,),
            )
            conn.execute(
                "UPDATE scheduled_messages SET status='cancelled' WHERE reservation_id=? AND status='pending'",
                (reservation_id,),
            )

    return {
        "status": "ok",
        "created": created,
        "reservation_id": reservation_id,
        "scheduled_messages": scheduled,
    }

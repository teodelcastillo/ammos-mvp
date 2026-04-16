"""Programación de mensajes automáticos y worker que los envía."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from config import TIMEZONE
from db import get_conn, row_to_dict
from templates import TEMPLATES, all_templates, get_template
from whatsapp import send_text

logger = logging.getLogger(__name__)


def _load_property(conn, property_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM properties WHERE id = ?", (property_id,)
    ).fetchone()
    return row_to_dict(row)


def _load_reservation(conn, reservation_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM reservations WHERE id = ?", (reservation_id,)
    ).fetchone()
    return row_to_dict(row)


def schedule_reservation_messages(reservation_id: int) -> list[dict]:
    """Calcula y guarda todos los mensajes automáticos para una reserva.

    Idempotente gracias al UNIQUE(reservation_id, template_key): si ya
    existe un scheduled_message para ese template, lo deja como está.
    """
    created = []
    with get_conn() as conn:
        res = _load_reservation(conn, reservation_id)
        if not res:
            return []
        prop = _load_property(conn, res["property_id"])
        if not prop:
            return []

        tz = ZoneInfo(prop.get("timezone") or TIMEZONE)

        for tpl in all_templates():
            scheduled_at = tpl.schedule(res, tz)
            if scheduled_at is None:
                continue

            # SQLite guarda datetimes como texto ISO
            iso = scheduled_at.astimezone(ZoneInfo("UTC")).isoformat()

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO scheduled_messages
                    (reservation_id, template_key, scheduled_at, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (reservation_id, tpl.key, iso),
            )
            if cur.rowcount:
                created.append({"template_key": tpl.key, "scheduled_at": iso})

    logger.info("Reserva %s → %d mensajes programados", reservation_id, len(created))
    return created


def _parse_dt(value: str) -> datetime:
    # SQLite retorna el ISO con offset si lo insertamos así
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def process_due_messages(limit: int = 50) -> int:
    """Envía todos los mensajes `pending` cuyo scheduled_at ya pasó."""
    now_utc = datetime.now(ZoneInfo("UTC"))
    sent = 0

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT sm.*, r.guest_phone, r.guest_name, r.property_id
            FROM scheduled_messages sm
            JOIN reservations r ON r.id = sm.reservation_id
            WHERE sm.status = 'pending'
            ORDER BY sm.scheduled_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        due = [dict(r) for r in rows if _parse_dt(r["scheduled_at"]) <= now_utc]

    for job in due:
        await _send_scheduled(job)
        sent += 1

    return sent


async def _send_scheduled(job: dict) -> None:
    template_key = job["template_key"]
    reservation_id = job["reservation_id"]

    with get_conn() as conn:
        res = _load_reservation(conn, reservation_id)
        prop = _load_property(conn, job["property_id"]) if res else None

    if not res or not prop:
        _mark_failed(job["id"], "reserva o propiedad no encontrada")
        return

    if res.get("status") in ("cancelled", "canceled"):
        _mark_status(job["id"], "cancelled")
        return

    if not res.get("whatsapp_consent"):
        _mark_failed(job["id"], "sin consentimiento WhatsApp")
        return

    tpl = get_template(template_key)
    if not tpl:
        _mark_failed(job["id"], f"template desconocido: {template_key}")
        return

    try:
        text = tpl.render(res, prop)
    except Exception as exc:
        _mark_failed(job["id"], f"render error: {exc}")
        return

    result = await send_text(res["guest_phone"], text)

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE scheduled_messages
            SET status = ?, rendered_text = ?, sent_at = CURRENT_TIMESTAMP,
                whatsapp_message_id = ?, attempt = attempt + 1,
                error = ?
            WHERE id = ?
            """,
            (
                "sent" if result.get("status") in ("sent", "dry-run") else "failed",
                text,
                result.get("message_id"),
                result.get("error"),
                job["id"],
            ),
        )

        conn.execute(
            """
            INSERT INTO message_logs
              (reservation_id, property_id, chat, guest_phone, direction,
               message_type, template_key, content, whatsapp_message_id, status, error)
            VALUES (?, ?, ?, ?, 'out', 'template', ?, ?, ?, ?, ?)
            """,
            (
                reservation_id,
                prop["id"],
                result.get("to"),
                res["guest_phone"],
                template_key,
                text,
                result.get("message_id"),
                result.get("status"),
                result.get("error"),
            ),
        )


def _mark_status(job_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE scheduled_messages SET status = ? WHERE id = ?",
            (status, job_id),
        )


def _mark_failed(job_id: int, error: str) -> None:
    logger.warning("scheduled_message %s falló: %s", job_id, error)
    with get_conn() as conn:
        conn.execute(
            "UPDATE scheduled_messages SET status='failed', error=?, attempt=attempt+1 WHERE id=?",
            (error, job_id),
        )

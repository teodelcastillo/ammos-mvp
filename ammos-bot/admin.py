"""Endpoints administrativos: propiedades, reservas, FAQs, disparos manuales."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from config import ADMIN_TOKEN
from db import get_conn, normalize_phone, rows_to_list
from scheduler import schedule_reservation_messages
from templates import TEMPLATES, get_template
from whatsapp import send_text

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(x_admin_token: str = Header(default="")) -> None:
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido")


# ---------- Properties ----------

class PropertyIn(BaseModel):
    external_id: Optional[str] = None
    name: str
    address: Optional[str] = None
    timezone: Optional[str] = "America/Argentina/Cordoba"
    wifi_name: Optional[str] = None
    wifi_password: Optional[str] = None
    door_code: Optional[str] = None
    check_in_time: Optional[str] = "15:00"
    check_out_time: Optional[str] = "11:00"
    host_phone: Optional[str] = None
    amenities: Optional[str] = None
    house_rules: Optional[str] = None
    notes: Optional[str] = None


@router.post("/properties", dependencies=[Depends(require_admin)])
async def create_property(payload: PropertyIn):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO properties
              (external_id, name, address, timezone, wifi_name, wifi_password,
               door_code, check_in_time, check_out_time, host_phone, amenities,
               house_rules, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.external_id, payload.name, payload.address, payload.timezone,
                payload.wifi_name, payload.wifi_password, payload.door_code,
                payload.check_in_time, payload.check_out_time, payload.host_phone,
                payload.amenities, payload.house_rules, payload.notes,
            ),
        )
        return {"id": cur.lastrowid}


@router.get("/properties", dependencies=[Depends(require_admin)])
async def list_properties():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM properties ORDER BY id").fetchall()
    return {"properties": rows_to_list(rows)}


# ---------- Reservations ----------

class ReservationIn(BaseModel):
    external_id: Optional[str] = None
    source: Optional[str] = "manual"
    property_id: int
    guest_name: str
    guest_phone: str
    guest_email: Optional[str] = None
    guest_language: Optional[str] = "es"
    check_in_date: date
    check_out_date: date
    num_guests: Optional[int] = None
    status: Optional[str] = "confirmed"
    whatsapp_consent: bool = True
    notes: Optional[str] = None


@router.post("/reservations", dependencies=[Depends(require_admin)])
async def create_reservation(payload: ReservationIn):
    nights = (payload.check_out_date - payload.check_in_date).days
    phone = normalize_phone(payload.guest_phone)

    with get_conn() as conn:
        prop = conn.execute(
            "SELECT id FROM properties WHERE id = ?", (payload.property_id,)
        ).fetchone()
        if not prop:
            raise HTTPException(status_code=400, detail="property_id inválido")

        cur = conn.execute(
            """
            INSERT INTO reservations
              (external_id, source, property_id, guest_name, guest_phone, guest_email,
               guest_language, check_in_date, check_out_date, nights, num_guests,
               status, whatsapp_consent, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.external_id, payload.source, payload.property_id,
                payload.guest_name, phone, payload.guest_email,
                payload.guest_language, payload.check_in_date, payload.check_out_date,
                nights, payload.num_guests, payload.status,
                1 if payload.whatsapp_consent else 0, payload.notes,
            ),
        )
        reservation_id = cur.lastrowid

    scheduled = schedule_reservation_messages(reservation_id)
    return {"id": reservation_id, "nights": nights, "scheduled": scheduled}


@router.get("/reservations", dependencies=[Depends(require_admin)])
async def list_reservations(property_id: int | None = None):
    with get_conn() as conn:
        if property_id:
            rows = conn.execute(
                "SELECT * FROM reservations WHERE property_id = ? ORDER BY check_in_date DESC",
                (property_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reservations ORDER BY check_in_date DESC LIMIT 200"
            ).fetchall()
    return {"reservations": rows_to_list(rows)}


@router.get("/reservations/{reservation_id}/messages", dependencies=[Depends(require_admin)])
async def reservation_messages(reservation_id: int):
    with get_conn() as conn:
        scheduled = conn.execute(
            "SELECT * FROM scheduled_messages WHERE reservation_id = ? ORDER BY scheduled_at",
            (reservation_id,),
        ).fetchall()
        logs = conn.execute(
            "SELECT * FROM message_logs WHERE reservation_id = ? ORDER BY created_at",
            (reservation_id,),
        ).fetchall()
    return {
        "scheduled": rows_to_list(scheduled),
        "logs": rows_to_list(logs),
    }


# ---------- FAQs ----------

class FaqIn(BaseModel):
    property_id: Optional[int] = None
    category: Optional[str] = None
    question: str
    answer: str
    keywords: Optional[str] = None
    is_global: bool = False


@router.post("/faqs", dependencies=[Depends(require_admin)])
async def create_faq(payload: FaqIn):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO faqs (property_id, category, question, answer, keywords, is_global)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.property_id, payload.category, payload.question,
                payload.answer, payload.keywords, 1 if payload.is_global else 0,
            ),
        )
        return {"id": cur.lastrowid}


@router.get("/faqs", dependencies=[Depends(require_admin)])
async def list_faqs(property_id: int | None = None):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM faqs WHERE ? IS NULL OR property_id = ? OR is_global = 1",
            (property_id, property_id),
        ).fetchall()
    return {"faqs": rows_to_list(rows)}


# ---------- Manual trigger (para demos) ----------

class SendTemplateIn(BaseModel):
    reservation_id: int
    template_key: str


@router.post("/send-template", dependencies=[Depends(require_admin)])
async def send_template_now(payload: SendTemplateIn):
    tpl = get_template(payload.template_key)
    if not tpl:
        raise HTTPException(status_code=400, detail="template_key inválido")

    with get_conn() as conn:
        res_row = conn.execute(
            "SELECT * FROM reservations WHERE id = ?", (payload.reservation_id,)
        ).fetchone()
        if not res_row:
            raise HTTPException(status_code=404, detail="reserva no encontrada")
        res = dict(res_row)

        prop_row = conn.execute(
            "SELECT * FROM properties WHERE id = ?", (res["property_id"],)
        ).fetchone()
        prop = dict(prop_row)

    text = tpl.render(res, prop)
    result = await send_text(res["guest_phone"], text)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO message_logs
              (reservation_id, property_id, chat, guest_phone, direction,
               message_type, template_key, content, status, error)
            VALUES (?, ?, ?, ?, 'out', 'template_manual', ?, ?, ?, ?)
            """,
            (
                res["id"], prop["id"], result.get("to"), res["guest_phone"],
                payload.template_key, text, result.get("status"), result.get("error"),
            ),
        )

    return {"rendered": text, "result": result}


@router.get("/templates", dependencies=[Depends(require_admin)])
async def list_templates():
    return {
        "templates": [
            {"key": t.key, "description": t.description}
            for t in TEMPLATES.values()
        ]
    }


@router.get("/logs", dependencies=[Depends(require_admin)])
async def recent_logs(limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM message_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"logs": rows_to_list(rows)}

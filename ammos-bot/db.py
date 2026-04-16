"""SQLite para el MVP de AMMOS: propiedades, reservas, FAQs, templates y logs."""

import os
import sqlite3
from contextlib import contextmanager

from config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id        TEXT UNIQUE,
    name               TEXT NOT NULL,
    address            TEXT,
    timezone           TEXT DEFAULT 'America/Argentina/Cordoba',
    wifi_name          TEXT,
    wifi_password      TEXT,
    door_code          TEXT,
    check_in_time      TEXT DEFAULT '15:00',
    check_out_time     TEXT DEFAULT '11:00',
    host_phone         TEXT,
    amenities          TEXT,
    house_rules        TEXT,
    notes              TEXT,
    created_at         DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reservations (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id        TEXT UNIQUE,
    source             TEXT,
    property_id        INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    guest_name         TEXT NOT NULL,
    guest_phone        TEXT NOT NULL,
    guest_email        TEXT,
    guest_language     TEXT DEFAULT 'es',
    check_in_date      DATE NOT NULL,
    check_out_date     DATE NOT NULL,
    nights             INTEGER,
    num_guests         INTEGER,
    status             TEXT DEFAULT 'confirmed',
    whatsapp_consent   INTEGER DEFAULT 1,
    notes              TEXT,
    created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_res_phone    ON reservations(guest_phone);
CREATE INDEX IF NOT EXISTS idx_res_checkin  ON reservations(check_in_date);
CREATE INDEX IF NOT EXISTS idx_res_property ON reservations(property_id);

CREATE TABLE IF NOT EXISTS scheduled_messages (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id         INTEGER NOT NULL REFERENCES reservations(id) ON DELETE CASCADE,
    template_key           TEXT NOT NULL,
    scheduled_at           DATETIME NOT NULL,
    status                 TEXT DEFAULT 'pending',
    rendered_text          TEXT,
    sent_at                DATETIME,
    whatsapp_message_id    TEXT,
    attempt                INTEGER DEFAULT 0,
    error                  TEXT,
    created_at             DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(reservation_id, template_key)
);

CREATE INDEX IF NOT EXISTS idx_sm_status ON scheduled_messages(status, scheduled_at);

CREATE TABLE IF NOT EXISTS faqs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id   INTEGER REFERENCES properties(id) ON DELETE CASCADE,
    category      TEXT,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    keywords      TEXT,
    is_global     INTEGER DEFAULT 0,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_faq_property ON faqs(property_id);

CREATE TABLE IF NOT EXISTS message_logs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id        INTEGER REFERENCES reservations(id),
    property_id           INTEGER REFERENCES properties(id),
    chat                  TEXT,
    guest_phone           TEXT,
    direction             TEXT NOT NULL,
    message_type          TEXT,
    template_key          TEXT,
    content               TEXT,
    whatsapp_message_id   TEXT,
    status                TEXT,
    error                 TEXT,
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_log_phone ON message_logs(guest_phone, created_at);

CREATE TABLE IF NOT EXISTS webhook_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT UNIQUE,
    source        TEXT,
    event_type    TEXT,
    payload       TEXT,
    processed_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row) -> dict | None:
    return dict(row) if row else None


def rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


def normalize_phone(phone: str) -> str:
    """Deja el teléfono como solo dígitos con código de país.

    Acepta formatos como '+54 9 11 1234-5678', '5491112345678',
    '5491112345678@s.whatsapp.net', etc.
    """
    if not phone:
        return ""
    # Si viene un JID de WhatsApp, tomar la parte del usuario
    if "@" in phone:
        phone = phone.split("@", 1)[0]
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits

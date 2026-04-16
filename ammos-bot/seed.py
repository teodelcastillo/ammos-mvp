"""Datos de prueba para el MVP interno.

Uso dentro del contenedor:
    docker compose exec ammos-bot python seed.py
"""

from datetime import date, timedelta

from db import get_conn, init_db


PROPERTIES = [
    {
        "external_id": "AMMOS-001",
        "name": "Casa Bella Córdoba",
        "address": "Calle Falsa 123, Nueva Córdoba",
        "timezone": "America/Argentina/Cordoba",
        "wifi_name": "CasaBella_WiFi",
        "wifi_password": "bienvenidos2026",
        "door_code": "4821",
        "check_in_time": "15:00",
        "check_out_time": "11:00",
        "host_phone": "+54 351 555-0100",
        "amenities": "Pileta climatizada, parrilla, cochera, aire acondicionado",
        "house_rules": "No fiestas. No fumar adentro. Silencio después de las 23:00.",
        "notes": "Supermercado Disco a 3 cuadras. Farmacia 24hs a 2 cuadras.",
    },
    {
        "external_id": "AMMOS-002",
        "name": "Depto Costanera Mar del Plata",
        "address": "Bv. Marítimo 2100, MDQ",
        "timezone": "America/Argentina/Buenos_Aires",
        "wifi_name": "Costanera_2A",
        "wifi_password": "olas12345",
        "door_code": "9981",
        "check_in_time": "16:00",
        "check_out_time": "10:00",
        "host_phone": "+54 223 555-0200",
        "amenities": "Vista al mar, ascensor, cocina equipada, smart TV",
        "house_rules": "Mascotas bajo consulta. No se permite fumar.",
        "notes": "Playa pública a 50m. Estacionamiento en la calle.",
    },
]

GLOBAL_FAQS = [
    {
        "category": "Check-in",
        "question": "¿A qué hora puedo hacer check-in?",
        "answer": "El check-in es a partir de las 15:00 en la mayoría de nuestras propiedades. Si querés entrar antes, avisanos y vemos disponibilidad.",
        "keywords": "check in checkin hora entrar llegar ingresar",
    },
    {
        "category": "Check-out",
        "question": "¿A qué hora es el check-out?",
        "answer": "El check-out es hasta las 11:00. Si necesitás un poco más de tiempo, escribinos y vemos cómo acomodarlo.",
        "keywords": "check out checkout hora salir irse egresar",
    },
    {
        "category": "Cancelación",
        "question": "¿Cómo cancelo mi reserva?",
        "answer": "Las cancelaciones se gestionan desde la plataforma donde reservaste (Airbnb, Booking o sitio directo). Si tenés un caso especial, contactanos al teléfono del anfitrión.",
        "keywords": "cancelar cancelacion reembolso devolucion",
    },
]

PROPERTY_FAQS = [
    {
        "property_external_id": "AMMOS-001",
        "category": "WiFi",
        "question": "¿Cuál es la contraseña del WiFi?",
        "answer": "La red es *CasaBella_WiFi* y la clave *bienvenidos2026*.",
        "keywords": "wifi internet clave contrasena password red",
    },
    {
        "property_external_id": "AMMOS-001",
        "category": "Estacionamiento",
        "question": "¿Dónde puedo estacionar?",
        "answer": "La casa tiene cochera propia con portón automático. También hay estacionamiento libre en la calle.",
        "keywords": "estacionar estacionamiento auto coche garage cochera",
    },
    {
        "property_external_id": "AMMOS-002",
        "category": "Playa",
        "question": "¿Qué tan cerca está la playa?",
        "answer": "La playa está a 50 metros del edificio, cruzando la costanera.",
        "keywords": "playa mar arena costa distancia cerca",
    },
]


def seed():
    init_db()
    with get_conn() as conn:
        id_by_ext = {}
        for p in PROPERTIES:
            existing = conn.execute(
                "SELECT id FROM properties WHERE external_id = ?", (p["external_id"],)
            ).fetchone()
            if existing:
                id_by_ext[p["external_id"]] = existing["id"]
                continue
            cur = conn.execute(
                """
                INSERT INTO properties
                  (external_id, name, address, timezone, wifi_name, wifi_password,
                   door_code, check_in_time, check_out_time, host_phone, amenities,
                   house_rules, notes)
                VALUES (:external_id, :name, :address, :timezone, :wifi_name,
                        :wifi_password, :door_code, :check_in_time, :check_out_time,
                        :host_phone, :amenities, :house_rules, :notes)
                """,
                p,
            )
            id_by_ext[p["external_id"]] = cur.lastrowid

        for f in GLOBAL_FAQS:
            exists = conn.execute(
                "SELECT id FROM faqs WHERE is_global = 1 AND question = ?",
                (f["question"],),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO faqs (category, question, answer, keywords, is_global)
                VALUES (?, ?, ?, ?, 1)
                """,
                (f["category"], f["question"], f["answer"], f["keywords"]),
            )

        for f in PROPERTY_FAQS:
            prop_id = id_by_ext.get(f["property_external_id"])
            if not prop_id:
                continue
            exists = conn.execute(
                "SELECT id FROM faqs WHERE property_id = ? AND question = ?",
                (prop_id, f["question"]),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO faqs (property_id, category, question, answer, keywords, is_global)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (prop_id, f["category"], f["question"], f["answer"], f["keywords"]),
            )

    print(f"Seed completado. Propiedades: {list(id_by_ext.keys())}")
    print("\nEjemplo para crear una reserva de prueba (ajustar teléfono):")
    today = date.today()
    payload = {
        "external_id": "TEST-001",
        "property_id": list(id_by_ext.values())[0],
        "guest_name": "Juan Test",
        "guest_phone": "5491112345678",
        "check_in_date": (today + timedelta(days=1)).isoformat(),
        "check_out_date": (today + timedelta(days=4)).isoformat(),
        "num_guests": 2,
    }
    print(payload)


if __name__ == "__main__":
    seed()

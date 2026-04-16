# AMMOS Vacation Rentals — Mini MVP

Prueba interna para el equipo de AMMOS. Reutiliza el `whatsapp-bridge`
(whatsmeow, vía QR) que ya está en este repo y agrega:

- Propiedades + reservas en SQLite
- Mensajes automáticos (confirmación, check-in, mid-stay, check-out, review)
- FAQs por propiedad + globales (match por keywords, sin embeddings)
- Respuestas con Claude usando contexto de reserva y propiedad
- Panel REST administrativo (crear propiedades, reservas, FAQs, disparar
  templates manualmente)
- Webhook simulado estilo Guestwisely para crear reservas desde "afuera"

> Intencionalmente **no** usa Meta Business Manager / 360dialog / Hostaway
> todavía. Es un MVP para que el equipo pruebe el flujo end-to-end.

## Cómo correr

Desde la raíz del repo:

```bash
cp .env.example .env   # completar ANTHROPIC_API_KEY y ADMIN_TOKEN
docker compose up --build whatsapp-bridge ammos-bot
```

1. Abrí `http://localhost:8080/qr` y escaneá el QR con el WhatsApp del número
   que va a actuar como "AMMOS".
2. Cargá datos de prueba:

   ```bash
   docker compose exec ammos-bot python seed.py
   ```

3. Por seguridad el envío real está **apagado por defecto** (`SEND_ENABLED=false`).
   Todos los mensajes se loguean en consola con `[dry-run]`. Cuando quieras
   mandar de verdad, poné `SEND_ENABLED=true` en el `.env` y reiniciá.

## Variables de entorno

| Variable             | Default                         | Descripción                                             |
|----------------------|---------------------------------|---------------------------------------------------------|
| `ANTHROPIC_API_KEY`  | —                               | Clave de Claude (obligatoria)                           |
| `ADMIN_TOKEN`        | `dev-token-change-me`           | Header `X-Admin-Token` para endpoints admin             |
| `SEND_ENABLED`       | `false`                         | Si es `true`, envía por el bridge; si no, dry-run       |
| `WA_BRIDGE_URL`      | `http://whatsapp-bridge:8080`   | URL del bridge                                          |
| `TIMEZONE`           | `America/Argentina/Cordoba`     | Zona horaria por defecto                                |
| `MAX_MSG_PER_SEC`    | `1`                             | Rate limit del sender                                   |
| `SCHEDULER_INTERVAL_SEC` | `30`                        | Cada cuánto revisa la cola de mensajes                  |
| `DB_PATH`            | `/app/data/ammos.db`            | Path de SQLite                                          |

## Endpoints

Todos los `/admin/*` requieren header `X-Admin-Token: <ADMIN_TOKEN>`.

- `POST /admin/properties` — crear propiedad
- `GET  /admin/properties`
- `POST /admin/reservations` — crear reserva (auto-agenda todos los templates)
- `GET  /admin/reservations?property_id=`
- `GET  /admin/reservations/{id}/messages` — ver cola + logs de la reserva
- `POST /admin/faqs` — alta de FAQ (global o por propiedad)
- `GET  /admin/faqs?property_id=`
- `GET  /admin/templates` — listar templates disponibles
- `POST /admin/send-template` — `{reservation_id, template_key}` dispara ya
- `GET  /admin/logs?limit=`

Webhooks:

- `POST /webhook` — entrante desde `whatsapp-bridge` (ya configurado en compose)
- `POST /webhooks/reservations` — simula Guestwisely (ver payload abajo)

## Flujo típico de prueba

1. Seed: `docker compose exec ammos-bot python seed.py`
2. Crear reserva con tu propio número:

   ```bash
   curl -X POST http://localhost:8001/admin/reservations \
     -H "Content-Type: application/json" \
     -H "X-Admin-Token: dev-token-change-me" \
     -d '{
       "property_id": 1,
       "guest_name": "Juan Test",
       "guest_phone": "5491112345678",
       "check_in_date": "2026-04-18",
       "check_out_date": "2026-04-21",
       "num_guests": 2
     }'
   ```

   La respuesta muestra qué templates se agendaron y cuándo.

3. Disparar uno ya (para demo):

   ```bash
   curl -X POST http://localhost:8001/admin/send-template \
     -H "Content-Type: application/json" \
     -H "X-Admin-Token: dev-token-change-me" \
     -d '{"reservation_id": 1, "template_key": "checkin_instructions"}'
   ```

4. Mandale un WhatsApp al número del bot (el que escaneó el QR) desde el número
   del huésped. El bot va a:
   - Buscar FAQs matcheando keywords → responder si hay match
   - Sino, pasar a Claude con todo el contexto de la reserva + propiedad
   - Loguear todo en `message_logs`

## Webhook de reservaciones (simulación Guestwisely)

```bash
curl -X POST http://localhost:8001/webhooks/reservations \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "gw-evt-001",
    "event_type": "reservation_created",
    "source": "guestwisely",
    "reservation": {
      "external_id": "GW-123",
      "property_external_id": "AMMOS-001",
      "guest_name": "María Pérez",
      "guest_phone": "+54 911 5555-1234",
      "guest_email": "maria@example.com",
      "check_in_date": "2026-04-20",
      "check_out_date": "2026-04-25",
      "num_guests": 3,
      "status": "confirmed"
    }
  }'
```

Eventos `reservation_updated` y `reservation_cancelled` son idempotentes
(dedup por `event_id`).

## Qué queda afuera (a propósito)

- Meta Business Manager / API oficial de WhatsApp / 360dialog
- Integraciones reales con Hostaway/Booking/Airbnb
- Postgres/Redis (para este MVP alcanza SQLite in-container)
- Embeddings / búsqueda semántica de FAQs
- Warm-up, quality rating monitoring
- Auto-scaling (Fargate, workers separados)

Todos los módulos están ya estructurados para poder reemplazarlos sin cambiar
el resto del código (por ejemplo, `whatsapp.py` se puede swapear por un
cliente de 360dialog cuando esté la cuenta).

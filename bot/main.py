import asyncio
import logging
import os

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request, Header, HTTPException

from agent import process_message
from admin import router as admin_router
from lawyer import router as lawyer_router
from briefing import send_briefing
from db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("bot")

WA_BRIDGE_URL = os.getenv("WA_BRIDGE_URL", "http://whatsapp-bridge:8080")
BOT_TRIGGER = os.getenv("BOT_TRIGGER", "lexia").lower()
_raw_allowed = os.getenv("ALLOWED_CHATS", "")
ALLOWED_CHATS: set[str] = {j.strip() for j in _raw_allowed.split(",") if j.strip()}

# Briefing: hora en formato "HH:MM" (zona America/Argentina/Cordoba)
BRIEFING_TIME = os.getenv("BRIEFING_TIME", "08:00")
# Token para disparar el briefing manualmente vía POST /trigger/briefing
BRIEFING_TOKEN = os.getenv("BRIEFING_TOKEN", "")

scheduler = AsyncIOScheduler(timezone="America/Argentina/Cordoba")

app = FastAPI(title="Del Castillo Bot")
app.include_router(admin_router)
app.include_router(lawyer_router)

@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Base de datos inicializada")

    hour, minute = BRIEFING_TIME.split(":")
    scheduler.add_job(send_briefing, CronTrigger(hour=int(hour), minute=int(minute)))
    scheduler.start()
    logger.info("Scheduler iniciado — briefing diario a las %s (Córdoba)", BRIEFING_TIME)


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)


@app.post("/trigger/briefing")
async def trigger_briefing(x_token: str = Header(default="")):
    """Dispara el briefing manualmente. Requiere header X-Token."""
    if BRIEFING_TOKEN and x_token != BRIEFING_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido")
    asyncio.create_task(send_briefing())
    return {"status": "briefing enviado"}


@app.post("/webhook")
async def webhook(request: Request):
    """Receive a message from the WhatsApp bridge and process it async."""
    data = await request.json()
    asyncio.create_task(_process_and_respond(data))
    return {"status": "received"}


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _process_and_respond(data: dict):
    chat = data["chat"]
    sender_name = data.get("sender_name", "Usuario")
    message = data.get("message", "")

    if not message:
        return

    # Solo responder si el chat está en la whitelist (si está configurada)
    if ALLOWED_CHATS and chat not in ALLOWED_CHATS:
        logger.debug("Ignored message from %s in %s (not in ALLOWED_CHATS)", sender_name, chat)
        return

    # Solo responder si el mensaje menciona el nombre del bot
    if BOT_TRIGGER not in message.lower():
        logger.debug("Ignored message from %s (trigger '%s' not found)", sender_name, BOT_TRIGGER)
        return

    logger.info("Processing message from %s: %s", sender_name, message[:100])

    try:
        response_text = await process_message(message, sender_name, chat)
    except Exception:
        logger.exception("Error processing message")
        response_text = "Hubo un error procesando tu mensaje. Intentá de nuevo en unos minutos."

    # Send response back through WhatsApp bridge
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                f"{WA_BRIDGE_URL}/send",
                json={"chat": chat, "message": response_text},
            )
        logger.info("Response sent to %s", chat)
    except Exception:
        logger.exception("Error sending response to bridge")

import asyncio
import logging
import os

import httpx
from fastapi import FastAPI, Request

from agent import process_message
from db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("bot")

WA_BRIDGE_URL = os.getenv("WA_BRIDGE_URL", "http://whatsapp-bridge:8080")

app = FastAPI(title="Del Castillo Bot")

@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Base de datos inicializada")


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
